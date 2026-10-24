"""Authorized, lossless managed reads; all data is a local synthetic fixture."""
from contextlib import ExitStack, contextmanager
import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import learning as L, learning_runs as R, learning_experiments as X
from tmh.platform import learning_experiment_views as V, habits, readiness
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


class ExperimentViewsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="experiment-views-")
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "platform.db")
        self.addCleanup(self.store.db.close)
        L.schema(self.store)
        R.schema(self.store)
        X.schema(self.store)
        self.p = self.store.add_project("APP", "项目", self.tmp.name)
        self.other = self.store.add_project("OTHER", "另一项目", self.tmp.name)
        self.accounts = {name: {"active": 1, "epoch": name + "-epoch"} for name in ("curator", "manager", "viewer")}
        self.grants = {name: {"role": "admin" if name == "manager" else "member", "project_grants": {"APP": "viewer"}, "authz_revision": 1} for name in self.accounts}
        self.guard = threading.RLock()
        @contextmanager
        def authorization_guard():
            with self.guard:
                yield
        registry = SimpleNamespace(authorization_guard=authorization_guard, one=lambda sql, args: copy.deepcopy(self.accounts.get(args[0])))
        context = SimpleNamespace(registry=registry, tenant_id="tenant-a", current_actor=lambda name: copy.deepcopy(self.grants.get(name)))
        self.P = SimpleNamespace(store=self.store, tenant_context=context, data_dir=Path(self.tmp.name))
        self.eid, self.jid, self.rid = "e" * 32, "b" * 32, "c" * 32
        self.secret = "完整留出材料\r\n" + "不可流出〈Ω〉" * 700 + "\r\nEND-SENTINEL"
        self.assets = [{"id": str(i) * 32, "kind": kind, "content": {"raw": self.secret + kind}, "family": "synthetic-family-a", "lineage": [], "revision_id": self.rid if kind == "candidate" else "", "visibility": "custody", "known_to": ["curator"]} for i, kind in enumerate(("candidate", "evaluation", "task", "oracle", "cassette"), 1)]
        self.assets[0]["content"]["revision_id"] = self.rid
        for asset in self.assets:
            asset["content_hash"] = X.digest(asset["content"])
        self.contract = {"schema": X.VERSION, "experiment_type": "fixed_a", "synthetic": True,
            "candidate_revision_id": self.rid, "baseline": {"revision_id": "", "token": "private-token"},
            "source_binding": {"project_id": self.p["id"], "commit": "a" * 40, "root": self.secret},
            "roles": {"curator": "curator", "optimizer": "manager", "selector": "viewer"},
            "known_custodians": ["curator"], "task_set": X.TASK_SET,
            "tasks": [{"task_asset_id": self.assets[2]["id"], "family": "synthetic-family-a"}],
            "repeats": 1, "max_calls": 2, "timeout_seconds": 120, "concurrency": 1,
            "executor": {"id": X.EXECUTOR_ID, "code_sha256": "f" * 64, "paid_dispatch": False, "python": self.secret},
            "renderer": {"renderer": "lesson-renderer-v3"}, "knowledge_block_same_renderer": True,
            "synthetic_source_families": 1, "order": "repeat_then_task_then_baseline_candidate",
            "stop_rule": "first_failure_or_unknown_stops_remaining_slots", "asset_commitments": {a["id"]: a["content_hash"] for a in self.assets}}
        self.hash = X.digest(self.contract)
        self.insert("learning_revisions", dict(id=self.rid, project_id=self.p["id"], kind="lesson", origin_id="L1", title=self.secret,
            content=self.secret, source=X.encoded({"oracle": self.secret}), fingerprint="f", parent_id="", author="curator", created="2026-10-24"))
        self.insert("learning_experiments", dict(id=self.eid, tenant_id="tenant-a", project_id=self.p["id"], creator="manager", curator="curator", optimizer="manager", selector="viewer",
            principals=X.encoded({name: value["epoch"] for name, value in self.accounts.items()}), request_id="create", request_hash="hash", contract_version=X.VERSION,
            contract=X.encoded(self.contract), contract_hash=self.hash, state="sealed", job_id=self.jid, created="2026-10-24", sealed="2026-10-24", error=self.secret))
        for asset in self.assets:
            self.insert("learning_experiment_assets", dict(experiment_id=self.eid, **{key: X.encoded(value) if key in ("content", "lineage", "known_to") else value for key, value in asset.items()}))
        for seq, kind in enumerate(("create", "seal"), 1):
            self.insert("learning_experiment_events", dict(experiment_id=self.eid, seq=seq, kind=kind,
                actor="manager", request_id="anchor-" + kind, request_hash="fixture-anchor",
                payload=X.encoded({"contract_hash": self.hash}), created="2026-10-24"))
        opaque = X.encoded({"schema": X.VERSION, "managed_experiment_id": self.eid, "contract_hash": self.hash})
        self.add_job(self.jid, opaque)
        self.run_ids = []
        for i, arm in enumerate(("baseline", "candidate"), 1):
            sid, role = str(i + 5) * 32, "slot:" + str(i + 5) * 32
            run = self.store.create_run(self.p["id"], None, "claude", "evaluate", "curator", self.secret, target=role,
                batch="experiment:" + self.eid + ":" + sid)
            run_id = run["id"]
            self.run_ids.append(run_id)
            self.store.update_run(run_id, output=self.secret, result=self.secret, diff=self.secret, status="failed")
            self.insert("learning_steps", dict(job_id=self.jid, seq=i, role=role, prompt=self.secret, prompt_hash="hash", status="failed", run_id=run_id, output=self.secret, raw_output=self.secret, created="2026-10-24"))
            self.insert("learning_experiment_slots", dict(experiment_id=self.eid, id=sid, ordinal=i, task_asset_id=self.assets[2]["id"], arm=arm, repeat=1,
                job_id=self.jid, step_role=role, run_id=run_id, state="unknown" if i == 1 else "not_executed", reserved_calls=1 if i == 1 else 0,
                result=X.encoded({"output": self.secret}), cleanup=X.encoded({"private": self.secret}), created="2026-10-24"))

    def insert(self, table, row):
        self.store.x("INSERT INTO " + table + "(" + ",".join(row) + ") VALUES(" + ",".join("?" for _ in row) + ")", list(row.values()))

    def add_job(self, jid, options="{}"):
        self.insert("learning_jobs", dict(id=jid, project_id=self.p["id"], kind="evaluate", revision_id=self.rid, current_revision_id=self.rid,
            request_id=jid, request_hash="hash", actor="curator", status="not_passed", options=options, binding="{}", created="2026-10-24", deadline=0,
            result=X.encoded({"output": self.secret}), error=self.secret))

    def expose(self, actor, assets=None):
        seq = self.store.one("SELECT COALESCE(MAX(seq),0)+1 n FROM learning_experiment_events")["n"]
        self.insert("learning_experiment_events", dict(experiment_id=self.eid, seq=seq, kind="expose", actor=actor, request_id=str(seq), request_hash="h",
            payload=X.encoded({"asset_ids": assets or [a["id"] for a in self.assets], "recipient": actor, "account_epoch": self.accounts[actor]["epoch"]}), created="2026-10-24"))

    def assert_safe(self, value):
        encoded = json.dumps(value, ensure_ascii=False)
        self.assertNotIn("END-SENTINEL", encoded)
        self.assertNotIn("private-token", encoded)
        self.assertNotIn("不可流出", encoded)

    def test_viewer_manager_and_curator_tool_receive_safe_full_plan(self):
        for actor in ("viewer", "manager", "curator"):
            if actor == "curator":
                self.grants[actor]["tool_connection"] = {"id": "tool"}
            with self.subTest(actor=actor):
                exp = V.experiment(self.P, self.p, self.eid, actor)
                self.assert_safe(exp)
                self.assertEqual(exp["planned_slots"], 2)
                self.assertEqual(exp["slot_counts"]["unknown"], 1)
                self.assertEqual(exp["slot_counts"]["not_executed"], 1)
                self.assertEqual(exp["budget"]["reserved_calls"], 1)
                self.assertEqual(exp["scientific_contract"]["roles"], self.contract["roles"])
                self.assertFalse(exp["rsi_qualified"])
                self.assertFalse(exp["production_prompt_equivalence"])
                self.assertFalse(exp["can_adopt"])
                self.assert_safe(V.job(self.P, self.p, self.jid, actor))
                self.assert_safe(V.run(self.P, self.p, self.run_ids[0], actor, include_prompt=True))

    def test_curator_gets_every_original_string_and_no_live_currentness_claim(self):
        exp = V.experiment(self.P, self.p, self.eid, "curator")
        self.assertEqual(exp["assets"][0]["content"]["raw"], self.secret + "candidate")
        self.assertFalse(exp["protected"])
        self.assertEqual(exp["currentness"], "not_checked")
        job = V.job(self.P, self.p, self.jid, "curator")
        self.assertEqual(job["steps"][0]["raw_output"], self.secret)
        run = V.run(self.P, self.p, self.run_ids[0], "curator", include_prompt=True)
        self.assertEqual(run["prompt"], self.secret)
        self.assertEqual(run["output"], self.secret)
        self.assertFalse(run["can_retry"])

    def test_exposure_requires_all_linked_assets_and_current_personal_epoch(self):
        self.expose("viewer", [self.assets[0]["id"]])
        exp = V.experiment(self.P, self.p, self.eid, "viewer")
        self.assertEqual(exp["assets"][0]["content"]["raw"], self.secret + "candidate")
        self.assert_safe(V.job(self.P, self.p, self.jid, "viewer"))
        self.expose("viewer")
        self.assertFalse(V.job(self.P, self.p, self.jid, "viewer")["protected"])
        self.accounts["viewer"]["epoch"] = "new-account-epoch"
        self.assert_safe(V.job(self.P, self.p, self.jid, "viewer"))

    def test_account_revocation_project_removal_and_unrelated_revision(self):
        self.grants["manager"]["authz_revision"] += 100
        self.assertFalse(V.experiment(self.P, self.p, self.eid, "curator")["protected"])
        self.accounts["curator"]["epoch"] = "recreated"
        self.assert_safe(V.experiment(self.P, self.p, self.eid, "curator"))
        self.grants["curator"]["project_grants"] = {}
        with self.assertRaises(ApiError) as raised:
            V.experiment(self.P, self.p, self.eid, "curator")
        self.assertEqual(raised.exception.code, 403)

    def test_manual_job_on_same_revision_keeps_old_full_history(self):
        self.add_job("d" * 32)
        self.assertIsNone(V.job(self.P, self.p, "d" * 32, "viewer"))
        old = R.get(self.P, self.p, "d" * 32)
        catalog = V.catalog(self.P, self.p, {"items": [], "jobs": [old]}, "viewer")
        self.assertEqual(catalog["jobs"][0], old)
        self.assertEqual(catalog["jobs"][0]["result"]["output"], self.secret)

    def test_all_detail_decision_copies_are_projected_and_input_not_mutated(self):
        revision = L.revision(self.P, self.p, self.rid)
        decision = {"id": "decision", "revision_id": self.rid, "payload": {"content": self.secret}, "result": {"oracle": self.secret}}
        payload = {"revision": revision, "history": [revision], "jobs": [{"id": self.jid}], "decisions": [decision], "current": True, "expected_token": self.secret}
        before = copy.deepcopy(payload)
        self.assert_safe(V.learning_detail(self.P, self.p, payload, "viewer"))
        self.assert_safe(V.decision(self.P, self.p, decision, "viewer"))
        self.assertEqual(payload, before)

    def test_partial_or_contradictory_ownership_never_becomes_manual(self):
        self.store.update_run(self.run_ids[0], project_id=self.other["id"])
        with self.assertRaises(ApiError) as error:
            V.run(self.P, self.p, self.run_ids[0], "viewer")
        self.assertEqual(error.exception.code, 409)
        self.store.x("DROP TABLE learning_experiment_events")
        with self.assertRaises(ApiError) as error:
            V.job(self.P, self.p, self.jid, "viewer")
        self.assertEqual(error.exception.code, 409)

    def test_reads_do_not_write_migrate_recover_or_probe(self):
        statements = []
        before = self.store.db.total_changes
        self.store.db.set_trace_callback(statements.append)
        self.addCleanup(self.store.db.set_trace_callback, None)
        with patch.object(X, "schema", side_effect=AssertionError("migration")), patch.object(R, "recover", side_effect=AssertionError("recovery")), patch.object(L, "binding", side_effect=AssertionError("source probe")):
            V.experiment(self.P, self.p, self.eid, "curator")
            V.job(self.P, self.p, self.jid, "curator")
            V.run(self.P, self.p, self.run_ids[0], "curator", include_prompt=True)
        self.assertEqual(self.store.db.total_changes, before)
        self.assertFalse(any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "BEGIN")) for s in statements))

    def test_operational_analytics_exclude_experimental_text_before_derivation(self):
        original = self.store.create_run(self.p["id"], None, "claude", "ask", "curator", "常规提问")
        self.store.update_run(original["id"], status="done", result="ok")
        clause = V.unmanaged_run_clause(self.store)
        rows = self.store.q("SELECT id FROM runs r WHERE " + clause + " ORDER BY id DESC LIMIT 1")
        self.assertEqual([r["id"] for r in rows], [original["id"]])
        self.assertEqual(habits.available(self.store)["runs"], 1)
        with patch("tmh.platform.agents.available", return_value=[{"name": "claude", "title": "Claude", "available": True}]):
            result = readiness._agents(self.P)
        self.assert_safe(result)
        self.assertFalse(any(x["key"] == "agent:claude" for x in result))

    def test_lists_apply_project_scope_before_limit_and_keep_required_null_keys(self):
        result = V.runs(self.P, "viewer", project_id=self.p["id"], limit=1, allowed_projects=[self.p["id"]])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], self.run_ids[-1])
        self.assertIsNone(result[0]["ticket_id"])
        self.assertIsNone(result[0]["session_id"])
        self.assert_safe(result)

    def test_legacy_reader_is_safe_even_with_curator_display_name(self):
        legacy = SimpleNamespace(store=self.store, data_dir=Path(self.tmp.name))
        self.assert_safe(V.experiment(legacy, self.p, self.eid, "curator"))
        self.assertFalse(V.experiments(legacy, self.p, "curator")["can_create"])

    def test_readonly_tenant_or_project_curator_has_no_post_capabilities(self):
        for tenant_role, grant in (("viewer", "manager"), ("member", "viewer")):
            with self.subTest(tenant_role=tenant_role, grant=grant):
                self.grants["curator"].update(role=tenant_role, project_grants={"APP": grant})
                view = V.experiment(self.P, self.p, self.eid, "curator")
                self.assertFalse(view["protected"])
                self.assertFalse(any(view["capabilities"].values()))

    def test_request_identity_is_current_person_epoch_and_never_tool_or_legacy(self):
        for actor in ('curator', 'manager', 'viewer'):
            with self.subTest(actor=actor):
                expected={'tenant_id':'tenant-a','actor':actor,'account_epoch':actor+'-epoch'}
                self.assertEqual(V.experiments(self.P,self.p,actor)['request_identity'],expected)
                self.assertEqual(V.experiment(self.P,self.p,self.eid,actor)['request_identity'],expected)
        self.accounts['viewer']['epoch']='viewer-recreated'
        self.assertEqual(V.experiments(self.P,self.p,'viewer')['request_identity']['account_epoch'],'viewer-recreated')
        self.grants['curator']['tool_connection']={'id':'tool'}
        self.assertIsNone(V.experiment(self.P,self.p,self.eid,'curator')['request_identity'])
        legacy=SimpleNamespace(store=self.store,data_dir=self.P.data_dir)
        self.assertIsNone(V.experiments(legacy,self.p,'curator')['request_identity'])

    def test_direct_capture_revision_reply_uses_same_custody_gate(self):
        payload=L.revision(self.P,self.p,self.rid)
        before=copy.deepcopy(payload)
        manager=V.revision(self.P,self.p,payload,'manager')
        self.assert_safe(manager)
        self.assertEqual(manager['id'],self.rid)
        self.assertTrue(manager['managed'])
        self.assertTrue(manager['protected'])
        self.assertIsNone(manager['content'])
        curator=V.revision(self.P,self.p,payload,'curator')
        self.assertEqual(curator['id'],self.rid)
        self.assertEqual(curator['content'],payload['content'])
        self.assertEqual(curator['source'],payload['source'])
        self.assertFalse(curator['protected'])
        self.assertEqual(payload,before)

    def test_real_tool_context_never_inherits_curator_full_custody(self):
        from tmh.platform.tenant_runtime import TenantContext
        registry=self.P.tenant_context.registry
        registry.data_dir=self.P.data_dir
        registry.context=lambda actor,tenant: {**copy.deepcopy(self.grants[actor]),
            'tenant':{'id':tenant,'status':'active'},'capabilities':{'read':True,'write':True,'execution':True},
            'project_grants':[{'project_id':str(self.p['id']),'role':'viewer'}]}
        context=TenantContext(registry,'tenant-a')
        context.platform=self.P
        self.P.tenant_context=context
        for scope in ('read','content'):
            with self.subTest(scope=scope),context.acting('curator',{'id':'tool','user':'curator','tenant':'tenant-a','scope':scope,'project_ids':[self.p['id']]}):
                exp=V.experiment(self.P,self.p,self.eid,'curator')
                self.assert_safe(exp)
                self.assertTrue(exp['protected'])
                self.assertIsNone(exp['request_identity'])
                self.assertFalse(any(exp['capabilities'].values()))
                self.assert_safe(V.job(self.P,self.p,self.jid,'curator'))
                run=V.run(self.P,self.p,self.run_ids[0],'curator',include_prompt=True)
                self.assertEqual(run['prompt'],'')
                self.assertEqual(run['output'],'')
                self.assert_safe(run)
                self.assert_safe(V.revision(self.P,self.p,L.revision(self.P,self.p,self.rid),'curator'))
        self.assertFalse(V.experiment(self.P,self.p,self.eid,'curator')['protected'])

    @contextmanager
    def forbid_live_reads(self, *, manual_annotations=False):
        from tmh.platform import learning_eval as E
        with ExitStack() as stack:
            for owner, name in ((L, "detail"), (L, "revision_current"), (L, "binding"),
                                (L.pk, "git"), (R, "get"), (R, "recover"), (E, "current")):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError("live read: " + name)))
            if not manual_annotations:
                stack.enter_context(patch.object(R, "_input_description", side_effect=AssertionError("managed input annotation")))
            yield

    def test_managed_detail_classifies_before_all_live_or_legacy_reads(self):
        statements = []
        before = self.store.db.total_changes
        self.store.db.set_trace_callback(statements.append)
        self.addCleanup(self.store.db.set_trace_callback, None)
        with self.forbid_live_reads():
            safe = V.managed_detail(self.P, self.p, self.rid, "viewer")
            full = V.managed_detail(self.P, self.p, self.rid, "curator")
        self.assert_safe(safe)
        self.assertTrue(safe["managed"])
        self.assertFalse(safe["current"])
        self.assertIsNone(safe["expected_token"])
        self.assertIsNone(safe["active_revision_id"])
        self.assertEqual(safe["currentness"], "not_checked")
        self.assertEqual(full["revision"]["content"], self.secret)
        self.assertEqual(full["jobs"][0]["steps"][0]["raw_output"], self.secret)
        self.assertEqual(self.store.db.total_changes, before)
        self.assertFalse(any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "BEGIN")) for s in statements))

    def test_manual_target_keeps_own_currentness_and_projects_managed_sibling_history(self):
        rid = "f" * 32
        row = self.store.one("SELECT * FROM learning_revisions WHERE id=?", (self.rid,))
        self.insert("learning_revisions", dict(row, id=rid, title="原手工修订", content="旧全文\r\n仍保留", source="{}"))
        with self.forbid_live_reads():
            self.assertIsNone(V.managed_detail(self.P, self.p, rid, "viewer"))
        from tmh.platform import learning_decisions as D
        with patch.object(R, "get", side_effect=AssertionError("unclassified jobs")), \
                patch.object(L, "revision_current", return_value=True) as current, \
                patch.object(D, "_token", return_value="manual-token"):
            payload = L.detail(self.P, self.p, rid,
                recorded_jobs=lambda value: V.catalog_jobs(self.P, self.p, "viewer", value, detail=True))
            result = V.learning_detail(self.P, self.p, payload, "viewer")
        current.assert_called_once()
        self.assertEqual(current.call_args.args[2]["id"], rid)
        self.assertNotIn("managed", result)
        self.assertTrue(result["current"])
        self.assertEqual(result["expected_token"], "manual-token")
        self.assertEqual(result["revision"]["content"], "旧全文\r\n仍保留")
        protected = next(r for r in result["history"] if r["id"] == self.rid)
        self.assertTrue(protected["protected"])
        self.assertIsNone(protected["content"])
        self.assert_safe(result)

    def test_pure_catalog_classifies_before_legacy_job_and_currentness_description(self):
        before = self.store.db.total_changes
        with self.forbid_live_reads():
            meta = V.catalog_revision(self.P, self.p, self.rid, "viewer")
            rows = V.catalog_jobs(self.P, self.p, "viewer")
            full = V.catalog_jobs(self.P, self.p, "curator", rid=self.rid)
        self.assert_safe(meta)
        self.assert_safe(rows)
        self.assertIsNone(meta["stale"])
        self.assertEqual(meta["currentness"], "not_checked")
        self.assertEqual(meta["machine"], {"status": "managed", "job_id": self.jid})
        self.assertEqual([j["id"] for j in rows], [self.jid])
        self.assertEqual(full[0]["steps"][0]["raw_output"], self.secret)
        self.assertEqual(self.store.db.total_changes, before)

    def test_mixed_catalog_and_managed_detail_keep_preexisting_manual_job_full(self):
        jid = "d" * 32
        self.add_job(jid)
        old_list = next(j for j in R.list_jobs(self.P, self.p) if j["id"] == jid)
        old_detail = R.get(self.P, self.p, jid)
        with self.forbid_live_reads(manual_annotations=True):
            catalog = V.catalog_jobs(self.P, self.p, "viewer")
            detail = V.managed_detail(self.P, self.p, self.rid, "viewer")
        self.assertEqual([j["id"] for j in catalog], [jid, self.jid])
        self.assertEqual(catalog[0], old_list)
        self.assertEqual(detail["jobs"][0], old_detail)
        self.assertEqual(detail["jobs"][0]["result"]["output"], self.secret)
        self.assertTrue(detail["jobs"][1]["protected"])

    def test_none_requires_known_unmanaged_records_and_ownership_errors_propagate(self):
        rid = "f" * 32
        row = self.store.one("SELECT * FROM learning_revisions WHERE id=?", (self.rid,))
        self.insert("learning_revisions", dict(row, id=rid, origin_id="manual-origin", content="旧手工正文", source="{}"))
        with self.forbid_live_reads():
            self.assertIsNone(V.managed_detail(self.P, self.p, rid, "viewer"))
            self.assertIsNone(V.catalog_revision(self.P, self.p, rid, "viewer"))
            with self.assertRaises(ApiError) as missing:
                V.managed_detail(self.P, self.p, "missing", "viewer")
            self.assertEqual(missing.exception.code, 404)
            self.store.x("DROP TABLE learning_experiment_events")
            for read in (lambda: V.managed_detail(self.P, self.p, rid, "viewer"),
                         lambda: V.catalog_revision(self.P, self.p, rid, "viewer"),
                         lambda: V.catalog_jobs(self.P, self.p, "viewer")):
                with self.assertRaises(ApiError) as broken:
                    read()
                self.assertEqual(broken.exception.code, 409)
