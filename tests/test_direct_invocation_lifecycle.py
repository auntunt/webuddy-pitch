"""Intake/evaluation callers must seal direct invoke lifecycles on every outcome."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh.platform import intake, learn
from tmh.platform.agents import Runner, git
from tmh.platform.store import Store


READER = r'''
import json, sys
if sys.argv[1] == 'understand':
    label = 'tmh-intake'
    data = {'title': '保存记录失败', 'items': [{'title': '保存记录失败', 'quote': '保存记录后提示错误',
        'kind': '缺陷', 'restated': '保存记录后系统提示错误', 'flow': '', 'questions': [],
        'ac': [{'id': 'A1', 'text': '保存后应显示原事项', 'check': '保存并读回事项'}]}]}
else:
    label = 'tmh-plan'
    data = {'files': [{'path': 'app.py', 'goal': '修正保存行为'}]}
print('fixture-original-output')
print('```' + label + '\n' + json.dumps(data, ensure_ascii=False) + '\n```', flush=True)
'''


class DirectInvocationLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-direct-invoke-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.root = self.data / "project"
        self.root.mkdir()
        (self.root / "app.py").write_text("VALUE = 0\n")
        git(self.root, "init", "-q")
        git(self.root, "add", ".")
        git(self.root, "-c", "user.name=test", "-c", "user.email=test@localhost", "commit", "-qm", "baseline")
        self.commit = git(self.root, "rev-parse", "HEAD").strip()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("DIRECT", "直接调用", str(self.root))
        self.runner = Runner(self.store, self.data)
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, runner=self.runner,
                                 root=lambda p: Path(p["root"]), project=self.store.project)
        self.script = self.data / "reader.py"
        self.script.write_text(READER)
        self.conf = {"reader": {"timeout": .5, "cmd": [sys.executable, str(self.script), "{mode}"]}}
        (self.data / "agents.json").write_text(json.dumps(self.conf))
        (self.data / "autoflow.json").write_text(json.dumps({"on": False, "understand": "rules"}))

    def new_run(self):
        run = self.store.create_run(self.project["id"], None, "reader", "plan", "tester", "fixture prompt")
        self.store.update_run(run["id"], status="running", started="2026-10-18 00:00:00")
        return run["id"]

    def invoke(self, rid):
        return self.runner.invoke(rid, self.project, None, "reader", self.conf, "plan", "fixture prompt", self.root)

    def receipt(self, rid):
        return json.loads((self.data / "runs" / str(rid) / "lifecycle.json").read_text())

    def assert_finished(self, rid, status, reason=""):
        run = self.store.run(rid)
        self.assertEqual(run["status"], status, run["result"])
        self.assertTrue(run["ended"])
        self.assertNotEqual(run["exit_code"], None)
        record = self.receipt(rid)
        self.assertTrue(record["finished"])
        self.assertEqual(record["stopped_reason"], reason)
        self.assertTrue(record["attempts"])
        raw = self.data / record["attempts"][0]["evidence"] / "output.bin"
        self.assertIn(b"fixture-original-output", raw.read_bytes())
        return run

    def interruption(self, action):
        invoke = self.runner.invoke
        def call(*args, **kwargs):
            code, result = invoke(*args, **kwargs)
            self.assertEqual(code, 0, result)
            if action == "timeout":
                time.sleep(self.runner.remaining(args[0]) + .02)
            elif action in ("cancelled", "cancel-exception"):
                self.runner.cancel(args[0], "tester")
            if action in ("exception", "cancel-exception"):
                raise RuntimeError("fixture result collection failed after process cleanup")
            return code, result
        return mock.patch.object(self.runner, "invoke", side_effect=call)

    def conversation(self):
        state = intake.start(self.P, self.project, "保存记录后提示错误，昨天开始所有员工都遇到，希望保存后看到原事项。", "tester", agent=False)
        state["state"] = "understanding"
        state["understanding_job"] = {"id": "fixture-job", "t0": time.time(), "agent": "reader"}
        intake._save(self.data, state)
        return state

    def understand(self, state):
        settings = dict(intake.settings(self.data), timeout=.5)
        with mock.patch.object(intake, "settings", return_value=settings):
            intake._understand(self.P, self.project, state["id"], "fixture-job", "reader")
        return intake.load(self.data, state["id"], self.P)

    def case(self):
        return {"id": "fixture-case", "title": "保存行为", "body": "保存后读回事项", "gold": ["app.py"], "base": self.commit}

    def evaluate(self):
        return learn._run_case(self.P, self.project, self.case(), "reader", "", self.conf, "tester", "fixture-batch")

    def latest(self):
        return self.store.run(self.store.runs(project_id=self.project["id"])[0]["id"])

    def test_success_is_finished_and_later_wall_time_does_not_reclassify_it(self):
        rid = self.new_run()
        code, result = self.invoke(rid)
        self.runner.finish_invocation(rid, code, result)
        self.assert_finished(rid, "done")
        before = self.receipt(rid)
        time.sleep(self.runner.remaining(rid) + .02)
        self.assertEqual(self.runner.stop_reason(rid), "")
        self.assertEqual(self.receipt(rid), before)

    def test_timeout_after_zero_exit_overrides_success_before_direct_finalize(self):
        rid = self.new_run()
        code, result = self.invoke(rid)
        self.assertEqual(code, 0)
        time.sleep(self.runner.remaining(rid) + .02)
        self.runner.finish_invocation(rid, code, result)
        run = self.assert_finished(rid, "failed", "timeout")
        self.assertEqual(run["exit_code"], 124)

    def test_cancel_after_zero_exit_remains_cancelled_when_direct_finalize_runs(self):
        rid = self.new_run()
        code, result = self.invoke(rid)
        self.runner.cancel(rid, "tester")
        self.runner.finish_invocation(rid, code, result)
        self.assertNotEqual(self.assert_finished(rid, "cancelled", "cancelled")["exit_code"], 0)

    def test_intake_success_seals_lifecycle_and_applies_actual_reader_output(self):
        updated = self.understand(self.conversation())
        self.assertEqual(updated["understood"]["by"], "智能体")
        run = self.assert_finished(updated["understood"]["run"], "done")
        self.assertFalse(Path(run["workdir"]).exists())

    def test_intake_timeout_or_cancel_cannot_apply_a_late_successful_answer(self):
        for action, status in (("timeout", "failed"), ("cancelled", "cancelled")):
            with self.subTest(action=action):
                state = self.conversation()
                with self.interruption(action):
                    updated = self.understand(state)
                self.assertEqual(updated["understood"]["by"], "规则")
                self.assert_finished(updated["understood"]["run"], status, action)

    def test_intake_invoke_exception_still_finishes_run_and_keeps_original_process_evidence(self):
        state = self.conversation()
        with self.interruption("exception"):
            updated = self.understand(state)
        self.assertEqual(updated["understood"]["by"], "规则")
        self.assertIn("result collection failed", updated["understood"]["why"])
        run = self.latest()
        self.assert_finished(run["id"], "failed")
        self.assertFalse(Path(run["workdir"]).exists())

    def test_intake_cancelled_then_invoke_exception_still_seals_lifecycle(self):
        state = self.conversation()
        with self.interruption("cancel-exception"):
            updated = self.understand(state)
        self.assertEqual(updated["understood"]["by"], "规则")
        self.assert_finished(self.latest()["id"], "cancelled", "cancelled")

    def test_evaluation_success_finishes_lifecycle_and_removes_only_its_temporary_worktree(self):
        result = self.evaluate()
        self.assertTrue(result["ok"])
        self.assertEqual(result["predicted"], ["app.py"])
        run = self.assert_finished(result["run"], "done")
        self.assertFalse(Path(run["workdir"]).exists())
        self.assertTrue(self.root.is_dir())

    def test_evaluation_timeout_or_cancel_never_reports_successful_execution(self):
        for action, status in (("timeout", "failed"), ("cancelled", "cancelled")):
            with self.subTest(action=action), self.interruption(action):
                result = self.evaluate()
                self.assertFalse(result["ok"])
                self.assert_finished(result["run"], status, action)

    def test_evaluation_exception_records_error_and_finishes_its_created_run(self):
        with self.interruption("exception"):
            learn._run_batch(self.P, self.project, [self.case()], "reader", "", self.conf, "tester", "fixture-exception")
        result = learn.results(self.data, self.project["key"])[-1]
        self.assertIn("result collection failed", result["error"])
        run = self.latest()
        self.assert_finished(run["id"], "failed")
        self.assertFalse(Path(run["workdir"]).exists())

    def test_evaluation_cancelled_then_invoke_exception_still_seals_lifecycle(self):
        with self.interruption("cancel-exception"):
            learn._run_batch(self.P, self.project, [self.case()], "reader", "", self.conf, "tester", "fixture-cancel-exception")
        self.assert_finished(self.latest()["id"], "cancelled", "cancelled")

    def test_real_stream_callback_failure_is_cleaned_up_and_finalized_by_both_callers(self):
        self.script.write_text(READER + "\nimport time\nfor n in range(80):\n    print('callback-stream-' + str(n), flush=True)\ntime.sleep(.15)\n")
        original = self.store.append_output
        failed = set()
        def broken_sink(rid, text):
            if "callback-stream-" in text and rid not in failed:
                failed.add(rid)
                raise RuntimeError("fixture output sink failed")
            return original(rid, text)
        for caller in ("intake", "evaluation"):
            with self.subTest(caller=caller), mock.patch.object(self.store, "append_output", side_effect=broken_sink):
                if caller == "intake":
                    updated = self.understand(self.conversation())
                    self.assertEqual(updated["understood"]["by"], "规则")
                else:
                    learn._run_batch(self.P, self.project, [self.case()], "reader", "", self.conf, "tester", "fixture-output-exception")
                run = self.latest()
                self.assert_finished(run["id"], "failed", "error")
                record = self.receipt(run["id"])
                self.assertTrue(record["attempts"][0]["cleanup"]["complete"])
                self.assertFalse(Path(run["workdir"]).exists())


if __name__ == "__main__":
    unittest.main()
