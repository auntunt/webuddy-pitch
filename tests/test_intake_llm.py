"""Plain LLM reading of requirements, attachments kept by hash, duplicate hints, and the rules' fixes."""
import base64
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tmh.platform import attachments, intake, llm
from tmh.platform.errors import ApiError
from tmh.platform.orchestra import Orchestra
from tmh.platform.store import Store

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()
REPLY = """```tmh-intake
{"title": "报销提交转圈", "big": false, "drop": ["在吗？？"],
 "items": [{"title": "报销单提交一直转圈", "quote": "点提交就一直转圈", "kind": "缺陷", "restated": "月底提交报销单时一直转圈，提交不上",
            "flow": "新模块", "said": {}, "questions": [], "ac": [{"id": "A1", "text": "当提交报销单时，系统应当在 3 秒内提示结果", "check": "提交一张单据核对"}],
            "keep": []}]}
```"""


def docx(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                   f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    return base64.b64encode(buf.getvalue()).decode()


class IntakeLLMTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tmh-intake-llm-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("OA", "示例 OA", str(self.data))
        self.runner = mock.Mock()
        self.flow = Orchestra(self.store, self.runner, self.data, mock.Mock())
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, flow=self.flow, runner=self.runner,
                                 project=self.store.project, root=lambda p: Path(p["root"]))
        (self.data / "autoflow.json").write_text(json.dumps({"on": False, "understand": "auto"}), encoding="utf-8")
        env = mock.patch.dict("os.environ", {"TMH_ROUTER_BASE_URL": "http://llm.invalid/v1", "TMH_ROUTER_MODEL": "m", "TMH_ROUTER_KEY": "k"})
        env.start()
        self.addCleanup(env.stop)

    def test_llm_reads_without_starting_an_agent_and_records_the_run(self):
        with mock.patch.object(llm.kbqa, "_post", return_value={"choices": [{"message": {"content": REPLY}}]}) as post:
            s = intake.start(self.P, self.project, "在吗？？点提交就一直转圈", "工程师", wait=True)
        self.assertEqual(s["understood"]["by"], "LLM")
        self.assertEqual(s["items"][0]["kind"], "bug")
        self.runner.invoke.assert_not_called()
        run = self.store.run(s["understood"]["run"])
        self.assertEqual((run["agent"], run["mode"], run["status"]), ("llm", "understand", "done"))
        self.assertIn("<<<原话开始", post.call_args[0][1]["messages"][1]["content"])
        self.assertIn(s["state"], ("asking", "ready"))  # nothing becomes a ticket before a person confirms
        self.assertEqual(self.store.tickets(project_id=self.project["id"]), [])

    def test_bad_llm_reply_falls_back_to_the_rules(self):
        with mock.patch.object(llm.kbqa, "_post", return_value={"choices": [{"message": {"content": "随便说说"}}]}):
            s = intake.start(self.P, self.project, "点提交就一直转圈，报错了", "工程师", wait=True)
        self.assertEqual(s["understood"]["by"], "规则")
        self.assertIn("tmh-intake", s["understood"]["why"])

    def test_project_without_direct_api_never_calls_the_llm(self):
        (self.data / "agent-routes.json").write_text(json.dumps({"schema": 1, "projects": {"OA": {"direct_api": False}}}), encoding="utf-8")
        self.assertFalse(llm.conf(self.P, self.project)["ready"])
        self.assertTrue(llm.conf(self.P, self.store.add_project("HR", "HR", str(self.data)))["ready"])

    def test_attachments_are_kept_by_hash_and_reach_prompt_ticket_and_record(self):
        files = attachments.save(self.data, [{"name": "截图.png", "data": "data:image/png;base64," + PNG},
                                             {"name": "需求.docx", "data": docx("审批列表要能导出 Excel")}])
        self.assertTrue((attachments.image_dir(self.data) / files[0]["file"]).is_file())
        self.assertEqual(files[1]["text"], "审批列表要能导出 Excel")
        with mock.patch.object(llm.kbqa, "_post", return_value={"choices": [{"message": {"content": REPLY}}]}) as post:
            s = intake.start(self.P, self.project, "见附件", "工程师", wait=True, attachments=files)
        prompt = post.call_args[0][1]["messages"][1]["content"]
        self.assertIn("审批列表要能导出 Excel", prompt)
        self.assertIn("截图《截图.png》", prompt)
        body = intake.ticket_body(s, s["items"][0])
        self.assertIn(files[0]["sha256"][:12], body)
        rec = intake.intake_record(s, s["items"][0], "工程师")
        self.assertEqual([a["sha256"] for a in rec["attachments"]], [f["sha256"] for f in files])
        self.assertNotIn("text", rec["attachments"][1])

    def test_vision_model_gets_the_screenshot(self):
        files = attachments.save(self.data, [{"name": "a.png", "data": "data:image/png;base64," + PNG}])
        with mock.patch.dict("os.environ", {"TMH_ROUTER_VISION": "1"}), \
                mock.patch.object(llm.kbqa, "_post", return_value={"choices": [{"message": {"content": REPLY}}]}) as post:
            intake.start(self.P, self.project, "看截图，提交报错", "工程师", wait=True, attachments=files)
        content = post.call_args[0][1]["messages"][1]["content"]
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_unsupported_or_oversized_attachments_are_refused(self):
        with self.assertRaises(ApiError):
            attachments.save(self.data, [{"name": "x.exe", "data": PNG}])
        with self.assertRaises(ApiError):
            attachments.save(self.data, [{"name": "a.txt", "data": base64.b64encode(b"x").decode()}] * 9)

    def test_rules_drop_greeting_split_on_another_and_do_not_echo(self):
        (self.data / "autoflow.json").write_text(json.dumps({"understand": "rules"}), encoding="utf-8")
        s = intake.start(self.P, self.project, "在吗？？报销单提交不了，一直转圈报错！另外审批列表最好能导出Excel", "工程师")
        self.assertTrue(any(x.startswith("在吗") for x in s["dropped"]))
        self.assertEqual([it["kind"] for it in s["items"]], ["bug", "feature"])
        self.assertNotIn("另外", intake.understanding(s["items"][0]))

    def test_similar_open_tickets_are_hinted(self):
        self.store.create_ticket(self.project["id"], "报销单提交不了一直转圈", "点提交就一直转圈", reporter="王姐")
        (self.data / "autoflow.json").write_text(json.dumps({"understand": "rules"}), encoding="utf-8")
        s = intake.start(self.P, self.project, "报销单提交不了，一直转圈", "工程师")
        self.assertEqual(s["items"][0]["similar"][0]["key"], "OA-1")


class AssistRoutingTest(unittest.TestCase):
    def test_code_questions_need_an_agent_business_questions_do_not(self):
        from tmh.platform import assist
        self.assertTrue(assist.needs_code("请假审批在哪个文件实现的"))
        self.assertTrue(assist.needs_code("LeaveService.java 里报错栈是什么意思"))
        self.assertFalse(assist.needs_code("请假超过三天要谁审批"))

    def test_llm_answer_words_the_cards_and_yields_when_nothing_matches(self):
        from tmh.platform import assist
        P = SimpleNamespace(data_dir=Path("."), root=lambda p: Path("."))
        card = {"cards": [{"title": "请假审批", "sub": "规则", "summary": "超过三天由部门经理审批"}], "body": "…"}
        with mock.patch.object(llm, "conf", return_value={"ready": True, "model": "m", "vision": False}), \
                mock.patch.object(assist, "kb_answer", return_value=dict(card)), \
                mock.patch.object(llm, "chat", return_value="超过三天由部门经理审批。") as chat:
            ans = assist.llm_answer(P, {"id": 1}, None, "请假超过三天谁审批", [])
        self.assertEqual((ans["body"], ans["source"]), ("超过三天由部门经理审批。", "知识库 + LLM"))
        self.assertIn("超过三天由部门经理审批", chat.call_args[0][2])
        with mock.patch.object(llm, "conf", return_value={"ready": True, "model": "m", "vision": False}), \
                mock.patch.object(assist, "kb_answer", return_value={"cards": [], "no_evidence": True, "body": ""}), \
                mock.patch.object(llm, "chat") as chat:
            self.assertIsNone(assist.llm_answer(P, {"id": 1}, None, "随便问问", []))
        chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
