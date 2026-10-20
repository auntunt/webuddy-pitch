"""A signer's preview capability follows its evidence package and code version.

The model receipts below are fixtures. HTTP redirects, cookies, evidence storage,
binding invalidation and the upstream application requests are exercised for real.
"""
import copy
import http.client
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urlparse

from tmh.platform import delivery, preview, server, signoff
from tmh.platform.store import Store


class SignoffPreviewBindingTest(unittest.TestCase):
    COMMIT = "a" * 40

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-sign-preview-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("APP", "预览签收", str(self.data))
        self.ticket = self.store.create_ticket(self.project["id"], "保存记录", "测试人员", links={"delivery": "a" * 12})
        self.key = self.ticket["key"]
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, preview_port=0,
                                 root=lambda p: Path(p["root"]), flow=SimpleNamespace(accepted=mock.Mock()))
        plan = self.make_run("plan")
        fix = self.make_run("fix")
        self.store.event(self.ticket["id"], "测试人员", "adopt", "采纳已复核实现",
                         {"run": fix, "commit": self.COMMIT, "branch": "tmh/test"})
        self.binding = {"delivery_id": "a" * 12, "valid": True, "blocked": [], "plan_run": plan,
                        "fix_run": fix, "commit": self.COMMIT,
                        "identity": {"develop": {"artifact": 2, "review": 2},
                                     "quality": {"artifact": 3, "review": 3},
                                     "security": {"artifact": 4, "review": 4}}}
        resolver = mock.patch.object(delivery, "signoff_binding", side_effect=lambda *_: copy.deepcopy(self.binding))
        resolver.start()
        self.addCleanup(resolver.stop)
        self.store.update_ticket(self.ticket["id"], "测试人员", status="verify")
        self.ticket = self.store.ticket(self.ticket["id"])
        self.requests = []
        requests = self.requests

        class App(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.respond(b'<form method="post" action="save"><input name="value"></form>')

            def do_POST(self):
                self.respond(self.rfile.read(int(self.headers.get("Content-Length", "0"))))

            def respond(self, body):
                requests.append((self.command, self.path, body))
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), App)
        self.main = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(self.P, token="local-test-token"))
        self.own = ThreadingHTTPServer(("127.0.0.1", 0), server.make_preview_handler(self.P))
        self.servers = (self.upstream, self.main, self.own)
        self.threads = [threading.Thread(target=s.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
                        for s in self.servers]
        for thread in self.threads:
            thread.start()
        self.addCleanup(self.close_servers)
        alive = mock.patch.object(preview, "_alive", return_value=True)
        alive.start()
        self.addCleanup(alive.stop)
        self.preview_state()

    def close_servers(self):
        for s in self.servers:
            s.shutdown()
            s.server_close()
        for thread in self.threads:
            thread.join(2)

    def make_run(self, mode):
        run = self.store.create_run(self.project["id"], self.ticket["id"], "fixture-agent", mode, "测试人员", "契约测试")
        result = "```tmh-plan\n" + json.dumps({"files": [{"path": "app.py", "goal": "保存记录"}],
                  "ac": [{"id": "A1", "text": "读回保存记录", "check": "打开并保存", "layer": "L4"}]}, ensure_ascii=False) + "\n```"
        self.store.update_run(run["id"], status="done", exit_code=0, result=result if mode == "plan" else "测试实现",
                              diff="diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old = 1\n+new = 2\n" if mode == "fix" else "",
                              decision="accepted:tmh/test@" + self.COMMIT if mode == "fix" else "")
        if mode == "fix":
            path = self.data / "runs" / str(run["id"])
            path.mkdir(parents=True)
            (path / "verify.json").write_text(json.dumps({"check": "pass", "verdict": "pass", "files": ["app.py"],
                "commands": [{"cmd": "fixture-check", "exit_code": 0}], "beyond_plan": []}), encoding="utf-8")
        return run["id"]

    def preview_state(self, commit=None, prefix=None):
        commit = commit or self.COMMIT
        state = {"state": "up", "commit_full": commit, "commit": commit[:10],
                 "prefix": prefix or preview.bound_prefix(self.key, commit), "port": self.upstream.server_port,
                 "pid": 999999, "root": str(self.data)}
        preview._save(self.data, {self.key: state})

    def packed_link(self):
        signoff.pack(self.P, self.ticket, "测试人员")
        return signoff.issue(self.P, self.ticket, "测试人员", "测试签收人", note="明确保留测试夹具的其他验证门")

    def call(self, srv, path, method="GET", body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def gateway(self, link):
        return self.call(self.main, "/sign/" + link["token"] + "/pv/")

    def open(self, link, browser):
        status, headers, _ = self.gateway(link)
        self.assertEqual(status, 303)
        address = urlparse(headers["Location"])
        grant = parse_qs(address.query)["g"][0]
        status, headers, _ = self.call(browser, address.path + "?" + address.query)
        self.assertEqual(status, 303)
        return headers["Location"], headers["Set-Cookie"].split(";", 1)[0], grant, headers["Set-Cookie"]

    def assert_no_preview_grant(self, link, status=409):
        code, headers, _ = self.gateway(link)
        self.assertEqual(code, status)
        self.assertNotIn("Location", headers)
        self.assertNotIn("Set-Cookie", headers)

    def test_valid_signer_gets_exact_commit_cookie_and_can_read_and_save_on_both_origins(self):
        link = self.packed_link()
        expected = preview.bound_prefix(self.key, self.COMMIT) + "/"
        for separate in (False, True):
            with self.subTest(separate_origin=separate):
                self.P.preview_port = self.own.server_port if separate else 0
                browser = self.own if separate else self.main
                path, cookie, grant, cookie_header = self.open(link, browser)
                self.assertEqual(path, expected)
                self.assertIn("Path=" + expected, cookie_header)
                self.assertTrue(preview.granted(self.data, self.key, grant, expected_commit=self.COMMIT))
                self.assertFalse(preview.granted(self.data, self.key, grant))
                self.assertEqual(self.call(browser, path, headers={"Cookie": cookie})[0], 200)
                payload = b"value=reviewed-version"
                self.assertEqual(self.call(browser, path + "save", "POST", payload, {"Cookie": cookie})[2], payload)
                self.assertEqual(self.requests[-1], ("POST", expected + "save", payload))

    def test_wrong_or_legacy_preview_never_receives_a_signoff_grant(self):
        link = self.packed_link()
        self.preview_state(commit="b" * 40)
        self.assert_no_preview_grant(link)
        self.preview_state(prefix="/pv/" + self.key)
        self.assert_no_preview_grant(link)
        self.assertEqual(self.requests, [])

    def test_delivery_without_full_commit_cannot_receive_or_reuse_preview_grants(self):
        for commit in ("", "a" * 10, None):
            with self.subTest(commit=commit):
                self.binding["commit"] = commit
                link = self.packed_link()
                self.assert_no_preview_grant(link)
                grant = preview.grant(self.data, self.key, signoff._th(link["token"]))
                self.assertFalse(preview.granted(self.data, self.key, grant))

    def test_retracted_review_revokes_live_signer_cookies_and_blocks_get_and_post(self):
        link = self.packed_link()
        self.P.preview_port = self.own.server_port
        path, cookie, grant, _ = self.open(link, self.own)
        self.assertEqual(self.call(self.own, path, headers={"Cookie": cookie})[0], 200)
        self.binding["identity"]["quality"]["review"] = 30
        self.binding.update(valid=False, blocked=["质量复核已失效"])
        self.assert_no_preview_grant(link)
        self.assertFalse(preview.granted(self.data, self.key, grant, expected_commit=self.COMMIT))
        count = len(self.requests)
        for method in ("GET", "POST"):
            code, _, _ = self.call(self.own, path + "save", method, b"changed" if method == "POST" else None, {"Cookie": cookie})
            self.assertEqual(code, 401)
        self.assertEqual(len(self.requests), count, "stale sign-off must not reach the application")

    def test_new_evidence_package_revokes_old_link_and_cookie_even_with_same_code_commit(self):
        link = self.packed_link()
        path, cookie, grant, _ = self.open(link, self.main)
        self.binding["identity"]["security"]["review"] = 40
        signoff.pack(self.P, self.ticket, "重新复核人员")
        self.assertFalse(signoff.state(self.data, self.key)["stale"])
        self.assert_no_preview_grant(link)
        self.assertFalse(preview.granted(self.data, self.key, grant, expected_commit=self.COMMIT))
        self.assertEqual(self.call(self.own, path, headers={"Cookie": cookie})[0], 401)
        fresh = signoff.issue(self.P, self.ticket, "测试人员", "测试签收人", note="明确保留其他验证门")
        fresh_path, fresh_cookie, _, _ = self.open(fresh, self.main)
        self.assertEqual(self.call(self.main, fresh_path, headers={"Cookie": fresh_cookie})[0], 200)

    def test_unbound_or_wrong_commit_signer_grant_cannot_be_bridged_to_another_version(self):
        link = self.packed_link()
        for commit in ("", "b" * 40):
            with self.subTest(granted_commit=commit):
                grant = preview.grant(self.data, self.key, signoff._th(link["token"]), expected_commit=commit)
                self.assertFalse(preview.granted(self.data, self.key, grant, expected_commit=commit))
                self.preview_state(commit=commit or self.COMMIT)
                prefix = preview.bound_prefix(self.key, commit) if commit else "/pv/" + self.key
                self.assertEqual(self.call(self.own, prefix + "/__open?g=" + grant)[0], 403)
        self.assertEqual(self.requests, [])

    def test_corrupt_package_revokes_gateway_and_existing_cookie(self):
        link = self.packed_link()
        path, cookie, grant, _ = self.open(link, self.main)
        records = signoff.records(self.data, self.key)
        records[0]["by"] = "tampered"
        signoff.epath(self.data, self.key).write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        self.assert_no_preview_grant(link)
        self.assertFalse(preview.granted(self.data, self.key, grant, expected_commit=self.COMMIT))
        self.assertEqual(self.call(self.own, path, headers={"Cookie": cookie})[0], 401)

    def test_ordinary_legacy_link_and_preview_remain_usable_until_revoked_or_expired(self):
        self.binding = None
        self.preview_state(prefix="/pv/" + self.key)
        link = self.packed_link()
        links = signoff._links(self.data)
        hashed = signoff._th(link["token"])
        links[hashed].pop("pack_hash")
        signoff._save_links(self.data, links)
        path, cookie, grant, _ = self.open(link, self.main)
        self.assertEqual(path, "/pv/" + self.key + "/")
        self.assertEqual(self.call(self.main, path, headers={"Cookie": cookie})[0], 200)
        self.assertTrue(preview.granted(self.data, self.key, grant))
        for change in ({"used": "replaced"}, {"used": "", "expires": "2000-01-01 00:00:00"}):
            with self.subTest(change=change):
                links[hashed].update(change)
                signoff._save_links(self.data, links)
                self.assert_no_preview_grant(link, 410)
                self.assertFalse(preview.granted(self.data, self.key, grant))
                self.assertEqual(self.call(self.own, path, headers={"Cookie": cookie})[0], 401)


if __name__ == "__main__":
    unittest.main()
