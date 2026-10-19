"""Independent regression probes for external candidate trust and evidence.

All mutations use temporary projects. Synthetic verification fixtures exercise
acceptance invalidation only; they are not evidence of real build/test success.
"""
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import agent_api, candidates, preview
from tmh.platform.errors import ApiError
from tmh.platform.operator_access import read_key
from tmh.platform.server import Platform, Req, make_handler
from tmh.platform.store import Store


class ExternalCandidateIndependentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-independent-candidate-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Independent fixture")
        self.git("config", "user.email", "fixture@localhost")
        (self.repo / "app.txt").write_text("baseline\n")
        self.git("add", ".")
        self.git("commit", "-m", "baseline")
        self.base = self.git("rev-parse", "HEAD")
        (self.repo / "app.txt").write_text("candidate\n")
        self.git("commit", "-am", "candidate")
        self.commit = self.git("rev-parse", "HEAD")
        self.P = Platform(self.root / "data", user="fixture-owner")
        self.addCleanup(self.P.store.db.close)
        self.project = self.P.store.add_project("INDEP", "Independent fixture", str(self.repo))
        self.ticket = self.call("ticket_create", {"project": "INDEP", "title": "需求", "body": "必须保留完整验证证据", "request_id": "create"})["ticket"]
        self.args = {"ticket": self.ticket["key"], "base_commit": self.base,
                     "commit": self.commit, "requirement_hash": agent_api._requirement(self.ticket, self.P.store),
                     "criteria": [{"id": "AC1", "text": "业务行为正确", "check": "操作固定版本预览"}],
                     "summary": "独立临时夹具", "request_id": "candidate"}
        self.candidate = self.call("candidate_submit", self.args)
        self.cid = self.candidate["candidate_id"]

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True,
                              check=True, text=True).stdout.strip()

    def call(self, operation, args, agent="implementer", operator=False):
        headers = {"X-Webuddy-Execution": "1"}
        headers.update({"X-Webuddy-Operator": "1"} if operator else {"X-Webuddy-Agent": agent})
        if operator:
            headers["X-Webuddy-Operator-Token"] = read_key(self.P.operator_key_path)
        req = Req(SimpleNamespace(headers=headers), {}, args, "fixture-owner")
        return agent_api.dispatch(self.P, req, operation)

    def synthetic_evidence(self):
        run = self.P.store.run(self.candidate["run_id"])
        verification = {"verification_current": True, "check": "pass", "checked_commit": self.commit,
                        "checked_base": self.base, "checked_diff": run["diff"],
                        "commands": [{"kind": "test", "exit_code": 0, "output": "SYNTHETIC acceptance-boundary fixture"}]}
        pv = {"state": "up", "commit_full": self.commit,
              "prefix": preview.bound_prefix(self.ticket["key"], self.commit)}
        for target, value in (("tmh.platform.fixloop.verified", verification), ("tmh.platform.preview.status", pv)):
            mock = patch(target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        return verification, pv

    def accept_synthetic_candidate(self):
        self.synthetic_evidence()
        view = candidates.view(self.P, self.cid)
        view = self.call("candidate_assess", {"candidate_id": self.cid, "verification_hash": view["verification_hash"],
            "preview_hash": view["preview_hash"],
            "results": [{"id": "AC1", "status": "pass", "evidence": "SYNTHETIC fixture, not actual business acceptance"}],
            "note": "状态边界夹具", "request_id": "assessment"}, agent="reviewer")
        view = self.call("candidate_decide", {"candidate_id": self.cid, "evidence_hash": view["evidence_hash"],
            "decision": "accept", "note": "isolated fixture operator", "request_id": "decision"}, operator=True)
        self.assertTrue(view["human_accepted"])
        return view

    def test_shared_agent_credential_cannot_become_operator_by_adding_headers(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.P, token="fixture-shared-agent-token"))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join, 3)
        self.addCleanup(server.shutdown)
        view = candidates.view(self.P, self.cid)
        connection = http.client.HTTPConnection(*server.server_address, timeout=3)
        self.addCleanup(connection.close)
        connection.request("POST", "/api/agent/candidate_decide", json.dumps({
            "candidate_id": self.cid, "evidence_hash": view["evidence_hash"], "decision": "reject",
            "note": "caller only holds the shared agent token", "request_id": "forged-operator"}),
            {"Content-Type": "application/json", "X-TMH": "1", "X-TMH-Token": "fixture-shared-agent-token",
             "X-Webuddy-Operator": "1", "X-TMH-User": "forged-human"})
        response = connection.getresponse()
        body = json.loads(response.read())
        self.assertEqual(response.status, 403, "shared agent credentials must not record a human decision: " + json.dumps(body, ensure_ascii=False))
        self.assertEqual(self.P.store.q("SELECT * FROM candidate_decisions"), [])

    def test_preview_command_change_invalidates_previous_acceptance(self):
        self.accept_synthetic_candidate()
        preview.set_conf(self.P.data_dir, self.project["key"], "python different_app.py {port}", by="fixture-owner")
        current = candidates.view(self.P, self.cid)
        self.assertFalse(current["human_accepted"], "changed application launch configuration must not reuse previous acceptance")
        self.assertFalse(current["technical_acceptance"])

    def test_new_requirement_message_invalidates_existing_acceptance(self):
        self.accept_synthetic_candidate()
        self.call("message_send", {"ticket": self.ticket["key"], "body": "补充需求：筛选必须保留刷新后的状态", "request_id": "requirement-change"})
        current = candidates.view(self.P, self.cid)
        self.assertFalse(current["current"])
        self.assertFalse(current["human_accepted"])
        self.assertFalse(current["technical_acceptance"])

    def test_same_implementer_cannot_record_independent_assessment(self):
        self.synthetic_evidence()
        view = candidates.view(self.P, self.cid)
        with self.assertRaises(ApiError) as caught:
            self.call("candidate_assess", {"candidate_id": self.cid, "verification_hash": view["verification_hash"],
                "preview_hash": view["preview_hash"],
                "results": [{"id": "AC1", "status": "pass", "evidence": "self attestation"}],
                "note": "same implementer", "request_id": "self-review"})
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.P.store.q("SELECT * FROM candidate_assessments"), [])

    def test_explicit_ticket_baseline_cannot_be_replaced_by_older_ancestor(self):
        # A ticket pinned to the candidate-era baseline must not silently
        # produce a new implementation that omitted that already-required code.
        current = self.P.store.ticket(self.ticket["id"])
        self.P.store.x("UPDATE tickets SET links=? WHERE id=?",
                      (json.dumps(dict(current["links"], base=self.commit)), current["id"]))
        fresh = self.P.store.ticket(current["id"])
        args = dict(self.args, requirement_hash=agent_api._requirement(fresh, self.P.store), request_id="wrong-base")
        with self.assertRaises(ApiError) as caught:
            self.call("candidate_submit", args)
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(len(self.P.store.q("SELECT * FROM code_candidates")), 1)

    def test_restarting_candidate_preview_preserves_previous_raw_log(self):
        preview.set_conf(self.P.data_dir, self.project["key"], "python fixture.py {port}", by="fixture-owner")
        # The Git checkout and log files are real, while process launch/watch is
        # intentionally replaced; this test is about lossless artifact storage.
        real_popen = subprocess.Popen
        def launch(command, *args, **kwargs):
            if isinstance(command, str):
                return SimpleNamespace(pid=999999)
            return real_popen(command, *args, **kwargs)
        with patch("tmh.platform.preview.subprocess.Popen", side_effect=launch), \
                patch("tmh.platform.preview.threading.Thread.start"), \
                patch("tmh.platform.preview._alive", return_value=False):
            first = preview.start(self.P, self.project, self.ticket, self.commit,
                                  "agent:reviewer", expected_commit=self.commit)
            first_log = Path(first["log"])
            original = first_log.read_bytes() + b"first preview evidence\x00\xff\n"
            first_log.write_bytes(original)
            second = preview.start(self.P, self.project, self.ticket, self.commit,
                                   "agent:reviewer", expected_commit=self.commit)
        self.assertEqual(first_log.read_bytes(), original, "restarting must preserve every byte of the original preview log")
        self.assertNotEqual(first["log"], second["log"])

    def test_other_process_closing_ticket_during_submission_cannot_be_reopened(self):
        # A second connection models another server process: the in-process
        # Store RLock must not be mistaken for a cross-process transaction.
        other = Store(self.P.store.path)
        self.addCleanup(other.db.close)
        actual_git = candidates._git
        closed = []
        def close_after_ref(root, *args, **kw):
            result = actual_git(root, *args, **kw)
            if args[0] == "update-ref":
                other.x("UPDATE tickets SET status='closed' WHERE id=?", (self.ticket["id"],))
                closed.append(True)
            return result
        args = dict(self.args, request_id="concurrent-close", criteria=[
            {"id": "AC2", "text": "different candidate fingerprint", "check": "race fixture"}])
        with patch("tmh.platform.candidates._git", side_effect=close_after_ref):
            with self.assertRaises(ApiError):
                self.call("candidate_submit", args)
        self.assertTrue(closed, "fixture did not close the ticket during candidate preparation")
        self.assertEqual(self.P.store.ticket(self.ticket["id"])["status"], "closed")
        self.assertEqual(len(self.P.store.q("SELECT * FROM code_candidates")), 1)

    def test_preview_restart_invalidates_previous_technical_observations(self):
        _, state = self.synthetic_evidence()
        view = candidates.view(self.P, self.cid)
        self.call("candidate_assess", {"candidate_id": self.cid, "verification_hash": view["verification_hash"],
            "preview_hash": view["preview_hash"],
            "results": [{"id": "AC1", "status": "pass", "evidence": "SYNTHETIC first preview process"}],
            "note": "first preview only", "request_id": "before-restart"}, agent="reviewer")
        self.assertTrue(candidates.view(self.P, self.cid)["technical_acceptance"])
        state.update(pid=999998, log="different-preserved-process.log", started="later")
        current = candidates.view(self.P, self.cid)
        self.assertFalse(current["technical_acceptance"])
        self.assertFalse(current["ready_for_human"])
        self.assertNotEqual(current["preview_hash"], view["preview_hash"])


if __name__ == "__main__":
    unittest.main()
