"""Human fact publication: exact bytes, file-side recovery and concurrent CAS."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh import kb
from tmh.platform import learning as L, learning_facts as F
from tmh.platform.errors import ApiError
from tmh.platform.org_knowledge import _pages
from tmh.platform.store import Store


class LearningFactsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name).resolve()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.root = self.data / "repo"
        self.root.mkdir()
        self.p = self.store.add_project("APP", "事实项目", str(self.root))
        self.page = self.root / ".tmh" / "knowledge" / "index.md"
        self.page.parent.mkdir(parents=True)
        self.regpath = self.page.parent / ".pages.json"
        self.evidence = self.root / "src" / "app.js"
        self.evidence.parent.mkdir()
        self.evidence.write_text("export const approved = true;\n", encoding="utf-8")
        self.original = ("---\nid: index\ntitle: 业务系统\nsummary: 说明审批业务\nstatus: 已确认\n"
                         "custom: 原样保留的未知字段\n---\n# 业务系统\n\n" + kb.FACTS_START +
                         "\n固定生成事实。\n" + kb.FACTS_END + "\n\n" +
                         "\n\n".join("## " + title + "\n完整说明，依据 `src/app.js:1`。"
                                      for title in kb.SECTIONS["index"]) + "\n")
        self.page.write_text(self.original, encoding="utf-8")
        kb.save_registry(self.root, {"index": {"status": kb.STATUS_OK, "title": "业务系统", "summary": "说明审批业务",
                                               "confirmed_by": "原确认者", "confirmed_at": "2026-10-20",
                                               "confirm_note": "原始完整说明", "custom": {"keep": [1, 2, 3]}}})
        item = L.catalog(self.P, self.p, "fact")["items"][0]
        self.base = L.capture(self.P, self.p, item["key"], item["fingerprint"], "撰写 Agent")
        self.revision = L.propose(self.P, self.p, self.base["id"], self.original + "\n新增完整业务说明。\n", "撰写 Agent")
        self.token = F.revision_token(self.P, self.p, "index")

    def raw(self):
        return json.loads(self.regpath.read_text(encoding="utf-8"))

    def publish(self, **kwargs):
        args = dict(P=self.P, p=self.p, r=self.revision, actor="人工复核人", decision_id="decision-1",
                    expected_token=self.token, reason="当前 APP 项目完整适用说明")
        args.update(kwargs)
        return F.project_revision(**args)

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob("*") if p.is_file()}

    def break_after_prepare(self):
        original = kb._atomic_text

        def fail(path, text):
            if path == self.page:
                raise OSError("synthetic publication failure")
            return original(path, text)

        with patch.object(kb, "_atomic_text", side_effect=fail):
            with self.assertRaises(OSError):
                self.publish()

    def test_readers_are_pure_and_legacy_confirmation_is_unchanged(self):
        before = self.snapshot()
        self.assertEqual(F.revision_token(self.P, self.p, "index"), self.token)
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        self.assertEqual(kb.load_registry(self.root)["index"]["status"], kb.STATUS_OK)
        self.assertEqual(_pages(self.page.parent)[0]["status"], kb.STATUS_OK)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / ".tmh" / "cache").exists())

    def test_unregistered_or_unreadable_page_has_no_active_revision(self):
        self.regpath.unlink()
        before = self.snapshot()
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        with self.assertRaises(ApiError):
            F.revision_token(self.P, self.p, "index")
        self.assertEqual(self.snapshot(), before)
        self.regpath.write_text("not json", encoding="utf-8")
        before = self.snapshot()
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        self.assertEqual(self.snapshot(), before)

    def test_publication_preserves_full_text_and_binds_confirmation_to_exact_content(self):
        result = self.publish()
        self.assertEqual(result["status"], "applied")
        self.assertEqual(self.page.read_text(encoding="utf-8"), self.revision["content"])
        self.assertIn("custom: 原样保留的未知字段", self.page.read_text(encoding="utf-8"))
        record = self.raw()["index"]
        self.assertEqual(record["status"], kb.STATUS_OK)
        self.assertEqual(record["confirmed_by"], "人工复核人")
        self.assertEqual(record["custom"], {"keep": [1, 2, 3]})
        receipt = record["learning"]["receipts"]["decision-1"]
        self.assertEqual(receipt["before_content"], self.original)
        self.assertEqual(receipt["before_registry"]["confirmed_by"], "原确认者")
        self.assertEqual(receipt["final_content"], self.revision["content"])
        self.assertEqual(receipt["stage"], "applied")
        self.assertEqual(F.active_revision(self.P, self.p, "index"), self.revision["id"])
        self.assertEqual(kb.confirmation_status(record, self.page.read_text(encoding="utf-8")), kb.STATUS_OK)

    def test_applied_retry_is_read_only_and_changed_identity_is_rejected(self):
        result = self.publish()
        before = self.snapshot()
        self.assertEqual(self.publish(), result)
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(ApiError):
            self.publish(reason="改变原决定")
        with self.assertRaises(ApiError):
            self.publish(actor="其他人")
        self.assertEqual(self.snapshot(), before)

    def test_human_gate_and_revision_identity_are_checked_before_writes(self):
        before = self.snapshot()
        for actor in ("agent", "system", "agent:writer", "external:operator", ""):
            with self.subTest(actor=actor), self.assertRaises(ApiError):
                self.publish(actor=actor)
        altered = copy.deepcopy(self.revision)
        altered["content"] += "未登记的内容"
        with self.assertRaises(ApiError):
            self.publish(r=altered)
        self.assertEqual(self.snapshot(), before)

    def test_concurrent_page_or_registry_change_rejects_original_token(self):
        for change in ("body", "registry"):
            with self.subTest(change=change):
                self.page.write_text(self.original, encoding="utf-8")
                reg = self.raw()
                reg["index"].pop("review_note", None)
                self.regpath.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
                if change == "body":
                    self.page.write_text(self.original + "\n人刚刚修改了正文。", encoding="utf-8")
                else:
                    reg["index"]["review_note"] = "人刚刚修改了登记"
                    self.regpath.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
                body, registry = self.page.read_bytes(), self.regpath.read_bytes()
                with self.assertRaises(ApiError):
                    self.publish()
                self.assertEqual(self.page.read_bytes(), body)
                self.assertEqual(self.regpath.read_bytes(), registry)

    def test_invalid_structure_is_rejected_before_prepared_receipt(self):
        invalid = L.propose(self.P, self.p, self.base["id"], self.original.replace("## 技术架构", "## 其他架构"), "writer")
        body, registry = self.page.read_bytes(), self.regpath.read_bytes()
        with self.assertRaises(ApiError) as caught:
            self.publish(r=invalid)
        self.assertIn("技术架构", str(caught.exception))
        self.assertEqual(self.page.read_bytes(), body)
        self.assertEqual(self.regpath.read_bytes(), registry)

    def test_prepared_is_never_confirmed_and_only_explicit_retry_recovers(self):
        self.break_after_prepare()
        self.assertEqual(self.page.read_text(encoding="utf-8"), self.original)
        self.assertEqual(self.raw()["index"]["learning"]["pending"], "decision-1")
        before = self.snapshot()
        self.assertEqual(kb.load_registry(self.root)["index"]["status"], kb.STATUS_DRAFT)
        self.assertEqual(_pages(self.page.parent)[0]["status"], kb.STATUS_DRAFT)
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        F.revision_token(self.P, self.p, "index")
        self.assertEqual(self.snapshot(), before)
        self.publish()
        self.assertEqual(F.active_revision(self.P, self.p, "index"), self.revision["id"])

    def test_legacy_human_confirmation_cannot_cover_an_unfinished_projection(self):
        self.break_after_prepare()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "恢复原人工决定"):
            kb.confirm(self.root, "index", "其他人工", "不能代替恢复")
        self.assertEqual(self.snapshot(), before)

    def test_new_legacy_human_confirmation_has_its_own_hash_and_clears_old_machine_adoption(self):
        self.publish()
        updated = self.revision["content"] + "\n人工新补充的完整业务说明。\n"
        self.page.write_text(updated, encoding="utf-8")
        note = "完整人工说明。" * 300
        with patch.object(kb.activity, "log"):
            kb.confirm(self.root, "index", "下一位人工", note)
        record = self.raw()["index"]
        self.assertEqual(record["status"], kb.STATUS_OK)
        self.assertEqual(record["confirmed_by"], "下一位人工")
        self.assertEqual(record["confirm_note"], note)
        self.assertEqual(record["learning"]["active_revision"], "")
        self.assertEqual(kb.load_registry(self.root)["index"]["status"], kb.STATUS_OK)
        self.assertEqual(_pages(self.page.parent)[0]["status"], kb.STATUS_OK)
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        history = record["learning"]["manual_confirmations"][-1]
        self.assertEqual(history["confirmed_content"], updated)
        self.assertEqual(history["note"], note)
        self.assertEqual(history["previous_active_revision"], self.revision["id"])
        self.assertEqual(record["learning"]["receipts"]["decision-1"]["final_content"], self.revision["content"])
        before = self.snapshot()
        self.assertEqual(self.publish()["status"], "applied")
        self.assertEqual(self.snapshot(), before)

    def test_crash_after_final_page_before_registry_is_pending_and_resumable(self):
        save = kb.save_registry

        def fail_final(root, reg, **kwargs):
            receipt = reg.get("index", {}).get("learning", {}).get("receipts", {}).get("decision-1", {})
            if receipt.get("stage") == "applied":
                raise OSError("synthetic final registry failure")
            return save(root, reg, **kwargs)

        with patch.object(kb, "save_registry", side_effect=fail_final):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(self.page.read_text(encoding="utf-8"), self.revision["content"])
        self.assertEqual(kb.load_registry(self.root)["index"]["status"], kb.STATUS_DRAFT)
        self.assertEqual(_pages(self.page.parent)[0]["status"], kb.STATUS_DRAFT)
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        self.publish()
        self.assertEqual(self.raw()["index"]["status"], kb.STATUS_OK)

    def test_atomic_replace_failure_never_falls_back_to_overwriting_page(self):
        replace = kb.os.replace

        def fail(source, target):
            if Path(target) == self.page:
                raise PermissionError("synthetic file busy")
            return replace(source, target)

        with patch.object(kb.os, "replace", side_effect=fail):
            with self.assertRaises(PermissionError):
                self.publish()
        self.assertEqual(self.page.read_text(encoding="utf-8"), self.original)
        self.assertEqual(kb.load_registry(self.root)["index"]["status"], kb.STATUS_DRAFT)
        self.assertEqual(list(self.page.parent.glob(".*.tmp")), [])

    def test_pending_retry_never_overwrites_newer_body_or_registry(self):
        self.break_after_prepare()
        self.page.write_text(self.original + "\n发布后有人新增的完整说明。", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(ApiError):
            self.publish()
        self.assertEqual(self.snapshot(), before)
        self.page.write_text(self.original, encoding="utf-8")
        reg = self.raw()
        reg["index"]["note"] = "更新后的登记不能被覆盖"
        self.regpath.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(ApiError):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_pending_retry_rechecks_all_evidence_and_workspace_binding(self):
        self.break_after_prepare()
        self.evidence.write_text("export const approved = false;\n", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(ApiError):
            self.publish()
        self.assertEqual(self.snapshot(), before)
        self.evidence.write_text("export const approved = true;\n", encoding="utf-8")
        with patch.object(L.library, "bindings", return_value=[{"revision": "changed"}]):
            with self.assertRaises(ApiError):
                self.publish()
        self.assertEqual(self.raw()["index"]["learning"]["pending"], "decision-1")

    def test_sources_changed_after_final_page_cannot_commit_confirmation(self):
        real = F._sources_current
        calls = 0

        def changing(*args):
            nonlocal calls
            calls += 1
            if calls == 3:
                self.evidence.write_text("export const changed = true;\n", encoding="utf-8")
            return real(*args)

        with patch.object(F, "_sources_current", side_effect=changing):
            with self.assertRaises(ApiError):
                self.publish()
        self.assertEqual(calls, 3)
        self.assertEqual(kb.load_registry(self.root)["index"]["status"], kb.STATUS_DRAFT)
        self.assertEqual(_pages(self.page.parent)[0]["status"], kb.STATUS_DRAFT)

    def test_post_publication_content_change_and_newline_change_invalidate_confirmation(self):
        self.publish()
        self.page.write_text(self.revision["content"] + "\n未确认的新内容。", encoding="utf-8")
        before = self.snapshot()
        self.assertEqual(kb.load_registry(self.root)["index"]["status"], "需更新")
        self.assertEqual(_pages(self.page.parent)[0]["status"], "需更新")
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        self.assertEqual(self.publish()["status"], "applied")
        self.assertEqual(self.snapshot(), before)
        self.page.write_bytes(self.revision["content"].replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(kb.load_registry(self.root)["index"]["status"], "需更新")
        self.assertEqual(_pages(self.page.parent)[0]["status"], "需更新")

    def test_revoke_keeps_current_body_and_receipts_and_old_adopt_cannot_republish(self):
        self.publish()
        token = F.revision_token(self.P, self.p, "index")
        result = F.revoke_revision(self.P, self.p, self.revision, "人工复核人", "revoke-1", token, "当前范围暂停使用")
        self.assertEqual(result["action"], "revoke")
        self.assertIn("新增完整业务说明。", self.page.read_text(encoding="utf-8"))
        self.assertIn("status: 待确认", self.page.read_text(encoding="utf-8"))
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        self.assertEqual(set(self.raw()["index"]["learning"]["receipts"]), {"decision-1", "revoke-1"})
        before = self.snapshot()
        self.assertEqual(F.revoke_revision(self.P, self.p, self.revision, "人工复核人", "revoke-1", token, "当前范围暂停使用"), result)
        self.assertEqual(self.publish()["status"], "applied")
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        self.assertEqual(self.snapshot(), before)

    def test_stale_sources_preserve_human_pointer_for_revocation_without_revalidation(self):
        self.publish()
        self.evidence.write_text("changed evidence\n", encoding="utf-8")
        with patch.object(L.library, "bindings", return_value=[{"revision": "changed"}]):
            self.assertFalse(L.revision_current(self.P, self.p, self.revision))
            self.assertEqual(F.active_revision(self.P, self.p, "index"), self.revision["id"])
            token = F.revision_token(self.P, self.p, "index")
            result = F.revoke_revision(self.P, self.p, self.revision, "人工复核人", "revoke-stale", token, "来源过期，停用此版本")
        self.assertEqual(result["status"], "applied")
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        self.assertIn("新增完整业务说明。", self.page.read_text(encoding="utf-8"))
        self.assertEqual(kb.load_registry(self.root)["index"]["status"], kb.STATUS_DRAFT)

    def test_applied_replay_audits_history_even_after_page_removal_or_invalid_edit(self):
        result = self.publish()
        for content in ("current page is being rewritten", None):
            with self.subTest(content=content):
                if content is None:
                    self.page.unlink()
                else:
                    self.page.write_text(content, encoding="utf-8")
                before = self.snapshot()
                with patch.object(L.library, "bindings", return_value=[{"revision": "changed"}]):
                    self.assertEqual(self.publish(), result)
                self.assertEqual(self.snapshot(), before)
                self.assertIsNone(F.active_revision(self.P, self.p, "index"))

    def test_applied_replay_rejects_corrupt_receipt_without_republishing(self):
        self.publish()
        reg = self.raw()
        reg["index"]["learning"]["receipts"]["decision-1"]["result"]["content_sha256"] = "forged"
        self.regpath.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        before = self.snapshot()
        with self.assertRaisesRegex(ApiError, "回执不完整"):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_managed_confirmation_without_a_content_hash_is_never_treated_as_confirmed(self):
        self.publish()
        reg = self.raw()
        for state in ({}, None, {"confirmed_sha256": ""}, {"receipts": []}):
            with self.subTest(state=state):
                reg["index"]["learning"] = state
                self.regpath.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
                before = self.snapshot()
                self.assertNotEqual(kb.load_registry(self.root)["index"]["status"], kb.STATUS_OK)
                self.assertNotEqual(_pages(self.page.parent)[0]["status"], kb.STATUS_OK)
                self.assertIsNone(F.active_revision(self.P, self.p, "index"))
                self.assertEqual(self.snapshot(), before)

    def test_two_concurrent_decisions_have_one_winner_without_deadlock(self):
        another = L.propose(self.P, self.p, self.base["id"], self.original + "\n另一条完整修订。\n", "writer")
        start = threading.Barrier(3)
        outcomes = []

        def run(revision, decision):
            start.wait(timeout=5)
            try:
                outcomes.append(("ok", self.publish(r=revision, decision_id=decision)))
            except ApiError as error:
                outcomes.append(("conflict", error.code))
            except Exception as error:
                outcomes.append(("unexpected", repr(error)))

        threads = [threading.Thread(target=run, args=(self.revision, "decision-1")),
                   threading.Thread(target=run, args=(another, "decision-2"))]
        for thread in threads:
            thread.start()
        start.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "fact projection deadlocked")
        self.assertEqual(sorted(x[0] for x in outcomes), ["conflict", "ok"], outcomes)
        winner = next(value for kind, value in outcomes if kind == "ok")
        self.assertEqual(F.active_revision(self.P, self.p, "index"), winner["revision_id"])
        self.assertEqual(len(self.raw()["index"]["learning"]["receipts"]), 1)

    def test_projection_preserves_callers_database_transaction(self):
        class Rollback(Exception):
            pass

        with self.assertRaises(Rollback):
            with L.transaction(self.store) as db:
                db.execute("UPDATE projects SET description=? WHERE id=?", ("not committed", self.p["id"]))
                self.publish()
                self.assertTrue(db.in_transaction, "file source checks committed the outer transaction")
                self.assertEqual(self.store.project("APP")["description"], "not committed")
                raise Rollback()
        self.assertEqual(self.store.project("APP")["description"], "")
        # A failed database commit must leave a durable exact file receipt to replay.
        before = self.snapshot()
        self.assertEqual(self.publish()["status"], "applied")
        self.assertEqual(self.snapshot(), before)

    def abandon(self, **kwargs):
        args = dict(P=self.P, p=self.p, r=self.revision, actor="人工复核人", decision_id="decision-1",
                    expected_token=F.revision_token(self.P, self.p, "index"), reason="保留当前现场，重新核对来源")
        args.update(kwargs)
        return F.abandon(**args)

    def test_abandon_preserves_changed_body_and_history_and_remains_unconfirmed(self):
        self.break_after_prepare()
        updated = self.original + "\n发布期间人工新增的完整说明。\n"
        self.page.write_text(updated, encoding="utf-8")
        self.evidence.write_text("new evidence requiring a new capture\n", encoding="utf-8")
        reg = self.raw()
        reg["index"]["note"] = "现场登记也完整保留"
        self.regpath.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        page_before = self.page.read_bytes(), self.page.stat().st_mtime_ns
        token = F.revision_token(self.P, self.p, "index")
        result = self.abandon(expected_token=token)
        self.assertEqual(result["status"], "abandoned")
        self.assertIn("不代表确认", result["message"])
        self.assertEqual((self.page.read_bytes(), self.page.stat().st_mtime_ns), page_before)
        record = self.raw()["index"]
        self.assertEqual(record["note"], "现场登记也完整保留")
        self.assertEqual(record["status"], kb.STATUS_DRAFT)
        self.assertEqual(record["learning"]["pending"], "")
        self.assertEqual(record["learning"]["active_revision"], "")
        receipt = record["learning"]["receipts"]["decision-1"]
        self.assertEqual(receipt["stage"], "abandoned")
        self.assertEqual(receipt["before_content"], self.original)
        self.assertEqual(receipt["final_content"], self.revision["content"])
        self.assertEqual(receipt["abandonment"]["content"], updated)
        self.assertEqual(receipt["abandonment"]["before_registry"]["note"], "现场登记也完整保留")
        before = self.snapshot()
        self.assertEqual(self.abandon(expected_token=token), result)
        self.assertIsNone(F.active_revision(self.P, self.p, "index"))
        self.assertEqual(kb.load_registry(self.root)["index"]["status"], kb.STATUS_DRAFT)
        self.assertEqual(_pages(self.page.parent)[0]["status"], kb.STATUS_DRAFT)
        with self.assertRaisesRegex(ApiError, "已放弃"):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_abandon_requires_current_cas_identity_and_the_same_pending_decision(self):
        self.break_after_prepare()
        before = self.snapshot()
        for args in ({"expected_token": self.token}, {"decision_id": "other-decision"},
                     {"actor": "agent"}, {"reason": ""}, {"r": dict(self.revision, content="forged")}):
            with self.subTest(args=args), self.assertRaises(ApiError):
                self.abandon(**args)
            self.assertEqual(self.snapshot(), before)
        token = F.revision_token(self.P, self.p, "index")
        self.abandon(expected_token=token)
        before = self.snapshot()
        for args in ({"actor": "另一位人工"}, {"reason": "改写原放弃说明"}):
            with self.subTest(args=args), self.assertRaises(ApiError):
                self.abandon(expected_token=token, **args)
        self.assertEqual(self.snapshot(), before)

    def test_successfully_applied_publication_cannot_be_abandoned(self):
        self.publish()
        before = self.snapshot()
        with self.assertRaisesRegex(ApiError, "改走撤销"):
            self.abandon()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(F.active_revision(self.P, self.p, "index"), self.revision["id"])

    def test_new_publication_after_abandon_is_not_blocked_or_overwritten_by_old_retry(self):
        self.break_after_prepare()
        abandoned_token = F.revision_token(self.P, self.p, "index")
        self.abandon(expected_token=abandoned_token)
        item = L.catalog(self.P, self.p, "fact")["items"][0]
        new_revision = L.capture(self.P, self.p, item["key"], item["fingerprint"], "writer")
        token = F.revision_token(self.P, self.p, "index")
        self.publish(r=new_revision, decision_id="decision-2", expected_token=token)
        self.assertEqual(F.active_revision(self.P, self.p, "index"), new_revision["id"])
        before = self.snapshot()
        with self.assertRaises(ApiError):
            self.abandon(expected_token=abandoned_token)
        with self.assertRaises(ApiError):
            self.publish()
        self.assertEqual(self.snapshot(), before)
        receipts = self.raw()["index"]["learning"]["receipts"]
        self.assertEqual(receipts["decision-1"]["stage"], "abandoned")
        self.assertEqual(receipts["decision-2"]["stage"], "applied")

    def test_concurrent_pending_retry_and_abandon_only_apply_one_decision(self):
        self.break_after_prepare()
        token = F.revision_token(self.P, self.p, "index")
        start = threading.Barrier(3)
        outcomes = []

        def run(action):
            start.wait(timeout=5)
            try:
                result = self.publish() if action == "retry" else self.abandon(expected_token=token)
                outcomes.append((action, result["status"]))
            except ApiError:
                outcomes.append((action, "conflict"))
            except Exception as error:
                outcomes.append((action, repr(error)))

        threads = [threading.Thread(target=run, args=(action,)) for action in ("retry", "abandon")]
        for thread in threads:
            thread.start()
        start.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "retry/abandon lock order deadlocked")
        self.assertEqual(sum(status == "conflict" for _, status in outcomes), 1, outcomes)
        stage = self.raw()["index"]["learning"]["receipts"]["decision-1"]["stage"]
        self.assertIn(stage, ("applied", "abandoned"))
        self.assertEqual(F.active_revision(self.P, self.p, "index"), self.revision["id"] if stage == "applied" else None)


if __name__ == "__main__":
    unittest.main()
