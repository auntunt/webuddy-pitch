"""Project routing tests use local fixtures and never invoke a model."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tmh.platform import agent_routes, handwork, intake, server, tenant_policy
from tmh.platform.errors import ApiError
from tmh.platform.orchestra import Orchestra
from tmh.platform.store import Store


class AgentRoutesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tmh-agent-routes-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.path = self.data / "agent-routes.json"
        self.agents = [{"name": name, "available": True} for name in ("claude", "codex", "cloudwave-codex")]
        available = patch("tmh.platform.agents.available", side_effect=lambda _: self.agents)
        available.start()
        self.addCleanup(available.stop)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        project_root = self.root / "project"
        project_root.mkdir()
        self.project = self.store.add_project("ALPHA", "Fixture", str(project_root))
        self.ticket = self.store.create_ticket(self.project["id"], "Fixture", "alice")
        self.runner = Mock()
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, runner=self.runner, surveys={},
                                 root=lambda p: Path(p["root"]), project=lambda key: self.store.project(key),
                                 ticket=lambda key: self.store.ticket(key))
        self.P.flow = Orchestra(self.store, self.runner, self.data, Mock())

    def write(self, value=None):
        value = value or {"schema": 1, "projects": {"ALPHA": {"agent": "cloudwave-codex",
                         "allowed_agents": ["cloudwave-codex"], "direct_api": False}}}
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def request(self, body):
        return SimpleNamespace(body=body, user="alice")

    def test_absent_configuration_keeps_legacy_explicit_and_fallback(self):
        self.assertEqual(agent_routes.resolve(self.data, self.project, "custom-api", "codex"), "custom-api")
        self.assertEqual(agent_routes.resolve(self.data, self.project, fallback="claude"), "claude")
        self.assertTrue(agent_routes.direct_api_allowed(self.data, self.project))

    def test_project_override_is_scoped_and_does_not_change_other_projects(self):
        self.write()
        self.assertEqual(agent_routes.resolve(self.data, {"key": "alpha"}, fallback="claude"), "cloudwave-codex")
        self.assertEqual(agent_routes.resolve(self.data, {"key": "BETA"}, fallback="claude"), "claude")
        self.assertTrue(agent_routes.direct_api_allowed(self.data, "BETA"))
        self.assertFalse(agent_routes.direct_api_allowed(self.data, "ALPHA"))

    def test_default_inheritance_and_allowed_explicit_request(self):
        self.write({"schema": 1, "default": {"agent": "codex", "direct_api": False,
                    "allowed_agents": ["codex", "cloudwave-codex"]},
                    "projects": {"ALPHA": {"agent": "cloudwave-codex"}}})
        self.assertEqual(agent_routes.resolve(self.data, "BETA"), "codex")
        self.assertEqual(agent_routes.resolve(self.data, self.project, "codex"), "codex")
        self.assertFalse(agent_routes.direct_api_allowed(self.data, self.project))

    def test_wrong_engine_and_missing_configured_engine_never_fall_back(self):
        self.write()
        with self.assertRaisesRegex(ValueError, "仅允许"):
            agent_routes.resolve(self.data, self.project, "claude")
        self.agents[-1]["available"] = False
        with self.assertRaisesRegex(ValueError, "不可用"):
            agent_routes.resolve(self.data, self.project, fallback="claude")

    def test_malformed_configuration_fails_closed(self):
        invalid = ["{", "[]", '{"schema":true}', '{"schema":1,"default":{"direct_api":"false"}}',
                   '{"schema":1,"default":{"agent":"codex","allowed_agents":["claude"]}}',
                   '{"schema":1,"projects":{"ALPHA":{},"alpha":{}}}',
                   '{"schema":1,"schema":1}', '{"schema":1,"default":{"typo":"codex"}}',
                   '{"schema":1,"default":{"allowed_agents":[]}}']
        for raw in invalid:
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ValueError):
                    agent_routes.resolve(self.data, self.project, "codex")
                with self.assertRaises(ValueError):
                    agent_routes.direct_api_allowed(self.data, self.project)
        self.path.write_bytes(b"\xff")
        with self.assertRaises(ValueError):
            agent_routes.resolve(self.data, self.project, "codex")

    def test_ticket_and_project_start_use_route_but_retain_legacy_defaults(self):
        for configured in (False, True):
            if configured:
                self.write()
            wanted = "cloudwave-codex" if configured else "claude"
            server.api_start_run(self.P, self.request({"mode": "analyze"}), self.ticket["key"])
            self.assertEqual(self.runner.start.call_args.args[2], wanted)
            server.api_project_run(self.P, self.request({"mode": "kb", "target": "overview"}), "ALPHA")
            self.assertEqual(self.runner.start.call_args.args[2], wanted)

    def test_http_entry_denies_wrong_engine_before_start_or_ticket_write(self):
        self.write()
        with self.assertRaises(ApiError) as caught:
            server.api_start_run(self.P, self.request({"agent": "claude"}), self.ticket["key"])
        self.assertEqual(caught.exception.code, 400)
        self.runner.start.assert_not_called()
        count = len(self.store.tickets())
        with self.assertRaises(ApiError):
            server.api_new_ticket(self.P, self.request({"project": "ALPHA", "title": "Denied", "type": "feature",
                                  "agent": "claude", "mode": "analyze"}))
        self.assertEqual(len(self.store.tickets()), count)

    def test_api_ticket_submission_remains_held_without_model_execution(self):
        self.write()
        result = server.api_new_ticket(self.P, self.request({"project": "ALPHA", "title": "Held",
                                       "type": "feature", "auto": False}))
        self.assertEqual(result["title"], "Held")
        self.runner.start.assert_not_called()

    def test_survey_and_eval_defaults_obey_project_route(self):
        self.write()
        with patch("tmh.platform.agents.load_config", return_value={"cloudwave-codex": {}}), \
                patch("tmh.platform.survey.Survey") as survey:
            server.api_survey_start(self.P, self.request({}), "ALPHA")
            self.assertEqual(survey.call_args.args[2], "cloudwave-codex")
        with patch("tmh.platform.learn.run_evals") as run:
            server.api_eval_run(self.P, self.request({}), "ALPHA")
            self.assertEqual(run.call_args.args[2], "cloudwave-codex")

    def test_explicit_eval_engine_can_override_unavailable_default_when_allowed(self):
        self.write({"schema": 1, "projects": {"ALPHA": {"agent": "cloudwave-codex",
                   "allowed_agents": ["cloudwave-codex", "codex"]}}})
        self.agents[-1]["available"] = False
        with patch("tmh.platform.learn.run_evals") as run:
            server.api_eval_run(self.P, self.request({"agent": "codex"}), "ALPHA")
            self.assertEqual(run.call_args.args[2], "codex")

    def test_flow_intake_and_handwork_select_route_without_other_provider(self):
        self.write()
        (self.data / "autoflow.json").write_text('{"understand":"agent"}', encoding="utf-8")
        self.assertEqual(self.P.flow.agent({"agent": "claude"}, self.project), "cloudwave-codex")
        self.assertEqual(intake.understander(self.P, self.project), "cloudwave-codex")
        with patch("tmh.platform.handwork.available", return_value=self.agents):
            self.assertEqual(handwork.reviewer(self.P, self.project), "cloudwave-codex")
        self.agents[-1]["available"] = False
        self.P.flow._flow_analyze(self.project, self.ticket["id"], {"agent": "claude"})
        self.runner.start.assert_not_called()
        self.assertTrue(any("不可用" in event["body"] for event in self.store.events(self.ticket["id"])))

    def test_codex_only_route_blocks_direct_api_chooser_and_model_triage(self):
        self.write()
        with patch("tmh.kbqa.router_conf") as config, patch("tmh.kbqa.triage", return_value={}) as triage:
            self.assertIsNone(server._chooser(self.P, self.project))
            config.assert_not_called()
            with self.assertRaises(ApiError) as caught:
                server.api_kb_triage(self.P, self.request({"request": "Fix issue"}), "ALPHA")
            self.assertEqual(caught.exception.code, 400)
            triage.assert_not_called()
            server.api_kb_triage(self.P, self.request({"request": "Fix issue", "model": False}), "ALPHA")
            self.assertFalse(triage.call_args.kwargs["use_model"])

    def test_command_rules_are_explicit_when_direct_api_disabled(self):
        self.write()
        with patch("tmh.kbqa.router_conf") as config, patch("tmh.platform.command.plan", return_value={"kind": "question"}) as plan:
            result = server.api_command(self.P, self.request({"text": "查看任务"}), "ALPHA")
            config.assert_not_called()
            self.assertEqual(plan.call_args.args[-1], {})
            self.assertIn("model_skipped", result)

    def test_unconfigured_direct_api_remains_available(self):
        with patch("tmh.kbqa.router_conf", return_value={"ready": True}) as config, \
                patch("tmh.kbqa.choose", return_value={"index": 1}) as choose:
            self.assertEqual(server._chooser(self.P, self.project)("text", "q", []), 1)
            config.assert_called_once()
            choose.assert_called_once()

    def test_project_metadata_is_scoped_and_does_not_probe_or_execute(self):
        self.write({"schema": 1, "projects": {
            "ALPHA": {"agent": "cloudwave-codex", "direct_api": False},
            "BETA": {"agent": "private-other-route"}}})
        request = SimpleNamespace(user="alice", h=SimpleNamespace(headers={}))
        with patch("tmh.platform.tenant_policy.visible_projects", return_value=[dict(self.project)]), \
                patch("tmh.platform.agents.available", side_effect=AssertionError("read must not probe")):
            rows = server.api_projects(self.P, request)
        self.assertEqual(rows[0]["agent_route"], {"agent": "cloudwave-codex", "direct_api": False})
        self.assertEqual(rows[0]["agent_route_error"], "")
        self.assertNotIn("private-other-route", json.dumps(rows))
        self.path.write_text("{", encoding="utf-8")
        metadata = server._route_metadata(self.P, self.project)
        self.assertEqual(metadata["agent_route"], {})
        self.assertTrue(metadata["agent_route_error"])
        self.runner.start.assert_not_called()

    def test_route_configuration_never_grants_tenant_execution(self):
        from tests.test_tenant_policy import Context
        from tmh.platform.tool_access import allowed_operations
        self.write()
        self.P.tenant_context = Context(self.root)
        self.P.flow.tenant_context = self.P.tenant_context
        self.assertFalse(self.P.flow.autoflow()["on"])
        self.assertFalse(self.P.flow.autoflow()["merge"])
        for actor in ("owner", "alice", "bob"):
            with self.subTest(actor=actor), self.assertRaises(ApiError) as caught:
                tenant_policy.authorize(self.P, "POST", "/api/tickets/ALPHA-1/runs", {}, {"agent": "cloudwave-codex"}, actor)
            self.assertEqual(caught.exception.code, 403)
        self.assertNotIn("run_start", allowed_operations("content"))
        tenant_policy.authorize(self.P, "POST", "/api/tickets", {},
                                {"project": "ALPHA", "auto": False, "title": "held"}, "alice")


if __name__ == "__main__":
    unittest.main()
