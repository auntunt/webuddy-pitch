"""A new project must be executable, isolated and recoverable, not just a registered path."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh import config
from tmh.platform import delivery, preview, project_bootstrap
from tmh.platform.agents import GREENFIELD_EDIT, GREENFIELD_FIX, Runner, build_prompt
from tmh.platform.errors import ApiError
from tmh.platform.fixloop import FixLoop
from tmh.platform.store import Store


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        data = Path(self.tmp.name)
        self.P = SimpleNamespace(data_dir=data, store=Store(data / "platform.db"))
        self.addCleanup(self.P.store.db.close)
        self.P.project = lambda key: self.P.store.project(key)

    def test_runnable_project_has_tests_git_baseline_and_preview(self):
        result = project_bootstrap.create(self.P, {"key": "DEMO", "name": "发布工作台", "brief": "保留所有需求"}, "Li")
        root = Path(result["project"]["root"])
        self.assertEqual(root, (self.P.data_dir / "projects" / "DEMO").resolve())
        self.assertEqual(result["checks"]["test"]["exit_code"], 0)
        self.assertIn("Ran 26 tests", result["checks"]["test"]["output"])
        self.assertTrue(config.load(root)["commands"]["test"])
        self.assertEqual(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True), "")
        self.assertEqual(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(), result["commit"])
        self.assertIn("{prefix}", preview.project_conf(self.P.data_dir, "DEMO")["cmd"])
        self.assertIn(str(self.P.data_dir / "projects" / "DEMO" / "app.db"), preview.project_conf(self.P.data_dir, "DEMO")["cmd"])
        receipt = json.loads((self.P.data_dir / "project-bootstrap" / "DEMO.json").read_text())
        self.assertEqual(receipt["checks"], result["checks"])
        before = (root / "project.json").read_text()
        with self.assertRaises(ApiError):
            project_bootstrap.create(self.P, {"key": "demo", "name": "不可覆盖"}, "Li")
        self.assertEqual((root / "project.json").read_text(), before)

    def test_input_cannot_escape_owned_directory(self):
        for value in ("../escape", "X/../Y", "A;touch pwn", "A" * 11, ""):
            with self.subTest(value=value), self.assertRaises(ApiError):
                project_bootstrap.create(self.P, {"key": value, "name": "x"}, "Li")
        outside = self.P.data_dir / "outside"
        outside.mkdir()
        (self.P.data_dir / "projects").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ApiError):
            project_bootstrap.create(self.P, {"key": "TEST", "name": "x"}, "Li")
        self.assertEqual(list(outside.iterdir()), [])

    def test_preview_configuration_failure_preserves_created_project_and_receipt(self):
        broken = self.P.data_dir / "previews.json"
        broken.write_text("{invalid json", encoding="utf-8")
        result = project_bootstrap.create(self.P, {"key": "RECOVER", "name": "可恢复项目"}, "Li")
        self.assertEqual(self.P.store.project("RECOVER"), result["project"])
        self.assertFalse(result["preview_configured"])
        self.assertTrue(any("预览配置失败" in text for text in result["warnings"]))
        self.assertEqual(result["checks"]["test"]["exit_code"], 0)
        saved = json.loads((self.P.data_dir / "project-bootstrap" / "RECOVER.json").read_text())
        self.assertEqual(saved, result)
        self.assertEqual(broken.read_text(), "{invalid json")
        self.assertEqual(subprocess.check_output(["git", "status", "--porcelain"],
                                                cwd=result["project"]["root"], text=True), "")

    def test_unwritable_receipt_does_not_hide_registered_project(self):
        (self.P.data_dir / "project-bootstrap").write_text("existing file", encoding="utf-8")
        result = project_bootstrap.create(self.P, {"key": "RECEIPT", "name": "回执恢复"}, "Li")
        self.assertEqual(self.P.store.project("RECEIPT"), result["project"])
        self.assertTrue(result["preview_configured"])
        self.assertTrue(any("创建回执未能写入磁盘" in text for text in result["warnings"]))
        self.assertEqual((self.P.data_dir / "project-bootstrap").read_text(), "existing file")

    def test_delivery_runner_sends_current_request_instead_of_short_session_followup(self):
        project = self.P.store.add_project("FRESH", "当前交付资料", str(self.P.data_dir))
        ticket = self.P.store.create_ticket(project["id"], "实现当前需求", "Li", auto=False,
                                             links={"delivery": "a" * 12, "greenfield": True})
        prompt = "当前需求第 2 版\n本轮补充要求：保留完整审计记录"
        run = self.P.store.create_run(project["id"], ticket["id"], "codex", "plan", "Li", prompt)
        runner = Runner(self.P.store, self.P.data_dir)
        with mock.patch("tmh.platform.agents.earlier_session") as previous, \
                mock.patch.object(runner, "invoke", return_value=(0, "已完成当前方案")) as invoke:
            runner._go(run["id"], project, ticket, "codex", "plan", prompt, {}, "", False)
        previous.assert_not_called()
        self.assertEqual(invoke.call_args.args[6], prompt)
        self.assertNotIn("resume", invoke.call_args.kwargs)
        self.assertEqual(self.P.store.run(run["id"])["status"], "done")

    def test_delivery_prompt_preserves_full_acceptance_and_scopes_new_product_rules(self):
        p = self.P.store.add_project("APP", "完整需求", str(self.P.data_dir))
        created = delivery.create(self.P, {"project": "APP", "type": "new_product", "title": "新产品", "goal": "完整目标"}, "Li")
        did = created["delivery"]["id"]
        content = "A1：保存需求\n" + "完整内容。" * 1800 + "\nA2：末尾验收条款不能丢失"
        delivery.act(self.P, did, {"action": "save_artifact", "stage": "requirements", "body": content}, "Li")
        delivery.act(self.P, did, {"action": "review_artifact", "stage": "requirements", "version": 1,
                                   "confirm": True, "evidence": "测试中核对了完整验收条款"}, "Li")
        ticket = self.P.store.ticket(created["delivery"]["ticket_id"])
        unrelated = self.P.store.create_run(p["id"], ticket["id"], "codex", "plan", "Li", "未复核方案")
        self.P.store.update_run(unrelated["id"], status="done", exit_code=0, result="未复核方案不得污染交付提示")
        prompt = build_prompt(self.P.store, p, ticket, "plan")
        self.assertIn(content, prompt)
        self.assertIn("可以规划必要的新测试和构建配置", prompt)
        self.assertNotIn("不要新增测试文件", prompt)
        self.assertNotIn("未复核方案不得污染交付提示", prompt)
        self.assertIn("产出当前交付阶段的草稿", build_prompt(self.P.store, p, ticket, "ask", question="需求阶段"))
        ordinary = self.P.store.create_ticket(p["id"], "普通工单", "Li", auto=False)
        self.assertIn("不要新增测试文件", build_prompt(self.P.store, p, ordinary, "plan"))


class DeliveryExecutionPromptTest(unittest.TestCase):
    def test_fix_uses_reviewed_plan_binding_even_when_a_newer_plan_exists(self):
        loop = self.loop()
        loop.t.update(id=7, project_id=1)
        loop.t["links"]["delivery_plan_run"] = 10
        reviewed = {"id": 10, "ticket_id": 7, "mode": "plan", "status": "done", "exit_code": 0,
                    "result": '```tmh-plan\n{"files":[{"path":"app.py","goal":"已复核的业务行为"}],"ac":[]}\n```'}
        loop.st.run.return_value = reviewed
        loop.st.runs.return_value = [{"id": 99, "mode": "plan", "status": "done"}]
        loop.set = {"max_files": 16}
        loop.commands = mock.Mock(side_effect=RuntimeError("stop after selecting plan"))
        # This unit tests selection of the reviewed plan; real reference-input
        # validity is covered by test_library_integration with a real Store.
        with mock.patch('tmh.platform.project_library.require_run_current') as current:
            with self.assertRaisesRegex(RuntimeError, "stop after selecting plan"):
                loop.run()
        current.assert_called_once_with(loop.st, loop.st.project.return_value, 10)
        loop.st.run.assert_called_once_with(10)
        loop.st.runs.assert_not_called()
        loop.commands.assert_called_once_with({"app.py": "已复核的业务行为"})
        loop.t["links"].pop("delivery_plan_run")
        code, reason = loop.run()
        self.assertEqual(code, 1)
        self.assertIn("绑定已复核", reason)

    def loop(self):
        loop = FixLoop.__new__(FixLoop)
        loop.t = {"links": {"delivery": "a" * 12, "greenfield": True}}
        loop.prompt = "已复核需求第 2 版\n本轮必须保存完整审计记录\n\n" + GREENFIELD_FIX
        loop.st = mock.Mock()
        loop.p = {"key": "APP"}
        loop.r = SimpleNamespace(data_dir=Path("/unused"))
        loop.agent = "codex"
        loop.wt = Path("/unused/worktree")
        loop.sid = "obsolete-plan-session"
        loop.nobuild = ""
        loop.notes = {}
        loop.say = mock.Mock()
        loop.call = mock.Mock(return_value="已完成当前修改")
        return loop

    def test_whole_and_retry_keep_current_packet_and_failure_evidence(self):
        loop = self.loop()
        with mock.patch("tmh.platform.fixloop.earlier_session") as previous:
            loop.whole(None)
            loop.whole({"evidence": "重启后记录丢失", "cause": "写入未提交", "guide": "提交事务再返回成功"})
        previous.assert_not_called()
        first, retry = loop.call.call_args_list
        for call in (first, retry):
            self.assertEqual(call.args[0], "fix")
            self.assertIn("本轮必须保存完整审计记录", call.args[1])
            self.assertIn(GREENFIELD_FIX, call.args[1])
            self.assertEqual(call.kwargs, {})
        self.assertIn("重启后记录丢失", retry.args[1])
        self.assertIn("写入未提交", retry.args[1])
        self.assertIn("提交事务再返回成功", retry.args[1])

    def test_per_file_work_keeps_stage_request_and_only_its_own_file_instruction(self):
        loop = self.loop()
        loop.set = {"max_files": 16}
        loop.models = {"edit": ""}
        loop.brought = set()
        loop.cancelled = mock.Mock(return_value=False)
        loop.dirty = mock.Mock(return_value={})
        loop.keep_to = mock.Mock()
        with mock.patch("tmh.platform.fixloop.additional_context_prompt", return_value="重新读取的资料\n" + GREENFIELD_FIX) as rebuilt:
            loop.collaborate({"tests/test_audit.py": "新增审计持久化测试"}, {"guide": "覆盖重启后读取"})
        rebuilt.assert_not_called()  # Delivery must use the reviewed frozen packet.
        loop.call.assert_called_once()
        prompt = loop.call.call_args.args[1]
        self.assertIn("本轮必须保存完整审计记录", prompt)
        self.assertIn("覆盖重启后读取", prompt)
        self.assertIn(GREENFIELD_EDIT.replace("{target}", "tests/test_audit.py"), prompt)
        self.assertNotIn(GREENFIELD_FIX, prompt)
        self.assertNotIn("不要新增测试文件", prompt)
        loop.keep_to.assert_called_once_with("tests/test_audit.py", {})


if __name__ == "__main__":
    unittest.main()
