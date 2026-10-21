"""Run budgets cover real descendant processes and every invoke in a fix loop.

Only this test's unique temporary fixture executable/PID registry is cleaned up;
no process-name search, listening-port lookup or unrelated process-group kill is used.
"""
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unittest
from pathlib import Path
from unittest import mock

from tmh.platform.agents import Runner, git
from tmh.platform.store import Store


FIXTURE = r'''
import os, signal, sys, time
scenario, token, registry, mode, prompt_file, workdir = sys.argv[1:]

def ready(name):
    path = registry + "." + name + ".ready"
    staging = path + "." + str(os.getpid()) + ".tmp"
    with open(staging, "w") as f:
        f.write(str(os.getpid()))
    os.replace(staging, path)

# This standalone POSIX fixture has no threads. Fork real descendants without
# serial interpreter/import startup consuming the readiness allowance. Each
# child still registers its own PID, ignores TERM and holds the output pipe.
while True:
    with open(registry, "a") as f:
        f.write(str(os.getpid()) + "\n")
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print("fixture-start:" + scenario + ":" + mode, flush=True)
    ready(scenario)
    if scenario not in ("parent-exits", "tree", "child"):
        break
    next_scenario = "leaf" if scenario == "child" else "child"
    if os.fork():
        break
    scenario = next_scenario
if scenario == "parent-exits":
    print("wrapper-exiting-with-child-pipe-open", flush=True)
    sys.exit(0)
if scenario == "success":
    print("completed-within-budget", flush=True)
    sys.exit(0)
if scenario == "slow-success":
    time.sleep(.45)
    print("completed-within-budget", flush=True)
    sys.exit(0)
if scenario == "busy":
    print("ERROR 429 overloaded attempt=" + str(os.getpid()), flush=True)
    sys.exit(1)
if scenario == "fix-then-timeout":
    if mode == "fix":
        with open(os.path.join(workdir, "app.py"), "w") as f:
            f.write("VALUE = 1\n")
        print("fixture-edit-completed", flush=True)
        sys.exit(0)
    print("fixture-diagnosis-started-but-not-completed", flush=True)
    ready("diagnosis")
if scenario == "long-log":
    for n in range(160):
        print("retained-log-%03d:" % n + "evidence" * 12, flush=True)
    print("partial-line-must-survive", end="", flush=True)
    ready("long-log-output")
time.sleep(60)
'''


@unittest.skipUnless(os.name == "posix", "process-group lifecycle tests require POSIX")
class RunLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-lifecycle-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.root = self.data / "project"
        self.root.mkdir()
        (self.root / "app.py").write_text("VALUE = 0\n")
        git(self.root, "init", "-q")
        git(self.root, "add", ".")
        git(self.root, "-c", "user.name=test", "-c", "user.email=test@localhost", "commit", "-qm", "baseline")
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("LIFE", "运行生命周期", str(self.root))
        self.ticket = self.store.create_ticket(self.project["id"], "保留失败现场", "tester", auto=False)
        self.runner = Runner(self.store, self.data)
        self.script = self.data / "owned-fixture.py"
        self.script.write_text(FIXTURE)
        self.registry = self.data / "owned-pids.txt"
        self.token = self.data.name
        self.workers = []
        self.addCleanup(self.cleanup_owned)

    def conf(self, scenario="tree", timeout=3):
        return {"fixture": {"timeout": timeout, "cmd": [sys.executable, str(self.script), scenario,
            self.token, str(self.registry), "{mode}", "{prompt_file}", "{workdir}"]}}

    def shell_conf(self, body, timeout):
        conf = self.conf(timeout=timeout)
        conf["fixture"]["cmd"] = ["/bin/sh", "-c",
            'printf "%s\\n" "$$" >> "$1"\n' + body,
            str(self.script), str(self.registry), self.token]
        return conf

    def new_run(self, mode="ask"):
        run = self.store.create_run(self.project["id"], self.ticket["id"], "fixture", mode, "tester", "fixture prompt")
        (self.data / "runs" / str(run["id"])).mkdir(parents=True)
        return run["id"]

    def owned_live(self):
        pids = set(int(p) for p in self.registry.read_text().splitlines()) if self.registry.exists() else set()
        live = []
        for pid in pids:
            # procps may truncate redirected command lines to the terminal
            # width; ownership checks need the complete fixture path/token.
            result = subprocess.run(["ps", "-ww", "-p", str(pid), "-o", "stat=", "-o", "command="], capture_output=True, text=True)
            text = result.stdout.strip()
            if result.returncode == 0 and text and not text.startswith("Z") and str(self.script) in text and self.token in text:
                live.append(pid)
        return live

    def cleanup_owned(self):
        # Revoke pending launches before taking the PID snapshot. A worker may
        # still be preparing its supervisor when a readiness assertion fails.
        try:
            if any(thread.is_alive() for thread in self.workers):
                for run in self.store.runs(project_id=self.project["id"]):
                    if run["status"] not in ("queued", "running"):
                        continue
                    try:
                        self.runner.cancel(run["id"], "test cleanup")
                    except ValueError:
                        # The worker may finish between the read and cancel.
                        if self.store.run(run["id"])["status"] in ("queued", "running"):
                            raise
        finally:
            # A cancellation error must not bypass the existing PID cleanup.
            for pid in self.owned_live():
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for thread in self.workers:
                thread.join(2)

    def async_call(self, operation):
        result = {}
        def go():
            try:
                result["value"] = operation()
            except BaseException as error:
                result["error"] = error
        thread = threading.Thread(target=go, daemon=True)
        self.workers.append(thread)
        thread.start()
        return thread, result

    def bounded(self, operation, limit=2.5):
        started = time.monotonic()
        thread, result = self.async_call(operation)
        thread.join(limit)
        stuck = thread.is_alive()
        stack = "".join(traceback.format_stack(sys._current_frames()[thread.ident])) if stuck else ""
        if stuck:
            self.cleanup_owned()
        self.assertFalse(stuck, "run did not finish within the lifecycle budget:\n" + stack)
        if "error" in result:
            raise result["error"]
        return result.get("value"), time.monotonic() - started

    def invoke(self, rid, conf, tag=""):
        return self.runner.invoke(rid, self.project, self.ticket, "fixture", conf, "ask", "fixture prompt", self.root, tag=tag)

    def lifecycle(self, rid):
        return json.loads((self.data / "runs" / str(rid) / "lifecycle.json").read_text())

    def all_evidence(self, rid):
        folder = self.data / "runs" / str(rid)
        return "\n".join(f.read_text(errors="replace") for f in folder.rglob("*") if f.is_file())

    def wait_ready(self, *scenarios, limit=2):
        files = [Path(str(self.registry) + "." + scenario + ".ready") for scenario in scenarios]
        until = time.monotonic() + limit
        while time.monotonic() < until:
            if all(path.exists() for path in files):
                self.assertGreaterEqual(len(self.owned_live()), len(scenarios),
                                        "ready markers must belong to live owned fixture processes")
                return
            time.sleep(.01)
        self.fail("fixture did not reach its required scenario: "
                  + repr({path.name: path.exists() for path in files}))

    def bounded_ready(self, rid, operation, *scenarios, limit=5.5):
        # Files are written after signal setup or the specific work/output.
        # Runner batches short displayed logs, so DB output is not a handshake.
        started = time.monotonic()
        thread, result = self.async_call(operation)
        self.wait_ready(*scenarios)
        self.assertGreater(self.runner.remaining(rid), 0, "startup consumed the entire fixture budget")
        thread.join(max(0, started + limit - time.monotonic()))
        if thread.is_alive():
            stack = "".join(traceback.format_stack(sys._current_frames()[thread.ident]))
            self.cleanup_owned()
            self.fail("ready fixture outlived its timeout and cleanup allowance:\n" + stack)
        if "error" in result:
            raise result["error"]
        return result.get("value"), time.monotonic() - started

    def start_fix(self, rid, conf):
        return self.runner._go(rid, self.project, self.ticket, "fixture", "fix", "change app.py safely", conf)

    def configure_check(self, command):
        (self.data / "autoflow.json").write_text(json.dumps({"check": command, "rounds": 2, "check_timeout": 20}))

    def test_owned_process_lookup_preserves_arguments_in_narrow_environments(self):
        child = subprocess.Popen([sys.executable, str(self.script), "guard", self.token,
            str(self.registry), "guard", "unused", str(self.root)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            marker = Path(str(self.registry) + ".guard.ready")
            until = time.monotonic() + 2
            while not marker.exists() and time.monotonic() < until:
                time.sleep(.01)
            self.assertTrue(marker.exists(), "fixture must start before checking process ownership")
            self.assertIsNone(child.poll())
            with mock.patch.dict(os.environ, {"COLUMNS": "40"}):
                self.assertIn(child.pid, self.owned_live())
        finally:
            child.kill()
            child.wait(timeout=5)

    def test_wrapper_exit_does_not_leave_descendants_holding_the_log_pipe(self):
        rid = self.new_run()
        (code, _), elapsed = self.bounded(lambda: self.invoke(rid, self.conf("parent-exits")))
        self.assertNotEqual(code, 0, "wrapper exit alone is not a completed run while descendants remain")
        self.assertLess(elapsed, 2.5)
        self.assertEqual(self.owned_live(), [])
        self.assertIn("wrapper-exiting-with-child-pipe-open", self.store.run(rid)["output"])
        self.assertEqual(self.runner.stop_reason(rid), "orphaned")

    def test_timeout_kills_term_ignoring_descendants_and_keeps_complete_logs(self):
        rid = self.new_run()
        # This case needs a live three-generation tree, so allow interpreter
        # startup separately from asserting the bounded timeout/cleanup path.
        # The real run clock starts normally and is never reset at readiness.
        budget, limit = 3, 5.5
        (code, _), elapsed = self.bounded_ready(rid,
            lambda: self.invoke(rid, self.conf("tree", timeout=budget)), "tree", "child", "leaf", limit=limit)
        markers = ["fixture-start:" + scenario for scenario in ("tree", "child", "leaf")]
        self.assertNotEqual(code, 0)
        self.assertLess(elapsed, limit)
        self.assertEqual(self.owned_live(), [])
        self.assertEqual(self.runner.stop_reason(rid), "timeout")
        life = self.lifecycle(rid)
        self.assertEqual(life["stopped_reason"], "timeout")
        cleanup = life["attempts"][0]["cleanup"]
        self.assertTrue(cleanup["term_sent"])
        self.assertTrue(cleanup["kill_sent"])
        self.assertTrue(cleanup["complete"])
        for marker in markers:
            self.assertIn(marker, self.store.run(rid)["output"])

    def test_timeout_preserves_every_output_line_and_unterminated_tail(self):
        rid = self.new_run()
        (code, _), _ = self.bounded_ready(rid,
            lambda: self.invoke(rid, self.conf("long-log", timeout=3)), "long-log-output")
        self.assertNotEqual(code, 0)
        evidence = self.all_evidence(rid)
        for n in range(160):
            self.assertIn("retained-log-%03d:" % n + "evidence" * 12, evidence)
        self.assertIn("partial-line-must-survive", evidence)
        self.assertEqual(self.owned_live(), [])

    def test_cancel_stops_the_ignoring_tree_without_waiting_for_configured_timeout(self):
        rid = self.new_run()
        self.store.update_run(rid, status="running")
        thread, result = self.async_call(lambda: self.invoke(rid, self.conf("tree", timeout=20)))
        self.wait_ready("tree", "child", "leaf")
        started = time.monotonic()
        cancelled = self.runner.cancel(rid, "tester")
        thread.join(2)
        self.assertFalse(thread.is_alive(), "cancelled descendants kept the reader alive")
        self.assertLess(time.monotonic() - started, 2)
        self.assertNotIn("error", result)
        self.assertNotEqual(result["value"][0], 0)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.store.run(rid)["status"], "cancelled")
        self.assertEqual(self.runner.stop_reason(rid), "cancelled")
        self.assertEqual(self.lifecycle(rid)["stopped_reason"], "cancelled")
        self.assertEqual(self.owned_live(), [])

    def test_cancel_before_invoke_cannot_launch_any_process(self):
        rid = self.new_run()
        self.runner.cancel(rid, "tester")
        (code, _), _ = self.bounded(lambda: self.invoke(rid, self.conf("success")))
        self.assertNotEqual(code, 0)
        self.assertFalse(self.registry.exists())
        self.assertEqual(self.store.run(rid)["status"], "cancelled")

    def test_cleanup_prevents_launch_after_its_pid_snapshot(self):
        rid = self.new_run()
        entered, release = threading.Event(), threading.Event()

        def delayed_invoke():
            entered.set()
            release.wait()
            return self.invoke(rid, self.conf("tree", timeout=20))

        owned_live = self.owned_live

        def snapshot_then_start():
            pids = owned_live()
            release.set()
            return pids

        try:
            thread, result = self.async_call(delayed_invoke)
            self.assertTrue(entered.wait(2), "worker did not reach the launch barrier")
            with mock.patch.object(self, "owned_live", side_effect=snapshot_then_start):
                self.cleanup_owned()
        finally:
            release.set()
        self.assertFalse(thread.is_alive(), "cleanup allowed a late fixture launch")
        self.assertNotIn("error", result)
        self.assertNotEqual(result["value"][0], 0)
        self.assertFalse(self.registry.exists(), "cancelled cleanup must prevent new fixture processes")
        self.assertEqual(self.runner.stop_reason(rid), "cancelled")

    def test_ready_marker_publishes_complete_pid_before_cancellation(self):
        # Pause the real leaf after writing its PID but before closing the file.
        # This also catches a rename incorrectly moved inside the with block.
        self.script.write_text(r'''
import builtins, os, time
original_open = builtins.open

class PausedWriter:
    def __init__(self, file):
        self.file = file

    def __enter__(self):
        return self

    def __exit__(self, *args):
        with original_open(registry + ".leaf.paused", "w") as marker:
            marker.write(str(os.getpid()))
        while not os.path.exists(registry + ".leaf.release"):
            time.sleep(.01)
        return self.file.__exit__(*args)

    def write(self, text):
        return self.file.write(text)

def gated_open(path, mode="r", *args, **kwargs):
    file = original_open(path, mode, *args, **kwargs)
    if ".leaf.ready" in str(path) and mode == "w":
        return PausedWriter(file)
    return file

builtins.open = gated_open
''' + FIXTURE)
        paused = Path(str(self.registry) + ".leaf.paused")
        release = Path(str(self.registry) + ".leaf.release")
        marker = Path(str(self.registry) + ".leaf.ready")
        wait_ready = self.wait_ready

        def check_publication(*scenarios, **kwargs):
            until = time.monotonic() + 2
            try:
                while not paused.exists() and time.monotonic() < until:
                    time.sleep(.01)
                self.assertTrue(paused.exists(), "leaf did not reach the publication barrier")
                self.assertFalse(marker.exists(), "ready marker became visible before PID file closed")
            finally:
                release.write_text("release")
            wait_ready(*scenarios, **kwargs)
            self.assertIn(int(marker.read_text()), self.owned_live())

        with mock.patch.object(self, "wait_ready", side_effect=check_publication):
            self.test_cancel_stops_the_ignoring_tree_without_waiting_for_configured_timeout()

    def test_total_budget_is_shared_across_invokes_and_no_later_attempt_starts(self):
        rid = self.new_run()
        conf = self.shell_conf('sleep 1.2\nprintf "completed-within-budget\\n"', timeout=2)
        def sequence():
            return [self.invoke(rid, conf, tag="-" + str(n))[0] for n in range(3)]
        codes, elapsed = self.bounded(sequence, limit=4)
        self.assertEqual(codes[0], 0)
        self.assertTrue(all(code != 0 for code in codes[1:]), codes)
        self.assertLess(elapsed, 4)
        self.assertLessEqual(self.runner.remaining(rid), 0)
        self.assertEqual(self.runner.stop_reason(rid), "timeout")
        self.assertEqual(len(self.registry.read_text().splitlines()), 2, "spent run budget cannot reset on the next invoke")
        record = self.lifecycle(rid)
        self.assertEqual(record["stopped_reason"], "timeout")
        self.assertGreaterEqual(len(record["attempts"]), 2)
        self.assertIn("completed-within-budget", self.all_evidence(rid))

    def test_busy_backoff_cannot_outlive_the_total_run_budget(self):
        rid = self.new_run()
        # Exercise real 429/backoff behavior without spending most of a tiny
        # budget importing Python. The long retry wait must still stop at the
        # single run deadline, with no second executable invocation.
        conf = self.shell_conf('printf "ERROR 429 overloaded attempt=%s\\n" "$$"\nexit 1', timeout=1)
        (code, _), elapsed = self.bounded(lambda: self.invoke(rid, conf))
        self.assertNotEqual(code, 0)
        self.assertLess(elapsed, 2)
        self.assertEqual(self.runner.stop_reason(rid), "timeout")
        self.assertTrue(self.registry.exists(), "busy fixture must have emitted 429 before testing backoff")
        self.assertEqual(len(self.registry.read_text().splitlines()), 1, "a backoff cannot reset the time allowance")
        self.assertIn("ERROR 429 overloaded", self.all_evidence(rid))

    def test_retries_keep_separate_original_outputs_instead_of_overwriting_evidence(self):
        rid = self.new_run()
        with mock.patch("tmh.platform.agents.BUSY_WAITS", (.03, .03)):
            conf = self.shell_conf('printf "ERROR 429 overloaded attempt=%s\\n" "$$"\nexit 1', timeout=3)
            (code, _), _ = self.bounded(lambda: self.invoke(rid, conf))
        self.assertNotEqual(code, 0)
        pids = self.registry.read_text().splitlines()
        self.assertEqual(len(pids), 3)
        attempts = self.lifecycle(rid)["attempts"]
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len({a["evidence"] for a in attempts}), 3)
        for pid, attempt in zip(pids, attempts):
            folder = self.data / attempt["evidence"]
            raw = (folder / "output.bin").read_bytes()
            self.assertIn(("ERROR 429 overloaded attempt=" + pid).encode(), raw)
            self.assertEqual((folder / "prompt.md").read_text(), "fixture prompt")
            self.assertTrue((folder / "timing.json").is_file())

    def test_fix_success_then_diagnosis_timeout_is_failed_not_adoptable_and_keeps_worktree(self):
        rid = self.new_run("fix")
        self.configure_check(shlex.quote(sys.executable) + " -c " + shlex.quote("print('actual-build-passed')"))
        followup, charge = mock.Mock(), mock.Mock()
        followup.always = followup.owns_status = False
        self.runner.after[rid], self.runner.charge = followup, charge
        _, elapsed = self.bounded_ready(rid,
            lambda: self.start_fix(rid, self.conf("fix-then-timeout", timeout=3)), "diagnosis")
        run = self.store.run(rid)
        self.assertLess(elapsed, 5.5)
        self.assertEqual(run["status"], "failed", run["result"])
        self.assertNotEqual(run["exit_code"], 0)
        self.assertEqual(run["decision"], "")
        self.assertEqual(self.runner.stop_reason(rid), "timeout")
        followup.assert_not_called()
        charge.assert_not_called()
        with self.assertRaises(ValueError):
            self.runner.decide(rid, "accept", "tester")
        wt = Path(run["workdir"])
        self.assertTrue(wt.is_dir())
        self.assertEqual((wt / "app.py").read_text(), "VALUE = 1\n")
        self.assertEqual((self.root / "app.py").read_text(), "VALUE = 0\n")
        self.assertIn("+VALUE = 1", run["diff"])
        self.assertIn("fixture-edit-completed", self.all_evidence(rid))
        self.assertIn("fixture-diagnosis-started-but-not-completed", self.all_evidence(rid))
        verification = json.loads((self.data / "runs" / str(rid) / "verify.json").read_text())
        self.assertNotEqual(verification["verdict"], "pass")
        self.assertEqual(self.owned_live(), [])

    def test_build_tree_uses_run_budget_and_cannot_launch_model_after_timeout(self):
        rid = self.new_run("fix")
        cmd = [sys.executable, str(self.script), "tree", self.token, str(self.registry), "check", "unused", str(self.root)]
        self.configure_check(shlex.join(cmd))
        _, elapsed = self.bounded_ready(rid,
            lambda: self.start_fix(rid, self.conf("success", timeout=3)), "tree", "child", "leaf")
        run = self.store.run(rid)
        self.assertLess(elapsed, 5.5)
        self.assertEqual(run["status"], "failed")
        self.assertNotEqual(run["exit_code"], 0)
        self.assertEqual(self.runner.stop_reason(rid), "timeout")
        self.assertNotIn("fixture-start:success:fix", self.all_evidence(rid))
        self.assertEqual(self.owned_live(), [])
        self.assertTrue(Path(run["workdir"]).is_dir())

    def test_build_tree_with_slow_descendant_startup_keeps_real_deadline(self):
        # Reproduce repeated interpreter startup with real time: restarting
        # Python for both descendants costs at least 2.1s before leaf readiness.
        # Fork descendants do not rerun this prefix; this is a regression for
        # serial interpreter initialization, not arbitrary scheduling delays.
        # A single initialized fixture can create the same tree without that
        # serial startup cost. Neither readiness nor the run budget is extended.
        self.script.write_text("import sys, time\nif sys.argv[1] in ('child', 'leaf'):\n    time.sleep(1.05)\n" + FIXTURE)
        wait_ready = self.wait_ready

        def check_tree(*scenarios, **kwargs):
            wait_ready(*scenarios, **kwargs)
            pids = {name: int(Path(str(self.registry) + "." + name + ".ready").read_text())
                    for name in ("tree", "child", "leaf")}
            result = subprocess.run(["ps", "-p", ",".join(str(pid) for pid in pids.values()),
                                     "-o", "pid=", "-o", "ppid=", "-o", "pgid="],
                                    capture_output=True, text=True, check=True)
            lineage = {pid: (parent, group) for pid, parent, group in
                       (map(int, line.split()) for line in result.stdout.splitlines())}
            self.assertEqual(len(set(pids.values())), 3)
            self.assertEqual(set(lineage), set(pids.values()))
            self.assertEqual(lineage[pids["child"]][0], pids["tree"])
            self.assertEqual(lineage[pids["leaf"]][0], pids["child"])
            self.assertEqual(len({group for parent, group in lineage.values()}), 1)

        with mock.patch.object(self, "wait_ready", side_effect=check_tree):
            self.test_build_tree_uses_run_budget_and_cannot_launch_model_after_timeout()
        runs = self.store.runs(project_id=self.project["id"])
        self.assertEqual(len(runs), 1)
        record = self.lifecycle(runs[0]["id"])
        self.assertEqual(record["timeout_seconds"], 3)
        self.assertGreaterEqual(record["elapsed_seconds"], 3)
        self.assertEqual(len(record["attempts"]), 1)
        attempt = record["attempts"][0]
        self.assertEqual(attempt["kind"], "check:check")
        self.assertEqual((attempt["reason"], attempt["returncode"]), ("timeout", 124))
        for field in ("term_sent", "kill_sent", "complete"):
            self.assertTrue(attempt["cleanup"][field], field)
        for scenario in ("tree", "child", "leaf"):
            self.assertIn("fixture-start:" + scenario + ":check", self.all_evidence(runs[0]["id"]))

    def test_cancel_also_stops_an_active_baseline_build_tree(self):
        rid = self.new_run("fix")
        cmd = [sys.executable, str(self.script), "tree", self.token, str(self.registry), "check", "unused", str(self.root)]
        self.configure_check(shlex.join(cmd))
        thread, result = self.async_call(lambda: self.start_fix(rid, self.conf("success", timeout=20)))
        self.wait_ready("tree", "child", "leaf")
        self.runner.cancel(rid, "tester")
        thread.join(2)
        self.assertFalse(thread.is_alive(), "build cancellation must stop shell and every descendant")
        self.assertNotIn("error", result)
        self.assertEqual(self.store.run(rid)["status"], "cancelled")
        self.assertEqual(self.owned_live(), [])
        self.assertNotIn("fixture-start:success:fix", self.all_evidence(rid))

    def test_timeout_does_not_signal_a_separate_process_started_by_this_test(self):
        # A guard represents another task. It is also ours, but belongs to an
        # unrelated session and has a separate registry from the run's tree.
        guard = subprocess.Popen([sys.executable, str(self.script), "guard", self.token,
            str(self.data / "guard-pids.txt"), "guard", "unused", str(self.root)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            rid = self.new_run()
            (code, _), _ = self.bounded_ready(rid,
                lambda: self.invoke(rid, self.conf("tree", timeout=3)), "tree", "child", "leaf")
            self.assertNotEqual(code, 0)
            self.assertIsNone(guard.poll(), "another process group must never receive the run's stop signals")
            self.assertEqual(self.owned_live(), [])
        finally:
            guard.kill()
            guard.wait(timeout=2)

    def test_normal_completion_retains_evidence_without_false_timeout(self):
        rid = self.new_run()
        (code, result), _ = self.bounded(lambda: self.invoke(rid, self.conf("success", timeout=3)))
        self.assertEqual(code, 0)
        self.assertIn("completed-within-budget", result)
        self.assertEqual(self.runner.stop_reason(rid), "")
        self.assertGreater(self.runner.remaining(rid), 0)
        self.assertTrue(self.lifecycle(rid)["attempts"])
        self.assertEqual(self.owned_live(), [])


if __name__ == "__main__":
    unittest.main()
