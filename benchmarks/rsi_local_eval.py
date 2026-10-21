"""Local-model RSI baseline: can a retrieved context pack help a 9B model find files?

The RSI (recursive self-improvement) flywheel needs a measured baseline for
"the agent with project context vs the agent without it". This module supplies
that experiment for the checked-in example project:

* a fixed set of file-level "改哪里" tasks (Chinese requirement + gold files);
* three conditions with the same local Ollama model — ``cold`` (requirement
  only), ``pack-4000`` and ``pack-8000`` (the same requirement plus a real
  ``tmh.context_pack.assemble`` pack);
* a strict JSON-array answer parser, file metrics (recall / precision / exact),
  latency and token accounting, and explicit failure kinds (timeout / http /
  empty / parse / unavailable) instead of crashing.

Nothing here talks to the network by itself: ``OllamaClient`` accepts injectable
transport functions, which is what the offline tests use. ``run_rsi_local.py`` is
the real run over the local Ollama daemon.
"""
from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

from tmh.context_quality import estimate_tokens

SCHEMA = 1
OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "qwen3.5:9b"
DEFAULT_MAX_TOKENS = 512
DEFAULT_TIMEOUT = 180
THINK = False  # measured: think=True burns the whole max_tokens on reasoning (800/800 tokens)
CONDITIONS = ("cold", "pack-4000", "pack-8000")
PACK_BUDGET = {"pack-4000": 4000, "pack-8000": 8000}
ANSWER_RULE = "只输出一个 JSON 数组，元素是仓库相对路径；没有把握就输出 []。不要输出解释。"

# 16 file-level "change where" tasks. The gold set is the files that must be
# touched for the stated behaviour change; it was checked against the real
# example project (controllers / services / mappers / xml / schema / config).
TASKS = [
    {"id": "t01", "query": "报销单提交时单笔金额上限现在是 5 万，业务要改成 8 万",
     "gold": ["src/main/java/com/acme/oa/service/ExpenseService.java"]},
    {"id": "t02", "query": "财务审核驳回报销单以后要把冻结的部门预算释放掉，现在这条分支漏了释放",
     "gold": ["src/main/java/com/acme/oa/service/ExpenseService.java"]},
    {"id": "t03", "query": "出纳付款成功以后要额外写一条付款流水记录，现在只更新报销单状态",
     "gold": ["src/main/java/com/acme/oa/service/ExpenseService.java",
              "src/main/resources/mapper/ExpenseMapper.xml", "sql/schema.sql"]},
    {"id": "t04", "query": "请假超过 3 天必须部门经理审批，现在只有一行注释，要补成真正的校验逻辑",
     "gold": ["src/main/java/com/acme/oa/service/LeaveService.java"]},
    {"id": "t05", "query": "请假单列表分页查询要支持按部门过滤",
     "gold": ["src/main/resources/mapper/LeaveMapper.xml",
              "src/main/java/com/acme/oa/service/LeaveService.java",
              "src/main/java/com/acme/oa/controller/LeaveController.java"]},
    {"id": "t06", "query": "请假审批通过时要同时记录审批人工号，现在审批人字段长度不够存工号",
     "gold": ["src/main/resources/mapper/LeaveMapper.xml", "sql/schema.sql"]},
    {"id": "t07", "query": "超期未审批的请假单除了每天凌晨自动作废，还要提供一个手动触发的 HTTP 接口",
     "gold": ["src/main/java/com/acme/oa/controller/LeaveController.java",
              "src/main/java/com/acme/oa/service/LeaveService.java"]},
    {"id": "t08", "query": "每晚导出请假汇总改成生成 Excel 文件并上传到文件服务器共享目录",
     "gold": ["src/main/java/com/acme/oa/job/ReportJob.java", "pom.xml"]},
    {"id": "t09", "query": "用户密码从 MD5 换成 BCrypt，并且要能兼容校验历史 MD5 密码",
     "gold": ["src/main/java/com/acme/oa/util/PasswordUtil.java", "pom.xml"]},
    {"id": "t10", "query": "请假列表分页用的是 Oracle ROWNUM 写法，数据库迁到达梦后要改分页 SQL",
     "gold": ["src/main/resources/mapper/LeaveMapper.xml"]},
    {"id": "t11", "query": "付款时调用财务系统的接口 URL 写死在 Java 代码里，要挪到配置文件",
     "gold": ["src/main/java/com/acme/oa/service/ExpenseService.java", "src/main/resources/application.yml"]},
    {"id": "t12", "query": "请假统计现在靠数据库存储过程，要改成应用内定时统计任务",
     "gold": ["src/main/java/com/acme/oa/job/ReportJob.java",
              "src/main/java/com/acme/oa/service/LeaveService.java", "sql/schema.sql"]},
    {"id": "t13", "query": "报销单打印页面要加公司抬头和打印时间",
     "gold": ["src/main/webapp/print.jsp"]},
    {"id": "t14", "query": "新增用户时如果工号重复只抛异常，要求同时记录一条操作日志",
     "gold": ["src/main/java/com/acme/oa/service/UserService.java",
              "src/main/java/com/acme/oa/mapper/ApprovalLogMapper.java",
              "src/main/resources/mapper/ApprovalLogMapper.xml"]},
    {"id": "t15", "query": "用户被停用后，他名下进行中的请假单要自动转交给同部门其他人",
     "gold": ["src/main/java/com/acme/oa/service/UserService.java",
              "src/main/java/com/acme/oa/service/LeaveService.java",
              "src/main/resources/mapper/LeaveMapper.xml"]},
    {"id": "t16", "query": "报销单列表按用户查询时要支持再按部门过滤",
     "gold": ["src/main/resources/mapper/ExpenseMapper.xml",
              "src/main/java/com/acme/oa/service/ExpenseService.java",
              "src/main/java/com/acme/oa/controller/ExpenseController.java"]},
]


# ---- answer parsing ---------------------------------------------------------
def _json_values(text: str) -> list:
    """Every JSON value embedded in ``text`` (the model may wrap it in prose/fences)."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch not in "[{":
            i += 1
            continue
        depth, j, quote, esc = 0, i, "", False
        while j < n:
            c = text[j]
            if quote:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == quote:
                    quote = ""
            elif c in "\"'":
                quote = c
            elif c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth == 0:
            try:
                out.append(json.loads(text[i:j + 1]))
            except ValueError:
                pass
            i = j + 1
        else:
            i += 1
    return out


def normalize_path(path: str, project_files: list[str] | None = None) -> str:
    """Turn a model-written path into the repository-relative POSIX form.

    Models mix absolute paths, Windows separators, ``./`` prefixes and bare file
    names. Bare/partial paths are resolved against the project file list when the
    suffix is unique, so the metric judges the answer, not its spelling.
    """
    p = (path or "").strip().strip("`'\"").replace("\\", "/")
    p = re.sub(r"^\./+", "", p)
    p = re.sub(r"/+", "/", p).lstrip("/")
    if not p or p in (".", "-"):
        return ""
    known = list(project_files or [])
    if p in known:
        return p
    suffix = "/" + p
    matches = [f for f in known if f.endswith(suffix)]
    if len(matches) == 1:
        return matches[0]
    base = p.rsplit("/", 1)[-1]
    matches = [f for f in known if f.rsplit("/", 1)[-1] == base]
    if len(matches) == 1:
        return matches[0]
    return p  # keep the unmatched path: metrics count it as a hallucination


def parse_file_list(text: str, project_files: list[str] | None = None) -> tuple[list[str], str]:
    """Parse the model answer into unique file paths. Returns (files, error)."""
    if not text or not text.strip():
        return [], "empty"
    values, seen = _json_values(text), set()
    answer = None
    for value in values:
        if isinstance(value, list) and all(isinstance(x, str) for x in value):
            answer = value
            break
        if isinstance(value, dict):
            for key in ("files", "paths", "file_list", "result"):
                if isinstance(value.get(key), list):
                    answer = [x for x in value[key] if isinstance(x, str)]
                    break
        if answer is not None:
            break
    if answer is None:
        return [], "parse"
    files = []
    for raw in answer:
        path = normalize_path(raw, project_files)
        if path and path not in seen:
            seen.add(path)
            files.append(path)
    return files, ""


# ---- prompt building --------------------------------------------------------
def build_messages(task: dict, condition: str, pack_text: str = "") -> list[dict]:
    """The exact messages sent to the model (kept small so the comparison is honest)."""
    if condition == "cold":
        user = "你是资深 Java 工程师。%s\n\n需求：%s" % (ANSWER_RULE, task["query"])
    elif condition in PACK_BUDGET:
        user = ("你是资深 Java 工程师。下面是项目知识库检索到的上下文（来自真实代码图谱与知识页，可能不完整）：\n"
                "<context>\n%s\n</context>\n\n需求：%s\n%s" % (pack_text, task["query"], ANSWER_RULE))
    else:
        raise ValueError("未知条件：%r（可选 %s）" % (condition, "、".join(CONDITIONS)))
    return [{"role": "user", "content": user}]


# ---- Ollama client (injectable, degrades instead of raising) ----------------
def http_get_json(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_post_json(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _error_kind(exc: Exception) -> str:
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(exc, urllib.error.HTTPError):
        return "http_%d" % exc.code
    if isinstance(exc, (urllib.error.URLError, ConnectionError, OSError)):
        return "unavailable"
    return "error"


class OllamaClient:
    """Minimal native-API client for one local Ollama model.

    ``think=False`` is not cosmetic: with thinking on, the model spent the whole
    ``num_predict`` budget on reasoning and returned empty content (measured), so
    the RSI experiment would measure the token limit, not file finding.
    """

    def __init__(self, base_url: str = OLLAMA_URL, model: str = MODEL, timeout: float = DEFAULT_TIMEOUT,
                 get=None, post=None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._get = get or http_get_json
        self._post = post or http_post_json

    def available(self) -> tuple[bool, str]:
        try:
            data = self._get(self.base_url + "/api/tags", 10)
        except Exception as exc:  # noqa: BLE001 - degradation is the contract
            return False, "Ollama 不可达：%s: %s" % (type(exc).__name__, exc)
        names = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]
        if self.model not in names:
            return False, "模型不存在：%s（已有：%s）" % (self.model, "、".join(names) or "无")
        return True, "ok"

    def chat(self, messages: list[dict], max_tokens: int = DEFAULT_MAX_TOKENS,
             think: bool = THINK) -> dict:
        payload = {"model": self.model, "messages": messages, "stream": False, "think": bool(think),
                   "options": {"temperature": 0.0, "num_predict": int(max_tokens)}}
        t0 = time.time()
        try:
            data = self._post(self.base_url + "/api/chat", payload, self.timeout)
        except Exception as exc:  # noqa: BLE001
            return {"content": "", "latency_s": round(time.time() - t0, 2), "prompt_tokens": 0,
                    "completion_tokens": 0, "done_reason": "", "error": "%s: %s" % (type(exc).__name__, exc),
                    "error_kind": _error_kind(exc)}
        message = data.get("message") or {}
        return {"content": message.get("content") or "", "thinking": message.get("thinking") or "",
                "latency_s": round(time.time() - t0, 2),
                "prompt_tokens": int(data.get("prompt_eval_count") or 0),
                "completion_tokens": int(data.get("eval_count") or 0),
                "done_reason": data.get("done_reason") or "",
                "error": "", "error_kind": "ok"}


# ---- one task, one condition -------------------------------------------------
def project_files(root: Path) -> list[str]:
    root = Path(root)
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file() and ".tmh" not in p.parts and ".git" not in p.parts)


def run_task(client, task: dict, condition: str, root: Path, files: list[str],
             pack_text: str = "", max_tokens: int = DEFAULT_MAX_TOKENS) -> dict:
    messages = build_messages(task, condition, pack_text)
    prompt = messages[0]["content"]
    reply = client.chat(messages, max_tokens=max_tokens)
    parsed, parse_error = parse_file_list(reply.get("content", ""), files)
    if reply.get("error"):
        parse_error = "request_" + reply.get("error_kind", "error")
    gold = list(task["gold"])
    hit = [f for f in parsed if f in gold]
    return {
        "task_id": task["id"], "condition": condition, "query": task["query"], "gold": gold,
        "files": parsed, "raw": (reply.get("content") or "")[:500],
        "error": reply.get("error", ""), "error_kind": reply.get("error_kind", ""),
        "parse_error": parse_error, "done_reason": reply.get("done_reason", ""),
        "recall": round(len(hit) / float(len(gold)), 4) if gold else 0.0,
        "precision": round(len(hit) / float(len(parsed)), 4) if parsed else 0.0,
        "exact": 1.0 if gold and all(g in parsed for g in gold) else 0.0,
        "hallucinated": [f for f in parsed if f not in files],
        "latency_s": reply.get("latency_s", 0.0),
        "prompt_tokens": reply.get("prompt_tokens", 0),
        "completion_tokens": reply.get("completion_tokens", 0),
        "effective_output_tokens": estimate_tokens(reply.get("content", "")),
        "prompt_estimate_tokens": estimate_tokens(prompt),
        "pack_chars": len(pack_text or ""),
    }


# ---- aggregation -------------------------------------------------------------
def _mean(values) -> float:
    values = list(values)
    return round(sum(values) / len(values), 4) if values else 0.0


def summarize(samples: list[dict]) -> dict:
    """Condition-level metrics. Unparseable/empty answers count as misses, not as dropped rows."""
    n = len(samples)
    failures: dict[str, int] = {}
    for s in samples:
        if s["parse_error"]:
            failures[s["parse_error"]] = failures.get(s["parse_error"], 0) + 1
    predicted = [s for s in samples if s["files"]]
    total_paths = sum(len(s["files"]) for s in samples)
    hallucinated = sum(len(s["hallucinated"]) for s in samples)
    return {
        "n": n,
        "answered": len(predicted),
        "empty_answers": sum(1 for s in samples if not s["files"] and not s["parse_error"]),
        "failures": dict(sorted(failures.items())),
        "recall_mean": _mean(s["recall"] for s in samples),
        "precision_mean": _mean(s["precision"] for s in samples),
        "exact_rate": _mean(s["exact"] for s in samples),
        "latency_mean_s": _mean(s["latency_s"] for s in samples),
        "latency_max_s": round(max((s["latency_s"] for s in samples), default=0.0), 2),
        "prompt_tokens_mean": _mean(s["prompt_tokens"] for s in samples),
        "prompt_estimate_tokens_mean": _mean(s["prompt_estimate_tokens"] for s in samples),
        "completion_tokens_mean": _mean(s["completion_tokens"] for s in samples),
        "effective_output_tokens_mean": _mean(s["effective_output_tokens"] for s in samples),
        "pack_chars_mean": _mean(s["pack_chars"] for s in samples),
        "hallucinated_path_rate": round(hallucinated / float(total_paths), 4) if total_paths else 0.0,
    }


def compare(summaries: dict, min_gain: float = 0.05) -> dict:
    """Does context help? Delta on recall/exact between cold and each pack condition."""
    cold = summaries.get("cold", {})
    rows, best_gain = {}, 0.0
    for condition in CONDITIONS:
        if condition == "cold" or condition not in summaries:
            continue
        pack = summaries[condition]
        gain = round(pack["recall_mean"] - cold.get("recall_mean", 0.0), 4)
        best_gain = max(best_gain, gain)
        rows[condition] = {
            "recall_delta_vs_cold": gain,
            "exact_delta_vs_cold": round(pack["exact_rate"] - cold.get("exact_rate", 0.0), 4),
            "latency_delta_s": round(pack["latency_mean_s"] - cold.get("latency_mean_s", 0.0), 2),
            "completion_tokens_delta": round(pack["completion_tokens_mean"] - cold.get("completion_tokens_mean", 0.0), 2),
        }
    improved = best_gain >= min_gain
    return {
        "min_gain_rule": "file recall 至少提升 %.2f 视为“有提升”（样本 %d 条，仅作方向性结论）" % (min_gain, cold.get("n", 0)),
        "per_condition": rows,
        "context_helps": improved,
        "best_recall_gain": best_gain,
        "conclusion": ("本地模型下上下文包带来了文件召回提升（小样本，需扩大复测）。" if improved
                       else "本地 9B 模型下，上下文包未带来可判定的文件召回提升。"),
    }
