"""Hand-written commits share one real build/review budget and close its receipt."""
import json
import os
import shlex
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests import test_run_lifecycle as helpers
from tmh.platform import fixloop, handwork
from tmh.platform.agents import git


CHECKER = r'''
import json, pathlib, signal, sys, time, os
mode, scenario, token, registry, ready, reviewed = sys.argv[1:]
with open(registry, 'a') as stream:
    stream.write(str(os.getpid()) + '\n')
print('SYNTHETIC actual ' + mode + ': ' + pathlib.Path('app.py').read_text(), flush=True)
if mode == 'check':
    pathlib.Path(ready).write_text('check started')
    if scenario in ('build-timeout', 'build-cancel'):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(20)
    time.sleep(.15)
else:
    pathlib.Path(reviewed).write_text('review started')
    if scenario == 'review-timeout':
        time.sleep(20)
    print('```tmh-diag\n' + json.dumps({'verdict':'pass','match':'candidate behavior checked','evidence':'synthetic local fixture'}) + '\n```', flush=True)
    if scenario == 'review-error':
        sys.exit(7)
'''


@unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
class HandworkLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.f = helpers.RunLifecycleTest()
        f = self.f
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.addCleanup(self.stop_owned_checks)
        f.script.write_text(CHECKER)
        self.ready = f.data / "check-ready"
        self.reviewed = f.data / "review-ready"
        self.main = git(f.root, "branch", "--show-current").strip()
        self.branch = "wb/" + f.ticket["key"]
        git(f.root, "checkout", "-qb", self.branch)
        (f.root / "app.py").write_text("VALUE = 1\n")
        git(f.root, "add", "app.py")
        git(f.root, "-c", "user.name=SYNTHETIC", "-c", "user.email=fixture@localhost", "commit", "-qm", "synthetic hand-written change")
        self.sha = git(f.root, "rev-parse", "HEAD").strip()
        git(f.root, "checkout", "-q", self.main)
        f.ticket = f.store.update_ticket(f.ticket["id"], "tester", links={"hold": "SYNTHETIC writer"}, status="doing")
        self.platform = SimpleNamespace(store=f.store, runner=f.runner, data_dir=f.data)

    def stop_owned_checks(self):
        for control in self.f.runner.controls.values():
            if not control["finished"]:
                control["event"].set()
        end = time.monotonic() + 3
        while time.monotonic() < end and handwork.busy(self.f.ticket["key"]):
            time.sleep(.01)

    def start(self, scenario, budget=3):
        f = self.f
        args = [scenario, f.token, str(f.registry), str(self.ready), str(self.reviewed)]
        cmd = [sys.executable, str(f.script), "{mode}"] + args
        (f.data / "agents.json").write_text(json.dumps({"fixture": {"cmd": cmd, "run_timeout": budget}}))
        build = shlex.join([sys.executable, str(f.script), "check"] + args)
        (f.data / "autoflow.json").write_text(json.dumps({"on": False, "handwork": "off", "review_agent": "fixture",
                                                         "check": build, "check_timeout": 20, "rounds": 0}))
        return handwork.take(self.platform, f.project, f.ticket, self.branch, self.sha, "SYNTHETIC writer")["run"]

    def wait(self, rid):
        f = self.f
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if not handwork.busy(f.ticket["key"]) and f.runner.controls.get(rid, {}).get("finished"):
                with f.runner.lock:
                    return f.store.run(rid), f.lifecycle(rid)
            time.sleep(.01)
        self.fail("hand-written build/review did not finish within its budget")

    def assert_not_adopted(self):
        f = self.f
        self.assertEqual(f.store.ticket(f.ticket["id"])["status"], "doing")
        self.assertFalse([e for e in f.store.events(f.ticket["id"]) if e["kind"] == "adopt"])

    def test_build_timeout_closes_lifecycle_without_starting_review(self):
        rid = self.start("build-timeout", .6)
        run, life = self.wait(rid)
        self.assertEqual(run["status"], "failed", run["result"])
        self.assertEqual(run["exit_code"], 124)
        self.assertEqual(life["stopped_reason"], "timeout")
        self.assertTrue(life["finished"])
        self.assertTrue(life["attempts"][0]["cleanup"]["complete"])
        self.assertFalse(self.reviewed.exists())
        self.assert_not_adopted()

    def test_cancel_during_build_remains_cancelled_and_recheck_api_stays_guarded(self):
        rid = self.start("build-cancel", 4)
        end = time.monotonic() + 2
        while time.monotonic() < end and not self.ready.exists():
            time.sleep(.01)
        self.assertTrue(self.ready.exists())
        with self.assertRaises(ValueError):
            fixloop.recheck(self.f.runner, rid)
        cancelled = self.f.runner.cancel(rid, "fixture canceller")
        self.assertEqual(cancelled["status"], "cancelled")
        run, life = self.wait(rid)
        self.assertEqual(run["status"], "cancelled")
        self.assertEqual(life["stopped_reason"], "cancelled")
        self.assertTrue(all(a["cleanup"]["complete"] for a in life["attempts"]))
        self.assertFalse(self.reviewed.exists())
        self.assert_not_adopted()

    def test_review_shares_time_spent_on_baseline_and_candidate_checks(self):
        rid = self.start("review-timeout", 1.2)
        run, life = self.wait(rid)
        self.assertEqual(run["status"], "failed", run["result"])
        self.assertEqual(run["exit_code"], 124)
        self.assertEqual(life["stopped_reason"], "timeout")
        self.assertTrue(self.reviewed.exists())
        attempts = life["attempts"]
        self.assertGreaterEqual(len([a for a in attempts if a["kind"].startswith("check:")]), 2)
        model = next(a for a in attempts if a["kind"].startswith("model:"))
        self.assertLess(model["timeout_seconds"], 1.0)
        self.assertTrue(model["cleanup"]["complete"])
        self.assertLess(life["elapsed_seconds"], 2.5)
        self.assert_not_adopted()

    def test_failed_reviewer_cannot_turn_its_printed_pass_into_adoption(self):
        rid = self.start("review-error")
        run, life = self.wait(rid)
        self.assertEqual(run["status"], "failed", run["result"])
        self.assertIn("审查", run["result"])
        self.assertTrue(life["finished"])
        self.assertEqual(life["attempts"][-1]["returncode"], 7)
        self.assert_not_adopted()

    def test_successful_direct_review_finishes_before_adoption(self):
        rid = self.start("success")
        run, life = self.wait(rid)
        self.assertEqual(run["status"], "done", run["result"])
        self.assertEqual(run["exit_code"], 0)
        self.assertTrue(life["finished"])
        self.assertEqual(life["stopped_reason"], "")
        self.assertTrue(all(a["cleanup"]["complete"] for a in life["attempts"]))
        self.assertEqual(self.f.store.ticket(self.f.ticket["id"])["status"], "verify")
        self.assertTrue([e for e in self.f.store.events(self.f.ticket["id"]) if e["kind"] == "adopt"])
