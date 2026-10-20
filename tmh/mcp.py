"""`tmh mcp`: a stdio MCP server so Codex / Claude Code call tmh as native tools.

Each tool runs the matching tmh command in-process and returns its text, so
the CLI and the MCP surface never drift apart. Integration tools are listed
only when a configured tool provides that capability. Write tools (comment,
transition, trigger, notify) are dry runs unless the repo config sets
integrations.agent_writes = true and the call passes confirm = true.

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio).
"""
from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from . import __version__
from . import integrations as I
from . import usage

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
S = lambda d="": {"type": "string", "description": d}
N = lambda d="": {"type": "integer", "description": d}
B = lambda d="": {"type": "boolean", "description": d}
VIA = S("可选：用哪个接入（tmh int list 里的名字），默认按能力自动选")
CONFIRM = B("真正执行。需要仓库配置 integrations.agent_writes=true，否则只演练")
CLIENT = {"name": ""}  # who connected (Cursor, Claude Code …), from initialize; recorded with each call


def _tool(name, desc, props, required, argv, cap=None, write=False):
    return {"name": name, "description": desc, "props": props, "required": required, "argv": argv, "cap": cap, "write": write}


def _opt(flag, key):
    return lambda a: [flag, str(a[key])] if a.get(key) not in (None, "") else []


TOOLS = [
    _tool("context", "任务开始时先调用：按需求原文/业务词/类名/表名，从项目知识库取相关知识页、业务流、表和代码位置（不必通读仓库）",
          {"query": S("需求原文或关键词"), "budget": N("字符上限，默认 8000")}, ["query"],
          lambda a: ["context", a["query"]] + _opt("--budget", "budget")(a)),
    _tool("kb_chain", "按需求读业务链路的知识库原文：业务域 → 业务流 → 表，整页原文、带状态和未答复问题。要理解业务时用它，不要自己概括知识库",
          {"query": S("需求原文或业务词"), "budget": N("字符上限，默认 30000；超出的页面只列 id，不截断")}, ["query"],
          lambda a: ["kb", "chain", a["query"]] + _opt("--budget", "budget")(a)),
    _tool("kb_read", "按 id 读知识页原文（index、dom:x、flow:x、tbl:x，或 glossary.md、open-questions.md 等）", {"ids": S("页面 id，逗号或空格分隔")}, ["ids"],
          lambda a: ["kb", "read"] + [x for x in re.split(r"[,\s，]+", a["ids"]) if x]),
    _tool("kb_triage", "需求预判：依据知识库判断能不能做、把握多大、要问业务方什么。涉及资金/审批/口径、依据未经确认或有未答问题时一律交人判断",
          {"request": S("需求或问题原文"), "record": B("把要问的问题记入待确认问题，并把没写的业务流排进撰写队列")}, ["request"],
          lambda a: ["kb", "triage", a["request"]] + (["--record"] if a.get("record") else [])),
    _tool("kb_questions", "列出还没答复的业务问题（编号、涉及页面、要问谁）", {"all": B("连已答复的一起列")}, [],
          lambda a: ["kb", "questions"] + (["--all"] if a.get("all") else [])),
    _tool("kb_ask", "把需要业务方回答的问题记入知识库的待确认问题（不要猜答案）", {"question": S(), "pages": S("涉及的知识页 id，逗号分隔"), "to": S("要问谁")},
          ["question"], lambda a: ["kb", "ask", a["question"]] + _opt("--pages", "pages")(a) + _opt("--to", "to")(a)),
    _tool("flows", "业务流：入口 → 业务逻辑 → 数据访问 → 表，含状态变化和代码里的规则", {"query": S("业务流 id、URL、类名、表名或中文业务名")}, ["query"],
          lambda a: ["flows", a["query"]]),
    _tool("impact", "影响分析：改一个类/表/文件会波及哪些代码和业务流", {"target": S("类名、表名或文件路径")}, ["target"], lambda a: ["impact", a["target"]]),
    _tool("trace", "按工单号追溯 git 历史：哪些提交、改了哪些文件、涉及哪些业务流", {"key": S("工单号，如 OA-123")}, ["key"], lambda a: ["trace", a["key"]]),
    _tool("integrations", "列出已接入的运维工具及其能力", {}, [], lambda a: ["int", "list"]),
    _tool("ticket", "按工单开工：工单详情 + 知识库里相关的业务流/表/代码", {"key": S("工单号"), "via": VIA}, ["key"],
          lambda a: ["ticket", a["key"]] + _opt("--via", "via")(a), cap="issues"),
    _tool("ticket_task", "从工单生成任务契约 .tmh/tasks/T###-*.md（含工单链接和相关知识）", {"key": S("工单号"), "via": VIA}, ["key"],
          lambda a: ["ticket", a["key"], "--task"] + _opt("--via", "via")(a), cap="issues"),
    _tool("issue_get", "查看工单详情和最近评论", {"key": S("工单号"), "via": VIA}, ["key"], lambda a: ["issue", "get", a["key"]] + _opt("--via", "via")(a), cap="issues"),
    _tool("issue_search", "搜索工单（关键词，Jira 也可直接写 JQL）", {"query": S(), "limit": N(), "via": VIA}, ["query"],
          lambda a: ["issue", "search", a["query"]] + _opt("--limit", "limit")(a) + _opt("--via", "via")(a), cap="issues"),
    _tool("issue_comment", "在工单上评论（默认只演练）", {"key": S(), "body": S("评论内容"), "confirm": CONFIRM, "via": VIA}, ["key", "body"],
          lambda a: ["issue", "comment", a["key"], a["body"]] + _opt("--via", "via")(a), cap="issues", write=True),
    _tool("issue_transition", "流转工单状态（默认只演练）", {"key": S(), "to": S("目标状态或流转名"), "confirm": CONFIRM, "via": VIA}, ["key", "to"],
          lambda a: ["issue", "transition", a["key"], a["to"]] + _opt("--via", "via")(a), cap="issues", write=True),
    _tool("build_status", "最近的构建/流水线", {"job": S("job 名或分支，可空"), "limit": N(), "via": VIA}, [],
          lambda a: ["build", "status", a.get("job", "")] + _opt("--limit", "limit")(a) + _opt("--via", "via")(a), cap="builds"),
    _tool("build_log", "构建日志末尾", {"job": S(), "number": S("构建号或 last/lastFailed"), "tail": N("行数，默认 200"), "via": VIA}, [],
          lambda a: ["build", "log", a.get("job", "")] + _opt("--number", "number")(a) + _opt("--tail", "tail")(a) + _opt("--via", "via")(a), cap="builds"),
    _tool("build_failure", "分析失败的构建：错误行、落在项目代码里的位置、受影响的业务流", {"job": S(), "number": S("默认最近一次失败"), "via": VIA}, [],
          lambda a: ["build", "failure", a.get("job", "")] + _opt("--number", "number")(a) + _opt("--via", "via")(a), cap="builds"),
    _tool("build_trigger", "触发构建（默认只演练）", {"job": S(), "params": {"type": "object", "description": "构建参数"}, "confirm": CONFIRM, "via": VIA}, [],
          lambda a: ["build", "trigger", a.get("job", "")] + sum((["--param", "%s=%s" % kv] for kv in (a.get("params") or {}).items()), []) + _opt("--via", "via")(a),
          cap="builds", write=True),
    _tool("change_list", "合并请求列表", {"state": S("open/merged/closed/all"), "via": VIA}, [],
          lambda a: ["change", "list"] + _opt("--state", "state")(a) + _opt("--via", "via")(a), cap="changes"),
    _tool("change_get", "合并请求详情、改动文件和涉及的业务流", {"id": S("如 !12"), "via": VIA}, ["id"],
          lambda a: ["change", "get", a["id"]] + _opt("--via", "via")(a), cap="changes"),
    _tool("quality_issues", "未解决的代码质量问题，按业务流分组", {"path": S("目录前缀"), "severity": S("最低级别，如 MAJOR"), "via": VIA}, [],
          lambda a: ["quality"] + _opt("--path", "path")(a) + _opt("--severity", "severity")(a) + _opt("--via", "via")(a), cap="quality"),
    _tool("quality_gate", "质量门禁状态", {"via": VIA}, [], lambda a: ["quality", "--gate"] + _opt("--via", "via")(a), cap="quality"),
    _tool("doc_search", "搜索团队文档（需求说明、设计、运维手册）", {"query": S(), "via": VIA}, ["query"],
          lambda a: ["doc", "search", a["query"]] + _opt("--via", "via")(a), cap="docs"),
    _tool("doc_get", "读取一篇文档正文", {"id": S("文档 id"), "via": VIA}, ["id"], lambda a: ["doc", "get", a["id"]] + _opt("--via", "via")(a), cap="docs"),
    _tool("notify_send", "发群通知（默认只演练）", {"title": S(), "text": S(), "confirm": CONFIRM, "via": VIA}, ["title", "text"],
          lambda a: ["notify", a["title"], a["text"]] + _opt("--via", "via")(a), cap="notify", write=True),
]


def list_tools(root: Path) -> list:
    caps = {c for c in I.CAPABILITIES if I.available(root, c)}
    out = []
    for t in TOOLS:
        if t["cap"] and t["cap"] not in caps:
            continue
        out.append({"name": t["name"], "description": t["description"],
                    "inputSchema": {"type": "object", "properties": t["props"], "required": t["required"]}})
    return out


def call_tool(root: Path, name: str, args: dict) -> tuple[str, bool]:
    from .cli import main
    t = next((x for x in TOOLS if x["name"] == name), None)
    if not t:
        return "没有这个工具：%s" % name, True
    for r in t["required"]:
        if args.get(r) in (None, ""):
            return "缺少参数 %s" % r, True
    argv = t["argv"](args) + ["--repo", str(root)]
    note = ""
    if t["write"]:
        allowed = bool(I.settings(root).get("agent_writes"))
        if args.get("confirm") and allowed:
            argv.append("--confirm")
        elif args.get("confirm"):
            note = "\n\n（仓库配置 integrations.agent_writes=false，智能体只能演练。请让人在终端执行对应的 tmh 命令并加 --confirm。）"
    buf = io.StringIO()
    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = main(argv)
    except SystemExit as e:  # argparse error
        rc = e.code or 2
    except Exception as e:  # never kill the server
        return "%s 执行出错：%s: %s" % (name, type(e).__name__, e), True
    return (buf.getvalue().strip() or "（无输出）") + note, rc not in (0, None)


def handle(root: Path, msg: dict) -> dict | None:
    mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if mid is None:  # notification
        return None
    if method == "initialize":
        want = params.get("protocolVersion", PROTOCOLS[0])
        ci = params.get("clientInfo") or {}
        CLIENT["name"] = ("%s %s" % (ci.get("name", ""), ci.get("version", ""))).strip()
        result = {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0], "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "tmh", "version": __version__},
                  "instructions": "传统 toB 项目维护工具。任务开始先调 context 定位、kb_chain 读业务链路原文（知识库是唯一的项目知识，按原文读，不要另做摘要）；业务方的需求先 kb_triage；有工单号先调 ticket；构建失败调 build_failure。写操作默认只演练。"}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": list_tools(root)}
    elif method == "tools/call":
        text, err = call_tool(root, params.get("name", ""), params.get("arguments") or {})
        usage.log(root, params.get("name", ""), params.get("arguments") or {}, CLIENT["name"], ok=not err)
        result = {"content": [{"type": "text", "text": text}], "isError": err}
    elif method in ("resources/list", "prompts/list"):
        result = {method.split("/")[0]: []}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found: " + method}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(root: Path, stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
            stdout.flush()
            continue
        batch = msg if isinstance(msg, list) else [msg]
        for m in batch:
            resp = handle(root, m)
            if resp is not None:
                stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                stdout.flush()
    return 0
