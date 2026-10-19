"""Independent operation rows and real supervised commands, never model calls."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tmh.platform.recheck_operations import Operations, read_status, source_guard
from tmh.platform.store import Store, now


@unittest.skipUnless(os.name == "posix", "requires POSIX ownership leases")
class RecheckOperationsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="tmh-operation-")
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name).resolve()
        self.project_root = self.data / "project"
        self.project_root.mkdir()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        project = self.store.add_project("OP", "复检操作夹具", str(self.project_root))
        self.source = self.store.create_run(project["id"], None, "fixture", "fix", "original-author", "原任务内容")
        self.store.update_run(self.source["id"], status="done", started=now(), ended=now(), exit_code=0,
                              result="原始完整结论", output="原始完整输出\n", diff="原始完整改动")
        self.original = self.store.run(self.source["id"])
        self.original_folder = self.data / "runs" / str(self.source["id"])
        self.original_folder.mkdir(parents=True)
        (self.original_folder / "original.bin").write_bytes(b"original\x00\xff")
        self.operations = Operations(self.store, self.data)
        self.addCleanup(self.release_owners)

    def release_owners(self):
        for opid in list(self.operations.runner.owners):
            self.operations.runner._release(opid)
        for opid in list(self.operations._source_guards):
            self.operations._source_guards.pop(opid).__exit__(None, None, None)

    def source_binding(self):
        return {"source_commit": "a" * 40, "base": "b" * 40, "diffhash": "c" * 64,
                "decision": "accepted", "fixture": "synthetic identity; no claim of repository verification"}

    def start(self, budget=5):
        operation = self.operations.start(self.source["id"], "new-reviewer", budget)
        self.operations.bind(operation["id"], self.source_binding())
        return operation

    def command(self, opid, code="import os;os.write(1,b'operation-output\\x00\\xff')", **kwargs):
        return self.operations.runner.run_command(opid, [sys.executable, "-c", code], self.project_root, **kwargs)

    def snapshot(self):
        return {str(p.relative_to(self.data)): p.read_bytes() for p in self.data.rglob("*") if p.is_file()}

    def test_real_command_is_isolated_from_source_run_and_original_bytes(self):
        op = self.start()
        self.assertEqual(op["id"], self.source["id"], "overlapping numeric IDs must still be isolated")
        result, folder = self.command(op["id"])
        final = self.operations.finish(op["id"], result.returncode, "实际复检已完成")
        self.assertEqual(final["status"], "done")
        self.assertFalse(final["running"])
        self.assertTrue(final["can_retry"], final["blocked"])
        self.assertTrue(final["lifecycle"]["attempts"][0]["cleanup"]["complete"])
        self.assertEqual((folder / "output.bin").read_bytes(), b"operation-output\x00\xff")
        self.assertEqual(self.store.run(self.source["id"]), self.original)
        self.assertEqual(self.store.q("SELECT count(*) AS n FROM runs"), [{"n": 1}])
        self.assertEqual((self.original_folder / "original.bin").read_bytes(), b"original\x00\xff")
        second = self.start()
        self.assertNotEqual(second["id"], op["id"])
        self.assertEqual((folder / "output.bin").read_bytes(), b"operation-output\x00\xff")
        self.operations.finish(second["id"], 1, "未运行命令的夹具停止")

    def test_read_status_is_read_only_and_immediately_blocks_previous_result(self):
        self.assertIsNone(read_status(self.data, self.source["id"]))
        op = self.start()
        before = self.snapshot()
        state = read_status(self.data, self.source["id"])
        self.assertEqual(state["id"], op["id"])
        self.assertTrue(state["running"])
        self.assertFalse(state["can_retry"])
        self.assertEqual(before, self.snapshot())
        self.operations.finish(op["id"], 1, "fixture stop")

    def test_two_instances_start_exactly_one_operation_and_keep_sqlite_usable(self):
        other_store = Store(self.data / "platform.db")
        other = Operations(other_store, self.data)
        self.addCleanup(other_store.db.close)
        self.addCleanup(lambda: [other.runner._release(x) for x in list(other.runner.owners)])
        barrier = threading.Barrier(2)
        results = [{}, {}]
        managers = [self.operations, other]
        def start(index):
            barrier.wait(timeout=3)
            try:
                results[index]["value"] = managers[index].start(self.source["id"], "concurrent reviewer", 5)
            except Exception as exc:
                results[index]["error"] = exc
        workers = [threading.Thread(target=start, args=(i,)) for i in range(2)]
        for thread in workers:
            thread.start()
        for thread in workers:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum("value" in r for r in results), 1, results)
        self.assertEqual(sum(isinstance(r.get("error"), ValueError) for r in results), 1, results)
        self.assertEqual(self.store.q("SELECT count(*) AS n FROM verification_operations"), [{"n": 1}])
        self.assertFalse(self.store.db.in_transaction)
        self.assertFalse(other_store.db.in_transaction)
        for manager, outcome in zip(managers, results):
            if "value" in outcome:
                manager.finish(outcome["value"]["id"], 1, "fixture completed without a command")

    def test_done_database_row_without_sealed_lifecycle_blocks_new_operation(self):
        op = self.start()
        self.operations.adapter.update_run(op["id"], status="done", ended=now(), exit_code=0)
        state = self.operations.status(self.source["id"])
        self.assertTrue(state["running"])
        self.assertFalse(state["can_retry"])
        with self.assertRaises(ValueError):
            self.start()
        self.operations.finish(op["id"], 1, "fixture interrupt")

    def test_failed_sealed_command_can_retry_but_missing_receipt_blocks(self):
        op = self.start()
        result, folder = self.command(op["id"], "print('actual check failed');raise SystemExit(7)")
        final = self.operations.finish(op["id"], result.returncode, "实际检查失败")
        self.assertEqual(final["status"], "failed")
        self.assertTrue(final["can_retry"])
        final_receipt = folder / "supervisor-result.json"
        final_receipt.rename(folder / "supervisor-result.original.json")
        state = read_status(self.data, self.source["id"])
        self.assertFalse(state["can_retry"])
        with self.assertRaises(ValueError):
            self.start()
        self.assertIn(b"actual check failed", (folder / "output.bin").read_bytes())

    def test_source_binding_is_full_id_bound_and_cannot_be_replaced(self):
        op = self.start()
        path = self.operations.folder(op["id"]) / "source.json"
        original = path.read_bytes()
        manifest = self.operations.bind(op["id"], self.source_binding())
        self.assertEqual(manifest["operation_id"], op["id"])
        self.assertEqual(manifest["source_run"], self.source["id"])
        self.assertEqual(path.read_bytes(), original)
        with self.assertRaises(ValueError):
            self.operations.bind(op["id"], dict(self.source_binding(), diffhash="d" * 64))
        self.assertEqual(path.read_bytes(), original)
        self.operations.finish(op["id"], 1, "fixture done")

    def test_unadopted_worktree_binding_preserves_explicit_empty_candidate_commit(self):
        op = self.operations.start(self.source["id"], "reviewer", 5)
        source = {"run": self.source["id"], "commit": "", "decision": "", "base": "b" * 40,
                  "diff_sha256": "c" * 64, "diff": "complete uncommitted synthetic diff"}
        self.operations.bind(op["id"], source)
        self.assertEqual(self.operations.get(op["id"])["source"], source)
        self.operations.finish(op["id"], 1, "fixture done")

    def test_source_guard_conflicts_until_finish_and_rechecks_current_discard_decision(self):
        op = self.start()
        with self.assertRaises(ValueError):
            with source_guard(self.data, self.source["id"]):
                self.fail("a decision must not enter while recheck still owns the source")
        self.operations.finish(op["id"], 1, "fixture done")
        with source_guard(self.data, self.source["id"]):
            self.store.update_run(self.source["id"], decision="discarded")
            with self.assertRaises(ValueError):
                self.start()
        with self.assertRaisesRegex(ValueError, "已经放弃"):
            self.start()

    def test_source_guard_is_cross_process_and_released_when_its_owner_is_killed(self):
        marker = self.data / "source-lock-ready"
        script = """import pathlib,sys,time
from tmh.platform.recheck_operations import source_guard
with source_guard(sys.argv[1],int(sys.argv[2])):
 pathlib.Path(sys.argv[3]).touch()
 time.sleep(20)
"""
        child = subprocess.Popen([sys.executable, "-c", script, str(self.data), str(self.source["id"]), str(marker)],
                                 cwd=str(Path(__file__).resolve().parents[1]))
        try:
            deadline = time.monotonic() + 3
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(marker.exists())
            with self.assertRaisesRegex(ValueError, "正在复检或处理采纳"):
                self.start()
            self.assertEqual(self.store.q("SELECT count(*) AS n FROM verification_operations"), [{"n": 0}])
            child.kill()
            child.wait(timeout=3)
            op = self.start()
            self.operations.finish(op["id"], 1, "fixture done")
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)

    def test_total_operation_budget_covers_multiple_commands(self):
        # Leave room for real Python/supervisor startup. The second command
        # must still receive only the budget left after the first one ran.
        budget = 3.0
        op = self.start(budget=budget)
        first, folder = self.command(op["id"], "import time;time.sleep(.25);print('first complete')")
        self.assertEqual(first.returncode, 0)
        self.assertGreaterEqual(first.elapsed, .25)
        second, second_folder = self.command(op["id"], "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('second',flush=True);time.sleep(20)")
        self.assertEqual(second.reason, "timeout")
        self.assertEqual(second.returncode, 124)
        final = self.operations.finish(op["id"], 0, "不能用最后调用参数覆盖总时限")
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["exit_code"], 124)
        self.assertEqual(final["lifecycle"]["stopped_reason"], "timeout")
        life = final["lifecycle"]
        self.assertTrue(life["finished"])
        self.assertFalse(final["running"])
        self.assertEqual(life["timeout_seconds"], budget)
        self.assertEqual(len(life["attempts"]), 2)
        self.assertLessEqual(life["attempts"][1]["timeout_seconds"] + first.elapsed, budget + .02)
        self.assertLess(life["elapsed_seconds"], budget + 1.3)
        self.assertTrue(all(a["cleanup"]["complete"] for a in life["attempts"]))
        self.assertIn(b"first complete", (folder / "output.bin").read_bytes())
        self.assertEqual(first.output_bytes, b"first complete\n")
        self.assertEqual((folder / "output.bin").read_bytes(), first.output_bytes)
        self.assertEqual(second.output_bytes, b"second\n")
        self.assertEqual((second_folder / "output.bin").read_bytes(), second.output_bytes)

    def test_recovery_uses_operation_table_and_preserves_source_run(self):
        op = self.start()
        result, _ = self.command(op["id"])
        self.assertEqual(result.returncode, 0)
        # Simulate service loss after the real command has completed, before
        # operation publication/finish. There is no process to signal here.
        self.operations.runner._release(op["id"])
        self.operations._source_guards.pop(op["id"]).__exit__(None, None, None)
        rebuilt = Operations(self.store, self.data)
        rebuilt.recover()
        recovered = rebuilt.status(self.source["id"])
        self.assertEqual(recovered["status"], "failed")
        self.assertTrue(recovered["can_retry"], recovered["blocked"])
        self.assertEqual(recovered["recovery"]["state"], "complete")
        self.assertEqual(self.store.run(self.source["id"]), self.original)
        self.assertEqual(self.store.q("SELECT count(*) AS n FROM runs"), [{"n": 1}])

    def test_legacy_read_does_not_initialize_schema_and_corrupt_database_fails_closed(self):
        other = self.data / "legacy"
        other.mkdir()
        old_store = Store(other / "platform.db")
        old_store.db.close()
        before = {p.name: p.read_bytes() for p in other.iterdir()}
        self.assertIsNone(read_status(other, self.source["id"]))
        self.assertEqual(before, {p.name: p.read_bytes() for p in other.iterdir()})
        (other / "platform.db").write_bytes(b"corrupt-synthetic-database\x00\xff")
        with self.assertRaises(ValueError):
            read_status(other, self.source["id"])

    def test_success_without_source_binding_is_failed_not_accepted(self):
        op = self.operations.start(self.source["id"], "reviewer", 5)
        final = self.operations.finish(op["id"], 0, "not actually bound")
        self.assertEqual(final["status"], "failed")
        self.assertNotEqual(final["exit_code"], 0)
        self.assertEqual(self.store.run(self.source["id"]), self.original)

    def test_corrupt_source_binding_is_preserved_and_cannot_be_reported_as_success(self):
        op = self.start()
        path = self.operations.folder(op["id"]) / "source.json"
        original = path.read_bytes()
        (path.parent / "source.before-corruption.json").write_bytes(original)
        damaged = b'{"schema":1,"source":\xff partial synthetic receipt'
        path.write_bytes(damaged)
        final = self.operations.finish(op["id"], 0, "must not claim success")
        self.assertEqual(final["status"], "failed")
        self.assertFalse(final["can_retry"])
        self.assertEqual(path.read_bytes(), damaged)
        self.assertEqual((path.parent / "source.before-corruption.json").read_bytes(), original)
        with source_guard(self.data, self.source["id"]):
            pass  # The source lock is released; the durable gate remains closed.
