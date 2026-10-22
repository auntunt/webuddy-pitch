"""Real DB/ledger adoption boundaries with executed synthetic answer assertions.

The evaluator fixture executes both sides and persists the full synthetic steps;
it is evidence for transaction mechanics, not real model quality or usage costs.
No worker is launched and no model executable/network is used.
"""
from contextlib import contextmanager
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh import kb
from tmh.platform import learn, learning as L, learning_decisions as D
from tmh.platform import learning_eval as E, learning_runs as R, learning_facts as F, server
from tmh.platform.errors import ApiError
from tmh.platform.store import Store, now


class LearningDecisionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-learning-decisions-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "runtime"
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.source = self.root / "app.py"
        self.source.write_text("STATUS = 'OPEN'\n", encoding="utf-8")
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.p = self.store.add_project("APP", "应用项目", str(self.root))
        other_root = Path(self.temp.name) / "other"
        other_root.mkdir()
        self.other = self.store.add_project("OTHER", "另一项目", str(other_root))
        self.fields = {"title": "重复回调处理", "symptom": "相同事件重复投递", "cause": "重试投递",
                       "fix": "使用持久幂等键", "verify": "两次投递只提交一次", "anti": "不丢弃独立事件",
                       "applicability": "同一事件的重复回调", "non_applicability": "不同事件"}
        self.card = learn.add_lesson(self.data, dict(self.fields, project=self.p["key"], status="candidate",
                                                    ticket="APP-1", files=["app.py"]))
        item = L._origin(self.P, self.p, "lesson:" + self.card["id"])
        self.r = L.capture(self.P, self.p, item["key"], item["fingerprint"], "writer")
        self.serial = 0

    def second_store(self):
        store = Store(self.store.path)
        self.addCleanup(store.db.close)
        return SimpleNamespace(store=store, data_dir=self.data)

    @staticmethod
    def cases(prefix="ordinary"):
        return [{"id": "%s-%d" % (prefix, i), "input": "%s 回调场景 %d" % (prefix, i),
                 "validator": "exact", "expected": "已按幂等规则处理", "generation": False,
                 "scenario": "retry" if i else "first_delivery"} for i in range(3)]

    @staticmethod
    def configuration(*_):
        return {"agent": "claude", "model": "synthetic-fixture", "configuration": {"isolated": True},
                "executable": "not-executed", "prompt_version": R.PROMPT_VERSION}

    @staticmethod
    def policy_pack(P, p, query, budget):
        # Context retrieval has separate tests. Here varying complete synthetic
        # packs makes the actual paired assertions exercise the policy protocol.
        receipt = {"budget": budget, "items": [query, str(budget)]}
        return {"text": L.encoded(receipt), "receipt": receipt, "digest": L.digest(receipt)}

    def start(self, r=None, cases=None, request_id=None):
        self.serial += 1
        r = r or self.r
        with patch.object(R, "_configuration", side_effect=self.configuration):
            return R.start(self.P, self.p, "evaluate", r["id"],
                           {"cases": cases or self.cases(str(self.serial)), "max_calls": 20},
                           "operator", request_id or "eval-%d" % self.serial, launch=False)

    def seal(self, job):
        steps = []
        def step(role, prompt):
            output = "已按幂等规则处理" if role.endswith(":candidate") else "尚未能根据材料确定处理方式"
            steps.append((role, prompt, output))
            return output
        result = E.run(self.P, self.p, job, step)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["counts"], {"baseline": 0, "candidate": 3})
        with L.transaction(self.store) as db:
            for seq, (role, prompt, output) in enumerate(steps, 1):
                db.execute("""INSERT INTO learning_steps
                    (job_id,seq,role,prompt,prompt_hash,status,output,raw_output,exit_code,created,ended,elapsed_seconds)
                    VALUES(?,?,?,?,?,'done',?,?,0,?,?,0)""",
                    (job["id"], seq, role, prompt, R._hash(prompt), output, output, now(), now()))
            db.execute("UPDATE learning_jobs SET status='passed',result=?,calls=?,ended=? WHERE id=?",
                       (L.encoded(result), len(steps), now(), job["id"]))
        return R.get(self.P, self.p, job["id"])

    def passed(self, r=None, **kwargs):
        return self.seal(self.start(r, **kwargs))

    def fact_candidate(self):
        page = self.root / ".tmh" / "knowledge" / "index.md"
        page.parent.mkdir(parents=True)
        original = ("---\nid: index\ntitle: 状态查询\nsummary: 查询固定的应用状态\nstatus: 待确认\n"
                    "custom: 保留原始登记字段\n---\n# 状态查询\n\n" + kb.FACTS_START +
                    "\n固定状态值 OPEN，依据 `app.py:1`。\n" + kb.FACTS_END + "\n\n" +
                    "\n\n".join("## " + title + "\n状态值是 OPEN，依据 `app.py:1`。" for title in kb.SECTIONS["index"]) + "\n")
        page.write_text(original, encoding="utf-8")
        kb.save_registry(self.root, {"index": {"status": kb.STATUS_DRAFT, "title": "状态查询",
                                              "summary": "查询固定的应用状态", "custom": {"keep": [1, 2, 3]}}})
        item = L._origin(self.P, self.p, "fact:index")
        base = L.capture(self.P, self.p, item["key"], item["fingerprint"], "agent:writer")
        candidate = L.propose(self.P, self.p, base["id"], original + "\n该状态由固定源码定义。\n", "agent:writer")
        return page, candidate

    def reviewed_fact(self, revision):
        self.serial += 1
        with patch.object(R, "_configuration", side_effect=self.configuration):
            job = R.start(self.P, self.p, "review", revision["id"], {"max_revisions": 0},
                          "operator", "fact-review-%d" % self.serial, launch=False)
        expected = R.claims(revision["content"])
        evidence = revision["source"]["evidence"][0]
        output = L.encoded({"claims": [{"id": c["id"], "verdict": "supported", "kind": "code",
                            "reason": "合成回执：固定源码定义了所述状态，验证记录与事务机制",
                            "evidence": [{"path": evidence["path"], "sha256": evidence["sha256"],
                                          "start": 1, "end": 1, "quote": evidence["content"].splitlines()[0]}]}
                           for c in expected], "summary": "合成事实评审，仅证明工程机制"})
        result = R._validate_review(revision, expected, output)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["human_confirmation"], "pending")
        prompt = R._review_prompt(revision, expected)
        with L.transaction(self.store) as db:
            db.execute("""INSERT INTO learning_steps
                (job_id,seq,role,prompt,prompt_hash,status,output,raw_output,exit_code,created,ended,elapsed_seconds)
                VALUES(?,1,'review:0',?,?,'done',?,?,0,?,?,0)""",
                (job["id"], prompt, R._hash(prompt), output, output, now(), now()))
            db.execute("INSERT INTO learning_rounds VALUES(?,0,?,?,?,?)",
                       (job["id"], revision["id"], L.encoded(expected), L.encoded(result), now()))
            db.execute("UPDATE learning_jobs SET status='passed',result=?,calls=1,ended=? WHERE id=?",
                       (L.encoded(result), now(), job["id"]))
        return R.get(self.P, self.p, job["id"])

    def decide(self, job, r=None, P=None, action="adopt", expected=None, request="adopt", actor="alice"):
        r = r or self.r
        return D.decide(P or self.P, self.p, action, r["id"], actor, request, expected,
                        "核对冻结证据后作出本项目决定", job["id"] if job else "")

    def pending(self, job, r=None, **kwargs):
        with patch.object(D, "project_decision", side_effect=OSError("after durable intent")):
            with self.assertRaisesRegex(OSError, "durable intent"):
                self.decide(job, r, **kwargs)
        return self.store.one("SELECT * FROM learning_decisions WHERE status='pending'")

    def parallel(self, calls):
        barrier = threading.Barrier(len(calls))
        results = [None] * len(calls)
        def worker(index, call):
            try:
                barrier.wait(5)
                results[index] = ("ok", call())
            except BaseException as exc:
                results[index] = ("error", exc)
        threads = [threading.Thread(target=worker, args=(i, call), daemon=True) for i, call in enumerate(calls)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "adoption lock order deadlocked")
        return results

    def assert_conflict(self, call):
        with self.assertRaises(ApiError) as caught:
            call()
        self.assertEqual(caught.exception.code, 409)

    def test_only_authenticated_personal_route_can_adopt_and_actor_cannot_be_spoofed(self):
        job = self.passed()
        body = {"action": "adopt", "project": self.p["key"], "revision_id": self.r["id"],
                "request_id": "route", "expected_active": None, "reason": "本人核对", "job_id": job["id"],
                "actor": "forged-person"}
        for who, headers in (("", {}), ("alice", {"X-Webuddy-Agent": "bot"}),
                             ("", {"X-Webuddy-User": "alice"})):
            req = SimpleNamespace(body=body, user="shared-token", h=SimpleNamespace(_who=who, headers=headers))
            with self.subTest(who=who, headers=headers), self.assertRaises(ApiError) as caught:
                server.api_learning_action(self.P, req)
            self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.store.q("SELECT * FROM learning_decisions"), [])
        req = SimpleNamespace(body=body, user="shared-token", h=SimpleNamespace(_who="alice", headers={}))
        result = server.api_learning_action(self.P, req)
        self.assertEqual(result["actor"], "alice")
        self.assertEqual(result["status"], "applied")

    def test_reserved_agent_actors_never_make_a_human_decision(self):
        job = self.passed()
        for actor in ("", "system", "agent", "agent:writer", "external:token", "自动流转"):
            with self.subTest(actor=actor), self.assertRaises(ApiError) as caught:
                self.decide(job, actor=actor)
            self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.store.q("SELECT * FROM learning_decisions"), [])
        self.assertEqual(learn.lesson(self.data, self.card["id"])["status"], "candidate")

    def test_revision_and_decision_ids_cannot_cross_projects(self):
        job = self.passed()
        with self.assertRaises(ApiError) as caught:
            D.decide(self.P, self.other, "adopt", self.r["id"], "alice", "cross", None, "核对", job["id"])
        self.assertEqual(caught.exception.code, 404)
        pending = self.pending(job)
        with self.assertRaises(ApiError) as caught:
            D.project_decision(self.P, self.other, pending["id"])
        self.assertEqual(caught.exception.code, 404)
        self.assertIsNone(learn.active_revision(self.data, self.card["id"]))

    def test_partial_lesson_proposal_remains_current_after_actual_adoption(self):
        proposal = L.propose(self.P, self.p, self.r["id"], L.encoded({"fix": "事务内持久保存幂等键"}), "agent:writer")
        self.assertEqual(json.loads(proposal["content"]), dict(self.fields, fix="事务内持久保存幂等键"))
        adopted = self.decide(self.passed(proposal), proposal)
        self.assertEqual(adopted["status"], "applied")
        self.assertTrue(D.adopted_current(self.P, self.p, proposal))
        self.assertTrue(L.detail(self.P, self.p, proposal["id"])["current"])
        current = learn.lesson(self.data, self.card["id"])
        self.assertEqual(L.encoded({f: current[f] for f in L.LESSON_FIELDS}), proposal["content"])
        self.assertEqual(D.usable_lessons(self.store, self.p, [current])[0], [current])
        next_revision = L.propose(self.P, self.p, proposal["id"], L.encoded({"verify": "并发重复回调只落库一次"}), "agent:writer")
        self.assertEqual(json.loads(next_revision["content"])["fix"], "事务内持久保存幂等键")
        self.assertTrue(L.revision_current(self.P, self.p, next_revision))
        self.decide(self.passed(next_revision), next_revision, expected=proposal["id"], request="next")
        self.assertTrue(D.adopted_current(self.P, self.p, next_revision))

    def test_fact_adoption_can_be_revised_reviewed_and_adopted_again_without_inheriting_confirmation(self):
        page, first = self.fact_candidate()
        first_job = self.reviewed_fact(first)
        first_adoption = self.decide(first_job, first, request="fact-first")
        self.assertEqual(F.active_revision(self.P, self.p, "index"), first["id"])
        self.assertIn("status: 待确认\n", first["content"])
        published = page.read_text(encoding="utf-8")
        self.assertIn("status: 已确认\n", published)
        regpath = page.parent / ".pages.json"
        before = page.read_bytes(), regpath.read_bytes()
        second = L.propose(self.P, self.p, first["id"], first["content"] + "\n再次说明：状态取自固定源码。\n", "agent:writer")
        self.assertEqual(second["parent_id"], first["id"])
        self.assertEqual(second["source"]["origin_fingerprint"], L.digest(published))
        self.assertEqual(second["source"]["registry"], json.loads(before[1])["index"])
        self.assertEqual(second["content"], published + "\n再次说明：状态取自固定源码。\n")
        self.assertEqual(kb.FACTS_RX.findall(second["content"]), kb.FACTS_RX.findall(first["content"]))
        self.assertEqual((page.read_bytes(), regpath.read_bytes()), before)
        self.assertTrue(L.revision_current(self.P, self.p, second))
        self.assertEqual(F.active_revision(self.P, self.p, "index"), first["id"])
        self.assertFalse(D.adopted_current(self.P, self.p, second))
        # The prior exact-version review is never transferred to this new body.
        self.assert_conflict(lambda: self.decide(first_job, second, expected=first["id"], request="no-new-review"))
        self.assertEqual((page.read_bytes(), regpath.read_bytes()), before)
        second_job = self.reviewed_fact(second)
        second_adoption = self.decide(second_job, second, expected=first["id"], request="fact-second", actor="bob")
        self.assertEqual(second_adoption["status"], "applied")
        self.assertEqual(page.read_text(encoding="utf-8"), second["content"])
        self.assertEqual(F.active_revision(self.P, self.p, "index"), second["id"])
        record = json.loads(regpath.read_text(encoding="utf-8"))["index"]
        self.assertEqual(record["confirmed_by"], "bob")
        self.assertEqual(record["custom"], {"keep": [1, 2, 3]})
        self.assertEqual(record["learning"]["receipts"][first_adoption["id"]]["stage"], "applied")
        after = page.read_bytes(), regpath.read_bytes()
        self.assertEqual(self.decide(first_job, first, request="fact-first")["id"], first_adoption["id"])
        self.assertEqual((page.read_bytes(), regpath.read_bytes()), after)
        self.assertEqual(L.revision(self.P, self.p, first["id"])["content"], first["content"])
        self.assert_conflict(lambda: L.propose(self.P, self.p, first["id"], first["content"] + "旧父修订", "agent:writer"))
        third = L.propose(self.P, self.p, second["id"], second["content"] + "\n下一次修改仍为未采用草稿。\n", "agent:writer")
        self.assertTrue(L.revision_current(self.P, self.p, third))
        self.assertFalse(D.adopted_current(self.P, self.p, third))

    def test_next_fact_revision_cannot_forge_human_metadata_generated_facts_or_stale_source(self):
        page, first = self.fact_candidate()
        self.decide(self.reviewed_fact(first), first, request="fact-first")
        regpath = page.parent / ".pages.json"
        before = page.read_bytes(), regpath.read_bytes()
        revisions = self.store.q("SELECT id FROM learning_revisions")
        malicious = [first["content"].replace("status: 待确认", "status: 已确认"),
                     first["content"].replace("status: 待确认", "status: 待确认\nconfirmed_by: agent"),
                     first["content"].replace("固定状态值 OPEN", "固定状态值 CLOSED")]
        for content in malicious:
            with self.subTest(content=content), self.assertRaises(ApiError) as caught:
                L.propose(self.P, self.p, first["id"], content, "agent:writer")
            self.assertEqual(caught.exception.code, 400)
        self.source.write_text("STATUS = 'CLOSED'\n", encoding="utf-8")
        self.assert_conflict(lambda: L.propose(self.P, self.p, first["id"], first["content"] + "\n新说明", "agent:writer"))
        self.assertEqual((page.read_bytes(), regpath.read_bytes()), before)
        self.assertEqual(self.store.q("SELECT id FROM learning_revisions"), revisions)

    def test_two_stores_competing_adoptions_have_one_winner(self):
        other = self.second_store()
        r2 = L.propose(self.P, self.p, self.r["id"], L.encoded(dict(self.fields, fix="在事务中保存幂等键")), "writer")
        job1, job2 = self.passed(), self.passed(r2)
        results = self.parallel([lambda: self.decide(job1, request="first"),
                                 lambda: self.decide(job2, r2, P=other, request="second")])
        successes = [value for kind, value in results if kind == "ok"]
        errors = [value for kind, value in results if kind == "error"]
        self.assertEqual(len(successes), 1, results)
        self.assertEqual(len(errors), 1, results)
        self.assertIsInstance(errors[0], ApiError)
        self.assertEqual(errors[0].code, 409)
        self.assertEqual(learn.active_revision(self.data, self.card["id"]), successes[0]["revision_id"])
        self.assertEqual(len(self.store.q("SELECT * FROM learning_decisions WHERE status='applied'")), 1)

    def test_two_stores_replaying_one_pending_intent_append_one_batch(self):
        other = self.second_store()
        pending = self.pending(self.passed())
        results = self.parallel([lambda: D.project_decision(self.P, self.p, pending["id"]),
                                 lambda: D.project_decision(other, self.p, pending["id"])])
        self.assertTrue(all(kind == "ok" and value["status"] == "applied" for kind, value in results), results)
        markers = [row for row in learn._log(self.data) if row.get("decision_id") == pending["id"]]
        self.assertEqual(len(markers), 1)

    def test_registration_failure_rolls_back_without_any_file_projection(self):
        job = self.passed()
        before = learn.revision_token(self.data, self.card["id"])
        self.store.x("""CREATE TRIGGER fail_intent BEFORE INSERT ON learning_decisions
                        BEGIN SELECT RAISE(ABORT, 'synthetic intent failure'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "intent failure"):
            self.decide(job)
        self.assertFalse(self.store.db.in_transaction)
        self.assertEqual(self.store.q("SELECT * FROM learning_decisions"), [])
        self.assertEqual(learn.revision_token(self.data, self.card["id"]), before)

    def test_pending_intent_is_not_drained_by_reads_and_retries_exactly_once(self):
        job = self.passed()
        pending = self.pending(job)
        L.catalog(self.P, self.p)
        L.detail(self.P, self.p, self.r["id"])
        R.get(self.P, self.p, job["id"])
        self.assertIsNone(learn.projection_receipt(self.data, pending["id"]))
        first = self.decide(job)
        before = learn._log(self.data)
        second = self.decide(job)
        self.assertEqual((first["id"], second["id"]), (pending["id"], pending["id"]))
        self.assertEqual(second["status"], "applied")
        self.assertEqual(learn._log(self.data), before)
        self.assert_conflict(lambda: self.decide(job, action="revoke", expected=self.r["id"]))

    def test_file_success_db_failure_retry_preserves_later_human_retirement(self):
        job = self.passed()
        real = L.transaction
        calls = 0
        @contextmanager
        def fail_ack(store):
            nonlocal calls
            calls += 1
            call = calls
            with real(store) as db:
                yield db
                if call == 2:
                    raise sqlite3.OperationalError("after file before acknowledgement")
        with patch.object(L, "transaction", side_effect=fail_ack):
            with self.assertRaisesRegex(sqlite3.OperationalError, "before acknowledgement"):
                self.decide(job)
        row = self.store.one("SELECT * FROM learning_decisions")
        self.assertEqual(row["status"], "pending")
        self.assertEqual(learn.active_revision(self.data, self.card["id"]), self.r["id"])
        self.assertIsNotNone(learn.projection_receipt(self.data, row["id"]))
        learn.set_status(self.data, self.card["id"], "retired", "bob", "新证据要求停用")
        self.source.write_text("STATUS = 'CLOSED'\n", encoding="utf-8")
        before = learn._log(self.data)
        recovered = self.decide(job)
        self.assertEqual(recovered["status"], "applied")
        self.assertTrue(recovered["result"]["projection"]["replayed"])
        self.assertEqual(learn.lesson(self.data, self.card["id"])["status"], "retired")
        self.assertIsNone(learn.active_revision(self.data, self.card["id"]))
        self.assertEqual(learn._log(self.data), before)

    def test_legacy_edit_after_intent_conflicts_without_overwriting(self):
        job = self.passed()
        pending = self.pending(job)
        learn.edit_lesson(self.data, self.card["id"], {"fix": "人工更正后的步骤"}, "bob")
        before = learn._log(self.data)
        self.assert_conflict(lambda: D.project_decision(self.P, self.p, pending["id"]))
        self.assertEqual(learn._log(self.data), before)
        self.assertEqual(learn.lesson(self.data, self.card["id"])["fix"], "人工更正后的步骤")
        self.assertEqual(self.store.one("SELECT status FROM learning_decisions")["status"], "conflict")

    def test_real_editor_cannot_enter_validated_intent_window_or_be_overwritten(self):
        job = self.passed()
        begin, probed, edited = threading.Event(), threading.Event(), threading.Event()
        probe, errors = [], []
        def editor():
            try:
                if not begin.wait(5):
                    raise AssertionError("decision did not reach its validation barrier")
                acquired = learn._LOCK.acquire(blocking=False)
                if acquired:
                    learn._LOCK.release()
                probe.append(acquired)
                probed.set()
                learn.edit_lesson(self.data, self.card["id"], {"fix": "由另一线程人工修正"}, "bob")
            except BaseException as exc:
                errors.append(exc)
            finally:
                edited.set()
        thread = threading.Thread(target=editor, daemon=True)
        thread.start()
        real_job, real_projection = D._job, D.project_decision
        def checked(*args):
            result = real_job(*args)
            begin.set()
            self.assertTrue(probed.wait(5), "editor did not reach the explicit barrier")
            self.assertEqual(probe, [False], "validation and token capture must hold one ledger lock")
            return result
        def after_intent(*args):
            self.assertTrue(edited.wait(5), "editor remained blocked after the intent transaction")
            return real_projection(*args)
        try:
            with patch.object(D, "_job", side_effect=checked), patch.object(D, "project_decision", side_effect=after_intent):
                self.assert_conflict(lambda: self.decide(job))
        finally:
            begin.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(learn.lesson(self.data, self.card["id"])["fix"], "由另一线程人工修正")
        self.assertIsNone(learn.active_revision(self.data, self.card["id"]))

    def test_reentrant_edit_after_validation_cannot_recapture_a_new_token(self):
        job = self.passed()
        real = D._job
        def edit_at_boundary(*args):
            result = real(*args)
            learn.edit_lesson(self.data, self.card["id"], {"fix": "回调中人工修改的原文"}, "bob")
            return result
        with patch.object(D, "_job", side_effect=edit_at_boundary):
            self.assert_conflict(lambda: self.decide(job))
        self.assertEqual(self.store.q("SELECT * FROM learning_decisions"), [])
        self.assertEqual(learn.lesson(self.data, self.card["id"])["fix"], "回调中人工修改的原文")

    def test_same_intent_replay_is_serialized_across_file_publication_and_db_ack(self):
        other = self.second_store()
        pending = self.pending(self.passed())
        published, release, replay_started = threading.Event(), threading.Event(), threading.Event()
        local = threading.local()
        real_project = learn.project_revision
        results = []
        def publish(*args, **kwargs):
            result = real_project(*args, **kwargs)
            if getattr(local, "role", "") == "first":
                published.set()
                self.assertTrue(release.wait(5), "publication checkpoint was not released")
            return result
        def worker(P, role):
            local.role = role
            try:
                if role == "second":
                    self.assertTrue(published.wait(5), "first worker did not publish")
                    replay_started.set()
                results.append(("ok", D.project_decision(P, self.p, pending["id"])))
            except BaseException as exc:
                results.append(("error", exc))
        threads = [threading.Thread(target=worker, args=(other, "first"), daemon=True),
                   threading.Thread(target=worker, args=(self.P, "second"), daemon=True)]
        with patch.object(learn, "project_revision", side_effect=publish):
            try:
                for thread in threads:
                    thread.start()
                self.assertTrue(published.wait(5), "first worker did not reach durable file checkpoint")
                self.assertTrue(replay_started.wait(5), "second connection did not attempt replay")
                probe = sqlite3.connect(self.store.path, timeout=0)
                try:
                    with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                        probe.execute("BEGIN IMMEDIATE")
                finally:
                    probe.rollback()
                    probe.close()
            finally:
                release.set()
                for thread in threads:
                    thread.join(10)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "projection transaction deadlocked")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(kind == "ok" and value["status"] == "applied" for kind, value in results), results)
        self.assertEqual(self.store.one("SELECT status FROM learning_decisions")["status"], "applied")
        self.assertEqual(learn.active_revision(self.data, self.card["id"]), self.r["id"])
        self.assertEqual(len([row for row in learn._log(self.data) if row.get("decision_id") == pending["id"]]), 1)

    def test_baseline_status_changed_after_evaluation_cannot_be_adopted(self):
        job = self.passed()
        learn.set_status(self.data, self.card["id"], "active", "bob")
        self.assert_conflict(lambda: self.decide(job))
        self.assertEqual(self.store.q("SELECT * FROM learning_decisions"), [])
        self.assertEqual(learn.lesson(self.data, self.card["id"])["status"], "active")
        self.assertIsNone(learn.active_revision(self.data, self.card["id"]))

    def test_stale_lesson_source_has_empty_effective_baseline_but_keeps_ledger_token(self):
        self.decide(self.passed())
        before = E._baseline(self.P, self.p, self.r)
        self.assertEqual(before["revision_id"], self.r["id"])
        self.assertEqual(before["content"], self.r["content"])
        self.source.write_text("STATUS = 'CLOSED'\n", encoding="utf-8")
        after = E._baseline(self.P, self.p, self.r)
        self.assertEqual(after, {"revision_id": None, "content": "", "token": before["token"]})
        self.assertEqual(learn.active_revision(self.data, self.card["id"]), self.r["id"])
        self.assertEqual(D.usable_lessons(self.store, self.p, learn.lessons(self.data, self.p["key"]))[0], [])
        # A fresh source-bound candidate compares against the same empty input
        # that current runs see, not the obsolete adopted card's old guidance.
        item = L._origin(self.P, self.p, "lesson:" + self.card["id"])
        fresh = L.capture(self.P, self.p, item["key"], item["fingerprint"], "writer")
        job = self.start(fresh)
        self.assertEqual(job["options"]["evaluation"]["baseline"], after)
        self.assertTrue(E.current(self.P, self.p, job))
        self.source.write_text("STATUS = 'OPEN'\n", encoding="utf-8")
        self.assertFalse(E.current(self.P, self.p, job))

    def test_revoked_lesson_baseline_is_empty_and_keeps_the_new_human_token(self):
        self.decide(self.passed())
        adopted = E._baseline(self.P, self.p, self.r)
        self.decide(None, action="revoke", expected=self.r["id"], request="revoke")
        paused = E._baseline(self.P, self.p, self.r)
        self.assertEqual(paused["revision_id"], None)
        self.assertEqual(paused["content"], "")
        self.assertEqual(paused["token"], learn.revision_token(self.data, self.card["id"]))
        self.assertNotEqual(paused["token"], adopted["token"])
        # An independent later legacy human activation keeps its existing meaning.
        learn.set_status(self.data, self.card["id"], "active", "bob")
        legacy = E._baseline(self.P, self.p, self.r)
        self.assertIsNone(legacy["revision_id"])
        self.assertEqual(legacy["content"], self.r["content"])

    def test_stale_policy_baseline_uses_runtime_default_and_keeps_expected_pointer(self):
        policy = L.policy_create(self.P, self.p, "source_bound", "预算", {"context_budget": 9000}, "咨询", "writer")
        with patch.object(E, "_pack", side_effect=self.policy_pack):
            self.decide(self.passed(policy), policy, request="policy")
        before = E._baseline(self.P, self.p, policy)
        self.assertEqual(before, {"revision_id": policy["id"], "token": policy["id"], "content": policy["content"]})
        self.store.x("UPDATE projects SET root=? WHERE id=?", (self.other["root"], self.p["id"]))
        current_project = self.store.project(self.p["id"])
        runtime = D.runtime_policy(self.store, current_project)
        self.assertEqual(runtime["status"], "stale")
        self.assertEqual(runtime["context_budget"], 6000)
        baseline = E._baseline(self.P, current_project, policy)
        self.assertEqual(baseline, {"revision_id": None, "token": policy["id"],
                                    "content": L.encoded({"parameters": {"context_budget": 6000}})})
        self.assertEqual(self.store.one("SELECT revision_id FROM learning_policy_active")["revision_id"], policy["id"])

    def test_baseline_body_status_and_token_are_one_locked_snapshot(self):
        learn.set_status(self.data, self.card["id"], "active", "alice")
        old_token = learn.revision_token(self.data, self.card["id"])
        begin, probed, finished = threading.Event(), threading.Event(), threading.Event()
        probe, errors = [], []
        def editor():
            try:
                if not begin.wait(5):
                    raise AssertionError("baseline did not reach its card read")
                acquired = learn._LOCK.acquire(blocking=False)
                if acquired:
                    learn._LOCK.release()
                probe.append(acquired)
                probed.set()
                learn.edit_lesson(self.data, self.card["id"], {"fix": "基线读取后的人工修改"}, "bob")
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()
        real = learn.lesson
        first = True
        def card_snapshot(*args):
            nonlocal first
            result = real(*args)
            if first and threading.current_thread() is threading.main_thread():
                first = False
                begin.set()
                self.assertTrue(probed.wait(5))
                self.assertEqual(probe, [False], "body read must share the status/token ledger lock")
            return result
        thread = threading.Thread(target=editor, daemon=True)
        thread.start()
        try:
            with patch.object(learn, "lesson", side_effect=card_snapshot):
                frozen = E._baseline(self.P, self.p, self.r)
        finally:
            begin.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(finished.is_set())
        self.assertEqual(frozen, {"revision_id": None, "token": old_token, "content": self.r["content"]})
        self.assertNotEqual(learn.revision_token(self.data, self.card["id"]), frozen["token"])

    def test_generation_sample_cannot_be_relabelled_as_new_holdout(self):
        generation = dict(self.cases("used-in-generation")[0], generation=True)
        self.passed(cases=self.cases("fresh") + [generation])
        next_revision = L.propose(self.P, self.p, self.r["id"], L.encoded(dict(self.fields, fix="修订后持久保存幂等键")), "writer")
        before_jobs = self.store.q("SELECT id FROM learning_jobs")
        before_cases = self.store.q("SELECT * FROM learning_eval_cases")
        with self.assertRaises(ApiError) as caught:
            self.start(next_revision, cases=[dict(generation, generation=False)] + self.cases("unused")[:2])
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.store.q("SELECT id FROM learning_jobs"), before_jobs)
        self.assertEqual(self.store.q("SELECT * FROM learning_eval_cases"), before_cases)

    def test_same_revision_cannot_change_frozen_oracle_under_a_new_request_id(self):
        cases = self.cases("frozen-oracle")
        self.passed(cases=cases)
        changed = [dict(c, expected="改成观察到的输出即可通过") for c in cases]
        before = self.store.q("SELECT id FROM learning_jobs")
        with self.assertRaises(ApiError) as caught:
            self.start(cases=changed)
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.store.q("SELECT id FROM learning_jobs"), before)

    def test_policy_name_cannot_reset_holdout_history_for_the_same_runtime_slot(self):
        a = L.policy_create(self.P, self.p, "name_a", "预算甲", {"context_budget": 8000}, "咨询", "writer")
        b = L.policy_create(self.P, self.p, "name_b", "预算乙", {"context_budget": 9000}, "咨询", "writer")
        cases = self.cases("policy-frozen")
        with patch.object(E, "_pack", side_effect=self.policy_pack):
            self.passed(a, cases=cases)
            with self.assertRaises(ApiError) as caught:
                self.start(b, cases=cases)
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(len(self.store.q("SELECT * FROM learning_jobs")), 1)

    def test_source_change_after_intent_blocks_initial_projection(self):
        pending = self.pending(self.passed())
        self.source.write_text("STATUS = 'CLOSED'\n", encoding="utf-8")
        self.assert_conflict(lambda: D.project_decision(self.P, self.p, pending["id"]))
        self.assertIsNone(learn.projection_receipt(self.data, pending["id"]))
        self.assertEqual(learn.lesson(self.data, self.card["id"])["status"], "candidate")

    def test_usage_events_do_not_invalidate_an_evaluated_baseline(self):
        job = self.passed()
        learn._append_log(self.data, [{"kind": "inject", "id": self.card["id"], "ticket": "APP-2", "run_id": 101},
                                     {"kind": "outcome", "id": self.card["id"], "ticket": "APP-2", "outcome": "accepted"}])
        self.assertTrue(E.current(self.P, self.p, job))
        self.assertEqual(self.decide(job)["status"], "applied")

    def test_revoked_card_snapshot_cannot_fall_back_to_legacy_runtime_use(self):
        self.decide(self.passed())
        selected = learn.lessons(self.data, self.p["key"])
        self.assertEqual(selected[0]["active_revision"], self.r["id"])
        self.decide(None, action="revoke", expected=self.r["id"], request="revoke")
        usable, receipts = D.usable_lessons(self.store, self.p, selected)
        self.assertEqual(usable, [], "a revoked new-workflow card must not become legacy fallback")

    def test_changed_source_disables_current_adoption_without_erasing_history(self):
        adopted = self.decide(self.passed())
        cards = learn.lessons(self.data, self.p["key"])
        self.source.write_text("STATUS = 'CLOSED'\n", encoding="utf-8")
        usable, receipts = D.usable_lessons(self.store, self.p, cards)
        self.assertEqual(usable, [])
        self.assertEqual(receipts, [{"kind": "lesson", "origin_id": self.card["id"],
                                    "revision_id": self.r["id"], "included": False}])
        self.assertEqual(learn.projection_receipt(self.data, adopted["id"])["revision_id"], self.r["id"])
        self.assertEqual(self.store.one("SELECT status FROM learning_decisions")["status"], "applied")

    def test_current_legacy_local_and_explicitly_taken_shared_cards_remain_usable(self):
        learn.set_status(self.data, self.card["id"], "active", "alice")
        local = learn.lessons(self.data, self.p["key"])
        usable, receipts = D.usable_lessons(self.store, self.p, local)
        self.assertEqual(usable, local)
        self.assertEqual(receipts, [])
        learn.set_shared(self.data, self.card["id"], True, "alice", "公开经验", {"fix": "公开的处理步骤"})
        learn.take_shared(self.data, self.card["id"], self.other["key"], True, "bob")
        shared = learn.shared(self.data, self.other["key"])
        usable, receipts = D.usable_lessons(self.store, self.other, shared)
        self.assertEqual(usable, shared)
        self.assertEqual(receipts, [])

    def test_new_adoption_needs_separate_share_and_take_without_consumer_confirmation(self):
        self.decide(self.passed())
        learn.set_shared(self.data, self.card["id"], True, "alice", "公开经验", {"fix": "公开的处理步骤"})
        shared = learn.shared(self.data, self.other["key"])
        self.assertEqual(D.usable_lessons(self.store, self.other, shared)[0], [])
        learn.take_shared(self.data, self.card["id"], self.other["key"], True, "bob")
        shared = learn.shared(self.data, self.other["key"])
        usable, receipts = D.usable_lessons(self.store, self.other, shared)
        self.assertEqual(usable, shared)
        self.assertEqual(receipts, [{"kind": "shared_lesson", "origin_id": self.card["id"],
                                    "revision_id": self.r["id"], "included": True,
                                    "consumer_project": self.other["key"], "explicit_take": True,
                                    "shared_ts": shared[0]["shared_ts"],
                                    "shared_fingerprint": L.digest({f: shared[0].get(f) for f in
                                                                   ("title", *learn.FIELDS, "shared_ts")}),
                                    "take": learn.lesson(self.data, self.card["id"])["taken"][self.other["key"]]}])
        self.assertEqual(self.store.q("SELECT * FROM learning_decisions WHERE project_id=?", (self.other["id"],)), [])
        with self.assertRaises(ApiError) as caught:
            L._origin(self.P, self.other, "lesson:" + self.card["id"])
        self.assertEqual(caught.exception.code, 404)
        learn.take_shared(self.data, self.card["id"], self.other["key"], False, "bob")
        self.assertEqual(D.usable_lessons(self.store, self.other, shared)[0], [])

    def test_adopted_shared_card_with_stale_source_is_not_runtime_evidence(self):
        self.decide(self.passed())
        learn.set_shared(self.data, self.card["id"], True, "alice", "公开经验", {"fix": "公开的处理步骤"})
        learn.take_shared(self.data, self.card["id"], self.other["key"], True, "bob")
        shared = learn.shared(self.data, self.other["key"])
        self.source.write_text("STATUS = 'CLOSED'\n", encoding="utf-8")
        self.assertEqual(D.usable_lessons(self.store, self.other, shared)[0], [])

    def test_revoke_and_old_adoption_retry_never_reactivate(self):
        job = self.passed()
        adopted = self.decide(job)
        revoked = self.decide(None, action="revoke", expected=self.r["id"], request="revoke")
        self.assertEqual(revoked["status"], "applied")
        self.assertEqual(learn.lesson(self.data, self.card["id"])["status"], "probation")
        before = learn._log(self.data)
        self.assertEqual(self.decide(job)["id"], adopted["id"])
        self.assertEqual(self.decide(None, action="revoke", expected=self.r["id"], request="revoke")["id"], revoked["id"])
        self.assertEqual(learn._log(self.data), before)
        self.assertIsNone(learn.active_revision(self.data, self.card["id"]))

    def test_pending_revoke_cannot_undo_a_later_legacy_confirmation(self):
        self.decide(self.passed())
        pending = self.pending(None, action="revoke", expected=self.r["id"], request="revoke")
        learn.set_status(self.data, self.card["id"], "active", "bob", "重新核对原经验")
        self.assert_conflict(lambda: D.project_decision(self.P, self.p, pending["id"]))
        self.assertEqual(learn.lesson(self.data, self.card["id"])["status"], "active")
        self.assertIsNone(learn.active_revision(self.data, self.card["id"]))

    def test_policy_candidates_share_one_cas_slot_and_revoke_preserves_new_owner(self):
        other = self.second_store()
        a = L.policy_create(self.P, self.p, "first", "预算甲", {"context_budget": 8000}, "咨询", "writer")
        b = L.policy_create(self.P, self.p, "second", "预算乙", {"context_budget": 9000}, "咨询", "writer")
        with patch.object(E, "_pack", side_effect=self.policy_pack):
            ja, jb = self.passed(a), self.passed(b)
            results = self.parallel([lambda: self.decide(ja, a, request="a"),
                                     lambda: self.decide(jb, b, P=other, request="b")])
            winners = [value for kind, value in results if kind == "ok"]
            losers = [value for kind, value in results if kind == "error"]
            self.assertEqual(len(winners), 1, results)
            self.assertEqual(len(losers), 1, results)
            self.assertIsInstance(losers[0], ApiError)
            self.assertEqual(losers[0].code, 409)
            winner = a if winners[0]["revision_id"] == a["id"] else b
            loser = b if winner is a else a
            self.assertEqual(len(self.store.q("SELECT * FROM learning_policy_active")), 1)
            self.assertEqual(D.runtime_policy(self.store, self.p)["revision_id"], winner["id"])
            # A fresh evaluation is needed once the active baseline has changed.
            replacement = self.passed(loser)
            new = self.decide(replacement, loser, expected=winner["id"], request="replace")
            self.assertEqual(new["status"], "applied")
            self.assert_conflict(lambda: self.decide(None, winner, action="revoke", expected=winner["id"], request="old-revoke"))
            self.assertEqual(D.runtime_policy(self.store, self.p)["revision_id"], loser["id"])


if __name__ == "__main__":
    unittest.main()
