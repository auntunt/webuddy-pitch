"""Regressions from independent lifecycle review, using real worker threads."""
import os
import json
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import test_run_lifecycle as helpers
from tests import test_run_recovery as recovery_helpers
from tmh.platform import agents
from tmh.platform.store import Store


@unittest.skipUnless(os.name == "posix", "requires POSIX owned process groups")
class RuntimeReviewTest(unittest.TestCase):
    def setUp(self):
        self.f = helpers.RunLifecycleTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def go(self, rid, mode="ask"):
        f = self.f
        f.runner._go(rid, f.project, f.ticket, "fixture", mode, "fixture prompt", f.conf("success", timeout=5))

    def join(self, thread, result):
        thread.join(3)
        self.assertFalse(thread.is_alive(), "controlled worker did not finish")
        if "error" in result:
            raise result["error"]

    def test_accepted_cancel_before_finalization_cannot_become_done(self):
        f = self.f
        rid = f.new_run()
        ready, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = f.runner.invoke
        def pause_after_invoke(*args, **kwargs):
            result = original(*args, **kwargs)
            ready.set()
            if not release.wait(3):
                raise RuntimeError("test finalization barrier timed out")
            return result
        with mock.patch.object(f.runner, "invoke", side_effect=pause_after_invoke):
            worker, result = f.async_call(lambda: self.go(rid))
            self.assertTrue(ready.wait(2))
            cancelled = f.runner.cancel(rid, "test-canceller")
            self.assertEqual(cancelled["status"], "cancelled")
            release.set()
            self.join(worker, result)
        self.assertEqual(f.store.run(rid)["status"], "cancelled")
        self.assertNotEqual(f.store.run(rid)["exit_code"], 0)
        self.assertEqual(f.runner.stop_reason(rid), "cancelled")

    def test_final_commit_and_cancel_are_serialized_across_threads(self):
        f = self.f
        rid = f.new_run()
        committing, release, cancel_entered, cancel_done = [threading.Event() for _ in range(4)]
        self.addCleanup(release.set)
        original = f.store.update_run
        def pause_commit(run_id, **fields):
            if run_id == rid and fields.get("status") == "done":
                committing.set()
                if not release.wait(3):
                    raise RuntimeError("test final commit barrier timed out")
            return original(run_id, **fields)
        def cancel():
            cancel_entered.set()
            try:
                return f.runner.cancel(rid, "concurrent-canceller")
            finally:
                cancel_done.set()
        with mock.patch.object(f.store, "update_run", side_effect=pause_commit):
            worker, result = f.async_call(lambda: self.go(rid))
            self.assertTrue(committing.wait(2))
            canceller, cancelled = f.async_call(cancel)
            self.assertTrue(cancel_entered.wait(1))
            self.assertFalse(cancel_done.wait(.1), "cancel was accepted inside an in-progress final commit")
            release.set()
            self.join(worker, result)
            canceller.join(2)
            self.assertFalse(canceller.is_alive())
        self.assertIsInstance(cancelled.get("error"), ValueError)
        self.assertEqual(f.store.run(rid)["status"], "done")
        self.assertEqual(f.runner.stop_reason(rid), "")

    def test_cancel_during_worktree_preparation_cannot_become_running(self):
        f = self.f
        rid = f.new_run("fix")
        prepared, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = agents.make_worktree
        def pause_preparation(*args, **kwargs):
            result = original(*args, **kwargs)
            prepared.set()
            if not release.wait(3):
                raise RuntimeError("test preparation barrier timed out")
            return result
        with mock.patch.object(agents, "make_worktree", side_effect=pause_preparation):
            worker, result = f.async_call(lambda: self.go(rid, "fix"))
            self.assertTrue(prepared.wait(2))
            cancelled = f.runner.cancel(rid, "preparation-canceller")
            self.assertEqual(cancelled["status"], "cancelled")
            release.set()
            self.join(worker, result)
        run = f.store.run(rid)
        self.assertEqual(run["status"], "cancelled")
        self.assertTrue(Path(run["workdir"]).is_dir())
        self.assertFalse(f.registry.exists(), "cancelled preparation must not launch a model")
        self.assertTrue(f.lifecycle(rid)["finished"])

    def test_failed_process_receipt_write_does_not_leave_a_phantom_process(self):
        f = self.f
        rid = f.new_run()
        original = Path.write_text
        def fail_receipt(path, *args, **kwargs):
            if path.name == "process.json":
                raise OSError("synthetic process receipt storage failure")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "write_text", fail_receipt):
            self.go(rid)
        self.assertEqual(f.store.run(rid)["status"], "failed")
        self.assertNotIn(rid, f.runner.procs)
        life = f.lifecycle(rid)
        self.assertTrue(life["finished"])
        self.assertTrue(life["attempts"][0]["cleanup"]["complete"])
        self.assertNotIn("原运行仍在回收，请稍后刷新", f.runner.retry_state(rid)["retry_blocked"])
        output = f.data / life["attempts"][0]["evidence"] / "output.bin"
        self.assertIn(b"completed-within-budget", output.read_bytes())

    def storage_failure(self, failed_name, preserved_name):
        f = self.f
        rid = f.new_run()
        original = Path.write_bytes
        def fail_output(path, *args, **kwargs):
            if path.name == failed_name:
                raise OSError("synthetic " + failed_name + " storage failure")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "write_bytes", fail_output):
            self.go(rid)
        self.assertEqual(f.store.run(rid)["status"], "failed")
        self.assertNotIn(rid, f.runner.procs)
        life = f.lifecycle(rid)
        self.assertTrue(life["finished"])
        attempt = life["attempts"][0]
        self.assertTrue(attempt["cleanup"]["complete"])
        self.assertEqual(attempt["returncode"], 0)
        self.assertEqual(attempt["reason"], "error")
        self.assertIn(failed_name, attempt["evidence_error"])
        output = f.data / attempt["evidence"] / preserved_name
        self.assertIn(b"completed-within-budget", output.read_bytes())

    def test_failed_binary_output_write_preserves_text_and_cleanup(self):
        self.storage_failure("output.bin", "output.txt")

    def test_failed_text_output_write_preserves_original_bytes_and_cleanup(self):
        self.storage_failure("output.txt", "output.bin")


@unittest.skipUnless(os.name == "posix", "requires POSIX owned process groups")
class RuntimeRecoveryReviewTest(unittest.TestCase):
    def setUp(self):
        self.f = recovery_helpers.RunRecoveryTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def failed_run(self):
        f = self.f
        f.configure("initial-failure")
        old = f.wait(f.start()["id"])
        # _go sets its in-memory finished flag while holding this lock, then
        # writes the final receipt. Join that operation before asserting the
        # persisted recovery gate; a transient pre-flush gate is legitimate.
        with f.runner.lock:
            self.assertEqual(old["status"], "failed")
            self.assertTrue(f.runner.retry_state(old["id"])["can_retry"])
        return old

    def assert_durable_successor(self, old, new):
        f = self.f
        finished = f.wait(new["id"])
        self.assertEqual(finished["status"], "done", finished["result"])
        self.assertEqual(finished["retry_of"], old["id"])
        self.assertIn("恢复补充回执保存失败", finished["output"])
        # Reopen the real database and construct a runner with no in-memory
        # controls: the UNIQUE parent link must survive a server restart.
        reopened = Store(f.data / "platform.db")
        try:
            rebuilt = agents.Runner(reopened, f.data)
            state = rebuilt.retry_state(old["id"])
            self.assertFalse(state["can_retry"])
            self.assertEqual(state["retry_run"], new["id"])
            with self.assertRaises(ValueError):
                rebuilt.retry(old["id"], "restart-test")
            children = reopened.q("SELECT id FROM runs WHERE retry_of=?", (old["id"],))
            self.assertEqual(children, [{"id": new["id"]}])
        finally:
            reopened.db.close()

    def test_failed_lifecycle_retry_link_still_returns_one_durable_successor(self):
        f = self.f
        old = self.failed_run()
        before = f.receipt(old["id"]).read_bytes()
        f.configure("recovered")
        save = f.runner._save_lifecycle
        def fail_link(rid):
            if rid == old["id"] and f.runner.controls[rid].get("retry_run"):
                raise OSError("synthetic retry lifecycle persistence failure")
            return save(rid)
        with mock.patch.object(f.runner, "_save_lifecycle", side_effect=fail_link):
            new = f.runner.retry(old["id"], "recovery-review")
        self.assertEqual(f.receipt(old["id"]).read_bytes(), before)
        self.assertNotIn("retry_run", json.loads(before))
        self.assert_durable_successor(old, new)

    def test_failed_supplemental_retry_receipt_keeps_database_idempotency(self):
        f = self.f
        old = self.failed_run()
        f.configure("recovered")
        write = Path.write_text
        def fail_receipt(path, *args, **kwargs):
            if path.name == "retry.json":
                raise OSError("synthetic retry.json persistence failure")
            return write(path, *args, **kwargs)
        with mock.patch.object(Path, "write_text", fail_receipt):
            new = f.runner.retry(old["id"], "recovery-review")
        self.assert_durable_successor(old, new)

    def test_independent_runners_commit_and_dispatch_only_one_retry(self):
        f = self.f
        old = self.failed_run()
        f.configure("recovered")
        other_store = Store(f.data / "platform.db")
        other_runner = agents.Runner(other_store, f.data)
        owners = [f.runner, other_runner]
        barrier = threading.Barrier(2)
        original = Store.create_run
        outcomes = [{}, {}]
        threads = []
        def create_together(store, *args, **kwargs):
            if kwargs.get("retry_of") == old["id"]:
                barrier.wait(timeout=3)
            return original(store, *args, **kwargs)
        def attempt(index):
            try:
                outcomes[index]["run"] = owners[index].retry(old["id"], "concurrent-recovery")
            except Exception as exc:
                outcomes[index]["error"] = exc
        try:
            with mock.patch.object(Store, "create_run", create_together):
                for index in range(2):
                    thread = threading.Thread(target=attempt, args=(index,), daemon=True)
                    threads.append(thread)
                    thread.start()
                for thread in threads:
                    thread.join(4)
                    self.assertFalse(thread.is_alive(), "concurrent retry request did not finish")
            winners = [i for i, value in enumerate(outcomes) if "run" in value]
            losers = [i for i, value in enumerate(outcomes) if "error" in value]
            self.assertEqual(len(winners), 1, outcomes)
            self.assertEqual(len(losers), 1, outcomes)
            # A uniqueness conflict must release its SQLite transaction and be
            # a user-visible conflict, not block the winner's worker writes.
            loser = owners[losers[0]]
            self.assertFalse(loser.store.db.in_transaction, "losing UNIQUE insert left a database write lock")
            self.assertIsInstance(outcomes[losers[0]]["error"], ValueError)
            owner = owners[winners[0]]
            new = outcomes[winners[0]]["run"]
            end = time.monotonic() + 4
            while time.monotonic() < end and not owner.controls.get(new["id"], {}).get("finished"):
                time.sleep(.01)
            self.assertTrue(owner.controls.get(new["id"], {}).get("finished"))
            final = owner.store.run(new["id"])
            self.assertEqual(final["status"], "done", final["result"])
            self.assertEqual(f.store.q("SELECT id FROM runs WHERE retry_of=?", (old["id"],)), [{"id": new["id"]}])
            self.assertTrue((f.data / ("pid-" + str(new["id"]))).is_file())
            for runner in owners:
                self.assertFalse(runner.retry_state(old["id"])["can_retry"])
        finally:
            # Failure diagnostics must not leave this test's second connection
            # holding a write lock or close it under its own running worker.
            other_store.db.rollback()
            f.store.db.rollback()
            for runner in owners:
                for control in runner.controls.values():
                    if not control.get("finished"):
                        control["event"].set()
            end = time.monotonic() + 3
            while time.monotonic() < end and any(not c.get("finished") for r in owners for c in r.controls.values()):
                time.sleep(.01)
            for thread in threads:
                thread.join(1)
            other_store.db.close()
