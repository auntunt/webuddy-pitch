"""A run-specific preview must open the adopted commit, never another run or a moved branch."""
import http.client
import io
import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urljoin, urlparse

from tmh.platform import preview, server
from tmh.platform.agents import Runner
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


class PreviewRunBindingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tmh-preview-binding-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo, self.data = self.base / "repo", self.base / "data"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Local preview test")
        self.git("config", "user.email", "preview-test@localhost")
        (self.repo / "app.py").write_text("first adopted version\n", encoding="utf-8")
        self.git("add", "app.py")
        self.git("commit", "-q", "-m", "First version")
        self.first = self.git("rev-parse", "HEAD")
        self.git("branch", "tmh/first", self.first)
        (self.repo / "app.py").write_text("second adopted version\n", encoding="utf-8")
        self.git("commit", "-qam", "Second version")
        self.second = self.git("rev-parse", "HEAD")
        self.git("branch", "tmh/second", self.second)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("APP", "Preview test", str(self.repo))
        self.other_project = self.store.add_project("OTHER", "Other", str(self.repo))
        self.ticket = self.store.create_ticket(self.project["id"], "First ticket", "自动流转")
        self.other_ticket = self.store.create_ticket(self.project["id"], "Other ticket", "自动流转")
        self.P = SimpleNamespace(store=self.store, data_dir=self.data, preview_port=0, ticket=self.store.ticket,
                                 runner=Runner(self.store, self.data))
        self.r1 = self.run_record(self.first, "tmh/first")
        self.r2 = self.run_record(self.second, "tmh/second")
        preview.set_conf(self.data, "APP", "python3 app.py {port} {prefix}", "/health", "自动流转")
        (self.data / "autoflow.json").write_text('{"preview":"off","on":false}')
        for r, branch, commit in ((self.r1, "tmh/first", self.first), (self.r2, "tmh/second", self.second)):
            self.store.event(self.ticket["id"], "自动流转", "adopt", "Local technical commit",
                             {"run": r["id"], "branch": branch, "commit": commit[:10]})

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True, stderr=subprocess.PIPE).strip()

    def run_record(self, commit=None, branch="tmh/run", mode="fix", ticket=None, project=None, decision=None):
        r = self.store.create_run((project or self.project)["id"], (ticket or self.ticket)["id"], "local-test", mode, "自动流转", "")
        self.store.update_run(r["id"], status="done", exit_code=0,
                              decision=decision if decision is not None else "accepted:%s@%s" % (branch, (commit or self.first)[:10]))
        return self.store.run(r["id"])

    def req(self, body=None, **query):
        return server.Req(None, {key: [value] for key, value in query.items()}, body or {}, "自动流转")

    def state(self, commit=None, state="up", **extra):
        commit = commit or self.first
        return dict({"state": state, "commit_full": commit, "commit": commit[:10],
                     "prefix": preview.bound_prefix(self.ticket["key"], commit), "root": str(self.repo),
                     "port": 12345, "pid": 999999}, **extra)

    def handler(self, headers=None, body=b""):
        h = server.make_handler(self.P).__new__(server.make_handler(self.P))
        h.headers = {"Host": "localhost", **(headers or {})}
        h.rfile, h.wfile = io.BytesIO(body), io.BytesIO()
        h._send, h._authorized = mock.Mock(), mock.Mock(return_value=True)
        h.send_response, h.send_header, h.end_headers = mock.Mock(), mock.Mock(), mock.Mock()
        return h

    def error(self, status, fn, *args):
        with self.assertRaises(ApiError) as cm:
            fn(*args)
        self.assertEqual(cm.exception.code, status, str(cm.exception))

    def test_exact_old_run_is_resolved_without_latest_adopt_event(self):
        self.assertEqual(preview.branch_of(self.P, self.ticket), "tmh/second")
        bound = preview.run_binding(self.P, self.ticket, str(self.r1["id"]))
        self.assertEqual(bound, {"run_id": self.r1["id"], "expected_commit": self.first, "branch": "tmh/first"})
        self.assertEqual(preview.run_binding(self.P, self.ticket, self.r2["id"])["expected_commit"], self.second)

    def test_running_old_preview_does_not_expose_url_for_second_fix(self):
        st = self.state(branch="tmh/first")
        with mock.patch.object(preview, "status", return_value=st):
            old = server.api_preview(self.P, self.req(run_id=str(self.r1["id"])), self.ticket["key"])
            new = server.api_preview(self.P, self.req(run_id=str(self.r2["id"])), self.ticket["key"])
        self.assertTrue(old["matches_run"])
        self.assertEqual(old["url"], preview.bound_prefix("APP-1", self.first) + "/")
        self.assertFalse(new["matches_run"])
        self.assertEqual(new["url"], "")
        self.assertEqual(new["expected_commit"], self.second)
        self.assertEqual(new["run_id"], self.r2["id"])
        self.assertEqual(new["preview"], st)

    def test_matching_commit_alone_does_not_claim_preview_is_up(self):
        for state in ("starting", "failed", "stopped"):
            with self.subTest(state=state), mock.patch.object(preview, "status", return_value=self.state(state=state)):
                result = preview.ticket_view(self.P, self.ticket, self.r1["id"])
                self.assertTrue(result["matches_run"])
                self.assertEqual(result["url"], "")
        with mock.patch.object(preview, "status", return_value={}):
            result = preview.ticket_view(self.P, self.ticket, self.r1["id"])
            self.assertFalse(result["matches_run"])
            self.assertEqual(result["url"], "")

    def test_legacy_preview_response_and_start_keep_latest_branch_behavior(self):
        st = {"state": "up", "commit": self.first[:10]}
        with mock.patch.object(preview, "status", return_value=st), \
                mock.patch.object(preview, "start", return_value={"state": "starting", "commit": self.second[:10]}) as start:
            get = server.api_preview(self.P, self.req(), self.ticket["key"])
            post = server.api_preview_do(self.P, self.req({"action": "start"}), self.ticket["key"])
        for result in (get, post):
            self.assertEqual(result["url"], "/pv/APP-1/")
            self.assertEqual(result["branch"], "tmh/second")
            self.assertIsNone(result["run_id"])
            self.assertIsNone(result["matches_run"])
            self.assertEqual(result["expected_commit"], "")
        self.assertEqual(start.call_args.args[3], "tmh/second")

    def test_invalid_ids_and_non_owned_runs_are_rejected(self):
        for rid in (True, False, 0, -1, "", "-2", "1.5", " 1", [], {}, 2 ** 80, "9" * 30):
            with self.subTest(run_id=rid):
                self.error(400, preview.run_binding, self.P, self.ticket, rid)
        self.error(404, preview.run_binding, self.P, self.ticket, 9999)
        other = self.run_record(ticket=self.other_ticket)
        self.error(404, preview.run_binding, self.P, self.ticket, other["id"])
        inconsistent = self.run_record(project=self.other_project)
        self.error(404, preview.run_binding, self.P, self.ticket, inconsistent["id"])

    def test_unadopted_non_fix_missing_and_malformed_commit_are_rejected(self):
        for kwargs in ({"decision": ""}, {"decision": "discarded"}, {"mode": "plan"},
                       {"decision": "accepted:tmh/first@main"}, {"decision": "accepted:tmh/first"},
                       {"decision": "accepted:tmh/first@" + "0" * 40}):
            with self.subTest(kwargs=kwargs), mock.patch.object(preview, "start") as start:
                r = self.run_record(**kwargs)
                self.error(409, preview.start_for_ticket, self.P, self.ticket, "自动流转", r["id"])
                start.assert_not_called()

    def test_branch_moves_but_post_and_real_worktree_stay_on_adopted_commit(self):
        self.git("branch", "-f", "tmh/first", self.second)
        process = SimpleNamespace(pid=999999)
        popen = subprocess.Popen
        launch = lambda *args, **kwargs: process if kwargs.get("shell") else popen(*args, **kwargs)
        with mock.patch.object(preview.subprocess, "Popen", side_effect=launch), \
                mock.patch.object(preview.threading, "Thread"), mock.patch.object(preview, "_alive", return_value=True):
            result = server.api_preview_do(self.P, self.req({"action": "start", "run_id": self.r1["id"]}), self.ticket["key"])
        self.assertEqual(result["run_id"], self.r1["id"])
        self.assertEqual(result["expected_commit"], self.first)
        self.assertTrue(result["matches_run"])
        self.assertEqual(result["url"], "")  # genuinely starting, not reported up by the API
        rec = result["preview"]
        self.assertEqual(rec["branch"], self.first)
        self.assertEqual(rec["commit_full"], self.first)
        self.assertEqual(rec["prefix"], preview.bound_prefix("APP-1", self.first))
        self.assertIn(rec["prefix"], rec["cmd"])
        self.assertEqual((Path(rec["dir"]) / "app.py").read_text(), "first adopted version\n")
        self.assertEqual(subprocess.check_output(["git", "-C", rec["dir"], "rev-parse", "HEAD"], text=True).strip(), self.first)
        event = self.store.events(self.ticket["id"])[-1]
        self.assertEqual(event["data"]["run"], self.r1["id"])
        self.assertEqual(event["data"]["commit"], self.first)

    def test_get_binding_does_not_mutate_business_state(self):
        changes = self.store.db.total_changes
        with mock.patch.object(preview, "status", return_value=self.state()):
            for _ in range(2):
                self.assertTrue(preview.ticket_view(self.P, self.ticket, self.r1["id"])["matches_run"])
        self.assertEqual(self.store.db.total_changes, changes)
        self.assertFalse((self.data / "previews" / "state.json").exists())

    def test_bound_stop_does_not_stop_another_runs_preview(self):
        st = {"state": "up", "commit": self.first[:10], "root": str(self.repo)}
        preview._save(self.data, {self.ticket["key"]: st})
        with mock.patch.object(preview, "_kill") as kill, mock.patch.object(preview, "_clean"):
            self.error(409, server.api_preview_do, self.P, self.req({"action": "stop", "run_id": self.r2["id"]}), self.ticket["key"])
            kill.assert_not_called()
            self.assertEqual(preview._load(self.data)[self.ticket["key"]], st)
            server.api_preview_do(self.P, self.req({"action": "stop", "run_id": self.r1["id"]}), self.ticket["key"])
            kill.assert_called_once_with(st)
            self.assertNotIn(self.ticket["key"], preview._load(self.data))

    def test_concurrent_preview_replacement_is_rechecked_before_bound_stop(self):
        first = {"state": "up", "commit_full": self.first, "root": str(self.repo)}
        second = {"state": "up", "commit_full": self.second, "root": str(self.repo)}
        preview._save(self.data, {self.ticket["key"]: first})
        resolved, replaced = threading.Event(), threading.Event()
        binding, outcomes = preview.run_binding, []

        def delayed_binding(*args):
            result = binding(*args)
            resolved.set()
            if not replaced.wait(3):
                raise AssertionError("replacement did not happen")
            return result

        def stop():
            try:
                server.api_preview_do(self.P, self.req({"action": "stop", "run_id": self.r1["id"]}), self.ticket["key"])
            except Exception as e:
                outcomes.append(e)

        with mock.patch.object(preview, "run_binding", side_effect=delayed_binding), \
                mock.patch.object(preview, "_kill") as kill, mock.patch.object(preview, "_clean") as clean:
            thread = threading.Thread(target=stop)
            thread.start()
            try:
                self.assertTrue(resolved.wait(3))
                # A concurrent start uses this same per-ticket lock to replace the live record.
                with preview._key_lock(self.ticket["key"]):
                    with preview._LOCK:
                        preview._save(self.data, {self.ticket["key"]: second})
            finally:
                replaced.set()
                thread.join(3)
            self.assertFalse(thread.is_alive())
            kill.assert_not_called()
            clean.assert_not_called()
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], ApiError)
        self.assertEqual(outcomes[0].code, 409)
        self.assertEqual(preview._load(self.data)[self.ticket["key"]], second)

    def test_hex_named_branch_cannot_override_adopted_commit_object(self):
        self.git("branch", self.first[:10], self.second)
        self.assertEqual(preview._commit(self.repo, self.first[:10]), self.first)
        self.assertEqual(preview.run_binding(self.P, self.ticket, self.r1["id"])["expected_commit"], self.first)
        with mock.patch.object(preview, "git", return_value=self.first + "\n" + self.second):
            self.assertEqual(preview._commit(self.repo, self.first[:4]), "")
        blob = self.git("rev-parse", "HEAD:app.py")
        self.assertEqual(preview._commit(self.repo, blob), "")

    def test_same_commit_legacy_prefix_must_restart_before_exposing_bound_url(self):
        with mock.patch.object(preview, "status", return_value=self.state(prefix="/pv/APP-1")):
            result = preview.ticket_view(self.P, self.ticket, self.r1["id"])
        self.assertFalse(result["matches_run"])
        self.assertEqual(result["url"], "")

    def test_open_url_and_existing_tab_requests_reject_a_replacement_preview(self):
        preview._save(self.data, {"APP-1": self.state()})
        with mock.patch.object(preview, "_alive", return_value=True):
            old_url = preview.ticket_view(self.P, self.ticket, self.r1["id"])["url"]
        h = self.handler()
        h._preview("GET", urlparse(old_url), {})
        opened = h._send.call_args.args[3]["Location"]
        self.assertTrue(opened.startswith(old_url + "__open?g="))
        server.serve_preview(h, self.P, "GET", urlparse(opened), sandboxed=True)
        cookie = h._send.call_args.args[3]["Set-Cookie"]
        self.assertIn("Path=" + old_url + ";", cookie)
        self.assertEqual(h._send.call_args.args[3]["Location"], old_url)
        # Another tab replaces the running code and receives its own cookie.
        preview._save(self.data, {"APP-1": self.state(self.second)})
        second_grant = preview.grant(self.data, "APP-1", expected_commit=self.second)
        all_cookies = cookie.split(";", 1)[0] + "; " + preview.cookie_name("APP-1", self.second) + "=" + second_grant
        h.headers["Cookie"] = all_cookies
        with mock.patch.object(preview, "forward") as forward:
            h._preview("GET", urlparse(old_url), {})
            self.assertEqual(h._send.call_args.args[0], 409)
            for method, path in (("GET", opened), ("GET", old_url + "app.js"), ("POST", old_url + "save")):
                with self.subTest(method=method, path=path):
                    server.serve_preview(h, self.P, method, urlparse(path), sandboxed=True)
                    self.assertEqual(h._send.call_args.args[0], 409)
            forward.assert_not_called()

    def test_bound_grants_and_forwarding_preserve_prefix_and_form_body(self):
        st = self.state()
        preview._save(self.data, {"APP-1": st})
        old = preview.grant(self.data, "APP-1")
        g = preview.grant(self.data, "APP-1", expected_commit=self.first)
        self.assertTrue(preview.granted(self.data, "APP-1", g, expected_commit=self.first))
        self.assertFalse(preview.granted(self.data, "APP-1", old, expected_commit=self.first))
        self.assertFalse(preview.granted(self.data, "APP-1", g, expected_commit=self.second))
        self.assertFalse(preview.granted(self.data, "APP-1", g))
        body = b"name=first-version"
        h = self.handler({"Cookie": preview.cookie_name("APP-1", self.first) + "=" + g, "Content-Length": str(len(body))}, body)
        response = io.BytesIO(b"saved")
        path = st["prefix"] + "/save?tab=first"
        with mock.patch.object(preview, "forward", return_value=(200, [], response, 5)) as forward:
            server.serve_preview(h, self.P, "POST", urlparse(path), sandboxed=True)
        self.assertEqual(forward.call_args.args[2:4], ("POST", path))
        self.assertEqual(forward.call_args.args[5], body)
        self.assertEqual(forward.call_args.kwargs["expected_commit"], self.first)
        self.assertEqual(h.wfile.getvalue(), b"saved")
        # forward independently rechecks state, closing the read-to-use gap in the handler.
        preview._save(self.data, {"APP-1": self.state(self.second)})
        with mock.patch.object(preview.http.client, "HTTPConnection") as conn:
            with self.assertRaises(ApiError) as cm:
                preview.forward(self.data, "APP-1", "POST", path, {}, body, expected_commit=self.first)
            self.assertEqual(cm.exception.code, 409)
            conn.assert_not_called()

    def test_forward_connects_to_pinned_process_under_start_stop_lock(self):
        st = self.state()
        preview._save(self.data, {"APP-1": st})
        conn = mock.Mock()
        conn.getresponse.return_value.getheaders.return_value = []
        conn.getresponse.return_value.getheader.return_value = "0"
        def connect():
            lock = preview._key_lock("APP-1")
            self.assertFalse(lock.acquire(blocking=False), "replacement must be excluded until TCP connects")
        conn.connect.side_effect = connect
        with mock.patch.object(preview, "_alive", return_value=True), \
                mock.patch.object(preview.http.client, "HTTPConnection", return_value=conn):
            preview.forward(self.data, "APP-1", "GET", st["prefix"] + "/", {}, b"", expected_commit=self.first)
        conn.connect.assert_called_once()
        self.assertEqual(conn.request.call_args.kwargs["headers"]["X-Forwarded-Prefix"], st["prefix"])

    def test_legacy_grant_opens_current_bound_prefix_without_extending_expiry(self):
        preview._save(self.data, {"APP-1": self.state()})
        g = preview.grant(self.data, "APP-1")
        h = self.handler()
        with mock.patch.object(preview, "_alive", return_value=True):
            server.serve_preview(h, self.P, "GET", urlparse("/pv/APP-1/__open?g=" + g), sandboxed=True)
        self.assertEqual(h._send.call_args.args[0], 303)
        loc = h._send.call_args.args[3]["Location"]
        self.assertTrue(loc.startswith(preview.bound_prefix("APP-1", self.first) + "/__open?g="))
        bound_grant = parse_qs(urlparse(loc).query)["g"][0]
        self.assertEqual(bound_grant.split(".")[0], g.split(".")[0])
        self.assertTrue(preview.granted(self.data, "APP-1", bound_grant, expected_commit=self.first))
        h.headers["Cookie"] = preview.cookie_name("APP-1") + "=" + g
        with mock.patch.object(preview, "_alive", return_value=True), mock.patch.object(preview, "forward") as forward:
            server.serve_preview(h, self.P, "GET", urlparse("/pv/APP-1/"), sandboxed=True)
            self.assertEqual(h._send.call_args.args[0], 303)
            self.assertEqual(h._send.call_args.args[3]["Location"], loc)
            forward.assert_not_called()

    def test_real_http_bound_page_links_form_and_two_tabs_do_not_cross_versions(self):
        requests = []
        class App(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                requests.append(("GET", self.path, b""))
                body = b'<a href="next">Next</a><form method="post" action="save"><input name="name"></form>'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                requests.append(("POST", self.path, body))
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), App)
        main = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(self.P, token="local-test-token"))
        own = ThreadingHTTPServer(("127.0.0.1", 0), server.make_preview_handler(self.P))
        servers = (upstream, main, own)
        threads = [threading.Thread(target=x.serve_forever, daemon=True) for x in servers]
        for thread in threads:
            thread.start()
        def call(srv, path, method="GET", body=None, headers=None):
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
            try:
                conn.request(method, path, body=body, headers=headers or {})
                r = conn.getresponse()
                return r.status, dict(r.getheaders()), r.read()
            finally:
                conn.close()
        try:
            for separate in (False, True):
                with self.subTest(separate_origin=separate), mock.patch.object(preview, "_alive", return_value=True):
                    self.P.preview_port = own.server_port if separate else 0
                    browser = own if separate else main
                    preview._save(self.data, {"APP-1": self.state(port=upstream.server_port)})
                    url = preview.ticket_view(self.P, self.ticket, self.r1["id"])["url"]
                    legacy = preview.grant(self.data, "APP-1")
                    legacy_cookie = preview.cookie_name("APP-1") + "=" + legacy
                    code, headers, _ = call(browser, "/pv/APP-1/", headers={"Cookie": legacy_cookie})
                    self.assertEqual(code, 303)
                    self.assertTrue(headers["Location"].startswith(url + "__open?g="))
                    bridged = parse_qs(urlparse(headers["Location"]).query)["g"][0]
                    self.assertEqual(bridged.split(".")[0], legacy.split(".")[0])
                    code, headers, _ = call(main, url, headers={"X-TMH-Token": "local-test-token"})
                    self.assertEqual(code, 303)
                    opened = headers["Location"]
                    path = urlparse(opened).path + "?" + urlparse(opened).query
                    code, headers, _ = call(browser, path)
                    self.assertEqual((code, headers["Location"]), (303, url))
                    cookie = headers["Set-Cookie"].split(";", 1)[0]
                    self.assertIn("Path=" + url, headers["Set-Cookie"])
                    code, _, page = call(browser, url, headers={"Cookie": cookie})
                    self.assertEqual(code, 200)
                    self.assertIn(b'action="save"', page)
                    next_url, form_url = urljoin(url, "next"), urljoin(url, "save")
                    self.assertEqual(call(browser, next_url, headers={"Cookie": cookie})[0], 200)
                    payload = b"name=first-version"
                    self.assertEqual(call(browser, form_url, "POST", payload, {"Cookie": cookie})[2], payload)
                    self.assertEqual(requests[-1], ("POST", form_url, payload))
                    preview._save(self.data, {"APP-1": self.state(self.second, port=upstream.server_port)})
                    old_count = len(requests)
                    for method, old_path in (("GET", url), ("GET", next_url), ("POST", form_url)):
                        self.assertEqual(call(browser, old_path, method, payload if method == "POST" else None, {"Cookie": cookie})[0], 409)
                    self.assertEqual(len(requests), old_count, "stale reads/forms must never reach the replacement")
                    new_prefix = preview.bound_prefix("APP-1", self.second)
                    old_grant = parse_qs(urlparse(opened).query)["g"][0]
                    self.assertEqual(call(browser, new_prefix + "/__open?g=" + old_grant)[0], 403)
        finally:
            self.P.preview_port = 0
            for srv in servers:
                srv.shutdown()
                srv.server_close()
            for thread in threads:
                thread.join(2)

    def test_run_detail_exposes_ticket_key_and_actual_verification(self):
        folder = self.data / "runs" / str(self.r1["id"])
        folder.mkdir(parents=True)
        evidence = {"check": "pass", "verdict": "pass", "commands": [{"kind": "test", "command": "python3 -m unittest", "exit_code": 0}]}
        (folder / "verify.json").write_text(json.dumps(evidence))
        result = server.api_run(self.P, self.req(), str(self.r1["id"]))
        self.assertEqual(result["ticket_key"], "APP-1")
        self.assertEqual(result["verification"], evidence)
        plan = self.run_record(mode="plan", decision="")
        self.assertIsNone(server.api_run(self.P, self.req(), str(plan["id"]))["verification"])


if __name__ == "__main__":
    unittest.main()
