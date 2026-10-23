"""Recovery forks real retained Git changes; failed run evidence stays historical."""
import base64
import concurrent.futures
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tmh.platform.agents import Runner, git
from tmh.platform.store import Store


CHECKER = r'''
import base64, json, os, pathlib, subprocess, sys, time
action, workdir, prompt_file = sys.argv[1:]
root = pathlib.Path(workdir)
data = pathlib.Path(__file__).parent
rid = os.environ['TMH_RUN']
(data / ('pid-' + rid)).write_text(str(os.getpid()))
def git(*args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True)
if action.startswith('initial-'):
    (root / 'app.py').write_text('VALUE = 1\n')
    (root / 'staged.txt').write_text('staged intermediate\n')
    git('add', 'staged.txt')
    (root / 'staged.txt').write_text('final working bytes\n')
    (root / 'delete.txt').unlink()
    git('mv', 'rename.txt', 'renamed 名称.txt')
    (root / 'binary.bin').write_bytes(bytes(range(256)) + b'\x00changed')
    (root / 'nested').mkdir()
    (root / 'nested' / 'new.txt').write_text('untracked must survive\n')
    (root / 'new.bin').write_bytes(b'\x00\xffnew binary\x00')
    (root / 'link-to-app').symlink_to('app.py')
    print('original-output-kept-verbatim', flush=True)
    (data / ('ready-' + rid)).write_text('ready')
    if action == 'initial-failure':
        sys.exit(7)
    time.sleep(60)
if action == 'wait':
    print('original-wait-output', flush=True)
    (data / ('ready-' + rid)).write_text('ready')
    time.sleep(60)
if action == 'recovered':
    files = {}
    for p in root.rglob('*'):
        if '.git' not in p.parts and p.is_file():
            files[str(p.relative_to(root))] = base64.b64encode(p.read_bytes()).decode()
    print('RECOVERY_OBS ' + json.dumps({'files': files, 'head': git('rev-parse', 'HEAD').strip(),
        'prompt': pathlib.Path(prompt_file).read_text(), 'cwd': str(root)}, ensure_ascii=False), flush=True)
    time.sleep(.15)
'''


@unittest.skipUnless(os.name == "posix", "managed POSIX process lifecycle")
class RunRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-recovery-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.root = self.data / "project"
        self.root.mkdir()
        for name in ("app.py", "staged.txt", "delete.txt", "rename.txt"):
            (self.root / name).write_text("VALUE = 0\n" if name == "app.py" else "original\n")
        (self.root / "binary.bin").write_bytes(b"original binary\x00")
        git(self.root, "init", "-q")
        git(self.root, "add", ".")
        git(self.root, "-c", "user.name=test", "-c", "user.email=test@localhost", "commit", "-qm", "baseline")
        self.original_head = git(self.root, "rev-parse", "HEAD").strip()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("RESTORE", "恢复现场", str(self.root))
        self.ticket = self.store.create_ticket(self.project["id"], "继续保留的改动", "tester", auto=False)
        self.runner = Runner(self.store, self.data)
        self.script = self.data / "owned-checker.py"
        self.script.write_text(CHECKER)
        (self.data / "autoflow.json").write_text(json.dumps({"check": "none", "rounds": 0}))
        self.addCleanup(self.cleanup_owned)

    def configure(self, action, timeout=3):
        (self.data / "agents.json").write_text(json.dumps({"checker": {"timeout": timeout,
            "cmd": [sys.executable, str(self.script), action, "{workdir}", "{prompt_file}"]}}))

    def cleanup_owned(self):
        for rid, control in self.runner.controls.items():
            if not control.get("finished"):
                control["event"].set()
        end = time.monotonic() + 3
        while time.monotonic() < end and any(not c.get("finished") for c in self.runner.controls.values()):
            time.sleep(.02)
        # Only a PID whose command still names this fixture can be killed.
        for path in self.data.glob("pid-*"):
            pid = int(path.read_text())
            command = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
            if str(self.script) in command:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def wait(self, rid, limit=6):
        end = time.monotonic() + limit
        while time.monotonic() < end:
            # _go sets the in-memory flag before replacing lifecycle.json, while
            # holding this lock. Join that finalization before testing recovery.
            with self.runner.lock:
                run = self.store.run(rid)
                control = self.runner.controls.get(rid, {})
                try:
                    life = json.loads(self.receipt(rid).read_text())
                except (OSError, ValueError):
                    life = {}
                if (run["status"] not in ("queued", "running") and control.get("finished")
                        and life.get("finished") and rid not in self.runner.procs):
                    return run
            time.sleep(.01)
        self.fail("owned fixture did not finish finalization: " + self.diagnostic(rid))

    def diagnostic(self, rid):
        with self.runner.lock:
            run = self.store.run(rid)
            control = self.runner.controls.get(rid, {})
            try:
                life = json.loads(self.receipt(rid).read_text())
            except (OSError, ValueError) as error:
                life = {"read_error": str(error)}
            return json.dumps({"run": run, "control": {k: control.get(k) for k in
                ("finished", "stopped_reason", "ended_at")}, "process": self.runner.procs.get(rid),
                "lifecycle": life, "recovery": self.runner.retry_state(rid)}, ensure_ascii=False)

    def ready(self, rid):
        end = time.monotonic() + 3
        while time.monotonic() < end:
            if (self.data / ("ready-" + str(rid))).exists():
                return
            time.sleep(.01)
        self.fail("owned fixture did not prepare its worktree")

    def start(self, mode="fix"):
        ticket = self.store.ticket(self.ticket["id"])
        return self.runner.start(self.project, ticket, "checker", mode, "tester", question="原始完整任务：保留记录并继续。")

    def old_run(self, cancelled=False):
        self.configure("initial-wait" if cancelled else "initial-failure")
        run = self.start()
        if cancelled:
            self.ready(run["id"])
            self.runner.cancel(run["id"], "tester")
        result = self.wait(run["id"])
        self.assertEqual(result["status"], "cancelled" if cancelled else "failed")
        self.assertTrue(self.runner.retry_state(run["id"])["can_retry"], self.diagnostic(run["id"]))
        return result

    def receipt(self, rid):
        return self.data / "runs" / str(rid) / "lifecycle.json"

    def observation(self, rid):
        for path in (self.data / "runs" / str(rid) / "attempts").glob("*/output.txt"):
            for line in path.read_text().splitlines():
                if line.startswith("RECOVERY_OBS "):
                    return json.loads(line[len("RECOVERY_OBS "):])
        self.fail("recovery checker never actually ran")

    def git_state(self, root):
        head = git(root, "rev-parse", "HEAD").strip()
        branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        status = git(root, "status", "--porcelain", "--untracked-files=all")
        index = Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").strip()).read_bytes()
        files = {str(f.relative_to(root)): f.read_bytes() for f in root.rglob("*") if f.is_file() and f.name != ".git"}
        return {"head": head, "branch": branch, "status": status, "index": index, "files": files}

    def assert_blocked(self, rid):
        count = len(self.store.runs(project_id=self.project["id"]))
        self.assertFalse(self.runner.retry_state(rid)["can_retry"])
        with self.assertRaises(ValueError):
            self.runner.retry(rid, "tester")
        self.assertEqual(len(self.store.runs(project_id=self.project["id"])), count)

    def test_failed_and_cancelled_recovery_include_all_git_bytes_without_changing_original_scene(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                old = self.old_run(cancelled)
                rid = old["id"]
                wt = Path(old["workdir"])
                original = self.git_state(wt)
                folder = self.data / "runs" / str(rid)
                logs = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file() and p.name != "lifecycle.json"}
                life = json.loads(self.receipt(rid).read_text())
                self.configure("recovered")
                new = self.wait(self.runner.retry(rid, "tester")["id"])
                self.assertEqual(new["status"], "done", new["result"])
                seen = self.observation(new["id"])
                self.assertNotEqual(Path(seen["cwd"]), wt)
                decoded = {p: base64.b64decode(b) for p, b in seen["files"].items() if p != ".git"}
                self.assertEqual(decoded, original["files"])
                self.assertFalse((Path(new["workdir"]) / "delete.txt").exists())
                self.assertTrue((Path(new["workdir"]) / "link-to-app").is_symlink())
                self.assertEqual(self.git_state(wt), original)
                self.assertEqual(self.store.run(rid), old)
                for name, raw in logs.items():
                    self.assertEqual((folder / name).read_bytes(), raw, name)
                linked = json.loads(self.receipt(rid).read_text())
                self.assertEqual(linked.pop("retry_run"), new["id"])
                self.assertEqual(linked, life, "the original run's stopped receipt must remain historical")
                self.assertEqual(git(self.root, "rev-parse", "HEAD").strip(), self.original_head)
                snap_file = next(folder.glob("recovery-*/snapshot.json"))
                snapshot = json.loads(snap_file.read_text())
                self.assertEqual(snapshot["commit"], seen["head"])
                self.assertEqual(git(self.root, "rev-parse", seen["head"] + "^").strip(), original["head"])
                self.assertIn(old["prompt"], new["prompt"])
                self.assertIn("原始完整任务：保留记录并继续。", seen["prompt"])
                self.assertIn("未验证", snap_file.read_text())
                self.assertEqual(new["decision"], "")

    def test_concurrent_retry_clicks_create_exactly_one_new_run(self):
        old = self.old_run()
        self.configure("recovered")
        barrier = threading.Barrier(2)
        def click():
            barrier.wait()
            try:
                return self.runner.retry(old["id"], "tester")
            except ValueError as error:
                return error
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: click(), range(2)))
        created = [r for r in results if isinstance(r, dict)]
        self.assertEqual(len(created), 1)
        self.assertEqual(len(self.store.runs(project_id=self.project["id"])), 2)
        self.wait(created[0]["id"])
        self.assertEqual(self.runner.retry_state(old["id"])["retry_run"], created[0]["id"])
        self.assert_blocked(old["id"])

    def test_new_run_gets_a_fresh_budget_without_resetting_old_timeout_or_logs(self):
        self.configure("wait", timeout=.2)
        old = self.wait(self.start("ask")["id"])
        self.assertEqual(old["status"], "failed")
        before = json.loads(self.receipt(old["id"]).read_text())
        self.assertEqual(before["stopped_reason"], "timeout")
        time.sleep(.05)
        self.configure("recovered", timeout=1.5)
        new = self.wait(self.runner.retry(old["id"], "tester")["id"])
        self.assertEqual(new["status"], "done", new["result"])
        after = json.loads(self.receipt(old["id"]).read_text())
        after.pop("retry_run")
        self.assertEqual(before, after)
        self.assertEqual(self.store.run(old["id"]), old)
        fresh = json.loads(self.receipt(new["id"]).read_text())
        self.assertEqual(fresh["timeout_seconds"], 1.5)
        self.assertEqual(fresh["stopped_reason"], "")
        self.assertNotEqual(fresh["attempts"][0]["pid"], before["attempts"][0]["pid"])

    def test_uncertain_cleanup_or_malformed_receipts_never_allow_recovery(self):
        old = self.old_run()
        path = self.receipt(old["id"])
        original = path.read_bytes()
        values = [
            {"finished": False, "attempts": []},
            {"finished": True, "attempts": [{"pid": 123, "cleanup": {"complete": False}}]},
            {"finished": True, "attempts": [{"pid": 123, "cleanup": {}}]},
            {"finished": True, "attempts": [{"pid": 123}]},
            {"finished": True, "attempts": "unreadable"},
            {"finished": True, "attempts": ["unreadable"]},
            "invalid-json",
        ]
        try:
            for value in values:
                with self.subTest(receipt=value):
                    path.write_text(value if isinstance(value, str) else json.dumps(value))
                    self.assert_blocked(old["id"])
            path.unlink()
            self.assert_blocked(old["id"])
        finally:
            path.write_bytes(original)

    def test_active_run_and_other_work_on_same_ticket_prevent_recovery(self):
        old = self.old_run()
        self.configure("wait")
        active = self.start("ask")
        self.ready(active["id"])
        self.assert_blocked(active["id"])
        self.assert_blocked(old["id"])
        self.runner.cancel(active["id"], "tester")
        self.wait(active["id"])
        self.assertTrue(self.runner.retry_state(old["id"])["can_retry"])

    def test_closed_ticket_and_delivery_stage_cannot_bypass_their_workflow(self):
        old = self.old_run()
        self.store.update_ticket(self.ticket["id"], "tester", status="closed")
        self.assert_blocked(old["id"])
        self.store.update_ticket(self.ticket["id"], "tester", status="doing", links={"delivery": "delivery-test"})
        self.store.x("INSERT INTO delivery_runs(run_id,delivery_id,stage,base_version,inputs,created) VALUES(?,?,?,?,?,?)",
                     (old["id"], "delivery-test", "develop", 0, "{}", old["created"]))
        state = self.runner.retry_state(old["id"])
        self.assertEqual((state["delivery_id"], state["delivery_stage"]), ("delivery-test", "develop"))
        self.assert_blocked(old["id"])

    def test_missing_or_unmanaged_worktree_never_silently_restarts_from_main(self):
        old = self.old_run()
        self.store.update_run(old["id"], workdir=str(self.data / "missing"))
        self.assert_blocked(old["id"])
        self.store.update_run(old["id"], workdir=str(self.root))
        count = len(self.store.runs(project_id=self.project["id"]))
        with self.assertRaisesRegex(ValueError, "受管目录"):
            self.runner.retry(old["id"], "tester")
        self.assertEqual(len(self.store.runs(project_id=self.project["id"])), count)
        foreign = self.data / "worktrees" / "foreign"
        foreign.mkdir()
        git(foreign, "init", "-q")
        self.store.update_run(old["id"], workdir=str(foreign))
        with self.assertRaisesRegex(ValueError, "不属于这个项目"):
            self.runner.retry(old["id"], "tester")
        self.assertEqual(len(self.store.runs(project_id=self.project["id"])), count)


if __name__ == "__main__":
    unittest.main()
