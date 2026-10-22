"""The original lesson ledger owns revision adoption, including crash recovery."""
from __future__ import annotations

import multiprocessing
import os
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import learn


def ledger_worker(channel, data_dir, operation, arguments):
    """Fresh interpreter and OS lock, not another facade over one Store lock."""
    try:
        channel.send({"ready": True})
        if channel.recv() != "start":
            raise RuntimeError("missing test barrier")
        try:
            if operation == "probe_ledger":
                acquire = learn.filelock.try_lock
                def nonblocking(stream, **options):
                    return acquire(stream, blocking=False)
                try:
                    with patch.object(learn.filelock, "try_lock", side_effect=nonblocking):
                        with learn.ledger_lock(data_dir):
                            result = "acquired"
                except BlockingIOError:
                    result = "blocked"
            elif operation == "crash_projection":
                append = learn._append_log
                def terminate_before_marker(data_dir, rows):
                    append(data_dir, rows[:-1])
                    os._exit(23)
                learn._append_log = terminate_before_marker
                learn.project_revision(Path(data_dir), **arguments)
                raise RuntimeError("crash checkpoint was not reached")
            else:
                result = getattr(learn, operation)(Path(data_dir), **arguments)
        except ValueError as error:
            channel.send({"conflict": str(error)})
        else:
            channel.send({"result": result})
    finally:
        channel.close()


class LearningLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "ledger"
        self.card = learn.add_lesson(self.data, {"project": "CLIENT", "status": "candidate", "title": "原始经验",
            "symptom": "刷新后记录消失", "cause": "待核对", "fix": "旧做法", "verify": "旧验证", "anti": "旧反例"})
        self.lid = self.card["id"]
        self.token = learn.revision_token(self.data, self.lid)
        self.fields = {"title": "固定经验", "symptom": "刷新后记录消失", "cause": "提交尚未完成", "fix": "事务提交后刷新",
                       "verify": "重读持久记录", "anti": "不能把响应成功等同于落库", "applicability": "已使用事务的写入接口",
                       "non_applicability": "只读列表请求"}

    def arguments(self, **changes):
        return {"project_key": "CLIENT", "origin_id": self.lid, "revision_id": "revision-one", "fields": self.fields,
                "actor": "alice", "decision_id": "decision-one", "expected_token": self.token, **changes}

    def adopt(self, **changes):
        return learn.project_revision(self.data, **self.arguments(**changes))

    def revoke(self, **changes):
        return learn.revoke_revision(self.data, **{"project_key": "CLIENT", "origin_id": self.lid,
            "revision_id": "revision-one", "actor": "alice", "decision_id": "revoke-one",
            "expected_token": learn.revision_token(self.data, self.lid), "reason": "新证据与这次做法冲突", **changes})

    def concurrent(self, calls):
        context = multiprocessing.get_context("spawn")
        workers = []
        try:
            for operation, arguments in calls:
                parent, child = context.Pipe()
                process = context.Process(target=ledger_worker, args=(child, str(self.data), operation, arguments))
                process.start()
                child.close()
                workers.append((process, parent))
            for process, channel in workers:
                self.assertTrue(channel.poll(15), "worker did not reach the explicit barrier")
                self.assertEqual(channel.recv(), {"ready": True})
            for process, channel in workers:
                channel.send("start")
            results = []
            for process, channel in workers:
                self.assertTrue(channel.poll(15), "ledger operation did not finish; possible nested-lock deadlock")
                results.append(channel.recv())
                process.join(15)
                self.assertFalse(process.is_alive())
                self.assertEqual(process.exitcode, 0)
            return results
        finally:
            for process, channel in workers:
                if process.is_alive():
                    process.terminate()
                    process.join(15)
                channel.close()

    def test_readers_do_not_create_missing_directory_or_lock(self):
        missing = Path(self.temp.name) / "never-created"
        self.assertEqual(learn.lessons(missing), [])
        self.assertIsNone(learn.active_revision(missing, "L1"))
        self.assertIsNone(learn.projection_receipt(missing, "unknown"))
        self.assertFalse(missing.exists())
        legacy = Path(self.temp.name) / "legacy"
        legacy.mkdir()
        (legacy / learn.LESSONS).write_text('{"id":"L1","title":"legacy"}\n', encoding="utf-8")
        before = {x.name: x.read_bytes() for x in legacy.iterdir()}
        self.assertEqual(learn.lessons(legacy)[0]["title"], "legacy")
        learn.revision_token(legacy, "L1")
        self.assertEqual({x.name: x.read_bytes() for x in legacy.iterdir()}, before)

    def test_nested_operations_take_one_kernel_lock_and_release_on_exception(self):
        original_lock, original_unlock = learn.filelock.try_lock, learn.filelock.unlock
        with patch.object(learn.filelock, "try_lock", wraps=original_lock) as acquire, patch.object(learn.filelock, "unlock", wraps=original_unlock) as release:
            with self.assertRaisesRegex(RuntimeError, "synthetic abort"):
                with learn.ledger_lock(self.data):
                    with learn.ledger_lock(self.data, create=False):
                        self.adopt()
                        learn.lesson(self.data, self.lid)
                        learn.revision_token(self.data, self.lid)
                        raise RuntimeError("synthetic abort")
            self.assertEqual(acquire.call_count, 1)
            self.assertEqual(release.call_count, 1)
            with learn.ledger_lock(self.data, create=False):
                self.assertEqual(acquire.call_count, 2)

    def test_existing_ledger_reads_hold_the_shared_kernel_lock(self):
        original = learn.filelock.try_lock
        with patch.object(learn.filelock, "try_lock", wraps=original) as acquire:
            learn.lessons(self.data)
        self.assertEqual(acquire.call_count, 1)
        self.assertEqual(Path(acquire.call_args.args[0].name).name, "lessons.lock")

    def test_another_process_cannot_enter_the_parent_ledger_lock(self):
        with learn.ledger_lock(self.data):
            self.assertEqual(self.concurrent([("probe_ledger", {})]), [{"result": "blocked"}])

    @unittest.skipUnless(hasattr(os, "fork"), "requires POSIX fork")
    def test_fork_does_not_inherit_reentrant_ownership_or_unlock_parent(self):
        context = multiprocessing.get_context("fork")
        parent, child = context.Pipe()
        process = context.Process(target=ledger_worker, args=(child, str(self.data), "probe_ledger", {}))
        try:
            with learn.ledger_lock(self.data):
                process.start()
                child.close()
                self.assertTrue(parent.poll(15))
                self.assertEqual(parent.recv(), {"ready": True})
                parent.send("start")
                self.assertTrue(parent.poll(15))
                self.assertEqual(parent.recv(), {"result": "blocked"})
                process.join(15)
                self.assertEqual(process.exitcode, 0)
                # The child's cleanup must not release the parent's flock.
                self.assertEqual(self.concurrent([("probe_ledger", {})]), [{"result": "blocked"}])
        finally:
            if process.is_alive():
                process.terminate()
                process.join(15)
            parent.close()
            child.close()

    def test_credit_reads_database_before_ledger_and_consumes_usage_once(self):
        ticket = {"id": 1, "key": "CLIENT-1"}
        learn.note_used(self.data, ticket, [self.card], "fix")
        calls = []
        def runs(**query):
            self.assertNotIn(str(self.data.resolve()), getattr(learn._LEDGER_LOCAL, "held", {}))
            calls.append(query)
            return [{"created": "2026-10-22 12:00:00", "result": "用了经验 " + self.lid}]
        platform = SimpleNamespace(data_dir=self.data, store=SimpleNamespace(runs=runs))
        learn._credit(platform, ticket, True, "alice")
        learn._credit(platform, ticket, True, "alice")
        self.assertEqual(len(calls), 2)
        card = learn.lesson(self.data, self.lid)
        self.assertEqual((card["stats"]["passed"], card["stats"]["cited"]), (1, 1))

    def test_projection_keeps_one_card_full_text_and_original_history(self):
        original = (self.data / learn.LESSONS).read_bytes()
        fields = {**self.fields, "fix": "确认持久写入之后再刷新。\n" * 1500}
        card = self.adopt(fields=fields)
        self.assertEqual(card["id"], self.lid)
        self.assertEqual(len(learn.lessons(self.data)), 1)
        self.assertEqual((self.data / learn.LESSONS).read_bytes(), original)
        for key, value in fields.items():
            self.assertEqual(card[key], value)
        self.assertEqual(card["status"], "active")
        self.assertEqual(learn.active_revision(self.data, self.lid), "revision-one")
        self.assertEqual([r["kind"] for r in learn._log(self.data)], ["edit", "status", "revision_projection"])
        self.assertNotEqual(learn.revision_token(self.data, self.lid), self.token)

    def test_only_complete_consistent_projection_can_bind_a_revision(self):
        other = learn.add_lesson(self.data, {"project": "CLIENT", "status": "active", "title": "旧卡",
                                           "active_revision": "unrecorded-revision"})
        self.assertIsNone(learn.active_revision(self.data, other["id"]))
        self.adopt()
        path = self.data / learn.LOG
        good = path.read_bytes()
        for mutate in (lambda rows: rows[-1].update(revision_id="changed-binding"),
                       lambda rows: rows[0]["fields"].update(fix="changed-text"),
                       lambda rows: rows[-1].update(rows_digest="invalid")):
            with self.subTest(mutate=mutate):
                rows = [json.loads(line) for line in good.decode("utf-8").splitlines()]
                mutate(rows)
                path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
                self.assertIsNone(learn.projection_receipt(self.data, "decision-one"))
                self.assertIsNone(learn.active_revision(self.data, self.lid))
                self.assertEqual(learn.lesson(self.data, self.lid)["status"], "candidate")
                self.assertEqual(learn.lesson(self.data, self.lid)["fix"], "旧做法")
        path.write_bytes(good)
        self.assertEqual(learn.active_revision(self.data, self.lid), "revision-one")

    def test_usage_preserves_token_and_revision_but_human_changes_do_not(self):
        self.adopt()
        token = learn.revision_token(self.data, self.lid)
        learn.note_used(self.data, {"key": "CLIENT-2"}, [learn.lesson(self.data, self.lid)], "fix")
        learn._append_log(self.data, [{"kind": "outcome", "id": self.lid, "ticket": "CLIENT-2", "passed": True}])
        self.assertEqual(learn.revision_token(self.data, self.lid), token)
        self.assertEqual(learn.active_revision(self.data, self.lid), "revision-one")
        learn.edit_lesson(self.data, self.lid, {"fix": "人工修改的新做法"}, "bob")
        self.assertNotEqual(learn.revision_token(self.data, self.lid), token)
        self.assertIsNone(learn.active_revision(self.data, self.lid))
        with self.assertRaisesRegex(ValueError, "不能撤销"):
            self.revoke(expected_token=token)

    def test_legacy_status_including_same_active_status_clears_revision(self):
        for status in ("active", "candidate", "retired", "probation"):
            with self.subTest(status=status):
                self.adopt(decision_id="adopt-" + status, expected_token=learn.revision_token(self.data, self.lid))
                before = learn.revision_token(self.data, self.lid)
                learn.set_status(self.data, self.lid, status, "bob", "人工的新决定")
                self.assertEqual(learn.lesson(self.data, self.lid)["status"], status)
                self.assertIsNone(learn.active_revision(self.data, self.lid))
                self.assertNotEqual(learn.revision_token(self.data, self.lid), before)

    def test_share_and_take_change_token_without_relabelling_source_revision(self):
        self.adopt()
        before = learn.revision_token(self.data, self.lid)
        learn.set_shared(self.data, self.lid, True, "alice", "已核对副本", {"fix": "脱敏后做法"})
        shared = learn.revision_token(self.data, self.lid)
        self.assertNotEqual(shared, before)
        learn.take_shared(self.data, self.lid, "OTHER", True, "bob")
        self.assertNotEqual(learn.revision_token(self.data, self.lid), shared)
        self.assertEqual(learn.active_revision(self.data, self.lid), "revision-one")
        with self.assertRaisesRegex(ValueError, "不属于当前项目"):
            self.adopt(project_key="OTHER", decision_id="foreign", expected_token=learn.revision_token(self.data, self.lid))

    def test_successful_replay_never_reactivates_after_later_human_decision(self):
        self.adopt()
        learn.set_status(self.data, self.lid, "retired", "bob", "不再采用")
        before = (self.data / learn.LOG).read_bytes()
        replay = self.adopt()
        self.assertTrue(replay["projection"]["replayed"])
        self.assertEqual(replay["status"], "retired")
        self.assertIsNone(learn.active_revision(self.data, self.lid))
        self.assertEqual((self.data / learn.LOG).read_bytes(), before)

    def test_projection_receipt_is_readonly_and_preserves_old_decision_binding(self):
        self.assertIsNone(learn.projection_receipt(self.data, "decision-one"))
        self.adopt()
        receipt = learn.projection_receipt(self.data, "decision-one")
        self.assertEqual(receipt["expected_token"], self.token)
        self.assertEqual(receipt["revision_id"], "revision-one")
        self.assertEqual(receipt["project"], "CLIENT")
        self.assertEqual(receipt["id"], self.lid)
        learn.edit_lesson(self.data, self.lid, {"fix": "后续的人工修订"}, "bob")
        before = {f.name: f.read_bytes() for f in self.data.iterdir()}
        with patch.object(learn.os, "fsync", side_effect=AssertionError("read must not sync or write")):
            self.assertEqual(learn.projection_receipt(self.data, "decision-one"), receipt)
        self.assertEqual({f.name: f.read_bytes() for f in self.data.iterdir()}, before)
        with self.assertRaisesRegex(ValueError, "决定编号已用于其他投影"):
            self.adopt(fields={**self.fields, "fix": "不同做法"})
        self.assertEqual((self.data / learn.LOG).read_bytes(), before[learn.LOG])

    def test_partial_projection_is_invisible_and_retry_keeps_original_bytes(self):
        append = learn._append_log
        def interrupt_after_status(data_dir, rows):
            append(data_dir, rows[:-1])
            raise OSError("synthetic interruption before marker")
        with patch.object(learn, "_append_log", side_effect=interrupt_after_status):
            with self.assertRaisesRegex(OSError, "before marker"):
                self.adopt()
        partial = (self.data / learn.LOG).read_bytes()
        self.assertEqual(learn.lesson(self.data, self.lid)["fix"], "旧做法")
        self.assertEqual(learn.lesson(self.data, self.lid)["status"], "candidate")
        self.assertEqual(learn.revision_token(self.data, self.lid), self.token)
        self.assertIsNone(learn.active_revision(self.data, self.lid))
        self.assertIsNone(learn.projection_receipt(self.data, "decision-one"))
        self.adopt()
        self.assertTrue((self.data / learn.LOG).read_bytes().startswith(partial))
        self.assertEqual(learn.active_revision(self.data, self.lid), "revision-one")
        self.assertEqual(len(learn.lesson(self.data, self.lid)["history"]), 2)

    def test_process_exit_before_marker_releases_lock_and_preserves_retry(self):
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(target=ledger_worker, args=(child, str(self.data), "crash_projection", self.arguments()))
        try:
            process.start()
            child.close()
            self.assertTrue(parent.poll(15))
            self.assertEqual(parent.recv(), {"ready": True})
            parent.send("start")
            process.join(15)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 23)
            prefix = (self.data / learn.LOG).read_bytes()
            self.assertEqual(learn.lesson(self.data, self.lid)["status"], "candidate")
            self.assertEqual(learn.revision_token(self.data, self.lid), self.token)
            result = self.concurrent([("project_revision", self.arguments())])
            self.assertEqual(result[0]["result"]["active_revision"], "revision-one")
            self.assertTrue((self.data / learn.LOG).read_bytes().startswith(prefix))
        finally:
            if process.is_alive():
                process.terminate()
                process.join(15)
            parent.close()
            child.close()

    def test_partial_projection_cannot_overwrite_later_legacy_edit(self):
        append = learn._append_log
        def interrupt_after_edit(data_dir, rows):
            append(data_dir, rows[:1])
            raise OSError("synthetic interruption")
        with patch.object(learn, "_append_log", side_effect=interrupt_after_edit):
            with self.assertRaises(OSError):
                self.adopt()
        learn.edit_lesson(self.data, self.lid, {"fix": "后来人工确认的做法"}, "bob")
        with self.assertRaisesRegex(ValueError, "人工决定已经变化"):
            self.adopt()
        self.assertEqual(learn.lesson(self.data, self.lid)["fix"], "后来人工确认的做法")
        self.assertEqual(learn.lesson(self.data, self.lid)["status"], "candidate")

    def test_complete_append_with_failed_fsync_retries_only_durability(self):
        with patch.object(learn.os, "fsync", side_effect=OSError("synthetic fsync failure")):
            with self.assertRaisesRegex(OSError, "fsync failure"):
                self.adopt()
        before = (self.data / learn.LOG).read_bytes()
        real_fsync = learn.os.fsync
        with patch.object(learn.os, "fsync", wraps=real_fsync) as sync:
            replay = self.adopt()
        self.assertTrue(replay["projection"]["replayed"])
        self.assertEqual(sync.call_count, 1)
        self.assertEqual((self.data / learn.LOG).read_bytes(), before)

    def test_torn_final_line_is_preserved_and_next_record_is_readable(self):
        damaged = b'{"kind":"edit","fields":{"fix":"partial'
        (self.data / learn.LOG).write_bytes(damaged)
        self.adopt()
        self.assertTrue((self.data / learn.LOG).read_bytes().startswith(damaged + b"\n"))
        self.assertEqual(learn.active_revision(self.data, self.lid), "revision-one")

    def test_revoke_only_current_revision_and_replay_cannot_undo_restoration(self):
        self.adopt()
        before = learn.revision_token(self.data, self.lid)
        with self.assertRaisesRegex(ValueError, "不能撤销"):
            self.revoke(revision_id="different-revision")
        note = "新证据与这次做法冲突。" * 500
        revoked = self.revoke(reason=note)
        self.assertEqual(revoked["status"], "probation")
        self.assertEqual(revoked["history"][-1]["why"], note)
        self.assertIsNone(learn.active_revision(self.data, self.lid))
        learn.set_status(self.data, self.lid, "active", "bob", "人工复核恢复")
        replay = self.revoke(expected_token=before, reason=note)
        self.assertTrue(replay["projection"]["replayed"])
        self.assertEqual(replay["status"], "active")
        self.assertIsNone(learn.active_revision(self.data, self.lid))

    def test_two_processes_adopting_same_expected_token_have_one_winner(self):
        results = self.concurrent([("project_revision", self.arguments(decision_id="first", revision_id="first")),
                                   ("project_revision", self.arguments(decision_id="second", revision_id="second"))])
        self.assertEqual(sum("result" in result for result in results), 1)
        self.assertEqual(sum("conflict" in result for result in results), 1)
        winner = next(result["result"] for result in results if "result" in result)
        self.assertEqual(learn.active_revision(self.data, self.lid), winner["active_revision"])
        self.assertEqual(len(learn._log(self.data)), 3)

    def test_two_processes_replaying_same_decision_append_once(self):
        results = self.concurrent([("project_revision", self.arguments()), ("project_revision", self.arguments())])
        self.assertTrue(all("result" in result for result in results), results)
        self.assertEqual(sorted(result["result"]["projection"]["replayed"] for result in results), [False, True])
        self.assertEqual(len(learn._log(self.data)), 3)
        self.assertEqual(len(learn.lessons(self.data)), 1)

    def test_legacy_retirement_and_new_projection_serialize_across_processes(self):
        results = self.concurrent([("set_status", {"lid": self.lid, "status": "retired", "by": "bob", "why": "人工停用"}),
                                   ("project_revision", self.arguments())])
        self.assertIn("result", results[0])
        self.assertTrue("result" in results[1] or "conflict" in results[1])
        self.assertEqual(learn.lesson(self.data, self.lid)["status"], "retired")
        self.assertIsNone(learn.active_revision(self.data, self.lid))

    def test_two_processes_deduplicate_original_card_source(self):
        card = {"project": "CLIENT", "status": "candidate", "source_key": "fixed-acceptance-12", "title": "来源卡"}
        results = self.concurrent([("add_lesson", {"d": card}), ("add_lesson", {"d": card})])
        self.assertEqual([result["result"]["id"] for result in results], ["L2", "L2"])
        self.assertEqual(len(learn.lessons(self.data)), 2)


if __name__ == "__main__":
    unittest.main()
