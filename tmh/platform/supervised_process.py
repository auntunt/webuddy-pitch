"""Keep process ownership and raw output alive if the calling service is killed.

The supervisor owns the target Popen and its new process group. Its control pipe
has exactly one writer, the caller. EOF revokes that ownership request and causes
TERM/KILL through process_control; recovery never signals a saved numeric PID.
Deliberate setsid escapes, supervisor SIGKILL and machine failure are outside this
contract and cannot produce a trustworthy complete-cleanup receipt.
"""
from __future__ import annotations

import base64
import codecs
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

if __package__:
    from .process_control import ProcessResult, run_process
else:  # The worker is launched by absolute filename, independent of target cwd.
    from process_control import ProcessResult, run_process


SCHEMA = 1


def _atomic_json(path, data, exclusive=False):
    """Never expose a partial receipt, including when the caller is killed."""
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, path)  # Atomic claim: an existing attempt is immutable.
        else:
            os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _identity(folder, owner):
    if not isinstance(owner, dict) or not isinstance(owner.get("token"), str) or not owner["token"]:
        raise ValueError("supervised process requires an owner token")
    if "run_id" not in owner or not owner.get("data_dir"):
        raise ValueError("supervised process requires run_id and data_dir")
    return {"schema": SCHEMA, "owner": {"token": owner["token"], "run_id": owner["run_id"],
            "data_dir": str(Path(owner["data_dir"]).resolve())},
            "nonce": uuid.uuid4().hex, "folder": str(folder)}


def _json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError("cannot read supervised receipt: " + str(exc)) from exc
    if not isinstance(value, dict):
        raise ValueError("supervised receipt must be an object")
    return value


def read_receipt(folder, owner=None):
    """Read and validate a finished receipt and original output; never mutate.

    No final receipt returns None (it does not prove cleanup). An existing bad
    receipt raises ValueError. The optional owner must match all its supplied
    fields; the caller should supply the persisted run owner when recovering.
    """
    folder = Path(folder).resolve()
    final = folder / "supervisor-result.json"
    if not final.exists():
        return None
    planned, result = _json(folder / "supervisor.json"), _json(final)
    for key in ("schema", "owner", "nonce", "folder"):
        if result.get(key) != planned.get(key):
            raise ValueError("supervised receipt identity mismatch: " + key)
    if result.get("schema") != SCHEMA or result.get("folder") != str(folder):
        raise ValueError("unsupported supervised receipt or wrong folder")
    if not isinstance(result.get("nonce"), str) or not result["nonce"]:
        raise ValueError("missing supervised receipt nonce")
    bound_owner = result.get("owner")
    if not isinstance(bound_owner, dict) or not bound_owner.get("token"):
        raise ValueError("missing supervised receipt owner")
    if owner is not None:
        if isinstance(owner, dict) and "data_dir" in owner:
            owner = dict(owner, data_dir=str(Path(owner["data_dir"]).resolve()))
        if not isinstance(owner, dict) or any(bound_owner.get(k) != v for k, v in owner.items()):
            raise ValueError("supervised receipt belongs to a different run owner")
    if result.get("phase") != "finished" or not isinstance(result.get("cleanup"), dict):
        raise ValueError("supervised receipt is not finished")
    if type(result.get("returncode")) is not int or not isinstance(result.get("reason"), str) or not result["reason"]:
        raise ValueError("invalid supervised result")
    if (type(result.get("elapsed_seconds")) not in (int, float) or
            not math.isfinite(result["elapsed_seconds"]) or result["elapsed_seconds"] < 0):
        raise ValueError("invalid supervised elapsed time")
    for key in ("pid", "pgid", "process_returncode"):
        if result.get(key) is not None and type(result[key]) is not int:
            raise ValueError("invalid supervised process identifier or exit status")
    if result.get("pid") != result.get("pgid") or (result.get("pid") is not None and result["pid"] <= 0):
        raise ValueError("invalid supervised process group binding")
    cleanup = result["cleanup"]
    for key in ("term_sent", "kill_sent", "remaining_group", "output_complete", "reaped", "complete"):
        if type(cleanup.get(key)) is not bool:
            raise ValueError("invalid supervised cleanup evidence: " + key)
    if cleanup["complete"] and (cleanup["remaining_group"] or not cleanup["output_complete"] or not cleanup["reaped"]):
        raise ValueError("contradictory supervised cleanup evidence")
    output = result.get("output")
    if not isinstance(output, dict) or output.get("file") != "output.bin":
        raise ValueError("invalid supervised output binding")
    try:
        raw = (folder / "output.bin").read_bytes()
    except OSError as exc:
        raise ValueError("missing supervised raw output") from exc
    if output.get("bytes") != len(raw) or output.get("sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("supervised raw output does not match its receipt")
    if result["reason"] == "owner_lost" and result["returncode"] != 125:
        raise ValueError("owner-lost execution cannot be successful")
    if result["returncode"] == 0 and (result["reason"] != "exited" or result["cleanup"].get("complete") is not True):
        raise ValueError("incomplete supervised execution cannot be successful")
    return result


def _result(receipt, raw):
    return ProcessResult(receipt["returncode"], receipt["reason"], receipt["elapsed_seconds"],
                         receipt.get("pid"), receipt.get("pgid"), raw.decode("utf-8", "replace"),
                         raw, receipt["cleanup"], receipt.get("process_returncode"), receipt.get("error", ""))


def _empty(reason, elapsed=0, complete=True):
    return ProcessResult({"cancelled": 130, "timeout": 124}.get(reason, 125), reason, elapsed,
                         None, None, "", b"", {"trigger": reason + "_before_spawn", "term_sent": False,
                         "kill_sent": False, "signals": [], "errors": [], "remaining_group": False,
                         "output_complete": complete, "reaped": complete, "complete": complete,
                         "no_spawn": True})


def _worker(request_fd, control_fd):
    with os.fdopen(request_fd, "rb") as source:
        request = json.load(source)
    folder = Path(request["identity"]["folder"])
    identity = request["identity"]
    started = request["started"]
    state = {"reason": "", "started": False}
    state_lock = threading.Lock()
    start_event, cancel = threading.Event(), threading.Event()

    def control():
        try:
            while True:
                token = os.read(control_fd, 1)
                with state_lock:
                    if not token:
                        state["reason"] = "owner_lost"
                        cancel.set()
                        start_event.set()
                        return
                    if token == b"S":
                        state["started"] = True
                        start_event.set()
                    elif token in (b"C", b"E"):
                        if not state["reason"]:
                            state["reason"] = "cancelled" if token == b"C" else "error"
                        cancel.set()
                        start_event.set()
        finally:
            os.close(control_fd)

    monitor = threading.Thread(target=control, daemon=True)
    monitor.start()
    progress = dict(identity, phase="ready", supervisor_pid=os.getpid())
    _atomic_json(folder / "supervisor.json", progress)
    start_event.wait()
    result = None
    error = ""
    try:
        # Open before the target exists. A bad evidence sink must not spawn work.
        with open(folder / "output.bin", "xb", buffering=0) as raw_file:
            def spool(chunk):
                view = memoryview(chunk)
                while view:
                    written = raw_file.write(view)
                    if not written:
                        raise OSError("raw output sink did not accept bytes")
                    view = view[written:]

            def spawned(pid, pgid):
                progress.update(phase="running", pid=pid, pgid=pgid)
                _atomic_json(folder / "supervisor.json", progress)

            with state_lock:
                reason, allowed = state["reason"], state["started"]
            if reason or not allowed:
                result = _empty(reason or "owner_lost")
            else:
                limit = request["timeout"]
                remaining = max(0., limit - (time.monotonic() - started)) if limit is not None else None
                stdin = base64.b64decode(request["stdin"]) if request["stdin"] is not None else None
                try:
                    result = run_process(request["command"], cwd=request["cwd"], timeout=remaining,
                                         cancel_event=cancel, stdin=stdin, on_spawn=spawned, on_bytes=spool,
                                         terminate_grace=request["terminate_grace"])
                except BaseException as exc:
                    error = repr(exc)
                    result = getattr(exc, "process_result", None) or _empty("error")
                    result.reason, result.returncode = "error", 125
                    # If a sink failed, keep its existing prefix and append the
                    # retained bytes where possible; never silently truncate it.
                    offset = raw_file.tell()
                    if offset < len(result.output_bytes):
                        spool(result.output_bytes[offset:])
            raw_file.flush()
            os.fsync(raw_file.fileno())
    except BaseException as exc:
        error = repr(exc)
        if result is None:
            result = _empty("error")
        result.reason, result.returncode = "error", 125
        result.cleanup.setdefault("errors", []).append(error)
    # The pipe is checked again at the commit point, including a target which
    # returned 0 as its caller disappeared. No abandoned attempt becomes success.
    with state_lock:
        reason = state["reason"]
    if os.getppid() != request["parent_pid"]:
        reason = "owner_lost"  # Also closes the monitor-thread scheduling window.
    if reason:
        result.reason = reason
        result.returncode = 130 if reason == "cancelled" else 125
        result.cleanup["trigger"] = reason
    result.elapsed = time.monotonic() - started
    try:
        raw = (folder / "output.bin").read_bytes()
        if raw != result.output_bytes:
            result.cleanup.update(output_complete=False, complete=False)
            result.cleanup.setdefault("errors", []).append("original output could not be completely persisted")
            if result.reason != "owner_lost":
                result.reason, result.returncode = "error", 125
        with open(folder / "output.txt", "x", encoding="utf-8") as text:
            text.write(raw.decode("utf-8", "replace"))
            text.flush()
            os.fsync(text.fileno())
        record = dict(identity, phase="finished", supervisor_pid=os.getpid(), pid=result.pid, pgid=result.pgid,
                      reason=result.reason, returncode=result.returncode, process_returncode=result.process_returncode,
                      elapsed_seconds=result.elapsed, cleanup=result.cleanup, ended_at=time.time(),
                      output={"file": "output.bin", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        if error:
            record["error"] = error
        _atomic_json(folder / "supervisor-result.json", record)
    except BaseException:
        # No final receipt is stronger and safer than claiming output survived.
        return 125
    return 0


def run_supervised(cmd, *, folder, owner, cwd=None, env=None, timeout=None, cancel_event=None,
                   on_output=None, stdin=None, on_spawn=None, terminate_grace=.3):
    """Run a target under a durable supervisor, retaining the ProcessResult API.

    Environment is inherited by the supervisor and target, never written to a
    request or receipt. Input is carried in an anonymous temporary file whose
    descriptor is inherited only by the supervisor. The target gets no control
    pipe descriptor. Calls use a fresh evidence folder and never replace output.
    """
    if os.name != "posix":
        raise NotImplementedError("supervised execution requires POSIX")
    if timeout is not None and (not math.isfinite(timeout) or timeout < 0):
        raise ValueError("timeout must be finite and nonnegative or None")
    if not math.isfinite(terminate_grace) or terminate_grace < 0:
        raise ValueError("terminate_grace must be finite and nonnegative")
    if stdin is not None and not isinstance(stdin, (str, bytes)):
        raise TypeError("stdin must be str or bytes")
    started = time.monotonic()
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("supervisor.json", "supervisor-result.json", "output.bin", "output.txt"):
        if (folder / name).exists():
            raise ValueError("supervised evidence already exists: " + name)
    identity = _identity(folder, owner)
    _atomic_json(folder / "supervisor.json", dict(identity, phase="planned"), exclusive=True)
    data = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
    request = {"identity": identity, "command": cmd, "cwd": str(cwd) if cwd is not None else None,
               "timeout": timeout, "started": started, "terminate_grace": terminate_grace,
               "parent_pid": os.getpid(),
               "stdin": base64.b64encode(data).decode("ascii") if data is not None else None}
    read_fd, write_fd = os.pipe()
    process = None
    error = None
    spawned_pid = None
    offset = 0
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    sent_start = sent_stop = False
    try:
        with tempfile.TemporaryFile() as payload:
            payload.write(json.dumps(request, ensure_ascii=False).encode("utf-8"))
            payload.seek(0)
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), str(payload.fileno()), str(read_fd)],
                                       env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, pass_fds=(payload.fileno(), read_fd),
                                       close_fds=True, start_new_session=True)
        os.close(read_fd)
        read_fd = None
        while True:
            try:
                progress = _json(folder / "supervisor.json")
                if progress.get("nonce") != identity["nonce"]:
                    raise ValueError("supervisor launch identity changed")
                if not sent_start and progress.get("phase") == "ready":
                    token = b"C" if cancel_event is not None and cancel_event.is_set() else b"S"
                    os.write(write_fd, token)
                    sent_start = True
                    sent_stop = token == b"C"
                if not sent_stop and cancel_event is not None and cancel_event.is_set():
                    os.write(write_fd, b"C")
                    # C is itself a terminal launch decision, including while
                    # the worker still reports planned. Do not later send an
                    # ACK to a no-spawn worker that has already finished.
                    sent_start = sent_stop = True
                if progress.get("pid") is not None and spawned_pid is None:
                    spawned_pid = progress["pid"]
                    if on_spawn is not None:
                        on_spawn(progress["pid"], progress["pgid"])
                raw_path = folder / "output.bin"
                if raw_path.exists():
                    with raw_path.open("rb") as raw:
                        raw.seek(offset)
                        # Bound each parent polling pass; the independent worker
                        # enforces its own deadline even if a UI callback is slow.
                        chunk = raw.read(65536)
                        offset += len(chunk)
                    if chunk:
                        text = decoder.decode(chunk)
                        if text and on_output is not None:
                            on_output(text)
            except BaseException as exc:
                if error is None:
                    error = exc
                    on_output = on_spawn = None
                    try:
                        os.write(write_fd, b"E")
                    except OSError:
                        pass
            if process.poll() is not None:
                break
            time.sleep(.01)
        receipt = read_receipt(folder, identity["owner"])
        if receipt is None:
            raise ValueError("supervisor exited without a complete receipt; cleanup is unknown")
        raw = (folder / "output.bin").read_bytes()
        result = _result(receipt, raw)
        if error is None and on_output is not None:
            try:
                tail = decoder.decode(raw[offset:], final=True)
                if tail:
                    on_output(tail)
            except BaseException as exc:
                error = exc
        if error is not None:
            error.process_result = result
            raise error
        return result
    except BaseException as exc:
        if not hasattr(exc, "process_result"):
            # Preserve the spool even for damaged/missing receipts, but never
            # infer cleanup from a saved PID or from the supervisor's exit code.
            raw = (folder / "output.bin").read_bytes() if (folder / "output.bin").exists() else b""
            result = _empty("cleanup_failed", time.monotonic() - started, complete=False)
            result.cleanup.update(no_spawn=False, remaining_group=True)
            result.output_bytes, result.output = raw, raw.decode("utf-8", "replace")
            exc.process_result = result
        raise
    finally:
        if read_fd is not None:
            os.close(read_fd)
        os.close(write_fd)  # EOF also handles exceptional caller exits.


if __name__ == "__main__":
    raise SystemExit(_worker(int(sys.argv[1]), int(sys.argv[2])))
