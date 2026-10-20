"""Account login: sign-in page, session cookie, token fallback, throttling, logout."""
import http.client
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tmh.platform import login  # noqa: E402
from tmh.platform.server import Platform, make_handler  # noqa: E402


class LoginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name)
        (cls.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")
        login.set_user(cls.data, "li", "correct-horse")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Platform(cls.data, "tester"), "tok123"))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.tmp.cleanup()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        if body is not None:
            body = urlencode(body)
            h["Content-Type"] = "application/x-www-form-urlencoded"
        c.request(method, path, body, h)
        r = c.getresponse()
        return r.status, dict(r.getheaders()), r.read().decode("utf-8", "replace")

    def sign_in(self, pw="correct-horse", ip="10.0.0.1"):
        return self.req("POST", "/login", {"username": "li", "password": pw, "next": "//evil.example"},
                        {"X-Forwarded-For": ip, "X-Forwarded-Proto": "https"})

    def test_anonymous_is_sent_to_login(self):
        st, h, _ = self.req("GET", "/")
        self.assertEqual((st, h.get("Location")), (303, "/login"))
        self.assertEqual(self.req("GET", "/api/meta")[0], 401)
        st, _, body = self.req("GET", "/login")
        self.assertEqual(st, 200)
        self.assertIn('name="password"', body)

    def test_session_and_user_identity(self):
        st, h, _ = self.sign_in()
        self.assertEqual((st, h["Location"]), (303, "/"))  # off-site next is dropped
        self.assertIn("Secure", h["Set-Cookie"])
        cookie = h["Set-Cookie"].split(";")[0]
        st, _, body = self.req("GET", "/api/meta", headers={"Cookie": cookie, "X-TMH-User": "someone-else"})
        self.assertEqual(st, 200)
        self.assertIn('"user": "li"', body)
        self.assertIn('"login": true', body)
        self.assertEqual(self.req("GET", "/", headers={"Cookie": cookie})[0], 200)
        forged = cookie[:-3] + "AAA"
        self.assertEqual(self.req("GET", "/api/meta", headers={"Cookie": forged})[0], 401)

    def test_token_still_works(self):
        self.assertEqual(self.req("GET", "/api/meta", headers={"X-TMH-Token": "tok123"})[0], 200)

    def test_wrong_password_and_throttle(self):
        for _ in range(login.MAX_FAILS):
            self.assertEqual(self.sign_in("nope", ip="10.0.0.9")[0], 401)
        self.assertEqual(self.sign_in(ip="10.0.0.9")[0], 429)  # locked even with the right password
        self.assertEqual(self.sign_in(ip="10.0.0.10")[0], 303)

    def test_logout_clears_cookie(self):
        st, h, _ = self.req("GET", "/logout")
        self.assertEqual((st, h["Location"]), (303, "/login"))
        self.assertIn("Max-Age=0", h["Set-Cookie"])


if __name__ == "__main__":
    unittest.main()
