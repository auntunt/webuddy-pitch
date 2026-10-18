"""Execution handoffs must preserve the request and reject known failed changes."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh import config
from tmh.platform.agents import Runner, build_prompt, git, make_worktree, worktree_diff
from tmh.platform.fixloop import FixLoop, recheck
from tmh.platform.store import Store


class RunHandoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("EDIT", "编辑验收", str(self.data))
        self.ticket = self.store.create_ticket(self.project["id"], "保存原事项", "agent", auto=False)
        self.runner = Runner(self.store, self.data)

    def test_long_request_plan_and_failure_feedback_survive_handoff(self):
        body = "完整需求\n" + "标题和状态必须保留。" * 600 + "\n需求末尾：重试不能新增记录"
        self.ticket = self.store.update_ticket(self.ticket["id"], "agent", body=body)
        comment = "操作补充。" * 200 + "末尾：按失败页的表单重试"
        rejection = "复现记录。" * 200 + "末尾：另外一条记录不得改变"
        self.store.event(self.ticket["id"], "agent", "comment", comment)
        self.store.event(self.ticket["id"], "agent", "reject", rejection)
        run = self.store.create_run(self.project["id"], self.ticket["id"], "codex", "plan", "agent", "")
        plan = "完整方案\n" + "实现编辑和失败恢复。" * 600 + '\n```tmh-plan\n{"files":[{"path":"app.py"}],"ac":[{"id":"A5","text":"故障重试不新增"}]}\n```'
        self.store.update_run(run["id"], status="done", exit_code=0, result=plan)
        prompt = build_prompt(self.store, self.project, self.ticket, "fix")
        for name, value in (("需求", body), ("方案", plan), ("补充", comment), ("退回", rejection)):
            self.assertTrue(value in prompt, name + "必须完整保留")

    def test_resumed_plan_and_fix_receive_current_full_contract(self):
        run = self.store.create_run(self.project["id"], self.ticket["id"], "codex", "plan", "agent", "")
        current = "需求已修改：503重试必须更新原id，不能新增记录"
        previous = {"mode": "analyze", "ended": "2026-10-18 00:00:00"}
        with mock.patch("tmh.platform.agents.earlier_session", return_value=("session", previous)), \
                mock.patch.object(self.runner, "invoke", return_value=(0, "方案")) as invoke:
            self.runner._go(run["id"], self.project, self.ticket, "codex", "plan", current, {})
        self.assertIn(current, invoke.call_args.args[6])
        self.assertEqual(invoke.call_args.kwargs["resume"], "session")
        loop = FixLoop.__new__(FixLoop)
        from tmh.platform.agents import MODE_TEXT
        loop.prompt = current + "\n\n" + MODE_TEXT["fix"]
        loop.t, loop.st, loop.r, loop.wt = self.ticket, self.store, self.runner, self.data
        loop.agent, loop.sid, loop.nobuild, loop.notes = "codex", "session", "", {}
        loop.say = mock.Mock()
        loop.call = mock.Mock(return_value="已修改")
        loop.whole({"evidence": "重试误新增", "guide": "使用编辑地址"})
        self.assertIn(current, loop.call.call_args.args[1])
        self.assertIn("重试误新增", loop.call.call_args.args[1])
        self.assertEqual(loop.call.call_args.kwargs["resume"], "session")

    def test_failed_runs_or_checks_cannot_commit_or_remove_the_worktree(self):
        for status, exit_code, verification in (
            ("failed", 1, {}), ("cancelled", 0, {}), ("done", 2, {}),
            ("done", 0, {"check": "fail"}),
            ("done", 0, {"check": "pass", "commands": [{"exit_code": 1}]}),
            ("done", 0, {"check": "pass", "verdict": "fail"}),
            ("done", 0, {"check": "pass", "beyond_plan": ["unplanned.py"]}),
            ("done", 0, ["unreadable verification"]),
        ):
            with self.subTest(status=status, exit_code=exit_code, verification=verification):
                run = self.store.create_run(self.project["id"], self.ticket["id"], "codex", "fix", "agent", "")
                self.store.update_run(run["id"], status=status, exit_code=exit_code, diff="real change",
                                      workdir=str(self.data / "worktree"))
                folder = self.data / "runs" / str(run["id"])
                folder.mkdir(parents=True)
                (folder / "verify.json").write_text(json.dumps(verification))
                with mock.patch("tmh.platform.agents.git") as git:
                    with self.assertRaises(ValueError):
                        self.runner.decide(run["id"], "accept", "自动流转")
                    git.assert_not_called()
                self.assertEqual(self.store.run(run["id"])["decision"], "")

    def test_passing_commands_do_not_invent_a_missing_diagnosis(self):
        folder = self.data / "runs" / "77"
        folder.mkdir(parents=True)
        loop = FixLoop.__new__(FixLoop)
        loop.r, loop.rid, loop.t = SimpleNamespace(data_dir=self.data), 77, None
        loop.wt, loop.set = self.data, {"rounds": 0, "split_from": 3}
        loop.box, loop.nobuild, loop.ok = None, "", True
        loop.brought, loop.log, loop.notes = set(), [], {}
        loop.commands = mock.Mock(return_value=([("test", "python3 -m unittest")], ""))
        loop.baseline = mock.Mock(return_value="")
        loop.execute = mock.Mock(return_value=[{"kind": "test", "command": "python3 -m unittest", "exit_code": 0}])
        loop.cancelled = mock.Mock(return_value=False)
        loop.whole = mock.Mock()
        loop.diagnose = mock.Mock(return_value={"text": "模型未返回有效结论"})
        loop.say = mock.Mock()
        with mock.patch("tmh.platform.fixloop.worktree_diff", return_value="diff --git a/app.py b/app.py\n+edit"):
            code, summary = loop.run()
        saved = json.loads((folder / "verify.json").read_text())
        self.assertEqual(code, 0)
        self.assertEqual(saved["check"], "pass")
        self.assertEqual(saved["verdict"], "unknown")
        self.assertIn("没有给出结论", summary)
        self.assertNotIn("诊断认为已解决", summary)

    def recheck_fixture(self, verdict="fail"):
        root = self.data / "source"
        root.mkdir()
        (root / "app.py").write_text("VALUE = 0\n")
        (root / ".gitignore").write_text("__pycache__/\n")
        cfg = config.load(root)
        cfg["commands"].update(build=sys.executable + " -m py_compile app.py", test="")
        config.save(root, cfg)
        for args in (("init", "-q"), ("add", "app.py", ".gitignore", ".tmh/config.json"),
                     ("-c", "user.name=tests", "-c", "user.email=tests@localhost", "commit", "-qm", "baseline")):
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        p = self.store.add_project("CHECK", "重新验证", str(root))
        ticket = self.store.create_ticket(p["id"], "修正已完成运行的边界", "agent", auto=False)
        run = self.store.create_run(p["id"], ticket["id"], "codex", "fix", "agent", "")
        wt, _ = make_worktree(self.data, p, ticket, run["id"])
        (wt / "app.py").write_text("VALUE = 1\n")
        before = worktree_diff(wt)
        self.store.update_run(run["id"], status="done", exit_code=0, workdir=str(wt), diff=before)
        folder = self.data / "runs" / str(run["id"])
        folder.mkdir(parents=True)
        (folder / "verify.json").write_text(json.dumps({"check": "pass", "verdict": verdict, "diagnosis": {"cause": "原始模型诊断"}}))
        return root, run, wt, folder, before

    def test_recheck_refreshes_changed_code_and_invalidates_old_diagnosis(self):
        root, run, wt, folder, before = self.recheck_fixture()
        (wt / "app.py").write_text("VALUE = 2\n")
        current = worktree_diff(wt)
        result = recheck(self.runner, run["id"])
        self.assertEqual(result["check"], "pass")
        self.assertTrue(result["commands"])
        self.assertTrue(all(x["exit_code"] == 0 for x in result["commands"]))
        self.assertEqual(result["verdict"], "unknown")
        self.assertEqual(result["diagnosis"], {})
        self.assertEqual(result["previous_verifications"][0]["diff"], before)
        self.assertEqual(result["previous_verifications"][0]["verification"]["verdict"], "fail")
        self.assertEqual(self.store.run(run["id"])["diff"], current)
        self.assertFalse(result["code_changed_during_check"])

    def test_accepted_recheck_uses_commit_object_even_with_hex_named_branch(self):
        root, run, wt, folder, original = self.recheck_fixture(verdict="pass")
        adopted = self.runner.decide(run["id"], "accept", "自动流转")
        short = adopted["decision"].rsplit("@", 1)[-1]
        from tmh.platform.preview import _commit
        exact = _commit(root, short)
        (root / "app.py").write_text("VALUE = 9\n")
        git(root, "add", "app.py")
        git(root, "-c", "user.name=test", "-c", "user.email=test@localhost", "commit", "-qm", "unrelated change")
        git(root, "branch", short, "HEAD")
        result = recheck(self.runner, run["id"])
        self.assertEqual(result["check"], "pass")
        self.assertEqual(result["checked_commit"], exact)
        self.assertEqual(result["checked_diff"], original)
        self.assertEqual(self.store.run(run["id"])["diff"], original)
        self.assertEqual(result["verdict"], "pass")
        self.assertNotIn("+VALUE = 9", result["checked_diff"])
        self.assertFalse((self.data / "worktrees" / ("recheck-%d" % run["id"])).exists())

    def test_accepted_recheck_test_mutations_do_not_replace_adopted_diff_or_erase_history(self):
        root, run, wt, folder, original = self.recheck_fixture(verdict="pass")
        adopted = self.runner.decide(run["id"], "accept", "自动流转")
        short = adopted["decision"].rsplit("@", 1)[-1]
        def mutate(loop, seq, untouched=False):
            (loop.wt / "app.py").write_text("VALUE = 3\n")
            return [{"kind": "test", "command": "fixture rewrites source", "exit_code": 0, "tail": "kept evidence"}]
        with mock.patch.object(FixLoop, "baseline", return_value=""), mock.patch.object(FixLoop, "execute", mutate):
            changed = recheck(self.runner, run["id"])
        self.assertEqual(changed["check"], "fail")
        self.assertEqual(changed["verdict"], "unknown")
        self.assertTrue(changed["code_changed_during_check"])
        self.assertEqual(changed["checked_diff"], original)
        self.assertIn("+VALUE = 3", changed["after_check_diff"])
        self.assertEqual(self.store.run(run["id"])["diff"], original)
        self.assertEqual(git(root, "show", short + ":app.py").strip(), "VALUE = 1")
        # A clean recheck proves the commit's tests, while the old model verdict stays invalidated.
        rerun = recheck(self.runner, run["id"])
        self.assertEqual(rerun["check"], "pass")
        self.assertEqual(rerun["verdict"], "unknown")
        self.assertFalse(rerun["code_changed_during_check"])
        self.assertNotIn("after_check_diff", rerun)
        self.assertEqual(self.store.run(run["id"])["diff"], original)
        self.assertEqual(len(rerun["previous_verifications"]), 2)
        prior = rerun["previous_verifications"][-1]["verification"]
        self.assertEqual(prior["after_check_diff"], changed["after_check_diff"])
        self.assertEqual(prior["commands"], changed["commands"])
        self.assertEqual(prior["check"], "fail")
        self.assertEqual(rerun["previous_verifications"][0]["verification"]["diagnosis"], {"cause": "原始模型诊断"})

    def test_unadopted_recheck_refreshes_test_mutations_but_blocks_acceptance(self):
        root, run, wt, folder, original = self.recheck_fixture(verdict="pass")
        def mutate(loop, seq, untouched=False):
            (loop.wt / "app.py").write_text("VALUE = 3\n")
            return [{"kind": "test", "command": "fixture rewrites source", "exit_code": 0}]
        with mock.patch.object(FixLoop, "baseline", return_value=""), mock.patch.object(FixLoop, "execute", mutate):
            result = recheck(self.runner, run["id"])
        self.assertEqual(result["check"], "fail")
        self.assertEqual(result["verdict"], "unknown")
        self.assertEqual(result["checked_diff"], original)
        self.assertEqual(self.store.run(run["id"])["diff"], result["after_check_diff"])
        self.assertIn("+VALUE = 3", self.store.run(run["id"])["diff"])
        with mock.patch("tmh.platform.agents.git") as mutate_git:
            with self.assertRaises(ValueError):
                self.runner.decide(run["id"], "accept", "自动流转")
            mutate_git.assert_not_called()

    def test_adopt_rejects_code_changed_after_passing_check(self):
        root, run, wt, folder, original = self.recheck_fixture(verdict="pass")
        checked = recheck(self.runner, run["id"])
        self.assertEqual(checked["check"], "pass")
        before_head = git(wt, "rev-parse", "HEAD")
        (wt / "app.py").write_text("def broken(:\n")
        with mock.patch("tmh.platform.agents.git", wraps=git) as observed:
            with self.assertRaisesRegex(ValueError, "当前代码与展示或验证的版本不一致"):
                self.runner.decide(run["id"], "accept", "自动流转")
        self.assertFalse(any("commit" in call.args for call in observed.call_args_list))
        self.assertFalse(any(call.args[1:] == ("add", "-A") for call in observed.call_args_list))
        self.assertEqual(git(wt, "rev-parse", "HEAD"), before_head)
        self.assertEqual((wt / "app.py").read_text(), "def broken(:\n")
        self.assertEqual(self.store.run(run["id"])["decision"], "")
        self.assertEqual(self.store.run(run["id"])["diff"], original)

    def test_adopt_rejects_changed_code_even_if_shown_diff_was_updated_without_recheck(self):
        root, run, wt, folder, original = self.recheck_fixture(verdict="pass")
        recheck(self.runner, run["id"])
        (wt / "app.py").write_text("VALUE = 2\n")
        self.store.update_run(run["id"], diff=worktree_diff(wt))
        with self.assertRaisesRegex(ValueError, "当前代码与展示或验证的版本不一致"):
            self.runner.decide(run["id"], "accept", "自动流转")
        self.assertEqual(self.store.run(run["id"])["decision"], "")
        self.assertTrue(wt.is_dir())

    def test_adopt_legacy_without_verification_still_requires_displayed_diff(self):
        root, run, wt, folder, original = self.recheck_fixture(verdict="pass")
        (folder / "verify.json").unlink()
        (wt / "app.py").write_text("def broken(:\n")
        with self.assertRaisesRegex(ValueError, "当前代码与展示或验证的版本不一致"):
            self.runner.decide(run["id"], "accept", "自动流转")
        self.assertEqual(self.store.run(run["id"])["decision"], "")
        # The existing legacy policy still permits the exact displayed version on its isolated branch.
        (wt / "app.py").write_text("VALUE = 1\n")
        accepted = self.runner.decide(run["id"], "accept", "自动流转")
        self.assertTrue(accepted["decision"].startswith("accepted:"))
        sha = accepted["decision"].rsplit("@", 1)[-1]
        self.assertEqual(git(root, "show", sha + ":app.py").strip(), "VALUE = 1")
        self.assertFalse((folder / "verify.json").exists(), "legacy acceptance must not invent verification")

    def test_adopt_existing_unreadable_verification_rejects_before_git_mutation(self):
        root, run, wt, folder, original = self.recheck_fixture(verdict="pass")
        for raw in (b'{"check":"fail"', b'\xff', b'', b'null', b'[]'):
            with self.subTest(raw=raw):
                (folder / "verify.json").write_bytes(raw)
                with mock.patch("tmh.platform.agents.git") as mutate_git:
                    with self.assertRaisesRegex(ValueError, "验证记录不可读"):
                        self.runner.decide(run["id"], "accept", "自动流转")
                    mutate_git.assert_not_called()
                self.assertEqual(self.store.run(run["id"])["decision"], "")
                self.assertTrue(wt.is_dir())

    def test_adopt_rechecks_the_snapshot_staged_after_the_initial_diff_read(self):
        root, run, wt, folder, original = self.recheck_fixture(verdict="pass")
        recheck(self.runner, run["id"])
        before_head = git(wt, "rev-parse", "HEAD")
        def race(where, *args, **kwargs):
            if args == ("add", "-A"):
                (wt / "app.py").write_text("def broken(:\n")
            return git(where, *args, **kwargs)
        with mock.patch("tmh.platform.agents.git", side_effect=race) as observed:
            with self.assertRaisesRegex(ValueError, "代码在采纳期间发生变化"):
                self.runner.decide(run["id"], "accept", "自动流转")
        self.assertFalse(any("commit" in call.args for call in observed.call_args_list))
        self.assertEqual(git(wt, "rev-parse", "HEAD"), before_head)
        self.assertEqual(self.store.run(run["id"])["decision"], "")
        self.assertTrue(wt.is_dir())

    def test_adopt_rejects_unverified_changed_baseline_even_when_diff_is_identical(self):
        root, run, wt, folder, original = self.recheck_fixture(verdict="pass")
        checked_base = git(wt, "rev-parse", "HEAD").strip()
        checked = recheck(self.runner, run["id"])
        self.assertEqual(checked["check"], "pass")
        self.assertEqual(checked["checked_base"], checked_base)
        (wt / "unverified-baseline.txt").write_text("external baseline commit\n")
        git(wt, "add", "unverified-baseline.txt")
        git(wt, "-c", "user.name=external", "-c", "user.email=external@localhost", "commit", "-qm", "Unverified baseline")
        new_base = git(wt, "rev-parse", "HEAD").strip()
        self.assertNotEqual(new_base, checked_base)
        self.assertEqual(worktree_diff(wt), original)
        with mock.patch("tmh.platform.agents.git", wraps=git) as observed:
            with self.assertRaisesRegex(ValueError, "当前代码基线与验证的版本不一致"):
                self.runner.decide(run["id"], "accept", "自动流转")
        self.assertFalse(any("commit" in call.args for call in observed.call_args_list))
        self.assertFalse(any(call.args[1:] == ("add", "-A") for call in observed.call_args_list))
        self.assertEqual(self.store.run(run["id"])["decision"], "")
        self.assertEqual(git(wt, "rev-parse", "HEAD").strip(), new_base)
        self.assertTrue(wt.is_dir())
        # Explicitly rechecking the new baseline provides a fresh matching record.
        fresh = recheck(self.runner, run["id"])
        self.assertEqual(fresh["check"], "pass")
        self.assertEqual(fresh["checked_base"], new_base)
        self.assertEqual(fresh["previous_verifications"][-1]["verification"]["checked_base"], checked_base)
        accepted = self.runner.decide(run["id"], "accept", "自动流转")
        self.assertTrue(accepted["decision"].startswith("accepted:"))


if __name__ == "__main__":
    unittest.main()
