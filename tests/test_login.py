"""Account login: sign-in page, session cookie, token fallback, throttling, logout."""
import http.client
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
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
        cls.platform = Platform(cls.data, "tester")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.platform, "tok123"))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.platform.store.db.close()
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


class LanRegistrationTest(LoginTest):
    def test_registration_is_opt_in(self):
        with patch.dict("os.environ", {"WEBUDDY_LAN_SIGNUP": ""}):
            self.assertEqual(self.req("GET", "/register")[0], 404)

    def test_register_auto_login_admin_and_duplicate(self):
        from tmh.platform.tenancy import Registry
        with patch.dict("os.environ", {"WEBUDDY_LAN_SIGNUP": "admin"}):
            body = {"username": "lan-person", "password": "test-password-123", "next": "/next/"}
            self.assertEqual(self.req("POST", "/register", body)[0], 403)
            headers = {"Origin": "http://127.0.0.1:%s" % self.port}
            status, response, _ = self.req("POST", "/register", body, headers)
            self.assertEqual(status, 303)
            self.assertEqual(response["Location"], "/next/")
            cookie = response["Set-Cookie"].split(";")[0]
            self.assertEqual(self.req("GET", "/api/meta", headers={"Cookie": cookie})[0], 200)
            reg = Registry(self.data)
            try:
                self.assertTrue(reg.context("lan-person")["platform_owner"])
                self.assertEqual(reg.context("lan-person")["role"], "admin")
            finally:
                reg.close()
            self.assertEqual(self.req("POST", "/register", {**body, "password": "replacement-pass"}, headers)[0], 400)
            self.assertTrue(login.verify(self.data, "lan-person", body["password"]))

    def test_empty_instance_requires_login(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"WEBUDDY_LAN_SIGNUP": "admin"}):
            platform = Platform(Path(directory), "tester")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(platform, ""))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
                conn.request("GET", "/next/")
                response = conn.getresponse()
                self.assertEqual(response.status, 303)
                self.assertTrue(response.getheader("Location").startswith("/login"))
                response.read()
                conn.close()
            finally:
                server.shutdown()
                server.server_close()
                platform.store.db.close()




class LanRestartTest(unittest.TestCase):
    def test_registered_instance_restarts_as_standalone(self):
        import importlib
        serve = importlib.import_module('tmh.platform.httpd.serve')
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ', {'WEBUDDY_LAN_SIGNUP': 'admin'}):
            data = Path(d)
            login.register(data, 'pilot', 'pilot-password')
            cookie = login.make_session(data, 'pilot')
            with patch.object(serve, 'Platform', side_effect=RuntimeError('standalone-selected')):
                with self.assertRaisesRegex(RuntimeError, 'standalone-selected'):
                    serve.serve(data)
            self.assertEqual(login.read_session(data, cookie), 'pilot')
            self.assertTrue(login.verify(data, 'pilot', 'pilot-password'))
            with patch.dict('os.environ', {'WEBUDDY_LAN_SIGNUP': ''}), patch('tmh.platform.tenant_gateway.serve', return_value=7) as gateway:
                self.assertEqual(serve.serve(data), 7)
                gateway.assert_called_once()

    def test_registration_flag_cannot_bypass_tenant_isolation(self):
        import importlib
        from tmh.platform.tenancy import Registry
        serve = importlib.import_module('tmh.platform.httpd.serve')
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ', {'WEBUDDY_LAN_SIGNUP': 'admin'}):
            data = Path(d)
            login.register(data, 'pilot', 'pilot-password')
            reg = Registry(data)
            try:
                with reg.transaction() as db:
                    db.execute("UPDATE tenants SET runtime='isolated' WHERE id='default'")
            finally:
                reg.close()
            with patch.object(serve, 'Platform') as platform:
                with self.assertRaisesRegex(ValueError, '不能接管'):
                    serve.serve(data)
                platform.assert_not_called()


if __name__ == "__main__":
    unittest.main()
