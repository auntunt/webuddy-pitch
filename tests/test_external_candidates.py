"""External commits traverse real isolated verification before acceptance."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import agent_api, candidates
from tmh.platform.errors import ApiError
from tmh.platform.server import Platform, Req


class ExternalCandidateTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="webuddy-candidate-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@localhost")
        (self.repo / "app.py").write_text("VALUE = 1\n")
        (self.repo / ".gitignore").write_text("__pycache__/\n")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/test_app.py").write_text("import unittest\nfrom app import VALUE\nclass Test(unittest.TestCase):\n def test_value(self): self.assertIn(VALUE, (1, 2))\n")
        (self.repo / ".tmh").mkdir()
        (self.repo / ".tmh/config.json").write_text(json.dumps({"commands": {
            "build": sys.executable + " -m py_compile app.py", "test": sys.executable + " -m unittest discover -s tests -v"}}))
        self.git("add", ".")
        self.git("commit", "-m", "baseline")
        self.base = self.git("rev-parse", "HEAD")
        (self.repo / "app.py").write_text("VALUE = 2\n")
        self.git("commit", "-am", "candidate")
        self.sha = self.git("rev-parse", "HEAD")
        self.P = Platform(self.root / "data", user="fixture-human")
        self.addCleanup(self.P.store.db.close)
        self.p = self.P.store.add_project("EXT", "Fixture", str(self.repo))
        self.ticket = self.call("ticket_create", {"project": "EXT", "title": "Use value 2", "body": "Use value 2 and preserve the test.", "request_id": "create"})["ticket"]
        self.criteria = [{"id": "A1", "text": "Value 2 is returned", "check": "Read the app and run its test"}]

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True).stdout.strip()

    def call(self, op, args, actor="writer", operator=False):
        headers = {"X-Webuddy-Execution": "1"}
        headers.update({"X-Webuddy-Operator": "1"} if operator else {"X-Webuddy-Agent": actor})
        if operator:
            from tmh.platform.operator_access import read_key
            headers["X-Webuddy-Operator-Token"] = read_key(self.P.operator_key_path)
        return agent_api.dispatch(self.P, Req(SimpleNamespace(headers=headers), {}, args, "fixture-human"), op)

    def submit(self, **kw):
        packet = self.call("ticket_get", {"ticket": self.ticket["key"]})
        args = {"ticket": self.ticket["key"], "base_commit": self.base, "commit": self.sha,
                "requirement_hash": packet["requirement_hash"], "criteria": self.criteria,
                "summary": "External fixture implementation", "request_id": "submit"}
        args.update(kw)
        return self.call("candidate_submit", args)

    def verify(self, cid, req="verify"):
        r = self.call("candidate_verify", {"candidate_id": cid, "request_id": req})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            op = self.P.flow.rechecks.status(r["run"])
            if op and not op["running"]:
                return candidates.view(self.P, cid)
            time.sleep(.02)
        self.fail("verification did not finish")

    def preview(self):
        from tmh.platform.preview import bound_prefix
        return patch("tmh.platform.preview.status", return_value={"state": "up", "commit_full": self.sha,
                   "prefix": bound_prefix(self.ticket["key"], self.sha)})

    def assess(self, cid, v, **kw):
        v = candidates.view(self.P, cid)
        args = {"candidate_id": cid, "verification_hash": v["verification_hash"], "results": [{"id": "A1", "status": "pass", "evidence": "Independent fixture check of VALUE and test output"}], "note": "Technical fixture only", "request_id": "assess"}
        args["preview_hash"] = v["preview_hash"]
        args.update(kw)
        return self.call("candidate_assess", args, actor="reviewer")

    def test_submit_is_immutable_deduplicated_and_never_adopted(self):
        a = self.submit()
        self.assertEqual(self.submit(), a)
        reused = self.submit(request_id="same-intent-new-id")
        self.assertEqual(reused["candidate_id"], a["candidate_id"])
        run = self.P.store.run(a["run_id"])
        self.assertEqual(run["agent"], "external:writer")
        self.assertEqual(run["decision"], "")
        self.assertEqual(self.P.store.q("SELECT * FROM verification_operations"), [])
        row = candidates._row(self.P, a["candidate_id"])
        self.assertEqual(self.git("rev-parse", row["ref"]), self.sha)
        self.assertTrue((Path(row["artifact_dir"]) / "change.patch").read_bytes())
        self.assertFalse(candidates.view(self.P, row["id"])["ready_for_human"])
        with self.assertRaises(ValueError):
            self.P.runner.decide(run["id"], "accept", "fixture-human")

    def test_real_verification_binds_full_candidate_and_preserves_run(self):
        a = self.submit(); before = self.P.store.run(a["run_id"])
        v = self.verify(a["candidate_id"])
        self.assertTrue(v["verification_passed"], v["verification"])
        self.assertEqual(v["verification"]["checked_commit"], self.sha)
        self.assertEqual(v["verification"]["checked_base"], self.base)
        self.assertEqual(self.P.store.run(a["run_id"]), before)
        self.assertFalse(v["human_accepted"])

    def test_failed_test_does_not_enable_preview_or_acceptance(self):
        (self.repo / "app.py").write_text("VALUE = 999\n")
        self.git("commit", "-am", "broken candidate")
        self.sha = self.git("rev-parse", "HEAD")
        a = self.submit(); v = self.verify(a["candidate_id"])
        self.assertFalse(v["verification_passed"])
        self.assertEqual(v["verification"]["check"], "fail")
        with patch("tmh.platform.preview.start") as start, self.assertRaises(ApiError):
            self.call("candidate_preview", {"candidate_id": a["candidate_id"], "request_id": "preview"})
        start.assert_not_called()

    def test_changed_requirement_rejects_submission_without_unknown_lock(self):
        packet = self.call("ticket_get", {"ticket": self.ticket["key"]})
        self.call("message_send", {"ticket": self.ticket["key"], "body": "new requirement", "request_id": "m"})
        with self.assertRaises(ApiError):
            self.submit(requirement_hash=packet["requirement_hash"])
        self.assertEqual(self.call("request_get", {"request_id": "submit"})["state"], "failed")
        self.assertTrue(self.submit(request_id="fresh")["candidate_id"])

    def test_human_decision_is_separate_and_stale_after_new_verification(self):
        a = self.submit(); cid = a["candidate_id"]; v = self.verify(cid)
        with self.preview():
            v = self.assess(cid, v)
            self.assertTrue(v["ready_for_human"], v)
            args = {"candidate_id": cid, "evidence_hash": v["evidence_hash"], "decision": "accept", "note": "Synthetic human acceptance fixture", "request_id": "approve"}
            with self.assertRaises(ApiError) as e:
                self.call("candidate_decide", args)
            self.assertEqual(e.exception.code, 403)
            approved = self.call("candidate_decide", args, operator=True)
            self.assertTrue(approved["human_accepted"])
            self.assertEqual(approved["human_decision"]["author"], "operator:fixture-human")
            self.verify(cid, "verify-new")
            after = candidates.view(self.P, cid)
            self.assertFalse(after["human_accepted"])
            self.assertFalse(after["technical_acceptance"])
            self.assertEqual(after["human_decision"], approved["human_decision"])

    def test_assessment_cannot_skip_criteria_or_self_review(self):
        a = self.submit(); cid = a["candidate_id"]; v = self.verify(cid)
        with self.preview():
            with self.assertRaises(ApiError):
                self.assess(cid, v, results=[{"id": "wrong", "status": "pass", "evidence": "fixture"}])
            args = {"candidate_id": cid, "verification_hash": v["verification_hash"], "results": [{"id": "A1", "status": "pass", "evidence": "fixture"}], "note": "fixture", "request_id": "self-review"}
            with self.assertRaises(ApiError):
                self.call("candidate_assess", args)
            self.assertFalse(candidates.view(self.P, cid)["technical_acceptance"])

    def test_stopped_preview_never_counts_as_ready(self):
        a = self.submit(); cid = a["candidate_id"]; v = self.verify(cid)
        with self.preview():
            self.assess(cid, v)
        with patch("tmh.platform.preview.status", return_value={"state": "stopped", "commit_full": self.sha, "prefix": "/pv/EXT-1/__commit/" + self.sha}):
            after = candidates.view(self.P, cid)
            self.assertFalse(after["preview_ready"])
            self.assertFalse(after["ready_for_human"])

    def test_preview_link_enters_authenticated_workbench_before_preview_port(self):
        a = self.submit()
        self.P.preview_port = 8793
        self.P.public_url = "https://workbench.example"
        with self.preview():
            value = candidates.view(self.P, a["candidate_id"])
        self.assertEqual(value["preview_url"], "https://workbench.example" + value["preview_entry_path"])
        self.assertEqual(value["preview_entry_path"], "/pv/EXT-1/__commit/" + self.sha + "/")
        self.assertNotIn("8793", value["preview_url"])

    def test_comment_after_assessment_invalidates_old_approval_package(self):
        a = self.submit(); cid = a["candidate_id"]; v = self.verify(cid)
        with self.preview():
            assessed = self.assess(cid, v)
            self.call("message_send", {"ticket": self.ticket["key"], "body": "changed criterion", "request_id": "new-request"})
            self.assertFalse(candidates.view(self.P, cid)["current"])
            with self.assertRaises(ApiError):
                self.call("candidate_decide", {"candidate_id": cid, "evidence_hash": assessed["evidence_hash"], "decision": "accept", "note": "fixture", "request_id": "stale-approve"}, operator=True)

    def test_moved_candidate_ref_is_blocked_without_replacement(self):
        a = self.submit(); row = candidates._row(self.P, a["candidate_id"])
        self.git("update-ref", row["ref"], self.base)
        self.assertFalse(candidates.view(self.P, row["id"])["current"])
        with self.assertRaises(ApiError):
            self.call("candidate_verify", {"candidate_id": row["id"], "request_id": "verify"})

    def test_agent_names_are_not_human_reviewers(self):
        from tmh.platform.signoff import human
        self.assertFalse(human("agent:codex"))
        self.assertFalse(human("external:writer"))
        self.assertTrue(human("Actual operator"))


if __name__ == "__main__":
    unittest.main()
