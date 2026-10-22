"""Actual publication/source checks at prompt injection, using synthetic retrieval.

Retrieval ranking is covered by test_context_pack. Here the real page renderer,
registry, revision store, projection and prompt builder verify exact use receipts.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh import kb, context_pack as cp
from tmh.graph import graph_path
from tmh.platform import agents, learning as L, learning_facts as F, learning_decisions as D, learning_eval as E, server
from tmh.platform.store import Store


class LearningContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name).resolve()
        self.root = self.data / "project"
        self.root.mkdir()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.p = self.store.add_project("APP", "知识上下文", str(self.root))
        self.page = self.root / ".tmh/knowledge/index.md"
        self.page.parent.mkdir(parents=True)
        self.source = self.root / "app.py"
        self.source.write_text("OPEN = True\n", encoding="utf-8")
        text = ("---\nid: index\ntitle: 项目说明\nsummary: 当前项目事实\nstatus: 待确认\n---\n# 项目说明\n\n" +
                kb.FACTS_START + "\n固定生成事实\n" + kb.FACTS_END + "\n\n" +
                "\n\n".join("## " + title + "\n基于 `app.py:1` 的完整说明。" for title in kb.SECTIONS["index"]))
        self.page.write_text(text, encoding="utf-8")
        kb.save_registry(self.root, {"index": {"title": "项目说明", "status": kb.STATUS_DRAFT,
                                               "summary": "UNIQUE_VERIFIED_FACT"}})
        graph_path(self.root).parent.mkdir(exist_ok=True)
        graph_path(self.root).write_text("synthetic retrieval graph")
        item = L._origin(self.P, self.p, "fact:index")
        self.r = L.capture(self.P, self.p, item["key"], item["fingerprint"], "writer")
        F.project_revision(self.P, self.p, self.r, "alice", "first", F.revision_token(self.P, self.p, "index"), "人工检查")
        agents.reset_context_meta()
        self.addCleanup(agents.reset_context_meta)

    def pack(self, *_args, **_kwargs):
        item = cp._page_item(self.root, kb.load_registry(self.root), "index", 1.0)
        item["id"] = "APP:" + item["id"]
        item["source"] = "APP"
        return {"schema": 2, "query": "项目说明", "budget": 6000, "used": 0, "complete": True,
                "items": [item], "omissions": [], "omissions_capped": 0,
                "sections": {"pages": {"count": 1, "bytes": len(cp._render_item(item)) + 1}},
                "sources": [cp._source({"root": str(self.root), "label": "APP", "current": True}, 0)]}

    def prompt(self, collect=None):
        with patch.object(cp, "assemble", side_effect=collect or self.pack):
            return agents.knowledge(self.root, "项目说明", store=self.store, project=self.p)

    def receipt(self):
        return agents.take_context_meta()[-1]

    def test_exact_adopted_fact_is_injected_and_actual_receipt_is_persisted(self):
        text = self.prompt()
        self.assertIn("UNIQUE_VERIFIED_FACT", text)
        m = self.receipt()
        self.assertEqual(m["used"], len(text))
        self.assertTrue(m["complete"])
        self.assertEqual(m["learning_revisions"][0]["revision_id"], self.r["id"])
        self.assertTrue(m["learning_revisions"][0]["included"])
        run = self.store.create_run(self.p["id"], None, "reader", "ask", "test", "")
        agents._record_context(self.store, self.data, run["id"], agents.take_context_meta())
        saved = json.loads((self.data / "runs" / str(run["id"]) / "context.json").read_text())
        self.assertEqual(saved, agents.take_context_meta())

    def test_changed_source_is_excluded_but_keeps_human_pointer_and_full_handle(self):
        self.source.write_text("OPEN = False\n", encoding="utf-8")
        self.assertEqual(F.active_revision(self.P, self.p, "index"), self.r["id"])
        self.assertFalse(D.adopted_current(self.P, self.p, self.r))
        text = self.prompt()
        self.assertNotIn("UNIQUE_VERIFIED_FACT", text)
        self.assertIn("tmh kb read index", text)
        self.assertFalse(self.receipt()["complete"])
        self.assertFalse(self.receipt()["learning_revisions"][0]["included"])
        self.assertEqual(self.receipt()["omission_records"][0]["full_text"], "tmh kb read index")
        detail = L.detail(self.P, self.p, self.r["id"])
        self.assertEqual(detail["active_revision_id"], self.r["id"])
        self.assertFalse(detail["current"])

    def test_page_changes_after_retrieval_cannot_receive_old_revision_receipt(self):
        def collect(*args, **kwargs):
            pack = self.pack()
            self.page.write_text(self.page.read_text() + "\n后来改变的完整正文")
            return pack
        self.assertNotIn("UNIQUE_VERIFIED_FACT", self.prompt(collect))
        self.assertFalse(self.receipt()["learning_revisions"][0]["included"])

    def test_revoke_between_retrieval_and_use_cannot_fall_back_to_legacy(self):
        def collect(*args, **kwargs):
            pack = self.pack()
            F.revoke_revision(self.P, self.p, self.r, "alice", "revoke", F.revision_token(self.P, self.p, "index"), "停止使用")
            return pack
        with patch("tmh.context.build_context", return_value="UNSAFE_LEGACY") as legacy:
            text = self.prompt(collect)
        legacy.assert_not_called()
        self.assertNotIn("UNIQUE_VERIFIED_FACT", text)
        self.assertNotIn("UNSAFE_LEGACY", text)
        self.assertEqual(self.receipt()["mode"], "context_unavailable")

    def test_retrieval_failure_is_explicit_even_with_legacy_switch(self):
        with patch.dict("os.environ", {"TMH_CONTEXT_PACK": "0"}), \
                patch.object(cp, "assemble", side_effect=ValueError("broken registry")), \
                patch("tmh.context.build_context") as legacy:
            text = agents.knowledge(self.root, "说明", store=self.store, project=self.p)
        self.assertIn("本次未注入", text)
        legacy.assert_not_called()
        self.assertIn("broken registry", self.receipt()["error"])

    def test_removed_management_record_before_lock_is_not_legacy(self):
        original = kb._Lock.__enter__
        def enter(lock):
            registry = json.loads(kb._reg_path(self.root).read_text())
            registry["index"].pop("learning")
            kb.save_registry(self.root, registry)
            return original(lock)
        with patch.object(kb._Lock, "__enter__", enter):
            text = self.prompt()
        self.assertNotIn("UNIQUE_VERIFIED_FACT", text)
        self.assertEqual(self.receipt()["mode"], "context_unavailable")

    def test_ticket_context_preview_enforces_the_same_adoption_boundary(self):
        ticket = self.store.create_ticket(self.p["id"], "项目说明", "test", auto=False)
        self.P.ticket = self.store.ticket
        self.P.root = lambda p: Path(p["root"])
        self.source.write_text("OPEN = False\n", encoding="utf-8")
        with patch.object(cp, "assemble", side_effect=self.pack):
            response = server.api_ticket_context(self.P, None, ticket["key"])
        self.assertNotIn("UNIQUE_VERIFIED_FACT", response["text"])
        self.assertFalse(self.receipt()["learning_revisions"][0]["included"])

    def test_policy_freezes_the_same_filtered_text_as_ordinary_prompt(self):
        for changed in (False, True):
            with self.subTest(source_changed=changed):
                if changed:
                    self.source.write_text("OPEN = False\n", encoding="utf-8")
                text = self.prompt()
                receipts_before = agents.take_context_meta()
                with patch.object(cp, "assemble", side_effect=self.pack):
                    frozen = E._pack(self.P, self.p, "项目说明", 6000)
                self.assertEqual(frozen["text"], text)
                self.assertEqual(frozen["receipt"]["learning_revisions"], self.receipt()["learning_revisions"])
                self.assertEqual(frozen["receipt"]["sections"]["pages"]["count"], 0 if changed else 1)
                self.assertEqual(frozen["receipt"]["sections"]["pages"]["bytes"],
                                 sum(len(cp._render_item(item)) + 1 for item in frozen["receipt"]["items"]))
                self.assertEqual(agents.take_context_meta(), receipts_before)

    def test_new_legacy_human_confirmation_is_not_reported_as_old_adoption(self):
        self.page.write_text(self.page.read_text() + "\n人重新核对后的说明")
        kb.confirm(self.root, "index", "bob", "对当前完整正文重新确认")
        self.assertIn("UNIQUE_VERIFIED_FACT", self.prompt())
        receipt = self.receipt()["learning_revisions"][0]
        self.assertIsNone(receipt["revision_id"] or None)
        self.assertTrue(receipt["included"])
        self.assertEqual(receipt["reason"], "manual_confirmation")

    def test_render_budget_keeps_full_omission_receipt_without_splitting_items(self):
        pack = self.pack()
        pack["budget"] = 750
        pack["omissions"] = [dict(id="source:item" + str(i), section="pages", title="完整标题" * 40,
                                  reason="budget", full_text="tmh kb read full" + str(i), source="APP") for i in range(20)]
        pack["complete"] = False
        revisions = [{"item_id": pack["items"][0]["id"], "included": True}]
        text = agents._render_prompt_pack(pack, revisions)
        self.assertEqual(pack["used"], len(text))
        self.assertLessEqual(len(text), pack["budget"])
        self.assertGreaterEqual(len(pack["omissions"]), 20)
        self.assertEqual(pack["omissions"][19]["full_text"], "tmh kb read full19")
        self.assertIn("未列出", text)


if __name__ == "__main__":
    unittest.main()
