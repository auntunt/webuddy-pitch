"""Independent HTTP health contracts; temporary state and local fixture servers only.

The HTTP responses are real. PID ownership is represented by the current test
process (which owns the HTTP server), except the watcher test's explicit process
double. No production processes or business databases are touched.
"""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.sqlite_snapshot import dump_store
from tmh.platform import preview
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


class HTTPFixture:
    def __init__(self):
        self.routes = {}
        self.requests = []
        self.active = 0
        self.condition = threading.Condition()
        self.partial_closed = threading.Event()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self):
                super().setup()
                with fixture.condition:
                    fixture.active += 1

            def finish(self):
                try:
                    super().finish()
                finally:
                    with fixture.condition:
                        fixture.active -= 1
                        fixture.condition.notify_all()

            def log_message(self, *_):
                pass

            def do_GET(self):
                with fixture.condition:
                    fixture.requests.append(self.path)
                    fixture.condition.notify_all()
                code, body, headers = fixture.routes.get(self.path, (404, b"missing", {}))
                self.send_response(code)
                self.send_header("Content-Length", str(len(body) + (20 if headers.get("partial") else 0)))
                for name, value in headers.items():
                    if name != "partial":
                        self.send_header(name, value)
                self.end_headers()
                try:
                    self.wfile.write(body)
                    self.wfile.flush()
                    if headers.get("partial"):
                        self.connection.settimeout(4)
                        if not self.connection.recv(1):
                            fixture.partial_closed.set()
                        self.close_connection = True
                except (BrokenPipeError, ConnectionResetError):
                    fixture.partial_closed.set()
                    self.close_connection = True
                except socket.timeout:
                    self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        self.worker.start()

    @property
    def port(self):
        return self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)


class PreviewHealthIndependentTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="webuddy-preview-health-independent-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.data = self.base / "data"
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        project = self.store.add_project("INDEP", "Independent health fixture", str(self.base))
        self.ticket = self.store.create_ticket(project["id"], "Preview health", "fixture-owner")
        self.P = SimpleNamespace(data_dir=self.data, store=self.store)
        self.app = HTTPFixture()
        self.addCleanup(self.app.close)
        self.key = self.ticket["key"]
        self.commit = "1" * 40
        self.prefix = preview.bound_prefix(self.key, self.commit)
        self.health_path = self.prefix + "/health"
        self.record = {"key": self.key, "project": "INDEP", "commit_full": self.commit,
            "commit": self.commit[:10], "prefix": self.prefix, "ready": "/health",
            "port": self.app.port, "pid": os.getpid(), "dir": str(Path.cwd()),
            "state": "up", "started": "fixture-start", "cmd": "fixture HTTP server"}
        self.app.routes[self.health_path] = (200, b'{"status":"ok"}', {})
        preview._save(self.data, {self.key: self.record})

    def status(self):
        return preview.status(self.data, self.key)

    def test_http_401_404_and_503_cannot_be_reported_up(self):
        for code in (401, 404, 503):
            with self.subTest(code=code):
                self.app.routes[self.health_path] = (code, b"not available", {})
                state = self.status()
                self.assertNotEqual(state.get("state"), "up", "HTTP %d was treated as a usable preview" % code)
                self.assertTrue(state.get("why"), state)

    def test_only_the_exact_prefixed_endpoint_is_checked(self):
        self.app.routes["/"] = (503, b"unrelated root", {})
        self.app.routes["/health"] = (401, b"unprefixed application", {})
        self.assertEqual(self.status()["state"], "up")
        self.assertEqual(self.app.requests, [self.health_path])

    def test_redirects_do_not_inherit_success_or_contact_the_target(self):
        target = HTTPFixture()
        self.addCleanup(target.close)
        target.routes["/login"] = (200, b"login is not the configured health endpoint", {})
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code):
                self.app.routes[self.health_path] = (code, b"", {
                    "Location": "http://127.0.0.1:%d/login" % target.port})
                self.assertNotEqual(self.status().get("state"), "up")
        self.assertEqual(target.requests, [], "health followed a redirect to another origin")

    def test_unhealthy_then_recovery_is_read_only_for_business_and_saved_preview(self):
        before_records = list(dump_store(self.store))
        state_path = self.data / "previews/state.json"
        before_state = state_path.read_bytes()
        self.assertEqual(self.status()["state"], "up")
        self.app.routes[self.health_path] = (503, b"database temporarily unavailable", {})
        self.assertNotEqual(self.status().get("state"), "up")
        self.app.routes[self.health_path] = (200, b'{"status":"ok"}', {})
        recovered = self.status()
        self.assertEqual(recovered["state"], "up")
        self.assertTrue(preview.bound_matches(recovered, self.key, self.commit))
        self.assertEqual(list(dump_store(self.store)), before_records)
        self.assertEqual(state_path.read_bytes(), before_state)

    def test_status_ignores_environment_proxy(self):
        proxy = HTTPFixture()
        self.addCleanup(proxy.close)
        address = "http://127.0.0.1:%d" % proxy.port
        with patch.dict(os.environ, {"HTTP_PROXY": address, "http_proxy": address,
                                     "ALL_PROXY": address, "all_proxy": address,
                                     "NO_PROXY": "", "no_proxy": ""}):
            state = self.status()
        self.assertEqual(state["state"], "up")
        self.assertEqual(self.app.requests, [self.health_path])
        self.assertEqual(proxy.requests, [], "preview health was sent through an environment proxy")

    def test_incomplete_200_is_unhealthy_bounded_and_closes_connection(self):
        self.app.routes[self.health_path] = (200, b"partial-body", {"partial": True})
        started = time.monotonic()
        state = self.status()
        elapsed = time.monotonic() - started
        self.assertNotEqual(state.get("state"), "up", "incomplete HTTP 200 was accepted")
        self.assertLess(elapsed, 2.5, "a health read exceeded its bounded wait")
        self.assertTrue(self.app.partial_closed.wait(2), "timed-out health connection stayed open")

    def test_completed_error_responses_release_keepalive_connections(self):
        self.app.routes[self.health_path] = (404, b"a full error response", {})
        for _ in range(12):
            self.status()
        self.assertEqual(self.app.requests, [self.health_path] * 12)
        with self.app.condition:
            self.assertTrue(self.app.condition.wait_for(lambda: self.app.active == 0, timeout=2),
                            "health checks leaked persistent HTTP connections")

    def test_old_preview_binding_is_rejected_before_any_application_request(self):
        newer = "2" * 40
        replacement = dict(self.record, commit_full=newer, commit=newer[:10],
                           prefix=preview.bound_prefix(self.key, newer))
        preview._save(self.data, {self.key: replacement})
        with self.assertRaises(ApiError) as rejected:
            preview.forward(self.data, self.key, "GET", self.prefix + "/", {}, b"", expected_commit=self.commit)
        self.assertEqual(rejected.exception.code, 409)
        self.assertEqual(self.app.requests, [], "old version request reached the replacement application")

    def test_watcher_does_not_promote_from_an_unrelated_successful_root(self):
        self.app.routes[self.health_path] = (503, b"configured endpoint unavailable", {})
        self.app.routes["/"] = (200, b"unrelated root page", {})
        ended = threading.Event()

        class ProcessDouble:
            returncode = 0

            def poll(self):
                return 0 if ended.is_set() else None

            def wait(self, timeout=None):
                if ended.wait(min(timeout or .02, .02)):
                    return 0
                raise subprocess.TimeoutExpired("independent process fixture", timeout)

        # No real process has this fixture PID. HTTP is real; this double only
        # lets the watcher finish without launching or killing an application.
        record = dict(self.record, pid=2 ** 29, dir=str(self.base / "not-a-worktree"), state="starting")
        preview._save(self.data, {self.key: record})
        with patch.object(preview, "READY_S", .2):
            worker = threading.Thread(target=preview._watch, args=(self.P, record, ProcessDouble()), daemon=True)
            worker.start()
            try:
                deadline = time.monotonic() + 4
                state = {}
                while time.monotonic() < deadline:
                    state = preview._load(self.data).get(self.key, {})
                    if state.get("state") in ("up", "failed"):
                        break
                    time.sleep(.01)
                self.assertNotEqual(state.get("state"), "up", "root-page success bypassed configured readiness")
                self.assertTrue(self.app.requests, "watcher did not issue a real health request")
                self.assertNotIn("/", self.app.requests)
            finally:
                ended.set()
                worker.join(5)
                self.assertFalse(worker.is_alive(), "watcher fixture did not finish")


if __name__ == "__main__":
    unittest.main()
