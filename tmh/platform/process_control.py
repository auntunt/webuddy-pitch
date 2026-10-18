"""Bound the lifetime of one POSIX process group, including its inherited pipes.

Only the new session created here is signalled. Descendants which deliberately
create another session are outside this contract; unresolved pipes or group
members are reported as incomplete cleanup, never successful execution.
Callbacks run synchronously and must return promptly. Raw bytes are retained
even when a producer emits invalid UTF-8; text callbacks use replacement decoding.
"""
from __future__ import annotations

import codecs
import math
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProcessResult:
    returncode: int
    reason: str
    elapsed: float
    pid: Optional[int]
    pgid: Optional[int]
    output: str
    output_bytes: bytes
    cleanup: dict
    process_returncode: Optional[int] = None


def _group_exists(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Unknown is not evidence of successful cleanup.
    return True


class _OwnedProcess:
    def __init__(self, proc, started, deadline, cancel_event, callback, stdin, grace, selector):
        self.proc, self.started, self.deadline = proc, started, deadline
        self.cancel_event, self.callback, self.grace = cancel_event, callback, grace
        self.selector = selector
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.raw = bytearray()
        self.pending = memoryview(stdin)
        self.written = 0
        self.eof = False
        self.reason = "exited"
        self.stop_at = self.kill_at = None
        self.leader_exited_at = None
        self.cleanup = {"trigger": None, "term_sent": False, "kill_sent": False,
                        "signals": [], "errors": [], "remaining_group": False,
                        "output_complete": False, "reaped": False, "complete": False}

    def setup(self):
        os.set_blocking(self.proc.stdout.fileno(), False)
        self.selector.register(self.proc.stdout, selectors.EVENT_READ, "stdout")
        if self.proc.stdin is not None:
            os.set_blocking(self.proc.stdin.fileno(), False)
            if self.pending:
                self.selector.register(self.proc.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                self.proc.stdin.close()

    def close_stdin(self):
        stream = self.proc.stdin
        if stream is not None and not stream.closed:
            try:
                self.selector.unregister(stream)
            except KeyError:
                pass
            try:
                stream.close()
            except OSError as exc:
                self.cleanup["errors"].append(str(exc))

    def send(self, sig):
        event = {"signal": signal.Signals(sig).name, "at": time.monotonic() - self.started,
                 "sent": False}
        try:
            os.killpg(self.proc.pid, sig)
            event["sent"] = True
            self.cleanup["term_sent" if sig == signal.SIGTERM else "kill_sent"] = True
        except ProcessLookupError:
            pass
        except OSError as exc:
            event["error"] = str(exc)
            self.cleanup["errors"].append(str(exc))
        self.cleanup["signals"].append(event)

    def stop(self, reason):
        if self.stop_at is not None:
            return
        self.reason = reason
        self.cleanup["trigger"] = reason
        self.stop_at = time.monotonic()
        self.send(signal.SIGTERM)
        self.close_stdin()

    def read(self):
        try:
            chunk = os.read(self.proc.stdout.fileno(), 65536)
        except BlockingIOError:
            return
        if chunk:
            self.raw.extend(chunk)
            text = self.decoder.decode(chunk)
        else:
            self.eof = True
            self.selector.unregister(self.proc.stdout)
            self.proc.stdout.close()
            text = self.decoder.decode(b"", final=True)
        if text and self.callback is not None:
            self.callback(text)
        if chunk:
            # The caller may spend time persisting this chunk. Only time with
            # no pipe progress counts toward detecting an escaped pipe holder;
            # a normal producer can have exited before its last buffered bytes
            # and EOF are observed.
            self.leader_exited_at = None

    def write(self):
        try:
            self.written += os.write(self.proc.stdin.fileno(), self.pending[self.written:self.written + 65536])
        except BlockingIOError:
            return
        except BrokenPipeError:
            self.close_stdin()
            return
        if self.written == len(self.pending):
            self.close_stdin()

    def pump(self):
        while True:
            now = time.monotonic()
            code = self.proc.poll()
            if self.stop_at is None:
                if self.cancel_event is not None and self.cancel_event.is_set():
                    self.stop("cancelled")
                elif self.deadline is not None and now >= self.deadline:
                    self.stop("timeout")
                elif code is not None:
                    if _group_exists(self.proc.pid):
                        self.stop("orphaned")
                    elif self.eof:
                        break
                    else:
                        # Drain buffered output first. read() resets this idle
                        # clock after output callbacks complete, so useful
                        # draining time cannot make a normal exit an orphan.
                        if self.leader_exited_at is None:
                            self.leader_exited_at = now
                        elif now - self.leader_exited_at >= .1:
                            self.stop("orphaned")
            if self.stop_at is not None:
                remaining = _group_exists(self.proc.pid)
                if code is not None and not remaining and self.eof:
                    break
                if self.kill_at is None and now >= self.stop_at + self.grace:
                    self.send(signal.SIGKILL)
                    self.kill_at = now
                # SIGKILL normally yields EOF immediately. Bound failed cleanup
                # (for example an escaped pipe holder) and report it explicitly.
                if self.kill_at is not None and now >= self.kill_at + 1.0:
                    break
            wait = .05
            if self.stop_at is None and self.deadline is not None:
                wait = min(wait, max(0, self.deadline - now))
            for key, _ in self.selector.select(wait):
                if key.data == "stdout":
                    self.read()
                else:
                    self.write()

    def result(self):
        code = self.proc.poll()
        self.cleanup.update(remaining_group=_group_exists(self.proc.pid),
                            output_complete=self.eof, reaped=code is not None)
        self.cleanup["complete"] = (not self.cleanup["remaining_group"] and self.eof and code is not None)
        reason = self.reason if self.cleanup["complete"] else "cleanup_failed"
        status = code if reason == "exited" else {"timeout": 124, "cancelled": 130}.get(reason, 125)
        raw = bytes(self.raw)
        return ProcessResult(status, reason, time.monotonic() - self.started,
                             self.proc.pid, self.proc.pid, raw.decode("utf-8", "replace"),
                             raw, self.cleanup, code)

    def close(self):
        self.close_stdin()
        if not self.proc.stdout.closed:
            self.proc.stdout.close()
        self.selector.close()


def run_process(cmd, *, cwd=None, env=None, timeout=None, cancel_event=None,
                on_output=None, stdin=None, on_spawn=None, terminate_grace=.3):
    """Run argv in its own session, returning complete output and cleanup evidence.

    ``timeout`` is a remaining wall-clock allowance, including pipe I/O. stdin
    accepts str or bytes, and is written without blocking deadline checks.
    ``on_spawn(pid, pgid)`` runs after spawn. Both callbacks must return promptly.
    Callback/OS exceptions are re-raised *after* owned-group cleanup; when
    possible, the exception carries ``process_result`` with retained output.
    Root exit with remaining group members yields ``orphaned`` and status 125,
    even if the root returned zero. Timeout/cancellation yield 124/130.
    """
    if os.name != "posix":
        raise NotImplementedError("run_process requires POSIX process groups")
    if timeout is not None and (not math.isfinite(timeout) or timeout < 0):
        raise ValueError("timeout must be a finite nonnegative number or None")
    if not math.isfinite(terminate_grace) or terminate_grace < 0:
        raise ValueError("terminate_grace must be finite and nonnegative")
    if stdin is not None and not isinstance(stdin, (str, bytes)):
        raise TypeError("stdin must be str, bytes, or None")
    data = stdin.encode("utf-8") if isinstance(stdin, str) else (stdin or b"")
    started = time.monotonic()
    cancelled = cancel_event is not None and cancel_event.is_set()
    if cancelled or timeout == 0:
        reason = "cancelled" if cancelled else "timeout"
        cleanup = {"trigger": reason + "_before_spawn", "term_sent": False, "kill_sent": False,
                   "signals": [], "errors": [], "remaining_group": False,
                   "output_complete": True, "reaped": True, "complete": True}
        return ProcessResult(130 if cancelled else 124, reason, time.monotonic() - started,
                             None, None, "", b"", cleanup)
    # Allocate the selector before creating a child: an allocation/OS failure
    # here must not strand a process which has not yet entered the cleanup scope.
    selector = selectors.DefaultSelector()
    try:
        owned = _OwnedProcess(None, started, started + timeout if timeout is not None else None,
                              cancel_event, on_output, data, terminate_grace, selector)
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0, start_new_session=True)
    except BaseException:
        selector.close()
        raise
    owned.proc = proc
    try:
        owned.setup()
        if on_spawn is not None:
            on_spawn(proc.pid, proc.pid)
        owned.pump()
        return owned.result()
    except BaseException as exc:
        # A failed output sink must never strand its model/build subprocess.
        owned.callback = None
        owned.stop("exception")
        try:
            owned.pump()
        except BaseException as cleanup_error:
            owned.cleanup["errors"].append(str(cleanup_error))
            owned.send(signal.SIGKILL)
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        try:
            exc.process_result = owned.result()
        except (AttributeError, TypeError):
            pass
        raise
    finally:
        owned.close()
