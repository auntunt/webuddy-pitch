"""Serving tests for the /next/ Vue frontend shell: auth parity with /, hashed assets, traversal safety."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from tmh.platform.server import Platform, make_handler
from tmh.platform.httpd.handler import WEB_DIST

TOKEN = "next-test-token"


class NextFrontendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.P = Platform(Path(cls.tmp.name), "tester")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.P, TOKEN))
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.tmp.cleanup()

    def get(self, path, headers=None, method="GET"):
        req = urllib.request.Request(self.base + path, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_next_requires_the_same_token_as_root(self):
        code, _, body = self.get("/next/")
        self.assertEqual(code, 401)
        self.assertIn("需要访问令牌".encode(), body)
        code, _, body = self.get("/")
        self.assertEqual(code, 401)
        self.assertEqual(body, self.get("/next/")[2])

    def test_next_token_query_sets_the_same_cookie_and_serves_spa(self):
        code, headers, body = self.get("/next/?token=" + TOKEN)
        self.assertEqual(code, 200)
        self.assertIn("tmh_token=%s" % TOKEN, headers.get("Set-Cookie", ""))
        self.assertIn(b"<base href=\"/next/\">", body)
        self.assertIn(b'<div id="app">', body)

    def test_next_deep_link_serves_index_with_base(self):
        code, _, body = self.get("/next/p/E2E/candidates/7?token=" + TOKEN)
        self.assertEqual(code, 200)
        self.assertIn(b"<base href=\"/next/\">", body)

    def test_next_assets_immutable_and_typed(self):
        assets = sorted((WEB_DIST / "assets").iterdir())
        self.assertTrue(assets, "web_dist assets missing; run npm run build")
        js = next(a for a in assets if a.suffix == ".js")
        code, headers, body = self.get("/next/assets/" + js.name + "?token=" + TOKEN)
        self.assertEqual(code, 200)
        self.assertEqual(headers.get("Cache-Control"), "public, max-age=31536000, immutable")
        self.assertIn("javascript", headers.get("Content-Type", ""))
        self.assertEqual(body, js.read_bytes())

    def test_next_asset_missing_and_traversal_rejected(self):
        code, _, _ = self.get("/next/assets/nope-123.js?token=" + TOKEN)
        self.assertEqual(code, 404)
        for bad in ("/next/assets/..%2Findex.html", "/next/assets/%2e%2e%2f%2e%2e%2fpyproject.toml",
                    "/next/assets/..", "/next/assets/a/b.js"):
            code, headers, body = self.get(bad + ("&" if "?" in bad else "?") + "token=" + TOKEN)
            self.assertNotEqual(code, 200, bad)
            self.assertNotIn(b"pyproject", body)

    def test_next_head_and_post_method_behavior(self):
        code, headers, body = self.get("/next/?token=" + TOKEN, method="HEAD")
        self.assertEqual(code, 200)
        self.assertEqual(body, b"")
        code, _, _ = self.get("/next/", method="POST")
        self.assertEqual(code, 405)

    def test_legacy_root_unchanged(self):
        code, _, body = self.get("/")
        self.assertEqual(code, 401)
        code, _, body = self.get("/?token=" + TOKEN)
        self.assertEqual(code, 200)
        self.assertNotIn(b"<base href=\"/next/\">", body)
        self.assertIn(b"X-TMH", body)

    def test_next_with_accounts_redirects_to_login(self):
        from tmh.platform import login
        login.set_user(Path(self.tmp.name), "nextuser", "synthetic-password")

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        req = urllib.request.Request(self.base + "/next/p/E2E/verify")
        try:
            opener.open(req, timeout=10)
            self.fail("expected redirect")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 303)
            self.assertIn("/login?next=", e.headers.get("Location", ""))
        session = login.make_session(Path(self.tmp.name), "nextuser")
        code, _, body = self.get("/next/", headers={"Cookie": "tmh_session=" + session})
        self.assertEqual(code, 200)
        self.assertIn(b"<base href=\"/next/\">", body)


if __name__ == "__main__":
    unittest.main()
