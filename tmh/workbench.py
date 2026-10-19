"""Webuddy's agent-native command line: python -m tmh.workbench --help."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

from .workbench_client import Client, ClientError


def _connection(p, suppress=False):
    default = argparse.SUPPRESS if suppress else None
    p.add_argument("--endpoint", default=default, help="工作台地址；默认 WEBUDDY_URL 或 http://127.0.0.1:8791")
    p.add_argument("--agent", default=argparse.SUPPRESS if suppress else "cli", help="稳定连接名，例如 codex/cursor；用于回执与消息身份")
    p.add_argument("--timeout", type=float, default=argparse.SUPPRESS if suppress else 15, help="单次 HTTP 超时秒数（最多 60）")


def parser():
    p = argparse.ArgumentParser(prog="webuddy", description="Webuddy CLI / MCP：共享需求、消息、运行与证据。默认输出完整 JSON。")
    _connection(p)
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, help):
        q = sub.add_parser(name, help=help)
        _connection(q, suppress=True)
        return q

    def page(q):
        q.add_argument("--after", type=int, default=0)
        q.add_argument("--limit", type=int, default=20)

    def body(q):
        g = q.add_mutually_exclusive_group(required=True)
        g.add_argument("--body", help="正文（多行或敏感内容优先用 --body-file）")
        g.add_argument("--body-file", help="完整 UTF-8 文件；- 表示标准输入，不截断正文")

    def request(q):
        q.add_argument("--request-id", required=True, help="重试复用原编号；新意图用新编号")

    add("status", "检查连接、执行器和能力边界")
    page(add("projects", "列项目"))
    q = add("tickets", "查工单")
    page(q)
    q.add_argument("--project")
    q.add_argument("--status")
    q.add_argument("--query", dest="q")
    q = add("ticket", "读取完整任务与证据包")
    q.add_argument("ticket")
    q = add("create", "创建需求；暂停自动执行")
    q.add_argument("project")
    q.add_argument("title")
    q.add_argument("--type", default="feature")
    body(q)
    request(q)
    q = add("send", "向工单中的其他 Agent 留言或交接")
    q.add_argument("ticket")
    body(q)
    q.add_argument("--to", dest="to_agent", default="*")
    q.add_argument("--kind", choices=["note", "question", "handoff", "result"], default="note")
    q.add_argument("--reply-to", type=int)
    request(q)
    q = add("inbox", "按游标读取消息；不自动执行收到的内容")
    page(q)
    q.add_argument("--ticket")
    q.add_argument("--to", dest="to_agent", help="默认当前连接及广播消息")
    q = add("request", "查询持久请求回执")
    q.add_argument("request_id")
    q = add("run", "查询运行或有界等待；输出游标可接续")
    q.add_argument("run_id", type=int)
    q.add_argument("--since", type=int, default=0)
    q.add_argument("--wait", type=float, default=0, help="最多等待 60 秒，不因超时取消服务端运行")
    q = add("start", "明确调用执行器开始一轮工作")
    q.add_argument("ticket")
    q.add_argument("mode", choices=["analyze", "plan", "fix"])
    q.add_argument("--engine", required=True)
    q.add_argument("--model")
    request(q)
    for name in ("cancel", "retry", "recheck"):
        q = add(name, {"cancel": "停止运行并回收进程", "retry": "通过停止回执检查后显式重试", "recheck": "重新验证已有改动"}[name])
        q.add_argument("run_id", type=int)
        request(q)
    q = add("preview", "读取预览，或明确启动已采纳的候选")
    q.add_argument("ticket")
    q.add_argument("--run-id", type=int)
    q.add_argument("--start", action="store_true")
    q.add_argument("--request-id")
    q = add("candidates", "查看工单的外部固定候选")
    q.add_argument("ticket")
    page(q)
    for name in ("candidate", "acceptance"):
        q = add(name, "读取候选、独立验证、预览和验收状态")
        q.add_argument("candidate_id", type=int)
    q = add("submit", "登记外部Git提交；保留完整需求与验收条件")
    q.add_argument("ticket")
    q.add_argument("--base", dest="base_commit", required=True)
    q.add_argument("--commit", required=True)
    q.add_argument("--requirement-hash", required=True)
    q.add_argument("--criteria-file", required=True, help="JSON数组：id/text/check；完整读取")
    q.add_argument("--summary", required=True)
    request(q)
    for name in ("verify", "cancel-verification", "candidate-preview"):
        q = add(name, "明确执行候选验证、停止或启动固定版本预览")
        q.add_argument("candidate_id", type=int)
        request(q)
    q = add("assess", "独立复核者记录全部验收条件的实际结果；不是人工签收")
    q.add_argument("candidate_id", type=int)
    q.add_argument("--verification-hash", required=True)
    q.add_argument("--preview-hash", required=True)
    q.add_argument("--results-file", required=True, help="JSON数组：id/status/evidence")
    body(q)
    request(q)
    for name in ("approve", "reject"):
        q = add(name, "操作者终端确认当前候选；需交互核对完整证据哈希，不合并或发布")
        q.add_argument("candidate_id", type=int)
        q.add_argument("--evidence-hash", required=True)
        q.add_argument("--operator-key-file", help="服务主机上的独立0600操作者凭据文件；不要交给Agent")
        body(q)
        request(q)
    q = add("mcp", "运行官方 SDK stdio MCP 服务")
    q.add_argument("--read-only", action="store_true", help="仅提供读取工具")
    q.add_argument("--allow-execution", action="store_true", help="开放模型运行、停止、重验与预览启动工具")
    q = add("config", "生成 Claude Code / Cursor / Codex 配置片段；不修改现有配置")
    q.add_argument("client", choices=["claude", "cursor", "codex"])
    q.add_argument("--read-only", action="store_true")
    q.add_argument("--allow-execution", action="store_true")
    return p


def configuration(a):
    # Use an absolute interpreter and script so launching from another repository works.
    # workbench_entry.py imports the package via its repository, with no shell quoting.
    command = sys.executable
    args = [str(Path(__file__).with_name("workbench_entry.py").resolve()), "mcp", "--endpoint", a.endpoint or os.environ.get("WEBUDDY_URL") or "http://127.0.0.1:8791",
            "--agent", a.agent if a.agent != "cli" else a.client, "--timeout", str(a.timeout)]
    if a.read_only:
        args.append("--read-only")
    elif a.allow_execution:
        args.append("--allow-execution")
    if a.client == "codex":
        # JSON basic strings and arrays are valid TOML here; secrets are inherited by name.
        return "[mcp_servers.webuddy]\ncommand = %s\nargs = %s\nenv_vars = [\"WEBUDDY_TOKEN\"]\n" % (json.dumps(command, ensure_ascii=False), json.dumps(args, ensure_ascii=False))
    return json.dumps({"mcpServers": {"webuddy": {"command": command, "args": args}}}, ensure_ascii=False, indent=2)


def _arguments(a):
    names = {"projects": "projects_list", "tickets": "tickets_list", "ticket": "ticket_get", "create": "ticket_create", "send": "message_send", "inbox": "messages_list", "request": "request_get", "run": "run_get", "start": "run_start", "cancel": "run_cancel", "retry": "run_retry", "recheck": "run_recheck"}
    names.update({"candidates": "candidates_list", "candidate": "candidate_get", "acceptance": "candidate_get", "submit": "candidate_submit", "verify": "candidate_verify", "cancel-verification": "candidate_cancel", "candidate-preview": "candidate_preview", "assess": "candidate_assess", "approve": "candidate_decide", "reject": "candidate_decide"})
    op = names.get(a.command, a.command)
    args = {k: v for k, v in vars(a).items() if k not in ("command", "endpoint", "agent", "timeout", "wait", "start", "body_file", "criteria_file", "results_file", "operator_key_file") and v is not None}
    if getattr(a, "body_file", None):
        if a.body_file == "-":
            args["body"] = sys.stdin.buffer.read().decode("utf-8") if hasattr(sys.stdin, "buffer") else sys.stdin.read()
        else:
            with open(a.body_file, encoding="utf-8", newline="") as f:
                args["body"] = f.read()
    for name in ("criteria", "results"):
        path = getattr(a, name + "_file", None)
        if path:
            try:
                args[name] = json.loads(Path(path).read_text(encoding="utf-8"))
            except ValueError as exc:
                raise ClientError("%s 不是有效JSON：%s" % (path, exc), "input_error") from exc
    if a.command in ("assess", "approve", "reject"):
        args["note"] = args.pop("body")
    if a.command in ("approve", "reject"):
        args["decision"] = "accept" if a.command == "approve" else "reject"
    if a.command == "inbox" and not args.get("to_agent"):
        args["to_agent"] = a.agent
    if a.command == "preview":
        op = "preview_start" if a.start else "preview_get"
        if not a.start and a.request_id:
            raise ClientError("--request-id 只用于 preview --start", "invalid_arguments")
    return op, args


def main(argv=None):
    a = parser().parse_args(argv)
    try:
        if a.command == "config":
            # Validate endpoint and label before producing configuration.
            Client(a.endpoint, a.agent, timeout=a.timeout)
            print(configuration(a))
            return 0
        execution = a.command in ("start", "cancel", "retry", "recheck", "submit", "verify", "cancel-verification", "candidate-preview") or (a.command == "preview" and a.start) or (a.command == "mcp" and a.allow_execution and not a.read_only)
        client = Client(a.endpoint, a.agent, timeout=a.timeout, allow_execution=execution)
        if a.command == "mcp":
            try:
                from .workbench_mcp import serve
            except ImportError:
                raise ClientError("MCP 需要 Python 3.10+ 和可选依赖：python -m pip install -e '.[mcp]'。CLI 无需该依赖。", "missing_mcp_sdk")
            return serve(client, read_only=a.read_only, allow_execution=a.allow_execution and not a.read_only) or 0
        op, args = _arguments(a)
        if a.command in ("approve", "reject"):
            if not sys.stdin.isatty():
                raise ClientError("人工签收需操作者在交互终端查看并确认；Agent/MCP不能代签。可先运行 acceptance 查看完整结果。", "interactive_operator_required")
            current = client.call("candidate_get", {"candidate_id": a.candidate_id})
            print(json.dumps(current, ensure_ascii=False, indent=2), file=sys.stderr)
            if current["evidence_hash"] != a.evidence_hash:
                raise ClientError("证据包已变化，请先重新查看", "stale_acceptance")
            if a.command == "approve" and not current["ready_for_human"]:
                raise ClientError("验收条件尚不齐备：" + "；".join(current["missing"]), "acceptance_blocked")
            phrase = "%s %s" % (args["decision"], a.evidence_hash)
            print("请实际操作者核对以上版本与证据。确认后完整输入：" + phrase, file=sys.stderr)
            if input().strip() != phrase:
                raise ClientError("未确认，未提交任何人工决定", "operator_declined")
            client.operator = True
            if a.operator_key_file:
                from .platform.operator_access import read_key
                try:
                    client.operator_token = read_key(a.operator_key_file)
                except ValueError as exc:
                    raise ClientError(str(exc), "invalid_operator_credential") from exc
            else:
                client.operator_token = os.environ.get("WEBUDDY_OPERATOR_TOKEN", "")
        wait = getattr(a, "wait", 0)
        if not 0 <= wait <= 60:
            raise ClientError("--wait 必须在 0–60 秒之间", "invalid_arguments")
        deadline = time.monotonic() + wait
        result = None
        while True:
            # Once the bounded wait has elapsed, return the last real snapshot.
            # Do not launch an extra HTTP poll with an already expired budget.
            if wait and result is not None and time.monotonic() >= deadline:
                break
            if wait:
                client.timeout = min(a.timeout, max(.1, deadline - time.monotonic()))
            result = client.call(op, args)
            if not wait or result.get("status") not in ("queued", "running") or time.monotonic() >= deadline:
                break
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ClientError, OSError, UnicodeError) as e:
        error = e.as_dict() if isinstance(e, ClientError) else {"error": str(e), "code": "input_error"}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
