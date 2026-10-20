"""Knowledge ownership/publication regressions with real supervised snapshots.

All repositories, SQLite stores, and evidence files are disposable fixtures.
The two ordering tests place precise gates around the production launch/lease
boundaries; they retain the real worker, supervisor, kernel lease, and receipts.
Damaged-receipt cases modify only completed synthetic evidence, never create or
signal an unowned process. The 20 s fixture watchdog is not a product timeout.
"""
import io
import errno
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tmh import project_knowledge as worker
from tmh.platform import project_library as library
from tmh.platform import supervised_process
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


@unittest.skipUnless(os.name == "posix" and shutil.which("git"),
                     "real library lifecycle requires POSIX supervision and local Git")
class LibraryLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-library-lifecycle-")
        self.root = Path(self.temp.name).resolve()
        self.store = Store(self.root / "platform" / "platform.db")
        library.schema(self.store)
        self.revisions = []
        self.owner_threads = []
        repo = self.root / "repo"
        repo.mkdir()
        template = self.root / "empty-template"
        template.mkdir()
        worker.git(repo, "init", "--template=" + str(template))
        (repo / "approval.py").write_text("def Approval():\n    return 'fixed approval rule'\n", encoding="utf-8")
        worker.git(repo, "add", "approval.py")
        worker.git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@localhost",
                   "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + str(template),
                   "commit", "-m", "Synthetic fixed baseline")
        self.project = self.store.add_project("LIFE", "Lifecycle fixture", str(repo))

    def tearDown(self):
        try:
            for rid in self.revisions:
                row = library._row(self.store, rid)
                if row["status"] in ("queued", "building"):
                    library.cancel(self.store, self.project, rid)
                    self.wait_terminal(rid)
            for thread in self.owner_threads:
                thread.join(20)
                self.assertFalse(thread.is_alive(), "fixture owner must finish before closing its store")
        finally:
            self.store.db.close()
            self.temp.cleanup()

    def start(self):
        revision = library.start(self.store, self.project, author="synthetic operator")
        self.revisions.append(revision["id"])
        return revision["id"]

    def folder(self, rid):
        return library._folder(self.store, rid)

    def attempt(self, rid):
        row = library._row(self.store, rid)
        return self.folder(rid) / "attempts" / row["attempt"]

    def wait_terminal(self, rid, expected=None):
        deadline = time.monotonic() + 20
        row = None
        while time.monotonic() < deadline:
            row = library._row(self.store, rid)
            if row["status"] not in ("queued", "building"):
                try:
                    # Terminal SQL is written before ownership is released.
                    # Wait for the real owner to finish before reading evidence.
                    with library._lease(self.folder(rid)):
                        break
                except ApiError as exc:
                    if exc.code != 409:
                        raise
            time.sleep(.01)
        else:
            self.fail("synthetic knowledge worker exceeded 20 s: %r" % row)
        if expected is not None:
            self.assertEqual(row["status"], expected, row["error"])
        attempt = self.attempt(rid)
        owner = json.loads((attempt / "owner.json").read_text())
        receipt = supervised_process.read_receipt(attempt, owner)
        self.assertIsNotNone(receipt, "terminal status alone is not cleanup evidence")
        self.assertTrue(receipt["cleanup"]["complete"], receipt)
        self.assertFalse(receipt["cleanup"]["remaining_group"], receipt)
        self.assertTrue(receipt["cleanup"]["reaped"], receipt)
        self.assertTrue(receipt["cleanup"]["output_complete"], receipt)
        return row, receipt

    def build(self):
        rid = self.start()
        self.wait_terminal(rid, "ready")
        return rid

    def assert_resume_refused(self, rid):
        before = library._row(self.store, rid)
        with patch.object(library, "_launch") as launch:
            with self.assertRaises((ApiError, ValueError)):
                library.resume(self.store, self.project, rid)
            launch.assert_not_called()
        after = library._row(self.store, rid)
        self.assertEqual(after["attempt"], before["attempt"])
        self.assertEqual(after["status"], before["status"])
        # Refusal must release the kernel handle as well as prevent launch.
        with library._lease(self.folder(rid)):
            pass

    def test_cancel_accepted_while_queued_is_not_erased_by_first_launch(self):
        launch = library._launch
        observed = []

        def cancel_before_launch(store, rid, lease, **kwargs):
            self.assertEqual(library._row(store, rid)["status"], "queued")
            library.cancel(store, self.project, rid)
            observed.append(library._row(store, rid)["cancel_requested"])
            return launch(store, rid, lease, **kwargs)

        with patch.object(library, "_launch", side_effect=cancel_before_launch):
            rid = self.start()
        row, receipt = self.wait_terminal(rid, "cancelled")
        self.assertEqual(observed, [1], "cancellation was accepted before launch")
        self.assertEqual(row["cancel_requested"], 1)
        self.assertEqual(receipt["reason"], "cancelled")
        self.assertIsNone(receipt["pid"], "already cancelled work must not start the parser")
        self.assertTrue(receipt["cleanup"]["no_spawn"])
        self.assertFalse((self.folder(rid) / "source").exists())
        self.assertFalse((self.folder(rid) / "result.json").exists())

    def test_first_lease_io_error_preserves_error_and_closes_descriptor_without_launch(self):
        opened = []
        failure = OSError(errno.EIO, 'synthetic lock I/O failure')

        def unavailable(stream):
            opened.append(stream)
            raise failure

        with patch.object(library.filelock, 'try_lock', side_effect=unavailable), \
                patch.object(library, '_launch') as launch:
            with self.assertRaises(OSError) as caught:
                library.start(self.store, self.project, author='synthetic operator')
        self.assertIs(caught.exception, failure)
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].closed, 'failed first lease acquisition must not leak its descriptor')
        launch.assert_not_called()
        self.assertEqual(self.store.q('SELECT * FROM knowledge_revisions'), [])

    def test_resume_rechecks_ready_after_waiting_between_row_read_and_lease(self):
        child_finished, allow_publish = threading.Event(), threading.Event()
        real_supervised = supervised_process.run_supervised
        owner = {}

        def before_publication(*args, **kwargs):
            result = real_supervised(*args, **kwargs)
            owner["thread"] = threading.current_thread()
            self.owner_threads.append(owner["thread"])
            child_finished.set()
            if not allow_publish.wait(20):
                raise TimeoutError("test publication gate was not released")
            return result

        try:
            with patch.object(supervised_process, "run_supervised", side_effect=before_publication):
                rid = self.start()
                self.assertTrue(child_finished.wait(20), "real supervised parser did not reach publication")
                self.assertEqual(library._row(self.store, rid)["status"], "building")
                original_lock = library.filelock.try_lock
                observed = []

                def publish_then_acquire(stream, *args, **kwargs):
                    # resume has already read `building`; finish the real owner
                    # before its first flock attempt, without changing clocks.
                    allow_publish.set()
                    owner["thread"].join(20)
                    self.assertFalse(owner["thread"].is_alive())
                    observed.append(library._row(self.store, rid)["status"])
                    return original_lock(stream, *args, **kwargs)

                with patch.object(library.filelock, "try_lock", side_effect=publish_then_acquire), patch.object(library, "_launch") as launch:
                    with self.assertRaises(ApiError) as refused:
                        library.resume(self.store, self.project, rid)
                    self.assertEqual(refused.exception.code, 409)
                    launch.assert_not_called()
                self.assertEqual(observed, ["ready"])
        finally:
            allow_publish.set()
            if "thread" in owner:
                owner["thread"].join(20)
        self.wait_terminal(rid, "ready")

    def test_worker_refuses_a_recorded_analyzer_that_is_not_actually_running(self):
        with patch.object(library, "analyzer_version", return_value="0" * 64):
            rid = self.start()
        row, receipt = self.wait_terminal(rid, "failed")
        self.assertIn("分析器与固定输入不一致", row["error"])
        self.assertNotEqual(receipt["returncode"], 0)
        self.assertFalse((self.folder(rid) / "source").exists())
        self.assertFalse((self.folder(rid) / "result.json").exists())

    def test_worker_detects_analyzer_change_after_real_analysis_before_publication(self):
        folder = self.root / "changing-analyzer"
        folder.mkdir()
        actual = worker.analyzer_version()
        worker.atomic(folder / "request.json", {
            "root": self.project["root"], "commit": worker.git(self.project["root"], "rev-parse", "HEAD"),
            "analyzer": actual,
        })
        # Real export, parsing and indexing run; only the third version probe
        # reports an upgrade at the final publication boundary.
        with patch.object(worker, "analyzer_version", side_effect=[actual, actual, "changed-after-analysis"]), patch("sys.stdout", io.StringIO()):
            with self.assertRaisesRegex(ValueError, "分析器发生变化"):
                worker.build(folder)
        self.assertTrue((folder / "index.db").is_file())
        self.assertTrue(json.loads((folder / "checkpoint.json").read_text())["analyzed"])
        self.assertFalse((folder / "result.json").exists())

    def test_missing_final_supervisor_receipt_never_authorizes_resume(self):
        rid = self.build()
        attempt = self.attempt(rid)
        self.assertTrue((attempt / "supervisor.json").is_file())
        (attempt / "supervisor-result.json").unlink()
        self.store.x("UPDATE knowledge_revisions SET status='failed' WHERE id=?", (rid,))
        self.assert_resume_refused(rid)

    def test_incomplete_supervisor_cleanup_never_authorizes_resume(self):
        rid = self.build()
        attempt = self.attempt(rid)
        path = attempt / "supervisor-result.json"
        receipt = json.loads(path.read_text())
        receipt.update(returncode=125, reason="error")
        receipt["cleanup"].update(complete=False, remaining_group=True, reaped=False)
        worker.atomic(path, receipt)
        owner = json.loads((attempt / "owner.json").read_text())
        evidence = supervised_process.read_receipt(attempt, owner)
        self.assertFalse(evidence["cleanup"]["complete"], "exercise valid incomplete evidence, not malformed JSON")
        self.store.x("UPDATE knowledge_revisions SET status='failed' WHERE id=?", (rid,))
        self.assert_resume_refused(rid)

    def test_published_revision_cannot_be_resumed_or_have_its_evidence_rewritten(self):
        rid = self.build()
        folder = self.folder(rid)
        files = [folder / "result.json", folder / "index.db", folder / "request.json",
                 self.attempt(rid) / "supervisor-result.json"]
        before = {path: path.read_bytes() for path in files}
        self.assert_resume_refused(rid)
        self.assertEqual({path: path.read_bytes() for path in files}, before)
        self.assertEqual(library._row(self.store, rid)["status"], "ready")

    def test_tampered_index_is_unavailable_and_cannot_return_forged_evidence(self):
        rid = self.build()
        before = library.search(self.store, self.project, "Approval", limit=100)
        self.assertTrue(before["items"])
        self.assertFalse(before["partial"])
        path = self.folder(rid) / "index.db"
        db = sqlite3.connect(path)
        try:
            db.execute("UPDATE documents SET body='forged secret evidence' WHERE path='approval.py'")
            db.commit()
        finally:
            db.close()
        result = library.search(self.store, self.project, "Approval", limit=100)
        self.assertEqual(result["items"], [])
        self.assertTrue(result["partial"])
        self.assertEqual([item["revision_id"] for item in result["unavailable"]], [rid])
        self.assertEqual(library._row(self.store, rid)["status"], "ready", "read-side detection must not rewrite published history")


if __name__ == "__main__":
    unittest.main()
