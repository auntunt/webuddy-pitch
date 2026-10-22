"""Real local service death and durable supervisor receipts; no model calls."""
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
from unittest.mock import patch

from tmh.platform import supervised_process as supervised


@unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
class SupervisedProcessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / "attempt"
        self.owner = {"token": "synthetic-test-owner", "run_id": 17, "data_dir": str(self.root)}

    def run_code(self, code, **kwargs):
        return supervised.run_supervised([sys.executable, "-u", "-c", code], folder=self.folder,
                                         owner=self.owner, **kwargs)

    def wait_for(self, predicate, seconds=6):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(.02)
        self.fail("fixture did not reach expected state within %ss" % seconds)

    def assert_clean(self, result):
        self.assertTrue(result.cleanup["complete"], result)
        self.assertFalse(result.cleanup["remaining_group"], result)
        self.assertTrue(result.cleanup["output_complete"], result)

    def start_service(self, target, prelude="", hook="None"):
        code = """import os,signal,sys
from tmh.platform import supervised_process as managed
%s
managed.run_supervised([sys.executable,'-u','-c',%r],folder=%r,owner=%r,
 timeout=20,on_spawn=%s,terminate_grace=.1)
""" % (prelude, target, str(self.folder), self.owner, hook)
        service = subprocess.Popen([sys.executable, "-c", code], cwd=str(Path(__file__).resolve().parents[1]),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        def cleanup():
            if service.poll() is None:
                service.kill()
            service.communicate(timeout=3)
            # Only the target created by this exact synthetic test. This is test
            # cleanup after a failure, never the application's recovery policy.
            identity = self.folder / "supervisor.json"
            if identity.exists():
                progress = json.loads(identity.read_text())
                if progress.get("owner") == self.owner and progress.get("pid"):
                    try:
                        os.killpg(progress["pid"], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        self.addCleanup(cleanup)
        return service

    def test_raw_binary_output_and_full_stdin_survive_independent_worker(self):
        payload = ("完整中文" * 50000).encode() + b"\x00\xff"
        chunks = []
        result = self.run_code("import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())", timeout=5,
                               stdin=payload, on_output=chunks.append)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.output_bytes, payload)
        self.assertEqual("".join(chunks), payload.decode("utf-8", "replace"))
        self.assertEqual((self.folder / "output.bin").read_bytes(), payload)
        self.assertEqual((self.folder / "output.txt").read_text(), result.output)
        receipt = supervised.read_receipt(self.folder, self.owner)
        self.assertEqual(receipt["output"]["bytes"], len(payload))
        self.assert_clean(result)

    def test_service_sigkill_cleans_ignoring_group_and_preserves_live_raw_bytes(self):
        ready = self.root / "ready"
        target = """import os,pathlib,signal,time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=os.fork()
if child==0:
 os.write(1,b'child-output\\x00\\xff');time.sleep(20)
else:
 pathlib.Path(%r).write_text(str(os.getpid())+','+str(child))
 os.write(1,b'leader-output');os.waitpid(child,0)
""" % str(ready)
        guard = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(20)"], start_new_session=True)
        self.addCleanup(lambda: guard.poll() is None and guard.kill())
        self.addCleanup(lambda: guard.poll() is not None or guard.terminate())
        service = self.start_service(target)
        self.wait_for(lambda: ready.exists() and (self.folder / "output.bin").exists()
                      and len((self.folder / "output.bin").read_bytes()) == len(b"child-output\x00\xffleader-output"))
        before = (self.folder / "output.bin").read_bytes()
        service.kill()
        service.wait(timeout=3)
        receipt = self.wait_for(lambda: supervised.read_receipt(self.folder, self.owner))
        self.assertEqual(receipt["reason"], "owner_lost")
        self.assertEqual(receipt["returncode"], 125)
        self.assertTrue(receipt["cleanup"]["complete"], receipt)
        self.assertTrue(receipt["cleanup"]["kill_sent"], receipt)
        self.assertEqual((self.folder / "output.bin").read_bytes(), before)
        for pid in map(int, ready.read_text().split(",")):
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
        self.assertIsNone(guard.poll())
        guard.terminate()
        guard.wait(timeout=2)

    def test_service_dies_after_supervisor_spawn_before_ack_never_starts_target(self):
        target_marker = self.root / "target-was-started"
        prelude = """original=managed.subprocess.Popen
def kill_before_return(*args,**kwargs):
 process=original(*args,**kwargs)
 os.kill(os.getpid(),signal.SIGKILL)
managed.subprocess.Popen=kill_before_return"""
        service = self.start_service("from pathlib import Path;Path(%r).write_text('ran')" % str(target_marker), prelude)
        service.wait(timeout=3)
        receipt = self.wait_for(lambda: supervised.read_receipt(self.folder, self.owner))
        self.assertEqual(receipt["reason"], "owner_lost")
        self.assertIsNone(receipt["pid"])
        self.assertTrue(receipt["cleanup"]["no_spawn"])
        self.assertFalse(target_marker.exists())

    def test_service_dies_in_spawn_callback_still_has_owner_lost_receipt(self):
        service = self.start_service("import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(20)",
                                     hook="lambda pid,pgid: os.kill(os.getpid(),signal.SIGKILL)")
        service.wait(timeout=3)
        receipt = self.wait_for(lambda: supervised.read_receipt(self.folder, self.owner))
        self.assertEqual(receipt["reason"], "owner_lost")
        self.assertTrue(receipt["cleanup"]["complete"])

    def test_owner_loss_drains_term_handler_output_and_never_recovers_exit_zero_as_success(self):
        ready = self.root / "ready"
        target = """import os,pathlib,signal,time
def stop(*args):
 os.write(1,b'last-bytes\\x00\\xff');raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
os.write(1,b'before-stop')
pathlib.Path(%r).touch()
time.sleep(20)
""" % str(ready)
        service = self.start_service(target)
        self.wait_for(ready.exists)
        service.kill()
        service.wait(timeout=3)
        receipt = self.wait_for(lambda: supervised.read_receipt(self.folder, self.owner))
        self.assertEqual(receipt["process_returncode"], 0)
        self.assertEqual(receipt["reason"], "owner_lost")
        self.assertEqual(receipt["returncode"], 125)
        self.assertTrue(receipt["cleanup"]["complete"])
        self.assertEqual((self.folder / "output.bin").read_bytes(), b"before-stoplast-bytes\x00\xff")

    def test_deadline_includes_supervisor_startup(self):
        original = subprocess.Popen
        def slow_spawn(*args, **kwargs):
            time.sleep(.3)
            return original(*args, **kwargs)
        with patch.object(supervised.subprocess, "Popen", side_effect=slow_spawn):
            result = self.run_code("raise RuntimeError('must never execute')", timeout=.15)
        self.assertEqual(result.reason, "timeout")
        self.assertIsNone(result.pid)
        self.assertLess(result.elapsed, 1)
        self.assert_clean(result)

    def test_cancel_and_blocked_stdin_do_not_block_group_cleanup(self):
        cancel = threading.Event()
        result = self.run_code("import os,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);os.write(1,b'ready');time.sleep(20)",
                               stdin=b"x" * 4_000_000, timeout=5, cancel_event=cancel,
                               on_output=lambda text: cancel.set(), terminate_grace=.1)
        self.assertEqual(result.reason, "cancelled")
        self.assertEqual(result.returncode, 130)
        self.assertEqual(result.output_bytes, b"ready")
        self.assertTrue(result.cleanup["kill_sent"])
        self.assert_clean(result)

    def test_cancellation_already_requested_never_starts_target(self):
        cancel = threading.Event()
        cancel.set()
        read_json, polls = supervised._json, []
        def delay_poll_after_early_cancel(path):
            if Path(path).name == "supervisor.json":
                polls.append(1)
                if len(polls) == 2:
                    time.sleep(.2)  # Let the real worker consume C and finish.
                value = read_json(path)
                if len(polls) == 1:
                    return dict(value, phase="planned")
                return value
            return read_json(path)
        with patch.object(supervised, "_json", side_effect=delay_poll_after_early_cancel):
            result = self.run_code("raise RuntimeError('must never execute')", timeout=3, cancel_event=cancel)
        self.assertEqual(result.reason, "cancelled")
        self.assertIsNone(result.pid)
        self.assert_clean(result)

    def test_cancel_after_worker_timeout_uses_sealed_receipt_not_broken_pipe(self):
        cancel = threading.Event()
        read_json, popen = supervised._json, supervised.subprocess.Popen
        processes, gated = [], []
        def spawn(*args, **kwargs):
            process = popen(*args, **kwargs)
            processes.append(process)
            return process
        def after_timeout(path):
            value = read_json(path)
            if Path(path).name == "supervisor.json" and value.get("phase") == "running" and not gated:
                gated.append(True)
                self.wait_for(lambda: (self.folder / "supervisor-result.json").exists())
                # Reap the real supervisor before the late control write: its pipe
                # reader is now certainly closed, independent of scheduling speed.
                processes[0].wait(timeout=3)
                cancel.set()
            return value
        with patch.object(supervised.subprocess, "Popen", side_effect=spawn), patch.object(supervised, "_json", side_effect=after_timeout):
            result = self.run_code("import os,time;os.write(1,b'full-timeout-output');time.sleep(20)",
                                   timeout=1, terminate_grace=.1, cancel_event=cancel)
        self.assertTrue(gated)
        self.assertEqual(result.reason, "timeout")
        self.assertEqual(result.output_bytes, b"full-timeout-output")
        self.assert_clean(result)

    def test_missing_executable_returns_launch_error_and_proven_no_spawn(self):
        missing = self.root / "this-executable-does-not-exist"
        spawned = []
        result = supervised.run_supervised([str(missing)], folder=self.folder, owner=self.owner,
                                           timeout=3, on_spawn=lambda pid, pgid: spawned.append((pid, pgid)))
        self.assertEqual(result.reason, "error")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FileNotFoundError", result.error)
        self.assertIn("No such file or directory", result.error)
        self.assertEqual(spawned, [])
        self.assertIsNone(result.pid)
        self.assertIsNone(result.pgid)
        self.assertTrue(result.cleanup["no_spawn"])
        self.assert_clean(result)
        self.assertEqual(result.output_bytes, b"")
        self.assertEqual((self.folder / "output.bin").read_bytes(), b"")
        self.assertEqual(supervised.read_receipt(self.folder, self.owner)["error"], result.error)

    def test_output_callback_failure_cleans_target_while_retaining_original_binary(self):
        def fail(text):
            raise RuntimeError("synthetic presentation failure")
        with self.assertRaisesRegex(RuntimeError, "synthetic presentation failure") as caught:
            self.run_code("import os,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);os.write(1,b'raw\\x00\\xff');time.sleep(20)",
                           timeout=5, on_output=fail, terminate_grace=.1)
        self.assert_clean(caught.exception.process_result)
        self.assertEqual(caught.exception.process_result.output_bytes, b"raw\x00\xff")
        self.assertEqual((self.folder / "output.bin").read_bytes(), b"raw\x00\xff")

    def test_spawn_callback_failure_reclaims_target_and_keeps_receipt(self):
        def fail(*args):
            raise RuntimeError("synthetic spawn sink failed")
        with self.assertRaisesRegex(RuntimeError, "synthetic spawn sink failed") as caught:
            self.run_code("import time;time.sleep(20)", timeout=5, on_spawn=fail)
        self.assert_clean(caught.exception.process_result)
        self.assertNotEqual(caught.exception.process_result.returncode, 0)
        self.assertIsNotNone(supervised.read_receipt(self.folder, self.owner))

    def test_environment_is_not_persisted_and_existing_evidence_is_never_overwritten(self):
        secret = "test-value-not-for-receipts-123456"
        env = dict(os.environ, SUPERVISED_PRIVATE_TEST=secret)
        result = self.run_code("import os;assert os.environ['SUPERVISED_PRIVATE_TEST']", env=env, timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(all(secret not in p.read_text() for p in self.folder.iterdir() if p.suffix == ".json"))
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_code("raise RuntimeError('must never run')")
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.folder.iterdir()})

    def test_modified_nonce_or_raw_output_is_never_accepted_as_complete(self):
        self.run_code("print('raw evidence')", timeout=3)
        final = self.folder / "supervisor-result.json"
        original = final.read_bytes()
        receipt = json.loads(original)
        receipt["nonce"] = "different-attempt"
        final.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            supervised.read_receipt(self.folder, self.owner)
        final.write_bytes(original)
        (self.folder / "output.bin").write_bytes(b"changed evidence")
        with self.assertRaisesRegex(ValueError, "does not match"):
            supervised.read_receipt(self.folder, self.owner)

    def test_unexpected_supervisor_death_reports_unknown_cleanup_without_pid_reaping(self):
        def kill_worker(pid, pgid):
            progress = json.loads((self.folder / "supervisor.json").read_text())
            os.kill(progress["supervisor_pid"], signal.SIGKILL)
        try:
            with self.assertRaisesRegex(ValueError, "without a complete receipt") as caught:
                self.run_code("import time;time.sleep(20)", timeout=5, on_spawn=kill_worker)
            self.assertFalse(caught.exception.process_result.cleanup["complete"])
            self.assertIsNone(supervised.read_receipt(self.folder, self.owner))
        finally:
            progress = json.loads((self.folder / "supervisor.json").read_text())
            try:
                os.killpg(progress["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
