"""Root-owned completion projection, bound to one original supervised attempt.

The private HTTP journal stays on the host. This small projection cannot by
itself admit a result: the original SP output, owner and successful cleanup are
checked as well. There is no model, task or approval authority here.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid

from .supervised_process import read_receipt

ROOT_UID = 0
SCHEMA = "codex-root-completion-v1"
MAX_RECEIPT = 64 * 1024
CLEANUP = {"listener_FDs_closed": True, "owned_worker_reaped": True,
           "server_errors": [], "server_threads_joined": True}
EXECUTION_FIELDS = ("bin", "args", "engine", "profile", "prompt_transport", "resume", "retry_busy",
                    "timeout", "sha256", "size", "mtime_ns")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def execution_binding(settings):
    if set(settings) - set(EXECUTION_FIELDS) - {"run_timeout"} or any(k not in settings for k in EXECUTION_FIELDS):
        raise OSError("complete frozen task execution fields required")
    value = {k: settings[k] for k in EXECUTION_FIELDS}
    if (value["engine"] != "codex" or value["prompt_transport"] != "stdin"
            or value["resume"] is not False or value["retry_busy"] is not False
            or not isinstance(value["bin"], str) or not Path(value["bin"]).is_absolute()
            or not isinstance(value["profile"], str) or not value["profile"]
            or not isinstance(value["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
            or type(value["size"]) is not int or value["size"] <= 0
            or type(value["mtime_ns"]) is not int or value["mtime_ns"] < 0
            or type(value["timeout"]) not in (int, float) or not math.isfinite(value["timeout"]) or value["timeout"] <= 0
            or type(value["args"]) is not list or any(not isinstance(s, str) for s in value["args"])
            or tuple(value["args"]) not in ((), ("--ephemeral",), ("--color", "never"),
                ("--ephemeral", "--color", "never"), ("--color", "never", "--ephemeral"))):
        raise OSError("invalid frozen task execution fields")
    return json.loads(encoded(value))


def binding(context, frozen_binding, controller_sha256):
    if (type(context.run_id) is not int or context.run_id <= 0
            or not re.fullmatch(r"[0-9a-f]{32}", context.launch_nonce)
            or not re.fullmatch(r"[0-9a-f]{64}", controller_sha256)
            or type(context.deadline_monotonic) not in (int, float)
            or not math.isfinite(context.deadline_monotonic)):
        raise OSError("invalid original carrier identity")
    owner = dict(context.owner)
    if (set(owner) != {"token", "run_id", "data_dir"} or type(owner["run_id"]) is not int
            or owner["run_id"] != context.run_id or not isinstance(owner["data_dir"], str)
            or not isinstance(owner["token"], str) or not owner["token"]):
        raise OSError("invalid original carrier owner")
    raw = context.prompt.encode("utf-8")
    return {"run_id": context.run_id, "launch_nonce": context.launch_nonce, "owner": owner,
            "deadline_monotonic": context.deadline_monotonic,
            "prompt": {"bytes": len(raw), "sha256": digest(raw)},
            "configuration": frozen_binding, "execution": execution_binding(context.settings),
            "controller_sha256": controller_sha256}


def current(context):
    if context.cancel_event.is_set() or time.monotonic() >= context.deadline_monotonic:
        raise OSError("original carrier cancelled or expired")


def open_root(root, gid=None):
    """Hold the full directory chain; no symlink or writable ancestor allowed."""
    root = Path(root)
    if not root.is_absolute() or ".." in root.parts:
        raise OSError("absolute fixed completion root required")
    fd = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in root.parts[1:]:
            before = os.fstat(fd)
            if before.st_uid not in (0, ROOT_UID) or before.st_mode & 0o022:
                raise OSError("untrusted completion ancestor")
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        info = os.fstat(fd)
        if info.st_uid != ROOT_UID or info.st_mode & 0o022:
            raise OSError("completion root must be root-owned and immutable to the service")
        if gid is not None and (info.st_gid != gid or stat.S_IMODE(info.st_mode) != 0o750):
            raise OSError("completion root must have the registered read-only service group")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_projection(root, nonce, gid):
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise OSError("invalid completion nonce")
    base = open_root(root, gid)
    try:
        anchor = os.fstat(base)
        name = nonce + ".json"
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=base)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != ROOT_UID or before.st_gid != gid
                    or stat.S_IMODE(before.st_mode) != 0o640 or before.st_nlink != 1
                    or before.st_size > MAX_RECEIPT):
                raise OSError("untrusted or oversized complete projection")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_RECEIPT + 1)
            if (len(raw) != before.st_size or _identity(before) != _identity(os.fstat(fd))
                    or _identity(before) != _identity(os.stat(name, dir_fd=base, follow_symlinks=False))):
                raise OSError("completion projection changed during full read")
        finally:
            os.close(fd)
        check = open_root(root, gid)
        try:
            if (anchor.st_dev, anchor.st_ino) != (os.fstat(check).st_dev, os.fstat(check).st_ino):
                raise OSError("completion root path replaced")
        finally:
            os.close(check)
    finally:
        os.close(base)
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate completion field")
            out[key] = value
        return out
    def constant(value):
        raise ValueError("non-finite completion field")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError):
        raise OSError("invalid complete projection JSON") from None


def publish_projection(root, nonce, gid, value):
    """First publication wins; root writer never replaces an old completion."""
    if os.geteuid() != ROOT_UID or not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise OSError("root-only completion publication required")
    raw = encoded(value)
    if len(raw) > MAX_RECEIPT:
        raise OSError("complete projection exceeds the schema limit")
    base = open_root(root, gid)
    temporary = ".pending-" + uuid.uuid4().hex
    created = False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=base)
        created = True
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fchown(stream.fileno(), ROOT_UID, gid)
            os.fchmod(stream.fileno(), 0o640)
            os.fsync(stream.fileno())
        os.link(temporary, nonce + ".json", src_dir_fd=base, dst_dir_fd=base, follow_symlinks=False)
        os.unlink(temporary, dir_fd=base)
        created = False
        os.fsync(base)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=base)
        finally:
            os.close(base)


def verify_completion(root, gid, expected, context, process, folder):
    current(context)
    receipt = read_receipt(folder, owner=dict(context.owner))
    if (receipt is None or encoded(receipt["owner"]) != encoded(dict(context.owner))
            or process.returncode != 0 or process.reason != "exited" or not process.cleanup.get("complete")
            or receipt["returncode"] != 0 or receipt["pid"] != process.pid or receipt["pgid"] != process.pgid
            or (folder / "output.bin").read_bytes() != process.output_bytes):
        raise OSError("original supervision does not match completion")
    value = read_projection(root, context.launch_nonce, gid)
    keys = {"schema", "binding", "worker_exit", "cleanup", "stdout", "private_journal", "gateway_attempts", "completed_payloads"}
    if (not isinstance(value, dict) or set(value) != keys or value["schema"] != SCHEMA
            or encoded(value["binding"]) != encoded(expected) or type(value["worker_exit"]) is not int
            or value["worker_exit"] != 0 or encoded(value["cleanup"]) != encoded(CLEANUP)
            or encoded(value["stdout"]) != encoded({"bytes": len(process.output_bytes), "sha256": digest(process.output_bytes)})):
        raise OSError("root completion binding or cleanup mismatch")
    journal = value["private_journal"]
    if (not isinstance(journal, dict) or set(journal) != {"bytes", "sha256", "closed"}
            or journal["closed"] is not True or type(journal["bytes"]) is not int or journal["bytes"] < 0
            or not isinstance(journal["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", journal["sha256"])
            or any(type(value[k]) is not int or value[k] < 0 for k in ("gateway_attempts", "completed_payloads"))
            or value["completed_payloads"] > value["gateway_attempts"]):
        raise OSError("invalid private journal completion")
    current(context)
