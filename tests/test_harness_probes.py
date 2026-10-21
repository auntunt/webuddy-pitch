"""Real HTTP/SQLite probe and durable acceptance gates, with fixed app snapshots."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import agent_api, candidates, harness_probes
from tmh.platform.errors import ApiError
from tmh.platform.server import Platform, Req


FIXTURE = Path(__file__).parent / "fixtures/bootv2-search/app.py"


class HarnessProbeTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="webuddy-harness-probe-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Probe fixture")
        self.git("config", "user.email", "fixture@localhost")
        original = FIXTURE.read_text()
        self.assertIn("if keyword in text.casefold()", original)
        (self.repo / "app.py").write_text(original.replace("if keyword in text.casefold()", "if True"))
        (self.repo / "project.json").write_text('{"name":"Probe fixture"}')
        (self.repo / ".gitignore").write_text("__pycache__/\napp.db\n")
        (self.repo / ".tmh").mkdir()
        # Deliberately green tests that do NOT check business behavior. The
        # independent recipe must distinguish the wrong and right app anyway.
        (self.repo / ".tmh/config.json").write_text(json.dumps({"commands": {
            "build": sys.executable + " -m py_compile app.py",
            "test": sys.executable + ' -c "print(\'generic tests passed\')"'}}))
        self.git("add", ".")
        self.git("commit", "-m", "renders filters but ignores keywords")
        self.base = self.git("rev-parse", "HEAD")
        (self.repo / "app.py").write_text(original)
        self.git("commit", "-am", "apply keyword filter")
        self.commit = self.git("rev-parse", "HEAD")
        (self.repo / "app.db").write_bytes(b"original user data, do not touch")
        self.P = Platform(self.root / "data", user="fixture-human")
        self.addCleanup(self.P.store.db.close)
        self.P.store.add_project("PROBE", "Probe fixture", str(self.repo))
        self.ticket = self.call("ticket_create", {"project": "PROBE", "title": "Search and filter", "body": "Keep existing editing and persistence.", "request_id": "create"})["ticket"]
        self.criteria = [{"id": k, "text": v, "check": "Run independent HTTP and SQLite probe"}
                         for k, v in harness_probes.recipes()[0]["checks"].items()]

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.DEVNULL, text=True).strip()

    def call(self, op, args, actor="writer", execution=True):
        headers = {"X-Webuddy-Agent": actor}
        if execution:
            headers["X-Webuddy-Execution"] = "1"
        return agent_api.dispatch(self.P, Req(SimpleNamespace(headers=headers), {}, args, "fixture-human"), op)

    def prepare(self):
        packet = self.call("ticket_get", {"ticket": self.ticket["key"]})
        candidate = self.call("candidate_submit", {"ticket": self.ticket["key"], "base_commit": self.base,
            "commit": self.commit, "requirement_hash": packet["requirement_hash"], "criteria": self.criteria,
            "summary": "Synthetic fixture; generic tests intentionally omit behavior", "request_id": "submit"})
        self.cid = candidate["candidate_id"]
        self.call("candidate_verify", {"candidate_id": self.cid, "request_id": "verify"})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = candidates.view(self.P, self.cid)
            if state["verification_passed"]:
                return state
            time.sleep(.02)
        self.fail("independent generic build/test did not pass")

    def start(self, request="probe"):
        return self.call("harness_probe_start", {"candidate_id": self.cid,
            "recipe": "bootv2-items-search-v1", "request_id": request})["probe_id"]

    def finish(self, pid):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = self.call("harness_probe_get", {"probe_id": pid})
            if not state["running"]:
                return state
            time.sleep(.03)
        self.fail("probe did not finish")

    def preview(self):
        from tmh.platform.preview import bound_prefix
        return patch("tmh.platform.preview.status", return_value={"state": "up", "commit_full": self.commit,
            "prefix": bound_prefix(self.ticket["key"], self.commit)})

    def assess(self, request):
        state = candidates.view(self.P, self.cid)
        return self.call("candidate_assess", {"candidate_id": self.cid,
            "verification_hash": state["verification_hash"], "preview_hash": state["preview_hash"],
            "results": [{"id": c["id"], "status": "pass", "evidence": "Independent synthetic observation"} for c in self.criteria],
            "note": "Fixture only, not human acceptance", "request_id": request}, actor="independent")

    def test_real_probe_distinguishes_behavior_with_both_generic_tests_green(self):
        self.prepare()
        before = self.P.store.run(candidates._row(self.P, self.cid)["run_id"])
        result = self.finish(self.start())
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["result"]["comparison"], "improved")
        self.assertEqual(result["result"]["improved_checks"], ["A1", "A2"])
        self.assertTrue(result["cleanup_complete"])
        self.assertEqual((self.repo / "app.db").read_bytes(), b"original user data, do not touch")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.P.store.run(before["id"]), before)
        memory = self.call("harness_library", {"project": "PROBE"})
        self.assertEqual(memory["entries"][0]["commit"], self.commit)
        self.assertFalse(memory["automatic_policy_changes"])
        self.assertEqual(self.call("ticket_get", {"ticket": self.ticket["key"]})["harness_library"], memory)

    def test_probe_invalidates_previous_assessment_then_requires_new_observations(self):
        self.prepare()
        with self.preview():
            previous = self.assess("before")
            self.assertTrue(previous["technical_acceptance"])
            pid = self.start()
            self.assertFalse(candidates.view(self.P, self.cid)["technical_acceptance"])
            result = self.finish(pid)
            self.assertTrue(result["passed"], result)
            self.assertFalse(candidates.view(self.P, self.cid)["technical_acceptance"])
            self.assertNotEqual(previous["verification_hash"], candidates.view(self.P, self.cid)["verification_hash"])
            self.assertTrue(self.assess("after")["technical_acceptance"])
            self.assertFalse(candidates.view(self.P, self.cid)["human_accepted"])

    def test_bad_behavior_cannot_be_bypassed_by_green_tests_or_self_reported_pass(self):
        (self.repo / "app.py").write_text(FIXTURE.read_text().replace("if keyword in text.casefold()", "if True") + "\n# broken candidate\n")
        self.git("commit", "-am", "regress literal search")
        self.commit = self.git("rev-parse", "HEAD")
        self.prepare()
        result = self.finish(self.start())
        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "done", result)
        self.assertEqual(result["result"]["arms"]["candidate"]["process"]["exit_code"], 0)
        self.assertIn("fail", [r["status"] for r in result["result"]["arms"]["candidate"]["results"]])
        with self.preview():
            self.assertFalse(self.assess("unfounded-claim")["technical_acceptance"])
        self.assertEqual(self.call("harness_library", {"project": "PROBE"})["entries"], [])

    def test_tampered_evidence_and_changed_recipe_invalidate_current_gate(self):
        self.prepare()
        pid = self.start()
        result = self.finish(pid)
        self.assertTrue(result["passed"])
        recipe = harness_probes.recipes()[0]
        with patch.object(harness_probes, "recipes", return_value=[dict(recipe, version="0" * 64)]):
            self.assertFalse(harness_probes.view(self.P, pid)["passed"])
        report = harness_probes.folder(self.P, pid) / "candidate/observations/report.json"
        report.write_text(report.read_text() + " ")
        after = harness_probes.view(self.P, pid)
        self.assertFalse(after["passed"])
        self.assertTrue(any("证据" in why for why in after["blocked"]))

    def test_execution_permission_recipe_scope_and_replay(self):
        self.prepare()
        args = {"candidate_id": self.cid, "recipe": "bootv2-items-search-v1", "request_id": "probe"}
        with self.assertRaises(ApiError) as error:
            self.call("harness_probe_start", args, execution=False)
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(ApiError):
            self.call("harness_probe_start", dict(args, recipe="arbitrary.py", request_id="bad"))
        first = self.call("harness_probe_start", args)
        self.assertEqual(self.call("harness_probe_start", args), first)
        self.finish(first["probe_id"])
        self.assertEqual(len(self.P.store.q("SELECT * FROM harness_probe_runs")), 1)

    def test_total_timeout_returns_unknown_and_reaps_processes(self):
        (self.repo / "app.py").write_text("import time\ntime.sleep(60)\n")
        self.git("commit", "-am", "never ready")
        self.commit = self.git("rev-parse", "HEAD")
        self.prepare()
        with patch.object(harness_probes, "TOTAL_SECONDS", .8):
            result = self.finish(self.start())
        self.assertFalse(result["passed"])
        self.assertTrue(result["cleanup_complete"], result)
        self.assertEqual(result["result"]["comparison"], "unknown")
        self.assertTrue(any(arm["process"]["reason"] == "timeout" for arm in result["result"]["arms"].values()))

    def test_explicit_stop_prevents_duplicate_and_preserves_partial_evidence(self):
        (self.repo / "app.py").write_text("import time\ntime.sleep(60)\n")
        self.git("commit", "-am", "slow candidate")
        self.commit = self.git("rev-parse", "HEAD")
        self.prepare()
        pid = self.start()
        with self.assertRaises(ApiError):
            self.start("duplicate")
        stopped = self.call("harness_probe_cancel", {"probe_id": pid, "request_id": "stop"})
        self.assertTrue(stopped["stop_requested"])
        result = self.finish(pid)
        self.assertFalse(result["passed"])
        self.assertTrue((harness_probes.folder(self.P, pid) / "cancel.json").is_file())


if __name__ == "__main__":
    unittest.main()
