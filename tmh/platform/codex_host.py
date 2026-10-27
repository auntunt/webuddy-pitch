"""Host assembly candidate for the original SP and a registered root controller.

No controller is installed or admitted here. The fixed root entry must still
provide the v9 namespace/privilege lifecycle, authenticated relay, parent-death
cleanup and exact stdout projection. This module supplies its configuration,
fixed exchange, private journal and completion publication/verification.
"""
import hashlib
import hmac
import os
from pathlib import Path
import re
import stat
import struct
import threading

from .codex_carrier import CarrierLaunch
from .codex_frozen_config import FrozenConfig, worker_command, worker_environment
from .codex_gateway import forward
from . import codex_host_completion as completion


class HostSession:
    def __init__(self, context, frozen, environment, *, expected_configuration,
                 expected_execution, expected_credential_sha256, controller_sha256, private_root, completion_root, service_gid):
        if os.geteuid() != completion.ROOT_UID or type(frozen) is not FrozenConfig:
            raise OSError("trusted root host session required")
        if type(service_gid) is not int or service_gid < 0:
            raise OSError("registered service group required")
        self.context, self.frozen, self.environment = context, frozen, environment
        self.expected_configuration = completion.encoded(expected_configuration)
        self.expected_execution = completion.encoded(completion.execution_binding(expected_execution))
        if not re.fullmatch(r"[0-9a-f]{64}", expected_credential_sha256):
            raise OSError("original private credential identity required")
        # Supplied by the original server-private registration, never a job
        # option or a public receipt. Do not recreate it to bless a rotation.
        self._credential_sha = expected_credential_sha256
        self.binding = completion.binding(context, frozen.binding(), controller_sha256)
        self.completion_root, self.gid = Path(completion_root), service_gid
        self.lock = threading.RLock()
        self.closed = False
        self.attempts = self.completed = self.journal_bytes = 0
        self.journal_digest = hashlib.sha256()
        self._check()
        base = completion.open_root(private_root)
        try:
            if stat.S_IMODE(os.fstat(base).st_mode) != 0o700:
                raise OSError("root-only private journal directory required")
            fd = os.open(context.launch_nonce + ".gateway.bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=base)
            self.stream = os.fdopen(fd, "wb")
        finally:
            os.close(base)

    def _check(self):
        completion.current(self.context)
        self.frozen.assert_current(self.environment)
        if completion.encoded(self.frozen.binding()) != self.expected_configuration:
            raise OSError("original registered configuration differs")
        task = completion.execution_binding(self.context.settings)
        if (task["profile"] != self.frozen.profile or completion.encoded(task) != self.expected_execution
                or self.context.model and self.context.model != self.frozen.model):
            raise OSError("task execution/profile differs from original registration")
        actual = completion.digest(self.frozen.upstream(self.environment)["key"].encode("ascii"))
        if not hmac.compare_digest(actual, self._credential_sha):
            raise OSError("original private credential identity differs")

    def worker_inputs(self):
        with self.lock:
            if self.closed:
                raise OSError("host session already closed")
            self._check()
            return {"command": worker_command(), "environment": worker_environment(),
                    "config": self.frozen.worker_config()}

    def _journal(self, event, value):
        if self.closed:
            raise OSError("private journal already closed")
        raw = value if isinstance(value, bytes) else completion.encoded(value)
        header = completion.encoded({"event": event, "format": "bytes" if isinstance(value, bytes) else "json",
                                     "bytes": len(raw), "sha256": completion.digest(raw)})
        # Complete length-delimited frames, including every body byte. Metadata
        # and payload are both private; none is emitted to the worker or API.
        for part in (struct.pack("!I", len(header)), header, raw):
            self.stream.write(part)
            self.journal_digest.update(part)
            self.journal_bytes += len(part)

    def exchange(self, method, target, headers, body, *, on_headers, on_body):
        # The fixed root controller authenticates its namespace relay before
        # calling here. Serializing exchanges also prevents interleaved frames.
        with self.lock:
            self._check()
            if self.closed:
                raise OSError("host session already closed")
            self.attempts += 1  # local attempts, not wire/model/billing counts
            result = forward(self.frozen, self.environment, method, target, headers, body,
                             deadline=self.context.deadline_monotonic, cancel=self.context.cancel_event,
                             on_headers=on_headers, on_body=on_body, journal=self._journal)
            self.completed += 1  # complete HTTP payload, not model success
            return result

    def close(self):
        with self.lock:
            if not self.closed:
                try:
                    self.stream.flush()
                    os.fsync(self.stream.fileno())
                finally:
                    self.stream.close()
                    self.closed = self.stream.closed

    def complete(self, stdout, worker_exit, namespace_result):
        with self.lock:
            self._check()
            if (not isinstance(stdout, bytes) or type(worker_exit) is not int or worker_exit != 0
                    or namespace_result.get("passed") is not True
                    or completion.encoded(namespace_result.get("cleanup")) != completion.encoded(completion.CLEANUP)):
                raise OSError("trusted namespace lifecycle did not complete")
            self.close()  # all journal flush/close work precedes positive checks
            self._check()
            value = {"schema": completion.SCHEMA, "binding": self.binding, "worker_exit": worker_exit,
                     "stdout": {"bytes": len(stdout), "sha256": completion.digest(stdout)},
                     "cleanup": namespace_result["cleanup"], "gateway_attempts": self.attempts,
                     "completed_payloads": self.completed,
                     "private_journal": {"bytes": self.journal_bytes, "sha256": self.journal_digest.hexdigest(), "closed": True}}
            completion.publish_projection(self.completion_root, self.context.launch_nonce, self.gid, value)
            self._check()  # publication/closure consuming the budget is failure


class RootCarrier:
    """Trusted host dependency, never constructed from public task options."""
    def __init__(self, frozen, environment, *, controller_entry, controller_sha256,
                 registration_id, execution_binding, completion_root, service_gid):
        if type(frozen) is not FrozenConfig or not re.fullmatch(r"[0-9a-f]{64}", registration_id):
            raise OSError("registered fixed root carrier required")
        if type(service_gid) is not int or service_gid < 0:
            raise OSError("registered service group required")
        self.frozen, self.environment = frozen, environment
        self.execution = completion.execution_binding(execution_binding)
        if self.execution["profile"] != frozen.profile:
            raise OSError("registered execution/profile differs from frozen source")
        self.entry, self.entry_sha = Path(controller_entry), controller_sha256
        self.registration = registration_id
        self.completion_root, self.gid = Path(completion_root), service_gid

    def _entry_current(self):
        base = completion.open_root(self.entry.parent)
        try:
            parent_identity = os.fstat(base)
            fd = os.open(self.entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=base)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != completion.ROOT_UID or info.st_nlink != 1
                        or info.st_mode & 0o022 or not info.st_mode & stat.S_IXUSR or info.st_size > 8 * 1024 * 1024):
                    raise OSError("immutable registered root entry required")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    raw = stream.read(info.st_size + 1)
                if (len(raw) != info.st_size or completion._identity(info) != completion._identity(os.fstat(fd))
                        or completion._identity(info) != completion._identity(os.stat(self.entry.name, dir_fd=base, follow_symlinks=False))
                        or completion.digest(raw) != self.entry_sha):
                    raise OSError("registered root entry changed")
            finally:
                os.close(fd)
            fresh = completion.open_root(self.entry.parent)
            try:
                if (parent_identity.st_dev, parent_identity.st_ino) != (os.fstat(fresh).st_dev, os.fstat(fresh).st_ino):
                    raise OSError("registered root entry parent replaced")
            finally:
                os.close(fresh)
        finally:
            os.close(base)

    def prepare(self, context):
        completion.current(context)
        self.frozen.assert_current(self.environment)
        task = completion.execution_binding(context.settings)
        if task["profile"] != self.frozen.profile or completion.encoded(task) != completion.encoded(self.execution):
            raise OSError("task execution/profile differs from original registration")
        self._entry_current()
        if context.model and context.model != self.frozen.model:
            raise OSError("carrier model differs from frozen source")
        expected = completion.binding(context, self.frozen.binding(), self.entry_sha)
        packet = {"schema": "codex-root-launch-v1", "registration_id": self.registration, "binding": expected}
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        key = self.frozen._provider.get("env_key")
        preserve = []
        if key:
            # Never preserve interpreter/shell/loader control variables into a
            # privileged entry. Only conventional credential-variable names.
            if not re.fullmatch(r"(?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|TOKEN)", key):
                raise OSError("unsupported privileged credential variable name")
            environment[key] = self.environment[key]
            preserve = ["--preserve-env=" + key]
        command = ("/usr/bin/sudo", "-n", *preserve, "--", str(self.entry), "--run", completion.encoded(packet).decode())

        def verify(original, process, folder):
            self.frozen.assert_current(self.environment)
            self._entry_current()
            completion.verify_completion(self.completion_root, self.gid, expected, original, process, folder)

        return CarrierLaunch(command, environment, verify)
