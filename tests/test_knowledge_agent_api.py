"""Knowledge CLI/agent contract, authority gates, and durable request routing.

These tests use a temporary SQLite store and an explicit library-executor seam.
They verify transport boundaries, not parser quality or a real knowledge build.
The optional MCP cases exercise the installed SDK's actual discovery handlers;
they are skipped when that optional dependency is absent, never emulated.
"""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tmh import workbench
from tmh.agent_contract import SPECS, schema, validate
from tmh.platform import agent_api
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tmh.workbench_client import Client, ClientError


REVISION = "a" * 32
READS = {"library_get", "library_search", "library_read"}
EXECUTIONS = {"library_build", "library_cancel", "library_resume"}
WRITES = EXECUTIONS | {"library_reference", "library_unlink"}
LIBRARY = READS | WRITES
SDK_AVAILABLE = sys.version_info >= (3, 10) and importlib.util.find_spec("mcp") is not None


def arguments(operation, request_id="request-1", project="CUSTOMER"):
    args = {"project": project}
    if operation in WRITES:
        args["request_id"] = request_id
    if operation in {"library_read", "library_cancel", "library_resume", "library_reference"}:
        args["revision_id"] = REVISION
    if operation == "library_read":
        args["path"] = "modules/审批/README.md"
    elif operation == "library_search":
        args["query"] = "审批"
    elif operation == "library_reference":
        args["purpose"] = "参考审批界面；客户业务规则仍待核对。"
    elif operation == "library_unlink":
        args["binding_id"] = 7
    return args


def command_cases():
    return [
        (["library", "CUSTOMER"], "library_get", arguments("library_get")),
        (["knowledge-search", "CUSTOMER", "审批", "--limit", "7", "--offset", "14"],
         "library_search", dict(arguments("library_search"), limit=7, offset=14)),
        (["knowledge-read", "CUSTOMER", REVISION, "modules/审批/README.md"],
         "library_read", arguments("library_read")),
        (["knowledge-build", "CUSTOMER", "--request-id", "request-1"],
         "library_build", dict(arguments("library_build"), commit="HEAD")),
        (["knowledge-cancel", "CUSTOMER", REVISION, "--request-id", "request-1"],
         "library_cancel", arguments("library_cancel")),
        (["knowledge-resume", "CUSTOMER", REVISION, "--request-id", "request-1"],
         "library_resume", arguments("library_resume")),
        (["knowledge-reference", "CUSTOMER", REVISION, "--scope", "modules/审批",
          "--scope", "docs", "--purpose", arguments("library_reference")["purpose"],
          "--request-id", "request-1"], "library_reference",
         dict(arguments("library_reference"), scopes=["modules/审批", "docs"])),
        (["knowledge-unlink", "CUSTOMER", "7", "--request-id", "request-1"],
         "library_unlink", arguments("library_unlink")),
    ]


class KnowledgeAgentContractTest(unittest.TestCase):
    def test_operations_declare_exact_authority_and_strict_schemas(self):
        self.assertEqual({name for name in SPECS if name.startswith("library_")}, LIBRARY)
        for operation in LIBRARY:
            with self.subTest(operation=operation):
                self.assertEqual(SPECS[operation]["write"], operation in WRITES)
                self.assertEqual(SPECS[operation]["execution"], operation in EXECUTIONS)
                self.assertFalse(SPECS[operation].get("operator"))
                self.assertFalse(schema(operation)["additionalProperties"])
                self.assertIn("project", schema(operation)["required"])
                if operation in WRITES:
                    self.assertIn("request_id", schema(operation)["required"])
        for operation in ("library_share", "library_derive", "library_maintain", "library_approve"):
            with self.assertRaises(ValueError):
                validate(operation, {"project": "CUSTOMER"})

    def test_defaults_are_typed_and_never_share_a_mutable_scope_list(self):
        self.assertEqual(validate("library_build", arguments("library_build"))["commit"], "HEAD")
        search = validate("library_search", arguments("library_search"))
        self.assertEqual((search["limit"], search["offset"]), (20, 0))
        first = validate("library_reference", arguments("library_reference"))
        first["scopes"].append("must-not-leak")
        self.assertEqual(validate("library_reference", arguments("library_reference"))["scopes"], [])

    def test_full_purpose_and_unicode_scope_are_preserved(self):
        purpose = "  客户解释\r\n" + "完整用途与不同适用条件。\t\n" * 2000 + "最后一行  "
        args = dict(arguments("library_reference"), purpose=purpose, scopes=["模块/审批", "docs"])
        self.assertEqual(validate("library_reference", args), args)

    def test_invalid_inputs_are_rejected_without_coercion_or_silent_drop(self):
        bad = [
            ("library_get", {"project": "../OTHER"}),
            ("library_get", {"project": "CUSTOMER", "root": "/outside"}),
            ("library_search", dict(arguments("library_search"), limit=101)),
            ("library_search", dict(arguments("library_search"), limit=0)),
            ("library_search", dict(arguments("library_search"), offset=True)),
            ("library_search", dict(arguments("library_search"), offset=-1)),
            ("library_search", dict(arguments("library_search"), query=" \n")),
            ("library_read", dict(arguments("library_read"), revision_id="HEAD")),
            ("library_read", dict(arguments("library_read"), path="")),
            ("library_build", {"project": "CUSTOMER"}),
            ("library_build", dict(arguments("library_build"), commit=" ")),
            ("library_reference", dict(arguments("library_reference"), scopes="docs")),
            ("library_reference", dict(arguments("library_reference"), scopes=[True])),
            ("library_reference", dict(arguments("library_reference"), scopes=[""])),
            ("library_reference", dict(arguments("library_reference"), grant=True)),
            ("library_reference", dict(arguments("library_reference"), purpose="")),
            ("library_unlink", dict(arguments("library_unlink"), binding_id=True)),
            ("library_unlink", dict(arguments("library_unlink"), binding_id=0)),
        ]
        for operation, args in bad:
            with self.subTest(operation=operation, args=args), self.assertRaises(ValueError):
                validate(operation, args)

    def test_cli_commands_map_to_shared_contract(self):
        for argv, operation, expected in command_cases():
            with self.subTest(command=argv[0]):
                actual_operation, args = workbench._arguments(workbench.parser().parse_args(argv))
                self.assertEqual(actual_operation, operation)
                self.assertEqual(validate(actual_operation, args), expected)
        op, args = workbench._arguments(workbench.parser().parse_args([
            "knowledge-build", "CUSTOMER", "--commit", "v5.2", "--request-id", "build-tag"]))
        self.assertEqual((op, args["commit"]), ("library_build", "v5.2"))

    def test_cli_enables_execution_only_for_explicit_build_controls(self):
        for argv, operation, expected in command_cases():
            client = Mock()
            client.call.side_effect = lambda op, args: {"operation": op, "arguments": validate(op, args)}
            output = io.StringIO()
            with self.subTest(command=argv[0]), patch.object(workbench, "Client", return_value=client) as factory, patch("sys.stdout", output):
                self.assertEqual(workbench.main(argv), 0)
                self.assertEqual(factory.call_args.kwargs["allow_execution"], operation in EXECUTIONS)
                self.assertEqual(json.loads(output.getvalue()), {"operation": operation, "arguments": expected})
                self.assertEqual(client.call.call_count, 1)

    def test_client_rejects_execution_without_opening_a_connection(self):
        client = Client("http://127.0.0.1:1", token="", allow_execution=False)
        with patch("http.client.HTTPConnection") as connection:
            for operation in EXECUTIONS:
                with self.subTest(operation=operation), self.assertRaises(ClientError) as caught:
                    client.call(operation, arguments(operation))
                self.assertEqual(caught.exception.code, "execution_disabled")
            connection.assert_not_called()


class KnowledgeAgentReceiptTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-library-api-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = Store(root / "platform.db")
        self.addCleanup(self.store.db.close)
        (root / "customer").mkdir()
        (root / "other").mkdir()
        self.project = self.store.add_project("CUSTOMER", "客户", str(root / "customer"))
        self.other = self.store.add_project("OTHER", "另一个客户", str(root / "other"))
        self.P = SimpleNamespace(store=self.store, data_dir=root)
        module = ModuleType("tmh.platform.project_library")

        def execute(P, actor, operation, args, mutation_callback):
            if operation in WRITES:
                mutation_callback()
            return {"operation": operation, "arguments": args, "actor": actor}

        module.execute = self.execute = Mock(side_effect=execute)
        # Patch only the business executor; the real schema, permission check,
        # request journal, resource resolution, and dispatcher all run below.
        self.library_patch = patch.dict(sys.modules, {module.__name__: module})
        self.library_patch.start()
        self.addCleanup(self.library_patch.stop)

    def call(self, operation, args=None, execution=False, actor="codex"):
        headers = {"X-Webuddy-Agent": actor}
        if execution:
            headers["X-Webuddy-Execution"] = "1"
        req = SimpleNamespace(h=SimpleNamespace(headers=headers), body=args or {}, user="human-login")
        return agent_api.dispatch(self.P, req, operation)

    def test_reads_route_to_library_as_agent_without_creating_write_receipts(self):
        for operation in READS:
            with self.subTest(operation=operation):
                args = validate(operation, arguments(operation))
                result = self.call(operation, args)
                self.assertEqual(result, {"operation": operation, "arguments": args, "actor": "agent:codex"})
                self.assertIs(self.execute.call_args.args[0], self.P)
                self.assertTrue(callable(self.execute.call_args.args[4]))
        self.assertEqual(self.store.q("SELECT * FROM agent_requests"), [])

    def test_execution_header_is_required_before_any_library_mutation(self):
        for operation in EXECUTIONS:
            with self.subTest(operation=operation), self.assertRaises(ApiError) as caught:
                self.call(operation, arguments(operation))
            self.assertEqual(caught.exception.code, 403)
        self.execute.assert_not_called()

    def test_each_write_has_a_project_resource_and_exactly_once_receipt_replay(self):
        for index, operation in enumerate(sorted(WRITES)):
            with self.subTest(operation=operation):
                args = arguments(operation, request_id="write-%d" % index)
                first = self.call(operation, args, execution=operation in EXECUTIONS)
                self.assertEqual(first, self.call(operation, args, execution=operation in EXECUTIONS))
                receipt = self.call("request_get", {"request_id": args["request_id"]})
                self.assertEqual(receipt["resource"], "project:%d:library" % self.project["id"])
                self.assertEqual(receipt["state"], "complete")
                self.assertEqual(receipt["arguments"], validate(operation, args))
                self.assertEqual(receipt["result"], first)
                with self.assertRaises(ApiError) as caught:
                    self.call(operation, dict(args, project="OTHER"), execution=operation in EXECUTIONS)
                self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.execute.call_count, len(WRITES))

    def test_source_denial_is_a_failed_receipt_and_agent_cannot_elevate_sharing(self):
        self.execute.side_effect = ApiError(403, "来源没有授权共享")
        args = arguments("library_reference")
        with self.assertRaises(ApiError) as denied:
            self.call("library_reference", args)
        self.assertEqual(denied.exception.code, 403)
        self.assertEqual(self.call("request_get", {"request_id": args["request_id"]})["state"], "failed")
        for operation, extra in (("library_reference", {"share": True}), ("library_share", {})):
            with self.subTest(operation=operation), self.assertRaises(ApiError) as caught:
                self.call(operation, dict(args, **extra), execution=True)
            self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.execute.call_count, 1)

    def test_uncertain_project_write_blocks_new_mutations_but_allows_cancel_and_reads(self):
        normal = self.execute.side_effect

        def lose_reply(P, actor, operation, args, mutate):
            result = normal(P, actor, operation, args, mutate)
            if operation == "library_build" and args["request_id"] == "lost-build":
                raise ApiError(409, "reply lost after recording build")
            return result

        self.execute.side_effect = lose_reply
        lost = arguments("library_build", request_id="lost-build")
        with self.assertRaises(ApiError) as caught:
            self.call("library_build", lost, execution=True)
        self.assertIn("needs_reconcile", str(caught.exception))
        receipt = self.call("request_get", {"request_id": "lost-build"})
        self.assertEqual(receipt["state"], "uncertain")
        with self.assertRaises(ApiError):
            self.call("library_build", lost, execution=True)
        for operation in WRITES - {"library_cancel"}:
            with self.subTest(operation=operation), self.assertRaises(ApiError) as blocked:
                self.call(operation, arguments(operation, "different-" + operation),
                          execution=operation in EXECUTIONS, actor="cursor")
            self.assertIn("needs_reconcile", str(blocked.exception))
        self.assertEqual(self.execute.call_count, 1)
        self.call("library_cancel", arguments("library_cancel", "stop-lost"), execution=True)
        self.call("library_get", arguments("library_get"))
        self.call("library_build", arguments("library_build", "other-build", "OTHER"), execution=True)
        self.assertEqual(self.execute.call_count, 4)
        self.assertEqual(self.call("request_get", {"request_id": "lost-build"})["state"], "uncertain")

    def test_unknown_project_rejected_before_journaling_or_library_mutation(self):
        with self.assertRaises(ApiError) as caught:
            self.call("library_build", arguments("library_build", project="MISSING"), execution=True)
        self.assertEqual(caught.exception.code, 404)
        self.execute.assert_not_called()
        self.assertEqual(self.store.q("SELECT * FROM agent_requests"), [])


@unittest.skipUnless(SDK_AVAILABLE, "optional MCP SDK not installed; no protocol coverage without it")
class KnowledgeMCPDiscoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_discovery_obeys_readonly_and_execution_permissions(self):
        import mcp.types as types
        from tmh.workbench_mcp import build_server

        for read_only, execution in ((True, True), (False, False), (False, True)):
            client = Mock()
            server = build_server(client, read_only=read_only, allow_execution=execution)
            result = await server.request_handlers[types.ListToolsRequest](types.ListToolsRequest(method="tools/list"))
            tools = result.root.tools
            actual = {tool.name: tool for tool in tools if tool.name.startswith("webuddy_library_")}
            expected = READS if read_only else LIBRARY if execution else READS | (WRITES - EXECUTIONS)
            with self.subTest(read_only=read_only, execution=execution):
                self.assertEqual(set(actual), {"webuddy_" + op for op in expected})
                self.assertEqual(client.allow_execution, execution and not read_only)
                for operation in expected:
                    tool = actual["webuddy_" + operation]
                    self.assertEqual(tool.inputSchema, schema(operation))
                    self.assertEqual(tool.annotations.readOnlyHint, operation in READS)
                client.call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
