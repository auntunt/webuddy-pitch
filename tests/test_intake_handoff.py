"""A client's answer may release its own wait, never a person's takeover or another task's wait."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tmh.platform import intake, signoff
from tmh.platform.orchestra import Orchestra
from tmh.platform.store import Store


class ClientHandoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tmh-client-handoff-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("OA", "示例 OA", str(self.data))
        self.runner = mock.Mock()
        self.flow = Orchestra(self.store, self.runner, self.data, mock.Mock())
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, flow=self.flow,
                                 project=self.store.project, root=lambda p: Path(p["root"]))
        self.agent = mock.patch.object(self.flow, "_flow_agent", return_value="fake")
        self.agent.start()
        self.addCleanup(self.agent.stop)
        self.configure(False)

    def configure(self, on):
        (self.data / "autoflow.json").write_text(json.dumps({"on": on, "understand": "rules"}), encoding="utf-8")

    def conversation(self, confirm=True):
        s = intake.start(self.P, self.project, "报销单提交后财务看不到，昨天开始的，财务部所有人。", "工程师", agent=False)
        if confirm:
            s = intake.confirm(self.P, s["id"], "工程师")
        a = intake.ask_client(self.P, s["id"], "工程师", tell=False)
        return s, a

    def answer(self, a, complete=True):
        answers = {"expected": "财务审核列表马上出现这张报销单"}
        if complete:
            answers["example"] = "李四提交 300 元报销，财务登录后看到该单"
        return intake.client_answer(self.P, a["token"], {"0": answers}, name="王总")

    def concurrent_answer(self, a, patch_target, patch_name, change):
        entered, proceed = threading.Event(), threading.Event()
        original = getattr(patch_target, patch_name)
        errors = []

        def paused(*args, **kwargs):
            entered.set()
            if not proceed.wait(5):
                raise AssertionError("the takeover did not finish")
            return original(*args, **kwargs)

        def answer():
            try:
                self.answer(a)
            except BaseException as exc:
                errors.append(exc)

        with mock.patch.object(patch_target, patch_name, paused):
            thread = threading.Thread(target=answer)
            thread.start()
            try:
                self.assertTrue(entered.wait(5), "the answer never reached the handoff")
                change()
            finally:
                proceed.set()
                thread.join(5)
            self.assertFalse(thread.is_alive())
            if errors:
                raise errors[0]

    def test_a_takeover_while_the_answer_is_prepared_is_kept(self):
        s, a = self.conversation()
        key = s["tickets"][0]
        self.configure(True)
        self.concurrent_answer(a, intake, "ticket_body", lambda: self.flow.take_over(self.store.ticket(key), True, "工程师"))
        t = self.store.ticket(key)
        self.assertEqual(t["links"]["hold"], "工程师")
        self.assertNotIn("open_ac", t["links"])
        self.runner.start.assert_not_called()
        self.assertIn("财务审核列表马上出现", t["body"])

    def test_a_takeover_after_the_contract_is_written_still_stops_the_handoff(self):
        for blocker in ("hold", "handwork", "later", "closed", "autoflow_off"):
            with self.subTest(blocker=blocker):
                self.configure(False)
                s, a = self.conversation()
                key = s["tickets"][0]
                self.configure(True)

                def stop():
                    t = self.store.ticket(key)
                    if blocker == "autoflow_off":
                        self.configure(False)
                    elif blocker == "closed":
                        self.store.update_ticket(t["id"], "工程师", status="closed")
                    elif blocker == "hold":
                        self.flow.take_over(t, True, "工程师")
                    else:
                        self.store.update_ticket(t["id"], "工程师", links=dict(t["links"], **{blocker: "工程师"}))

                with mock.patch.object(self.flow, "resume", wraps=self.flow.resume) as resume:
                    self.concurrent_answer(a, signoff, "contract_changed", stop)
                if blocker in ("hold", "handwork", "later"):
                    self.assertEqual(self.store.ticket(key)["links"][blocker], "工程师")
                resume.assert_not_called()
                self.runner.start.assert_not_called()

    def test_landing_uses_the_latest_links_instead_of_the_callers_snapshot(self):
        for extra in ({"hold": "工程师"}, {"handwork": "工程师"}, {"later": "等前一张单合入"}):
            with self.subTest(extra=extra):
                self.configure(False)
                s, a = self.conversation()
                old = self.store.ticket(s["tickets"][0])
                intake._apply(s, {"0": {"expected": "立即显示", "example": "提交后看到"}}, "王总")
                intake._plan(s)
                s["state"] = "confirmed"
                latest = dict(old["links"], client=17, **extra)
                self.store.update_ticket(old["id"], "工程师", links=latest)
                self.configure(True)
                with mock.patch.object(self.flow, "resume", wraps=self.flow.resume) as resume:
                    intake._land_item(self.P, s, s["items"][0], old, "王总", "客户答复")
                now = self.store.ticket(old["id"])
                self.assertEqual(now["links"], {k: v for k, v in latest.items() if k != "open_ac"})
                resume.assert_not_called()
        self.runner.start.assert_not_called()

    def test_a_ticket_closed_since_the_snapshot_is_not_rewritten(self):
        s, a = self.conversation()
        old = self.store.ticket(s["tickets"][0])
        self.store.update_ticket(old["id"], "工程师", status="closed", body="已验收的内容")
        before = signoff.records(self.data, old["key"])
        self.configure(True)
        intake._land_item(self.P, s, s["items"][0], old, "王总", "客户答复")
        current = self.store.ticket(old["id"])
        self.assertEqual((current["status"], current["body"]), ("closed", "已验收的内容"))
        self.assertEqual(signoff.records(self.data, old["key"]), before)
        self.runner.start.assert_not_called()
        self.assertIn("已完成验收", intake.client_page(self.P, a["token"], done=True))

    def test_only_complete_answers_on_an_enabled_line_start_work(self):
        for enabled, complete in ((False, True), (True, False), (True, True)):
            with self.subTest(enabled=enabled, complete=complete):
                self.configure(False)
                s, a = self.conversation()
                self.configure(enabled)
                self.runner.reset_mock()
                self.answer(a, complete)
                t = self.store.ticket(s["tickets"][0])
                self.assertEqual(bool(t["links"].get("open_ac")), not complete)
                self.assertEqual(self.runner.start.call_count, int(enabled and complete))

    def test_a_draft_answer_does_not_confirm_or_start_a_ticket(self):
        s, a = self.conversation(confirm=False)
        self.configure(True)
        self.answer(a)
        s = intake.load(self.data, s["id"], self.P)
        self.assertEqual(s["tickets"], [])
        self.assertNotEqual(s["state"], "confirmed")
        self.runner.start.assert_not_called()
        html = intake.client_page(self.P, a["token"])
        self.assertNotIn("答完就开工", html)
        self.assertNotIn("写好验收标准并开工", html)
        self.assertIn("工程师确认", html)


if __name__ == "__main__":
    unittest.main()
