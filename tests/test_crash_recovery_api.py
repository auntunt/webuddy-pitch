"""Recovery is explicit, ownership-bound, and cannot turn missing proof into success."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh.platform.agents import Runner
from tmh.platform.server import ApiError, api_run, api_recover_run
from tmh.platform.store import Store, now


class CrashRecoveryApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-crash-api-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        project = self.store.add_project("CRAPI", "隔离回执接口", str(self.data))
        self.run = self.store.create_run(project["id"], None, "fixture", "plan", "fixture", "原始完整输入")
        self.rid = self.run["id"]
        self.runner = Runner(self.store, self.data)
        self.P = SimpleNamespace(store=self.store, runner=self.runner, data_dir=self.data)
        self.req = SimpleNamespace(user="恢复操作者", body={}, arg=lambda key: "1" if key == "prompt" else "")
        self.folder = self.data / "runs" / str(self.rid)
        self.addCleanup(lambda: self.runner._release(self.rid))

    def read(self):
        return api_run(self.P, self.req, str(self.rid))

    def write_life(self, life):
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "lifecycle.json").write_text(json.dumps(life))

    def test_get_is_read_only_and_malformed_proof_never_enables_retry(self):
        self.store.update_run(self.rid, status="failed", started=now())
        for life in ({"finished": True}, {"finished": True, "attempts": [], "recovery": "bad"},
                     {"finished": True, "attempts": [], "recovery": ["bad"]},
                     {"finished": True, "attempts": [{"supervised": True, "pid": None}]},
                     {"finished": True, "attempts": [] , "recovery": {"state": "pending"}}):
            with self.subTest(life=life):
                self.write_life(life)
                before = (self.folder / "lifecycle.json").read_bytes()
                row = self.store.run(self.rid)
                with mock.patch.object(self.runner, "recover_run", side_effect=AssertionError("GET must not recover")):
                    result = self.read()
                self.assertFalse(result["can_retry"])
                self.assertEqual(result["lifecycle"], life)
                self.assertEqual(before, (self.folder / "lifecycle.json").read_bytes())
                self.assertEqual(row, self.store.run(self.rid))

    def test_recovery_post_cannot_take_a_live_owner(self):
        self.runner._control(self.rid)
        self.store.update_run(self.rid, status="running", started=now())
        before = self.store.run(self.rid)
        with self.assertRaises(ApiError) as caught:
            api_recover_run(self.P, self.req, str(self.rid))
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.store.run(self.rid), before)

    def test_missing_final_receipt_blocks_then_post_collects_real_receipt(self):
        # The independent SIGKILL suite covers real owner death. Here a real
        # completed process has its final receipt withheld to test API recovery.
        self.runner._control(self.rid)
        self.store.update_run(self.rid, status="running", started=now(), result="原诊断保留")
        result, part = self.runner.run_command(self.rid, [sys.executable, "-c", "print('实际原始输出')"], self.data)
        self.assertEqual(result.returncode, 0)
        raw = (part / "output.bin").read_bytes()
        final = part / "supervisor-result.json"
        receipt = final.read_bytes()
        final.unlink()
        self.runner._release(self.rid)
        # Recover using a new owner object, without manipulating any PID.
        restarted = Runner(self.store, self.data)
        self.P.runner = restarted
        from tmh.platform import crash_recovery
        original = crash_recovery.reconcile
        with mock.patch.object(crash_recovery, "reconcile", side_effect=lambda *a: original(*a, wait_seconds=0)):
            blocked = api_recover_run(self.P, self.req, str(self.rid))
        self.assertEqual(blocked["lifecycle"]["recovery"]["state"], "blocked")
        self.assertFalse(blocked["can_retry"])
        self.assertFalse(blocked["lifecycle"]["finished"])
        self.assertEqual((part / "output.bin").read_bytes(), raw)
        final.write_bytes(receipt)
        recovered = api_recover_run(self.P, self.req, str(self.rid))
        self.assertEqual(recovered["status"], "failed")
        self.assertEqual(recovered["exit_code"], 125)
        self.assertTrue(recovered["lifecycle"]["finished"])
        self.assertTrue(recovered["can_retry"])
        self.assertIn("原诊断保留", recovered["result"])
        self.assertIn("实际原始输出", recovered["output"])
        self.assertEqual(recovered["prompt"], "原始完整输入")
        self.assertEqual((part / "output.bin").read_bytes(), raw)
        after = self.store.run(self.rid)
        again = api_recover_run(self.P, self.req, str(self.rid))
        self.assertEqual(again["lifecycle"], recovered["lifecycle"])
        self.assertEqual(after, self.store.run(self.rid))

    def test_interruption_during_recovery_never_seals_before_database_write(self):
        self.runner._control(self.rid)
        self.store.update_run(self.rid, status="running", started=now())
        self.runner._release(self.rid)
        restarted = Runner(self.store, self.data)
        with mock.patch.object(self.store, "update_run", side_effect=OSError("fixture database write interruption")):
            with self.assertRaises(OSError):
                restarted.recover_run(self.rid)
        self.assertFalse(json.loads((self.folder / "lifecycle.json").read_text())["finished"])
        restarted.recover_run(self.rid)
        self.assertEqual(self.store.run(self.rid)["status"], "failed")
        self.assertTrue(json.loads((self.folder / "lifecycle.json").read_text())["finished"])

    def test_failed_final_seal_releases_owner_and_done_window_is_recoverable(self):
        self.runner._control(self.rid)
        self.store.update_run(self.rid, status="running", started=now())
        process, part = self.runner.run_command(self.rid, [sys.executable, "-c", "print('sealed output')"], self.data)
        raw = (part / "output.bin").read_bytes()
        with mock.patch.object(Path, "replace", side_effect=OSError("fixture final seal interrupted")):
            with self.assertRaises(OSError):
                self.runner.finish_invocation(self.rid, 0, process.output)
        self.assertNotIn(self.rid, self.runner.owners)
        self.assertEqual(self.store.run(self.rid)["status"], "done")
        self.assertFalse(json.loads((self.folder / "lifecycle.json").read_text())["finished"])
        Runner(self.store, self.data).recover()
        self.assertEqual(self.store.run(self.rid)["status"], "failed")
        self.assertTrue(json.loads((self.folder / "lifecycle.json").read_text())["finished"])
        self.assertEqual((part / "output.bin").read_bytes(), raw)

    def test_interrupted_first_backup_keeps_complete_live_source_for_next_recovery(self):
        self.runner._control(self.rid)
        self.store.update_run(self.rid, status="running", started=now())
        self.runner._release(self.rid)
        raw = (self.folder / "lifecycle.json").read_bytes()
        restarted = Runner(self.store, self.data)
        with mock.patch.object(os, "link", side_effect=OSError("fixture backup publication interruption")):
            with self.assertRaises(OSError):
                restarted.recover_run(self.rid)
        backup = self.folder / "restart-recovery" / "original-lifecycle.json"
        self.assertFalse(backup.exists())
        self.assertEqual((self.folder / "lifecycle.json").read_bytes(), raw)
        restarted.recover_run(self.rid)
        self.assertEqual(backup.read_bytes(), raw)
        self.assertTrue(json.loads((self.folder / "lifecycle.json").read_text())["finished"])


if __name__ == "__main__":
    unittest.main()
