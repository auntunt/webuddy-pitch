"""Real POSIX descendants, pipes and cancellation; no mocked kill success."""
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tmh.platform.process_control import run_process


@unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
class ProcessControlTest(unittest.TestCase):
    def run_python(self, code, **kwargs):
        return run_process([sys.executable, "-u", "-c", code], **kwargs)

    def assert_clean(self, result):
        self.assertTrue(result.cleanup["complete"], result)
        self.assertFalse(result.cleanup["remaining_group"], result)
        self.assertTrue(result.cleanup["output_complete"], result)
        self.assertTrue(result.cleanup["reaped"], result)

    def test_complete_binary_and_split_utf8_output_without_newlines(self):
        chunks = []
        payload = ("汉字" * 70000).encode() + b"\xff\x00end"
        result = self.run_python("import os\nb=('汉字'*70000).encode()+b'\\xff\\x00end'\nfor i in range(0,len(b),7): os.write(1,b[i:i+7])", timeout=5, on_output=chunks.append)
        self.assertEqual(result.reason, "exited")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.output_bytes, payload)
        self.assertEqual(result.output, payload.decode("utf-8", "replace"))
        self.assertEqual("".join(chunks), result.output)
        self.assert_clean(result)

    def test_stdin_is_written_completely_while_stdout_is_drained(self):
        payload = "完整输入。" * 100000
        result = self.run_python("import sys\nsys.stdout.write('ready'*20000);sys.stdout.flush()\nb=sys.stdin.buffer.read();sys.stdout.buffer.write(b)", stdin=payload, timeout=5)
        self.assertEqual(result.output, "ready" * 20000 + payload)
        self.assertEqual(result.returncode, 0)
        self.assert_clean(result)

    def test_blocked_stdin_and_no_newline_output_do_not_block_deadline(self):
        # This checks blocked pipes and escalation, not whether a cold Python
        # interpreter starts within 250ms. Shell builtins emit the exact bytes
        # before exec; ignored SIGTERM survives exec into the sleeping process.
        result = run_process(["/bin/sh", "-c", "trap '' TERM; printf %s partial-without-newline; exec /bin/sleep 20"],
                             stdin=b"x" * 4_000_000, timeout=.25, terminate_grace=.1)
        self.assertEqual(result.reason, "timeout")
        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.output_bytes, b"partial-without-newline")
        self.assertTrue(result.cleanup["term_sent"])
        self.assertTrue(result.cleanup["kill_sent"])
        self.assertLess(result.elapsed, 2)
        self.assert_clean(result)

    def test_cancellation_kills_ignoring_descendant_and_keeps_group_boundary(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(20)"], start_new_session=True)
        self.addCleanup(lambda: unrelated.poll() is None and unrelated.kill())
        self.addCleanup(lambda: unrelated.poll() is None and os.killpg(unrelated.pid, signal.SIGTERM))
        event = threading.Event()
        def cancel_on_ready(text):
            if "ready" in text:
                event.set()
        result = self.run_python("import os,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\npid=os.fork()\nif pid==0:\n print('ready',flush=True);time.sleep(20)\nelse:\n os.waitpid(pid,0)", cancel_event=event, on_output=cancel_on_ready, timeout=5, terminate_grace=.1)
        self.assertEqual(result.reason, "cancelled")
        self.assertEqual(result.returncode, 130)
        self.assertTrue(result.cleanup["kill_sent"])
        self.assertIsNone(unrelated.poll())
        unrelated.terminate()
        unrelated.wait(timeout=2)
        self.assert_clean(result)

    def test_parent_exit_with_descendant_holding_stdout_is_not_success(self):
        result = self.run_python("import os,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nif os.fork()==0:\n child=os.fork()\n if child==0:\n  os.write(1,b'descendant-output');time.sleep(20)\n else:\n  os.waitpid(child,0)\nelse:\n time.sleep(.05);os._exit(0)", timeout=5, terminate_grace=.1)
        self.assertEqual(result.reason, "orphaned")
        self.assertEqual(result.returncode, 125)
        self.assertEqual(result.process_returncode, 0)
        self.assertEqual(result.output_bytes, b"descendant-output")
        self.assertTrue(result.cleanup["kill_sent"])
        self.assertLess(result.elapsed, 2)
        self.assert_clean(result)

    def test_silent_process_with_blocked_stdin_can_be_cancelled(self):
        event = threading.Event()
        timer = threading.Timer(.2, event.set)
        self.addCleanup(timer.cancel)
        result = self.run_python("import signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\ntime.sleep(20)",
                                 stdin=b"x" * 4_000_000, timeout=5, cancel_event=event,
                                 on_spawn=lambda pid, pgid: timer.start(), terminate_grace=.1)
        self.assertEqual(result.reason, "cancelled")
        self.assertEqual(result.returncode, 130)
        self.assertEqual(result.output_bytes, b"")
        self.assertLess(result.elapsed, 2)
        self.assert_clean(result)

    def test_descendants_are_reclaimed_even_after_output_eof(self):
        result = self.run_python("import os,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nif os.fork()==0:\n os.close(1);os.close(2);time.sleep(20)\nelse:\n os._exit(0)", timeout=5, terminate_grace=.1)
        self.assertEqual(result.reason, "orphaned")
        self.assertNotEqual(result.returncode, 0)
        self.assert_clean(result)

    def test_output_callback_failure_still_reclaims_group(self):
        def broken(text):
            raise RuntimeError("output sink failed")
        with self.assertRaisesRegex(RuntimeError, "output sink failed") as caught:
            self.run_python("import signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nprint('ready',flush=True);time.sleep(20)", on_output=broken, timeout=5, terminate_grace=.1)
        result = caught.exception.process_result
        self.assertIn("ready", result.output)
        self.assertEqual(result.cleanup["trigger"], "exception")
        self.assert_clean(result)

    def test_spawn_callback_failure_still_reclaims_group(self):
        def broken(pid, pgid):
            self.assertEqual(pid, pgid)
            self.assertNotEqual(pgid, os.getpgrp())
            raise RuntimeError("spawn hook failed")
        with self.assertRaisesRegex(RuntimeError, "spawn hook failed") as caught:
            self.run_python("import time;time.sleep(20)", on_spawn=broken, timeout=5)
        self.assert_clean(caught.exception.process_result)

    def test_preexisting_cancellation_and_zero_budget_never_spawn(self):
        event = threading.Event()
        event.set()
        for kwargs, reason in [({"cancel_event": event}, "cancelled"), ({"timeout": 0}, "timeout")]:
            result = run_process(["/definitely/not/an/executable"], **kwargs)
            self.assertEqual(result.reason, reason)
            self.assertIsNone(result.pid)
            self.assert_clean(result)

    def test_nonzero_exit_remains_nonzero_and_term_handler_output_is_preserved(self):
        result = self.run_python("import sys;print('failure');sys.exit(7)", timeout=2)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.reason, "exited")
        self.assert_clean(result)
        result = self.run_python("import os,signal,time\ndef stop(*args):\n os.write(1,b'term-handler-final-output');raise SystemExit(0)\nsignal.signal(signal.SIGTERM,stop)\nprint('ready',flush=True)\ntime.sleep(20)", timeout=.25, terminate_grace=.3)
        self.assertEqual(result.reason, "timeout")
        self.assertIn(b"term-handler-final-output", result.output_bytes)
        self.assertFalse(result.cleanup["kill_sent"])
        self.assert_clean(result)

    def test_buffered_output_after_leader_exit_is_not_an_orphan(self):
        chunks = []
        def persist(text):
            chunks.append(text)
            time.sleep(.15)  # A real output sink can briefly wait on storage.
        result = self.run_python("import os;os.write(1,b'x'*4096)", timeout=3,
                                 on_spawn=lambda pid, pgid: time.sleep(.1), on_output=persist)
        self.assertEqual(result.reason, "exited")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.output_bytes, b"x" * 4096)
        self.assertEqual("".join(chunks), result.output)
        self.assertFalse(result.cleanup["term_sent"])
        self.assert_clean(result)

    def test_busy_stdout_cannot_starve_deadline_checks(self):
        # This tests draining a busy pipe, not cold Python startup. A 200ms
        # budget could legitimately expire before Python emits its first byte
        # during the full suite. Use native shell builtins and a startup margin,
        # while tightening the former 2s overall completion assertion.
        reads = []
        def consume(chunk):
            reads.append(len(chunk))
            time.sleep(.005)  # Keep the pipe busy without collecting huge logs.
        result = run_process(["/bin/sh", "-c", "while :; do printf '%4096s' x; done"],
                             timeout=1, terminate_grace=.1, on_output=consume)
        self.assertEqual(result.reason, "timeout")
        self.assertGreater(len(reads), 1, "fixture must reach continuous output before its deadline")
        self.assertGreater(len(result.output_bytes), 4096)
        self.assertEqual(sum(reads), len(result.output_bytes))
        self.assertLess(result.elapsed, 1.5)
        self.assert_clean(result)

    def test_idle_pipe_outside_owned_group_reports_incomplete_cleanup(self):
        # A deliberately escaped session is outside the helper's ownership.
        # It must report unresolved EOF and must not signal that other group.
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "escaped-pid"
            code = "import os,pathlib,time\np=pathlib.Path(%r)\nif os.fork()==0:\n os.setsid();p.write_text(str(os.getpid()));time.sleep(20)\nelse:\n while not p.exists():time.sleep(.001)\n os._exit(0)" % str(marker)
            try:
                result = self.run_python(code, timeout=3, terminate_grace=.05)
                escaped = int(marker.read_text())
                os.kill(escaped, 0)
                self.assertEqual(result.reason, "cleanup_failed")
                self.assertEqual(result.returncode, 125)
                self.assertFalse(result.cleanup["remaining_group"])
                self.assertFalse(result.cleanup["output_complete"])
                self.assertFalse(result.cleanup["complete"])
                self.assertFalse(result.cleanup["term_sent"])
                self.assertFalse(result.cleanup["kill_sent"])
                self.assertLess(result.elapsed, 2)
            finally:
                if marker.exists():
                    try:
                        os.kill(int(marker.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
