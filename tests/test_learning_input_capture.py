"""Persisted options cannot authenticate their own original selection pool."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh.platform import learn, learning as L, learning_eval as E, learning_runs as R, learning_decisions as D
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


class LearningInputCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="lesson-capture-")
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        root = self.data / "repo"
        root.mkdir()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.p = self.store.add_project("APP", "APP", str(root))
        fields = dict(project="APP", title="transaction callback", symptom="transaction callback",
                      fix="transaction callback", verify="transaction callback verified",
                      applicability="transaction callback", non_applicability="unrelated event")
        self.origin = learn.add_lesson(self.data, dict(fields, ticket="OLD-1", status="candidate"))
        for i in range(3):
            learn.add_lesson(self.data, dict(fields, ticket="OLD-%d" % (i + 2), status="active"))
        item = L._origin(self.P, self.p, "lesson:" + self.origin["id"])
        self.r = L.capture(self.P, self.p, item["key"], item["fingerprint"], "writer")
        self.body = {"max_calls": 6, "cases": [dict(id=str(i), input="transaction callback " + str(i),
            expected=["ok"], forbidden=[], validator="contains_all", generation=False) for i in range(3)]}

    def start(self, request="capture"):
        with patch.object(R, "_configuration", return_value={"agent": "claude", "model": "synthetic",
                "configuration": {"isolated": True}, "executable": "never-executed", "prompt_version": R.PROMPT_VERSION}):
            return R.start(self.P, self.p, "evaluate", self.r["id"], self.body, "operator", request, launch=False)

    def row(self, jid):
        return self.store.one("SELECT * FROM learning_jobs WHERE id=?", (jid,))

    def mutate(self, options, name):
        value = copy.deepcopy(options)
        f, lid = value["evaluation"], self.origin["id"]
        pool = f["pool"]
        if name == "remove":
            pool["local"] = [c for c in pool["local"] if c["id"] == lid]
            pool["anchors"] = {lid: pool["anchors"][lid]}
            pool["binding"]["local_tokens"] = {lid: pool["binding"]["local_tokens"][lid]}
            pool["binding"]["eligibility"]["local"] = {lid: pool["binding"]["eligibility"]["local"][lid]}
        elif name == "order":
            pool["local"].reverse()
        else:
            next(c for c in pool["local"] if c["id"] == lid)["stats"].update(passed=1000, failed=0)
        f["inputs"] = E._build_lesson_inputs(pool, f["candidate_origin_id"], f["candidate_content"], f["cases"], f["evidence"])
        f["integrity_sha256"] = E._integrity(f)
        return value

    def test_options_only_rehashed_pool_mutations_never_reach_step(self):
        job = self.start()
        original = self.row(job["id"])
        self.assertFalse(job["options"]["evaluation"]["inputs"]["0"]["intervention"]["candidate_selected"])
        for name in ("remove", "order", "stats"):
            with self.subTest(mutation=name):
                changed = self.mutate(job["options"], name)
                self.store.x("UPDATE learning_jobs SET options=? WHERE id=?", (R._json(changed), job["id"]))
                loaded = R._decode(self.row(job["id"]))
                current, calls, error = E.current(self.P, self.p, loaded), [], None
                try:
                    E.run(self.P, self.p, loaded, lambda role, prompt: calls.append((role, prompt)) or "ok")
                except ApiError as exc:
                    error = exc
                self.assertEqual(self.row(job["id"])["binding"], original["binding"])
                self.assertFalse(current)
                self.assertIsNotNone(error)
                self.assertEqual(calls, [])
                self.assertFalse(R.get(self.P, self.p, job["id"])["input_contract"]["executable"])

    def test_unsealed_v2_expires_without_backfill_or_budget_restart(self):
        job = self.start()
        source = L.binding(self.P, self.p)
        self.store.x("UPDATE learning_jobs SET binding=? WHERE id=?", (R._json(source), job["id"]))
        before = self.row(job["id"])
        self.assertFalse(E.current(self.P, self.p, R._decode(before)))
        with patch.object(R.threading, "Thread", side_effect=AssertionError("unsealed launch")):
            self.assertTrue(R._expire_input(self.P, self.p, job["id"]))
        after = self.row(job["id"])
        self.assertEqual(after["status"], "stale")
        self.assertIn("input_schema_expired", after["error"])
        for field in ("options", "binding", "calls", "deadline", "result"):
            self.assertEqual(after[field], before[field])

    def test_atomic_registration_rolls_back_capture_job_and_cases(self):
        reserve = E.reserve
        def fail(*args):
            reserve(*args)
            raise RuntimeError("after reservations")
        with patch.object(E, "reserve", side_effect=fail), self.assertRaisesRegex(RuntimeError, "after reservations"):
            self.start()
        self.assertEqual(self.store.q("SELECT * FROM learning_jobs"), [])
        self.assertEqual(self.store.q("SELECT * FROM learning_eval_cases"), [])

    def test_later_usage_and_cards_do_not_change_original_capture(self):
        job = self.start()
        before = self.row(job["id"])
        learn._append_log(self.data, [{"kind": "outcome", "id": self.origin["id"], "passed": True, "ticket": "NEW-1"}])
        learn.add_lesson(self.data, dict(project="APP", ticket="NEW-2", title="FUTURE", fix="FUTURE", status="active"))
        self.assertTrue(E.current(self.P, self.p, job))
        calls = []
        E.run(self.P, self.p, job, lambda role, prompt: calls.append(prompt) or "ok")
        self.assertEqual(len(calls), 6)
        self.assertTrue(all("FUTURE" not in prompt for prompt in calls))
        self.assertEqual(self.row(job["id"])["binding"], before["binding"])
        self.assertEqual(self.row(job["id"])["options"], before["options"])

    def test_captured_input_cannot_downgrade_to_terminal_legacy(self):
        job = self.start()
        frozen = copy.deepcopy(job["options"])
        frozen["evaluation"].pop("schema")
        self.store.x("UPDATE learning_jobs SET options=?,status='passed' WHERE id=?", (R._json(frozen), job["id"]))
        loaded = R.get(self.P, self.p, job["id"])
        self.assertFalse(E.current(self.P, self.p, loaded))
        self.assertEqual(loaded["evidence_scope"]["input_scope"], "unknown")

    def test_unsealed_new_content_revision_cannot_impersonate_old_terminal_input(self):
        job = self.start()
        frozen = copy.deepcopy(job["options"])
        frozen["evaluation"].pop("schema")
        self.store.x("UPDATE learning_jobs SET options=?,binding=?,status='passed' WHERE id=?",
                     (R._json(frozen), R._json(L.binding(self.P, self.p)), job["id"]))
        loaded = R.get(self.P, self.p, job["id"])
        self.assertFalse(E.current(self.P, self.p, loaded))
        self.assertEqual(loaded["evidence_scope"]["input_scope"], "unknown")

    def test_caller_binding_is_not_the_authority_for_rewritten_options(self):
        job = self.start()
        changed = self.mutate(job["options"], "order")
        self.store.x("UPDATE learning_jobs SET options=? WHERE id=?", (R._json(changed), job["id"]))
        forged = R._decode(self.row(job["id"]))
        receipt = forged["binding"][E.CAPTURE_KEY]
        receipt["evaluation"] = changed["evaluation"]
        receipt["evaluation_sha256"] = E._digest(changed["evaluation"])
        self.assertFalse(E.current(self.P, self.p, forged))
        with self.assertRaises(ApiError):
            E.run(self.P, self.p, forged, lambda *_: self.fail("forged binding executed"))
        before = self.row(job["id"])["binding"]
        with patch.object(R.threading, "Thread", side_effect=AssertionError("rewritten replay launched")):
            replay = self.start()
        self.assertEqual(replay["status"], "stale")
        self.assertEqual(self.row(job["id"])["binding"], before)

    def test_capture_identity_cannot_move_between_jobs_or_projects(self):
        first = self.start()
        self.store.x("UPDATE learning_jobs SET status='not_passed' WHERE id=?", (first["id"],))
        second = self.start("another-request")
        original = self.row(second["id"])
        for field, value in (("id", first["id"]), ("project_id", True), ("revision_id", "other"),
                             ("actor", "other"), ("request_id", first["request_id"]), ("request_hash", "other")):
            with self.subTest(field=field):
                binding = json.loads(original["binding"])
                binding[E.CAPTURE_KEY]["job"][field] = value
                self.store.x("UPDATE learning_jobs SET binding=? WHERE id=?", (R._json(binding), second["id"]))
                self.assertFalse(E.current(self.P, self.p, R._decode(self.row(second["id"]))))
        self.store.x("UPDATE learning_jobs SET binding=? WHERE id=?", (original["binding"], second["id"]))
        self.assertTrue(E.current(self.P, self.p, R._decode(self.row(second["id"]))))

    def test_unregistered_or_mismatched_caller_identity_cannot_execute(self):
        job = self.start()
        for field, value in (("id", "absent-job"), ("project_id", True), ("kind", "review"),
                             ("revision_id", "other"), ("current_revision_id", "other"),
                             ("actor", "other"), ("request_id", "other"), ("request_hash", "other")):
            with self.subTest(field=field):
                caller = copy.deepcopy(job)
                caller[field] = value
                self.assertEqual(E.execution_contract_error(caller, "lesson", P=self.P, p=self.p), "input_schema_expired")
                self.assertFalse(E.current(self.P, self.p, caller))
        unregistered = copy.deepcopy(job)
        unregistered["id"] = "absent-job"
        with self.assertRaises(ApiError):
            E.run(self.P, self.p, unregistered, lambda *_: self.fail("unregistered input executed"))

    def test_capture_retains_exact_source_binding_and_worker_checks_all_other_keys(self):
        job = self.start()
        source = L.binding(self.P, self.p)
        capture = job["binding"][E.CAPTURE_KEY]
        self.assertEqual(E.source_binding(job["binding"]), source)
        self.assertEqual(capture["evaluation"], job["options"]["evaluation"])
        self.assertEqual(capture["evaluation_sha256"], E._digest(job["options"]["evaluation"]))
        config = {key: job["options"][key] for key in ("agent", "model", "configuration", "executable", "prompt_version")}
        with patch.object(R, "_configuration", return_value=config):
            self.assertEqual(R._check_current(self.P, self.p, job)["id"], self.r["id"])
            for field, value in (("root", "different-root"), ("future_source_key", "must-not-ignore")):
                with self.subTest(field=field):
                    changed = copy.deepcopy(job)
                    changed["binding"][field] = value
                    with self.assertRaises(R._Stopped) as caught:
                        R._check_current(self.P, self.p, changed)
                    self.assertEqual(caught.exception.status, "stale")

    def test_two_independent_stores_register_one_complete_capture_for_same_request(self):
        second_store = Store(self.store.path)
        self.addCleanup(second_store.db.close)
        second = SimpleNamespace(store=second_store, data_dir=self.data)
        barrier = threading.Barrier(2)
        validate = E.validate_options
        results, errors = [None, None], [None, None]
        def prepare(*args):
            frozen = validate(*args)
            barrier.wait(5)  # both callers saw no job before competing for the writer transaction
            return frozen
        def register(index, platform):
            try:
                results[index] = R.start(platform, self.p, "evaluate", self.r["id"], self.body,
                                        "operator", "same-request", launch=False)
            except BaseException as exc:
                errors[index] = repr(exc)
        config = {"agent": "claude", "model": "synthetic", "configuration": {"isolated": True},
                  "executable": "never-executed", "prompt_version": R.PROMPT_VERSION}
        threads = [threading.Thread(target=register, args=(index, platform), daemon=True)
                   for index, platform in enumerate((self.P, second))]
        with patch.object(R, "_configuration", return_value=config), \
                patch.object(E, "validate_options", side_effect=prepare) as preparing, \
                patch.object(E, "reserve", wraps=E.reserve) as reserving:
            try:
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(10)
            finally:
                barrier.abort()
            self.assertTrue(all(not thread.is_alive() for thread in threads), "registration deadlocked")
            self.assertEqual(errors, [None, None])
            self.assertEqual(preparing.call_count, 2)
            self.assertEqual(reserving.call_count, 1)
        self.assertEqual(results[0]["id"], results[1]["id"])
        rows = self.store.q("SELECT * FROM learning_jobs")
        self.assertEqual(len(rows), 1)
        job = R._decode(rows[0])
        capture = job["binding"][E.CAPTURE_KEY]
        self.assertEqual(capture["job"], {key: job[key] for key in E.CAPTURE_IDENTITY})
        self.assertEqual(capture["evaluation"], job["options"]["evaluation"])
        self.assertEqual(capture["evaluation_sha256"], E._digest(capture["evaluation"]))
        self.assertTrue(E.current(self.P, self.p, job))
        self.assertTrue(E.current(second, self.p, R.get(second, self.p, job["id"])))
        reservations = self.store.q("SELECT * FROM learning_eval_cases")
        self.assertEqual(len(reservations), 3)
        self.assertEqual({row["job_id"] for row in reservations}, {job["id"]})
        self.assertEqual({row["revision_id"] for row in reservations}, {self.r["id"]})
        self.assertEqual({row["purpose"] for row in reservations}, {"holdout"})
        self.assertEqual(job["calls"], 0)
        self.assertEqual(self.store.q("SELECT * FROM learning_steps"), [])

    def test_genuine_legacy_passed_receipt_can_cross_actual_personal_adoption_gate(self):
        from tests.test_learning_input_compat import _legacy_job
        fixture = SimpleNamespace(P=self.P, p=self.p, store=self.store, data=self.data,
                                  r=self.r, card=self.origin)
        revision, jid, _, _ = _legacy_job(fixture, "passed")
        stored_revision = self.store.one("SELECT * FROM learning_revisions WHERE id=?", (revision["id"],))
        stored_job = self.row(jid)
        self.assertNotIn("lesson_content_schema", revision["source"])
        self.assertNotIn(E.CAPTURE_KEY, R._decode(stored_job)["binding"])
        self.assertFalse(R.get(self.P, self.p, jid)["input_contract"]["executable"])
        with self.assertRaises(ApiError) as denied:
            D.decide(self.P, self.p, "adopt", revision["id"], "agent:reviewer", "agent-request",
                     None, "合成旧回执不得由智能体采用", jid)
        self.assertEqual(denied.exception.code, 403)
        self.assertEqual(self.store.q("SELECT * FROM learning_decisions"), [])
        self.assertIsNone(learn.active_revision(self.data, self.origin["id"]))
        # This is an explicitly supplied synthetic personal decision, not model approval.
        result = D.decide(self.P, self.p, "adopt", revision["id"], "alice", "human-request",
                          None, "合成人工操作者已核对原旧版证据", jid)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["actor"], "alice")
        self.assertEqual(learn.active_revision(self.data, self.origin["id"]), revision["id"])
        self.assertEqual(learn.lesson(self.data, self.origin["id"])["status"], "active")
        self.assertEqual(self.row(jid), stored_job)
        self.assertEqual(self.store.one("SELECT * FROM learning_revisions WHERE id=?", (revision["id"],)), stored_revision)


if __name__ == "__main__":
    unittest.main()
