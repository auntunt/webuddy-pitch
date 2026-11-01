"""What an agent hands back for the platform to act on: a fixed block per step, never guessed from its prose.

analyze ends with ```tmh-report {"refs": [{"path", "line"}], "human_action": ""}```, plan with ```tmh-plan```,
diagnose with ```tmh-diag```. An answer whose block is missing or broken gets one format repair: the same
executor is shown its own answer and asked for the block only, with no new analysis. A question for a person is
the report's `human_action`, not something read out of the text (after dsh-superagent's `human_action`).
"""
from __future__ import annotations

import re

LABEL = {"analyze": "tmh-report", "plan": "tmh-plan", "diagnose": "tmh-diag"}

SHAPE = {
    "analyze": '{"refs": [{"path": "相对路径", "line": 78}], "human_action": ""}',
    "plan": '{"files": [{"path": "相对路径", "goal": "这个文件要做到什么", "role": "改动|调用方|配置|测试"}], '
            '"ac": [{"id": "A1", "text": "做到什么算修好", "layer": "L1|L2|L3|L4", "check": "怎么检查"}]}',
    "diagnose": '{"verdict": "pass 或 fail", "blocking": [{"ac": "没做到的验收标准", "scenario": "输入或操作 → 错误结果", '
                '"where": "文件:行号"}], "advisory": [], "ac": [{"id": "A1", "result": "pass / fail / unverified", "how": "依据"}], '
                '"match": "equivalent / partial / different / wrong", "match_why": "", "evidence": "", "cause": "", '
                '"files": [{"path": "相对路径", "goal": ""}], "guide": ""}',
}

ANALYZE_REPORT = """
最后附上一个机器读的结论块（平台只读这个块决定下一步，不从正文里猜）：
- refs：正文里给出的代码位置，每处一个 path（相对项目根目录）和 line（数字）；没找到就写 []。
- human_action：只有在不问人就没法往下做时，才写一个具体的问题（比如两种业务口径只能由客户定）；能按合理假设继续的写进正文的“待确认问题”，这里留空。
```tmh-report
%s
```""" % SHAPE["analyze"]


def block(mode: str, text: str):
    """The step's block as a dict, or None when it is missing, broken or not the right shape."""
    from .fixloop import fenced
    label = LABEL.get(mode)
    j = fenced(label, text) if label else None
    if not isinstance(j, dict):
        return None
    if mode == "analyze" and not isinstance(j.get("refs"), list):
        return None
    if mode == "plan" and not (isinstance(j.get("files"), list) and isinstance(j.get("ac"), list)):
        return None
    if mode == "diagnose" and str(j.get("verdict") or "").strip().lower() not in ("pass", "fail"):
        return None
    return j


def refs(text: str):
    """Code locations the analysis report names as (path, line) pairs; None when it has no report."""
    from .fixloop import rel_path
    j = block("analyze", text)
    if j is None:
        return None
    out = []
    for r in j["refs"]:
        if not isinstance(r, dict):
            continue
        path, line = rel_path(r.get("path")), str(r.get("line") or "").strip()
        if path and line.isdigit() and int(line) > 0:
            out.append((path, line))
    return out


def human_action(text: str) -> str:
    """The question the analysis says only a person can answer ("" for none)."""
    j = block("analyze", text) or {}
    q = j.get("human_action")
    return q.strip()[:500] if isinstance(q, str) else ""


def repair_prompt(mode: str, answer: str) -> str:
    return ("## 你的任务：补上机器读的结尾块（只读，不要修改任何文件）\n"
            "下面是你刚才这一步的回答。它缺少平台要读的结尾块，或者块的格式不对。\n"
            "只根据这份回答本身输出这个块：不要重新分析，不要查代码，不要增加或改动任何结论；回答里没有的内容就留空或写 []。\n"
            "只输出这一个代码块，块里是合法 JSON（字符串里的双引号要转义）：\n"
            "```%s\n%s\n```\n\n## 刚才的回答\n%s" % (LABEL[mode], SHAPE[mode], (answer or "")[-12000:]))


def repair(mode: str, answer: str, ask) -> tuple[str, bool]:
    """`answer` with its block, asking the executor once (`ask(prompt) -> text`) when it is missing.
    Returns (answer, repaired). A repair that still has no usable block leaves the answer as it was."""
    if mode not in LABEL or block(mode, answer) is not None or not (answer or "").strip():
        return answer, False
    try:
        out = ask(repair_prompt(mode, answer)) or ""
    except Exception:  # noqa: BLE001 - a failed repair keeps the original answer and its outcome
        return answer, False
    if block(mode, out) is None:
        return answer, False
    from .fixloop import FENCE
    fixed = re.findall(FENCE % re.escape(LABEL[mode]), out, re.DOTALL)
    if not fixed:  # the block came wrapped some other way: keep the answer, the reader handles those forms too
        return answer.rstrip() + "\n\n" + out.strip(), True
    return answer.rstrip() + "\n\n```%s\n%s\n```" % (LABEL[mode], fixed[-1].strip()), True
