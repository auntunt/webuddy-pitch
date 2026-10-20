"""Independent probe boundaries; temporary Git fixtures, never real app data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import agent_api, candidates, harness_probes
from tmh.platform.errors import ApiError
from tmh.platform.server import Platform, Req
from tmh.platform.store import Store
from tmh.platform.supervised_process import run_supervised


class HarnessProbeIndependentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="webuddy-probe-independent-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Probe independent fixture")
        self.git("config", "user.email", "fixture@localhost")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True,
                              text=True, check=True).stdout.strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-m", "independent fixture")
        return self.git("rev-parse", "HEAD")

    def call(self, operation, args, platform=None):
        req = Req(SimpleNamespace(headers={"X-Webuddy-Agent": "independent-fixture",
                                          "X-Webuddy-Execution": "1"}), {}, args, "fixture-owner")
        return agent_api.dispatch(platform or self.P, req, operation)

    def prepare_candidate(self):
        (self.repo / "app.py").write_bytes((Path(__file__).parent / "fixtures/bootv2-search/app.py").read_bytes())
        (self.repo / "project.json").write_text('{"name":"Independent fixture"}')
        (self.repo / ".gitignore").write_text("__pycache__/\n")
        (self.repo / ".tmh").mkdir()
        (self.repo / ".tmh/config.json").write_text(json.dumps({"commands": {
            "build": sys.executable + " -m py_compile app.py",
            "test": sys.executable + " -m py_compile app.py"}}))
        base = self.commit()
        with (self.repo / "app.py").open("a") as stream:
            stream.write("\n# Separate immutable candidate for lifecycle testing.\n")
        commit = self.commit()
        self.P = Platform(self.root / "data", user="fixture-owner")
        self.addCleanup(self.P.store.db.close)
        self.P.store.add_project("INDEP", "Independent fixture", str(self.repo))
        self.ticket = self.call("ticket_create", {"project": "INDEP", "title": "Search lifecycle",
            "body": "Use the same recipe against both immutable versions", "request_id": "create"})["ticket"]
        packet = self.call("ticket_get", {"ticket": self.ticket["key"]})
        candidate = self.call("candidate_submit", {"ticket": self.ticket["key"], "base_commit": base,
            "commit": commit, "requirement_hash": packet["requirement_hash"],
            "criteria": [{"id": key, "text": value, "check": "Independent recipe"}
                         for key, value in harness_probes.recipes()[0]["checks"].items()],
            "summary": "Isolated lifecycle regression; generic compile is not business validation",
            "request_id": "candidate"})
        self.cid = candidate["candidate_id"]
        self.call("candidate_verify", {"candidate_id": self.cid, "request_id": "verify"})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if candidates.view(self.P, self.cid)["verification_passed"]:
                return
            time.sleep(.02)
        self.fail("real verification fixture did not finish")

    def finish_probe(self, pid):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = harness_probes.view(self.P, pid)
            if not state["running"]:
                return state
            time.sleep(.02)
        self.fail("probe did not finish within independent fixture deadline")

    def test_snapshot_preserves_export_ignored_tracked_source(self):
        (self.repo / ".gitattributes").write_text("runtime.json export-ignore\n")
        source = b'{"search_is_broken": true}\n'
        (self.repo / "runtime.json").write_bytes(source)
        (self.repo / "app.py").write_text("print('read runtime.json in the real worktree')\n")
        sha = self.commit()
        target = self.root / "snapshot"
        harness_probes._snapshot(self.repo, sha, target, 5)
        self.assertTrue((target / "runtime.json").exists(), "probe snapshot omitted tracked runtime source")
        self.assertEqual((target / "runtime.json").read_bytes(), source)

    def test_snapshot_never_expands_export_subst_in_tracked_source(self):
        (self.repo / ".gitattributes").write_text("app.py export-subst\n")
        source = b"VERSION = '$Format:%H$'\n"
        (self.repo / "app.py").write_bytes(source)
        sha = self.commit()
        target = self.root / "snapshot"
        harness_probes._snapshot(self.repo, sha, target, 5)
        self.assertEqual((target / "app.py").read_bytes(), source,
                         "probe must execute the same blob bytes as the fixed candidate")

    def test_optimized_python_cannot_turn_broken_search_into_a_pass(self):
        fixture = Path(__file__).parent / "fixtures/bootv2-search/app.py"
        original = fixture.read_text()
        self.assertIn("if keyword in text.casefold()", original)
        (self.repo / "app.py").write_text(original.replace("if keyword in text.casefold()", "if True"))
        (self.repo / "project.json").write_text('{"name":"Independent broken search"}')

        def run(optimization):
            output = self.root / ("observations-" + optimization)
            process = run_supervised(
                [sys.executable, "-u", str(harness_probes.PROBE), "--root", str(self.repo), "--output", str(output)],
                folder=self.root / ("process-" + optimization),
                owner={"token": "independent-optimized-fixture", "run_id": 1, "data_dir": str(self.root)},
                cwd=self.repo, env=dict(os.environ, PYTHONOPTIMIZE=optimization), timeout=15)
            self.assertTrue(process.cleanup["complete"], process)
            report_path = output / "report.json"
            return process, json.loads(report_path.read_text()) if report_path.exists() else None

        control, control_report = run("0")
        self.assertEqual(control.returncode, 0, control.output)
        self.assertEqual(control_report["setup_error"], "")
        self.assertEqual(control_report["results"][0]["status"], "fail", control_report)
        process, report = run("1")
        accepted = bool(process.returncode == 0 and report and not report["setup_error"]
                        and all(r["status"] == "pass" for r in report["results"]))
        self.assertFalse(accepted, "broken literal search became a false pass under PYTHONOPTIMIZE=1: "
                         + json.dumps(report, ensure_ascii=False))

    def test_timeout_preserves_application_output_without_a_final_newline(self):
        # Readiness succeeds, but the HTTP response never arrives. The app's
        # flushed non-UTF8 tail must survive killing the probe and its child.
        emitted = b"application raw tail \\x00 \\xff without final newline".decode("unicode_escape").encode("latin1")
        (self.repo / "app.py").write_text(
            "import os, socket, time\n"
            "listener=socket.socket()\n"
            "listener.bind(('127.0.0.1',0))\n"
            "listener.listen()\n"
            "print('Ready on http://127.0.0.1:%d' % listener.getsockname()[1], flush=True)\n"
            f"os.write(1, {emitted!r})\n"
            "time.sleep(60)\n")
        output = self.root / "observations"
        process = run_supervised(
            [sys.executable, "-u", str(harness_probes.PROBE), "--root", str(self.repo), "--output", str(output)],
            folder=self.root / "process", owner={"token": "independent-output-fixture", "run_id": 2,
                "data_dir": str(self.root)}, cwd=self.repo, timeout=1)
        self.assertEqual(process.reason, "timeout", process)
        self.assertTrue(process.cleanup["complete"], process)
        logs = list(output.glob("application-*.log"))
        self.assertTrue(logs, "application output evidence is missing")
        retained = b"".join(path.read_bytes() for path in logs)
        self.assertIn(emitted, retained,
                      "complete supervisor cleanup concealed lost application output: %r" % retained)

    def test_second_store_cannot_launch_duplicate_probe(self):
        self.prepare_candidate()
        other_store = Store(self.P.store.path)
        self.addCleanup(other_store.db.close)
        other = SimpleNamespace(**vars(self.P))
        other.store = other_store
        entered, release, exited = threading.Event(), threading.Event(), threading.Event()
        actual = harness_probes._run

        def held_worker(*args):
            entered.set()
            try:
                release.wait(5)
                actual(*args)
            finally:
                exited.set()

        args = {"candidate_id": self.cid, "recipe": "bootv2-items-search-v1", "request_id": "first"}
        with patch.object(harness_probes, "_run", side_effect=held_worker):
            first = self.call("harness_probe_start", args)
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(ApiError) as rejected:
                    self.call("harness_probe_start", dict(args, request_id="second"), platform=other)
                self.assertEqual(rejected.exception.code, 409)
                self.assertEqual(len(other_store.q("SELECT * FROM harness_probe_runs")), 1)
            finally:
                release.set()
                self.assertTrue(exited.wait(20), "first worker did not release its ownership")
        state = harness_probes.view(self.P, first["probe_id"])
        self.assertFalse(state["running"])
        self.assertTrue(state["cleanup_complete"], state)

    def test_requirement_change_at_last_process_completion_blocks_pass(self):
        self.prepare_candidate()
        other_store = Store(self.P.store.path)
        self.addCleanup(other_store.db.close)
        actual = harness_probes.run_supervised
        changed = []

        def finish_then_change(*args, **kwargs):
            result = actual(*args, **kwargs)
            if Path(kwargs["folder"]).parent.name == "candidate":
                other_store.event(self.ticket["id"], "fixture-owner", "comment",
                                  "New requirement after candidate observations, before publication")
                changed.append(True)
            return result

        with patch.object(harness_probes, "run_supervised", side_effect=finish_then_change):
            started = self.call("harness_probe_start", {"candidate_id": self.cid,
                "recipe": "bootv2-items-search-v1", "request_id": "last-moment-change"})
            state = self.finish_probe(started["probe_id"])
        self.assertTrue(changed, "fixture did not exercise the final publication boundary")
        self.assertFalse(state["passed"], "old requirement evidence was published as a current pass")
        self.assertFalse(candidates.view(self.P, self.cid)["current"])
        self.assertTrue(state["cleanup_complete"], state)

    def test_verification_replacement_invalidates_current_pass_but_retains_history(self):
        self.prepare_candidate()
        started = self.call("harness_probe_start", {"candidate_id": self.cid,
            "recipe": "bootv2-items-search-v1", "request_id": "before-verification-change"})
        state = self.finish_probe(started["probe_id"])
        self.assertTrue(state["passed"], state)
        verification = candidates.view(self.P, self.cid)["verification"]
        # This is a version-binding test, not synthetic business validation:
        # real build/test and both business arms have already completed.
        changed = dict(verification, independent_fixture_revision="changed evidence content")
        with patch("tmh.platform.fixloop.verified", return_value=changed):
            candidate = candidates.view(self.P, self.cid)
            self.assertTrue(candidate["verification_passed"])
            self.assertTrue(candidate["current"])
            after = harness_probes.view(self.P, started["probe_id"])
            self.assertFalse(after["passed"])
            self.assertTrue(after["observed_passed"])
            self.assertFalse(after["source_current"])
            self.assertEqual(after["result"], state["result"])
            history = harness_probes.library(self.P, "INDEP")["entries"]
            self.assertEqual(len(history), 1)
            self.assertFalse(history[0]["source_current"])

    def test_legacy_source_without_verification_digest_is_readable_and_stale(self):
        self.prepare_candidate()
        started = self.call("harness_probe_start", {"candidate_id": self.cid,
            "recipe": "bootv2-items-search-v1", "request_id": "legacy-binding"})
        state = self.finish_probe(started["probe_id"])
        self.assertTrue(state["passed"], state)
        legacy = dict(state["source"])
        del legacy["verification_digest"]
        # Model an older durable record explicitly: no final result is claimed.
        self.P.store.x("UPDATE harness_probe_runs SET source=?,result_hash='' WHERE id=?",
                       (json.dumps(legacy), started["probe_id"]))
        after = self.call("harness_probe_get", {"probe_id": started["probe_id"]})
        self.assertFalse(after["passed"])
        self.assertFalse(after["source_current"])
        packet = self.call("ticket_get", {"ticket": self.ticket["key"]})
        self.assertIn("harness_library", packet)

    def test_stop_acknowledged_after_candidate_process_exit_cannot_publish_pass(self):
        self.prepare_candidate()
        actual = harness_probes.run_supervised
        acknowledgements = []

        def finish_then_stop(*args, **kwargs):
            result = actual(*args, **kwargs)
            if Path(kwargs["folder"]).parent.name == "candidate":
                pid = int(Path(kwargs["folder"]).parents[1].name)
                acknowledgements.append(self.call("harness_probe_cancel", {
                    "probe_id": pid, "request_id": "stop-before-publication"}))
            return result

        with patch.object(harness_probes, "run_supervised", side_effect=finish_then_stop):
            started = self.call("harness_probe_start", {"candidate_id": self.cid,
                "recipe": "bootv2-items-search-v1", "request_id": "publication-stop"})
            state = self.finish_probe(started["probe_id"])
        self.assertEqual(len(acknowledgements), 1)
        self.assertTrue(acknowledgements[0]["stop_requested"])
        self.assertFalse(state["passed"], "acknowledged stop was published as a passing experiment")
        self.assertTrue(state["cleanup_complete"], state)


if __name__ == "__main__":
    unittest.main()
