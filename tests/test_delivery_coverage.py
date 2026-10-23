"""Coverage uses synthetic materials/people, never an execution or acceptance."""
import concurrent.futures
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import delivery, delivery_coverage as C, login
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tests.sqlite_snapshot import dump_store


class Context:
    tenant_id = "coverage-fixture"

    def __init__(self):
        self.people = {
            "alice": {"role": "member", "project_grants": {"APP": "contributor"}},
            "reader": {"role": "viewer", "project_grants": {"APP": "manager"}},
            "other": {"role": "member", "project_grants": {"OTHER": "manager"}},
            "admin": {"role": "admin", "project_grants": {}},
        }

    def current_actor(self, actor):
        person = self.people.get(actor)
        return dict(copy.deepcopy(person), authz_revision=1) if person else None

    def directory(self):
        return copy.deepcopy(self.people)


class DeliveryCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tmh-coverage-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.data = self.root / "data"
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("APP", "合成交付", str(self.root))
        self.other_project = self.store.add_project("OTHER", "其他合成项目", str(self.root))
        self.context = Context()
        self.P = SimpleNamespace(store=self.store, data_dir=self.data, tenant_context=self.context)
        delivery._db(self.P)
        C.schema(self.store)
        self.did = "0123456789ab"
        self.other_did = "abcdef012345"
        self.same_project_did = "111111111111"
        self.make_delivery(self.did, self.project)
        self.make_delivery(self.other_did, self.other_project)
        self.make_delivery(self.same_project_did, self.project)
        self.counter = 0

    def make_delivery(self, did, project, stages=None):
        ticket = self.store.create_ticket(project["id"], "合成任务", "alice", auto=False)
        self.store.x("INSERT INTO delivery_items VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (did, project["id"], "feature", "完整交付目标", "不改原交付状态", json.dumps(stages or ["requirements", "design", "develop", "quality", "release"]), ticket["id"], "created", "updated", "alice"))

    def artifact(self, did=None, stage="requirements", body="完整原文\n第二行", inputs=None, title="材料"):
        did = did or self.did
        n = self.store.one("SELECT MAX(version) AS n FROM delivery_artifacts WHERE delivery_id=? AND stage=?", (did, stage))["n"] or 0
        return self.store.x("INSERT INTO delivery_artifacts(delivery_id,stage,version,title,body,created,author,inputs) VALUES(?,?,?,?,?,?,?,?)",
                            (did, stage, n + 1, title, body, "created", "alice", json.dumps(inputs or {})))

    def read(self, actor="alice", did=None):
        return C.read(self.P, did or self.did, actor)

    def body(self, action, **kw):
        self.counter += 1
        b = dict(action=action, revision=self.read()["revision"], request_id="request-%d" % self.counter)
        if action in ("add", "update"):
            b.update(title="覆盖要求", requirement="逐条覆盖并保留完整原文", required=True, artifact_id=None, note="说明")
        b.update(kw)
        return b

    def act(self, action, **kw):
        return C.act(self.P, self.did, self.body(action, **kw), "alice")

    def add(self, aid=None, **kw):
        return self.act("add", artifact_id=aid, **kw)["items"][-1]

    def verify(self, row):
        return self.act("verify", item_id=row["id"], source_token=row["source_token"], note="本人逐行阅读材料并与该要求核对；不表示实际测试通过")

    def assert_api(self, code, fn):
        before = dump_store(self.store)
        with self.assertRaises(ApiError) as err:
            fn()
        self.assertEqual(err.exception.code, code)
        self.assertEqual(before, dump_store(self.store))

    def original_tables(self):
        return {r["name"]: self.store.q('SELECT * FROM "' + r["name"] + '"') for r in self.store.q("SELECT name FROM sqlite_master WHERE type='table'")
                if not r["name"].startswith("delivery_coverage_") and r["name"] != "sqlite_sequence"}

    def test_read_has_no_schema_write_or_external_effects(self):
        before = dump_store(self.store)
        with patch.object(delivery, "_db", side_effect=AssertionError("legacy migration")), patch("subprocess.Popen", side_effect=AssertionError("execution")), patch.object(self.store, "x", side_effect=AssertionError("write")):
            v = self.read()
        self.assertEqual(v["revision"], 0)
        self.assertEqual(v["items"], [])
        self.assertEqual(v["history"], [])
        self.assertFalse(v["counts"]["complete"])
        self.assertEqual(dump_store(self.store), before)

    def test_missing_pending_checked_are_material_states_only(self):
        old = self.original_tables()
        row = self.add()
        self.assertEqual(row["status"], "missing")
        self.assertFalse(row["can_verify"])
        self.assert_api(409, lambda: self.verify(row))
        aid = self.artifact()
        old = self.original_tables()
        v = self.act("update", item_id=row["id"], artifact_id=aid)
        row = v["items"][0]
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["binding"]["artifact"]["id"], aid)
        v = self.verify(row)
        self.assertEqual(v["items"][0]["status"], "checked")
        self.assertEqual(v["counts"]["required_checked"], 1)
        self.assertTrue(v["counts"]["complete"])
        self.assertEqual(v["items"][0]["verification"]["actor"], "alice")
        self.assertEqual(self.original_tables(), old)
        self.assertEqual(self.store.q("SELECT * FROM delivery_reviews"), [])
        self.assertEqual(self.store.q("SELECT * FROM runs"), [])
        self.assertIn("不代表测试通过", v["boundary"])

    def test_text_is_complete_in_rows_artifacts_history_and_receipts(self):
        text = "  完整中文要求，不能静默截断。\n" * 4000 + "尾部证明"
        aid = self.artifact(body=text)
        row = self.add(aid, title="  标题保留空格  ", requirement=text, note=text)
        self.assertEqual(row["requirement"], text)
        self.assertEqual(row["note"], text)
        self.assertEqual(row["title"], "  标题保留空格  ")
        v = self.act("verify", item_id=row["id"], source_token=row["source_token"], note=text)
        self.assertEqual(v["items"][0]["verification"]["note"], text)
        self.assertEqual(v["artifacts"][0]["body"], text)
        self.assertEqual(v["history"][0]["after"][0]["requirement"], text)
        self.assertEqual(v["history"][1]["note"], text)

    def test_edit_even_note_invalidates_previous_check_and_keeps_history(self):
        aid = self.artifact()
        row = self.add(aid)
        self.verify(row)
        v = self.act("update", item_id=row["id"], artifact_id=aid, note="修改说明")
        self.assertEqual(v["items"][0]["status"], "pending")
        self.assertIsNone(v["items"][0]["verification"])
        self.assertEqual(v["history"][-1]["before"][0]["verification"]["actor"], "alice")
        self.assert_api(409, lambda: self.act("verify", item_id=row["id"], source_token=row["source_token"], note="旧行"))
        self.assertEqual(self.verify(v["items"][0])["items"][0]["status"], "checked")

    def test_new_artifact_version_stales_exact_binding_and_requires_rebind(self):
        aid = self.artifact()
        row = self.add(aid)
        self.verify(row)
        new_aid = self.artifact(body="新版材料")
        v = self.read()
        self.assertEqual(v["items"][0]["artifact_id"], aid)
        self.assertEqual(v["items"][0]["status"], "stale")
        self.assertEqual(v["counts"]["required_checked"], 0)
        self.assertFalse(v["items"][0]["can_verify"])
        self.assertFalse(v["counts"]["complete"])
        self.assert_api(409, lambda: self.verify(v["items"][0]))
        self.assert_api(409, lambda: self.act("update", item_id=row["id"], artifact_id=aid))
        fresh = self.act("update", item_id=row["id"], artifact_id=new_aid)["items"][0]
        self.assertEqual(self.verify(fresh)["items"][0]["status"], "checked")
        self.assertEqual(self.read()["history"][1]["after"][0]["binding"]["artifact"]["id"], aid)

    def test_changed_artifact_body_or_inputs_stales_saved_hash(self):
        for column, changed in (("body", "变更正文"), ("inputs", '{"requirements":{"artifact":99}}')):
            with self.subTest(column=column):
                aid = self.artifact(stage="design")
                row = self.add(aid)
                self.verify(row)
                self.store.x('UPDATE delivery_artifacts SET '+column+'=? WHERE id=?', (changed, aid))
                current = next(x for x in self.read()["items"] if x["id"] == row["id"])
                self.assertEqual(current["status"], "stale")
                self.assertFalse(current["can_verify"])

    def test_upstream_new_version_and_review_change_stale_downstream(self):
        upstream = self.artifact()
        aid = self.artifact(stage="design", inputs={"requirements": {"artifact": upstream, "review": None, "inputs": {}}})
        row = self.add(aid)
        self.verify(row)
        self.store.x("INSERT INTO delivery_reviews(artifact_id,evidence,author,created,inputs) VALUES(?,?,?,?,?)", (upstream, "旧阶段正式复核", "admin", "created", "{}"))
        self.assertEqual(self.read()["items"][0]["status"], "stale")
        row = self.act("update", item_id=row["id"], artifact_id=aid)["items"][0]
        self.verify(row)
        self.artifact(body="前置新版")
        self.assertEqual(self.read()["items"][0]["status"], "stale")

    def test_unrelated_later_stage_does_not_invalidate_requirement_material(self):
        row = self.add(self.artifact())
        self.verify(row)
        self.artifact(stage="release", body="独立后续交付材料")
        self.assertEqual(self.read()["items"][0]["status"], "checked")

    def test_project_root_or_delivery_scope_changes_stale_material(self):
        row = self.add(self.artifact())
        self.verify(row)
        self.store.x("UPDATE projects SET root=? WHERE id=?", (str(self.root / "different"), self.project["id"]))
        self.assertEqual(self.read()["items"][0]["status"], "stale")
        row = self.act("update", item_id=row["id"], artifact_id=row["artifact_id"])["items"][0]
        self.verify(row)
        self.store.x("UPDATE delivery_items SET goal=? WHERE id=?", ("交付要求变化", self.did))
        self.assertEqual(self.read()["items"][0]["status"], "stale")

    def test_missing_deleted_artifact_is_stale_without_resurrection(self):
        row = self.add(self.artifact())
        self.verify(row)
        self.store.x("DELETE FROM delivery_artifacts WHERE id=?", (row["artifact_id"],))
        current = self.read()["items"][0]
        self.assertEqual(current["status"], "stale")
        self.assertFalse(current["can_verify"])

    def test_withdraw_is_reasoned_history_and_never_delete(self):
        row = self.add(self.artifact())
        self.verify(row)
        self.assert_api(400, lambda: self.act("withdraw", item_id=row["id"], note="   "))
        v = self.act("withdraw", item_id=row["id"], note="完整撤回原因\n保留原行")
        self.assertEqual(v["items"][0]["status"], "withdrawn")
        self.assertEqual(v["items"][0]["withdraw_reason"], "完整撤回原因\n保留原行")
        self.assertEqual(v["history"][-1]["before"][0]["verification"]["actor"], "alice")
        self.assertEqual(v["counts"]["total"], 0)
        self.assertFalse(v["counts"]["complete"])
        self.assert_api(409, lambda: self.verify(v["items"][0]))
        self.assert_api(409, lambda: self.act("update", item_id=row["id"]))

    def test_template_is_explicit_stage_specific_missing_and_nonduplicating(self):
        before = self.original_tables()
        self.assertEqual(len(self.read()["template"]["items"]), 4)
        payload = self.body("seed_template", template_id=C.TEMPLATE_ID)
        v = C.act(self.P, self.did, payload, "alice")
        self.assertEqual(len(v["items"]), 4)
        self.assertEqual(v["counts"]["missing"], 4)
        self.assertEqual(v["counts"]["checked"], 0)
        self.assertFalse(v["template"]["available"])
        self.assertEqual(len(v["history"]), 1)
        self.assertTrue(C.act(self.P, self.did, payload, "alice")["receipt"]["replayed"])
        self.assert_api(409, lambda: self.act("seed_template", template_id=C.TEMPLATE_ID))
        self.act("withdraw", item_id=v["items"][0]["id"], note="保留历史")
        self.assert_api(409, lambda: self.act("seed_template", template_id=C.TEMPLATE_ID))
        self.assertEqual(self.original_tables(), before)
        self.store.x("UPDATE delivery_items SET stages=? WHERE id=?", ('["research","release"]', self.same_project_did))
        other = C.act(self.P, self.same_project_did, dict(action="seed_template",revision=0,request_id="other-template",template_id=C.TEMPLATE_ID),"alice")
        self.assertEqual([r["template_key"] for r in other["items"]], [C.TEMPLATE_ID+":delivery"])

    def test_idempotency_is_actor_delivery_payload_bound_and_projects_rechecked(self):
        payload = self.body("add", artifact_id=self.artifact())
        first = C.act(self.P, self.did, payload, "alice")
        replay = C.act(self.P, self.did, payload, "alice")
        self.assertTrue(replay["receipt"]["replayed"])
        self.assertEqual(replay["receipt"]["item_ids"], first["receipt"]["item_ids"])
        self.assertEqual(len(replay["history"]), 1)
        self.assert_api(409, lambda: C.act(self.P, self.did, dict(payload,note="不同正文"), "alice"))
        self.assert_api(409, lambda: C.act(self.P, self.same_project_did, payload, "alice"))
        self.context.people["alice"]["project_grants"] = {}
        self.assert_api(403, lambda: C.act(self.P, self.did, payload, "alice"))
        self.assert_api(403, lambda: self.read())

    def test_replay_reports_current_staleness_not_historical_checked_state(self):
        row = self.add(self.artifact())
        payload = self.body("verify",item_id=row["id"],source_token=row["source_token"],note="本人核对")
        first = C.act(self.P,self.did,payload,"alice")
        self.artifact(body="新版本")
        replay = C.act(self.P,self.did,payload,"alice")
        self.assertTrue(replay["receipt"]["replayed"])
        self.assertEqual(replay["receipt"]["revision"],first["receipt"]["revision"])
        self.assertEqual(replay["items"][0]["status"],"stale")
        self.assertEqual(len(replay["history"]),2)

    def test_viewer_is_readonly_and_artifact_item_scopes_cannot_cross(self):
        self.assertFalse(self.read("reader")["can_edit"])
        self.assert_api(403,lambda: C.act(self.P,self.did,self.body("add"),"reader"))
        self.assert_api(403,lambda: self.read("other"))
        for did in (self.other_did,self.same_project_did):
            aid=self.artifact(did)
            self.assert_api(400,lambda: self.act("add",artifact_id=aid))
        other=C.act(self.P,self.same_project_did,dict(self.body("add"),revision=0),"alice")["items"][0]
        self.assert_api(404,lambda: self.act("update",item_id=other["id"]))

    def test_forged_identity_status_and_malformed_tokens_are_rejected(self):
        for field in ("actor","by","verified","status","project","delivery_id"):
            self.assert_api(400,lambda field=field: self.act("add",**{field:"forged"}))
        for kw in ({"required":1},{"artifact_id":True},{"title":""},{"requirement":" "},{"note":None}):
            self.assert_api(400,lambda kw=kw:self.act("add",**kw))
        row=self.add(self.artifact())
        self.assert_api(400,lambda:self.act("verify",item_id=row["id"],source_token=row["source_token"],note=" "))
        self.assert_api(400,lambda:self.act("verify",item_id=row["id"],source_token="invalid",note="核对"))
        self.assert_api(409,lambda:self.act("verify",item_id=row["id"],source_token="0"*64,note="核对"))
        self.assert_api(400,lambda:C.act(self.P,self.did,dict(self.body("add"),revision=True),"alice"))
        self.assert_api(404,lambda:C.read(self.P,"not-a-delivery","alice"))

    def test_same_revision_competition_has_one_atomic_winner(self):
        other=Store(self.store.path)
        self.addCleanup(other.db.close)
        P2=SimpleNamespace(store=other,data_dir=self.data,tenant_context=self.context)
        barrier=threading.Barrier(2)
        payload=self.body("add")
        def submit(P,request):
            barrier.wait(3)
            try:return C.act(P,self.did,dict(payload,request_id=request),"alice")["revision"]
            except ApiError as exc:return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(submit,self.P,"race-a");b=pool.submit(submit,P2,"race-b")
            self.assertEqual(sorted([a.result(5),b.result(5)]),[1,409])
        v=self.read()
        self.assertEqual(len(v["items"]),1)
        self.assertEqual(len(v["history"]),1)
        self.assertEqual(len(self.store.q("SELECT * FROM delivery_coverage_requests")),1)

    def test_same_request_concurrent_replay_has_one_event(self):
        other=Store(self.store.path);self.addCleanup(other.db.close)
        P2=SimpleNamespace(store=other,data_dir=self.data,tenant_context=self.context)
        barrier=threading.Barrier(2);payload=self.body("add")
        def submit(P):
            barrier.wait(3)
            return C.act(P,self.did,payload,"alice")["receipt"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(submit,self.P);b=pool.submit(submit,P2)
            results=[a.result(5),b.result(5)]
        self.assertEqual(sorted(x["replayed"] for x in results),[False,True])
        self.assertEqual(results[0]["item_ids"],results[1]["item_ids"])
        self.assertEqual(len(self.read()["history"]),1)

    def test_audit_or_receipt_failure_rolls_back_item_head_and_history(self):
        for table in ("delivery_coverage_events","delivery_coverage_requests"):
            with self.subTest(table=table):
                self.store.x("CREATE TRIGGER fail_coverage BEFORE INSERT ON "+table+" BEGIN SELECT RAISE(ABORT,'injected failure'); END")
                before=dump_store(self.store)
                payload=self.body("add")
                with self.assertRaisesRegex(sqlite3.IntegrityError,"injected failure"):
                    C.act(self.P,self.did,payload,"alice")
                self.assertEqual(dump_store(self.store),before)
                self.assertFalse(self.store.db.in_transaction)
                self.store.x("DROP TRIGGER fail_coverage")
        self.assertEqual(self.read()["revision"],0)

    def test_write_does_not_call_legacy_schema_store_x_or_runner(self):
        payload=self.body("add")
        with patch.object(delivery,"_db",side_effect=AssertionError("implicit commit")),patch.object(self.store,"x",side_effect=AssertionError("implicit commit")),patch("subprocess.Popen",side_effect=AssertionError("spawn")):
            v=C.act(self.P,self.did,payload,"alice")
        self.assertEqual(v["revision"],1)

    def test_legacy_mode_still_requires_real_account_not_display_name(self):
        del self.P.tenant_context
        self.assert_api(403,lambda:self.read())
        login._save_users(self.data,{"alice":{"pw":"synthetic-not-a-real-password"},"agent":{"pw":"synthetic"}})
        self.assertTrue(self.read()["can_edit"])
        self.assert_api(403,lambda:self.read("agent"))
        self.add()

    def test_read_uses_one_snapshot_while_another_connection_updates(self):
        row = self.add(self.artifact())
        facts_ready = threading.Event()
        writer_changed = threading.Event()
        original = C._facts
        def paused(P, d, project):
            facts = original(P, d, project)
            facts_ready.set()
            self.assertTrue(writer_changed.wait(3))
            return facts
        def writer():
            self.assertTrue(facts_ready.wait(3))
            with closing(sqlite3.connect(str(self.store.path), timeout=5)) as db, db:
                db.execute("UPDATE delivery_coverage_items SET title='concurrent title' WHERE id=?", (row["id"],))
                db.execute("UPDATE delivery_coverage_heads SET revision=2 WHERE delivery_id=?", (self.did,))
                writer_changed.set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(writer)
            with patch.object(C, "_facts", side_effect=paused):
                snapshot = self.read()
            future.result(5)
        self.assertEqual(snapshot["revision"], 1)
        self.assertEqual(snapshot["items"][0]["title"], "覆盖要求")
        self.assertEqual(self.read()["revision"], 2)
        self.assertEqual(self.read()["items"][0]["title"], "concurrent title")

    def test_linked_run_input_change_stales_coverage_without_running_anything(self):
        aid = self.artifact(stage="design")
        ticket = self.store.one("SELECT ticket_id FROM delivery_items WHERE id=?", (self.did,))["ticket_id"]
        run = self.store.create_run(self.project["id"], ticket, "synthetic", "ask", "alice", "完整合成输入")
        self.store.x("INSERT INTO delivery_runs(delivery_id,stage,run_id,base_version,inputs,created) VALUES(?,?,?,?,?,?)",
                     (self.did, "design", run["id"], 0, "{}", "created"))
        row = self.add(aid)
        self.verify(row)
        self.store.x("UPDATE delivery_runs SET inputs=? WHERE run_id=?", ('{"changed":true}', run["id"]))
        self.assertEqual(self.read()["items"][0]["status"], "stale")
        self.assertEqual(self.store.run(run["id"])["status"], "queued")

    def test_actual_source_run_remains_bound_after_a_newer_stage_attempt(self):
        ticket = self.store.one("SELECT ticket_id FROM delivery_items WHERE id=?", (self.did,))["ticket_id"]
        sources = []
        for text in ("actual material input", "newer attempt"):
            run = self.store.create_run(self.project["id"], ticket, "synthetic", "ask", "alice", text)
            self.store.x("INSERT INTO delivery_runs(delivery_id,stage,run_id,base_version,inputs,created) VALUES(?,?,?,?,?,?)",
                         (self.did, "requirements", run["id"], 0, "{}", "created"))
            sources.append(run)
        aid = self.artifact()
        self.store.x("UPDATE delivery_artifacts SET source_run=? WHERE id=?", (sources[0]["id"], aid))
        row = self.add(aid)
        self.verify(row)
        self.assertEqual(self.read()["items"][0]["status"], "checked")
        self.store.x("UPDATE runs SET prompt=? WHERE id=?", ("changed actual source", sources[0]["id"]))
        self.assertEqual(self.read()["items"][0]["status"], "stale")

    def test_source_run_must_match_delivery_project_ticket_and_stage(self):
        own_ticket = self.store.one("SELECT ticket_id FROM delivery_items WHERE id=?", (self.did,))["ticket_id"]
        same_project_ticket = self.store.one("SELECT ticket_id FROM delivery_items WHERE id=?", (self.same_project_did,))["ticket_id"]
        foreign_ticket = self.store.one("SELECT ticket_id FROM delivery_items WHERE id=?", (self.other_did,))["ticket_id"]
        cases = ((self.other_project["id"], foreign_ticket, "requirements"),
                 (self.project["id"], same_project_ticket, "requirements"),
                 (self.project["id"], own_ticket, "design"),
                 (self.project["id"], own_ticket, None))
        for project_id, ticket_id, stage in cases:
            with self.subTest(project=project_id, ticket=ticket_id, stage=stage):
                run = self.store.create_run(project_id, ticket_id, "synthetic", "ask", "alice", "synthetic input")
                if stage:
                    self.store.x("INSERT INTO delivery_runs(delivery_id,stage,run_id,base_version,inputs,created) VALUES(?,?,?,?,?,?)",
                                 (self.did, stage, run["id"], 0, "{}", "created"))
                aid = self.artifact()
                self.store.x("UPDATE delivery_artifacts SET source_run=? WHERE id=?", (run["id"], aid))
                self.assert_api(400, lambda: self.add(aid))
                self.store.x("DELETE FROM delivery_runs WHERE run_id=?", (run["id"],))

    def test_integer_overflow_ids_are_bad_requests_without_writes(self):
        for kw in ({"item_id": 2**63}, {"item_id": 1, "artifact_id": 2**63}):
            self.assert_api(400, lambda kw=kw: self.act("update", **kw))

    def test_schema_is_idempotent_and_rollback_has_no_implicit_commit(self):
        before=dump_store(self.store)
        C.schema(self.store)
        self.assertEqual(dump_store(self.store),before)
        db=sqlite3.connect(":memory:");self.addCleanup(db.close)
        store=SimpleNamespace(db=db,lock=threading.RLock())
        db.execute("CREATE TABLE existing(value TEXT)");db.commit()
        with patch.object(C,"DDL",C.DDL+("THIS IS NOT VALID SQL",)):
            with self.assertRaises(sqlite3.OperationalError):C.schema(store)
        self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),[("existing",)])
        db.execute("INSERT INTO existing VALUES('not committed')")
        with self.assertRaisesRegex(RuntimeError,"cannot nest"):C.schema(store)
        self.assertTrue(db.in_transaction)
        db.rollback()
        self.assertEqual(db.execute("SELECT * FROM existing").fetchall(),[])
