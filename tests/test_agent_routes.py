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

    def test_ticket_handed_back_while_doing_goes_on_from_analysis_to_plan(self):
        self.write()
        self.store.update_ticket(self.ticket["id"], "li", status="doing")
        self.P.flow._flow_analyze(self.project, self.ticket["id"], {"agent": "claude", "plan": True})
        then = self.runner.start.call_args.kwargs["then"]
        with patch.object(self.P.flow, "_flow_plan") as plan:
            then({"status": "done", "result": "see src/a.vue:10"})
            plan.assert_called_once()
            self.store.update_ticket(self.ticket["id"], "li", status="verify")
            then({"status": "done", "result": "see src/a.vue:10"})
            plan.assert_called_once()

    def test_criteria_the_client_confirmed_let_a_plan_without_its_own_go_on_to_the_fix(self):
        self.write()
        tid = self.ticket["id"]
        self.store.update_ticket(tid, "li", status="doing")
        self.P.flow._flow_plan(self.project, tid, {"fix": True}, "claude")
        then = self.runner.start.call_args.kwargs["then"]
        with patch.object(self.P.flow, "_flow_fix") as fix:
            then({"id": 1, "status": "done", "result": "A1 prose only"})
            fix.assert_not_called()
            self.assertTrue(any("没有验收标准" in e["body"] for e in self.store.events(tid)))
            with patch("tmh.platform.signoff.client_ac", return_value=[{"id": "A1", "text": "x"}]):
                then({"id": 1, "status": "done", "result": "A1 prose only"})
            fix.assert_called_once()

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


    def test_steps_route_modes_to_their_agent_inside_the_allowlist(self):
        self.write({"schema": 1, "projects": {"ALPHA": {"agent": "cloudwave-codex", "allowed_agents": ["cloudwave-codex", "claude"],
                    "steps": {"analyze": "claude", "plan": "claude", "diagnose": "claude"}}}})
        for mode in ("analyze", "plan", "diagnose"):
            self.assertEqual(agent_routes.step_agent(self.data, self.project, mode, "cloudwave-codex"), "claude")
            self.assertEqual(agent_routes.step_agent(self.data, self.project, mode, ""), "claude")
        for mode in ("fix", "edit", "ask"):
            self.assertEqual(agent_routes.step_agent(self.data, self.project, mode, "cloudwave-codex"), "cloudwave-codex")
        # a person who picked another allowed agent keeps it
        self.assertEqual(agent_routes.step_agent(self.data, self.project, "plan", "codex"), "codex")
        self.assertEqual(agent_routes.step_agent(self.data, "BETA", "plan", "codex"), "codex")
        self.assertEqual(agent_routes.resolve(self.data, self.project, "claude"), "claude")

    def test_steps_fail_closed_outside_the_allowlist_or_on_unknown_modes(self):
        for steps in ({"plan": "codex"}, {"merge": "claude"}, {"plan": ""}, ["plan"]):
            with self.subTest(steps=steps):
                self.write({"schema": 1, "projects": {"ALPHA": {"agent": "cloudwave-codex",
                            "allowed_agents": ["cloudwave-codex", "claude"], "steps": steps}}})
                with self.assertRaises(ValueError):
                    agent_routes.route(self.data, self.project)

    def test_fix_loop_sends_diagnose_to_the_step_agent_and_keeps_the_change_on_the_main_one(self):
        from tmh.platform.fixloop import FixLoop
        self.write({"schema": 1, "projects": {"ALPHA": {"agent": "cloudwave-codex", "allowed_agents": ["cloudwave-codex", "claude"],
                    "steps": {"plan": "claude", "diagnose": "claude"}}}})
        conf = {"cloudwave-codex": {"defaults": {}}, "claude": {"defaults": {"diagnose": "opus-x"}}}
        runner = Mock(data_dir=self.data, store=self.store)
        runner.invoke.return_value = (0, "ok")
        with patch("tmh.platform.fixloop.git", return_value="abc\n"), \
                patch("tmh.platform.fixloop.learning_context_current", return_value=True):
            loop = FixLoop(runner, 1, self.project, None, "cloudwave-codex", conf, "luna", False, "prompt", self.root)
            loop.call("diagnose", "check")
            loop.call("fix", "change")
        calls = [(c.args[3], c.args[5], c.args[8]) for c in runner.invoke.call_args_list]
        self.assertEqual(calls, [("claude", "diagnose", "opus-x"), ("cloudwave-codex", "fix", "luna")])


    def test_fix_loop_has_the_routed_engine_diagnose_a_small_unbuilt_change(self):
        from tmh.platform.fixloop import FixLoop
        conf = {"cloudwave-codex": {"defaults": {}}, "claude": {"defaults": {"diagnose": "opus-x"}}}
        diff = "diff --git a/a.vue b/a.vue\n--- a/a.vue\n+++ b/a.vue\n@@ -1 +1 @@\n-x\n+y\n"
        for steps, diagnosed in (({"diagnose": "claude"}, True), ({}, False)):
            with self.subTest(steps=steps):
                self.write({"schema": 1, "projects": {"ALPHA": {"agent": "cloudwave-codex",
                            "allowed_agents": ["cloudwave-codex", "claude"], "steps": steps}}})
                runner = Mock(data_dir=self.data, store=Mock())
                runner.store.run.return_value = {"status": "running"}
                runner.stop_reason.return_value = ""
                (self.data / "runs" / "1").mkdir(parents=True, exist_ok=True)
                with patch("tmh.platform.fixloop.git", return_value="abc\n"), \
                        patch("tmh.platform.fixloop.worktree_diff", return_value=diff):
                    loop = FixLoop(runner, 1, self.project, None, "cloudwave-codex", conf, "luna", False, "prompt", self.root)
                    loop.commands = Mock(return_value=([], "no build here"))
                    loop.whole = Mock()
                    loop.diagnose = Mock(return_value={"verdict": "pass"})
                    loop.run()
                self.assertEqual(loop.diagnose.called, diagnosed)
                verdict = json.loads((self.data / "runs" / "1" / "verify.json").read_text(encoding="utf-8"))["verdict"]
                self.assertEqual(verdict, "pass" if diagnosed else "unknown")


    def _diagnose_on_ticket(self, said, earlier=(), setup=None, raw=None):
        from tmh.platform.fixloop import FixLoop
        self.write({"schema": 1, "projects": {"ALPHA": {"agent": "cloudwave-codex",
                    "allowed_agents": ["cloudwave-codex", "claude"], "steps": {"diagnose": "claude"}}}})
        conf = {"cloudwave-codex": {"defaults": {}}, "claude": {"defaults": {"diagnose": "opus-x"}}}
        blocker = {"ac": "A1 取消后恢复", "scenario": "第二次打开后取消 → 值没恢复", "where": "a.vue:3"}
        for verdict in earlier:
            verdict, said_then = verdict if isinstance(verdict, tuple) else (verdict, verdict)
            old = self.store.create_run(self.project["id"], self.ticket["id"], "cloudwave-codex", "fix", "alice", "p")["id"]
            self.store.update_run(old, status="done")
            (self.data / "runs" / str(old)).mkdir(parents=True, exist_ok=True)
            (self.data / "runs" / str(old) / "verify.json").write_text(json.dumps(
                {"verdict": verdict, "diagnosis": {"verdict": said_then, "blocking": [blocker], "guide": "old guide"}}), encoding="utf-8")
        rid = self.store.create_run(self.project["id"], self.ticket["id"], "cloudwave-codex", "fix", "alice", "p")["id"]
        self.store.update_run(rid, status="running")
        (self.data / "runs" / str(rid)).mkdir(parents=True, exist_ok=True)
        runner = Mock(data_dir=self.data, store=self.store)
        runner.stop_reason.return_value = ""
        runner.invoke.return_value = (0, raw or "```tmh-diag\n%s\n```" % json.dumps(said, ensure_ascii=False))
        diff = "diff --git a/a.vue b/a.vue\n--- a/a.vue\n+++ b/a.vue\n@@ -1 +1 @@\n-x\n+y\n"
        with patch("tmh.platform.fixloop.git", return_value="abc\n"), patch("tmh.platform.fixloop.worktree_diff", return_value=diff), \
                patch("tmh.platform.fixloop.learning_context_current", return_value=True):
            loop = FixLoop(runner, rid, self.project, self.ticket, "cloudwave-codex", conf, "luna", False, "prompt", self.root)
            loop.commands = Mock(return_value=([], "no build here"))
            loop.whole = Mock()
            loop.context = Mock(return_value="ticket")
            if setup:
                setup(loop)
            _, summary = loop.run()
        verify = json.loads((self.data / "runs" / str(rid) / "verify.json").read_text(encoding="utf-8"))
        return verify, summary, runner.invoke.call_args.args[6]

    def test_a_plan_that_lists_no_files_is_built_on_the_test_machine_from_what_was_changed(self):
        def setup(loop):
            loop.box = Mock()
            loop.commands = Mock(side_effect=lambda goals=None: ([("build", "pnpm exec vite build")], "") if goals else ([], "no files"))
            loop.baseline = Mock(return_value="")
            loop.execute = Mock(return_value=[{"kind": "build", "command": "pnpm exec vite build", "exit_code": 0, "seconds": 1, "tail": ""}])
            self.loop = loop
        verify, _, _ = self._diagnose_on_ticket({"verdict": "pass", "blocking": []}, setup=setup)
        self.assertEqual((verify["check"], verify["skip"], verify["verdict"]), ("pass", "", "pass"))
        self.assertEqual(self.loop.commands.call_args.args[0], {"a.vue": ""})
        self.loop.baseline.assert_called_once()

    def test_a_diagnosis_wrapped_in_a_json_block_under_its_own_name_is_read(self):
        from tmh.platform.fixloop import fenced
        said = {"verdict": "PASS", "blocking_issues": [], "ac": [{"id": "A1", "result": "pass", "how": "a.vue:3"}]}
        out = "看完了\n```json\n%s\n```" % json.dumps({"tmh-diag": said}, ensure_ascii=False)
        self.assertEqual(fenced("tmh-diag", out), said)
        self.assertIsNone(fenced("tmh-diag", "```json\n{\"verdict\": \"pass\"}\n```"))
        self.assertEqual(fenced("tmh-diag", out + "\n```tmh-diag\n{\"verdict\": \"fail\"}\n```"), {"verdict": "fail"})
        verify, _, _ = self._diagnose_on_ticket({}, raw=out)
        self.assertEqual((verify["verdict"], verify["diagnosis"]["blocking"]), ("pass", []))

    def test_a_fail_that_names_no_blocker_is_no_verdict(self):
        verify, _, _ = self._diagnose_on_ticket({"verdict": "fail", "blocking": [], "advisory": ["可能需要深拷贝"]})
        self.assertEqual(verify["verdict"], "unknown")
        self.assertNotIn("stalled", verify)

    def test_blockers_without_a_criterion_or_scenario_are_no_blockers_and_wait_for_a_person(self):
        verify, _, _ = self._diagnose_on_ticket({"verdict": "fail", "blocking": [{}, None, {"ac": "A1", "scenario": " "}]})
        self.assertEqual(verify["verdict"], "unknown")
        self.assertEqual(verify["diagnosis"]["verdict"], "unknown")
        self.assertEqual(verify["diagnosis"]["blocking"], [])
        self.assertTrue(verify["vague_fail"])

    def test_failed_builds_with_passing_diagnoses_are_not_called_circling(self):
        said = {"verdict": "fail", "blocking": [{"ac": "A2", "scenario": "x → y", "where": "a.vue:9"}]}
        verify, _, _ = self._diagnose_on_ticket(said, earlier=(("fail", "pass"), ("fail", "pass")))
        self.assertEqual(verify["verdict"], "fail")
        self.assertNotIn("stalled", verify)

    def test_each_criterion_is_put_to_the_diagnosis_and_its_answer_shown(self):
        plan = self.store.create_run(self.project["id"], self.ticket["id"], "claude", "plan", "alice", "p")["id"]
        self.store.update_run(plan, status="done", result='```tmh-plan\n{"files": [], "ac": [{"id": "A1", "text": "取消后恢复原值", "check": "点取消"}]}\n```')
        said = {"verdict": "pass", "blocking": [], "ac": [{"id": "A1", "result": "pass", "how": "a.vue:3"}]}
        verify, summary, prompt = self._diagnose_on_ticket(said)
        self.assertIn("逐条核对的验收标准", prompt)
        self.assertIn("A1：取消后恢复原值", prompt)
        self.assertEqual(verify["diagnosis"]["ac"], said["ac"])
        self.assertIn("A1：通过（a.vue:3）", summary)

    def test_a_doubt_is_advice_and_does_not_send_the_work_back(self):
        verify, summary, _ = self._diagnose_on_ticket({"verdict": "pass", "blocking": [], "advisory": ["可能需要深拷贝"]})
        self.assertEqual(verify["verdict"], "pass")
        self.assertEqual(verify["diagnosis"]["advisory"], ["可能需要深拷贝"])
        self.assertIn("建议（不影响结论）", summary)

    def test_the_next_change_is_diagnosed_against_the_last_blockers_and_circling_is_called_out(self):
        said = {"verdict": "fail", "blocking": [{"ac": "A2", "scenario": "切换记录后取消 → 显示上一条", "where": "a.vue:9"}]}
        verify, summary, prompt = self._diagnose_on_ticket(said, earlier=("fail", "fail"))
        self.assertIn("这张工单上一次修改（#2）的诊断", prompt)
        self.assertIn("第二次打开后取消", prompt)
        self.assertEqual(verify["verdict"], "fail")
        self.assertEqual(verify["stalled"], 3)
        self.assertIn("在兜圈子", summary)
        self.assertIn("切换记录后取消", summary)

    def test_one_earlier_pass_breaks_the_circle(self):
        said = {"verdict": "fail", "blocking": [{"ac": "A2", "scenario": "x → y", "where": "a.vue:9"}]}
        verify, _, prompt = self._diagnose_on_ticket(said, earlier=("fail", "pass"))
        self.assertNotIn("stalled", verify)
        self.assertNotIn("上一次修改", prompt)


if __name__ == "__main__":
    unittest.main()


class FileLineTest(unittest.TestCase):
    def test_code_locations_written_the_chinese_way_count_as_evidence(self):
        from tmh.platform.orchestra import Orchestra
        text = "// jeecgboot-vue3/src/locales/lang/zh-CN/sys.ts 第 78 行\na.vue:12，b.ts#L3，C.java (line 9)，d.vue（行 4）"
        self.assertEqual(Orchestra.FILE_LINE.findall(text), [("jeecgboot-vue3/src/locales/lang/zh-CN/sys.ts", "78"), ("a.vue", "12"),
                                                             ("b.ts", "3"), ("C.java", "9"), ("d.vue", "4")])
        self.assertEqual(Orchestra.FILE_LINE.findall("改 sys.ts 里的 rememberMe，共 3 处"), [])
        self.assertEqual(
            Orchestra.FILE_LINE.findall("- 文件：`jeecgboot-vue3/src/locales/lang/zh-CN/sys.ts` 第 78 行；**a.vue** 的第 5 行；`b.ts`:7"),
            [("jeecgboot-vue3/src/locales/lang/zh-CN/sys.ts", "78"), ("a.vue", "5"), ("b.ts", "7")])
        from tmh.platform.server import Platform
        self.assertEqual(Platform.FILE_LINE.pattern, Orchestra.FILE_LINE.pattern)
