"""Real Git objects with synthetic DB reviews exercise candidate provenance and recovery.

Composition reuses DeliveryTest's fixture helpers without inheriting its test cases.
No model calls, browser data, customer data or actual human approvals are involved.
"""
import copy
import json
import unittest

from tests import test_delivery as helpers
from tmh.platform import delivery
from tmh.platform.agents import git


class DeliverySourceTest(unittest.TestCase):
    def setUp(self):
        self.f = helpers.DeliveryTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.did = self.f.plan_ready()
        self.plan = self.f.rows(self.did)["develop"]["artifact"]["source_run"]
        self.fix = self.f.collected(self.did, "develop", "fix")
        self.repo, self.commit = self.f.adopt_fixture(self.fix)
        self.f.review(self.did, "develop")
        git(self.repo, "branch", "fixture", self.commit)
        git(self.repo, "switch", "-qc", "main", self.commit + "^")

    def row(self, stage="quality"):
        return self.f.rows(self.did)[stage]

    def run_with_receipt(self, stage="quality"):
        rid = self.f.start(self.did, stage)
        self.f.finish(rid, result="SYNTHETIC inspection output")
        source = copy.deepcopy(self.row(stage)["source"])
        path = self.f.data / "runs" / str(rid) / "source.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        receipt = {"schema": 1, "binding": source, "actual_commit": source["commit"],
                   "after_commit": source["commit"], "code_unchanged": True,
                   "notice": "SYNTHETIC receipt for controller regression"}
        path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertTrue(self.row(stage)["runs"][0]["can_collect"])
        return rid, path, receipt

    def reviewed_inspection(self, stage="quality"):
        rid, path, receipt = self.run_with_receipt(stage)
        self.f.act(self.did, "collect", stage, run_id=rid)
        self.f.review(self.did, stage)
        self.assertEqual(self.row(stage)["state"], "approved")
        return rid, path, receipt

    def commit_file(self, content, message):
        (self.repo / "app.py").write_text(content, encoding="utf-8")
        git(self.repo, "add", "app.py")
        git(self.repo, "-c", "user.name=fixture", "-c", "user.email=fixture@localhost", "commit", "-qm", message)
        return git(self.repo, "rev-parse", "HEAD").strip()

    def test_main_branch_movement_and_later_ordinary_plan_do_not_replace_source(self):
        expected = self.row()["source"]
        self.assertEqual(expected["commit"], self.commit)
        main = self.commit_file("unrelated main version\n", "move main")
        git(self.repo, "branch", "-f", "fixture", main)
        ticket = self.f.store.ticket(delivery.view(self.f.P, self.did)["delivery"]["ticket_id"])
        extra = self.f.store.create_run(ticket["project_id"], ticket["id"], "local-test", "plan", "SYNTHETIC", "unreviewed")
        self.f.finish(extra["id"], result="NEW WRONG PLAN")
        self.assertEqual(self.row()["source"], expected)
        for stage in ("quality", "security"):
            rid, _, _ = self.run_with_receipt(stage)
            packet = self.f.P.runner.calls[-1]["ticket"]["links"]["delivery_source"]
            self.assertEqual(packet, expected)
            self.f.act(self.did, "collect", stage, run_id=rid)
        bound = delivery.signoff_binding(self.f.data, ticket["key"])
        self.assertEqual((bound["plan_run"], bound["fix_run"], bound["commit"]), (self.plan, self.fix, self.commit))
        self.assertFalse(bound["valid"], "Collected output is not a reviewed or customer-accepted result")

    def test_missing_receipt_blocks_collection_but_permits_rerun(self):
        rid, path, _ = self.run_with_receipt()
        path.unlink()
        self.f.assert_error(409, self.f.act, self.did, "collect", "quality", run_id=rid)
        self.assertTrue(self.row()["can_start"], "A done run with missing provenance must not deadlock collect and retry")
        self.assertFalse(self.row()["runs"][0]["can_collect"])
        self.assertTrue(self.row()["runs"][0]["collect_blocked"])
        self.assertIsNone(self.row()["artifact"])

    def test_malformed_or_mismatched_receipts_never_collect(self):
        rid, path, receipt = self.run_with_receipt()
        invalid = [b"not JSON", b"[]", b"null", json.dumps({**receipt, "code_unchanged": False}).encode(),
                   json.dumps({**receipt, "actual_commit": "0" * 40}).encode(),
                   json.dumps({**receipt, "binding": {**receipt["binding"], "plan_run": 999}}).encode()]
        for raw in invalid:
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                self.f.assert_error(409, self.f.act, self.did, "collect", "quality", run_id=rid)
                self.assertFalse(self.row()["runs"][0]["can_collect"])
                self.assertIsNone(self.row()["artifact"])
        path.write_text(json.dumps(receipt), encoding="utf-8")
        self.f.act(self.did, "collect", "quality", run_id=rid)
        self.assertEqual(self.row()["artifact"]["source_run"], rid)
        self.assertFalse(self.row()["runs"][0]["can_collect"], "Already collected output must not offer a second collection")

    def test_invalid_utf8_receipt_is_reported_as_missing_evidence_not_page_error(self):
        rid, path, _ = self.run_with_receipt()
        path.write_bytes(b"\xff\xfe corrupt source receipt")
        self.f.assert_error(409, self.f.act, self.did, "collect", "quality", run_id=rid)
        self.assertIsNone(self.row()["artifact"])

    def test_reviewing_implementation_again_does_not_resurrect_quality_review(self):
        rid, _, _ = self.reviewed_inspection()
        old = self.row()["source"]
        self.f.review(self.did, "develop")
        row = self.row()
        self.assertNotEqual(row["source"]["implementation_review"], old["implementation_review"])
        self.assertIsNone(row["review"])
        self.assertFalse(row["can_review"], "The old run inspected a different review identity")
        self.assertTrue(row["can_start"])
        self.assertEqual(row["artifact"]["source_run"], rid)
        self.assertFalse(row["runs"][0]["can_collect"])
        self.f.assert_error(409, self.f.review, self.did, "quality")
        self.reviewed_inspection()

    def test_rechecked_implementation_requires_new_inspection_after_rereview(self):
        self.reviewed_inspection()
        path = self.f.data / "runs" / str(self.fix) / "verify.json"
        verify = json.loads(path.read_text())
        verify["commands"][0]["output"] = "new real check output in synthetic unit fixture"
        path.write_text(json.dumps(verify))
        self.assertIsNone(self.row()["review"])
        self.assertFalse(self.row()["can_start"])
        self.f.review(self.did, "develop")
        self.assertIsNone(self.row()["review"])
        self.assertFalse(self.row()["can_review"])
        self.assertTrue(self.row()["can_start"])

    def test_missing_legacy_fix_binding_never_falls_back_to_latest_plan(self):
        self.f.store.x("UPDATE delivery_runs SET binding='{}' WHERE run_id=?", (self.fix,))
        self.f.review(self.did, "develop")
        row = self.row()
        self.assertEqual(row["source"], {})
        self.assertFalse(row["can_start"])
        self.assertIn("固定记录", "；".join(row["run_blocked"]))

    def test_old_database_without_binding_is_read_conservatively_then_migrated(self):
        self.f.store.x("ALTER TABLE delivery_runs DROP COLUMN binding")
        ticket = self.f.store.ticket(delivery.view(self.f.P, self.did)["delivery"]["ticket_id"])
        before = {r["name"] for r in self.f.store.db.execute("PRAGMA table_info(delivery_runs)")}
        self.assertNotIn("binding", before)
        bound = delivery.signoff_binding(self.f.data, ticket["key"])
        self.assertFalse(bound["valid"])
        self.assertIsNone(bound["plan_run"])
        after = {r["name"] for r in self.f.store.db.execute("PRAGMA table_info(delivery_runs)")}
        self.assertEqual(before, after, "Read-only signoff lookup must not migrate the database")
        self.f.store._delivery_ready = False
        self.assertFalse(self.row()["can_start"])
        self.assertIn("binding", {r["name"] for r in self.f.store.db.execute("PRAGMA table_info(delivery_runs)")})

    def test_failed_inspection_can_retry_without_reviewing_old_output(self):
        rid = self.f.start(self.did, "quality")
        self.f.finish(rid, status="failed", exit_code=1, result="SYNTHETIC actual check failure")
        self.assertTrue(self.row()["can_start"])
        self.assertFalse(self.row()["can_review"])
        self.run_with_receipt()

    def test_hex_named_refs_cannot_shadow_the_stored_commit(self):
        wrong = self.commit_file("wrong branch contents\n", "unrelated")
        for name in (self.commit[:12], self.commit):
            git(self.repo, "branch", name, wrong)
        self.f.store.update_run(self.fix, decision="accepted:fixture@" + self.commit[:12])
        self.assertEqual(self.row()["source"]["commit"], self.commit)

    def test_nondict_verification_blocks_instead_of_crashing(self):
        path = self.f.data / "runs" / str(self.fix) / "verify.json"
        path.write_text('["corrupt verification"]', encoding="utf-8")
        self.assertFalse(self.row()["can_start"])
        self.assertIsNone(self.row()["review"])


if __name__ == "__main__":
    unittest.main()
