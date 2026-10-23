"""Member-owned tool grants use synthetic control databases, never real accounts."""
import concurrent.futures
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from tmh.platform import login, tenancy as T, tool_access as A
from tmh.platform.errors import ApiError


class ToolAccessTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-tool-access-")
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        password = login.hash_password("synthetic-password")
        login._save_users(self.data, {name: {"pw": password} for name in ("owner", "alice", "bob")})
        self.reg = T.Registry(self.data, bootstrap_owner="owner")
        self.addCleanup(self.reg.close)
        self.sequence = 0
        self.change("project_grant", user="alice", project_id=1, role="contributor")
        self.change("project_grant", user="alice", project_id=2, role="viewer")
        self.change("project_grant", user="bob", project_id=1, role="contributor")

    def change(self, action, tenant="default", **fields):
        self.sequence += 1
        return self.reg.dispatch("owner", {"action": action, "tenant": tenant, "revision": self.reg.context("owner")["revision"], "request_id": "access-%d" % self.sequence, **fields})

    def body(self, **fields):
        self.sequence += 1
        return {"label": "Claude development", "project_ids": [1], "scope": "content", "expires_days": 7, "request_id": "tools-%d" % self.sequence, **fields}

    def mint(self, user="alice", tenant="default", **fields):
        return A.create(self.reg, user, tenant, self.body(**fields))

    def denied(self, code, call):
        with self.assertRaises(ApiError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def snapshot(self):
        with self.reg.lock:
            return tuple(self.reg.db.iterdump())

    def second(self):
        registry = T.Registry(self.data)
        self.addCleanup(registry.close)
        return registry

    def test_connection_context_is_stable_across_unrelated_authorization_changes(self):
        first = self.mint()
        browser_before = self.reg.context("alice")["context_token"]
        tool_before = A.context_token(first["connection"])
        tenant = self.change("tenant_create", name="Other organization", admin="bob")["tenant_id"]
        self.change("member_set", tenant=tenant, user="bob", role="admin")
        self.assertNotEqual(self.reg.context("alice")["context_token"], browser_before)
        current = A.authenticate(self.reg, "default", first["token"])
        self.assertEqual(A.context_token(current), tool_before)
        self.assertEqual(A.context_token(A.validate_connection(self.reg, "default", current["id"], "alice")), tool_before)

    def test_connection_context_binds_each_immutable_field_but_does_not_replace_validation(self):
        first = self.mint()
        record = first["connection"]
        original = A.context_token(record)
        self.assertRegex(original, r"^[a-f0-9]{64}$")
        for field, value in (("id", "0" * 32), ("user", "bob"), ("tenant", "another"), ("scope", "read"), ("project_ids", [2]), ("expires_at", record["expires_at"] + 1)):
            with self.subTest(field=field):
                self.assertNotEqual(A.context_token(dict(record, **{field: value})), original)
        self.assertEqual(A.context_token(dict(record, label="different display label", revision=999, context_token="browser-state")), original)
        self.assertEqual(A.context_token(dict(record, project_ids=[2, 1])), A.context_token(dict(record, project_ids=[1, 2])))
        A.revoke(self.reg, "alice", "default", {"connection_id": record["id"], "request_id": "context-revoke"})
        revoked = A.listing(self.reg, "alice", "default")["connections"][0]
        self.assertEqual(A.context_token(revoked), original)
        self.denied(401, lambda: A.validate_connection(self.reg, "default", record["id"], "alice"))

    def test_member_can_issue_only_own_scoped_connection_and_secret_is_stored_nowhere(self):
        out = self.mint()
        self.assertFalse(out["replayed"])
        self.assertRegex(out["token"], r"^wbt_[a-f0-9]{32}\.[A-Za-z0-9_-]{43}$")
        item = out["connection"]
        self.assertEqual((item["user"], item["tenant"], item["scope"], item["project_ids"]), ("alice", "default", "content", [1]))
        self.assertTrue(item["active"])
        self.assertEqual(A.authenticate(self.reg, "default", out["token"]), item)
        self.assertEqual(A.validate_connection(self.reg, "default", item["id"], "alice"), item)
        dump = "\n".join(self.snapshot())
        self.assertNotIn(out["token"], dump)
        self.assertNotIn(out["token"].split(".")[1], dump)
        self.assertNotIn("secret_hash", json.dumps(item))
        self.assertNotIn("account_epoch", json.dumps(item))
        self.assertEqual(A.listing(self.reg, "alice", "default")["connections"], [item])
        self.assertEqual(A.listing(self.reg, "bob", "default")["connections"], [])
        self.assertEqual(A.listing(self.reg, "owner", "default")["connections"], [])
        self.denied(401, lambda: A.validate_connection(self.reg, "default", item["id"], "bob"))

    def test_scope_and_identity_are_allowlisted_not_tool_name_or_owner_fields(self):
        for fields in ({"user": "owner"}, {"owner": "owner"}, {"scope": "execution"}, {"scope": "operator"}, {"project_ids": [3]}, {"project_ids": [1, 2]}):
            self.denied(403 if fields.get("project_ids") else 400, lambda fields=fields: A.create(self.reg, "alice", "default", self.body(**fields)))
        item = self.mint(label="owner / admin / reviewer", scope="read", project_ids=[2])
        self.assertEqual(A.authenticate(self.reg, "default", item["token"])["user"], "alice")
        self.assertEqual(set(A.allowed_operations("content")) - set(A.allowed_operations("read")), {"ticket_create", "message_send"})
        for scope in ("read", "content"):
            self.assertFalse(set(A.allowed_operations(scope)) & {"run_start", "candidate_adopt", "review", "accept", "close", "operation", "message_dispatch"})
        self.assertEqual(A.allowed_operations("operator"), ())

    def test_create_validates_payload_before_any_write(self):
        for fields in ({"project_ids": []}, {"project_ids": [True]}, {"project_ids": ["1"]}, {"project_ids": [0]}, {"project_ids": [1, 1]}, {"expires_days": True}, {"expires_days": 0}, {"expires_days": 31}, {"label": " "}, {"label": "x" * 121}, {"request_id": "has space"}, {"action": "revoke"}):
            before = self.snapshot()
            self.denied(400, lambda fields=fields: self.mint(**fields))
            self.assertEqual(self.snapshot(), before)

    def test_exact_create_replay_never_returns_secret_and_conflict_does_not_mutate(self):
        body = self.body(action="create")
        first = A.create(self.reg, "alice", "default", body)
        before = self.snapshot()
        replay = A.create(self.reg, "alice", "default", body)
        self.assertEqual(replay["connection"], first["connection"])
        self.assertTrue(replay["credential_unavailable"])
        self.assertTrue(replay["replayed"])
        self.assertNotIn("token", replay)
        self.denied(409, lambda: A.create(self.reg, "alice", "default", dict(body, label="different")))
        self.assertEqual(before, self.snapshot())

    def test_replay_is_reauthorized_after_revoke_or_scope_loss(self):
        body = self.body()
        first = A.create(self.reg, "alice", "default", body)
        self.change("project_revoke", user="alice", project_id=1)
        self.denied(403, lambda: A.create(self.reg, "alice", "default", body))
        self.change("project_grant", user="alice", project_id=1, role="contributor")
        replay = A.create(self.reg, "alice", "default", body)
        self.assertEqual(replay["connection"]["id"], first["connection"]["id"])
        self.assertFalse(replay["connection"]["active"])
        self.assertNotIn("token", replay)
        self.denied(401, lambda: A.authenticate(self.reg, "default", first["token"]))

    def test_authority_changes_are_precise_and_regrant_never_revives_old_credentials(self):
        first = self.mint()
        self.change("project_grant", user="bob", project_id=1, role="viewer")
        self.change("project_grant", user="alice", project_id=2, role="contributor")
        self.change("project_grant", user="alice", project_id=1, role="contributor")
        self.assertTrue(A.authenticate(self.reg, "default", first["token"])["active"])
        self.change("project_grant", user="alice", project_id=1, role="viewer")
        self.denied(401, lambda: A.authenticate(self.reg, "default", first["token"]))
        self.change("project_grant", user="alice", project_id=1, role="contributor")
        self.denied(401, lambda: A.authenticate(self.reg, "default", first["token"]))
        self.assertTrue(A.authenticate(self.reg, "default", self.mint()["token"])["active"])

    def test_member_removal_and_readdition_never_revives_credentials(self):
        first = self.mint()
        self.change("member_remove", user="alice")
        self.denied(401, lambda: A.authenticate(self.reg, "default", first["token"]))
        self.denied(403, lambda: A.listing(self.reg, "alice", "default"))
        self.change("member_set", user="alice", role="member")
        self.change("project_grant", user="alice", project_id=1, role="contributor")
        self.denied(401, lambda: A.authenticate(self.reg, "default", first["token"]))

    def test_account_reset_and_local_account_change_invalidate_all_tenants(self):
        first = self.mint()
        self.change("password_reset", user="alice", password="new-synthetic-password")
        self.denied(401, lambda: A.authenticate(self.reg, "default", first["token"]))
        second = self.mint()
        T.local_set_user(self.data, "alice", "other-synthetic-password")
        self.denied(401, lambda: A.authenticate(self.reg, "default", second["token"]))
        third = self.mint()
        self.assertTrue(T.local_del_user(self.data, "alice"))
        self.denied(401, lambda: A.authenticate(self.reg, "default", third["token"]))

    def test_account_disable_enable_does_not_revive_and_other_users_keep_access(self):
        alice = self.mint()
        bob = self.mint(user="bob")
        self.change("account_disable", user="alice")
        self.denied(401, lambda: A.authenticate(self.reg, "default", alice["token"]))
        self.assertTrue(A.authenticate(self.reg, "default", bob["token"])["active"])
        self.change("account_enable", user="alice")
        self.denied(401, lambda: A.authenticate(self.reg, "default", alice["token"]))

    def test_authentication_and_worker_validation_recheck_current_permissions(self):
        first = self.mint()
        # Simulate a permission edit outside dispatch. Both request boundaries
        # must inspect current grants, not trust only issued authority or flags.
        with self.reg.authorization_guard(), self.reg.transaction() as db:
            db.execute("UPDATE project_grants SET role='viewer' WHERE tenant_id='default' AND user='alice' AND project_id='1'")
        self.assertEqual(self.reg.one("SELECT revoked_at FROM tool_connections")["revoked_at"], "")
        self.denied(401, lambda: A.authenticate(self.reg, "default", first["token"]))
        self.denied(401, lambda: A.validate_connection(self.reg, "default", first["connection"]["id"], "alice"))

    def test_audit_failure_rolls_back_connection_and_receipt(self):
        self.reg.db.execute("CREATE TRIGGER tool_audit_fail BEFORE INSERT ON access_audit WHEN NEW.action='tool_connection_create' BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END")
        self.reg.db.commit()
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            self.mint()
        self.assertEqual(before, self.snapshot())

    def test_scopes_do_not_inherit_later_role_escalation(self):
        read = self.mint(scope="read")
        self.change("member_set", user="alice", role="admin")
        self.denied(401, lambda: A.authenticate(self.reg, "default", read["token"]))
        scoped = self.mint(scope="read")
        self.assertEqual(A.authenticate(self.reg, "default", scoped["token"])["scope"], "read")
        self.assertEqual(A.authenticate(self.reg, "default", scoped["token"])["project_ids"], [1])

    def test_viewer_can_issue_read_but_not_content(self):
        self.change("member_set", user="alice", role="viewer")
        self.denied(403, lambda: self.mint())
        item = self.mint(scope="read")
        self.assertEqual(A.authenticate(self.reg, "default", item["token"])["scope"], "read")

    def test_cross_tenant_same_project_id_and_request_id_stay_separate(self):
        tenant = self.change("tenant_create", name="Second", admin="bob")["tenant_id"]
        self.change("member_set", tenant=tenant, user="alice", role="member")
        self.change("project_grant", tenant=tenant, user="alice", project_id=1, role="contributor")
        body = self.body()
        first = A.create(self.reg, "alice", "default", body)
        second = A.create(self.reg, "alice", tenant, body)
        self.assertNotEqual(first["connection"]["id"], second["connection"]["id"])
        self.denied(401, lambda: A.authenticate(self.reg, tenant, first["token"]))
        self.denied(401, lambda: A.authenticate(self.reg, "default", second["token"]))
        self.change("project_revoke", tenant=tenant, user="alice", project_id=1)
        self.assertTrue(A.authenticate(self.reg, "default", first["token"])["active"])
        self.denied(401, lambda: A.authenticate(self.reg, tenant, second["token"]))

    def test_tenant_disable_then_enable_does_not_revive_credentials(self):
        tenant = self.change("tenant_create", name="Second", admin="bob")["tenant_id"]
        token = self.mint(user="bob", tenant=tenant)["token"]
        self.change("tenant_disable", tenant=tenant)
        self.denied(401, lambda: A.authenticate(self.reg, tenant, token))
        self.change("tenant_enable", tenant=tenant)
        self.denied(401, lambda: A.authenticate(self.reg, tenant, token))

    def test_expiry_and_malformed_secrets_fail_closed(self):
        with patch.object(A.time, "time", return_value=2000000000):
            out = self.mint(expires_days=1)
            self.assertTrue(A.authenticate(self.reg, "default", out["token"])["active"])
        with patch.object(A.time, "time", return_value=2000086400):
            self.denied(401, lambda: A.authenticate(self.reg, "default", out["token"]))
            self.assertEqual(A.listing(self.reg, "alice", "default")["connections"][0]["status"], "expired")
        for token in (None, "", "wbt_invalid", out["token"] + "x", out["token"].replace("wbt_", "Bearer wbt_"), "wbt_" + "0" * 32 + "." + "x" * 43):
            self.denied(401, lambda token=token: A.authenticate(self.reg, "default", token))

    def test_revoke_is_owner_only_and_idempotent_and_never_discloses_another_record(self):
        first = self.mint()
        body = {"connection_id": first["connection"]["id"], "request_id": "revoke-1", "action": "revoke"}
        self.denied(404, lambda: A.revoke(self.reg, "bob", "default", body))
        self.denied(404, lambda: A.revoke(self.reg, "owner", "default", body))
        out = A.revoke(self.reg, "alice", "default", body)
        self.assertFalse(out["connection"]["active"])
        self.assertEqual(out["connection"]["status"], "revoked")
        before = self.snapshot()
        self.assertTrue(A.revoke(self.reg, "alice", "default", body)["replayed"])
        self.assertEqual(before, self.snapshot())
        self.denied(401, lambda: A.authenticate(self.reg, "default", first["token"]))
        self.denied(409, lambda: A.revoke(self.reg, "alice", "default", dict(body, connection_id="0" * 32)))

    def test_revoke_remains_available_after_project_scope_loss(self):
        first = self.mint()
        self.change("project_revoke", user="alice", project_id=1)
        out = A.revoke(self.reg, "alice", "default", {"connection_id": first["connection"]["id"], "request_id": "revoke-after-loss"})
        self.assertFalse(out["connection"]["active"])
        self.assertEqual(len(A.listing(self.reg, "alice", "default")["connections"]), 1)

    def test_receipt_failure_rolls_back_creation_revocation_and_audit(self):
        first = self.mint()
        self.reg.db.execute("CREATE TRIGGER tool_fail BEFORE INSERT ON tool_access_requests BEGIN SELECT RAISE(ABORT,'synthetic receipt failure'); END")
        self.reg.db.commit()
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            self.mint()
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(sqlite3.IntegrityError):
            A.revoke(self.reg, "alice", "default", {"connection_id": first["connection"]["id"], "request_id": "revoke-fail"})
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(A.authenticate(self.reg, "default", first["token"])["active"])

    def test_authority_failure_rolls_back_revocation_with_role_change(self):
        first = self.mint()
        self.reg.db.execute("CREATE TRIGGER access_fail BEFORE INSERT ON access_requests BEGIN SELECT RAISE(ABORT,'synthetic receipt failure'); END")
        self.reg.db.commit()
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            self.change("project_revoke", user="alice", project_id=1)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(A.authenticate(self.reg, "default", first["token"])["active"])

    def test_duplicate_concurrent_create_has_one_secret_one_effect(self):
        other = self.second()
        barrier = threading.Barrier(2)
        body = self.body()
        def run(reg):
            barrier.wait()
            return A.create(reg, "alice", "default", body)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [pool.submit(run, reg) for reg in (self.reg, other)]
            results = [future.result(timeout=10) for future in tasks]
        self.assertEqual(sum("token" in result for result in results), 1)
        self.assertEqual(sum(result["replayed"] for result in results), 1)
        self.assertEqual(len({result["connection"]["id"] for result in results}), 1)
        self.assertEqual(len(self.reg.q("SELECT * FROM tool_connections")), 1)
        self.assertEqual(len(self.reg.q("SELECT * FROM tool_access_requests")), 1)

    def test_authorization_guard_serializes_worker_validation_with_revocation(self):
        first = self.mint()
        other = self.second()
        started, finished = threading.Event(), threading.Event()
        def revoke():
            started.set()
            try:
                return A.revoke(other, "alice", "default", {"connection_id": first["connection"]["id"], "request_id": "thread-revoke"})
            finally:
                finished.set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with self.reg.authorization_guard():
                self.assertTrue(A.validate_connection(self.reg, "default", first["connection"]["id"], "alice")["active"])
                future = pool.submit(revoke)
                self.assertTrue(started.wait(2))
                self.assertFalse(finished.wait(.05))
            future.result(timeout=10)
        self.denied(401, lambda: A.validate_connection(self.reg, "default", first["connection"]["id"], "alice"))

    def test_schema_migration_preserves_existing_rows_and_atomic_failure(self):
        original = (self.data / "users.json").read_bytes()
        accounts = self.reg.q("SELECT * FROM accounts ORDER BY name")
        self.reg.db.execute("DROP TABLE tool_connections")
        self.reg.db.execute("DROP TABLE tool_access_requests")
        self.reg.db.commit()
        before = self.snapshot()
        with patch.object(A, "DDL", A.DDL + ("INVALID SQL",)):
            with self.assertRaises(sqlite3.OperationalError):
                T.Registry(self.data)
        self.assertEqual(before, self.snapshot())
        other = self.second()
        self.assertEqual(accounts, other.q("SELECT * FROM accounts ORDER BY name"))
        self.assertEqual(original, (self.data / "users.json").read_bytes())
        after = self.snapshot()
        self.second()
        self.assertEqual(after, self.snapshot())


if __name__ == "__main__":
    unittest.main()
