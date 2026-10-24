"""A human decision binds a full version and never replays its side effects."""
from pathlib import Path
import json
import multiprocessing
import os
import tempfile
import unittest
from unittest.mock import patch

from tmh.platform import learn


def decision_worker(channel, directory, operation, arguments):
    try:
        channel.send({"ready": True})
        if channel.recv() != "start":
            raise RuntimeError("missing explicit barrier")
        if operation in ("crash_before_replace", "crash_after_replace"):
            replace = learn.os.replace
            stage = operation
            def crash(source, target):
                if stage == "crash_after_replace":
                    replace(source, target)
                os._exit(23)
            learn.os.replace = crash
            operation = "human_decision"
        try:
            result = getattr(learn, operation)(Path(directory), **arguments)
        except learn.LessonDecisionError as error:
            channel.send({"code": error.code})
        except ValueError as error:
            channel.send({"legacy_conflict": str(error)})
        else:
            channel.send({"result": result})
    finally:
        channel.close()


def snapshot_race_worker(channel, directory, lid):
    read = Path.read_bytes
    captured = False
    def read_with_barrier(path):
        nonlocal captured
        payload = read(path)
        if path.name == learn.LESSONS and not captured:
            captured = True
            channel.send({"raw_captured": True})
            if channel.recv() != "writer_complete":
                raise RuntimeError("missing writer barrier")
        return payload
    try:
        with patch.object(Path, "read_bytes", read_with_barrier):
            channel.send({"snapshot": learn.lesson_snapshot(Path(directory), "APP", lid)})
    finally:
        channel.close()


@unittest.skipUnless(os.name == "posix", "人工经验决定尚未验证 Windows 原子替换和目录 fsync；该平台明确拒绝写入")
class LessonHumanDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.card = learn.add_lesson(self.data, {"project": "APP", "status": "candidate", "title": "原文",
                                                "symptom": "现象", "fix": "A"})
        self.lid = self.card["id"]
        self.token = learn.revision_token(self.data, self.lid)

    def decide(self, action="confirm", token=None, request_id="one", fields=None, reason="", actor="alice"):
        return learn.human_decision(self.data, "APP", self.lid, actor, action,
                                    self.token if token is None else token, request_id,
                                    fields=fields, reason=reason)

    def test_stale_confirmation_never_confirms_replacement_text(self):
        learn.edit_lesson(self.data, self.lid, {"fix": "B"}, "owner")
        before = (self.data / learn.LOG).read_bytes()
        with self.assertRaises(ValueError):
            self.decide()
        self.assertEqual((self.data / learn.LOG).read_bytes(), before)
        self.assertEqual(learn.lesson(self.data, self.lid)["status"], "candidate")

    def test_successful_old_request_cannot_restore_retired_card(self):
        self.decide()
        learn.set_status(self.data, self.lid, "retired", "owner", "已失效")
        before = (self.data / learn.LOG).read_bytes()
        self.decide()
        self.assertEqual(learn.lesson(self.data, self.lid)["status"], "retired")
        self.assertEqual((self.data / learn.LOG).read_bytes(), before)

    def test_invalid_action_with_fields_has_no_partial_edit(self):
        with self.assertRaises(ValueError):
            self.decide(action="invalid", fields={"fix": "B"})
        self.assertEqual(learn.lesson(self.data, self.lid)["fix"], "A")

    def test_confirm_cannot_serve_as_restore(self):
        learn.set_status(self.data, self.lid, "retired", "owner", "已失效")
        with self.assertRaises(ValueError):
            self.decide(token=learn.revision_token(self.data, self.lid))
        self.assertEqual(learn.lesson(self.data, self.lid)["status"], "retired")

    def snapshot(self):
        return learn.lesson_snapshot(self.data, "APP", self.lid)

    def arguments(self, **changes):
        return {"project": "APP", "lid": self.lid, "actor": "alice", "action": "confirm",
                "expected_token": self.token, "request_id": "one", **changes}

    def assert_code(self, code, call):
        with self.assertRaises(learn.LessonDecisionError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def logfile(self):
        path = self.data / learn.LOG
        return path.read_bytes() if path.exists() else b""

    def concurrent(self, calls):
        context = multiprocessing.get_context("spawn")
        workers = []
        try:
            for operation, arguments in calls:
                parent, child = context.Pipe()
                process = context.Process(target=decision_worker, args=(child, str(self.data), operation, arguments))
                process.start()
                child.close()
                workers.append((process, parent))
            for _, channel in workers:
                self.assertTrue(channel.poll(15), "worker did not reach explicit start barrier")
                self.assertEqual(channel.recv(), {"ready": True})
            for _, channel in workers:
                channel.send("start")
            results = []
            for process, channel in workers:
                self.assertTrue(channel.poll(15), "operation did not finish under the ledger lock")
                try:
                    results.append(channel.recv())
                except EOFError:
                    results.append({"crashed": True})
                process.join(15)
                self.assertFalse(process.is_alive())
                self.assertEqual(process.exitcode, 23 if results[-1].get("crashed") else 0)
            return results
        finally:
            for process, channel in workers:
                if process.is_alive():
                    process.terminate()
                    process.join(15)
                channel.close()

    def test_combined_edit_confirmation_binds_full_reviewed_b_not_base_a(self):
        text = "完整\r\n尾部  \u2028\u2029\u0085" * 1000
        result = self.decide(fields={"fix": text}, reason=" 保留原因\r\n ")
        receipt, current = result["receipt"], result["current"]
        self.assertEqual(receipt["base_token"], self.token)
        self.assertEqual(receipt["reviewed_content"]["fix"], text)
        self.assertEqual(receipt["reason"], " 保留原因\r\n ")
        self.assertEqual(current["card"]["fix"], text)
        self.assertEqual(receipt["reviewed_content_digest"], current["content_digest"])
        self.assertEqual(receipt["reviewed_content_digest"], learn._content_digest(receipt["reviewed_content"]))
        self.assertNotEqual(receipt["base_token"], current["expected_token"])
        self.assertEqual(receipt["decision_token"], current["expected_token"])
        self.assertFalse(result["replayed"])
        self.assertFalse(result["superseded"])
        self.assertEqual(len(self.logfile().splitlines()), 1)

    def test_replay_retains_original_receipt_and_reports_current_card(self):
        first = self.decide()
        learn.set_status(self.data, self.lid, "retired", "owner", "撤销")
        replay = self.decide()
        self.assertEqual(replay["receipt"], first["receipt"])
        self.assertTrue(replay["replayed"])
        self.assertTrue(replay["superseded"])
        self.assertEqual(replay["current"]["card"]["status"], "retired")

    def test_same_request_id_changed_intent_rejected_before_stale_token(self):
        self.decide()
        before = self.logfile()
        variants = [{"fields": {"fix": "B"}}, {"action": "retire", "reason": "reason"},
                    {"token": self.snapshot()["expected_token"]}, {"reason": "changed"}]
        for changes in variants:
            with self.subTest(changes=changes):
                self.assert_code("request_id_conflict", lambda: self.decide(**changes))
                self.assertEqual(self.logfile(), before)

    def test_actor_namespaces_and_cross_project_request_binding(self):
        self.decide(action="edit")
        other = self.decide(actor="bob", action="edit")
        self.assertFalse(other["replayed"])
        card = learn.add_lesson(self.data, {"project": "OTHER", "status": "candidate", "fix": "private"})
        args = self.arguments(project="OTHER", lid=card["id"], expected_token=learn.revision_token(self.data, card["id"]))
        self.assert_code("request_id_conflict", lambda: learn.human_decision(self.data, **args))
        self.assert_code("lesson_not_found", lambda: learn.human_decision(self.data, **self.arguments(project="OTHER")))

    def test_restore_requires_explicit_new_intent_reason_and_current_version(self):
        self.decide()
        learn.set_status(self.data, self.lid, "retired", "owner", "撤销")
        token = self.snapshot()["expected_token"]
        self.assert_code("invalid_lesson_decision", lambda: self.decide(action="restore", token=token, request_id="restore"))
        self.assert_code("lesson_state_conflict", lambda: self.decide(action="confirm", token=token, request_id="new-confirm"))
        restored = self.decide(action="restore", token=token, request_id="restore", reason=" 核对后恢复\r\n ")
        self.assertEqual(restored["current"]["card"]["status"], "active")
        self.assertEqual(restored["receipt"]["reason"], " 核对后恢复\r\n ")
        self.assertTrue(self.decide()["superseded"])

    def test_noop_receipt_preserves_token_revision_and_usage_window(self):
        learn.project_revision(self.data, "APP", self.lid, "fixed-v1", {"fix": "fixed"}, "owner", "adopt", self.token)
        learn._append_log(self.data, [{"kind": "outcome", "id": self.lid, "passed": False}])
        before = self.snapshot()
        result = self.decide(action="edit", token=before["expected_token"], fields={"fix": "fixed", "anti": ""})
        self.assertFalse(result["receipt"]["changed"])
        self.assertEqual(result["current"]["expected_token"], before["expected_token"])
        self.assertEqual(result["current"]["card"]["active_revision"], "fixed-v1")
        self.assertEqual(result["current"]["card"]["stats"], before["card"]["stats"])
        self.assertEqual(result["receipt"]["reviewed_content_digest"], result["current"]["content_digest"])

    def test_replay_cannot_clear_later_projection_or_usage(self):
        first = self.decide()
        learn.project_revision(self.data, "APP", self.lid, "fixed-v2", {"fix": "new"}, "owner", "adopt",
                               first["current"]["expected_token"])
        learn._append_log(self.data, [{"kind": "outcome", "id": self.lid, "passed": False}])
        before = self.snapshot()
        result = self.decide()
        self.assertEqual(result["current"], before)
        self.assertEqual(result["receipt"], first["receipt"])

    def test_usage_other_cards_and_aba_content(self):
        learn._append_log(self.data, [{"kind": "inject", "id": self.lid, "ticket": "APP-1"}])
        other = learn.add_lesson(self.data, {"project": "APP", "fix": "other"})
        learn.edit_lesson(self.data, other["id"], {"fix": "changed"}, "owner")
        self.assertEqual(self.snapshot()["expected_token"], self.token)
        first = self.decide()
        learn.edit_lesson(self.data, self.lid, {"fix": "B"}, "owner")
        learn.edit_lesson(self.data, self.lid, {"fix": "A"}, "owner")
        replay = self.decide()
        self.assertEqual(replay["current"]["content_digest"], first["current"]["content_digest"])
        self.assertTrue(replay["superseded"])

    def test_invalid_requests_preserve_all_bytes(self):
        variants = [{"fields": {"unknown": "x"}}, {"fields": {"fix": 1}}, {"fields": []},
                    {"reason": None}, {"reason": "\ud800"}, {"request_id": "bad id"}, {"request_id": ""},
                    {"token": "bad"}, {"action": "retire", "reason": "   "}, {"action": []}]
        before = self.logfile()
        for changes in variants:
            with self.subTest(changes=changes):
                self.assert_code("invalid_lesson_decision", lambda: self.decide(**changes))
                self.assertEqual(self.logfile(), before)
                self.assertEqual(self.snapshot()["card"]["fix"], "A")

    def test_snapshot_and_creation_are_full_readonly_consistent_material(self):
        payload = {"project": "APP", "status": "candidate", "fix": "B\r\n \u2028\u2029\u0085",
                   "note": "长备注" * 2000, "files": ["file%d" % n for n in range(12)],
                   "applicability": "真实条件", "non_applicability": "不适用条件"}
        locks = learn.filelock.try_lock
        with patch.object(learn.filelock, "try_lock", wraps=locks) as calls:
            result = learn.add_lesson_snapshot(self.data, payload)
        self.assertEqual(calls.call_count, 1)
        for key, value in payload.items():
            self.assertEqual(result["card"][key], value)
        before = {p.name: p.read_bytes() for p in self.data.iterdir()}
        self.assertEqual(learn.lesson_snapshot(self.data, "APP", result["lesson_id"]), result)
        self.assertEqual(learn.lesson_snapshots(self.data, "APP")[0], result)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.data.iterdir()})

    def test_missing_directory_read_and_invalid_write_create_nothing(self):
        directory = self.data / "absent"
        self.assert_code("lesson_not_found", lambda: learn.lesson_snapshot(directory, "APP", "L1"))
        self.assertEqual(learn.lesson_snapshots(directory, "APP"), [])
        self.assert_code("invalid_lesson_decision", lambda: learn.human_decision(directory, **self.arguments(request_id="")))
        self.assertFalse(directory.exists())

    def test_missing_lock_read_does_not_pair_old_card_with_new_token(self):
        learn.edit_lesson(self.data, self.lid, {"fix": "before"}, "owner")
        before = self.snapshot()
        (self.data / "lessons.lock").unlink()
        read = Path.read_bytes
        mutated = False
        def capture(path):
            nonlocal mutated
            payload = read(path)
            if path == self.data / learn.LOG and not mutated:
                mutated = True
                learn.edit_lesson(self.data, self.lid, {"fix": "after"}, "owner")
            return payload
        with patch.object(Path, "read_bytes", capture):
            observed = self.snapshot()
        self.assertNotEqual(observed["expected_token"], before["expected_token"])
        self.assertEqual(observed, self.snapshot())
        self.assertEqual(self.snapshot()["card"]["fix"], "after")

    def test_first_writer_between_raw_and_log_reads_recaptures_under_real_lock(self):
        (self.data / "lessons.lock").unlink()
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(target=snapshot_race_worker, args=(child, str(self.data), self.lid))
        process.start()
        child.close()
        try:
            self.assertTrue(parent.poll(15), "reader did not capture raw file")
            self.assertEqual(parent.recv(), {"raw_captured": True})
            card = learn.add_lesson_snapshot(self.data, {"project": "APP", "fix": "new", "status": "candidate"})
            learn.human_decision(self.data, "APP", card["lesson_id"], "owner", "confirm", card["expected_token"], "new-card")
            learn.edit_lesson(self.data, self.lid, {"fix": "new target"}, "owner")
            parent.send("writer_complete")
            self.assertTrue(parent.poll(15), "reader did not recapture after first writer")
            self.assertEqual(parent.recv()["snapshot"], self.snapshot())
            process.join(15)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)
        finally:
            if process.is_alive():
                process.terminate()
                process.join(15)
            parent.close()

    def test_old_ids_positions_and_projection_are_not_reindexed(self):
        source = b'\n{"project":"APP","fix":"A","status":"candidate"}\n\n{"id":"L99","project":"APP","fix":"B"}\n'
        (self.data / learn.LESSONS).write_bytes(source)
        self.lid = "L2"
        learn._append_log(self.data, [{"kind": "inject", "id": self.lid, "ticket": "APP-1"},
                                     {"kind": "verdict", "ticket": "APP-1", "credited_injections": [0]}])
        token = learn.revision_token(self.data, self.lid)
        rows = learn._log(self.data)
        self.assertEqual(self.snapshot()["expected_token"], token)
        created = learn.add_lesson_snapshot(self.data, {"project": "APP", "status": "candidate", "fix": "new"})
        self.assertEqual(created["lesson_id"], "L100")
        self.assertTrue((self.data / learn.LESSONS).read_bytes().startswith(source))
        self.assertEqual(learn._log(self.data), rows)
        self.assertEqual(learn._pending_injections(rows, "APP-1")[0], {})

    def test_creation_after_valid_unterminated_original_preserves_both_cards(self):
        original = (self.data / learn.LESSONS).read_bytes().rstrip(b"\n")
        (self.data / learn.LESSONS).write_bytes(original)
        result = learn.add_lesson_snapshot(self.data, {"project": "APP", "status": "candidate", "fix": "new"})
        self.assertEqual(result["lesson_id"], "L2")
        self.assertTrue((self.data / learn.LESSONS).read_bytes().startswith(original + b"\n"))
        self.assertEqual([item["card"]["fix"] for item in learn.lesson_snapshots(self.data, "APP")], ["new", "A"])

    def test_valid_unterminated_log_and_old_partial_projection_keep_prefix(self):
        row = {"kind": "edit", "id": self.lid, "by": "owner", "fields": {"fix": "not sealed"}, "projection_batch": "unfinished"}
        prefix = json.dumps(row, ensure_ascii=False).encode()
        (self.data / learn.LOG).write_bytes(prefix)
        self.assertEqual(self.snapshot()["expected_token"], self.token)
        result = self.decide()
        self.assertTrue(self.logfile().startswith(prefix + b"\n"))
        self.assertEqual(result["current"]["card"]["fix"], "A")
        self.assertEqual(result["current"]["card"]["status"], "active")

    def test_snapshot_token_matches_legacy_after_each_supported_transition(self):
        def same():
            self.assertEqual(self.snapshot()["expected_token"], learn.revision_token(self.data, self.lid))
        same()
        self.decide()
        same()
        learn.edit_lesson(self.data, self.lid, {"fix": "later"}, "owner")
        same()
        learn.project_revision(self.data, "APP", self.lid, "revision", {"fix": "fixed"}, "owner", "adopt", self.snapshot()["expected_token"])
        same()
        learn.set_shared(self.data, self.lid, True, "owner", "共享", {"fix": "公开"})
        same()
        learn.take_shared(self.data, self.lid, "OTHER", True, "owner")
        same()
        self.decide(action="edit", token=self.snapshot()["expected_token"], request_id="no-op")
        same()

    def test_forged_consistent_hashes_cannot_change_base_or_reviewed_types(self):
        source = json.loads((self.data / learn.LESSONS).read_text())
        source["ticket_id"] = 1
        (self.data / learn.LESSONS).write_text(json.dumps(source) + "\n")
        self.token = learn.revision_token(self.data, self.lid)
        self.decide()
        original = json.loads(self.logfile())
        for mutation in ("base", "content_type"):
            row = json.loads(json.dumps(original))
            if mutation == "base":
                row["base_token"] = row["request"]["base_token"] = "0" * 64
                row["request_digest"] = learn._digest(row["request"])
            else:
                row["reviewed_content"]["ticket_id"] = True
                row["reviewed_content_digest"] = learn._content_digest(row["reviewed_content"])
            row["envelope_digest"] = learn._digest({k: v for k, v in row.items() if k != "envelope_digest"})
            (self.data / learn.LOG).write_text(json.dumps(row) + "\n")
            self.assert_code("lesson_history_unreadable", self.snapshot)

    def test_ambiguous_old_history_is_preserved_and_never_signed(self):
        variants = [b'{"kind":"status",', b'null\n', b'[]\n', b'{"kind":"status"}\xff',
                    b'{"kind":"status","why":"x\xe2\x80\xa8y"}\n',
                    b'{"kind":"status","why":"x\xe2\x80\xa9y"}\n',
                    b'{"kind":"status","why":"x\xc2\x85y"}\n']
        for payload in variants:
            with self.subTest(payload=payload):
                (self.data / learn.LOG).write_bytes(payload)
                self.assert_code("lesson_history_unreadable", self.snapshot)
                self.assert_code("lesson_history_unreadable", self.decide)
                self.assertEqual(self.logfile(), payload)

    def test_each_utf8_tail_cut_fails_closed_without_loss(self):
        prefix = b'{"kind":"status","why":"'
        for end in range(1, len("汉".encode()) + 1):
            payload = prefix + "汉".encode()[:end]
            (self.data / learn.LOG).write_bytes(payload)
            self.assert_code("lesson_history_unreadable", self.snapshot)
            self.assertEqual(self.logfile(), payload)

    def test_duplicate_card_ids_and_unreadable_raw_source_are_rejected(self):
        original = (self.data / learn.LESSONS).read_bytes()
        for payload in (original + original, b'null\n', original + b'\xff'):
            (self.data / learn.LESSONS).write_bytes(payload)
            self.assert_code("lesson_history_unreadable", self.snapshot)
            self.assertEqual((self.data / learn.LESSONS).read_bytes(), payload)

    def test_invalid_old_content_has_diagnostic_error_without_token_or_loss(self):
        original = json.loads((self.data / learn.LESSONS).read_text())
        for fields in ({"fix": "\ud800"}, {"source_extra": "\ud800"}, {"fix": {}}, {"fix": 17},
                       {"source_extra": float("nan")}, {"source_extra": float("inf")}):
            payload = (json.dumps({**original, **fields}, ensure_ascii=True) + "\n").encode()
            (self.data / learn.LESSONS).write_bytes(payload)
            self.assert_code("lesson_history_unreadable", self.snapshot)
            self.assert_code("lesson_history_unreadable", self.decide)
            self.assertEqual((self.data / learn.LESSONS).read_bytes(), payload)
        # Null is an existing absent-text representation, not silently rewritten.
        payload = (json.dumps({**original, "fix": None}) + "\n").encode()
        (self.data / learn.LESSONS).write_bytes(payload)
        self.assertIsNone(self.snapshot()["card"]["fix"])
        self.assertEqual((self.data / learn.LESSONS).read_bytes(), payload)

    def test_create_validates_complete_input_before_any_append(self):
        before = {p.name: p.read_bytes() for p in self.data.iterdir()}
        for fields in ({"fix": "\ud800"}, {"source_extra": "\ud800"}, {"fix": {}}, {"fix": 17},
                       {"source_extra": float("nan")}, {"source_extra": float("inf")}):
            self.assert_code("invalid_lesson_decision", lambda: learn.add_lesson_snapshot(
                self.data, {"project": "APP", "status": "candidate", **fields}))
            self.assertEqual({p.name: p.read_bytes() for p in self.data.iterdir()}, before)

    def test_nonfinite_derived_history_or_shared_copy_cannot_escape_snapshot(self):
        rows = [{"kind": "status", "id": self.lid, "status": "candidate", "by": "owner", "why": float("nan")},
                {"kind": "share", "id": self.lid, "on": True, "fields": {"fix": float("inf")}, "by": "owner"},
                {"kind": "status", "id": self.lid, "status": "candidate", "by": "owner", "why": "\ud800"}]
        for row in rows:
            with self.subTest(kind=row["kind"]):
                payload = (json.dumps(row, ensure_ascii=True) + "\n").encode()
                (self.data / learn.LOG).write_bytes(payload)
                self.assert_code("lesson_history_unreadable", self.snapshot)
                self.assert_code("lesson_history_unreadable", self.decide)
                self.assertEqual(self.logfile(), payload)

    def test_durable_replay_needs_no_second_publication(self):
        first = self.decide()
        before = self.logfile()
        with patch.object(learn, "_publish_human_log", side_effect=AssertionError("replay published")), \
             patch.object(learn, "_fsync_directory", wraps=learn._fsync_directory) as synced:
            result = self.decide()
        self.assertEqual(result["receipt"], first["receipt"])
        self.assertEqual(self.logfile(), before)
        self.assertEqual(synced.call_count, 1)

    def test_temp_fsync_and_replace_failure_preserve_formal_history(self):
        learn._append_log(self.data, [{"kind": "inject", "id": self.lid, "ticket": "APP-1"}])
        before = self.logfile()
        for method in ("fsync", "replace"):
            with self.subTest(method=method), patch.object(learn.os, method, side_effect=OSError("synthetic failure")):
                self.assert_code("decision_outcome_unknown", self.decide)
            self.assertEqual(self.logfile(), before)
            self.assertEqual(self.snapshot()["card"]["status"], "candidate")
            self.assertFalse(list(self.data.glob(".lesson-decision-*")))
        self.assertFalse(self.decide()["replayed"])

    def test_directory_fsync_failure_is_unknown_and_retry_cannot_reactivate(self):
        with patch.object(learn, "_fsync_directory", side_effect=OSError("directory sync failed")):
            self.assert_code("decision_outcome_unknown", self.decide)
        self.assertEqual(self.snapshot()["card"]["status"], "active")
        learn.set_status(self.data, self.lid, "retired", "owner", "new decision")
        before = self.logfile()
        result = self.decide()
        self.assertTrue(result["replayed"])
        self.assertTrue(result["superseded"])
        self.assertEqual(result["current"]["card"]["status"], "retired")
        self.assertEqual(self.logfile(), before)

    def test_first_log_creation_syncs_file_and_directory_preserves_modes_prefix(self):
        self.assertFalse((self.data / learn.LOG).exists())
        with patch.object(learn, "_fsync_directory", wraps=learn._fsync_directory) as directory:
            self.decide()
        self.assertEqual(directory.call_count, 1)
        path = self.data / learn.LOG
        os.chmod(path, 0o640)
        before = path.read_bytes()
        self.decide(action="edit", token=self.snapshot()["expected_token"], request_id="edit", fields={"fix": "B"})
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertTrue(path.read_bytes().startswith(before))

    def test_exact_duplicate_envelope_applies_once_but_conflicting_copy_fails(self):
        first = self.decide()
        payload = self.logfile()
        (self.data / learn.LOG).write_bytes(payload + payload)
        replay = self.decide()
        self.assertEqual(replay["current"], first["current"])
        self.assertEqual(replay["receipt"], first["receipt"])
        row = json.loads(payload)
        row["ts"] += "different"
        row["envelope_digest"] = learn._digest({key: value for key, value in row.items() if key != "envelope_digest"})
        (self.data / learn.LOG).write_bytes(payload + (json.dumps(row) + "\n").encode())
        self.assert_code("lesson_history_unreadable", self.snapshot)

    def test_corrupt_envelope_or_rewritten_prefix_never_reverts_to_prior_state(self):
        self.decide()
        payload = self.logfile()
        row = json.loads(payload)
        row["reviewed_content"]["fix"] = "not reviewed"
        for bad in ((json.dumps(row) + "\n").encode(), payload[:-5]):
            (self.data / learn.LOG).write_bytes(bad)
            self.assert_code("lesson_history_unreadable", self.snapshot)
            self.assert_code("lesson_history_unreadable", lambda: learn.lesson(self.data, self.lid))
        (self.data / learn.LOG).write_bytes(payload)
        original = json.loads((self.data / learn.LESSONS).read_text())
        original["fix"] = "rewritten source"
        (self.data / learn.LESSONS).write_text(json.dumps(original) + "\n")
        self.assert_code("lesson_history_unreadable", self.snapshot)

    def test_two_process_same_token_only_one_new_decision(self):
        results = self.concurrent([("human_decision", self.arguments(request_id="one")),
                                   ("human_decision", self.arguments(request_id="two"))])
        self.assertEqual(sum("result" in result for result in results), 1)
        self.assertEqual([result["code"] for result in results if "code" in result], ["lesson_changed"])
        self.assertEqual(len(learn._log(self.data)), 1)

    def test_two_process_same_request_publishes_once(self):
        results = self.concurrent([("human_decision", self.arguments()), ("human_decision", self.arguments())])
        self.assertEqual(sorted(result["result"]["replayed"] for result in results), [False, True])
        self.assertEqual(results[0]["result"]["receipt"], results[1]["result"]["receipt"])
        self.assertEqual(len(learn._log(self.data)), 1)

    def test_process_exit_before_and_after_replace_have_no_partial_decision(self):
        result = self.concurrent([("crash_before_replace", self.arguments())])
        self.assertEqual(result, [{"crashed": True}])
        self.assertEqual(self.snapshot()["card"]["status"], "candidate")
        result = self.concurrent([("crash_after_replace", self.arguments())])
        self.assertEqual(result, [{"crashed": True}])
        self.assertEqual(self.snapshot()["card"]["status"], "active")
        replay = self.decide()
        self.assertTrue(replay["replayed"])
        self.assertEqual(len(learn._log(self.data)), 1)

    def test_legacy_retire_and_human_confirm_serialize_without_revival(self):
        results = self.concurrent([("human_decision", self.arguments()),
                                   ("set_status", {"lid": self.lid, "status": "retired", "by": "owner", "why": "new"})])
        self.assertEqual(self.snapshot()["card"]["status"], "retired")
        if "result" in results[0]:
            self.assertEqual(self.decide()["current"]["card"]["status"], "retired")
        else:
            self.assertEqual(results[0]["code"], "lesson_changed")

    def test_fixed_projection_and_human_confirm_share_one_cas_lock(self):
        projection = {"project_key": "APP", "origin_id": self.lid, "revision_id": "fixed", "fields": {"fix": "new"},
                      "actor": "owner", "decision_id": "adopt", "expected_token": self.token}
        results = self.concurrent([("human_decision", self.arguments()), ("project_revision", projection)])
        self.assertEqual(sum("result" in result for result in results), 1)
        card = self.snapshot()["card"]
        self.assertEqual(card["status"], "active")
        self.assertEqual(card["fix"], "A" if "result" in results[0] else "new")


class LessonDecisionStorageBoundaryTests(unittest.TestCase):
    def test_unsupported_storage_fails_before_creation_or_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "never-created"
            with patch.object(learn.os, "fchmod", None, create=True):
                with self.assertRaises(learn.LessonDecisionError) as caught:
                    learn.human_decision(directory, "APP", "L1", "alice", "confirm", "a" * 64, "one")
            self.assertEqual(caught.exception.status, 503)
            self.assertEqual(caught.exception.code, "lesson_storage_unsupported")
            self.assertFalse(directory.exists())
