"""Synthetic people and temporary repositories exercise collaboration, not signoff."""
import concurrent.futures
from contextlib import nullcontext
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import agent_api, candidates, handoffs as H, login, team
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tests.sqlite_snapshot import dump_store


class HandoffsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-handoffs-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.repo = self.folder / "repo"
        self.repo.mkdir()
        self.data = self.folder / "data"
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        login._save_users(self.data, {name: {"pw": "synthetic-credentials-not-for-login"} for name in ("alice", "bob", "charlie", "agent", "system")})
        self.project = self.store.add_project("ORG", "Synthetic project", str(self.repo))
        self.ticket = self.store.create_ticket(self.project["id"], "完整需求", "alice", body="保存后必须可恢复\n" * 300, assignee="alice")
        self.count = 0

    def read(self, user="alice"):
        return H.read(self.P, self.ticket["key"], user)

    def body(self, action, user="alice", **kw):
        view = self.read(user)
        self.count += 1
        body = {"ticket": self.ticket["key"], "action": action, "revision": view["revision"], "request_id": "r-%s" % self.count, "note": "合成协作说明"}
        if action == "send":
            body.update(receiver="bob", stage="testing", materials="全部材料\n" * 500, source_token=view["source_token"])
        else:
            body["handoff_id"] = view["current"]["id"]
        body.update(kw)
        return body

    def action(self, action, user="alice", **kw):
        return H.dispatch_action(self.P, self.body(action, user, **kw), user)

    def assert_api(self, code, fn):
        with self.assertRaises(ApiError) as err:
            fn()
        self.assertEqual(err.exception.code, code)

    def second_store(self):
        other = Store(self.store.path)
        self.addCleanup(other.db.close)
        return SimpleNamespace(store=other, data_dir=self.data)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True, check=True).stdout.strip()

    def candidate(self):
        if not (self.repo / ".git").exists():
            self.git("init", "-b", "main")
            self.git("config", "user.name", "Synthetic")
            self.git("config", "user.email", "fixture@localhost")
            (self.repo / "app.txt").write_text("base")
            self.git("add", ".")
            self.git("commit", "-m", "base")
        base = self.git("rev-parse", "HEAD")
        (self.repo / "app.txt").write_text(base)
        self.git("commit", "-am", "candidate")
        commit = self.git("rev-parse", "HEAD")
        candidates.schema(self.store)
        rid = self.store.create_run(self.project["id"], self.ticket["id"], "external:fixture", "fix", "fixture", "synthetic")['id']
        requirement = agent_api._requirement(self.store.ticket(self.ticket["id"]), self.store)
        ref = "refs/webuddy/candidates/synthetic-%s" % rid
        self.git("update-ref", ref, commit)
        cid = self.store.x("INSERT INTO code_candidates(ticket_id,run_id,agent,base_commit,commit_sha,requirement_hash,configuration_hash,criteria,summary,fingerprint,ref,artifact_dir,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (self.ticket["id"], rid, "external:fixture", base, commit, requirement, candidates.configuration(self.P, self.project), "[]", "Synthetic unverified candidate", "fixture-%s" % rid, ref, str(self.folder / "artifacts"), "2026-10-23"))
        return cid, commit

    def test_unrecorded_wait_is_unknown_and_directory_has_only_people(self):
        r = self.read()
        self.assertIsNone(r["current"])
        self.assertEqual(r["revision"], 0)
        self.assertIsNone(r["waiting_since"])
        self.assertIsNone(r["waiting_seconds"])
        self.assertEqual(r["members"], [{"id": n, "name": n} for n in ("alice", "bob", "charlie")])
        self.assertNotIn("synthetic-credentials", json.dumps(r))
        self.assertEqual(H.summary_rows(self.store, [self.ticket["id"]]), {})

    def test_real_identities_and_server_authorship_only(self):
        b = self.body("send")
        for user in ("", "agent", "system", "agent:alice", "external:alice", "missing", None):
            self.assert_api(403, lambda u=user: H.dispatch_action(self.P, b, u))
        self.assert_api(403, lambda: H.dispatch_action(self.P, b, "charlie"))
        self.assert_api(400, lambda: H.dispatch_action(self.P, dict(b, actor="bob"), "alice"))
        for receiver in ("agent", "missing", "alice"):
            self.assert_api(400, lambda name=receiver: H.dispatch_action(self.P, dict(b, receiver=name), "alice"))
        self.assertEqual(self.store.q("SELECT * FROM ticket_handoffs"), [])

    def test_two_handoffs_receive_return_and_full_material_history(self):
        original = self.store.ticket(self.ticket["id"])
        req = agent_api._requirement(original, self.store)
        first = self.action("send")["current"]
        self.assertEqual(first["next_actor"], "bob")
        self.assertEqual(first["materials"], "全部材料\n" * 500)
        self.assertEqual(first["source"]["ticket"]["body"], original["body"])
        self.assert_api(409, lambda: self.action("send"))
        self.assert_api(403, lambda: self.action("receive", "charlie"))
        received = self.action("receive", "bob")
        self.assertEqual(received["current"]["status"], "received")
        self.assertIsNone(received["waiting_seconds"])
        second = self.action("send", "bob", receiver="charlie", stage="delivery")
        self.assertEqual(second["current"]["sender"], "bob")
        self.assertEqual(second["revision"], 3)
        returned = self.action("return", "charlie", note="缺少部署回滚步骤")
        self.assertEqual(returned["current"]["status"], "returned")
        self.assertEqual(returned["next_actor"], "bob")
        self.assertEqual(len(returned["history"]), 2)
        self.assertEqual([e["action"] for e in returned["history"][0]["events"]], ["send", "receive"])
        self.assertEqual([e["action"] for e in returned["history"][1]["events"]], ["send", "return"])
        self.assertFalse(any(returned["history"][0]["actions"].values()))
        self.assertEqual(self.store.ticket(self.ticket["id"]), original)
        self.assertEqual(agent_api._requirement(original, self.store), req)
        self.assertEqual(self.store.q("SELECT * FROM events WHERE kind IN ('accept','close','reject','candidate_decision')"), [])
        self.assertEqual(H.summary_rows(self.store, [self.ticket["id"]])[self.ticket["id"]]["revision"], 4)

    def test_block_resume_preserves_original_wait_and_notes(self):
        sent = self.action("send")
        waiting = sent["waiting_since"]
        self.assert_api(403, lambda: self.action("block", "charlie"))
        blocked = self.action("block", "bob", note="缺少测试环境")
        self.assertEqual(blocked["current"]["status"], "blocked")
        self.assertEqual(blocked["current"]["block_reason"], "缺少测试环境")
        self.assertNotEqual(blocked["waiting_since"], waiting)
        resumed = self.action("resume", "bob")
        self.assertEqual(resumed["current"]["status"], "waiting")
        self.assertEqual(resumed["waiting_since"], waiting)
        self.action("receive", "bob")
        self.action("block", "bob")
        resumed = self.action("resume", "bob")
        self.assertEqual(resumed["current"]["status"], "received")
        self.assertIsNone(resumed["waiting_seconds"])

    def test_stale_source_rejects_receive_but_allows_reasoned_return(self):
        self.action("send")
        self.store.update_ticket(self.ticket["id"], "alice", body="新需求")
        view = self.read("bob")
        self.assertTrue(view["current"]["stale"])
        self.assertFalse(view["actions"]["receive"])
        self.assertTrue(view["actions"]["return"])
        self.assert_api(409, lambda: self.action("receive", "bob"))
        self.assertEqual(self.action("return", "bob")["current"]["status"], "returned")
        self.action("send", "alice")
        self.assertFalse(self.read("bob")["current"]["stale"])

    def test_legacy_owner_and_project_root_changes_invalidate_source(self):
        old = self.body("send")
        self.store.update_ticket(self.ticket["id"], "alice", assignee="charlie")
        self.assert_api(409, lambda: H.dispatch_action(self.P, old, "charlie"))
        self.action("send", "charlie")
        replacement = self.folder / "replacement"
        replacement.mkdir()
        self.store.x("UPDATE projects SET root=? WHERE id=?", (str(replacement), self.project["id"]))
        self.assertTrue(self.read("bob")["current"]["stale"])
        self.assert_api(409, lambda: self.action("receive", "bob"))

    def test_reviewer_and_reference_grant_changes_invalidate_source(self):
        team.schema(self.P)
        self.action("send")
        self.store.x("INSERT INTO ticket_team VALUES(?,?,?,?,?)", (self.ticket["id"], "charlie", 1, "2026-10-23", "alice"))
        self.assertTrue(self.read("bob")["current"]["stale"])
        self.action("return", "bob")
        self.action("send")
        with patch("tmh.platform.project_library.bindings", return_value=[{"revision_id": 1, "digest": "f" * 64, "scopes": ["architecture"], "purpose": "reference", "available": False}]):
            self.assertTrue(self.read("bob")["current"]["stale"])
            self.assert_api(409, lambda: self.action("receive", "bob"))
            self.assertEqual(self.action("withdraw")["current"]["status"], "withdrawn")

    def test_real_reference_grant_revocation_prevents_receive(self):
        source = self.store.add_project("LIB", "Shared library", str(self.repo))
        self.store.x("INSERT INTO knowledge_revisions(id,project_id,source_id,commit_sha,root,analyzer,status,stage,created,author,digest) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     ("fixed-knowledge", source["id"], 1, "a" * 40, str(self.repo), "synthetic", "ready", "complete", "2026-10-23", "alice", "b" * 64))
        scopes = '["architecture"]'
        self.store.x("INSERT INTO knowledge_grants VALUES(?,?,?,?,?)", (source["id"], self.project["id"], scopes, "alice", "2026-10-23"))
        self.store.x("INSERT INTO knowledge_references(project_id,revision_id,scopes,purpose,created,author) VALUES(?,?,?,?,?,?)",
                     (self.project["id"], "fixed-knowledge", scopes, "reference", "2026-10-23", "alice"))
        self.action("send")
        self.store.x("DELETE FROM knowledge_grants WHERE source_project=? AND target_project=?", (source["id"], self.project["id"]))
        view = self.read("bob")
        self.assertTrue(view["current"]["stale"])
        self.assertFalse(view["source"]["bindings"][0]["available"])
        self.assert_api(409, lambda: self.action("receive", "bob"))
        self.action("return", "bob")

    def test_reference_mode_refuses_new_handoff_and_preserves_safe_return(self):
        self.action("send")
        self.store.x("UPDATE project_profiles SET workflow='reference' WHERE project_id=?", (self.project["id"],))
        self.assert_api(409, lambda: self.action("receive", "bob"))
        self.action("return", "bob")
        self.assertFalse(self.read()["can_send"])
        self.assert_api(409, lambda: self.action("send"))

    def test_legacy_event_timestamp_remains_compatible_with_response_metrics(self):
        from tmh.platform.metrics import _hours, _t
        self.action("send")
        self.action("receive", "bob")
        event = self.store.one("SELECT * FROM events WHERE kind='handoff_receive'")
        self.assertIsNotNone(_t(event["ts"]))
        self.assertIsNotNone(_hours(self.ticket["created"], event["ts"]))
        self.assertNotIn("T", event["ts"])
        self.assertIn("+00:00", self.read()["current"]["sent_at"])

    def test_candidate_snapshot_has_full_verified_identity_and_latest_change_stales(self):
        cid, commit = self.candidate()
        observed = self.read()["source"]["candidate"]
        self.assertEqual((observed["id"], observed["commit"]), (cid, commit))
        self.assertEqual(len(observed["evidence_hash"]), 64)
        self.action("send")
        self.candidate()
        self.assertTrue(self.read("bob")["current"]["stale"])
        self.assert_api(409, lambda: self.action("receive", "bob"))
        self.assertEqual(self.action("return", "bob")["current"]["source"]["candidate"]["commit"], commit)

    def test_candidate_tamper_is_stale_and_client_cannot_forge_sha(self):
        cid, commit = self.candidate()
        self.action("send")
        row = candidates._row(self.P, cid)
        self.git("update-ref", row["ref"], row["base_commit"])
        self.assertTrue(self.read("bob")["current"]["stale"])
        self.assert_api(409, lambda: self.action("receive", "bob"))
        self.action("withdraw")
        forged = self.body("send", commit="0" * 40)
        self.assert_api(400, lambda: H.dispatch_action(self.P, forged, "alice"))

    def test_deleted_receiver_can_be_withdrawn_without_impersonation(self):
        self.action("send")
        login.del_user(self.data, "bob")
        self.assertFalse(self.read()["current"]["receiver_active"])
        self.assertFalse(self.read()["current"]["next_actor_active"])
        self.assert_api(403, lambda: self.read("bob"))
        out = self.action("withdraw", note="接收人已离开团队，重新指定")
        self.assertEqual(out["current"]["status"], "withdrawn")
        self.assertEqual(out["next_actor"], "alice")
        self.action("send", receiver="charlie")
        self.assertEqual(self.read()["current"]["receiver"], "charlie")
        self.assertNotIn("return", [e["action"] for e in out["history"][0]["events"]])

    def test_close_is_readonly_but_exact_successful_receipt_still_replays(self):
        b = self.body("send")
        result = H.dispatch_action(self.P, b, "alice")
        # Synthetic fixture directly sets a closed row, never invoking signoff.
        self.store.x("UPDATE tickets SET status='closed' WHERE id=?", (self.ticket["id"],))
        self.assertFalse(any(self.read("bob")["actions"].values()))
        self.assert_api(409, lambda: self.action("receive", "bob"))
        replay = H.dispatch_action(self.P, b, "alice")
        self.assertTrue(replay["receipt"]["replayed"])
        self.assertEqual(replay["revision"], result["revision"])

    def test_payload_idempotency_is_exact_and_different_request_cas_conflicts(self):
        b = self.body("send")
        first = H.dispatch_action(self.P, b, "alice")
        second = H.dispatch_action(self.P, b, "alice")
        self.assertEqual(first["current"], second["current"])
        self.assertTrue(second["receipt"]["replayed"])
        self.assert_api(409, lambda: H.dispatch_action(self.P, dict(b, note="changed"), "alice"))
        self.assert_api(409, lambda: H.dispatch_action(self.P, dict(b, request_id="another"), "alice"))
        self.assertEqual(len(self.store.q("SELECT * FROM ticket_handoff_events")), 1)

    def test_fault_at_receipt_insertion_rolls_back_every_row(self):
        b = self.body("send")
        self.store.x("CREATE TRIGGER fail_receipt BEFORE INSERT ON ticket_handoff_requests BEGIN SELECT RAISE(ABORT,'synthetic receipt failure'); END")
        before = dump_store(self.store)
        with self.assertRaises(sqlite3.IntegrityError):
            H.dispatch_action(self.P, b, "alice")
        self.assertEqual(dump_store(self.store), before)
        self.store.x("DROP TRIGGER fail_receipt")
        self.assertEqual(H.dispatch_action(self.P, b, "alice")["revision"], 1)

    def test_fault_at_audit_event_rolls_back_update(self):
        self.action("send")
        b = self.body("receive", "bob")
        self.store.x("CREATE TRIGGER fail_audit BEFORE INSERT ON events WHEN NEW.kind='handoff_receive' BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END")
        before = dump_store(self.store)
        with self.assertRaises(sqlite3.IntegrityError):
            H.dispatch_action(self.P, b, "bob")
        self.assertEqual(dump_store(self.store), before)
        self.assertEqual(self.read()["current"]["status"], "waiting")

    def test_conflicting_actions_across_connections_have_one_winner(self):
        self.action("send")
        other = self.second_store()
        bodies = [self.body("receive", "bob"), self.body("return", "bob")]
        barrier = threading.Barrier(2)
        def run(P, b):
            barrier.wait()
            try:
                return H.dispatch_action(P, b, "bob")["current"]["status"]
            except ApiError as exc:
                return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, P, b) for P, b in zip((self.P, other), bodies)]
            outcomes = [f.result(timeout=10) for f in futures]
        self.assertEqual(outcomes.count(409), 1)
        self.assertEqual(len(self.store.q("SELECT * FROM ticket_handoff_events")), 2)
        self.assertEqual(self.read()["revision"], 2)

    def test_competing_sends_across_connections_preserve_one_pending(self):
        other = self.second_store()
        body = self.body("send")
        barrier = threading.Barrier(2)
        def run(P, request_id):
            barrier.wait()
            try:
                return H.dispatch_action(P, dict(body, request_id=request_id), "alice")["revision"]
            except ApiError as exc:
                return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda pair: run(*pair), ((self.P, "send-1"), (other, "send-2"))))
        self.assertEqual(sorted(outcomes), [1, 409])
        self.assertEqual(len(self.store.q("SELECT * FROM ticket_handoffs WHERE status IN ('waiting','blocked')")), 1)

    def test_concurrent_same_request_retries_one_durable_receipt(self):
        other = self.second_store()
        body = self.body("send")
        barrier = threading.Barrier(2)
        def run(P):
            barrier.wait()
            try:
                return H.dispatch_action(P, body, "alice")
            except ApiError as exc:
                self.assertEqual(exc.code, 409)
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(run, (self.P, other)))
        self.assertTrue(any(outcomes))
        replay = H.dispatch_action(other, body, "alice")
        self.assertTrue(replay["receipt"]["replayed"])
        self.assertEqual(replay["revision"], 1)
        self.assertEqual(len(self.store.q("SELECT * FROM ticket_handoff_requests")), 1)
        self.assertEqual(len(self.store.q("SELECT * FROM ticket_handoff_events")), 1)

    def test_database_cas_alone_rejects_racing_actions_after_same_source_read(self):
        self.action("send")
        other = self.second_store()
        bodies = [self.body("receive", "bob"), self.body("return", "bob")]
        barrier = threading.Barrier(2)
        source = H._source
        def simultaneous(P, key):
            result = source(P, key)
            barrier.wait(timeout=5)
            return result
        def run(P, b):
            try:
                return H.dispatch_action(P, b, "bob")["revision"]
            except ApiError as exc:
                return exc.code
        # File locks are an early refusal optimization; DB CAS remains the
        # integrity boundary even if both requests reach BEGIN IMMEDIATE.
        with patch.object(H, "_source_lock", side_effect=lambda *args: nullcontext()), patch.object(H, "_source", side_effect=simultaneous):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(run, P, b) for P, b in zip((self.P, other), bodies)]
                results = [f.result(timeout=10) for f in futures]
        self.assertEqual(sorted(results), [2, 409])
        self.assertEqual(len(self.store.q("SELECT * FROM ticket_handoff_events")), 2)

    def test_source_changes_during_capture_refuse_without_partial_write(self):
        body = self.body("send")
        original = H._source
        def changed(P, key):
            result = original(P, key)
            P.store.update_ticket(self.ticket["id"], "alice", body="changed during preparation")
            return result
        with patch.object(H, "_source", side_effect=changed):
            self.assert_api(409, lambda: H.dispatch_action(self.P, body, "alice"))
        self.assertEqual(self.store.q("SELECT * FROM ticket_handoffs"), [])
        self.assertEqual(self.store.q("SELECT * FROM ticket_handoff_requests"), [])

    def test_candidate_inspection_never_holds_sqlite_write_transaction(self):
        self.candidate()
        original = candidates.view
        def view(P, cid, **kwargs):
            self.assertFalse(P.store.db.in_transaction)
            return original(P, cid, **kwargs)
        with patch.object(candidates, "view", side_effect=view):
            self.action("send")
            self.action("receive", "bob")

    def test_removed_actor_during_preparation_cannot_write(self):
        body = self.body("send")
        original = H._source
        def removed(P, key):
            result = original(P, key)
            login.del_user(P.data_dir, "alice")
            return result
        with patch.object(H, "_source", side_effect=removed):
            self.assert_api(403, lambda: H.dispatch_action(self.P, body, "alice"))
        self.assertEqual(self.store.q("SELECT * FROM ticket_handoffs"), [])

    def test_legacy_migration_is_idempotent_and_ddl_failure_rolls_back(self):
        db = sqlite3.connect(self.folder / "migration.db")
        self.addCleanup(db.close)
        db.execute("CREATE TABLE legacy(v TEXT)")
        db.execute("INSERT INTO legacy VALUES('preserve all data')")
        db.commit()
        st = SimpleNamespace(db=db, lock=threading.RLock())
        before = tuple(db.iterdump())
        with patch.object(H, "DDL", H.DDL + ("INVALID SYNTHETIC SQL",)):
            with self.assertRaises(sqlite3.OperationalError):
                H.schema(st)
        self.assertEqual(tuple(db.iterdump()), before)
        H.schema(st)
        once = tuple(db.iterdump())
        H.schema(st)
        self.assertEqual(tuple(db.iterdump()), once)
        self.assertEqual(db.execute("SELECT * FROM legacy").fetchall(), [("preserve all data",)])

    def test_nested_schema_refuses_without_committing_outer_transaction(self):
        self.store.db.execute("BEGIN IMMEDIATE")
        self.store.db.execute("UPDATE tickets SET title='not committed' WHERE id=?", (self.ticket["id"],))
        with self.assertRaises(RuntimeError):
            H.schema(self.store)
        self.assertTrue(self.store.db.in_transaction)
        self.store.db.rollback()
        self.assertEqual(self.store.ticket(self.ticket["id"])["title"], "完整需求")


if __name__ == "__main__":
    unittest.main()
