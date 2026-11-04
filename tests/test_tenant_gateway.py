"""Real loopback gateway and private worker integration; all data is synthetic."""
import concurrent.futures
import hashlib
from http.server import ThreadingHTTPServer
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from tmh.bots import feishu_encrypt
from tmh.platform import feishu_login, login, tenancy, tenant_gateway
from tmh.platform.store import Store
from tmh.platform.tenant_runtime import Workers


@unittest.skipUnless(os.name == 'posix', 'tenant gateway requires POSIX Unix sockets')
class TenantGatewayTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="tmh-gateway-")
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        password = login.hash_password("synthetic-password")
        login._save_users(self.data, {name: {"pw": password, "updated": "2026-10-23"} for name in ("owner", "alice", "bob", "outsider")})
        self.reg = tenancy.Registry(self.data, bootstrap_owner="owner")
        self.addCleanup(self.reg.close)
        self.serial = 0
        self.a = self.change("tenant_create", name="组织甲")["tenant_id"]
        self.b = self.change("tenant_create", name="组织乙", admin="bob")["tenant_id"]
        self.change("member_set", tenant=self.a, user="alice", role="member")
        for user in ("alice", "bob", "outsider"):
            self.change("member_remove", user=user)
        for tenant, title in ((self.a, "甲的真实记录"), (self.b, "乙的真实记录")):
            root = Path(self.reg.one("SELECT path FROM tenants WHERE id=?", (tenant,))["path"])
            root.mkdir(parents=True)
            (root / "repositories" / "same").mkdir(parents=True)
            (root / "repositories" / "private").mkdir()
            store = Store(root / "platform.db")
            try:
                project = store.add_project("SAME", title, str(root / "repositories" / "same"))
                store.create_ticket(project["id"], title, author="owner")
                store.add_project("PRIVATE", "不可见项目", str(root / "repositories" / "private"))
            finally:
                store.db.close()
        self.change("project_grant", tenant=self.a, user="alice", project_id=1, role="contributor")
        self.workers = Workers(self.reg)
        self.addCleanup(self.workers.close)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), tenant_gateway.make_handler(self.reg, self.workers))
        self.httpd.daemon_threads = True
        # Fixture selector cadence only: avoid accumulating the default 0.5s
        # idle shutdown wait. Request, worker and test deadlines stay unchanged.
        thread = threading.Thread(target=self.httpd.serve_forever,
                                  kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.port = self.httpd.server_address[1]
        self.cookies = {name: "tmh_session=" + login.make_session(self.data, name) for name in ("owner", "alice", "bob", "outsider")}

    def change(self, action, tenant="default", **fields):
        self.serial += 1
        body = {"action": action, "tenant": tenant, "revision": self.reg.context("owner")["revision"], "request_id": "direct-%s" % self.serial, **fields}
        return self.reg.dispatch("owner", body)

    def request(self, method, path, user=None, body=None, *, token=None, headers=None, form=False):
        h = dict(headers or {})
        if user:
            h["Cookie"] = self.cookies[user]
        if token is not None:
            h["X-Webuddy-Context"] = token
        if body is not None:
            body = urlencode(body) if form else json.dumps(body)
            h["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request(method, path, body, h)
            response = conn.getresponse()
            content = response.read().decode()
            try:
                content = json.loads(content)
            except ValueError:
                pass
            return response.status, dict(response.getheaders()), content
        finally:
            conn.close()

    def token(self, user, tenant):
        return self.reg.context(user, tenant)["context_token"]

    def test_real_workers_keep_same_project_ids_and_sessions_in_separate_tenants(self):
        for user, tenant, expected, excluded in (("alice", self.a, "甲的真实记录", "乙的真实记录"), ("bob", self.b, "乙的真实记录", "甲的真实记录")):
            status, _, meta = self.request("GET", "/t/" + tenant + "/api/meta", user, headers={"X-TMH-User": "owner"})
            self.assertEqual(status, 200, meta)
            self.assertEqual(meta["user"], user)
            self.assertEqual(meta["access"]["tenant"]["id"], tenant)
            self.assertFalse(meta["access"]["capabilities"]["execution"])
            status, _, tickets = self.request("GET", "/t/" + tenant + "/api/tickets", user, token=meta["access"]["context_token"])
            self.assertEqual(status, 200, tickets)
            self.assertIn(expected, str(tickets))
            self.assertNotIn(excluded, str(tickets))
        processes = [value["proc"].pid for value in self.workers.live.values()]
        self.assertEqual(len(set(processes)), 2)
        self.assertEqual(self.request("GET", "/t/" + self.b + "/api/meta", "alice")[0], 403)
        token = self.token("alice", self.a)
        status, _, projects = self.request("GET", "/t/" + self.a + "/api/projects", "alice", token=token)
        self.assertEqual(status, 200, projects)
        self.assertIn("SAME", str(projects))
        self.assertNotIn("PRIVATE", str(projects))
        self.assertEqual(self.request("GET", "/t/" + self.a + "/api/projects/PRIVATE", "alice", token=token)[0], 403)

    def test_all_project_boards_filter_real_worker_data_and_reject_revoked_context(self):
        root = Path(self.reg.one("SELECT path FROM tenants WHERE id=?", (self.a,))["path"])
        store = Store(root / "platform.db")
        try:
            store.create_ticket(2, "不可见项目的私密工单", author="owner")
        finally:
            store.db.close()
        token = self.token("alice", self.a)
        base = "/t/" + self.a + "/api/projects/"
        status, _, board = self.request("GET", base + "*/loop", "alice", token=token, headers={"X-TMH-User": "owner"})
        self.assertEqual(status, 200, board)
        self.assertEqual((board["total"], board["projects"]), (1, 1))
        status, _, inbox = self.request("GET", base + "all/inbox", "alice", token=token)
        self.assertEqual(status, 200, inbox)
        self.assertEqual(inbox["open"], 1)
        self.assertNotIn("不可见", str(inbox))
        self.assertNotIn("PRIVATE", str(inbox))
        for suffix in ("PRIVATE/loop", "PRIVATE/inbox"):
            self.assertEqual(self.request("GET", base + suffix, "alice", token=token)[0], 403)
        self.assertEqual(self.request("GET", "/t/" + self.b + "/api/projects/*/loop", "alice", token=token)[0], 403)
        self.change("project_revoke", tenant=self.a, user="alice", project_id=1)
        self.assertEqual(self.request("GET", base + "*/loop", "alice", token=token)[0], 409)
        status, _, empty = self.request("GET", base + "*/loop", "alice", token=self.token("alice", self.a))
        self.assertEqual(status, 200, empty)
        self.assertEqual((empty["total"], empty["projects"]), (0, 0))

    def test_global_login_home_membership_and_no_token_fallback(self):
        status, headers, _ = self.request("POST", "/login", body={"username": "alice", "password": "synthetic-password", "next": "//bad.invalid"}, form=True)
        self.assertEqual((status, headers["Location"]), (303, "/"))
        self.assertIn("Path=/", headers["Set-Cookie"])
        self.assertEqual(self.request("GET", "/", "alice")[1]["Location"], "/t/" + self.a + "/")
        status, _, content = self.request("GET", "/", "outsider")
        self.assertEqual(status, 200)
        self.assertIn("尚未加入", content)
        self.assertEqual(self.request("GET", "/t/" + self.a + "/api/meta", headers={"X-TMH-Token": "any", "X-TMH-User": "owner"})[0], 401)
        self.assertEqual(self.request("GET", "/api/meta", "owner")[0], 404)

    def test_context_is_bound_to_url_user_and_live_revision(self):
        alice = self.token("alice", self.a)
        owner = self.token("owner", self.a)
        path = "/t/" + self.a + "/api/projects"
        self.assertEqual(self.request("GET", path, "alice")[0], 409)
        self.assertEqual(self.request("GET", path, "alice", token=owner)[0], 409)
        self.change("member_set", tenant=self.a, user="alice", role="viewer")
        status, _, body = self.request("GET", path, "alice", token=alice)
        self.assertEqual((status, body["code"]), (409, "context_changed"))
        self.assertEqual(self.request("GET", "/t/" + self.a + "/api/meta", "alice")[0], 200)
        self.change("member_remove", tenant=self.a, user="alice")
        self.assertEqual(self.request("GET", path, "alice", token=alice)[0], 403)

    def test_control_plane_owner_does_not_inherit_business_access(self):
        token = self.token("owner", self.b)
        self.assertEqual(self.request("GET", "/t/" + self.b + "/", "owner")[0], 200)
        status, _, meta = self.request("GET", "/t/" + self.b + "/api/meta", "owner")
        self.assertEqual(status, 200, meta)
        self.assertFalse(meta["access"]["capabilities"]["read"])
        self.assertNotIn(self.b, self.workers.live)
        self.assertEqual(self.request("GET", "/t/" + self.b + "/api/tickets", "owner", token=token)[0], 403)
        status, _, access = self.request("GET", "/t/default/api/access?tenant=" + self.b, "owner", token=self.token("owner", "default"))
        self.assertEqual(status, 200, access)
        self.assertTrue(access["permissions"]["project_manage"])
        self.assertEqual([p["id"] for p in access["projects"]], [1, 2])
        self.assertNotIn("path", access["current_tenant"])

    def test_control_plane_replay_is_exact_original_page_bound_and_currently_authorized(self):
        token = self.token("owner", "default")
        body = {"action": "tenant_rename", "tenant": self.a, "name": "新名字", "revision": self.reg.context("owner")["revision"], "request_id": "http-retry"}
        path = "/t/default/api/access"
        first = self.request("POST", path, "owner", body, token=token, headers={"X-TMH": "1"})
        self.assertEqual(first[0], 200, first)
        second = self.request("POST", path, "owner", body, token=token, headers={"X-TMH": "1"})
        self.assertEqual(second[0], 200, second)
        self.assertTrue(second[2]["replayed"])
        self.assertEqual(first[2]["revision"], second[2]["revision"])
        self.assertEqual(self.request("POST", path, "owner", dict(body, name="forged"), token=token, headers={"X-TMH": "1"})[0], 409)
        self.assertEqual(self.request("POST", "/t/" + self.a + "/api/access", "owner", body, token=self.token("owner", self.a), headers={"X-TMH": "1"})[0], 409)
        self.assertEqual(len(self.reg.q("SELECT * FROM access_requests WHERE request_id='http-retry'")), 1)

    def test_project_grant_checks_actual_target_database_and_csrf(self):
        path = "/t/default/api/access"
        body = {"action": "project_grant", "tenant": self.a, "project_id": 999, "user": "alice", "role": "viewer", "revision": self.reg.context("owner")["revision"], "request_id": "grant-missing"}
        token = self.token("owner", "default")
        self.assertEqual(self.request("POST", path, "owner", body, token=token)[0], 403)
        self.assertEqual(self.request("POST", path, "owner", body, token=token, headers={"X-TMH": "1", "Origin": "https://bad.invalid"})[0], 403)
        self.assertEqual(self.request("POST", path, "owner", body, token=token, headers={"X-TMH": "1"})[0], 404)
        self.assertEqual(self.reg.q("SELECT * FROM access_requests WHERE request_id='grant-missing'"), [])

    def test_feishu_callback_reaches_only_the_tenant_bot_handler(self):
        root = Path(self.reg.one("SELECT path FROM tenants WHERE id=?", (self.a,))["path"]) / "repositories" / "same" / ".tmh"
        root.mkdir()
        (root / "config.json").write_text(json.dumps({"bots": {"feishu": {
            "app_id_env": "T_FS_APP", "app_secret_env": "T_FS_SECRET", "verification_token_env": "T_FS_TOKEN",
            "encrypt_key_env": "T_FS_KEY", "base_url": "http://127.0.0.1:9"}}}))
        env = {"T_FS_APP": "cli_x", "T_FS_SECRET": "s", "T_FS_TOKEN": "vtok", "T_FS_KEY": "ekey"}

        def call(path, payload, key="ekey", method="POST"):
            raw = json.dumps({"encrypt": feishu_encrypt("ekey", payload)}).encode()
            sig = hashlib.sha256(("1700000000" + "n1" + key).encode() + raw).hexdigest()
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
            try:
                conn.request(method, path, raw, {"Content-Type": "application/json", "X-Lark-Signature": sig,
                                                 "X-Lark-Request-Timestamp": "1700000000", "X-Lark-Request-Nonce": "n1"})
                r = conn.getresponse()
                return r.status, json.loads(r.read() or b"{}")
            finally:
                conn.close()

        probe = {"type": "url_verification", "challenge": "c-1", "token": "vtok"}
        with patch.dict(os.environ, env):
            self.assertEqual(call("/t/%s/bot/feishu/SAME" % self.a, probe), (200, {"challenge": "c-1"}))
            self.assertEqual(call("/t/%s/bot/feishu/SAME" % self.a, probe, key="wrong")[0], 401)
            self.assertEqual(call("/t/%s/bot/feishu/SAME" % self.a, dict(probe, token="other"))[0], 401)
            self.assertEqual(call("/t/%s/bot/feishu/SAME" % self.a, probe, method="GET")[0], 405)
            self.assertEqual(call("/t/nosuch/bot/feishu/SAME", probe)[0], 404)
            # tenant b has the same project key but no robot: its own worker answers, not a's
            self.assertEqual(call("/t/%s/bot/feishu/SAME" % self.b, probe)[0], 404)
            self.assertEqual(call("/t/%s/bot/feishu/SAME/x" % self.a, probe)[0], 403)

    def test_feishu_login_binds_once_with_password_then_signs_in(self):
        env = {"TMH_FEISHU_APP_ID": "cli_x", "TMH_FEISHU_APP_SECRET": "s", "TMH_PUBLIC_URL": "https://w.example"}
        seen, who = [], {"open_id": "ou_1"}

        def fake(url, body=None, token=""):
            seen.append((url, body, token))
            if url.endswith("/oauth/token"):
                return {"code": 0, "access_token": "u-tok"} if body["code"] == "good" else {"code": 20003}
            return {"code": 0, "data": {"open_id": who["open_id"], "tenant_key": "tk", "name": "小李"}}

        def begin(nxt="/t/x/#/t/JB-1"):
            status, headers, _ = self.request("GET", "/login/feishu?next=" + quote(nxt, safe=""))
            self.assertEqual(status, 303)
            q = parse_qs(urlsplit(headers["Location"]).query)
            self.assertEqual((q["client_id"], q["redirect_uri"], q["code_challenge_method"]),
                             (["cli_x"], ["https://w.example/login/feishu/callback"], ["S256"]))
            return q["state"][0], headers["Set-Cookie"].split(";")[0]

        def cookies(headers):
            return [v for k, v in headers if k == "Set-Cookie"]

        def raw(path, cookie):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
            try:
                conn.request("GET", path, headers={"Cookie": cookie})
                r = conn.getresponse()
                return r.status, r.getheaders(), r.read().decode()
            finally:
                conn.close()

        self.assertEqual(self.request("GET", "/login/feishu")[0], 404)
        self.assertNotIn("用飞书登录", self.request("GET", "/login")[2])
        with patch.dict(os.environ, env), patch.object(feishu_login, "_call", fake):
            self.assertIn("用飞书登录", self.request("GET", "/login")[2])
            state, flow = begin()
            # a forged or replayed state never reaches 飞书
            self.assertEqual(raw("/login/feishu/callback?code=good&state=other", flow)[0], 401)
            self.assertEqual(raw("/login/feishu/callback?code=good&state=" + state, "")[0], 401)
            self.assertEqual(seen, [])
            self.assertEqual(raw("/login/feishu/callback?code=bad&state=" + state, flow)[0], 401)
            state, flow = begin()
            status, headers, _ = raw("/login/feishu/callback?code=good&state=" + state, flow)
            self.assertEqual(status, 303)
            self.assertEqual(dict(headers)["Location"], "/login?next=" + quote("/t/x/#/t/JB-1", safe=""))
            self.assertEqual(seen[-2][1]["code_verifier"] and seen[-1][2], "u-tok")
            bind = next(c for c in cookies(headers) if c.startswith("tmh_feishu_bind=")).split(";")[0]
            self.assertFalse(any(c.startswith("tmh_session=") for c in cookies(headers)))
            status, _, page = self.request("GET", "/login", headers={"Cookie": bind})
            self.assertIn("小李", page)
            # wrong password binds nothing; the right one binds and signs in
            status, _, _ = self.request("POST", "/login", body={"username": "alice", "password": "nope"}, form=True, headers={"Cookie": bind})
            self.assertEqual(status, 401)
            self.assertIsNone(self.reg.one("SELECT 1 FROM feishu_identities"))
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
            conn.request("POST", "/login", urlencode({"username": "alice", "password": "synthetic-password", "next": "/"}),
                         {"Content-Type": "application/x-www-form-urlencoded", "Cookie": bind})
            r = conn.getresponse(); r.read(); conn.close()
            self.assertEqual(r.status, 303)
            self.assertTrue(any(c.startswith("tmh_feishu_bind=;") for c in cookies(r.getheaders())))
            self.assertEqual(self.reg.one("SELECT user,tenant_key FROM feishu_identities"), {"user": "alice", "tenant_key": "tk"})
            self.assertEqual(self.reg.one("SELECT action FROM access_audit ORDER BY id DESC LIMIT 1")["action"], "feishu_bind")
            # replaying the pending cookie with another password cannot take the identity away
            self.request("POST", "/login", body={"username": "owner", "password": "synthetic-password"}, form=True, headers={"Cookie": bind})
            self.assertEqual(self.reg.one("SELECT user FROM feishu_identities WHERE open_id='ou_1'")["user"], "alice")
            # from now on 飞书 alone signs alice in and lands on the page she asked for
            state, flow = begin("/t/%s/" % self.a)
            status, headers, _ = raw("/login/feishu/callback?code=good&state=" + state, flow)
            self.assertEqual((status, dict(headers)["Location"]), (303, "/t/%s/" % self.a))
            session = next(c for c in cookies(headers) if c.startswith("tmh_session=")).split(";")[0]
            self.assertEqual(login.read_session(self.data, session.split("=", 1)[1]), "alice")
            # signed in already: an unbound 飞书 identity binds to the open session
            who["open_id"] = "ou_2"
            state, flow = begin("/t/%s/" % self.a)
            status, headers, _ = raw("/login/feishu/callback?code=good&state=" + state, flow + "; " + self.cookies["owner"])
            self.assertEqual((status, dict(headers)["Location"]), (303, "/t/%s/" % self.a))
            self.assertEqual(self.reg.one("SELECT user FROM feishu_identities WHERE open_id='ou_2'")["user"], "owner")
            who["open_id"] = "ou_1"
            # logging out inside 飞书 does not sign straight back in
            self.assertEqual(self.request("GET", "/logout", "owner")[1]["Location"], "/login?out=1")
            self.assertNotIn("location.replace", self.request("GET", "/login?out=1")[2])
            self.assertIn("location.replace", self.request("GET", "/login")[2])
            # another enterprise is refused before any binding, and a disabled account does not sign in
            with patch.dict(os.environ, {"TMH_FEISHU_TENANT_KEY": "other"}):
                state, flow = begin()
                status, headers, _ = raw("/login/feishu/callback?code=good&state=" + state, flow)
                self.assertEqual(status, 401)
                self.assertFalse(any(c.startswith(("tmh_session=", "tmh_feishu_bind=")) for c in cookies(headers)))
            self.reg.db.execute("UPDATE accounts SET active=0 WHERE name='alice'")
            self.reg.db.commit()
            state, flow = begin()
            status, headers, _ = raw("/login/feishu/callback?code=good&state=" + state, flow)
            self.assertFalse(any(c.startswith("tmh_session=") and not c.startswith("tmh_session=;") for c in cookies(headers)))

    def test_feishu_members_of_our_enterprise_join_the_default_organization(self):
        env = {"TMH_FEISHU_APP_ID": "cli_x", "TMH_FEISHU_APP_SECRET": "s", "TMH_PUBLIC_URL": "https://w.example", "TMH_FEISHU_TENANT_KEY": "tk"}
        who = {"open_id": "ou_9", "tenant_key": "tk", "name": "王 小明"}

        def fake(url, body=None, token=""):
            return {"code": 0, "access_token": "u"} if url.endswith("/oauth/token") else {"code": 0, "data": dict(who)}

        def sign_in():
            status, headers, _ = self.request("GET", "/login/feishu?next=%2F")
            state = parse_qs(urlsplit(headers["Location"]).query)["state"][0]
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
            try:
                conn.request("GET", "/login/feishu/callback?code=c&state=" + state, headers={"Cookie": headers["Set-Cookie"].split(";")[0]})
                r = conn.getresponse(); r.read()
                return r.status, [v for k, v in r.getheaders() if k == "Set-Cookie"]
            finally:
                conn.close()

        def session(cookies):
            c = next((c for c in cookies if c.startswith("tmh_session=") and not c.startswith("tmh_session=;")), "")
            return login.read_session(self.data, c.split(";")[0].split("=", 1)[1]) if c else ""

        with patch.dict(os.environ, env), patch.object(feishu_login, "_call", fake):
            status, cookies = sign_in()
            self.assertEqual((status, session(cookies)), (303, "王小明"))
            self.assertEqual(self.reg.one("SELECT role FROM memberships WHERE tenant_id='default' AND user='王小明'")["role"], "member")
            self.assertEqual(self.reg.one("SELECT action FROM access_audit ORDER BY id DESC LIMIT 1")["action"], "feishu_join")
            self.assertFalse(login.verify(self.data, "王小明", ""))
            # the same person signs in again without a second account; a namesake gets a distinct one
            self.assertEqual(session(sign_in()[1]), "王小明")
            who["open_id"] = "ou_8888"
            self.assertEqual(session(sign_in()[1]), "王小明-8888")
            self.assertEqual(self.reg.one("SELECT COUNT(*) n FROM feishu_identities")["n"], 2)
            # another enterprise gets nothing
            who.update(open_id="ou_7", tenant_key="other")
            status, cookies = sign_in()
            self.assertEqual((status, session(cookies)), (401, ""))
        # without an enterprise key, unbound identities still need a password binding first
        with patch.dict(os.environ, dict(env, TMH_FEISHU_TENANT_KEY="")), patch.object(feishu_login, "_call", fake):
            who.update(open_id="ou_6", tenant_key="tk")
            self.assertEqual(session(sign_in()[1]), "")
            self.assertIsNone(self.reg.one("SELECT 1 FROM feishu_identities WHERE open_id='ou_6'"))

    def test_disabled_accounts_and_unsupported_public_endpoints_fail_closed(self):
        for suffix in ("/bot/a", "/hook/alert/a", "/capture/x", "/pv/a", "/v/a", "/sign/a", "/ask/a"):
            self.assertEqual(self.request("GET", "/t/" + self.a + suffix, "owner")[0], 403)
        self.reg.db.execute("UPDATE accounts SET active=0")
        self.reg.db.commit()
        self.assertTrue(login.has_accounts(self.data))
        self.assertEqual(self.request("GET", "/t/" + self.a + "/api/meta", "owner")[0], 401)
        self.assertEqual(self.request("GET", "/t/" + self.a + "/api/meta")[0], 401)

    def test_revoke_after_startup_before_guard_rejects_queued_request(self):
        started, release = threading.Event(), threading.Event()
        original = self.workers.ensure
        token = self.token("alice", self.a)
        def pause(tenant):
            original(tenant)
            started.set()
            self.assertTrue(release.wait(5))
        with patch.object(self.workers, "ensure", side_effect=pause), concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.request, "GET", "/t/" + self.a + "/api/tickets", "alice", token=token)
            self.assertTrue(started.wait(5))
            try:
                self.change("member_remove", tenant=self.a, user="alice")
            finally:
                release.set()
            self.assertEqual(future.result(timeout=8)[0], 403)

    def test_revocation_between_gateway_admission_and_worker_delivery_rejects_request(self):
        started, release, revoking, revoked = (threading.Event() for _ in range(4))
        original = self.workers.request
        token = self.token("alice", self.a)
        def pause(*args, **kwargs):
            started.set()
            self.assertTrue(release.wait(5))
            return original(*args, **kwargs)
        def revoke():
            revoking.set()
            self.change("member_remove", tenant=self.a, user="alice")
            revoked.set()
        with patch.object(self.workers, "request", side_effect=pause), concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.request, "GET", "/t/" + self.a + "/api/tickets", "alice", token=token)
            self.assertTrue(started.wait(5))
            removal = pool.submit(revoke)
            self.assertTrue(revoking.wait(2))
            try:
                self.assertTrue(revoked.wait(2), "gateway must not hold authorization while awaiting delivery")
            finally:
                release.set()
            self.assertIn(future.result(timeout=8)[0], (403, 409))
            removal.result(timeout=8)
            self.assertTrue(revoked.is_set())
        self.assertEqual(self.request("GET", "/t/" + self.a + "/api/tickets", "alice", token=token)[0], 403)

    def test_slow_response_socket_does_not_hold_revocation_guard(self):
        writing, release, revoked = (threading.Event() for _ in range(3))
        handler = self.httpd.RequestHandlerClass
        original = handler._flush
        def pause(h, *args):
            writing.set()
            self.assertTrue(release.wait(5))
            return original(h, *args)
        def revoke():
            self.change("member_remove", tenant=self.a, user="alice")
            revoked.set()
        with patch.object(handler, "_flush", pause), concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.request, "GET", "/t/" + self.a + "/api/meta", "alice")
            self.assertTrue(writing.wait(5))
            removal = pool.submit(revoke)
            try:
                self.assertTrue(revoked.wait(2), "external socket write held the authorization guard")
            finally:
                release.set()
            self.assertEqual(future.result(timeout=8)[0], 200)
            removal.result(timeout=8)
        self.assertEqual(self.request("GET", "/t/" + self.a + "/api/meta", "alice")[0], 403)


@unittest.skipUnless(os.name == 'posix', 'tenant gateway requires POSIX Unix sockets')
class GatewayShutdownTest(unittest.TestCase):
    def test_failed_default_worker_does_not_open_public_listener(self):
        with tempfile.TemporaryDirectory(prefix="tmh-gateway-startup-") as directory:
            data = Path(directory)
            login.set_user(data, "owner", "synthetic-password")
            reg = tenancy.Registry(data, bootstrap_owner="owner")
            reg.close()
            with patch.object(Workers, 'ensure', side_effect=OSError('synthetic worker startup failure')), patch('tmh.platform.tenant_gateway.ThreadingHTTPServer') as listener:
                with self.assertRaises(OSError):
                    tenant_gateway.serve(data, '127.0.0.1', 0)
                listener.assert_not_called()
            reg = tenancy.Registry(data)
            try:
                workers = Workers(reg)
                workers.close()
            finally:
                reg.close()

    def test_sigterm_reaps_private_worker_and_releases_lifetime_lock(self):
        with tempfile.TemporaryDirectory(prefix="tmh-gateway-shutdown-") as directory:
            data = Path(directory)
            login.set_user(data, "owner", "synthetic-password")
            reg = tenancy.Registry(data, bootstrap_owner="owner")
            cookie = "tmh_session=" + login.make_session(data, "owner")
            reg.close()
            script = '''
import json, sys
from pathlib import Path
from tmh.platform import tenant_gateway as g, tenant_runtime as r
data=Path(sys.argv[1]); original=g.ThreadingHTTPServer; ensure=r.Workers.ensure
def server(*args, **kwargs):
    value=original(*args, **kwargs)
    (data/'port').write_text(str(value.server_address[1]))
    return value
def record(self, tenant):
    value=ensure(self, tenant)
    (data/'pids').write_text(json.dumps([v['proc'].pid for v in self.live.values()]))
    return value
g.ThreadingHTTPServer=server; r.Workers.ensure=record
g.serve(data, '127.0.0.1', 0)
'''
            proc = subprocess.Popen([sys.executable, "-c", script, str(data)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            pids = []
            try:
                deadline = time.monotonic() + 5
                while not (data / "port").exists() and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue((data / "port").exists(), "gateway failed to open a listener")
                self.assertTrue((data / "pids").exists(), "public listener opened before the default worker was ready")
                pids = json.loads((data / "pids").read_text())
                self.assertEqual(len(pids), 1)
                os.kill(pids[0], 0)
                conn = http.client.HTTPConnection("127.0.0.1", int((data / "port").read_text()), timeout=10)
                try:
                    conn.request("GET", "/t/default/api/meta", headers={"Cookie": cookie})
                    response = conn.getresponse()
                    payload = response.read()
                    self.assertEqual(response.status, 200, payload)
                finally:
                    conn.close()
                pids = json.loads((data / "pids").read_text())
                self.assertEqual(len(pids), 1)
                proc.send_signal(signal.SIGTERM)
                _, stderr = proc.communicate(timeout=8)
                self.assertEqual(proc.returncode, 0, stderr)
                for pid in pids:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pid, 0)
                reg = tenancy.Registry(data)
                try:
                    workers = Workers(reg)
                    workers.close()
                finally:
                    reg.close()
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.communicate(timeout=8)
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
