"""Actual ordinary prompt receipts, withdrawal and process input evidence."""
import copy
from contextlib import contextmanager
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmh.platform import agents, learn, lesson_context
from tmh.platform.store import Store


class LessonRuntimeReceiptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name).resolve()
        self.root = self.data / "project"
        self.root.mkdir()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.p = self.store.add_project("APP", "组织知识", str(self.root))
        self.ticket = self.store.create_ticket(self.p["id"], "核对项目说明", "alice", auto=False)
        agents.reset_context_meta()
        self.addCleanup(agents.reset_context_meta)

    def card(self, project="APP"):
        return learn.add_lesson(self.data, {"project": project, "status": "active",
            "title": "核对项目说明", "symptom": "核对项目说明", "fix": "核对项目说明，读取事务记录",
            "verify": "核对项目说明", "applicability": "只在事务提交后适用",
            "non_applicability": "不适用于尚未提交的事务"})

    def built(self):
        agents.reset_context_meta()
        with patch.object(agents, "knowledge", return_value="NO_EXTRA_CONTEXT"):
            prompt = agents.build_prompt(self.store, self.p, self.ticket, "analyze")
        metas = agents.take_context_meta()
        return prompt, metas

    def saved(self, prompt, metas):
        run = self.store.create_run(self.p["id"], self.ticket["id"], "fake", "analyze", "alice", prompt)
        self.store.update_run(run["id"], status="done", result="FROZEN_CONCLUSION", exit_code=0)
        agents._record_context(self.store, self.data, run["id"], metas)
        agents.record_session_context(self.data, run["id"])
        (self.data / "runs" / str(run["id"]) / "session.txt").write_text("session-1")
        return self.store.run(run["id"])

    def valid(self, run):
        return agents.learning_context_current(self.store, self.data, self.p, run)

    @unittest.skipUnless(os.name == "posix", "人工经验决定在 Windows 明确拒绝写入")
    def test_actual_prompt_keeps_complete_conditions_and_frozen_block(self):
        card = self.card()
        text = "核对项目说明 " + "完整长正文" * 150 + "\r\n结尾  "
        learn.human_decision(self.data, "APP", card["id"], "alice", "edit",
                             learn.revision_token(self.data, card["id"]), "long-edit", fields={"fix": text})
        prompt, metas = self.built()
        meta = next(m for m in metas if m["mode"] == "learning_lessons")
        self.assertIn("block", meta)
        block = meta["block"]
        self.assertIn(block["text"], prompt)
        payload = block["payloads"][0]
        self.assertEqual(payload["content"]["fix"], text)
        self.assertEqual(payload["content"]["applicability"], card["applicability"])
        self.assertEqual(payload["content"]["non_applicability"], card["non_applicability"])
        self.assertEqual(block["rendered_sha256"], hashlib.sha256(block["text"].encode()).hexdigest())
        self.assertTrue(self.valid(self.saved(prompt, metas)))

    @unittest.skipUnless(os.name == "posix", "人工经验决定在 Windows 明确拒绝写入")
    def test_manual_retire_invalidates_actual_cli_ancestor_and_copied_conclusion(self):
        card = self.card()
        prompt, metas = self.built()
        self.assertIn(card["id"], prompt)
        run = self.saved(prompt, metas)
        self.assertTrue(self.valid(run))
        learn.human_decision(self.data, "APP", card["id"], "alice", "retire",
                             learn.revision_token(self.data, card["id"]), "retire", reason="停止旧经验")
        self.assertFalse(self.valid(run))
        self.assertEqual(agents.earlier_session(self.store, self.data, self.ticket, "fake", "plan"), ("", None))
        with patch.object(agents, "knowledge", return_value="NO_EXTRA_CONTEXT"):
            self.assertNotIn("FROZEN_CONCLUSION", agents.build_prompt(self.store, self.p, self.ticket, "ask"))

    def test_public_same_second_take_aba_expires_but_unrelated_consumer_does_not(self):
        card = self.card("REF")
        with patch.object(learn, "now", return_value="2026-10-24T00:00:00"):
            learn.set_shared(self.data, card["id"], True, "owner", title="核对项目说明", fields={"fix": "核对项目说明"})
            learn.take_shared(self.data, card["id"], "APP", True, "alice")
            prompt, metas = self.built()
            self.assertIn(card["id"], prompt)
            run = self.saved(prompt, metas)
            self.assertTrue(self.valid(run))
            learn.take_shared(self.data, card["id"], "OTHER", True, "bob")
            self.assertTrue(self.valid(run))
            learn.take_shared(self.data, card["id"], "APP", False, "alice")
            learn.take_shared(self.data, card["id"], "APP", True, "alice")
            self.assertFalse(self.valid(run))

    def test_usage_change_does_not_rewrite_or_expire_frozen_block(self):
        card = self.card()
        prompt, metas = self.built()
        run = self.saved(prompt, metas)
        before = (self.data / "runs" / str(run["id"]) / "context.json").read_bytes()
        with learn.ledger_lock(self.data):
            learn._append_log(self.data, [{"kind": "outcome", "id": card["id"], "ticket": "APP-99", "passed": True}])
        self.assertTrue(self.valid(run))
        self.assertEqual(before, (self.data / "runs" / str(run["id"]) / "context.json").read_bytes())

    def test_frozen_public_card_is_rechecked_without_new_discovery_window(self):
        card = self.card("REF")
        learn.set_shared(self.data, card["id"], True, "owner", title="核对项目说明", fields={"fix": "核对项目说明"})
        learn.take_shared(self.data, card["id"], "APP", True, "alice")
        prompt, metas = self.built()
        run = self.saved(prompt, metas)
        self.assertTrue(self.valid(run))
        # Discovery may no longer include this old card; its own published
        # content and consumer authorization have not changed.
        with patch.object(learn, "shared", return_value=[]):
            self.assertTrue(self.valid(run))
            learn.take_shared(self.data, card["id"], "APP", False, "alice")
            self.assertFalse(self.valid(run))

    def test_wrong_block_renderer_and_corrupt_payload_are_not_reusable(self):
        self.card()
        prompt, metas = self.built()
        for key, value in (("renderer_version", "unknown"), ("rendered_sha256", "0" * 64), ("payloads", [])):
            altered = copy.deepcopy(metas)
            meta = next(m for m in altered if m["mode"] == "learning_lessons")
            meta.setdefault("block", {})[key] = value
            with self.subTest(key=key):
                self.assertFalse(self.valid(self.saved(prompt, altered)))

    def test_missing_receipt_is_not_legacy_after_unmanaged_local_history(self):
        self.card()
        run = self.store.create_run(self.p["id"], self.ticket["id"], "fake", "analyze", "alice", "old")
        self.store.update_run(run["id"], status="done", result="old")
        self.assertFalse(self.valid(self.store.run(run["id"])))

    def test_policy_sidecar_does_not_disguise_missing_old_lesson_receipt(self):
        self.card()
        prompt, metas = self.built()
        without_lessons = [m for m in metas if m["mode"] != "learning_lessons"]
        self.assertTrue(any(m["mode"] == "learning_policy" for m in without_lessons))
        self.assertFalse(self.valid(self.saved(prompt, without_lessons)))

    def test_missing_ledger_lease_is_not_recreated_by_currentness_read(self):
        self.card()
        prompt, metas = self.built()
        run = self.saved(prompt, metas)
        lock = self.data / "lessons.lock"
        self.assertTrue(lock.is_file())
        lock.unlink()
        self.assertFalse(self.valid(run))
        self.assertFalse(lock.exists())

    def test_lease_removed_between_path_check_and_acquisition_is_rejected(self):
        self.card()
        _, metas = self.built()
        block = next(m["block"] for m in metas if m["mode"] == "learning_lessons")
        lock = self.data / "lessons.lock"
        original = learn.ledger_lock
        removed = False

        @contextmanager
        def interrupted(data, *args, **kwargs):
            nonlocal removed
            if not removed:
                removed = True
                lock.unlink()
            with original(data, *args, **kwargs):
                yield

        with patch.object(learn, "ledger_lock", interrupted):
            self.assertFalse(lesson_context.current(self.store, self.p, block))
        self.assertTrue(removed)
        self.assertFalse(lock.exists())

    @unittest.skipUnless(os.name == "posix", "验证持有文件描述符期间替换锁路径")
    def test_replaced_lease_after_last_card_read_is_not_current(self):
        self.card()
        _, metas = self.built()
        block = next(m["block"] for m in metas if m["mode"] == "learning_lessons")
        lock = self.data / "lessons.lock"
        old_identity = (lock.stat().st_dev, lock.stat().st_ino)
        original = lesson_context.D.usable_lessons

        def replaced(*args, **kwargs):
            result = original(*args, **kwargs)
            lock.rename(self.data / "previous.lock")
            lock.touch()
            return result

        with patch.object(lesson_context.D, "usable_lessons", replaced):
            self.assertFalse(lesson_context.current(self.store, self.p, block))
        self.assertNotEqual((lock.stat().st_dev, lock.stat().st_ino), old_identity)
        # Once the previous lease is released, an unchanged ledger protected by
        # the new real lease is valid; replacement is not permanent revocation.
        self.assertTrue(lesson_context.current(self.store, self.p, block))

    @unittest.skipUnless(os.name == "posix", "验证重入锁持有旧文件描述符时的身份")
    def test_reentrant_old_lease_cannot_validate_replacement_path(self):
        self.card()
        _, metas = self.built()
        block = next(m["block"] for m in metas if m["mode"] == "learning_lessons")
        lock = self.data / "lessons.lock"
        with self.store.lock, learn.ledger_lock(self.data, create=False):
            self.assertTrue(lesson_context.current(self.store, self.p, block))
            lock.rename(self.data / "previous.lock")
            lock.touch()
            self.assertFalse(lesson_context.current(self.store, self.p, block))
        self.assertTrue(lesson_context.current(self.store, self.p, block))

    def test_context_write_failure_is_visible_before_execution(self):
        self.card()
        prompt, metas = self.built()
        run = self.store.create_run(self.p["id"], self.ticket["id"], "fake", "analyze", "alice", prompt)
        # A directory at the exact target is a real I/O failure for direct or atomic writes.
        target = self.data / "runs" / str(run["id"]) / "context.json"
        target.mkdir(parents=True)
        with self.assertRaises(OSError):
            agents._record_context(self.store, self.data, run["id"], metas)

    def test_runner_records_failed_preparation_without_starting_after_receipt_failure(self):
        self.card()
        (self.data / "agents.json").write_text(json.dumps({"fake": {"cmd": ["synthetic"]}}))
        runner = agents.Runner(self.store, self.data)
        with patch.object(agents, "_record_context", side_effect=OSError("full disk")), \
                patch.object(agents.threading, "Thread") as thread, \
                patch.object(agents, "knowledge", return_value="NO_EXTRA_CONTEXT"):
            run = runner.start(self.p, self.ticket, "fake", "analyze", "alice")
        thread.assert_not_called()
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["exit_code"], 1)
        self.assertIn("full disk", run["result"])
        self.assertNotIn(run["id"], runner.controls)

    @unittest.skipUnless(os.name == "posix", "人工经验决定在 Windows 明确拒绝写入")
    def test_result_after_mid_invocation_retirement_is_not_current_success(self):
        card = self.card()
        conf = {"fake": {"cmd": ["synthetic"], "timeout": 5}}
        (self.data / "agents.json").write_text(json.dumps(conf))
        runner = agents.Runner(self.store, self.data)
        with patch.object(agents.threading, "Thread"), patch.object(agents, "knowledge", return_value="NO_EXTRA_CONTEXT"):
            run = runner.start(self.p, self.ticket, "fake", "analyze", "alice")
        def invoke(*args, **kwargs):
            learn.human_decision(self.data, "APP", card["id"], "alice", "retire",
                                 learn.revision_token(self.data, card["id"]), "mid-call-retire", reason="停止")
            return 0, "COMPLETE_ORIGINAL_RESULT"
        with patch.object(runner, "invoke", side_effect=invoke):
            runner._go(run["id"], self.p, self.ticket, "fake", "analyze", run["prompt"], conf)
        result = self.store.run(run["id"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("COMPLETE_ORIGINAL_RESULT", result["result"])

    @unittest.skipUnless(os.name == "posix", "独立进程监管需要 POSIX")
    def test_actual_process_attempt_records_exact_utf8_prompt_hash(self):
        runner = agents.Runner(self.store, self.data)
        run = self.store.create_run(self.p["id"], None, "fake", "ask", "alice", "")
        prompt = "实际输入\r\n完整尾文  "
        result, folder = runner.run_command(run["id"], [sys.executable, "-c", "print('synthetic')"],
                                            self.root, timeout=5, prompt=prompt)
        self.assertEqual(result.returncode, 0)
        record = json.loads((folder / "process.json").read_text())
        self.assertEqual((folder / "prompt.md").read_bytes(), prompt.encode())
        self.assertEqual(record.get("prompt_sha256"), hashlib.sha256(prompt.encode()).hexdigest())
        self.assertEqual(record.get("prompt_utf8_bytes"), len(prompt.encode()))

    @unittest.skipUnless(os.name == "posix", "人工经验决定与独立进程监管需要 POSIX")
    def test_real_runner_argv_preserves_literal_workdir_inside_rule(self):
        card = self.card()
        text = "核对项目说明，保留字面 {workdir}；" + "完整条件" * 130 + "\r\n结尾  "
        learn.human_decision(self.data, "APP", card["id"], "alice", "edit",
                             learn.revision_token(self.data, card["id"]), "placeholder", fields={"fix": text})
        received = self.data / "received-prompt.bin"
        conf = {"fake": {"cmd": [sys.executable, "-c",
            "import pathlib,sys;pathlib.Path(sys.argv[1]).write_bytes(sys.argv[2].encode());print('synthetic done')",
            str(received), "{prompt}"], "timeout": 5}}
        (self.data / "agents.json").write_text(json.dumps(conf))
        runner = agents.Runner(self.store, self.data)
        with patch.object(agents.threading, "Thread"), patch.object(agents, "knowledge", return_value="NO_EXTRA_CONTEXT"):
            run = runner.start(self.p, self.ticket, "fake", "analyze", "alice")
        metas = json.loads((self.data / "runs" / str(run["id"]) / "context.json").read_text())
        block = next(m["block"] for m in metas if m["mode"] == "learning_lessons")
        self.assertEqual(block["payloads"][0]["content"]["fix"], text)
        runner._go(run["id"], self.p, self.ticket, "fake", "analyze", run["prompt"], conf)
        self.assertEqual(self.store.run(run["id"])["status"], "done", self.store.run(run["id"])["result"])
        raw = received.read_bytes()
        self.assertIn(block["text"].encode(), raw)
        self.assertIn(b"{workdir}", raw)
        folder = self.data / "runs" / str(run["id"]) / "attempts/0001"
        record = json.loads((folder / "process.json").read_text())
        self.assertEqual((folder / "prompt.md").read_bytes(), raw)
        self.assertEqual(record["prompt_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(record["prompt_transport"], ["argv"])
        self.assertEqual(record["prompt_scope"], "runner_attempt_prompt")


if __name__ == "__main__":
    unittest.main()
