"""Intake's real deadline, without the direct-ordering fixture's clock/watchdog."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh.platform import agents, intake, supervised_process
from tmh.platform.agents import Runner, git
from tmh.platform.store import Store


@unittest.skipUnless(os.name == "posix", "requires the real POSIX supervisor")
class IntakeWallClockTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tmh-intake-wall-clock-")
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        self.root = self.data / "project"
        self.root.mkdir()
        (self.root / "app.py").write_text("VALUE = 0\n")
        git(self.root, "init", "-q")
        git(self.root, "add", ".")
        git(self.root, "-c", "user.name=test", "-c", "user.email=test@localhost", "commit", "-qm", "baseline")
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("CLOCK", "真实超时", str(self.root))
        self.runner = Runner(self.store, self.data)
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, runner=self.runner,
                                 root=lambda p: Path(p["root"]), project=self.store.project)
        self.marker = self.data / "reader-started"
        script = self.data / "reader.py"
        answer = {"title": "不应采用的迟到答案", "items": [{"title": "保存记录失败", "quote": "保存记录后提示错误",
                  "kind": "缺陷", "restated": "保存记录后系统提示错误", "flow": "", "questions": [],
                  "ac": [{"id": "A1", "text": "保存后应显示原事项", "check": "保存并读回事项"}]}]}
        script.write_text("from pathlib import Path\nPath(%r).write_text('started')\nprint(%r)\n" % (
            str(self.marker), "```tmh-intake\n" + json.dumps(answer, ensure_ascii=False) + "\n```"))
        (self.data / "agents.json").write_text(json.dumps({
            "reader": {"timeout": .5, "cmd": [sys.executable, str(script)]}}))
        (self.data / "autoflow.json").write_text(json.dumps({"on": False, "understand": "rules"}))

    def test_slow_real_supervisor_startup_exhausts_intake_budget_before_reader_spawn(self):
        self.assertIs(agents.time, time)
        self.assertIs(supervised_process.time, time)
        state = intake.start(self.P, self.project, "保存记录后提示错误，昨天开始所有员工都遇到，希望保存后看到原事项。",
                             "tester", agent=False)
        state["state"] = "understanding"
        state["understanding_job"] = {"id": "wall-clock-job", "t0": time.time(), "agent": "reader"}
        intake._save(self.data, state)
        spawn = supervised_process.subprocess.Popen

        def slow_spawn(*args, **kwargs):
            # Exceed the real budget deterministically; no fast-start assumption.
            time.sleep(.6)
            return spawn(*args, **kwargs)

        settings = dict(intake.settings(self.data), timeout=.5)
        with mock.patch.object(intake, "settings", return_value=settings), \
                mock.patch.object(supervised_process.subprocess, "Popen", side_effect=slow_spawn) as spawned, \
                mock.patch.object(supervised_process, "run_supervised", wraps=supervised_process.run_supervised) as supervised:
            intake._understand(self.P, self.project, state["id"], "wall-clock-job", "reader")
        spawned.assert_called_once()
        supervised.assert_called_once()
        self.assertGreater(supervised.call_args.kwargs["timeout"], 0)
        self.assertLessEqual(supervised.call_args.kwargs["timeout"], .5)
        updated = intake.load(self.data, state["id"], self.P)
        self.assertEqual(updated["understood"]["by"], "规则")
        run = self.store.run(updated["understood"]["run"])
        self.assertEqual((run["status"], run["exit_code"]), ("failed", 124), run["result"])
        self.assertTrue(run["ended"])
        record = json.loads((self.data / "runs" / str(run["id"]) / "lifecycle.json").read_text())
        self.assertTrue(record["finished"])
        self.assertEqual(record["timeout_seconds"], .5)
        self.assertEqual(record["stopped_reason"], "timeout")
        self.assertGreaterEqual(record["elapsed_seconds"], .5)
        self.assertEqual(len(record["attempts"]), 1)
        attempt = record["attempts"][0]
        self.assertEqual((attempt["reason"], attempt["returncode"]), ("timeout", 124))
        self.assertTrue(attempt["cleanup"]["complete"])
        self.assertEqual(attempt["cleanup"]["trigger"], "timeout_before_spawn")
        receipt = supervised_process.read_receipt(self.data / attempt["evidence"])
        self.assertIsNone(receipt["pid"])
        self.assertFalse(self.marker.exists(), "deadline must stop the reader, not merely relabel its result")
        self.assertFalse(Path(run["workdir"]).exists())


if __name__ == "__main__":
    unittest.main()
