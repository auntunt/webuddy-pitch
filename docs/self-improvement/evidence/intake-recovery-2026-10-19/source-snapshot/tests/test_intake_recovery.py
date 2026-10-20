"""Customer answers survive failed re-reading and recover without reopening contracts.

The executor is an explicit synthetic in-process fixture: it calls the real
Runner lifecycle methods but never starts a model, process, or HTTP service.
"""
import copy
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh.platform import intake, signoff
from tmh.platform.agents import Runner
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


class IntakeRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="webuddy-intake-recovery-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("REC", "合成恢复夹具", str(self.data))
        self.runner = Runner(self.store, self.data)
        self.flow = SimpleNamespace(resume=mock.Mock(), submit=mock.Mock(), autoflow=lambda: {"on": self.on}, agent=lambda: "reader")
        self.on = False
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, runner=self.runner, flow=self.flow,
                                 project=self.store.project, root=lambda project: Path(project["root"]))
        (self.data / "autoflow.json").write_text(json.dumps({"on": False, "understand": "agent", "understand_agent": "reader"}))
        (self.data / "agents.json").write_text(json.dumps({"reader": {"cmd": [sys.executable, "-c", "raise AssertionError('must not execute')"]}}))
        self.spawn = mock.patch.object(intake, "_spawn")
        self.spawn_mock = self.spawn.start()
        self.addCleanup(self.spawn.stop)
        self.outcome = "timeout"
        self.calls = []
        self.invoke = mock.patch.object(self.runner, "invoke", side_effect=self.synthetic_reader)
        self.invoke.start()
        self.addCleanup(self.invoke.stop)

    def reading(self, answer=None, twist=False):
        item = {"title": "保存后列表可见", "quote": "保存后列表看不到记录", "kind": "缺陷",
                "restated": "我理解的是：保存后列表应出现记录", "flow": "新模块", "said": {},
                "questions": [{"q": "保存后应该多久可见？", "blocks": ["A1"]}],
                "ac": [{"id": "A1", "text": "保存后应在【待确认：多久】看到记录", "check": "保存一条记录并检查列表"},
                       {"id": "A2", "text": "旧记录内容保持不变", "check": "核对旧记录原文"}], "keep": ["权限范围保持不变"]}
        if answer:
            item["questions"] = []
            item["ac"][0]["text"] = "保存后应在%s看到记录" % answer
        if twist:
            item["title"] = "模型试图改标题"
            item["ac"][1].update(text="旧记录全部删除", check="无法核对")
        return "```tmh-intake\n" + json.dumps({"title": "保存后可见", "items": [item]}, ensure_ascii=False) + "\n```"

    def synthetic_reader(self, rid, project, ticket, name, conf, mode, prompt, cwd, model):
        self.calls.append(rid)
        self.runner._control(rid, conf, name)
        if self.outcome == "cancelled":
            self.runner.cancel(rid, "synthetic-canceller")
            return 0, self.reading("马上")
        if self.outcome == "timeout":
            self.runner._stopped(rid, "timeout")
            return 124, "synthetic timeout; full diagnostic retained"
        if self.outcome == "invalid":
            return 0, "synthetic unreadable result"
        return 0, self.reading("马上", twist=True)

    def conversation(self, answer="马上"):
        s = intake.start(self.P, self.project, "保存后列表看不到记录", "工程师", agent=False)
        s["items"] = intake._agent_items(self.P, self.project, s, intake.parse(self.reading()))
        s["understood"] = {"by": "智能体", "agent": "reader"}
        intake._plan(s)
        intake._save(self.data, s)
        s = intake.confirm(self.P, s["id"], "工程师")
        key = s["tickets"][0]
        link = intake.ask_client(self.P, s["id"], "工程师", tell=False)
        intake.client_answer(self.P, link["token"], {"0": {"q1": answer}}, name="王总")
        return s["id"], key, link

    def complete_job(self, sid):
        s = intake.load(self.data, sid, self.P)
        job = s["understanding_job"]["id"]
        intake._understand(self.P, self.project, sid, job, "reader")
        return intake.load(self.data, sid, self.P)

    def failed(self):
        sid, key, link = self.conversation()
        s = self.complete_job(sid)
        self.assertEqual(s["state"], "confirmed")
        self.assertEqual(s["items"][0]["questions"], [])
        self.assertTrue(s["items"][0]["ac"][0]["open"])
        self.assertEqual(self.store.ticket(key)["links"]["open_ac"], 1)
        return sid, key, link

    def test_timeout_preserves_answer_and_exposes_a_bound_read_only_recovery(self):
        sid, key, link = self.failed()
        before = {p: p.read_bytes() for p in self.data.rglob("*") if p.is_file()}
        state = intake.recovery_state(self.P, key)
        self.assertTrue(state["can_retry"], state)
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["session"], sid)
        self.assertEqual(state["run"], self.calls[-1])
        self.assertEqual(state["items"][0]["answers"][0]["value"], "马上")
        self.assertEqual(state["items"][0]["answers"][0]["from"], "王总（客户）")
        self.assertEqual(before, {p: p.read_bytes() for p in self.data.rglob("*") if p.is_file()})
        page = intake.client_page(self.P, link["token"], done=True)
        self.assertIn("再理解", page)
        self.assertIn("无需重复回答", page)
        self.assertIn("href='/ask/%s'" % link["token"], page)
        self.assertIn("刷新处理状态", page)
        self.assertNotIn("<form", page)

    def test_retry_success_keeps_confirmed_contract_and_customer_source(self):
        sid, key, _ = self.failed()
        original = copy.deepcopy(signoff.client_ac(self.data, key))
        state = intake.retry_understanding(self.P, key, "恢复操作员")
        self.assertEqual(state["status"], "running")
        self.assertEqual(intake.load(self.data, sid, self.P)["state"], "confirmed")
        self.outcome = "success"
        s = self.complete_job(sid)
        final = signoff.client_ac(self.data, key)
        self.assertIn("马上", final[0]["text"])
        self.assertFalse(final[0]["open"])
        self.assertEqual(final[1:], original[1:])
        self.assertEqual(s["items"][0]["title"], "保存后列表可见")
        self.assertNotIn("open_ac", self.store.ticket(key)["links"])
        self.assertEqual(signoff.records(self.data, key)[-1]["by"], "王总（客户）")
        self.assertEqual(intake.recovery_state(self.P, key)["status"], "resolved")
        self.assertNotIn("understanding_recovery", s)
        self.assertTrue(s["understanding_recovery_history"])
        self.flow.resume.assert_not_called()
        with self.assertRaises(ApiError):
            intake.retry_understanding(self.P, key, "再次点击")

    def test_repeated_failure_and_cancel_remain_retryable_with_history(self):
        sid, key, _ = self.failed()
        for outcome in ("invalid", "cancelled", "timeout"):
            intake.retry_understanding(self.P, key, "工程师")
            self.outcome = outcome
            self.complete_job(sid)
            state = intake.recovery_state(self.P, key)
            self.assertTrue(state["can_retry"], state)
            self.assertEqual(state["status"], "failed")
            self.assertTrue(self.store.ticket(key)["links"]["open_ac"])
        self.assertEqual(len(state["attempts"]), 4)
        self.assertEqual(len(set(self.calls)), 4)

    def test_concurrent_retry_starts_one_job_and_old_completion_cannot_execute(self):
        sid, key, _ = self.failed()
        old_job = intake.recovery_state(self.P, key)["job"]
        self.spawn_mock.reset_mock()
        barrier = threading.Barrier(3)
        results = []
        def retry():
            barrier.wait()
            try:
                results.append(intake.retry_understanding(self.P, key, "工程师")["status"])
            except ApiError as error:
                results.append(error.code)
        threads = [threading.Thread(target=retry) for _ in range(2)]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join(3)
        self.assertEqual(sorted(map(str, results)), ["409", "running"])
        self.assertEqual(self.spawn_mock.call_count, 1)
        before = len(self.calls)
        intake._understand(self.P, self.project, sid, old_job, "reader")
        self.assertEqual(len(self.calls), before)
        self.assertEqual(intake.recovery_state(self.P, key)["status"], "running")

    def test_running_recovery_blocks_old_session_actions(self):
        sid, key, link = self.failed()
        intake.retry_understanding(self.P, key, "工程师")
        for operation in (lambda: intake.answer(self.P, sid, "工程师", {"0": {"q1": "第二天"}}),
                          lambda: intake.ask_client(self.P, sid, "工程师", tell=False)):
            with self.assertRaises(ApiError) as raised:
                operation()
            self.assertEqual(raised.exception.code, 409)
        self.assertIn("正在", intake.client_page(self.P, link["token"], done=True))

    def test_unknown_answers_and_unverified_cleanup_do_not_become_executable(self):
        sid, key, _ = self.conversation(answer="不清楚")
        self.assertTrue(self.store.ticket(key)["links"]["open_ac"])
        self.assertFalse(intake.recovery_state(self.P, key)["can_retry"])
        sid, key, _ = self.failed()
        state = intake.recovery_state(self.P, key)
        receipt = self.data / "runs" / str(state["run"]) / "lifecycle.json"
        receipt.unlink()
        self.assertFalse(intake.recovery_state(self.P, key)["can_retry"])
        with self.assertRaises(ApiError):
            intake.retry_understanding(self.P, key, "工程师")

    def test_takeover_dependency_closed_and_global_off_survive_recovery(self):
        for blocker in ("hold", "handwork", "later", "closed", "off"):
            with self.subTest(blocker=blocker):
                sid, key, _ = self.failed()
                self.on = blocker != "off"
                t = self.store.ticket(key)
                if blocker == "closed":
                    self.store.update_ticket(t["id"], "工程师", status="closed")
                    with self.assertRaises(ApiError):
                        intake.retry_understanding(self.P, key, "工程师")
                    continue
                if blocker != "off":
                    self.store.update_ticket(t["id"], "工程师", links=dict(t["links"], **{blocker: "existing owner"}))
                self.flow.resume.reset_mock()
                intake.retry_understanding(self.P, key, "工程师")
                self.outcome = "success"
                self.complete_job(sid)
                self.flow.resume.assert_not_called()
                if blocker != "off": self.assertEqual(self.store.ticket(key)["links"][blocker], "existing owner")
                self.outcome = "timeout"

    def test_legacy_failure_is_recovered_only_with_original_answers_and_finished_run(self):
        sid, key, _ = self.failed()
        s = intake.load(self.data, sid, self.P)
        s.pop("understanding_recovery", None)
        intake._save(self.data, s)
        state = intake.recovery_state(self.P, key)
        self.assertTrue(state["can_retry"], state)
        intake.retry_understanding(self.P, key, "工程师")
        self.outcome = "success"
        self.complete_job(sid)
        self.assertFalse(self.store.ticket(key)["links"].get("open_ac"))

    def test_changed_answer_or_contract_requires_explicit_review(self):
        sid, key, _ = self.failed()
        s = intake.load(self.data, sid, self.P)
        s["items"][0]["slots"]["q1"]["value"] = "另一个未经绑定的答案"
        intake._save(self.data, s)
        state = intake.recovery_state(self.P, key)
        self.assertFalse(state["can_retry"])
        self.assertTrue(state["blocked"])

    def test_unavailable_reader_keeps_unspawned_attempt_distinct_from_initial_run(self):
        initial = self.store.create_run(self.project["id"], None, "reader", "understand", "初始受理人", "synthetic", "初次理解")
        self.store.update_run(initial["id"], status="done", exit_code=0)
        original_save = intake._save
        def keep_initial_run(data, state):
            if (state.get("understood") or {}).get("by") == "智能体" and "run" not in state["understood"]:
                state["understood"]["run"] = initial["id"]
            return original_save(data, state)
        with mock.patch.object(intake, "understander", return_value=""), mock.patch.object(intake, "_save", side_effect=keep_initial_run):
            sid, key, _ = self.conversation()
            state = intake.recovery_state(self.P, key)
            self.assertEqual(state["status"], "failed")
            self.assertIsNone(state["run"])
            self.assertFalse(state["can_retry"])
        session = intake.load(self.data, sid, self.P)
        self.assertTrue(session["understanding_recovery"]["no_spawn"])
        self.assertEqual(session["understood"]["run"], initial["id"])
        self.assertEqual(self.calls, [])
        self.assertTrue(intake.recovery_state(self.P, key)["can_retry"])
        intake.retry_understanding(self.P, key, "恢复配置的人")
        self.outcome = "success"
        self.complete_job(sid)
        self.assertFalse(signoff.client_ac(self.data, key)[0]["open"])
        self.assertEqual(intake.recovery_state(self.P, key)["status"], "resolved")

    def test_sweep_recovers_confirmed_session_with_expired_unspawned_retry(self):
        sid, key, _ = self.failed()
        intake.retry_understanding(self.P, key, "恢复操作员")
        session = intake.load(self.data, sid, self.P)
        session["understanding_job"]["t0"] = time.time() - intake.deadline(self.data) - 5
        intake._save(self.data, session)
        self.assertEqual(session["state"], "confirmed")
        self.assertEqual(intake.sweep(self.P), 1)
        after = intake.load(self.data, sid, self.P)
        self.assertEqual(after["state"], "confirmed")
        self.assertNotIn("understanding_job", after)
        self.assertTrue(intake.recovery_state(self.P, key)["can_retry"])
        self.assertTrue(self.store.ticket(key)["links"]["open_ac"])


if __name__ == "__main__":
    unittest.main()
