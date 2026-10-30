"""Synthetic accounts/tenants only; never provisions a Platform or a worker."""
import concurrent.futures
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from tmh.platform import login, tenancy as T
from tmh.platform.errors import ApiError


class TenancyTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="tmh-tenancy-")
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        self.users = {name: {"pw": login.hash_password("synthetic-password"), "updated": "2026-10-23"} for name in ("owner", "alice", "bob")}
        login._save_users(self.data, self.users)
        self.legacy = (self.data / "users.json").read_bytes()
        self.reg = T.Registry(self.data, bootstrap_owner="owner")
        self.addCleanup(self.reg.close)
        self.seq = 0

    def body(self, action, tenant="default", **kwargs):
        self.seq += 1
        return {"action": action, "tenant": tenant, "revision": self.reg.one("SELECT revision FROM access_meta")["revision"], "request_id": "test-%s" % self.seq, **kwargs}

    def action(self, action, actor="owner", tenant="default", **kwargs):
        return T.dispatch(self.reg, actor, self.body(action, tenant, **kwargs))

    def assert_api(self, code, fn):
        with self.assertRaises(ApiError) as error:
            fn()
        self.assertEqual(error.exception.code, code)
        return error.exception

    def snapshot(self):
        with self.reg.lock:
            old = self.reg.db.row_factory
            try:
                self.reg.db.row_factory = None
                return tuple(self.reg.db.iterdump())
            finally:
                self.reg.db.row_factory = old

    def second(self):
        reg = T.Registry(self.data)
        self.addCleanup(reg.close)
        return reg

    def test_default_migration_preserves_original_data_and_does_not_elevate_members(self):
        self.assertEqual((self.data / "users.json").read_bytes(), self.legacy)
        self.assertEqual(self.reg.context("alice")["role"], "member")
        self.assertEqual(self.reg.context("owner")["role"], "admin")
        self.assertEqual(self.reg.context("owner")["tenant"]["path"], str(self.data.resolve()))
        self.assertEqual(self.reg.context("owner")["tenant"]["runtime"], "legacy")
        self.assert_api(403, lambda: T.authorize(self.reg, "alice", "default", "read", "1"))
        before = self.snapshot()
        self.second()
        self.assertEqual(self.snapshot(), before)

    def test_owner_bootstrap_is_explicit_and_cannot_replace_existing_owner(self):
        self.assert_api(409, lambda: T.Registry(self.data, bootstrap_owner="alice"))
        self.assertEqual(self.reg.q("SELECT * FROM platform_owners"), [{"name": "owner"}])
        self.assert_api(403, lambda: self.action("tenant_create", "alice", name="Unauthorized"))

    def test_failed_initial_bootstrap_publishes_no_control_database(self):
        other = self.data / "bootstrap-failure"
        other.mkdir()
        login._save_users(other, self.users)
        self.assert_api(400, lambda: T.Registry(other, bootstrap_owner="missing"))
        self.assertFalse((other / "control/access.db").exists())
        self.assertEqual(list((other / "control").glob("*.tmp")), [])
        self.assertTrue(login.verify(other, "owner", "synthetic-password"))
        repaired = T.Registry(other, bootstrap_owner="owner")
        try:
            self.assertTrue(repaired.context("owner")["platform_owner"])
        finally:
            repaired.close()

    def test_legacy_control_receipts_gain_context_columns_without_rebinding(self):
        self.reg.db.execute("DROP TABLE access_requests")
        self.reg.db.execute("CREATE TABLE access_requests(actor TEXT,request_id TEXT,fingerprint TEXT,result TEXT,PRIMARY KEY(actor,request_id))")
        self.reg.db.execute("INSERT INTO access_requests VALUES('owner','old','fingerprint','{}')")
        self.reg.db.commit()
        migrated = self.second()
        old = migrated.one("SELECT * FROM access_requests WHERE request_id='old'")
        self.assertEqual(old["context_tenant"], "")
        self.assertEqual(old["context_digest"], "")
        self.assertEqual(old["fingerprint"], "fingerprint")
        self.assertFalse(T.bound_receipt(migrated, "owner", {"request_id": "old"}, "default", "token"))

    def test_owner_can_manage_grants_without_own_business_membership(self):
        tenant = self.action("tenant_create", name="Managed only", admin="alice")["tenant_id"]
        self.action("project_grant", tenant=tenant, user="alice", project_id="1", role="manager")
        self.assertTrue(self.reg.read("owner", tenant)["permissions"]["project_manage"])
        self.assertFalse(self.reg.context("owner", tenant)["capabilities"]["read"])
        self.assert_api(403, lambda: T.authorize(self.reg, "owner", tenant, "read", "1"))

    def test_tenant_creation_is_server_planned_and_never_initializes_runtime(self):
        with patch("tmh.platform.server.Platform", side_effect=AssertionError("must not start worker")):
            out = self.action("tenant_create", name="客户组织", admin="alice")
        tenant = self.reg.context("alice", out["tenant_id"])["tenant"]
        self.assertEqual(tenant["runtime"], "disabled")
        self.assertEqual(Path(tenant["path"]), self.data.resolve() / "tenants" / tenant["id"] / "data")
        self.assertFalse(Path(tenant["path"]).exists())
        self.assert_api(400, lambda: self.action("tenant_create", name="bad", path="/etc"))
        self.assert_api(403, lambda: T.authorize(self.reg, "alice", tenant["id"], "execution", "1"))
        self.assert_api(403, lambda: T.authorize(self.reg, "owner", tenant["id"], "read", "1"))

    def test_tenant_admin_cannot_manage_another_tenant_or_global_accounts(self):
        a = self.action("tenant_create", name="A", admin="alice")["tenant_id"]
        b = self.action("tenant_create", name="B", admin="bob")["tenant_id"]
        self.assert_api(403, lambda: T.context(self.reg, "alice", b))
        self.assert_api(403, lambda: self.action("tenant_rename", "alice", b, name="stolen"))
        self.assert_api(403, lambda: self.action("account_create", "alice", a, user="intruder", password="synthetic-password"))
        self.action("tenant_rename", "alice", a, name="自己的组织")
        self.assertEqual(self.reg.context("alice", a)["tenant"]["name"], "自己的组织")

    def test_roles_grants_and_revocation_are_checked_server_side(self):
        self.action("project_grant", project_id="P1", user="alice", role="contributor")
        self.assertEqual(T.authorize(self.reg, "alice", "default", "write", "P1")["role"], "member")
        self.assert_api(403, lambda: T.authorize(self.reg, "alice", "default", "project_manage", "P1"))
        self.action("project_grant", project_id="P1", user="alice", role="manager")
        T.authorize(self.reg, "alice", "default", "project_manage", "P1")
        self.action("member_set", user="alice", role="viewer")
        T.authorize(self.reg, "alice", "default", "read", "P1")
        self.assert_api(403, lambda: T.authorize(self.reg, "alice", "default", "write", "P1"))
        self.action("project_revoke", project_id="P1", user="alice")
        self.assert_api(403, lambda: T.authorize(self.reg, "alice", "default", "read", "P1"))

    def test_member_removal_deletes_grants_and_invalidates_context(self):
        self.action("project_grant", project_id=1, user="alice", role="contributor")
        token = self.reg.context("alice")["context_token"]
        self.action("member_remove", user="alice")
        self.assert_api(403, lambda: self.reg.context("alice"))
        self.assertEqual(self.reg.q("SELECT * FROM project_grants WHERE user='alice'"), [])
        self.action("member_set", user="alice", role="member")
        self.assertNotEqual(self.reg.context("alice")["context_token"], token)
        self.assertEqual(self.reg.directory("default")["alice"], {"name": "alice", "role": "member"})
        self.assertNotIn("pw", json.dumps(self.reg.directory("default")))

    def test_last_admin_self_lockout_and_owner_disable_are_rejected(self):
        a = self.action("tenant_create", name="A", admin="alice")["tenant_id"]
        self.assert_api(409, lambda: self.action("member_remove", tenant=a, user="alice"))
        self.assert_api(409, lambda: self.action("account_disable", user="alice"))
        self.assert_api(409, lambda: self.action("member_set", user="owner", role="viewer"))
        self.assert_api(409, lambda: self.action("account_disable", user="owner"))
        self.assert_api(409, lambda: self.action("tenant_disable"))
        self.action("member_set", tenant=a, user="bob", role="admin")
        self.action("member_remove", tenant=a, user="alice")
        self.assert_api(403, lambda: self.reg.context("alice", a))

    def test_disable_blocks_business_but_owner_can_reenable(self):
        a = self.action("tenant_create", name="A", admin="alice")["tenant_id"]
        self.action("tenant_disable", tenant=a)
        self.assert_api(403, lambda: T.authorize(self.reg, "alice", a, "read", "1"))
        self.action("tenant_enable", tenant=a)
        T.authorize(self.reg, "alice", a, "read", "1")
        self.assert_api(403, lambda: T.authorize(self.reg, "alice", a, "execution", "1"))

    def test_accounts_are_transactional_and_password_never_enters_audit_receipt(self):
        password = "unique-synthetic-plain-secret"
        self.action("account_create", user="newperson", password=password)
        self.assertTrue(login.verify(self.data, "newperson", password))
        self.assert_api(403, lambda: self.reg.context("newperson"))
        self.action("member_set", user="newperson", role="member")
        self.action("password_reset", user="newperson", password="other-synthetic-password")
        self.assertFalse(login.verify(self.data, "newperson", password))
        self.action("account_disable", user="newperson")
        self.assertNotIn("newperson", login.load_users(self.data))
        self.action("account_enable", user="newperson")
        self.assertIn("newperson", login.load_users(self.data))
        dump = json.dumps(T.read(self.reg, "owner"))
        self.assertNotIn(password, dump)
        self.assertNotIn("pbkdf2_sha256", dump)
        self.assertNotIn(password, str(self.reg.q("SELECT * FROM access_audit")))
        self.assertNotIn(password, str(self.reg.q("SELECT * FROM access_requests")))

    def test_password_receipts_use_salted_slow_fingerprints_and_bind_every_field(self):
        body = self.body("password_reset", user="alice", password="synthetic-new-password")
        token = self.reg.context("owner")["context_token"]
        out = self.reg.dispatch("owner", body, request_context={"tenant": "default", "token": token})
        row = self.reg.one("SELECT * FROM access_requests WHERE request_id=?", (body["request_id"],))
        self.assertTrue(row["fingerprint"].startswith("pbkdf2_sha256$240000$"))
        self.assertNotEqual(row["fingerprint"], T.digest(body))
        self.assertNotEqual(T.request_fingerprint(body), T.request_fingerprint(body))
        self.assertTrue(T.fingerprint_matches(body, row["fingerprint"]))
        self.assertTrue(T.bound_receipt(self.reg, "owner", body, "default", token))
        self.assertTrue(self.reg.dispatch("owner", body)["replayed"])
        self.assertEqual(self.reg.context("owner")["revision"], out["revision"])
        changed = dict(body, password="different-new-password")
        self.assertFalse(T.bound_receipt(self.reg, "owner", changed, "default", token))
        self.assert_api(409, lambda: self.reg.dispatch("owner", changed))
        # Experimental unsalted receipts are never accepted for a password write.
        self.reg.db.execute("UPDATE access_requests SET fingerprint=? WHERE request_id=?", (T.digest(body), body["request_id"]))
        self.reg.db.commit()
        self.assertFalse(T.bound_receipt(self.reg, "owner", body, "default", token))
        self.assert_api(409, lambda: self.reg.dispatch("owner", body))
        self.assertTrue(login.verify(self.data, "alice", body["password"]))

    def test_exact_replay_different_payload_and_stale_revision(self):
        body = self.body("member_set", user="alice", role="viewer")
        first = T.dispatch(self.reg, "owner", body)
        second = T.dispatch(self.reg, "owner", body)
        self.assertTrue(second["replayed"])
        self.assertEqual(first["revision"], second["revision"])
        self.assert_api(409, lambda: T.dispatch(self.reg, "owner", dict(body, role="admin")))
        self.assert_api(409, lambda: T.dispatch(self.reg, "owner", dict(body, request_id="new-id")))
        self.assertEqual(len(self.reg.q("SELECT * FROM access_requests")), 1)

    def test_receipt_failure_rolls_back_password_role_and_audit(self):
        self.reg.db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON access_requests BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        self.reg.db.commit()
        before = self.snapshot()
        body = self.body("password_reset", user="alice", password="changed-password")
        with self.assertRaises(sqlite3.IntegrityError):
            T.dispatch(self.reg, "owner", body)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(login.verify(self.data, "alice", "synthetic-password"))

    def test_two_connections_same_revision_have_one_winner(self):
        other = self.second()
        body = self.body("member_set", user="alice", role="viewer")
        barrier = threading.Barrier(2)
        def change(reg, request):
            barrier.wait()
            try:
                return T.dispatch(reg, "owner", dict(body, request_id=request))["changed"]
            except ApiError as exc:
                return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(change, self.reg, "one")
            two = pool.submit(change, other, "two")
            results = [one.result(timeout=10), two.result(timeout=10)]
        self.assertCountEqual(results, [True, 409])
        self.assertEqual(len(self.reg.q("SELECT * FROM access_requests")), 1)

    def test_concurrent_same_request_replays_once(self):
        other = self.second()
        body = self.body("tenant_create", name="Once")
        barrier = threading.Barrier(2)
        def change(reg):
            barrier.wait()
            return T.dispatch(reg, "owner", body)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(change, (self.reg, other)))
        self.assertEqual(results[0]["tenant_id"], results[1]["tenant_id"])
        self.assertEqual(sum(r["replayed"] for r in results), 1)
        self.assertEqual(len(self.reg.q("SELECT * FROM tenants")), 2)

    def test_authorization_guard_is_reentrant_and_revocation_waits_for_request(self):
        other = self.second()
        self.action("project_grant", user="alice", project_id="1", role="contributor")
        body = self.body("project_revoke", user="alice", project_id="1")
        started = threading.Event()
        finished = threading.Event()
        def revoke():
            started.set()
            T.dispatch(other, "owner", body)
            finished.set()
        with self.reg.authorization_guard(), other.authorization_guard():
            T.authorize(self.reg, "alice", "default", "write", "1")
            thread = threading.Thread(target=revoke)
            thread.start()
            self.assertTrue(started.wait(2))
            self.assertFalse(finished.wait(.05))
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(finished.is_set())
        self.assert_api(403, lambda: T.authorize(self.reg, "alice", "default", "write", "1"))

    def test_different_tenant_grants_do_not_leak_same_project_id(self):
        a = self.action("tenant_create", name="A")["tenant_id"]
        self.action("member_set", tenant=a, user="alice", role="member")
        self.action("project_grant", user="alice", project_id="1", role="contributor")
        self.assert_api(403, lambda: T.authorize(self.reg, "alice", a, "read", "1"))
        self.action("project_grant", tenant=a, user="alice", project_id="1", role="viewer")
        T.authorize(self.reg, "alice", a, "read", "1")
        self.assert_api(403, lambda: T.authorize(self.reg, "alice", a, "write", "1"))

    def test_schema_failure_is_atomic_and_nested_transaction_not_committed(self):
        other = self.data / "other"
        other.mkdir()
        with patch.object(T, "DDL", T.DDL + ("INVALID SQL",)):
            with self.assertRaises(sqlite3.OperationalError):
                T.Registry(other)
        self.assertFalse((other / "control/access.db").exists())
        self.assertEqual(list((other / "control").glob("*.tmp")), [])
        self.reg.db.execute("BEGIN IMMEDIATE")
        self.reg.db.execute("UPDATE access_meta SET revision=999")
        with self.assertRaises(RuntimeError):
            with self.reg.transaction():
                pass
        self.assertTrue(self.reg.db.in_transaction)
        self.reg.db.rollback()
        self.assertNotEqual(self.reg.context("owner")["revision"], 999)


if __name__ == "__main__":
    unittest.main()
