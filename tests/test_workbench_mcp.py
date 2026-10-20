"""Official MCP client interoperability, permissions and response-loss behavior.

The HTTP fixture is deliberate: these tests verify the installed MCP protocol
stack and the real workbench CLI/client adapter, not model-generated code or a
customer acceptance result. The API's business tests live separately.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest


SDK_AVAILABLE = sys.version_info >= (3, 10) and importlib.util.find_spec("mcp") is not None
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(SDK_AVAILABLE, "optional MCP SDK not installed; install .[mcp]")
class WorkbenchMCPTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.long_text = "  沟通原文\r\n检查版本、失败与重试。\t\n" * 2500
        self.reply_mode = "normal"
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                operation = self.path.rsplit("/", 1)[-1]
                owner.requests.append({"path": self.path, "body": body,
                                       "headers": {k.lower(): v for k, v in self.headers.items()}})
                if owner.reply_mode == "lost_reply":
                    self.close_connection = True
                    return
                status = 200
                if owner.reply_mode == "conflict":
                    status, payload = 409, {"error": "请求编号已用于不同正文", "code": "request_conflict"}
                elif owner.reply_mode == "non_object":
                    payload = ["the write may have been saved but the response is invalid"]
                elif operation == "status":
                    payload = {"ok": True, "workspace": "协议测试夹具", "engines": [], "scope": "fixture"}
                elif operation == "ticket_get":
                    payload = {"ticket": {"key": body["ticket"], "body": owner.long_text},
                               "evidence": [{"commit": "fixture-only", "verdict": "not_accepted"}]}
                elif operation == "message_send":
                    payload = {"ok": True, "event_id": 91, "request_id": body["request_id"],
                               "body": body["body"], "kind": body["kind"]}
                elif operation == "run_start":
                    payload = {"ok": True, "run_id": 17, "state": "queued", "request_id": body["request_id"]}
                else:
                    payload = {"ok": True, "operation": operation}
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = "http://127.0.0.1:%s" % self.http.server_port
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.http.shutdown)

    @asynccontextmanager
    async def session(self, *flags):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tmh.workbench", "mcp", "--endpoint", self.endpoint,
                  "--agent", "mcp-test", *flags],
            env={"PYTHONPATH": str(ROOT), "WEBUDDY_TOKEN": "stdio-fixture-token"},
            cwd=str(ROOT),
        )
        with tempfile.TemporaryFile(mode="w+") as stderr:
            async with stdio_client(params, errlog=stderr) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
                    initialization = await session.initialize()
                    self.assertEqual(initialization.serverInfo.name, "webuddy_mcp")
                    self.assertTrue(initialization.capabilities.tools)
                    yield session

    def assert_full_json(self, result):
        self.assertEqual(len(result.content), 1)
        self.assertEqual(result.content[0].type, "text")
        self.assertEqual(json.loads(result.content[0].text), result.structuredContent)

    async def check_generated_configuration(self, client_name):
        """Use the exact generated entry, with no repository cwd/PYTHONPATH aid.

        Running ``-m tmh.workbench`` does not catch a direct script directory
        shadowing the official ``mcp`` package with legacy ``tmh/mcp.py``.
        Desktop clients launch the generated absolute script, so exercise that
        path as a real SDK subprocess independently for each config format.
        """
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "tmh.workbench", "config", client_name,
            "--endpoint", self.endpoint, "--read-only",
            cwd=str(ROOT), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        self.assertEqual(process.returncode, 0, stderr.decode("utf-8"))
        configuration = stdout.decode("utf-8")
        if client_name == "codex":
            import tomllib
            entry = tomllib.loads(configuration)["mcp_servers"]["webuddy"]
            self.assertEqual(entry["env_vars"], ["WEBUDDY_TOKEN"])
        else:
            entry = json.loads(configuration)["mcpServers"]["webuddy"]
        self.assertEqual(Path(entry["command"]), Path(sys.executable))
        self.assertEqual(Path(entry["args"][0]), ROOT / "tmh" / "workbench_entry.py")
        self.assertNotIn("stdio-fixture-token", configuration)

        with tempfile.TemporaryDirectory(prefix="tmh-unrelated-client-cwd-") as cwd:
            params = StdioServerParameters(
                command=entry["command"], args=entry["args"], cwd=cwd,
                env={"PYTHONPATH": "", "WEBUDDY_TOKEN": "stdio-fixture-token"},
            )
            with tempfile.TemporaryFile(mode="w+") as errlog:
                async with stdio_client(params, errlog=errlog) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
                        initialized = await session.initialize()
                        self.assertEqual(initialized.serverInfo.name, "webuddy_mcp")
                        tools = (await session.list_tools()).tools
                        self.assertEqual(len(tools), 16)
                        self.assertTrue(all(tool.annotations.readOnlyHint for tool in tools))
                        reply = await session.call_tool("webuddy_status", {})
                        self.assertFalse(reply.isError)
                        self.assertEqual(reply.structuredContent["scope"], "fixture")
                        self.assert_full_json(reply)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["path"], "/api/agent/status")
        self.assertEqual(self.requests[0]["headers"]["x-webuddy-agent"], client_name)
        self.assertEqual(self.requests[0]["headers"]["x-tmh-token"], "stdio-fixture-token")

    async def test_generated_claude_configuration_launches_from_unrelated_directory(self):
        await self.check_generated_configuration("claude")

    async def test_generated_cursor_configuration_launches_from_unrelated_directory(self):
        await self.check_generated_configuration("cursor")

    @unittest.skipUnless(sys.version_info >= (3, 11), "stdlib TOML parser requires Python 3.11+")
    async def test_generated_codex_toml_launches_from_unrelated_directory(self):
        await self.check_generated_configuration("codex")

    async def test_official_client_discovers_strict_tools_and_calls_real_cli_http_adapter(self):
        from tmh.agent_contract import SPECS, schema
        async with self.session() as session:
            discovered = (await session.list_tools()).tools
            expected = {"webuddy_" + op for op, spec in SPECS.items() if not spec["execution"] and not spec.get("operator")}
            self.assertEqual({tool.name for tool in discovered}, expected)
            for tool in discovered:
                op = tool.name[len("webuddy_"):]
                self.assertEqual(tool.inputSchema, schema(op))
                self.assertEqual(tool.annotations.readOnlyHint, not SPECS[op]["write"])
                self.assertFalse(tool.inputSchema["additionalProperties"])
            status = await session.call_tool("webuddy_status", {})
            self.assertFalse(status.isError)
            self.assertEqual(status.structuredContent["scope"], "fixture")
            self.assert_full_json(status)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["path"], "/api/agent/status")
        self.assertEqual(self.requests[0]["headers"]["x-webuddy-agent"], "mcp-test")
        self.assertEqual(self.requests[0]["headers"]["x-tmh-token"], "stdio-fixture-token")

    async def test_complete_multiline_context_and_message_survive_stdio(self):
        text = "  我已完成代码修改。\r\n请 Cursor 检查实际保存和重试。\t\n"
        async with self.session() as session:
            context = await session.call_tool("webuddy_ticket_get", {"ticket": "BOOTV2-1"})
            self.assertEqual(context.structuredContent["ticket"]["body"], self.long_text)
            self.assert_full_json(context)
            sent = await session.call_tool("webuddy_message_send", {
                "ticket": "BOOTV2-1", "body": text, "to_agent": "cursor",
                "kind": "handoff", "request_id": "mcp-full-body-1",
            })
            self.assertFalse(sent.isError)
            self.assertEqual(sent.structuredContent["body"], text)
            self.assertEqual(sent.structuredContent["request_id"], "mcp-full-body-1")
            self.assert_full_json(sent)
        self.assertEqual(self.requests[-1]["body"]["body"], text)

    async def test_read_only_hides_writes_and_rejects_direct_calls_before_http(self):
        from tmh.agent_contract import SPECS
        async with self.session("--read-only", "--allow-execution") as session:
            names = {tool.name for tool in (await session.list_tools()).tools}
            self.assertEqual(names, {"webuddy_" + op for op, spec in SPECS.items() if not spec["write"]})
            for name, arguments in (
                ("webuddy_message_send", {"ticket": "BOOTV2-1", "body": "blocked", "request_id": "blocked"}),
                ("webuddy_run_start", {"ticket": "BOOTV2-1", "mode": "fix", "engine": "codex", "request_id": "blocked"}),
                ("webuddy_release", {}),
            ):
                reply = await session.call_tool(name, arguments)
                self.assertTrue(reply.isError)
                self.assertEqual(reply.structuredContent["code"], "tool_not_enabled")
                self.assert_full_json(reply)
        self.assertEqual(self.requests, [])

    async def test_invalid_arguments_and_disabled_execution_never_reach_http(self):
        async with self.session() as session:
            for name, arguments, code in (
                ("webuddy_status", {"arbitrary_url": "https://example.org"}, "invalid_arguments"),
                ("webuddy_ticket_get", {"ticket": "../secrets"}, "invalid_arguments"),
                ("webuddy_run_get", {"run_id": True}, "invalid_arguments"),
                ("webuddy_message_send", {"ticket": "BOOTV2-1", "body": "missing receipt"}, "invalid_arguments"),
                ("webuddy_run_start", {"ticket": "BOOTV2-1", "mode": "fix", "engine": "codex", "request_id": "blocked"}, "tool_not_enabled"),
            ):
                reply = await session.call_tool(name, arguments)
                self.assertTrue(reply.isError)
                self.assertEqual(reply.structuredContent["code"], code)
                self.assert_full_json(reply)
        self.assertEqual(self.requests, [])

    async def test_enabled_execution_returns_durable_receipt_without_waiting_for_model(self):
        async with self.session("--allow-execution") as session:
            names = {tool.name for tool in (await session.list_tools()).tools}
            self.assertIn("webuddy_run_start", names)
            self.assertIn("webuddy_candidate_submit", names)
            self.assertIn("webuddy_candidate_assess", names)
            self.assertNotIn("webuddy_candidate_decide", names)
            forbidden = await session.call_tool("webuddy_candidate_decide", {"candidate_id": 1, "evidence_hash": "a" * 64, "decision": "accept", "note": "fixture", "request_id": "forbidden"})
            self.assertTrue(forbidden.isError)
            self.assertEqual(forbidden.structuredContent["code"], "tool_not_enabled")
            reply = await session.call_tool("webuddy_run_start", {
                "ticket": "BOOTV2-1", "mode": "analyze", "engine": "codex",
                "request_id": "start-once",
            })
            self.assertFalse(reply.isError)
            self.assertEqual(reply.structuredContent["run_id"], 17)
            self.assertEqual(reply.structuredContent["state"], "queued")
            self.assert_full_json(reply)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["headers"]["x-webuddy-execution"], "1")

    async def test_http_conflict_is_structured_tool_error_not_protocol_success(self):
        self.reply_mode = "conflict"
        async with self.session() as session:
            reply = await session.call_tool("webuddy_message_send", {
                "ticket": "BOOTV2-1", "body": "changed body", "request_id": "collision",
            })
            self.assertTrue(reply.isError)
            self.assertEqual(reply.structuredContent["code"], "request_conflict")
            self.assertEqual(reply.structuredContent["status"], 409)
            self.assertFalse(reply.structuredContent["uncertain"])
            self.assert_full_json(reply)
        self.assertEqual(len(self.requests), 1)

    async def test_lost_write_response_is_uncertain_and_never_automatically_retried(self):
        self.reply_mode = "lost_reply"
        async with self.session() as session:
            reply = await session.call_tool("webuddy_message_send", {
                "ticket": "BOOTV2-1", "body": "may already be saved", "request_id": "lost-once",
            })
            self.assertTrue(reply.isError)
            self.assertEqual(reply.structuredContent["code"], "connection_error")
            self.assertTrue(reply.structuredContent["uncertain"])
            self.assertIn("request_get", reply.structuredContent["error"])
            self.assert_full_json(reply)
        self.assertEqual(len(self.requests), 1)

    async def test_invalid_write_response_preserves_uncertain_outcome(self):
        self.reply_mode = "non_object"
        async with self.session() as session:
            reply = await session.call_tool("webuddy_message_send", {
                "ticket": "BOOTV2-1", "body": "might be saved", "request_id": "invalid-reply",
            })
            self.assertTrue(reply.isError)
            self.assertTrue(reply.structuredContent["uncertain"])
            self.assert_full_json(reply)
        self.assertEqual(len(self.requests), 1)


@unittest.skipUnless(SDK_AVAILABLE, "optional MCP SDK not installed; install .[mcp]")
class WorkbenchMCPWorkersTest(unittest.IsolatedAsyncioTestCase):
    async def test_http_workers_are_bounded_and_do_not_block_protocol_loop(self):
        import mcp.types as types
        from tmh.workbench_mcp import build_server

        class Client:
            def __init__(self):
                self.active, self.maximum = 0, 0
                self.lock = threading.Lock()

            def call(self, operation, arguments):
                with self.lock:
                    self.active += 1
                    self.maximum = max(self.maximum, self.active)
                try:
                    time.sleep(0.05)
                    return {"ok": True, "operation": operation}
                finally:
                    with self.lock:
                        self.active -= 1

        client = Client()
        server = build_server(client)
        handler = server.request_handlers[types.CallToolRequest]
        request = types.CallToolRequest(method="tools/call", params=types.CallToolRequestParams(name="webuddy_status", arguments={}))
        results = await asyncio.gather(*(handler(request) for _ in range(12)))
        self.assertGreater(client.maximum, 1)
        self.assertLessEqual(client.maximum, 4)
        self.assertEqual(client.active, 0)
        self.assertTrue(all(not reply.root.isError for reply in results))

    async def test_cancellation_waits_for_bounded_http_worker_and_does_not_retry(self):
        import anyio
        import mcp.types as types
        from tmh.workbench_mcp import build_server

        class Client:
            def __init__(self):
                self.started = threading.Event()
                self.finished = threading.Event()
                self.calls = 0

            def call(self, operation, arguments):
                self.calls += 1
                self.started.set()
                time.sleep(0.12)
                self.finished.set()
                return {"ok": True}

        client = Client()
        server = build_server(client)
        handler = server.request_handlers[types.CallToolRequest]
        request = types.CallToolRequest(method="tools/call", params=types.CallToolRequestParams(name="webuddy_status", arguments={}))
        async with anyio.create_task_group() as group:
            group.start_soon(handler, request)
            while not client.started.is_set():
                await anyio.sleep(0.005)
            group.cancel_scope.cancel()
        self.assertTrue(client.finished.is_set())
        self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()
