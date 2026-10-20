"""Real local checks must remain bound to their sealed verification operation."""
import json
import unittest
from pathlib import Path
from unittest import mock

from tests import test_run_handoff as helpers
from tmh.platform.fixloop import recheck, recheck_operations, verified
from tmh.platform.orchestra import Orchestra
from tmh.platform.recheck_operations import read_status, source_guard
from tmh.platform.supervised_process import _atomic_json


class RecheckPublicationTest(unittest.TestCase):
    def setUp(self):
        # Reuse the real Git + py_compile fixture without inheriting its tests.
        self.fixture = helpers.RunHandoffTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.data, self.store, self.runner = self.fixture.data, self.fixture.store, self.fixture.runner
        self.root, run, self.wt, self.folder, self.diff = self.fixture.recheck_fixture(verdict="pass")
        self.rid = run["id"]
        self.original = self.store.run(self.rid)
        self.original_verification = (self.folder / "verify.json").read_bytes()
        self.addCleanup(self.release_owners)

    def release_owners(self):
        manager = getattr(self.runner, "rechecks", None)
        if manager is not None:
            for opid in list(manager.runner.owners):
                manager.runner._release(opid)
            for opid in list(manager._source_guards):
                manager._source_guards.pop(opid).__exit__(None, None, None)

    def assert_sealed_failure(self, code):
        operation = read_status(self.data, self.rid)
        self.assertEqual(operation["status"], "failed")
        self.assertEqual(operation["exit_code"], code)
        self.assertTrue(operation["lifecycle"]["finished"])
        self.assertTrue(operation["can_retry"], operation["blocked"])
        self.assertFalse(operation["running"])
        self.assertNotIn(operation["id"], recheck_operations(self.runner).runner.owners)
        for attempt in operation["lifecycle"]["attempts"]:
            self.assertTrue(attempt["cleanup"]["complete"])
        with source_guard(self.data, self.rid):
            pass  # a later decision/recheck can claim the released source lease
        self.assertEqual(self.store.run(self.rid), self.original)
        current = verified(self.data, self.rid)
        self.assertEqual(current["check"], "unknown")
        self.assertFalse(current["verification_current"])
        return operation

    def test_thread_start_failure_seals_without_mutating_original_run(self):
        orchestra = Orchestra(self.store, self.runner, self.data, None)
        failure = RuntimeError("fixture worker thread could not start")
        with mock.patch("tmh.platform.orchestra.threading.Thread.start", side_effect=failure):
            with self.assertRaises(RuntimeError) as caught:
                orchestra.recheck(self.rid, "publication reviewer")
        self.assertIs(caught.exception, failure)
        operation = self.assert_sealed_failure(125)
        self.assertEqual(operation["lifecycle"]["attempts"], [])
        self.assertIn(str(failure), operation["result"])
        self.assertNotIn(self.rid, orchestra.rechecking)
        self.assertEqual((self.folder / "verify.json").read_bytes(), self.original_verification)

    def assert_publication_failure(self, filename):
        failure = OSError("fixture cannot publish " + filename)

        def publish(path, value, **kwargs):
            if Path(path).name == filename:
                raise failure
            return _atomic_json(path, value, **kwargs)

        with mock.patch("tmh.platform.supervised_process._atomic_json", side_effect=publish):
            with self.assertRaises(OSError) as caught:
                recheck(self.runner, self.rid, by="publication reviewer")
        self.assertIs(caught.exception, failure, "sealing must not replace the initiating error")
        operation = self.assert_sealed_failure(1)
        self.assertIn(str(failure), operation["result"])
        self.assertIn(str(failure), operation["output"])
        self.assertTrue(operation["lifecycle"]["attempts"], "real build commands ran before publication failed")
        evidence = recheck_operations(self.runner).folder(operation["id"])
        self.assertEqual((evidence / "verification.before.json").read_bytes(), self.original_verification)
        self.assertEqual((self.folder / "verify.json").read_bytes(), self.original_verification)
        for attempt in operation["lifecycle"]["attempts"]:
            folder = evidence / "attempts" / ("%04d" % attempt["attempt"])
            self.assertTrue((folder / "output.bin").is_file())
            receipt = json.loads((folder / "supervisor-result.json").read_text())
            self.assertTrue(receipt["cleanup"]["complete"])
        return evidence

    def test_operation_artifact_publication_failure_cannot_revive_old_pass(self):
        evidence = self.assert_publication_failure("verification.json")
        self.assertFalse((evidence / "verification.json").exists())

    def test_current_verification_publication_failure_keeps_sealed_artifact_and_old_bytes(self):
        evidence = self.assert_publication_failure("verify.json")
        artifact = json.loads((evidence / "verification.json").read_text())
        self.assertEqual(artifact["check"], "pass", "a passed command does not imply publication succeeded")

    def successful_recheck(self):
        result = recheck(self.runner, self.rid, by="publication reviewer")
        self.assertEqual(result["check"], "pass")
        self.assertTrue(result["verification_current"])
        operation = read_status(self.data, self.rid)
        self.assertEqual(operation["status"], "done")
        self.assertTrue(operation["can_retry"], operation["blocked"])
        artifact = recheck_operations(self.runner).folder(operation["id"]) / "verification.json"
        value = json.loads(artifact.read_text())
        self.assertEqual(value["checked_commit"], "", "unadopted code is identified by base and diff, not an invented SHA")
        return artifact, value

    def assert_changed_binding_is_rejected(self, mutate):
        artifact, value = self.successful_recheck()
        mutate(value)
        # Both copies agree, so rejection must come from the immutable source
        # binding rather than a trivial artifact/current-file inequality.
        for path in (artifact, self.folder / "verify.json"):
            path.write_text(json.dumps(value), encoding="utf-8")
        current = verified(self.data, self.rid)
        self.assertEqual(current["check"], "unknown")
        self.assertFalse(current["verification_current"])

    def test_matching_artifacts_with_wrong_checked_commit_do_not_inherit_operation(self):
        self.assert_changed_binding_is_rejected(lambda value: value.update(checked_commit="d" * 40))

    def test_matching_artifacts_with_wrong_source_run_do_not_inherit_operation(self):
        self.assert_changed_binding_is_rejected(
            lambda value: value["recheck_operation"].update(source_run=self.rid + 100))

    def test_sealed_artifact_tamper_fails_closed(self):
        artifact, value = self.successful_recheck()
        value["commands"][0]["exit_code"] = 17
        artifact.write_text(json.dumps(value), encoding="utf-8")
        current = verified(self.data, self.rid)
        self.assertEqual(current["check"], "unknown")
        self.assertFalse(current["verification_current"])
        self.assertTrue(read_status(self.data, self.rid)["can_retry"], "process cleanup remains proven, but this check is untrusted")


if __name__ == "__main__":
    unittest.main()
