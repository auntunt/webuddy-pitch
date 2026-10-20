"""Kernel-owned locks for dedicated, seekable lock files (streams or raw fds).

POSIX uses flock; Windows locks byte zero through the CRT. Closing the handle
or terminating its process releases ownership. Never unlink a live lock file.
All ownership/guard callers use exclusive locks. CRT read-lock modes may be
more restrictive than POSIX shared locks, so callers must not depend on parallel
readers on Windows. No sentinel-file fallback is safe for ownership leases.
"""
from __future__ import annotations

import errno
import os
import time


def _backend():
    # Lazy imports keep consumers importable even on a host without either API.
    try:
        import fcntl
        return "posix", fcntl
    except ImportError:
        import msvcrt
        return "windows", msvcrt


def available() -> bool:
    """Whether a native backend exists; only kb may use its older fallback."""
    try:
        _backend()
        return True
    except ImportError:
        return False


def _fd(stream):
    return stream if isinstance(stream, int) else stream.fileno()


def _busy(exc):
    return exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) or getattr(exc, "winerror", None) in (33, 36)


def try_lock(stream, exclusive: bool = True, blocking: bool = False) -> None:
    """Acquire a lock, raising BlockingIOError on nonblocking contention.

    Windows initializes an empty writable lock file with one byte *after* the
    byte-range lock is held, avoiding a race that writes into another owner's
    locked byte. Byte ranges may extend beyond EOF. File offsets are preserved.
    """
    backend, api = _backend()
    fd = _fd(stream)
    if backend == "posix":
        mode = api.LOCK_EX if exclusive else api.LOCK_SH
        try:
            api.flock(fd, mode | (0 if blocking else api.LOCK_NB))
        except OSError as exc:
            if not blocking and _busy(exc):
                raise BlockingIOError(exc.errno, str(exc)) from exc
            raise
        return
    if not isinstance(stream, int):
        stream.flush()
    position = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        mode = api.LK_NBLCK if exclusive else api.LK_NBRLCK
        while True:
            try:
                api.locking(fd, mode, 1)
                break
            except OSError as exc:
                if not _busy(exc):
                    raise
                if not blocking:
                    raise BlockingIOError(errno.EAGAIN, str(exc)) from exc
                # LK_LOCK stops after a fixed number of attempts; emulate flock's
                # blocking semantics instead, allowing KeyboardInterrupt as usual.
                time.sleep(0.05)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
        except BaseException:
            os.lseek(fd, 0, os.SEEK_SET)
            api.locking(fd, api.LK_UNLCK, 1)
            raise
    finally:
        os.lseek(fd, position, os.SEEK_SET)


def unlock(stream) -> None:
    backend, api = _backend()
    fd = _fd(stream)
    if backend == "posix":
        api.flock(fd, api.LOCK_UN)
        return
    if not isinstance(stream, int):
        stream.flush()
    position = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        api.locking(fd, api.LK_UNLCK, 1)
    finally:
        os.lseek(fd, position, os.SEEK_SET)
