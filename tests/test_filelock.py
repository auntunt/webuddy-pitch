"""Native lock lifetime and Windows backend contract; no services or external network."""
import errno
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from tmh.platform import filelock


class FileLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tmh-filelock-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "owner.lock"

    def test_exclusion_unlock_and_close_release(self):
        with self.path.open("a+b") as first, self.path.open("a+b") as second:
            filelock.try_lock(first)
            with self.assertRaises(BlockingIOError):
                filelock.try_lock(second)
            filelock.unlock(first)
            filelock.try_lock(second)
            second.close()
            filelock.try_lock(first)
        with self.path.open("a+b") as third:
            filelock.try_lock(third)
            filelock.unlock(third)

    def test_blocking_waits_for_owner_and_then_acquires(self):
        attempted, acquired = threading.Event(), threading.Event()
        errors = []

        def take():
            try:
                with self.path.open("a+b") as second:
                    attempted.set()
                    filelock.try_lock(second, blocking=True)
                    acquired.set()
                    filelock.unlock(second)
            except BaseException as exc:
                errors.append(exc)

        with self.path.open("a+b") as first:
            filelock.try_lock(first)
            worker = threading.Thread(target=take, daemon=True)
            worker.start()
            try:
                self.assertTrue(attempted.wait(3))
                self.assertFalse(acquired.wait(.05))
            finally:
                filelock.unlock(first)
            worker.join(3)
            self.assertFalse(worker.is_alive(), errors)
            self.assertFalse(errors)
            self.assertTrue(acquired.is_set())

    @unittest.skipUnless(os.name == "posix", "real killed-owner proof is POSIX-only")
    def test_killed_process_releases_lock_without_removing_the_file(self):
        marker = self.root / "ready"
        script = (
            "import pathlib,sys\nfrom tmh.platform.filelock import try_lock\n"
            "f=pathlib.Path(sys.argv[1]).open('a+b')\ntry_lock(f)\n"
            "pathlib.Path(sys.argv[2]).write_text('locked')\nsys.stdin.read()\n")
        child = subprocess.Popen([sys.executable, "-c", script, str(self.path), str(marker)],
                                 cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(marker.exists(), "child did not acquire the lock")
            before = self.path.read_bytes()
            with self.path.open("a+b") as contender:
                with self.assertRaises(BlockingIOError):
                    filelock.try_lock(contender)
                child.kill()
                child.wait(timeout=3)
                filelock.try_lock(contender)
                filelock.unlock(contender)
            self.assertEqual(self.path.read_bytes(), before)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=3)

    @unittest.skipUnless(os.name == "posix", "POSIX shared reader semantics")
    def test_posix_shared_readers_exclude_a_writer(self):
        with self.path.open("a+b") as a, self.path.open("a+b") as b, self.path.open("a+b") as c:
            filelock.try_lock(a, exclusive=False)
            filelock.try_lock(b, exclusive=False)
            with self.assertRaises(BlockingIOError):
                filelock.try_lock(c)
            filelock.unlock(a)
            filelock.unlock(b)
            filelock.try_lock(c)

    def windows_api(self, side_effect=None):
        return SimpleNamespace(LK_NBLCK=2, LK_NBRLCK=4, LK_UNLCK=0,
                               locking=mock.Mock(side_effect=side_effect))

    def test_windows_byte_zero_initialization_offset_and_modes(self):
        def check(fd, mode, count):
            self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 0)
            self.assertEqual(count, 1)

        api = self.windows_api(check)
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": api}):
            with self.path.open("a+b") as stream:
                filelock.try_lock(stream)
                self.assertEqual(stream.tell(), 0)
                self.assertEqual(self.path.read_bytes(), b"\0")
                filelock.unlock(stream)
            self.path.write_bytes(b"original bytes")
            with self.path.open("r+b") as stream:
                stream.seek(3)
                filelock.try_lock(stream, exclusive=False)
                self.assertEqual(stream.tell(), 3)
                filelock.unlock(stream)
                self.assertEqual(stream.tell(), 3)
        self.assertEqual([call.args[1] for call in api.locking.call_args_list], [2, 0, 4, 0])
        self.assertEqual(self.path.read_bytes(), b"original bytes")

    def test_windows_nonblocking_contention_is_normalized_without_writing(self):
        api = self.windows_api(OSError(errno.EACCES, "lock held"))
        self.path.touch()
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": api}):
            with self.path.open("r+b") as stream:
                with self.assertRaises(BlockingIOError):
                    filelock.try_lock(stream)
                self.assertEqual(stream.tell(), 0)
        self.assertEqual(self.path.read_bytes(), b"")

    def test_windows_blocking_retries_beyond_crt_ten_attempts(self):
        api = self.windows_api([OSError(errno.EACCES, "busy") for _ in range(12)] + [None, None])
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": api}), mock.patch.object(filelock.time, "sleep") as sleep:
            with self.path.open("a+b") as stream:
                filelock.try_lock(stream, blocking=True)
                filelock.unlock(stream)
        self.assertEqual(sleep.call_count, 12)
        self.assertEqual(api.locking.call_count, 14)

    def test_windows_non_contention_error_is_not_hidden_or_retried(self):
        api = self.windows_api(OSError(errno.EBADF, "bad descriptor"))
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": api}), mock.patch.object(filelock.time, "sleep") as sleep:
            with self.path.open("a+b") as stream:
                with self.assertRaises(OSError) as raised:
                    filelock.try_lock(stream, blocking=True)
                self.assertEqual(raised.exception.errno, errno.EBADF)
        sleep.assert_not_called()

    def test_windows_initialization_failure_releases_acquired_lock(self):
        api = self.windows_api()
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": api}), \
                mock.patch.object(filelock.os, "write", side_effect=OSError(errno.ENOSPC, "full")):
            with self.path.open("a+b") as stream:
                with self.assertRaises(OSError):
                    filelock.try_lock(stream)
        self.assertEqual([call.args[1] for call in api.locking.call_args_list], [2, 0])

    def test_four_consumers_import_and_use_windows_backend_without_fcntl(self):
        api = self.windows_api()
        modules = {}
        folder = Path(filelock.__file__).parent
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": api}):
            for name in ("crash_recovery", "recheck_operations", "candidates", "harness_probes"):
                spec = importlib.util.spec_from_file_location("tmh.platform._filelock_test_" + name, folder / (name + ".py"))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                modules[name] = module
            owner = modules["crash_recovery"]._lock(self.root)
            self.assertIsNotNone(owner)
            owner.close()
            with modules["recheck_operations"].source_guard(self.root, 1):
                pass
            with modules["candidates"].guard(SimpleNamespace(data_dir=self.root), 1):
                pass
            with modules["harness_probes"]._completion(self.root):
                pass
            self.assertFalse(modules["harness_probes"]._active(self.path))
            self.assertFalse(modules["recheck_operations"].Operations._owner_active(None, self.root))
        self.assertGreaterEqual(api.locking.call_count, 11)
        self.assertEqual(self.path.read_bytes(), b"\0")

    def test_kb_native_windows_lock_and_no_backend_fallback(self):
        from tmh.kb import _Lock
        api = self.windows_api()
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": api}):
            with _Lock(self.path):
                self.assertEqual(self.path.read_bytes(), b"\0")
        self.path.unlink()
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": None}):
            self.assertFalse(filelock.available())
            with _Lock(self.path):
                self.assertTrue(self.path.is_file())
            self.assertFalse(self.path.exists())

    def test_windows_consumers_preserve_busy_errors_and_live_owner_checks(self):
        from tmh.platform import candidates, crash_recovery, harness_probes, recheck_operations
        api = self.windows_api(OSError(errno.EACCES, "lock held"))
        self.path.write_bytes(b"\0")
        with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": api}):
            self.assertIsNone(crash_recovery._lock(self.root))
            self.assertTrue(harness_probes._active(self.path))
            self.assertTrue(recheck_operations.Operations._owner_active(None, self.root))
            with self.assertRaisesRegex(ValueError, "该来源正在复检或处理采纳决定"):
                with recheck_operations.source_guard(self.root, 1):
                    self.fail("busy source entered")
            with self.assertRaisesRegex(candidates.ApiError, "此工单的候选操作正在处理"):
                with candidates.guard(SimpleNamespace(data_dir=self.root), 1):
                    self.fail("busy candidate entered")

    def test_kb_windows_initialization_error_is_not_reported_as_contention(self):
        from tmh.kb import _Lock
        lock = _Lock(self.path)
        api = self.windows_api()
        try:
            with mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": api}), \
                    mock.patch.object(filelock.os, "write", side_effect=OSError(errno.ENOSPC, "full")), \
                    mock.patch.object(filelock.time, "sleep") as sleep:
                with self.assertRaises(OSError) as raised:
                    lock.__enter__()
            self.assertEqual(raised.exception.errno, errno.ENOSPC)
            sleep.assert_not_called()
            self.assertEqual([call.args[1] for call in api.locking.call_args_list], [2, 0])
            with self.assertRaises(OSError) as closed:
                os.fstat(lock.fd)
            self.assertEqual(closed.exception.errno, errno.EBADF)
        finally:
            try:
                os.close(lock.fd)
            except OSError:
                pass

    def test_kb_interrupted_native_acquisition_closes_its_descriptor(self):
        from tmh.kb import _Lock
        lock = _Lock(self.path)
        try:
            with mock.patch.object(filelock, "try_lock", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    lock.__enter__()
            with self.assertRaises(OSError) as closed:
                os.fstat(lock.fd)
            self.assertEqual(closed.exception.errno, errno.EBADF)
        finally:
            try:
                os.close(lock.fd)
            except OSError:
                pass

    def test_kb_native_contention_still_retries_and_times_out_with_closed_descriptor(self):
        from tmh.kb import _Lock
        lock = _Lock(self.path)
        with mock.patch.object(filelock, "try_lock", side_effect=BlockingIOError(errno.EAGAIN, "busy")) as acquire, \
                mock.patch.object(filelock.time, "sleep") as sleep:
            with self.assertRaisesRegex(TimeoutError, "知识库被占用"):
                lock.__enter__()
        self.assertEqual(acquire.call_count, 1200)
        self.assertEqual(sleep.call_count, 1200)
        with self.assertRaises(OSError) as closed:
            os.fstat(lock.fd)
        self.assertEqual(closed.exception.errno, errno.EBADF)


if __name__ == "__main__":
    unittest.main()
