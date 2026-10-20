"""An expired preparation budget must leave a terminal, recoverable run.

These tests use an isolated real Store and lifecycle files. A delayed first
receipt reproduces a slow disk before execution; no model or subprocess runs.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tmh.platform.agents import Runner
from tmh.platform.store import Store


class RunEarlyStopTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="webuddy-early-stop-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("EARLY", "执行前停止", str(self.data))
        self.ticket = self.store.create_ticket(self.project["id"], "准备后继续", "tester", auto=False)
        self.runner = Runner(self.store, self.data)

    def new_run(self):
        return self.store.create_run(self.project["id"], self.ticket["id"], "fixture", "analyze",
                                     "tester", "synthetic preparation deadline reproduction")["id"]

    def receipt(self, rid):
        return json.loads((self.data / "runs" / str(rid) / "lifecycle.json").read_text())

    def go(self, rid, *, expire=False):
        original = self.runner._save_lifecycle
        first, sealed = True, []

        def save(run_id):
            nonlocal first
            if first:
                first = False
                if expire:
                    time.sleep(.06)
            original(run_id)
            if self.runner.controls[run_id]["finished"]:
                sealed.append(self.receipt(run_id))

        conf = {"fixture": {"run_timeout": .03 if expire else 3}}
        with mock.patch.object(self.runner, "_save_lifecycle", side_effect=save), \
                mock.patch.object(self.runner, "_execute_run") as execute:
            self.runner._go(rid, self.project, self.ticket, "fixture", "analyze", "fixture prompt", conf)
        execute.assert_not_called()
        run = self.store.run(rid)
        self.assertIn(run["status"], ("failed", "cancelled"), "a stopped worker cannot remain queued/running")
        self.assertIsNotNone(run["exit_code"])
        self.assertEqual(len(sealed), 1, "the lifecycle must be sealed exactly once")
        self.assertEqual(self.receipt(rid), sealed[0])
        self.assertEqual(sealed[0]["attempts"], [])
        self.assertNotIn(rid, self.runner.after)
        return run, sealed[0]

    def test_budget_exhausted_before_execution_becomes_failed_and_retryable(self):
        rid = self.new_run()
        calls = []
        self.runner.after[rid] = lambda run: calls.append(run)
        run, life = self.go(rid, expire=True)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["exit_code"], 124)
        self.assertTrue(run["ended"])
        self.assertIn("总时限", run["result"])
        self.assertEqual(life["stopped_reason"], "timeout")
        self.assertGreaterEqual(life["elapsed_seconds"], .06)
        self.assertTrue(life["finished"])
        self.assertEqual(calls, [], "a preparation timeout is not a successful run")
        self.assertTrue(self.runner.retry_state(rid)["can_retry"])
        events = [e for e in self.store.events(self.ticket["id"]) if e["kind"].startswith("run-")]
        self.assertEqual([e["kind"] for e in events], ["run-failed"])

    def test_cancelled_before_execution_stays_cancelled_without_success_callback(self):
        rid = self.new_run()
        calls = []
        self.runner.after[rid] = lambda run: calls.append(run)
        self.runner.cancel(rid, "tester")
        run, life = self.go(rid)
        self.assertEqual(run["status"], "cancelled")
        self.assertEqual(run["exit_code"], 125)
        self.assertTrue(run["ended"])
        self.assertEqual(life["stopped_reason"], "cancelled")
        self.assertEqual(calls, [])
        self.assertTrue(self.runner.retry_state(rid)["can_retry"])
        events = [e for e in self.store.events(self.ticket["id"]) if e["kind"].startswith("run-")]
        self.assertEqual([e["kind"] for e in events], ["run-cancelled"])

    def test_always_callback_gets_terminal_receipt_once_and_does_not_extend_elapsed(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                rid = self.new_run()
                calls = []

                def callback(run):
                    calls.append((run, self.receipt(rid)))
                    time.sleep(.04)

                callback.always = True
                self.runner.after[rid] = callback
                if cancelled:
                    self.runner.cancel(rid, "tester")
                run, life = self.go(rid, expire=not cancelled)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][0]["status"], "cancelled" if cancelled else "failed")
                self.assertEqual(calls[0][0]["exit_code"], 125 if cancelled else 124)
                self.assertEqual(life, calls[0][1], "callback time must not move the sealed elapsed/ended fields")

    def test_failure_callback_error_cannot_replace_the_original_stop_or_seal_again(self):
        rid = self.new_run()
        calls = []

        def callback(run):
            calls.append(run)
            raise RuntimeError("synthetic follow-up failure")

        callback.always = True
        self.runner.after[rid] = callback
        run, life = self.go(rid, expire=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["exit_code"], 124)
        self.assertEqual(life["stopped_reason"], "timeout")
        self.assertIn("synthetic follow-up failure", run["output"])
        events = [e for e in self.store.events(self.ticket["id"]) if e["kind"].startswith("run-")]
        self.assertEqual([e["kind"] for e in events], ["run-failed"])


if __name__ == "__main__":
    unittest.main()
