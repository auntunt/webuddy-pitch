"""Host assembly algorithms with a disposable fixture owner, not Linux root proof.

ROOT_UID is patched only for these private local fixture directories. A separate
negative control retains production UID0 and rejects these unprivileged files.
No sudo, namespace, official CLI, real key, provider or model is executed.
"""
from dataclasses import replace
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import sys
import tempfile
import threading
import time
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest import mock

from tmh.platform import codex_host as host, codex_host_completion as C, codex_gateway as G, learning_runs as lr
from tmh.platform.codex_carrier import CarrierContext
from tmh.platform.codex_frozen_config import FrozenConfig, PUBLIC_KEY
from tmh.platform.agents import Runner
from tmh.platform.store import Store


class CodexHostTests(unittest.TestCase):
    def setUp(self):
        # The production reader deliberately rejects writable ancestors such as
        # /tmp. A fresh private directory under the home keeps this identical
        # on macOS and Linux, without weakening the reader for test fixtures.
        temp = tempfile.TemporaryDirectory(prefix="tmh-host-candidate-", dir=Path.home())
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        self.home.chmod(0o700)
        self.config_home = self.home / "config"
        self.config_home.mkdir(mode=0o700)
        self.secret = "PUBLIC_SYNTHETIC_HOST_CREDENTIAL"
        base = ('model="synthetic-model"\nmodel_provider="synthetic"\n'
                '[model_providers.synthetic]\nname="public fixture"\n'
                'base_url="https://provider.example/v1"\nwire_api="responses"\n'
                'experimental_bearer_token="' + self.secret + '"\n')
        self.write(self.config_home / "config.toml", base.encode(), 0o600)
        self.write(self.config_home / "team.config.toml", b'approval_policy="never"\n', 0o600)
        self.environment = {}
        self.frozen = FrozenConfig(self.config_home, "team", environment=self.environment)
        self.private = self.home / "private"
        self.private.mkdir(mode=0o700)
        self.public = self.home / "completed"
        self.public.mkdir(mode=0o750)
        self.public.chmod(0o750)
        self.gid = os.getegid()
        self.entry = self.home / "root-entry"
        self.write(self.entry, b"PUBLIC_SYNTHETIC_ENTRY_NOT_EXECUTED\n", 0o700)
        self.entry_sha = C.digest(self.entry.read_bytes())
        info = self.entry.stat()
        self.execution = {"bin": str(self.entry), "args": [], "engine": "codex", "profile": "team",
                          "prompt_transport": "stdin", "resume": False, "retry_busy": False, "timeout": 30,
                          "sha256": self.entry_sha, "size": info.st_size, "mtime_ns": info.st_mtime_ns}
        self.store = Store(self.home / "data/platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("HOST", "公开宿主夹具", str(self.home))
        self.runner = Runner(self.store, self.home / "data")
        self.run = self.store.create_run(self.project["id"], None, "synthetic", "ask", "fixture", "full prompt")
        self.rid = self.run["id"]
        self.store.update_run(self.rid, status="running")
        control = self.runner._control(self.rid, {"synthetic": {"timeout": 30}}, "synthetic")
        self.addCleanup(self.runner._release, self.rid)
        self.context = CarrierContext(self.rid, "a" * 32, MappingProxyType(control["owner"]),
            control["start"] + control["timeout_seconds"], control["event"], "full prompt", "synthetic-model", self.execution)
        self.owner = mock.patch.object(C, "ROOT_UID", os.geteuid())
        self.owner.start()
        self.addCleanup(self.owner.stop)
        self.addCleanup(self.retain)

    def retain(self):
        target = os.environ.get("TMH_HOST_TEST_SCENES")
        if target:
            dest = Path(target) / self._testMethodName
            shutil.copytree(self.home, dest, symlinks=True,
                ignore=shutil.ignore_patterns("platform.db", "platform.db-wal", "platform.db-shm"))
            (dest / "data").mkdir(exist_ok=True)
            saved = sqlite3.connect(dest / "data/platform.db")
            try:
                self.store.db.backup(saved)
            finally:
                saved.close()

    def write(self, path, raw, mode):
        path.write_bytes(raw)
        path.chmod(mode)

    def session(self, **changes):
        fields = dict(expected_configuration=self.frozen.binding(), expected_execution=self.execution,
                      expected_credential_sha256=C.digest(self.secret.encode()),
                      controller_sha256=self.entry_sha, private_root=self.private, completion_root=self.public,
                      service_gid=self.gid)
        fields.update(changes)
        session = host.HostSession(self.context, self.frozen, self.environment, **fields)
        self.addCleanup(session.close)
        return session

    def process(self):
        output = b'{"type":"turn.completed","public":"synthetic"}\n'
        process, folder = self.runner.run_command(self.rid,
            [sys.executable, "-I", "-S", "-c", "import sys;sys.stdout.buffer.write(" + repr(output) + ")"],
            self.home, stdin=self.context.prompt, prompt=self.context.prompt, prompt_transport=["stdin"])
        return process, folder

    def complete(self, session, process):
        session.complete(process.output_bytes, 0, {"passed": True, "cleanup": dict(C.CLEANUP)})

    def frames(self, raw):
        frames = []
        while raw:
            n = struct.unpack("!I", raw[:4])[0]
            header = json.loads(raw[4:4+n])
            payload = raw[4+n:4+n+header["bytes"]]
            self.assertEqual(len(payload), header["bytes"])
            self.assertEqual(C.digest(payload), header["sha256"])
            frames.append((header, payload))
            raw = raw[4+n+len(payload):]
        return frames

    def test_loopback_exchange_private_full_journal_and_original_SP_joint_verification(self):
        body = b'{"model":"synthetic-model","input":"public synthetic request"}'
        payload = b"PUBLIC_RESPONSE" * 6000 + b"\x00\xff"
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, self.headers.get("Authorization"), self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        real_connection = http.client.HTTPConnection
        def loopback(hostname, port, timeout, context):
            return real_connection("127.0.0.1", server.server_port, timeout=timeout)
        session = self.session()
        output = []
        try:
            with mock.patch.object(G.http.client, "HTTPSConnection", side_effect=loopback):
                session.exchange("POST", G.TARGET,
                    [("Host", G.HOST), ("Authorization", "Bearer " + PUBLIC_KEY),
                     ("Content-Type", "application/json"), ("Content-Length", str(len(body)))], body,
                    on_headers=lambda *a: None, on_body=output.append)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(received, [(G.TARGET, "Bearer " + self.secret, body)])
        self.assertEqual(b"".join(output), payload)
        process, folder = self.process()
        self.complete(session, process)
        expected = C.binding(self.context, self.frozen.binding(), self.entry_sha)
        C.verify_completion(self.public, self.gid, expected, self.context, process, folder)
        journal = (self.private / (self.context.launch_nonce + ".gateway.bin")).read_bytes()
        frames = self.frames(journal)
        self.assertEqual(b"".join(b for h, b in frames if h["event"] == "response_body"), payload)
        self.assertEqual(b"".join(b for h, b in frames if h["event"] == "request_body"), body)
        value = C.read_projection(self.public, self.context.launch_nonce, self.gid)
        self.assertEqual(value["gateway_attempts"], 1)
        self.assertEqual(value["completed_payloads"], 1)
        self.assertEqual(value["private_journal"]["sha256"], C.digest(journal))
        self.assertEqual(value["private_journal"]["bytes"], len(journal))
        self.assertNotIn(self.secret.encode(), C.encoded(value))
        self.assertEqual((self.private / (self.context.launch_nonce + ".gateway.bin")).stat().st_mode & 0o777, 0o600)

    def test_root_carrier_builds_only_registered_public_packet_and_worker_inputs(self):
        carrier = host.RootCarrier(self.frozen, self.environment, controller_entry=self.entry,
            controller_sha256=self.entry_sha, registration_id="b" * 64, execution_binding=self.execution, completion_root=self.public, service_gid=self.gid)
        plan = carrier.prepare(self.context)
        packet = json.loads(plan.command[-1])
        self.assertEqual(plan.command[:5], ("/usr/bin/sudo", "-n", "--", str(self.entry), "--run"))
        self.assertEqual(packet["registration_id"], "b" * 64)
        self.assertEqual(packet["binding"]["launch_nonce"], self.context.launch_nonce)
        self.assertNotIn(self.secret, plan.command[-1])
        self.assertNotIn("provider.example", plan.command[-1])
        inputs = self.session().worker_inputs()
        self.assertNotIn(self.secret, repr(inputs))
        self.assertEqual(inputs["config"], self.frozen.worker_config())
        self.assertEqual(inputs["environment"]["WEBUDDY_ISOLATED_PUBLIC_KEY"], PUBLIC_KEY)
        self.assertIn("--strict-config", inputs["command"])

    def test_task_profile_and_frozen_execution_mismatch_refuse_before_entry_or_SP(self):
        carrier = host.RootCarrier(self.frozen, self.environment, controller_entry=self.entry,
            controller_sha256=self.entry_sha, registration_id="b" * 64, execution_binding=self.execution,
            completion_root=self.public, service_gid=self.gid)
        changes = ({"profile": "another-profile"}, {"bin": "/another/bin"}, {"sha256": "0" * 64},
                   {"size": self.execution["size"]+1}, {"mtime_ns": self.execution["mtime_ns"]+1},
                   {"args": ["--ephemeral"]}, {"timeout": 31})
        with mock.patch.object(carrier, "_entry_current") as entry, mock.patch.object(self.runner, "run_command") as execute:
            for change in changes:
                with self.subTest(change=change), self.assertRaisesRegex(OSError, "task execution/profile differs"):
                    carrier.prepare(replace(self.context, settings=dict(self.execution, **change)))
        entry.assert_not_called()
        execute.assert_not_called()
        self.assertFalse((self.home / "data/runs" / str(self.rid) / "attempts").exists())

    def test_private_original_credential_and_source_binding_are_required(self):
        with self.assertRaisesRegex(OSError, "credential identity differs"):
            self.session(expected_credential_sha256="0" * 64)
        with self.assertRaisesRegex(OSError, "configuration differs"):
            self.session(expected_configuration={})
        self.assertEqual(list(self.private.iterdir()), [])

    def test_environment_credential_stays_host_only_and_cannot_rebase_private_identity(self):
        base = self.config_home / "config.toml"
        self.write(base, base.read_bytes().replace(('experimental_bearer_token="' + self.secret + '"').encode(),
                                                 b'env_key="SYNTHETIC_API_KEY"'), 0o600)
        self.environment = {"SYNTHETIC_API_KEY": self.secret}
        self.frozen = FrozenConfig(self.config_home, "team", environment=self.environment)
        original = self.frozen.binding()
        carrier = host.RootCarrier(self.frozen, self.environment, controller_entry=self.entry,
            controller_sha256=self.entry_sha, registration_id="b" * 64, execution_binding=self.execution, completion_root=self.public, service_gid=self.gid)
        plan = carrier.prepare(self.context)
        self.assertIn("--preserve-env=SYNTHETIC_API_KEY", plan.command)
        self.assertEqual(plan.environment["SYNTHETIC_API_KEY"], self.secret)
        self.assertNotIn(self.secret, repr(plan.command))
        self.environment["SYNTHETIC_API_KEY"] = "PUBLIC_DIFFERENT_SYNTHETIC_KEY"
        self.frozen = FrozenConfig(self.config_home, "team", environment=self.environment)
        self.assertEqual(self.frozen.binding(), original)
        with self.assertRaisesRegex(OSError, "credential identity differs"):
            self.session(expected_configuration=original)
        self.write(base, base.read_bytes().replace(b'SYNTHETIC_API_KEY', b'PYTHONPATH'), 0o600)
        self.environment = {"PYTHONPATH": self.secret}
        self.frozen = FrozenConfig(self.config_home, "team", environment=self.environment)
        carrier = host.RootCarrier(self.frozen, self.environment, controller_entry=self.entry,
            controller_sha256=self.entry_sha, registration_id="b" * 64, execution_binding=self.execution, completion_root=self.public, service_gid=self.gid)
        with self.assertRaisesRegex(OSError, "credential variable"):
            carrier.prepare(self.context)

    def test_concurrent_exchange_serializes_complete_private_frames(self):
        session = self.session()
        entered, release = threading.Event(), threading.Event()
        order, errors = [], []
        def forward(*args, **kwargs):
            body = args[5]
            order.append(("begin", body))
            if body == b"one":
                entered.set()
                if not release.wait(3):
                    raise OSError("synthetic release missing")
            kwargs["journal"]("request_body", body)
            kwargs["journal"]("response_body", body)
            order.append(("end", body))
            return {"complete": True}
        def work(body):
            try:
                session.exchange("POST", G.TARGET, [], body, on_headers=lambda *a: None, on_body=lambda *a: None)
            except BaseException as error:
                errors.append(error)
        with mock.patch.object(host, "forward", side_effect=forward):
            first = threading.Thread(target=work, args=(b"one",))
            second = threading.Thread(target=work, args=(b"two",))
            first.start()
            try:
                self.assertTrue(entered.wait(3))
                second.start()
                held = session.lock.acquire(blocking=False)
                if held:
                    session.lock.release()
                self.assertFalse(held)
            finally:
                release.set()
                first.join(3)
                if second.ident is not None:
                    second.join(3)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(order, [("begin", b"one"), ("end", b"one"), ("begin", b"two"), ("end", b"two")])
        session.close()
        frames = self.frames((self.private / (self.context.launch_nonce + ".gateway.bin")).read_bytes())
        self.assertEqual([body for _, body in frames], [b"one", b"one", b"two", b"two"])
        self.assertEqual((session.attempts, session.completed), (2, 2))

    def test_completion_directory_and_root_entry_parent_replacement_refuse(self):
        session = self.session()
        process, _ = self.process()
        self.complete(session, process)
        real_open = C.open_root
        calls = [0]
        def swapped(root, gid=None):
            calls[0] += 1
            if calls[0] == 2:
                self.public.rename(self.home / "old-completed")
                self.public.mkdir(mode=0o750)
                self.public.chmod(0o750)
            return real_open(root, gid)
        with mock.patch.object(C, "open_root", side_effect=swapped):
            with self.assertRaisesRegex(OSError, "root path replaced"):
                C.read_projection(self.public, self.context.launch_nonce, self.gid)
        parent = self.home / "entry-folder"
        parent.mkdir(mode=0o700)
        entry = parent / "fixed"
        self.write(entry, self.entry.read_bytes(), 0o700)
        carrier = host.RootCarrier(self.frozen, self.environment, controller_entry=entry,
            controller_sha256=self.entry_sha, registration_id="b" * 64, execution_binding=self.execution, completion_root=self.public, service_gid=self.gid)
        calls[0] = 0
        def swapped_entry(root, gid=None):
            calls[0] += 1
            if calls[0] == 2:
                parent.rename(self.home / "old-entry-folder")
                parent.mkdir(mode=0o700)
                self.write(entry, self.entry.read_bytes(), 0o700)
            return real_open(root, gid)
        with mock.patch.object(C, "open_root", side_effect=swapped_entry):
            with self.assertRaisesRegex(OSError, "entry parent replaced"):
                carrier.prepare(self.context)

    def test_first_publication_wins_and_no_pending_or_overwrite(self):
        session = self.session()
        process, folder = self.process()
        self.complete(session, process)
        path = self.public / (self.context.launch_nonce + ".json")
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            C.publish_projection(self.public, self.context.launch_nonce, self.gid, {"forged": True})
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual([p.name for p in self.public.iterdir()], [path.name])
        self.assertEqual(path.stat().st_nlink, 1)

    def test_typed_binding_output_cleanup_and_unknown_fields_refuse(self):
        session = self.session()
        process, folder = self.process()
        self.complete(session, process)
        path = self.public / (self.context.launch_nonce + ".json")
        original = json.loads(path.read_bytes())
        expected = C.binding(self.context, self.frozen.binding(), self.entry_sha)
        changes = (lambda x: x["binding"].update(run_id=True), lambda x: x.update(worker_exit=False),
                   lambda x: x["cleanup"].update(owned_worker_reaped=1),
                   lambda x: x["stdout"].update(sha256="0" * 64), lambda x: x.update(extra=True),
                   lambda x: x["binding"].update(launch_nonce="f" * 32))
        for change in changes:
            value = json.loads(C.encoded(original))
            change(value)
            self.write(path, C.encoded(value), 0o640)
            with self.assertRaises(OSError):
                C.verify_completion(self.public, self.gid, expected, self.context, process, folder)

    def test_symlinks_hardlinks_modes_duplicate_JSON_and_complete_size_refuse(self):
        session = self.session()
        process, _ = self.process()
        self.complete(session, process)
        path = self.public / (self.context.launch_nonce + ".json")
        original = path.read_bytes()
        path.chmod(0o660)
        with self.assertRaises(OSError):
            C.read_projection(self.public, self.context.launch_nonce, self.gid)
        path.chmod(0o640)
        link = self.public / "hard-link"
        os.link(path, link)
        with self.assertRaises(OSError):
            C.read_projection(self.public, self.context.launch_nonce, self.gid)
        link.unlink()
        path.unlink()
        link.write_bytes(original)
        path.symlink_to(link)
        with self.assertRaises(OSError):
            C.read_projection(self.public, self.context.launch_nonce, self.gid)
        path.unlink()
        for raw in (b'{"schema":1,"schema":2}', b'{"value":NaN}', b"x" * (C.MAX_RECEIPT + 1)):
            self.write(path, raw, 0o640)
            with self.assertRaises(OSError):
                C.read_projection(self.public, self.context.launch_nonce, self.gid)
            self.assertEqual(path.read_bytes(), raw)

    def test_production_UID0_rejects_unprivileged_fixture_root(self):
        candidate = self.public
        if os.geteuid() == 0:
            candidate = self.home / "unprivileged"
            candidate.mkdir(mode=0o750)
            os.chown(candidate, 65534, self.gid)
        with mock.patch.object(C, "ROOT_UID", 0):
            with self.assertRaises(OSError):
                C.open_root(candidate, self.gid)

    def test_cancel_expiry_entry_change_or_incomplete_namespace_has_no_projection(self):
        carrier = host.RootCarrier(self.frozen, self.environment, controller_entry=self.entry,
            controller_sha256=self.entry_sha, registration_id="b" * 64, execution_binding=self.execution, completion_root=self.public, service_gid=self.gid)
        with self.assertRaisesRegex(OSError, "expired"):
            carrier.prepare(replace(self.context, deadline_monotonic=time.monotonic() - 1))
        self.write(self.entry, b"changed", 0o700)
        with self.assertRaisesRegex(OSError, "entry changed"):
            carrier.prepare(self.context)
        session = self.session()
        with self.assertRaisesRegex(OSError, "did not complete"):
            session.complete(b"stdout", 0, {"passed": True, "cleanup": dict(C.CLEANUP, owned_worker_reaped=False)})
        self.context.cancel_event.set()
        with self.assertRaisesRegex(OSError, "cancelled"):
            session.worker_inputs()
        self.assertEqual(list(self.public.iterdir()), [])

    def test_worker_uses_only_trusted_host_dependency_and_gate_stays_closed(self):
        carrier = host.RootCarrier(self.frozen, self.environment, controller_entry=self.entry,
            controller_sha256=self.entry_sha, registration_id="b" * 64, execution_binding=self.execution, completion_root=self.public, service_gid=self.gid)
        P = SimpleNamespace(store=self.store, data_dir=self.home / "data", independent_codex_carrier=carrier)
        with mock.patch.object(lr, "_row", return_value={"deadline": time.time()+30}):
            worker = lr._Worker(P, self.project, "synthetic", "synthetic")
        self.assertIs(worker.runner._codex_carrier, carrier)
        P.independent_codex_carrier = SimpleNamespace()
        with self.assertRaises(ValueError):
            lr._Worker(P, self.project, "synthetic", "synthetic")
        with self.assertRaisesRegex(ValueError, "尚未接入严格冻结输入隔离"):
            lr._capabilities("must-not-run", None, "codex")
