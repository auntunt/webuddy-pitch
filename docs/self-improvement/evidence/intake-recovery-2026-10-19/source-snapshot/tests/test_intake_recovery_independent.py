"""Independent recovery checks: customer answers, contracts, races and process receipts.

Each case owns a temporary Store and a real Runner. The local reader emits a
controlled JSON response; it is a process fixture, never a model or customer.
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
from tmh.platform.orchestra import Orchestra
from tmh.platform.store import Store


class IndependentIntakeRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-independent-intake-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.root = self.data / "project"
        self.root.mkdir()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("REC", "隔离恢复验证", str(self.root))
        self.runner = Runner(self.store, self.data)
        self.flow = Orchestra(self.store, self.runner, self.data, mock.Mock())
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, runner=self.runner, flow=self.flow,
                                 project=self.store.project, root=lambda p: Path(p["root"]))
        self.control = self.data / "reader-response.json"
        script = self.data / "controlled-reader.py"
        script.write_text("import json,sys\nfrom pathlib import Path\n"
                          "x=json.loads(Path(sys.argv[1]).read_text())\n"
                          "print('independent-reader-original-output', flush=True)\n"
                          "print('```tmh-intake\\n'+json.dumps(x['reply'],ensure_ascii=False)+'\\n```', flush=True)\n"
                          "sys.exit(x.get('exit',0))\n", encoding="utf-8")
        (self.data / "agents.json").write_text(json.dumps({"reader": {
            "cmd": [sys.executable, str(script), str(self.control)], "timeout": 10}}))
        (self.data / "autoflow.json").write_text(json.dumps({"on": False, "understand": "agent",
            "understand_agent": "reader", "understand_timeout": 10}))

    def reply(self, resolved=False, extra_question=False, twist=False, still_unknown=False):
        questions = [] if resolved else [{"q": "提交后财务应该多久看到？", "blocks": ["A1"]}]
        if extra_question and not resolved:
            questions.append({"q": "财务应在哪个列表查看？", "blocks": ["A1"]})
        return {"title": "报销单财务看不到", "items": [{
            "title": "被模型改掉的标题" if twist else "报销单财务看不到", "kind": "缺陷",
            "quote": "提交报销单后财务看不到", "restated": "提交报销单后财务看不到这张报销单", "flow": "",
            "questions": questions,
            "ac": [{"id": "A1", "text": "提交后财务应%s看到原单" % (
                "【待确认：多久】" if not resolved or still_unknown else "马上在审核列表"),
                "check": "李四提交300元报销，财务读回原单"},
                {"id": "A2", "text": "审核通过后应从待审核列表移走" + ("并通知老板" if twist else ""),
                 "check": "模型替换的弱检查" if twist else "审核前后分别查询，核对记录数与原单号", "layer": "L1"}],
            "keep": ["其他部门的报销记录与付款流程不变"]}]}

    def response(self, reply=None, code=0):
        self.control.write_text(json.dumps({"reply": reply or self.reply(), "exit": code}, ensure_ascii=False))

    def raw(self):
        return json.loads((intake.idir(self.data) / (self.sid + ".json")).read_text())

    def save(self, state):
        # Fixture mutations never touch a user's conversation or a running service.
        intake._save(self.data, state)

    def confirmed(self, extra_question=False):
        self.response(self.reply(extra_question=extra_question))
        s = intake.start(self.P, self.project, "提交报销单后财务看不到", "受理人甲", wait=True)
        self.assertEqual(s["understood"]["by"], "智能体")
        self.sid = s["id"]
        # A historical contract can carry a different layer; recovery must preserve it.
        s["items"][0]["agent_ac"][1]["layer"] = "L4"
        intake._plan(s)
        self.save(s)
        s = intake.confirm(self.P, self.sid, "确认工程师甲")
        self.key = s["tickets"][0]
        self.original_contract = copy.deepcopy(signoff.client_ac(self.data, self.key))
        self.link = intake.ask_client(self.P, self.sid, "发问工程师甲", tell=False)
        return s

    def fail_answer(self, extra_question=False):
        self.confirmed(extra_question=extra_question)
        self.response(self.reply(resolved=True), code=23)
        answer = {"q1": "马上"}
        if extra_question:
            answer["q2"] = "不清楚"
        intake.client_answer(self.P, self.link["token"], {"0": answer}, name="王总", wait=True)
        s = self.raw()
        self.assertEqual(s["state"], "confirmed")
        self.assertTrue(self.store.ticket(self.key)["links"].get("open_ac"))
        self.failed_run = s["understood"]["run"]
        self.assertEqual(self.store.run(self.failed_run)["status"], "failed")
        receipt = json.loads((self.data / "runs" / str(self.failed_run) / "lifecycle.json").read_text())
        self.assertTrue(receipt["finished"])
        self.assertTrue(all(x["cleanup"]["complete"] for x in receipt["attempts"]))
        return s

    def test_retry_preserves_entire_closed_contract_and_distinct_authors(self):
        failed = self.fail_answer()
        saved_answers = copy.deepcopy(failed["items"][0]["slots"])
        old_run = self.store.run(self.failed_run)
        self.response(self.reply(resolved=True, twist=True))
        intake.retry_understanding(self.P, self.key, "恢复工程师乙", wait=True)
        after = signoff.client_ac(self.data, self.key)
        self.assertEqual(after[1:], self.original_contract[1:], "closed AC text/check/layer/keep are contract fields")
        self.assertFalse(after[0]["open"])
        self.assertIn("马上", after[0]["text"])
        s = self.raw()
        self.assertEqual(s["items"][0]["slots"], saved_answers)
        self.assertEqual(saved_answers["q1"]["from"], "王总（客户）")
        self.assertEqual(self.store.ticket(self.key)["title"], "报销单财务看不到")
        self.assertNotIn("open_ac", self.store.ticket(self.key)["links"])
        self.assertEqual(self.store.run(self.failed_run), old_run, "retry must not rewrite original run evidence")
        latest = self.store.runs(project_id=self.project["id"])[0]
        self.assertEqual(latest["author"], "恢复工程师乙")
        records = signoff.records(self.data, self.key)
        record = [r for r in records if r["kind"] == "intake"][-1]
        self.assertEqual(record["data"]["confirmed_by"], "王总（客户）", "engineer requested re-reading, not customer signoff")
        evidence = json.dumps({"active": s.get("understanding_recovery"),
                               "history": s.get("understanding_recovery_history")}, ensure_ascii=False)
        self.assertIn("恢复工程师乙", evidence)
        self.assertIn("王总（客户）", json.dumps(records, ensure_ascii=False))

    def test_answered_unknown_stays_open_even_when_reader_claims_completion(self):
        self.fail_answer(extra_question=True)
        self.response(self.reply(resolved=True))
        with mock.patch.object(self.flow, "resume") as resume:
            intake.retry_understanding(self.P, self.key, "恢复工程师乙", wait=True)
        s = self.raw()
        self.assertEqual(s["items"][0]["slots"]["q2"]["value"], "不清楚")
        self.assertTrue(signoff.client_ac(self.data, self.key)[0]["open"])
        self.assertTrue(self.store.ticket(self.key)["links"].get("open_ac"))
        self.assertEqual(signoff.client_ac(self.data, self.key)[1:], self.original_contract[1:])
        resume.assert_not_called()

    def test_retry_that_returns_placeholder_is_visible_and_still_retryable(self):
        self.fail_answer()
        self.response(self.reply(resolved=True, still_unknown=True))
        intake.retry_understanding(self.P, self.key, "恢复工程师乙", wait=True)
        recovery = intake.recovery_state(self.P, self.key)
        self.assertIn(recovery["status"], ("failed", "blocked"))
        self.assertTrue(recovery["can_retry"])
        self.assertTrue(recovery.get("reason"))
        self.assertTrue(self.store.ticket(self.key)["links"].get("open_ac"))

    def test_real_finished_receipt_must_remain_readable_and_confirm_cleanup(self):
        self.fail_answer()
        receipt_file = self.data / "runs" / str(self.failed_run) / "lifecycle.json"
        original = receipt_file.read_bytes()
        receipt = json.loads(original)
        mutations = []
        unfinished = copy.deepcopy(receipt)
        unfinished["finished"] = False
        mutations.append(json.dumps(unfinished).encode())
        uncleared = copy.deepcopy(receipt)
        uncleared["attempts"][0]["cleanup"]["complete"] = False
        mutations.extend((json.dumps(uncleared).encode(), b"corrupt lifecycle", b'{"finished":true,"attempts":[null]}'))
        try:
            for mutated in mutations:
                with self.subTest(receipt=mutated[:90]):
                    receipt_file.write_bytes(mutated)
                    before = self.raw()
                    count = len(self.store.runs(project_id=self.project["id"]))
                    state = intake.recovery_state(self.P, self.key)
                    self.assertFalse(state["can_retry"])
                    self.assertTrue(state["blocked"])
                    with self.assertRaises(ApiError) as caught:
                        intake.retry_understanding(self.P, self.key, "恢复工程师乙")
                    self.assertEqual(caught.exception.code, 409)
                    self.assertEqual(self.raw(), before)
                    self.assertEqual(len(self.store.runs(project_id=self.project["id"])), count)
        finally:
            receipt_file.write_bytes(original)
        self.assertTrue(intake.recovery_state(self.P, self.key)["can_retry"])

    def test_two_retry_requests_create_only_one_new_job(self):
        self.fail_answer()
        gate = threading.Barrier(2)
        outcomes = []
        def retry():
            gate.wait(3)
            try:
                intake.retry_understanding(self.P, self.key, "恢复工程师乙")
                outcomes.append(200)
            except ApiError as error:
                outcomes.append(error.code)
        with mock.patch.object(intake, "_spawn") as spawn:
            threads = [threading.Thread(target=retry) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(5)
                self.assertFalse(t.is_alive())
        self.assertEqual(sorted(outcomes), [200, 409])
        spawn.assert_called_once()
        self.assertEqual(intake.recovery_state(self.P, self.key)["status"], "running")

    def test_expired_get_cannot_give_up_a_replacement_job_started_before_lock(self):
        self.fail_answer()
        old = self.raw()
        old["state"] = "understanding"
        old["understanding_job"] = {"id": "expired-older-job", "agent": "reader", "refine": [0],
            "t0": time.time() - intake.deadline(self.data) - 10}
        self.save(old)
        entering, proceed = threading.Event(), threading.Event()
        result, errors = [], []
        original_lock = intake._LOCK
        class DelayedLock:
            def __enter__(inner):
                entering.set()
                if not proceed.wait(5):
                    raise AssertionError("replacement job was not installed")
                return original_lock.__enter__()
            def __exit__(inner, *args):
                return original_lock.__exit__(*args)
        def read():
            try:
                result.append(intake.load(self.data, self.sid, self.P))
            except BaseException as error:
                errors.append(error)
        with mock.patch.object(intake, "_LOCK", DelayedLock()):
            thread = threading.Thread(target=read)
            thread.start()
            try:
                self.assertTrue(entering.wait(5))
                newer = copy.deepcopy(old)
                newer["understanding_job"].update(id="fresh-replacement-job", t0=time.time())
                self.save(newer)
            finally:
                proceed.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result[0]["understanding_job"]["id"], "fresh-replacement-job")
        self.assertEqual(self.raw(), newer)

    def test_late_success_cannot_replace_a_new_recovery_job(self):
        self.confirmed()
        self.response(self.reply(resolved=True))
        with mock.patch.object(intake, "_spawn"):
            intake.client_answer(self.P, self.link["token"], {"0": {"q1": "马上"}}, name="王总")
        old_job = self.raw()["understanding_job"]["id"]
        parsed, proceed = threading.Event(), threading.Event()
        original_parse = intake.parse
        errors = []
        def delayed_parse(output):
            result = original_parse(output)
            parsed.set()
            if not proceed.wait(5):
                raise AssertionError("replacement job was not requested")
            return result
        def run():
            try:
                intake._understand(self.P, self.project, self.sid, old_job, "reader")
            except BaseException as error:
                errors.append(error)
        with mock.patch.object(intake, "parse", delayed_parse):
            thread = threading.Thread(target=run)
            thread.start()
            try:
                self.assertTrue(parsed.wait(5), "real reader never completed")
                s = self.raw()
                s["understanding_job"]["t0"] = time.time() - intake.deadline(self.data) - 5
                self.save(s)
                intake.load(self.data, self.sid, self.P)
                self.assertTrue(intake.recovery_state(self.P, self.key)["can_retry"])
                with mock.patch.object(intake, "_spawn"):
                    intake.retry_understanding(self.P, self.key, "恢复工程师乙")
                newer = self.raw()
                before_contract = signoff.client_ac(self.data, self.key)
            finally:
                proceed.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertNotEqual(newer["understanding_job"]["id"], old_job)
        self.assertEqual(self.raw(), newer)
        self.assertEqual(signoff.client_ac(self.data, self.key), before_contract)
        intake._understand(self.P, self.project, self.sid, newer["understanding_job"]["id"], "reader")
        self.assertFalse(signoff.client_ac(self.data, self.key)[0]["open"])

    def test_recovery_read_is_side_effect_free(self):
        self.fail_answer()
        before = {p.relative_to(self.data): p.read_bytes() for p in self.data.rglob("*") if p.is_file()}
        changes = self.store.db.total_changes
        first = intake.recovery_state(self.P, self.key)
        second = intake.recovery_state(self.P, self.key)
        after = {p.relative_to(self.data): p.read_bytes() for p in self.data.rglob("*") if p.is_file()}
        self.assertEqual(first, second)
        self.assertEqual(before, after)
        self.assertEqual(self.store.db.total_changes, changes)

    def test_contract_check_and_layer_changed_during_retry_are_not_overwritten(self):
        self.fail_answer()
        self.response(self.reply(resolved=True))
        parse = intake.parse
        changed_contract = []
        def change_contract_after_process_finished(output):
            result = parse(output)
            current = copy.deepcopy(signoff.client_record(self.data, self.key))
            current["ac"][1]["check"] = "另一工程师要求：对账全部金额、逐条核对审核日志"
            current["ac"][1]["layer"] = "L3"
            signoff._add(signoff.epath(self.data, self.key), "intake", "合同工程师丙", current)
            changed_contract[:] = signoff.client_ac(self.data, self.key)
            return result
        with mock.patch.object(intake, "parse", change_contract_after_process_finished), \
                mock.patch.object(self.flow, "resume") as resume:
            intake.retry_understanding(self.P, self.key, "恢复工程师乙", wait=True)
        self.assertEqual(signoff.client_ac(self.data, self.key), changed_contract,
                         "a stale recovery must preserve the latest contract, including check and layer")
        self.assertTrue(self.store.ticket(self.key)["links"].get("open_ac"))
        self.assertIn(intake.recovery_state(self.P, self.key)["status"], ("failed", "blocked"))
        resume.assert_not_called()

    def test_contract_update_between_landing_read_and_write_is_not_lost(self):
        self.fail_answer()
        self.response(self.reply(resolved=True))
        ticket_body = intake.ticket_body
        changed_contract = []
        def change_contract_while_preparing_body(*args):
            body = ticket_body(*args)
            current = copy.deepcopy(signoff.client_record(self.data, self.key))
            current["ac"][1]["check"] = "最终写入前由工程师追加：核对审计日志和流水金额"
            signoff._add(signoff.epath(self.data, self.key), "intake", "合同工程师丙", current)
            changed_contract[:] = signoff.client_ac(self.data, self.key)
            return body
        with mock.patch.object(intake, "ticket_body", change_contract_while_preparing_body), \
                mock.patch.object(self.flow, "resume") as resume:
            intake.retry_understanding(self.P, self.key, "恢复工程师乙", wait=True)
        self.assertTrue(changed_contract, "the retry must reach the actual contract write boundary")
        self.assertEqual(signoff.client_ac(self.data, self.key), changed_contract)
        self.assertTrue(self.store.ticket(self.key)["links"].get("open_ac"))
        recovery = intake.recovery_state(self.P, self.key)
        self.assertIn(recovery["status"], ("failed", "blocked"))
        self.assertFalse(recovery["can_retry"], "stale contract binding must not be rebound for another retry")
        resume.assert_not_called()

    def test_expired_retry_does_not_overwrite_a_newer_contract_during_fallback(self):
        self.fail_answer()
        with mock.patch.object(intake, "_spawn"):
            intake.retry_understanding(self.P, self.key, "恢复工程师乙")
        current = copy.deepcopy(signoff.client_record(self.data, self.key))
        current["ac"][1]["check"] = "超时前工程师补充：逐条核对付款流水和审计记录"
        current["ac"][1]["layer"] = "L3"
        signoff._add(signoff.epath(self.data, self.key), "intake", "合同工程师丙", current)
        changed_contract = signoff.client_ac(self.data, self.key)
        state = self.raw()
        state["understanding_job"]["t0"] = time.time() - intake.deadline(self.data) - 5
        self.save(state)
        with mock.patch.object(self.flow, "resume") as resume:
            intake.load(self.data, self.sid, self.P)
        self.assertEqual(signoff.client_ac(self.data, self.key), changed_contract,
                         "timeout fallback must enforce the same contract binding as successful completion")
        self.assertFalse(intake.recovery_state(self.P, self.key)["can_retry"])
        self.assertTrue(self.store.ticket(self.key)["links"].get("open_ac"))
        resume.assert_not_called()

    def test_ticket_closed_while_reader_runs_is_not_reported_as_recovered(self):
        self.fail_answer()
        contract = copy.deepcopy(signoff.client_ac(self.data, self.key))
        self.response(self.reply(resolved=True))
        parse = intake.parse
        def close_before_landing(output):
            result = parse(output)
            self.store.update_ticket(self.store.ticket(self.key)["id"], "关闭工程师丙", status="closed")
            return result
        with mock.patch.object(intake, "parse", close_before_landing), mock.patch.object(self.flow, "resume") as resume:
            intake.retry_understanding(self.P, self.key, "恢复工程师乙", wait=True)
        self.assertEqual(signoff.client_ac(self.data, self.key), contract)
        self.assertEqual(self.store.ticket(self.key)["status"], "closed")
        recovery = intake.recovery_state(self.P, self.key)
        self.assertNotEqual(recovery["status"], "resolved", "skipping a closed ticket is not successful contract recovery")
        self.assertFalse(recovery["can_retry"])
        resume.assert_not_called()


if __name__ == "__main__":
    unittest.main()
