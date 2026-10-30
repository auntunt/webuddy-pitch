"""Manual delivery drafting stays independent from runtime and stage approval."""
import concurrent.futures
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import delivery, delivery_content as D
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tests.sqlite_snapshot import dump_store
from tests.test_delivery_coverage import Context


class DeliveryContentTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="tmh-delivery-content-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.data=self.root/"data"
        self.store=Store(self.data/"platform.db");self.addCleanup(self.store.db.close)
        self.project=self.store.add_project("APP","合成项目",str(self.root))
        self.other=self.store.add_project("OTHER","其他项目",str(self.root))
        self.context=Context()
        self.P=SimpleNamespace(store=self.store,data_dir=self.data,tenant_context=self.context)
        D.schema(self.store)
        self.counter=0

    def create_body(self,**kw):
        self.counter+=1
        return dict(action="create",request_id="create-%s"%self.counter,revision=0,project="APP",type="feature",title="完整交付",goal="目标与边界\n保留完整内容",**kw)

    def create(self,**kw):
        return D.create(self.P,self.create_body(**kw),"alice")

    def save_body(self,did,**kw):
        v=D.read(self.P,did,"alice");self.counter+=1
        b=dict(action="save_artifact",request_id="save-%s"%self.counter,revision=v["revision"],source_token=v["source_token"],stage="requirements",title="手工材料",body="完整原文\n不宣称测试通过")
        b.update(kw);return b

    def save(self,did,**kw):
        return D.act(self.P,did,self.save_body(did,**kw),"alice")

    def assert_api(self,code,fn):
        before=dump_store(self.store)
        with self.assertRaises(ApiError) as err:fn()
        self.assertEqual(err.exception.code,code)
        self.assertEqual(dump_store(self.store),before)

    def test_create_is_atomic_paused_unassigned_and_never_calls_legacy_effects(self):
        trap=lambda *a: (_ for _ in ()).throw(AssertionError("callback must not run"))
        self.store.on_create.append(trap);self.store.on_status.append(trap)
        payload=self.create_body()
        with patch.object(delivery,"_db",side_effect=trap),patch.object(delivery,"view",side_effect=trap),patch.object(delivery,"_rows",side_effect=trap),patch.object(self.store,"x",side_effect=trap),patch("subprocess.Popen",side_effect=trap):
            v=D.create(self.P,payload,"alice")
        t=self.store.ticket(v["delivery"]["ticket_id"])
        self.assertEqual(t["status"],"new");self.assertEqual(t["assignee"],"")
        self.assertEqual(t["reporter"],"alice")
        self.assertEqual(t["links"]["delivery"],v["delivery"]["id"])
        self.assertEqual(t["links"]["hold"],delivery._owned_hold(v["delivery"]["id"]))
        self.assertEqual(self.store.q("SELECT * FROM runs"),[])
        self.assertEqual(self.store.q("SELECT * FROM delivery_reviews"),[])
        self.assertEqual(v["revision"],1)
        self.assertFalse(v["technical_review_evaluated"])
        self.assertEqual(len(self.store.q("SELECT * FROM events WHERE ticket_id=?",(t["id"],))),2)

    def test_save_append_only_full_text_history_no_reviews_or_ticket_transition(self):
        v=self.create();did=v["delivery"]["id"]
        ticket=self.store.ticket(v["delivery"]["ticket_id"])
        text="  未执行测试的完整记录\n"*5000+"末尾"
        one=self.save(did,title=" 原始标题 ",body=text)
        a=one["stages"][1]["artifact"]
        self.assertEqual(a["body"],text);self.assertEqual(a["title"]," 原始标题 ")
        self.assertIsNone(a["source_run"])
        two=self.save(did,body="第二版")
        row=next(s for s in two["stages"] if s["key"]=="requirements")
        self.assertEqual(row["version"],2)
        self.assertEqual(row["history"][0]["body"],text)
        self.assertEqual(self.store.ticket(ticket["id"]),ticket)
        self.assertEqual(self.store.q("SELECT * FROM delivery_reviews"),[])
        self.assertEqual(self.store.q("SELECT * FROM runs"),[])

    def test_all_selected_stages_accept_manual_documents_without_approval(self):
        v=self.create();did=v["delivery"]["id"]
        for key in delivery.STAGE:
            result=self.save(did,stage=key,body="完整手工材料；未验证运行结果")
            stage=next(s for s in result["stages"] if s["key"]==key)
            self.assertIsNone(stage["artifact"]["source_run"])
        self.assertEqual(len(self.store.q("SELECT * FROM delivery_artifacts")),8)
        self.assertEqual(self.store.q("SELECT * FROM delivery_reviews"),[])
        self.assertEqual(self.store.q("SELECT * FROM runs"),[])

    def test_read_is_snapshot_only_and_body_kept_when_execution_disabled(self):
        did=self.create()["delivery"]["id"];self.save(did)
        before=dump_store(self.store)
        with patch.object(delivery,"_db",side_effect=AssertionError("legacy schema")),patch.object(delivery,"view",side_effect=AssertionError("legacy view")),patch("subprocess.Popen",side_effect=AssertionError("execution")):
            v=D.read(self.P,did,"reader")
        self.assertFalse(v["can_edit"]);self.assertTrue(all(not x["can_save"] for x in v["stages"]))
        self.assertEqual(dump_store(self.store),before)

    def test_viewer_cross_project_reference_and_missing_member_rejected(self):
        payload=self.create_body()
        self.assert_api(403,lambda:D.create(self.P,payload,"reader"))
        self.assert_api(403,lambda:D.create(self.P,payload,"other"))
        self.assert_api(403,lambda:D.create(self.P,payload,"agent"))
        did=D.create(self.P,payload,"alice")["delivery"]["id"]
        self.assert_api(403,lambda:D.read(self.P,did,"other"))
        self.store.x("UPDATE project_profiles SET workflow='reference' WHERE project_id=?",(self.project["id"],))
        self.assertFalse(D.read(self.P,did,"alice")["can_edit"])
        self.assert_api(403,lambda:self.save(did))
        self.assert_api(403,lambda:D.create(self.P,self.create_body(),"alice"))

    def test_replay_requires_live_membership_and_exact_scope_payload(self):
        payload=self.create_body();a=D.create(self.P,payload,"alice")
        b=D.create(self.P,payload,"alice")
        self.assertTrue(b["receipt"]["replayed"])
        self.assertEqual(a["delivery"]["id"],b["delivery"]["id"])
        self.assertEqual(len(self.store.q("SELECT * FROM tickets")),1)
        self.assert_api(409,lambda:D.create(self.P,dict(payload,title="different"),"alice"))
        did=a["delivery"]["id"];save=self.save_body(did)
        one=D.act(self.P,did,save,"alice");two=D.act(self.P,did,save,"alice")
        self.assertTrue(two["receipt"]["replayed"])
        self.assertEqual(one["receipt"]["artifact_id"],two["receipt"]["artifact_id"])
        self.assert_api(409,lambda:D.act(self.P,did,dict(save,body="changed"),"alice"))
        self.context.people["alice"]["project_grants"]={}
        self.assert_api(403,lambda:D.create(self.P,payload,"alice"))
        self.assert_api(403,lambda:D.act(self.P,did,save,"alice"))

    def test_old_legacy_artifact_or_review_change_invalidates_editor_token(self):
        did=self.create()["delivery"]["id"]
        pending=self.save_body(did)
        aid=self.store.x("INSERT INTO delivery_artifacts(delivery_id,stage,version,title,body,created,author,inputs) VALUES(?,?,?,?,?,?,?,?)",(did,"requirements",1,"旧入口","完整正文","created","alice","{}"))
        self.assert_api(409,lambda:D.act(self.P,did,pending,"alice"))
        pending=self.save_body(did)
        self.store.x("INSERT INTO delivery_reviews(artifact_id,evidence,author,created,inputs) VALUES(?,?,?,?,?)",(aid,"历史复核","admin","created","{}"))
        self.assert_api(409,lambda:D.act(self.P,did,pending,"alice"))
        self.assertEqual(self.save(did)["revision"],2)

    def test_any_busy_stage_blocks_save_and_current_run_changes_token(self):
        v=self.create();did=v["delivery"]["id"];pending=self.save_body(did)
        run=self.store.create_run(self.project["id"],v["delivery"]["ticket_id"],"synthetic","ask","alice","no execution")
        self.store.x("INSERT INTO delivery_runs(delivery_id,stage,run_id,base_version,inputs,created) VALUES(?,?,?,?,?,?)",(did,"design",run["id"],0,"{}","created"))
        self.assert_api(409,lambda:D.act(self.P,did,pending,"alice"))
        self.assertTrue(all(not s["can_save"] for s in D.read(self.P,did,"alice")["stages"]))
        self.assert_api(409,lambda:self.save(did))
        self.store.x("UPDATE runs SET status='failed' WHERE id=?",(run["id"],))
        pending=self.save_body(did)
        self.store.x("UPDATE runs SET prompt='changed input' WHERE id=?",(run["id"],))
        self.assert_api(409,lambda:D.act(self.P,did,pending,"alice"))
        self.assertEqual(self.save(did)["revision"],2)

    def test_create_and_save_receipt_failure_roll_back_every_business_write(self):
        self.store.x("CREATE TRIGGER fail_content BEFORE INSERT ON delivery_content_requests BEGIN SELECT RAISE(ABORT,'injected'); END")
        before=dump_store(self.store)
        with self.assertRaisesRegex(sqlite3.IntegrityError,"injected"):self.create()
        self.assertEqual(dump_store(self.store),before)
        self.store.x("DROP TRIGGER fail_content")
        did=self.create()["delivery"]["id"]
        for table in ("events","delivery_content_requests"):
            self.store.x("CREATE TRIGGER fail_content BEFORE INSERT ON "+table+" BEGIN SELECT RAISE(ABORT,'injected'); END")
            before=dump_store(self.store)
            with self.assertRaisesRegex(sqlite3.IntegrityError,"injected"):self.save(did)
            self.assertEqual(dump_store(self.store),before)
            self.store.x("DROP TRIGGER fail_content")

    def test_save_never_uses_callbacks_lazy_schema_git_or_implicit_commit(self):
        did=self.create()["delivery"]["id"];body=self.save_body(did)
        fail=AssertionError("unsafe helper")
        with patch.object(delivery,"_db",side_effect=fail),patch.object(delivery,"_rows",side_effect=fail),patch.object(delivery,"view",side_effect=fail),patch.object(self.store,"x",side_effect=fail),patch("subprocess.Popen",side_effect=fail):
            v=D.act(self.P,did,body,"alice")
        self.assertEqual(v["revision"],2)

    def test_competing_connections_cas_and_same_request_idempotency(self):
        other=Store(self.store.path);self.addCleanup(other.db.close)
        P2=SimpleNamespace(store=other,data_dir=self.data,tenant_context=self.context)
        did=self.create()["delivery"]["id"]
        for same in (False,True):
            barrier=threading.Barrier(2);payload=self.save_body(did)
            def submit(P,suffix):
                barrier.wait(3)
                try:return D.act(P,did,dict(payload,request_id=payload["request_id"]+("" if same else suffix)),"alice")["receipt"]["replayed"]
                except ApiError as exc:return exc.code
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(submit,self.P,"a");b=pool.submit(submit,P2,"b")
                actual=[a.result(5),b.result(5)]
            self.assertEqual(sorted(actual),[False,True] if same else [False,409])
        self.assertEqual(len(self.store.q("SELECT * FROM delivery_artifacts")),2)

    def test_concurrent_create_numbers_are_unique_without_callbacks(self):
        other=Store(self.store.path);self.addCleanup(other.db.close)
        P2=SimpleNamespace(store=other,data_dir=self.data,tenant_context=self.context)
        first=self.create_body();second=self.create_body();barrier=threading.Barrier(2)
        def submit(P,payload):
            barrier.wait(3)
            return D.create(P,payload,"alice")["delivery"]["ticket"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(submit,self.P,first);b=pool.submit(submit,P2,second)
            self.assertEqual({a.result(5),b.result(5)},{"APP-1","APP-2"})
        self.assertEqual(len(self.store.q("SELECT * FROM delivery_items")),2)

    def test_bad_fields_never_declare_actor_review_execution_or_assignment(self):
        base=self.create_body()
        for extra in ({"actor":"admin"},{"by":"admin"},{"ticket":"APP-1"},{"assignee":"alice"},{"auto":True},{"type":[]},{"type":{}},{"stages":["develop"]}):
            self.assert_api(400,lambda extra=extra:D.create(self.P,dict(base,**extra),"alice"))
        did=D.create(self.P,base,"alice")["delivery"]["id"]
        body=self.save_body(did)
        for extra in ({"confirm":True},{"status":"approved"},{"source_run":1},{"by":"admin"},{"body":""},{"source_token":"bad"}):
            self.assert_api(400,lambda extra=extra:D.act(self.P,did,dict(body,**extra),"alice"))
        self.assert_api(400,lambda:D.act(self.P,did,dict(body,body="x"*(delivery.MAX_BODY+1)),"alice"))

    def test_source_token_binds_all_versions_not_only_latest(self):
        did=self.create()["delivery"]["id"];self.save(did,body="first");self.save(did,body="second")
        body=self.save_body(did)
        aid=self.store.one("SELECT id FROM delivery_artifacts WHERE delivery_id=? AND version=1",(did,))["id"]
        self.store.x("UPDATE delivery_artifacts SET body='changed old source' WHERE id=?",(aid,))
        self.assert_api(409,lambda:D.act(self.P,did,body,"alice"))

    def test_schema_migrates_old_binding_atomically_and_never_commits_caller(self):
        db=sqlite3.connect(":memory:");self.addCleanup(db.close)
        store=SimpleNamespace(db=db,lock=threading.RLock())
        db.execute("CREATE TABLE delivery_runs(id INTEGER PRIMARY KEY,delivery_id TEXT,stage TEXT,run_id INTEGER UNIQUE,base_version INTEGER,inputs TEXT,created TEXT)")
        db.execute("INSERT INTO delivery_runs VALUES(1,'legacy','requirements',99,0,'{}','created')");db.commit()
        before=tuple(db.iterdump())
        with patch.object(D,"DDL",D.DDL+("INVALID SQL",)):
            with self.assertRaises(sqlite3.OperationalError):D.schema(store)
        self.assertEqual(tuple(db.iterdump()),before)
        self.assertNotIn("binding",{r[1] for r in db.execute("PRAGMA table_info(delivery_runs)")})
        D.schema(store)
        self.assertEqual(db.execute("SELECT binding FROM delivery_runs").fetchone(),("{}",))
        after=tuple(db.iterdump());D.schema(store);self.assertEqual(tuple(db.iterdump()),after)
        db.execute("UPDATE delivery_runs SET inputs='pending' WHERE id=1")
        with self.assertRaisesRegex(RuntimeError,"cannot nest"):D.schema(store)
        self.assertTrue(db.in_transaction);db.rollback()
        self.assertEqual(db.execute("SELECT inputs FROM delivery_runs").fetchone(),("{}",))
