"""Revoked learning cannot return through CLI memory, old conclusions or retries."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tmh import kb, context_pack as cp
from tmh.platform import agents, fixloop, learn, learning as L, learning_decisions as D, learning_facts as F
from tmh.platform.store import Store


class LearningSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name).resolve()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.root = self.data / "project"
        self.root.mkdir()
        self.source = self.root / "app.py"
        self.source.write_text("OPEN = True\n", encoding="utf-8")
        self.p = self.store.add_project("APP", "学习会话", str(self.root))
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.ticket = self.store.create_ticket(self.p["id"], "核对项目说明", "alice", auto=False)
        agents.reset_context_meta()
        self.addCleanup(agents.reset_context_meta)

    def fact(self):
        self.page = self.root / ".tmh/knowledge/index.md"
        self.page.parent.mkdir(parents=True)
        text = ("---\nid: index\ntitle: 项目说明\nsummary: 项目事实\nstatus: 待确认\n---\n# 项目说明\n\n" +
                kb.FACTS_START + "\n固定生成事实\n" + kb.FACTS_END + "\n\n" +
                "\n\n".join("## " + title + "\n完整说明依据 `app.py:1`。" for title in kb.SECTIONS["index"]))
        self.page.write_text(text, encoding="utf-8")
        kb.save_registry(self.root, {"index": {"status": kb.STATUS_DRAFT, "title": "项目说明"}})
        item = L._origin(self.P, self.p, "fact:index")
        revision = L.capture(self.P, self.p, item["key"], item["fingerprint"], "writer")
        F.project_revision(self.P, self.p, revision, "alice", "adopt-fact", F.revision_token(self.P, self.p, "index"), "当前项目适用")
        self.assertTrue(D.adopted_current(self.P, self.p, revision))
        receipt = {"kind": "fact", "origin_id": "index", "revision_id": revision["id"], "included": True, "reason": "active"}
        return revision, {"mode": "context_pack", "learning_revisions": [receipt]}

    def revoke_fact(self, revision):
        F.revoke_revision(self.P, self.p, revision, "alice", "revoke-fact", F.revision_token(self.P, self.p, "index"), "停止沿用旧事实")

    def lesson(self, owner=None):
        owner = owner or self.p
        card = learn.add_lesson(self.data, {"project": owner["key"], "status": "candidate", "title": "事务经验",
            "symptom": "刷新后记录消失", "cause": "尚未提交", "fix": "提交后刷新", "verify": "重读结果", "anti": "不能只看响应"})
        item = L._origin(self.P, owner, "lesson:" + card["id"])
        revision = L.capture(self.P, owner, item["key"], item["fingerprint"], "writer")
        learn.project_revision(self.data, owner["key"], card["id"], revision["id"], json.loads(revision["content"]),
                               "alice", "adopt-" + card["id"], learn.revision_token(self.data, card["id"]),
                               content_schema=revision["source"].get("lesson_content_schema", ""))
        return revision

    def local_lesson_meta(self, revision):
        cards, receipts = D.usable_lessons(self.store, self.p, [learn.lesson(self.data, revision["origin_id"])])
        self.assertEqual(len(cards), 1)
        from tmh.platform import lesson_context
        with self.store.lock, learn.ledger_lock(self.data):
            block = lesson_context.freeze(self.store, self.p, cards)
        return {"mode": "learning_lessons", "revisions": receipts, "block": block}

    def shared_lesson(self):
        root = self.data / "reference"
        root.mkdir()
        owner = self.store.add_project("REF", "参考项目", str(root))
        revision = self.lesson(owner)
        learn.set_shared(self.data, revision["origin_id"], True, "owner", title="通用事务经验", fields={"fix": "提交后刷新"})
        learn.take_shared(self.data, revision["origin_id"], self.p["key"], True, "consumer")
        cards, receipts = D.usable_lessons(self.store, self.p, learn.shared(self.data, self.p["key"]))
        self.assertEqual(len(cards), 1)
        from tmh.platform import lesson_context
        with self.store.lock, learn.ledger_lock(self.data):
            block = lesson_context.freeze(self.store, self.p, cards)
        return revision, {"mode": "learning_lessons", "revisions": receipts, "block": block}

    def saved_run(self, *metas, mode="analyze", parent=None, status="done", result="OLD_CONCLUSION", recorded=True):
        run = self.store.create_run(self.p["id"], self.ticket["id"], "fake", mode, "alice", "frozen")
        self.store.update_run(run["id"], status=status, exit_code=0, result=result, ended="2026-10-22T12:00:00")
        directory = self.data / "runs" / str(run["id"])
        directory.mkdir(parents=True)
        if recorded:
            policy = {"mode": "learning_policy", **D.runtime_policy(self.store, self.p)}
            (directory / "context.json").write_text(json.dumps([policy, *metas], ensure_ascii=False), encoding="utf-8")
            agents.record_session_context(self.data, run["id"], parent)
        (directory / "session.txt").write_text("session-" + str(run["id"]), encoding="utf-8")
        return self.store.run(run["id"])

    def valid(self, run):
        return agents.learning_context_current(self.store, self.data, self.p, run, running=run["status"] == "running")

    def resumed(self, mode="plan"):
        return agents.earlier_session(self.store, self.data, self.ticket, "fake", mode)[0]

    def test_current_fact_can_resume_but_revoke_removes_session_and_old_conclusion(self):
        revision, meta = self.fact()
        run = self.saved_run(meta)
        self.assertEqual(self.resumed(), "session-" + str(run["id"]))
        with patch.object(agents, "knowledge", return_value="CURRENT_CONTEXT"):
            self.assertIn("OLD_CONCLUSION", agents.build_prompt(self.store, self.p, self.ticket, "ask"))
        self.revoke_fact(revision)
        self.assertEqual(self.resumed(), "")
        with patch.object(agents, "knowledge", return_value="CURRENT_CONTEXT"):
            self.assertNotIn("OLD_CONCLUSION", agents.build_prompt(self.store, self.p, self.ticket, "ask"))

    def test_source_and_page_changes_each_invalidate_the_exact_fact(self):
        _, meta = self.fact()
        run = self.saved_run(meta)
        self.assertTrue(self.valid(run))
        self.source.write_text("OPEN = False\n", encoding="utf-8")
        self.assertFalse(self.valid(run))
        self.source.write_text("OPEN = True\n", encoding="utf-8")
        self.assertTrue(self.valid(run))
        self.page.write_text(self.page.read_text(encoding="utf-8") + "\n未经确认的新正文", encoding="utf-8")
        self.assertFalse(self.valid(run))

    def test_local_lesson_revoke_starts_new_session(self):
        revision = self.lesson()
        run = self.saved_run(self.local_lesson_meta(revision))
        self.assertTrue(self.resumed())
        learn.revoke_revision(self.data, self.p["key"], revision["origin_id"], revision["id"], "alice", "revoke-lesson",
                              learn.revision_token(self.data, revision["origin_id"]), "不再适用")
        self.assertFalse(self.valid(run))
        self.assertEqual(self.resumed(), "")

    def test_withdrawing_cross_project_take_invalidates_old_memory(self):
        revision, meta = self.shared_lesson()
        run = self.saved_run(meta)
        self.assertTrue(self.valid(run))
        learn.take_shared(self.data, revision["origin_id"], self.p["key"], False, "consumer")
        self.assertFalse(self.valid(run))
        self.assertEqual(self.resumed(), "")

    def test_shared_copy_and_take_receipt_are_bound_even_with_same_revision(self):
        revision, meta = self.shared_lesson()
        run = self.saved_run(meta)
        learn.set_shared(self.data, revision["origin_id"], True, "owner", title="另一共享正文", fields={"fix": "先核对再提交"})
        learn.take_shared(self.data, revision["origin_id"], self.p["key"], True, "different-consumer")
        self.assertEqual(learn.active_revision(self.data, revision["origin_id"]), revision["id"])
        self.assertFalse(self.valid(run))

    def test_policy_change_does_not_reuse_the_old_policy_session(self):
        run = self.saved_run()
        self.assertTrue(self.valid(run))
        revision = L.policy_create(self.P, self.p, "longer", "更长上下文", {"context_budget": 8000}, "大型模块", "writer")
        self.store.x("INSERT INTO learning_policy_active VALUES(?,?,?)", (self.p["id"], revision["id"], "synthetic-human-decision"))
        self.assertEqual(D.runtime_policy(self.store, self.p)["context_budget"], 8000)
        self.assertEqual(self.resumed(), "")
        active = self.saved_run()
        self.assertTrue(self.valid(active))
        self.store.x("DELETE FROM learning_policy_active WHERE project_id=?", (self.p["id"],))
        self.assertFalse(self.valid(active))

    def test_new_receipt_does_not_erase_a_resumed_ancestors_knowledge(self):
        revision, meta = self.fact()
        analysis = self.saved_run(meta)
        plan = self.saved_run(mode="plan", parent=analysis["id"])
        self.assertTrue(self.valid(plan))
        self.revoke_fact(revision)
        self.assertFalse(self.valid(plan))
        self.assertEqual(self.resumed("fix"), "")

    def test_copied_conclusion_is_an_ancestor_even_without_cli_resume(self):
        revision, meta = self.fact()
        analysis = self.saved_run(meta, result="FACT_DERIVED_ANALYSIS")
        agents.reset_context_meta()
        with patch.object(agents, "knowledge", return_value="NO_NEW_FACTS"):
            prompt = agents.build_prompt(self.store, self.p, self.ticket, "plan")
        self.assertIn("FACT_DERIVED_ANALYSIS", prompt)
        metas = agents.take_context_meta()
        self.assertIn({"mode": "learning_prior", "run_id": analysis["id"]}, metas)
        plan = self.saved_run(*metas, mode="plan", result="INDIRECT_PLAN")
        self.assertTrue(self.valid(plan))
        self.revoke_fact(revision)
        self.assertFalse(self.valid(plan))
        with patch.object(agents, "knowledge", return_value="NO_NEW_FACTS"):
            self.assertNotIn("INDIRECT_PLAN", agents.build_prompt(self.store, self.p, self.ticket, "ask"))

    def test_old_unreceipted_session_is_kept_only_before_learning_history(self):
        run = self.saved_run(recorded=False)
        self.assertTrue(self.valid(run))
        revision, _ = self.fact()
        self.assertFalse(self.valid(run))
        self.revoke_fact(revision)
        self.assertFalse(self.valid(run), "revocation must not make unknown historical memory safe")

    def test_unknown_memory_does_not_become_safe_after_shared_take_withdrawal(self):
        old = self.saved_run(recorded=False)
        revision, _ = self.shared_lesson()
        self.assertFalse(self.valid(old))
        learn.take_shared(self.data, revision["origin_id"], self.p["key"], False, "consumer")
        self.assertFalse(self.valid(old))

    def test_later_manual_confirmation_is_checked_as_its_own_exact_content(self):
        _, meta = self.fact()
        kb.confirm(self.root, "index", "alice", "人工重新核对完整正文")
        receipt = meta["learning_revisions"][0]
        receipt.update(revision_id=None, reason="manual_confirmation")
        meta.update(knowledge_revision=cp._knowledge_revision(self.root), source_version=cp._git_head(self.root))
        run = self.saved_run(meta)
        self.assertTrue(self.valid(run))
        self.page.write_text(self.page.read_text(encoding="utf-8") + "\n人工确认之后的新内容", encoding="utf-8")
        self.assertFalse(self.valid(run))

    def test_latest_invalid_step_does_not_fall_back_to_an_older_session(self):
        old = self.saved_run()
        revision, meta = self.fact()
        self.saved_run(meta)
        self.revoke_fact(revision)
        self.assertTrue(self.valid(old))
        self.assertEqual(self.resumed(), "")

    def test_excluded_receipt_does_not_claim_hidden_knowledge_was_injected(self):
        revision, meta = self.fact()
        meta["learning_revisions"][0]["included"] = False
        run = self.saved_run(meta)
        self.revoke_fact(revision)
        self.assertTrue(self.valid(run))

    def test_changed_receipt_or_foreign_ticket_parent_is_not_trusted(self):
        _, meta = self.fact()
        run = self.saved_run(meta)
        path = self.data / "runs" / str(run["id"]) / "context.json"
        path.write_text("[]", encoding="utf-8")
        self.assertFalse(self.valid(run))
        other = self.store.create_ticket(self.p["id"], "另一工单", "alice", auto=False)
        self.store.update_run(run["id"], ticket_id=other["id"])
        child = self.saved_run(mode="plan", parent=run["id"])
        self.assertFalse(self.valid(child))

    def fake_loop(self, run):
        runner = SimpleNamespace(store=self.store, data_dir=self.data, invoke=Mock(return_value=(0, "done")))
        loop = object.__new__(fixloop.FixLoop)
        loop.r, loop.st, loop.rid = runner, self.store, run["id"]
        loop.p, loop.t, loop.agent, loop.conf = self.p, self.ticket, "fake", {"fake": {"cmd": ["synthetic"]}}
        loop.wt, loop.prompt, loop.models = self.root, "frozen\n" + agents.MODE_TEXT["fix"], {"fix": "", "edit": ""}
        loop.n, loop.sid, loop.ok, loop.failed_call, loop.nobuild, loop.notes = 0, "", False, False, "", {}
        return loop

    def test_fix_loop_keeps_parent_receipt_and_stops_after_revoke(self):
        revision, meta = self.fact()
        parent = self.saved_run(meta, mode="plan")
        run = self.saved_run(mode="fix", status="running")
        loop = self.fake_loop(run)
        def invoke(*args):
            n = loop.n
            (self.data / "runs" / str(run["id"]) / ("session-%d.txt" % n)).write_text("continued", encoding="utf-8")
            return 0, "fix complete"
        loop.r.invoke.side_effect = invoke
        loop.whole(None)
        self.assertEqual(loop.r.invoke.call_args.args[-2], "session-" + str(parent["id"]))
        manifest = json.loads((self.data / "runs" / str(run["id"]) / "session-context.json").read_text())
        self.assertEqual(manifest["parent_run_id"], parent["id"])
        self.assertEqual(loop.sid, "continued")
        self.revoke_fact(revision)
        with self.assertRaisesRegex(ValueError, "重新启动任务"):
            loop.whole(None)
        self.assertEqual(loop.r.invoke.call_count, 1, "a new CLI session must not resend the stale frozen prompt")

    def test_extra_fix_context_keeps_both_old_and_new_receipts(self):
        revision, meta = self.fact()
        run = self.saved_run(mode="fix", status="running")
        loop = self.fake_loop(run)
        def knowledge(*args, **kwargs):
            agents._CTX_META.meta.append(meta)
            return "NEWLY_INJECTED_FACT"
        with patch.object(agents, "knowledge", side_effect=knowledge):
            self.assertIn("NEWLY_INJECTED_FACT", loop.context())
        saved = json.loads((self.data / "runs" / str(run["id"]) / "context.json").read_text())
        self.assertIn(meta, saved)
        self.assertTrue(self.valid(run))
        self.revoke_fact(revision)
        with self.assertRaisesRegex(ValueError, "重新启动任务"):
            loop.call("edit", loop.context())
        loop.r.invoke.assert_not_called()

    def test_busy_retry_checks_learning_again_after_the_wait(self):
        revision, meta = self.fact()
        run = self.saved_run(meta, status="running")
        runner = agents.Runner(self.store, self.data)
        parser = SimpleNamespace(session="busy-session")
        timing = agents.Timing().done()
        timing["busy"] = True
        def pause(*args):
            self.revoke_fact(revision)
            return True
        with patch.object(runner, "_spawn", return_value=(1, "busy", parser, timing)) as spawn, \
                patch.object(runner, "_pause", side_effect=pause):
            with self.assertRaisesRegex(ValueError, "重试已停止"):
                runner.invoke(run["id"], self.p, self.ticket, "fake", {"fake": {"cmd": ["synthetic"]}},
                              "analyze", "FROZEN_FACT_PROMPT", self.root)
        self.assertEqual(spawn.call_count, 1)

    def test_queued_run_with_stale_frozen_prompt_never_invokes_a_model(self):
        revision, meta = self.fact()
        run = self.saved_run(meta, status="queued")
        self.revoke_fact(revision)
        runner = agents.Runner(self.store, self.data)
        with patch.object(runner, "invoke") as invoke:
            runner._go(run["id"], self.p, self.ticket, "fake", "analyze", "FROZEN_FACT_PROMPT",
                       {"fake": {"cmd": ["synthetic"]}})
        invoke.assert_not_called()
        failed = self.store.run(run["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertIn("重新启动任务", failed["result"])

    def test_lost_session_fallback_does_not_resend_stale_full_prompt(self):
        revision, meta = self.fact()
        run = self.saved_run(meta, status="running")
        runner = agents.Runner(self.store, self.data)
        def lost(*args):
            self.revoke_fact(revision)
            return 1, "", SimpleNamespace(session=""), agents.Timing().done()
        with patch.object(runner, "_spawn", side_effect=lost) as spawn:
            with self.assertRaisesRegex(ValueError, "重新启动任务"):
                runner.invoke(run["id"], self.p, self.ticket, "fake", {"fake": {"cmd": ["synthetic", "{resume}"]}},
                              "analyze", "SHORT", self.root, resume="old", fresh="FROZEN_FACT_PROMPT")
        self.assertEqual(spawn.call_count, 1)


if __name__ == "__main__":
    unittest.main()
