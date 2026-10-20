import json
import unittest

from tmh.platform.command import plan, validate

TICKET_PAGE = {"route": "#/t/OA-3", "ticket": "OA-3", "title": "审批后单据未生效",
               "fields": [{"key": "cm", "label": "写评论", "type": "textarea"},
                          {"key": "fs", "label": "状态", "type": "select", "options": [["new", "新建"], ["verify", "待验证"]], "autosave": True},
                          {"key": "accNote", "label": "验收说明（不通过时必填）", "type": "textarea"}],
               "buttons": [{"key": "cb", "label": "评论"}, {"key": "accOk", "label": "验收通过"}]}


def ops(r):
    return [(s["op"], s.get("target") or s.get("to"), s.get("value"), bool(s.get("confirm"))) for s in r["steps"]]


class CommandRuleTest(unittest.TestCase):
    def test_comment_fills_then_waits_for_confirm(self):
        r = plan("给这单写评论：需要前方实施人员去现场取日志。", TICKET_PAGE)
        self.assertEqual(ops(r), [("fill", "cm", "需要前方实施人员去现场取日志。", False), ("click", "cb", None, True)])
        r = plan("给 OA-12 写评论：已联系现场", {"route": "#/"})
        self.assertEqual(r["steps"][0], {"op": "nav", "to": "#/t/OA-12", "label": "打开工单 OA-12"})
        self.assertTrue(r["steps"][-1]["confirm"])

    def test_navigation_and_kb_search(self):
        self.assertEqual(ops(plan("打开知识库", {})), [("nav", "#/kb", None, False)])
        self.assertEqual(ops(plan("去提效报告", {})), [("nav", "#/eff", None, False)])
        self.assertEqual(ops(plan("OA-7", {})), [("nav", "#/t/OA-7", None, False)])
        self.assertEqual(ops(plan("打开知识库里的请假审批", {}))[1], ("fill", "kbq", "请假审批", False))

    def test_saving_fields_need_confirmation(self):
        # status, type and priority wait for confirmation and can be undone from the card afterwards
        self.assertEqual(ops(plan("把这单改成待验证", TICKET_PAGE)), [("pick", "fs", "verify", True)])
        self.assertTrue(plan("把这单改成待验证", TICKET_PAGE)["steps"][0]["undo"])
        self.assertEqual(ops(plan("优先级改成高", TICKET_PAGE)), [("pick", "fp", "high", True)])
        self.assertEqual(ops(plan("把这单改成已关闭", TICKET_PAGE)), [("pick", "fs", "closed", True)])
        self.assertEqual(ops(plan("指派给张三", TICKET_PAGE)), [("fill", "fa", "张三", True)])
        self.assertEqual(ops(plan("验收说明写：已核对", TICKET_PAGE)), [("fill", "accNote", "已核对", False)])
        r = plan("验收不通过", TICKET_PAGE)
        self.assertFalse(any(s["op"] == "click" for s in r["steps"]))  # 不通过要先写说明

    def test_new_ticket_and_sessions(self):
        r = plan("新建工单：审批后单据未生效。用户反馈审批通过后状态没变", {})
        self.assertEqual([s["op"] for s in r["steps"]], ["open", "fill", "fill", "click"])
        self.assertEqual(r["steps"][1]["value"], "审批后单据未生效")
        r = plan("切换到审批的会话", {}, sessions=[{"id": 4, "title": "审批问题排查"}])
        self.assertEqual(r["steps"][0]["id"], 4)

    def test_questions_stay_questions(self):
        for q in ("这单为什么失败？", "审批在哪里实现", "帮我跟进一下现场日志的事"):
            self.assertEqual(plan(q, TICKET_PAGE)["kind"], "question", q)

    def test_model_steps_are_validated(self):
        steps = validate([{"op": "nav", "to": "http://evil"}, {"op": "fill", "target": "cm", "value": "x"},
                          {"op": "click", "target": "rm-rf"}, {"op": "click", "target": "cb"},
                          {"op": "pick", "target": "fs", "value": "待验证"}], TICKET_PAGE)
        self.assertEqual([(s["op"], s["target"], s.get("confirm")) for s in steps],
                         [("fill", "cm", False), ("click", "cb", True), ("pick", "fs", True)])
        self.assertEqual(steps[2]["value"], "verify")


if __name__ == "__main__":
    unittest.main()
