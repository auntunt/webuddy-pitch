"""业务状态图: each business flow drawn as states and the steps between them, with the rules a reader agrees to.

An agent in "chart" mode reads the code and writes one JSON file per chart under .tmh/knowledge/statecharts/.
This module only reads those files back for the page: it checks their shape, and marks a chart "代码改了" when
a file one of its rules cites changed after the commit the chart was drawn from. It never writes them.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

DIR = Path(".tmh") / "knowledge" / "statecharts"
STATUSES = ("待确认", "已确认")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
WHERE = re.compile(r"^([^:\s]+\.[A-Za-z0-9]+)(?::\d+(?:-\d+)?)?$")
MAX_BYTES = 200_000

FORMAT = """{
  "title": "主人与宠物",
  "domain": "dom:owner",
  "commit": "画图时 git rev-parse HEAD 的结果",
  "mermaid": "stateDiagram-v2\\n  state \\"查找主人\\" as find\\n  [*] --> find\\n  find --> detail: 只有一人",
  "rules": [{"text": "主人电话必须是 10 位数字", "where": "src/main/java/.../Owner.java:64", "holds": true}],
  "paths": [{"rule": 0, "steps": [{"state": "detail", "note": "按钮已经不见了"}, {"state": "addpet", "note": "直接打开 /owners/1/pets/new"}]}]
}"""


def _str(v, n=400) -> str:
    return v.strip()[:n] if isinstance(v, str) else ""


def _transitions(mermaid: str) -> list:
    """The `a --> b` lines in order: Pele numbers its edges the same way (edge0, edge1, ...)."""
    out = []
    for line in mermaid.splitlines():
        m = re.match(r"^\s*(\[\*\]|[\w.-]+)\s*-->\s*(\[\*\]|[\w.-]+)", line)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def _states(mermaid: str) -> set:
    names = set(re.findall(r'state\s+"[^"]*"\s+as\s+([\w.-]+)', mermaid))
    for a, b in _transitions(mermaid):
        names.update(x for x in (a, b) if x != "[*]")
    return names


def check(cid: str, data) -> dict:
    """One chart in the shape the page draws, with `problems` saying what the file got wrong."""
    problems = []
    if not isinstance(data, dict):
        return {"id": cid, "title": cid, "problems": ["文件不是 JSON 对象"]}
    mermaid = data.get("mermaid") if isinstance(data.get("mermaid"), str) else ""
    if not mermaid.lstrip().startswith("stateDiagram"):
        problems.append("mermaid 必须是 stateDiagram-v2 状态图")
    states, edges = _states(mermaid), _transitions(mermaid)
    rules = []
    for r in data.get("rules") if isinstance(data.get("rules"), list) else []:
        if not isinstance(r, dict) or not _str(r.get("text")):
            problems.append("有一条规则没有写内容")
            continue
        rules.append({"text": _str(r.get("text"), 200), "where": _str(r.get("where"), 300), "holds": r.get("holds") is not False})
    paths = []
    for p in data.get("paths") if isinstance(data.get("paths"), list) else []:
        if not isinstance(p, dict):
            continue
        rule = p.get("rule")
        if not isinstance(rule, int) or not 0 <= rule < len(rules):
            problems.append("问题路径没有指向一条规则")
            continue
        steps = []
        for s in p.get("steps") if isinstance(p.get("steps"), list) else []:
            st = _str((s or {}).get("state"), 64) if isinstance(s, dict) else ""
            if st not in states:
                problems.append(f"问题路径里的状态 {st or '（空）'} 不在图里")
                steps = []
                break
            steps.append({"state": st, "note": _str(s.get("note"), 200)})
        if steps:
            seq = [s["state"] for s in steps]
            # the edges between consecutive steps, by Pele's numbering; a step with no drawn edge is still listed
            ids = []
            for a, b in zip(seq, seq[1:]):
                ids += [f"edge{i}" for i, e in enumerate(edges) if e == (a, b)][:1]
            paths.append({"rule": rule, "steps": steps, "edges": ids})
    for p in paths:
        rules[p["rule"]]["holds"] = False
    status = data.get("status") if data.get("status") in STATUSES else "待确认"
    return {"id": cid, "title": _str(data.get("title"), 80) or cid, "domain": _str(data.get("domain"), 80), "status": status,
            "commit": _str(data.get("commit"), 64), "mermaid": mermaid[:20000], "rules": rules, "paths": paths, "problems": problems}


def _changed(root: Path, commit: str, files: list) -> list:
    if not commit or not files or not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit):
        return []
    try:
        r = subprocess.run(["git", "-C", str(root), "diff", "--name-only", commit, "HEAD", "--", *files],
                           capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    return [x for x in r.stdout.splitlines() if x] if r.returncode == 0 else []


def load(root: Path) -> list:
    d = Path(root) / DIR
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        cid = f.stem
        if not ID.match(cid) or f.is_symlink():
            continue
        try:
            raw = f.read_bytes()
            c = check(cid, json.loads(raw.decode("utf-8"))) if len(raw) <= MAX_BYTES else {"id": cid, "title": cid, "problems": ["文件太大"]}
        except (OSError, ValueError) as e:
            c = {"id": cid, "title": cid, "problems": [f"读不出来：{type(e).__name__}"]}
        files = sorted({m.group(1) for r in c.get("rules", []) for m in [WHERE.match(r["where"])] if m})
        c["changed"] = _changed(root, c.get("commit", ""), files)
        out.append(c)
    return out
