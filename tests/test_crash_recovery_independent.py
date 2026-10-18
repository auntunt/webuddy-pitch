"""A real killed service owner, real owned descendants, and an unrelated live owner.

Fixtures use only temporary repositories/databases and loopback random ports.
Cleanup signals a PID only while ps still identifies this exact fixture script.
No model, existing platform service, production process, or user data is used.
"""
import base64
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from tmh.platform.agents import Runner
from tmh.platform.store import Store, now


REPO = Path(__file__).resolve().parents[1]
RAW_OUTPUT = b"owned-crash-output\x00\xff\n"
RETAINED = b"VALUE = 1\n# complete intermediate change must survive\n"

WORKER = r'''
import base64,json,os,pathlib,signal,subprocess,sys,time
action=sys.argv[1]; root=pathlib.Path(sys.argv[2])
if action=='complete':
    (root/'draft.py').write_bytes(b'VALUE = 1\n# complete intermediate change must survive\n')
    os.write(1,b'owned-crash-output\x00\xff\n')
    raise SystemExit(0)
if action=='retry':
    print('RETRY_OBS '+json.dumps({'draft':base64.b64encode((root/'draft.py').read_bytes()).decode(),
          'cwd':str(root)}),flush=True)
    raise SystemExit(0)
control=pathlib.Path(sys.argv[3])
signal.signal(signal.SIGTERM,signal.SIG_IGN)
state={'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgrp(),'script':__file__,'action':action}
temporary=control/(action+'.json.tmp');temporary.write_text(json.dumps(state));temporary.replace(control/(action+'.json'))
if action=='leader':
    (root/'draft.py').write_bytes(b'VALUE = 1\n# complete intermediate change must survive\n')
    subprocess.Popen([sys.executable,__file__,'child',str(root),str(control)])
    os.write(1,b'owned-crash-output\x00\xff\n')
counter=0
while True:
    counter+=1
    (control/(action+'-heartbeat')).write_text(str(counter))
    time.sleep(.03)
'''

SERVICE = r'''
import json,pathlib,sys,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from tmh.platform.agents import Runner
from tmh.platform.store import Store,now
data=pathlib.Path(sys.argv[1]);rid=int(sys.argv[2]);worker=sys.argv[3];workdir=pathlib.Path(sys.argv[4])
class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.end_headers();self.wfile.write(b'owned temporary service')
    def log_message(self,*args):pass
httpd=ThreadingHTTPServer(('127.0.0.1',0),Health)
threading.Thread(target=httpd.serve_forever,daemon=True).start()
(data/'service.json').write_text(json.dumps({'port':httpd.server_port}))
store=Store(data/'platform.db');runner=Runner(store,data)
runner._control(rid,{'owned':{'timeout':120}},'owned')
store.update_run(rid,status='running',started=now(),workdir=str(workdir))
try:
    result,folder=runner.run_command(rid,[sys.executable,worker,'leader',str(workdir),str(data)],
        workdir,timeout=120,on_output=lambda chunk:store.append_output(rid,chunk),kind='independent-crash')
    runner.finish_invocation(rid,result.returncode,result.output)
finally:
    httpd.shutdown();httpd.server_close();store.db.close()
'''


@unittest.skipUnless(os.name == "posix", "requires real POSIX service-owner failure")
class CrashRecoveryIndependentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-crash-independent-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.root = self.data / "project"
        self.root.mkdir()
        (self.root / "draft.py").write_text("VALUE = 0\n")
        self.git("init", "-q")
        self.git("config", "user.name", "owned-fixture")
        self.git("config", "user.email", "fixture@localhost")
        self.git("add", "."); self.git("commit", "-qm", "owned baseline")
        self.initial_head = self.git("rev-parse", "HEAD")
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("CRASH", "临时服务崩溃验证", str(self.root))
        self.ticket = self.store.create_ticket(self.project["id"], "保留中间改动继续", "fixture", auto=False)
        self.run = self.store.create_run(self.project["id"], self.ticket["id"], "owned", "fix", "fixture", "完整原始任务")
        self.workdir = self.data / "worktrees" / ("CRASH-1-r" + str(self.run["id"]))
        self.workdir.parent.mkdir()
        self.git("worktree", "add", "-b", "tmh/crash-fixture", str(self.workdir), "HEAD")
        self.worker = self.data / "owned-worker.py"
        self.worker.write_text(WORKER)
        self.service_script = self.data / "owned-service.py"
        self.service_script.write_text(SERVICE)
        (self.data / "autoflow.json").write_text(json.dumps({"on": False, "check": "none", "rounds": 0}))
        (self.data / "agents.json").write_text(json.dumps({"owned": {"timeout": 10,
            "cmd": [sys.executable, str(self.worker), "retry", "{workdir}", "{prompt_file}"]}}))
        self.service = None
        self.unrelated = None
        self.runners = []
        self.observations = {"test": self.id(), "temporary_directory": str(self.data)}
        self.addCleanup(self.cleanup_owned)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True, stderr=subprocess.PIPE).strip()

    def read_json(self, path):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    def lifecycle(self):
        return self.read_json(self.data / "runs" / str(self.run["id"]) / "lifecycle.json")

    def process(self, pid):
        result = subprocess.run(["ps", "-ww", "-p", str(pid), "-o", "pid=,ppid=,pgid=,stat=,lstart=,command="],
                                capture_output=True, text=True)
        raw = result.stdout.strip()
        parts = raw.split(None, 4)
        return {"pid": pid, "alive": bool(len(parts) >= 4 and not parts[3].startswith("Z")), "ps": raw}

    def workers(self):
        return [self.read_json(self.data / (name + ".json")) for name in ("leader", "child")]

    def wait_for(self, predicate, seconds=6):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            value = predicate()
            if value:
                return value
            time.sleep(.025)
        return None

    def launch_service(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        self.service_log = (self.data / "service-output.bin").open("wb")
        self.addCleanup(self.service_log.close)
        self.service = subprocess.Popen([sys.executable, str(self.service_script), str(self.data), str(self.run["id"]), str(self.worker), str(self.workdir)],
                                        cwd=REPO, env=env, stdout=self.service_log, stderr=subprocess.STDOUT, start_new_session=True)

    def start_service(self):
        self.launch_service()
        ready = self.wait_for(lambda: all(self.workers()) and self.lifecycle() and
            self.lifecycle().get("attempts") and self.lifecycle()["attempts"][0].get("pid") and
            "owned-crash-output" in self.store.run(self.run["id"])["output"])
        self.assertTrue(ready, "owned service never started its real worker: " + (self.data / "service-output.bin").read_text(errors="replace"))
        health = self.read_json(self.data / "service.json")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:%d/" % health["port"], timeout=2) as response:
            self.assertEqual(response.read(), b"owned temporary service")
        workers = self.workers()
        self.assertTrue(all(str(self.worker) in self.process(row["pid"])["ps"] for row in workers))
        self.assertNotEqual(workers[0]["pgid"], os.getpgrp())
        self.assertNotEqual(workers[0]["pgid"], self.service.pid)
        self.assertEqual(workers[0]["pgid"], workers[1]["pgid"])
        self.observations["before"] = self.snapshot()

    def snapshot(self):
        row = self.store.run(self.run["id"])
        attempt = self.data / "runs" / str(self.run["id"]) / "attempts"
        evidence = {str(path.relative_to(self.data)): base64.b64encode(path.read_bytes()).decode()
                    for path in attempt.rglob("*") if path.is_file()} if attempt.exists() else {}
        return {"run": row, "lifecycle": self.lifecycle(), "workers": [self.process(w["pid"]) for w in self.workers() if w],
                "draft_base64": base64.b64encode((self.workdir / "draft.py").read_bytes()).decode(), "attempt_files": evidence}

    def save_observations(self):
        target = os.environ.get("TMH_CRASH_EVIDENCE")
        if target:
            folder = Path(target); folder.mkdir(parents=True, exist_ok=True)
            path = folder / (self._testMethodName + ".json")
            path.write_text(json.dumps(self.observations, ensure_ascii=False, indent=2) + "\n")

    def cleanup_owned(self):
        # Capture test results before fixture cleanup, which cannot count as recovery.
        try:
            self.observations["before_fixture_cleanup"] = self.snapshot()
            if self.service and self.service.poll() is None:
                self.service.kill(); self.service.wait(timeout=3)
                # Allow a real owner-loss supervisor to finish before our fallback
                # cleanup. This delay is not part of the tested recovery result.
                self.wait_for(lambda: all(not self.process(row["pid"])["alive"] for row in self.workers() if row), 2)
            for runner in self.runners:
                for control in runner.controls.values():
                    if not control.get("finished"):
                        control["event"].set()
            cleanup = []
            for name in ("child", "leader", "unrelated"):
                marker = self.read_json(self.data / (name + ".json"))
                if not marker:
                    continue
                current = self.process(marker["pid"])
                if current["alive"] and str(self.worker) in current["ps"]:
                    try:
                        os.kill(marker["pid"], signal.SIGKILL)
                        cleanup.append({"pid": marker["pid"], "signal": "SIGKILL", "matching_command": current["ps"]})
                    except ProcessLookupError:
                        pass
            if self.unrelated:
                self.unrelated.wait(timeout=3)
            self.wait_for(lambda: all(not self.process(row["pid"])["alive"] for row in self.workers() if row), 3)
            self.observations["fixture_cleanup_signals"] = cleanup
            self.observations["after_fixture_cleanup"] = self.snapshot()
            self.save_observations()
        finally:
            if self.service and self.service.poll() is None:
                self.service.kill(); self.service.wait(timeout=3)

    def test_service_sigkill_reclaims_descendants_and_recovers_preserved_work(self):
        self.start_service()
        owned = list(self.workers())
        self.service.kill()  # only the Popen service owner; worker groups are separate
        self.assertEqual(self.service.wait(timeout=3), -signal.SIGKILL)
        restarted = Runner(self.store, self.data)
        self.runners.append(restarted)
        restarted.recover()
        self.wait_for(lambda: all(not self.process(row["pid"])["alive"] for row in owned), 5)
        recovered = self.snapshot()
        policy = restarted.retry_state(self.run["id"])
        self.observations.update(service_returncode=self.service.returncode, after_recover=recovered, retry_state=policy)
        problems = []
        if any(row["alive"] for row in recovered["workers"]): problems.append("owned descendants still execute after service SIGKILL and recovery")
        if recovered["run"]["status"] != "failed": problems.append("interrupted run is not failed")
        life = recovered["lifecycle"] or {}
        if life.get("finished") is not True: problems.append("lifecycle remains unfinished")
        if not life.get("stopped_reason"): problems.append("interruption cause is absent")
        attempts = life.get("attempts") or []
        if not attempts or any(not isinstance(a.get("cleanup"), dict) or a["cleanup"].get("complete") is not True for a in attempts):
            problems.append("owned group cleanup has no completed durable receipt")
        raw_files = [base64.b64decode(value) for name, value in recovered["attempt_files"].items() if name.endswith("output.bin")]
        if not any(RAW_OUTPUT in raw for raw in raw_files): problems.append("already emitted original bytes were not preserved")
        if (self.workdir / "draft.py").read_bytes() != RETAINED: problems.append("intermediate code bytes changed")
        if not policy["can_retry"]: problems.append("safely recovered ordinary run cannot resume: " + str(policy["retry_blocked"]))
        self.assertFalse(problems, "; ".join(problems))
        before_repeat = self.snapshot()
        restarted.recover()
        self.assertEqual(self.snapshot(), before_repeat, "repeated recovery must not rewrite historical evidence")
        new = restarted.retry(self.run["id"], "fixture-recovery-operator")
        done = self.wait_for(lambda: restarted.controls.get(new["id"], {}).get("finished") and
            self.store.run(new["id"])["status"] not in ("queued", "running"), 10)
        self.assertTrue(done, "new isolated local checker did not finish")
        result = self.store.run(new["id"])
        self.observations["retried_run"] = result
        self.assertEqual(result["status"], "done", result["result"])
        line = next((x for x in result["output"].splitlines() if x.startswith("RETRY_OBS ")), None)
        self.assertIsNotNone(line, "retry checker never reported actual preserved bytes")
        seen = json.loads(line[len("RETRY_OBS "):])
        self.assertEqual(base64.b64decode(seen["draft"]), RETAINED)
        self.assertNotEqual(Path(seen["cwd"]), self.workdir)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.initial_head)
        self.assertEqual((self.workdir / "draft.py").read_bytes(), RETAINED)

    def test_second_runner_cannot_fail_or_recover_a_live_service_owners_run(self):
        self.start_service()
        before = self.store.run(self.run["id"])
        second = Runner(self.store, self.data)
        second.recover()
        self.observations["after_second_recover"] = self.snapshot()
        self.assertEqual(self.store.run(self.run["id"]), before, "a live service owner still owns this running record")
        self.assertTrue(all(self.process(row["pid"])["alive"] for row in self.workers()))
        self.assertFalse(second.retry_state(self.run["id"])["can_retry"])

    def test_legacy_pid_receipt_never_signals_a_different_live_owned_fixture(self):
        self.unrelated = subprocess.Popen([sys.executable, str(self.worker), "unrelated", str(self.root), str(self.data)],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.assertTrue(self.wait_for(lambda: self.read_json(self.data / "unrelated.json")))
        marker = self.read_json(self.data / "unrelated.json")
        self.store.update_run(self.run["id"], status="running", started=now(), workdir=str(self.root))
        folder = self.data / "runs" / str(self.run["id"]); folder.mkdir(parents=True)
        (folder / "lifecycle.json").write_text(json.dumps({"started_at": now(), "finished": False, "stopped_reason": "",
            "attempts": [{"attempt": 1, "pid": marker["pid"], "pgid": marker["pgid"], "command": ["old-unverifiable-command"]}]}))
        recovered = Runner(self.store, self.data)
        recovered.recover()
        policy = recovered.retry_state(self.run["id"])
        self.observations.update(after_legacy_recover=self.snapshot(), unrelated_process=self.process(marker["pid"]), retry_state=policy)
        self.assertTrue(self.process(marker["pid"])["alive"], "historic PID/PGID alone must not authorize signalling")
        self.assertFalse(policy["can_retry"], "missing ownership/cleanup proof must stay blocked")

    def completed_attempt(self, run):
        runner = Runner(self.store, self.data)
        self.runners.append(runner)
        runner._control(run["id"], {"owned": {"timeout": 10}}, "owned")
        self.store.update_run(run["id"], status="running", started=now(), workdir=str(self.workdir))
        result, folder = runner.run_command(run["id"], [sys.executable, "-c", "print('actual local proof')"],
                                            self.workdir, timeout=5, kind="independent-proof")
        runner.finish_invocation(run["id"], result.returncode, result.output)
        self.assertEqual(result.returncode, 0)
        return folder

    def test_receipt_from_another_real_run_cannot_prove_this_run_was_cleaned(self):
        import shutil
        target = self.completed_attempt(self.run)
        donor = self.store.create_run(self.project["id"], None, "owned", "ask", "fixture", "separate real command")
        source = self.completed_attempt(donor)
        donor_bytes = (source / "supervisor-result.json").read_bytes()
        self.observations["original_target"] = self.snapshot()
        # The target simulates an unsealed interrupted lifecycle; copy a real
        # other run's complete bundle, including matching nonce/hash, into it.
        life_path = self.data / "runs" / str(self.run["id"]) / "lifecycle.json"
        life = self.lifecycle(); life.update(finished=False, stopped_reason="")
        life.pop("recovery", None); life_path.write_text(json.dumps(life))
        self.store.update_run(self.run["id"], status="running", ended="", result="")
        for name in ("supervisor.json", "supervisor-result.json"):
            value = self.read_json(source / name)
            value["folder"] = str(target.resolve())
            (target / name).write_text(json.dumps(value))
        for name in ("output.bin", "output.txt"):
            shutil.copyfile(source / name, target / name)
        runner = Runner(self.store, self.data); runner.recover()
        current = self.lifecycle()
        policy = runner.retry_state(self.run["id"])
        self.observations.update(after_wrong_run_proof=self.snapshot(), retry_state=policy,
                                 donor_run=donor["id"])
        self.assertIs(current["finished"], False)
        self.assertEqual(current["recovery"]["state"], "blocked")
        self.assertFalse(policy["can_retry"])
        self.assertTrue(current["recovery"]["errors"])
        self.assertEqual((source / "supervisor-result.json").read_bytes(), donor_bytes)

    def test_service_crash_after_done_row_before_lifecycle_seal_is_reconciled(self):
        paused = SERVICE.replace("worker,'leader'", "worker,'complete'").replace(
            "    runner.finish_invocation(rid,result.returncode,result.output)",
            "    store.update_run(rid,status='done',exit_code=0,result=result.output,ended=now())\n"
            "    (data/'done-window.json').write_text(json.dumps({'run_id':rid}))\n"
            "    time.sleep(120)")
        self.service_script.write_text(paused)
        self.launch_service()
        self.assertTrue(self.wait_for(lambda: self.read_json(self.data / "done-window.json")))
        self.assertEqual(self.store.run(self.run["id"])["status"], "done")
        self.assertIs(self.lifecycle()["finished"], False)
        self.observations["before_done_window_crash"] = self.snapshot()
        self.service.kill(); self.assertEqual(self.service.wait(timeout=3), -signal.SIGKILL)
        runner = Runner(self.store, self.data); runner.recover()
        self.observations["after_done_window_recover"] = self.snapshot()
        self.assertIs(self.lifecycle()["finished"], True, "startup cannot skip an unsealed done row")
        self.assertEqual(self.lifecycle()["recovery"]["state"], "complete")
        self.assertEqual(self.store.run(self.run["id"])["status"], "failed", "abandoned unsealed work is not business success")
        self.assertTrue(runner.retry_state(self.run["id"])["can_retry"])
        self.assertEqual((self.workdir / "draft.py").read_bytes(), RETAINED)

    def test_corrupt_lifecycle_of_lost_known_owner_is_visible_blocked_not_running_forever(self):
        runner = Runner(self.store, self.data)
        runner._control(self.run["id"], {"owned": {"timeout": 10}}, "owned")
        self.store.update_run(self.run["id"], status="running", started=now(), workdir=str(self.workdir))
        runner._release(self.run["id"])
        folder = self.data / "runs" / str(self.run["id"])
        damaged = b'{"finished":false,"attempts":\xff incomplete original receipt'
        (folder / "lifecycle.json").write_bytes(damaged)
        restarted = Runner(self.store, self.data); restarted.recover()
        policy = restarted.retry_state(self.run["id"])
        self.observations.update(after_corrupt_lifecycle=self.snapshot(), retry_state=policy,
                                 damaged_original_base64=base64.b64encode(damaged).decode())
        self.assertFalse(policy["can_retry"])
        self.assertNotEqual(self.store.run(self.run["id"])["status"], "running",
                            "a known lost owner with unreadable proof must be visible as blocked, not spin forever")
        retained = {str(path.relative_to(folder)): base64.b64encode(path.read_bytes()).decode()
                    for path in folder.rglob("*") if path.is_file() and path.read_bytes() == damaged}
        self.observations["retained_corrupt_files"] = retained
        self.assertTrue(retained, "corrupt original evidence must remain byte-for-byte available")
        first = self.snapshot()
        restarted.recover()
        self.observations["after_corrupt_lifecycle_recheck"] = self.snapshot()
        self.assertEqual(self.snapshot(), first, "rechecking cannot replace corrupt original proof with its readable blocked summary")
        self.assertFalse(restarted.retry_state(self.run["id"])["can_retry"])

    def test_queued_owned_run_with_no_attempts_can_end_without_inventing_a_process(self):
        owner = Runner(self.store, self.data)
        owner._claim(self.run["id"])
        owner._release(self.run["id"])
        runner = Runner(self.store, self.data); runner.recover()
        life = self.lifecycle()
        self.observations["queued_recovered"] = self.snapshot()
        self.assertEqual(self.store.run(self.run["id"])["status"], "failed")
        self.assertIs(life["finished"], True)
        self.assertEqual(life["attempts"], [])
        self.assertEqual(life["recovery"]["state"], "complete")
        self.assertTrue(runner.retry_state(self.run["id"])["can_retry"])

    def test_unlisted_attempt_directory_prevents_no_attempt_shortcut(self):
        owner = Runner(self.store, self.data)
        owner._control(self.run["id"], {"owned": {"timeout": 10}}, "owned")
        owner._release(self.run["id"])
        self.store.update_run(self.run["id"], status="running", started=now())
        extra = self.data / "runs" / str(self.run["id"]) / "attempts" / "0001"
        extra.mkdir(parents=True)
        (extra / "unresolved-original.bin").write_bytes(b"not listed in lifecycle\x00\xff")
        runner = Runner(self.store, self.data); runner.recover()
        self.observations["unlisted_attempt_recovered"] = self.snapshot()
        self.assertIs(self.lifecycle()["finished"], False)
        self.assertEqual(self.lifecycle()["recovery"]["state"], "blocked")
        self.assertFalse(runner.retry_state(self.run["id"])["can_retry"])
        self.assertEqual((extra / "unresolved-original.bin").read_bytes(), b"not listed in lifecycle\x00\xff")


if __name__ == "__main__":
    unittest.main()
