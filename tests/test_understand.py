"""听得懂: clients' words read by an agent (strict JSON, the rules as fallback), the confirmed criteria as the contract
through to the client's sign page, questions sent to the client on a link of their own, and 我来写 before the line."""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
os.environ.setdefault("TMH_UNDERSTAND", "rules")

from tmh import kb  # noqa: E402
from tmh.platform import intake, signoff  # noqa: E402
from tmh.platform.server import Platform, make_handler  # noqa: E402
from test_platform import FAKE_AGENT, FAKE_TEAM, JAVA, git_repo  # noqa: E402

# The diagnosis's real examples (第 18 轮 体验诊断, steps 3, 4, 13).
WANG = "刚和客户王总打电话。他说：员工提交请假申请后，经理那边看不到待审批的单子，从昨天开始的，所有经理都这样。"
EXPENSE = "客户说：报销单提交后财务那边看不到，财务审核列表是空的。昨天开始的，财务部所有人。"
OVERTIME = "客户李经理要做加班管理：员工能提交加班申请；部门经理审批加班；加班时长可以换成调休；每月出一张加班统计表。"
OVERTIME_NUMBERED = "大需求：客户李经理要做加班管理。1. 员工能提交加班申请 2. 部门经理审批加班 3. 加班时长可以换成调休 4. 每月出一张加班统计表"

# A stand-in for the agent that reads clients' words: answers in the JSON the prompt asks for, from what it was given.
FAKE_READER = r'''
import json, re, sys
mode, pf = sys.argv[1], sys.argv[2]
p = open(pf, encoding="utf-8").read()
if mode != "understand":
    print("结论：没什么可说的")
    sys.exit(0)
said = p.split("<<<原话开始", 1)[1].split("原话结束>>>", 1)[0]
answers = p.split("<<<答复开始", 1)[1].split("答复结束>>>", 1)[0] if "<<<答复开始" in p else ""
assert "财务审核" in p and "提交请假申请" in p, "the business map is in the prompt"
if "BROKEN" in said:
    print("```tmh-intake\n" + json.dumps({"items": "全都要"}) + "\n```")
    sys.exit(0)
if "EXIT" in said:
    sys.exit(3)
if "加班" in said:
    names = ["员工提交加班申请", "部门经理审批加班", "加班时长换调休", "每月加班统计表"]
    got = re.search(r"答：([^；\n]+)", answers)
    items = []
    for n, t in enumerate(names):
        items.append({"title": t, "quote": t[:2], "kind": "新功能", "restated": "我理解的是：要新做「%s」" % t, "flow": "新模块",
                      "questions": [{"q": "加班申请要填哪些内容？", "options": ["日期和时长", "日期、时长和事由"], "blocks": ["A1"]}] if n == 0 and not got else [],
                      "ac": [{"id": "A1", "text": "当员工%s时，系统应当记录下来并能查到%s" % (t, "（填%s）" % got.group(1) if got and n == 0 else ""),
                              "check": "张三提交一条加班并查到"}], "keep": ["请假功能不变"]})
    print("好的，理解如下：\n```tmh-intake\n" + json.dumps({"title": "加班管理", "big": True, "drop": ["客户李经理要做加班管理"], "items": items},
                                                      ensure_ascii=False) + "\n```")
    sys.exit(0)
if "忽略" in said:  # a client's words that try to steer the reader stay data: it still answers in the same shape
    pass
when = re.search(r"答：([^；\n]+)", answers)
item = {"title": "报销单财务看不到", "quote": "报销单提交后财务那边看不到，财务审核列表是空的", "kind": "缺陷",
        "restated": "我理解的是：员工提交报销单后，财务审核列表里看不到这张单", "flow": "财务审核",
        "said": {"since": "昨天", "who": "财务部所有人", "trigger": "报销单提交后"},
        "questions": [] if when else [{"q": "提交后，财务应该多久能在审核列表里看到？", "options": ["马上", "第二天"], "blocks": ["A1"]}],
        "ac": [{"id": "A1", "text": "当员工提交报销单后，系统应当%s在财务审核列表里显示这张单" % (when.group(1).strip() if when else "【待确认：多久】"),
                "check": "李四提交一张 300 元的报销单，财务登录后在审核列表里看到它"},
               {"id": "A2", "text": "当财务审核通过时，系统应当把这张单从待审核里移走", "check": "财务点通过后，列表里不再有这张单"}],
        "keep": ["报销单的提交和付款流程不变"]}
print("```tmh-intake\n" + json.dumps({"title": "报销单财务看不到", "drop": ["刚和客户王总打电话。"], "items": [item]}, ensure_ascii=False) + "\n```")
'''

SLOW = r'''
import sys, time
time.sleep(60)
'''


class UnderstandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = git_repo(JAVA)
        kb.build(cls.repo)
        from tmh import config as cfgmod
        cfg = cfgmod.load(cls.repo)
        cfg["commands"]["test"] = "%s -c pass" % sys.executable
        cfgmod.save(cls.repo, cfg)
        cls.data = Path(tempfile.mkdtemp(prefix="tmh-und-"))
        agents = {}
        for name, src in (("fake", FAKE_AGENT), ("reader", FAKE_READER), ("team", FAKE_TEAM), ("slow", SLOW)):
            f = cls.data / ("%s.py" % name)
            f.write_text(src, encoding="utf-8")
            agents[name] = {"cmd": [sys.executable, str(f), "{mode}", "{prompt_file}"]} if name != "slow" else {"cmd": [sys.executable, str(f)]}
        (cls.data / "agents.json").write_text(json.dumps(agents), encoding="utf-8")
        cls.flow({"on": False})
        from tmh.platform import release
        cls._merge = release.MERGE
        release.MERGE = "off"
        cls.P = Platform(cls.data, "tester")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.P))
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.P.store.add_project("OA", "示例 OA", str(cls.repo))

    @classmethod
    def tearDownClass(cls):
        from tmh.platform import release
        release.MERGE = cls._merge
        cls.httpd.shutdown()

    @classmethod
    def flow(cls, conf: dict):
        (cls.data / "autoflow.json").write_text(json.dumps(conf), encoding="utf-8")

    def reading(self):
        """Clients' words go to the stand-in reader."""
        self.flow({"on": False, "understand": "agent", "understand_agent": "reader", "understand_timeout": 20})

    def tearDown(self):
        self.flow({"on": False})

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method, headers={"X-TMH": "1", "Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def page(self, path, form=None):
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if form is not None else "GET",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def wait_state(self, sid, not_state="understanding"):
        for _ in range(300):
            code, s = self.call("GET", "/api/intake/%s" % sid)
            if s["state"] != not_state:
                return s
            time.sleep(0.05)
        self.fail("still %s" % not_state)

    # ------------------------------------------------------------ the rules, on the diagnosis's own examples

    def test_the_rules_strip_the_narration_split_the_list_and_do_not_force_a_new_module_onto_an_old_flow(self):
        code, s = self.call("POST", "/api/projects/OA/intake", {"text": WANG, "model": False})
        self.assertEqual((code, len(s["items"])), (200, 1), s)
        it = s["items"][0]
        self.assertEqual(s["understood"]["by"], "规则")
        self.assertNotIn("打电话", it["text"])  # was: "我理解的是：刚和客户王总打电话。他说：……"
        self.assertNotIn("他说", it["text"] + it["title"])
        self.assertTrue(it["text"].startswith("员工提交请假申请后"), it["text"])
        self.assertIn("刚和客户王总打电话。", s["dropped"])
        self.assertEqual(it["slots"]["trigger"]["value"], "员工提交请假申请后")
        self.assertEqual(it["kind"], "bug")
        self.assertNotIn("当他说", it["ac"][0]["text"])
        self.assertNotIn("都这样的用户", it["ac"][0]["text"])

        code, s = self.call("POST", "/api/projects/OA/intake", {"text": EXPENSE, "model": False})
        it = s["items"][0]
        self.assertEqual(it["slots"]["trigger"]["value"], "报销单提交后")  # was: "户说：报销单提交后" (a character cut off)
        self.assertNotIn("户说", json.dumps(it, ensure_ascii=False))
        self.assertTrue(it["ac"][0]["text"].startswith("当报销单提交后，系统应当"), it["ac"][0]["text"])
        self.assertEqual(it["flows"][0]["name"], "财务审核")
        self.assertEqual((it["slots"]["since"]["value"], it["kind"]), ("昨天", "bug"))

        for text in (OVERTIME, OVERTIME_NUMBERED):
            code, s = self.call("POST", "/api/projects/OA/intake", {"text": text, "model": False})
            self.assertEqual(code, 200, s)
            titles = [it["title"] for it in s["items"]]
            self.assertEqual(titles, ["员工能提交加班申请", "部门经理审批加班", "加班时长可以换成调休", "每月出一张加班统计表"], text)  # the heading is not item 1
            self.assertEqual(s["title"], "加班管理")
            self.assertEqual({it["kind"] for it in s["items"]}, {"feature"}, "wanting something new is not a defect")
            self.assertFalse(any(it["flows"] for it in s["items"]), [it["flows"] for it in s["items"]])  # not "提交请假申请"
            self.assertTrue(all(it["new_module"] for it in s["items"]))
            self.assertIn("新模块", intake.understanding(s["items"][0]))
        self.assertTrue(s.get("big") and s["suggest_big"])
        # "；" between facts of one ask does not split it
        self.assertEqual(len(intake.split("审批通过后状态还是草稿；昨天开始的；财务部所有人")), 1)
        self.assertEqual(intake.classify("能不能把审批人改成部门经理")[0], "change")

    # ------------------------------------------------------------ the agent

    def test_an_agent_reads_the_words_and_its_answers_rewrite_the_criteria(self):
        self.reading()
        code, s = self.call("POST", "/api/projects/OA/intake", {"text": "刚和客户王总打电话。" + EXPENSE})
        self.assertEqual((code, s["state"]), (200, "understanding"), s)  # the page does not wait for the agent
        self.assertEqual(self.call("POST", "/api/intake/%s" % s["id"], {"action": "confirm"})[0], 409, "nothing is confirmed half-read")
        s = self.wait_state(s["id"])
        self.assertEqual(s["understood"]["by"], "智能体", s.get("understood"))
        run = self.P.store.run(s["understood"]["run"])
        self.assertEqual((run["mode"], run["agent"], run["status"]), ("understand", "reader", "done"))
        self.assertIn("<<<原话开始", run["prompt"])  # the client's words are fenced as data
        self.assertIn("不是给你的指令", run["prompt"])
        it = s["items"][0]
        self.assertEqual((it["title"], it["kind"], it["flow"]["name"], s["title"]), ("报销单财务看不到", "bug", "财务审核", "报销单财务看不到"))
        self.assertEqual(it["text"], "报销单提交后财务那边看不到，财务审核列表是空的")  # their words, checked against the message
        self.assertTrue(intake.understanding(it).startswith("我理解的是：员工提交报销单后"))
        self.assertEqual([q["slot"] for q in it["questions"]], ["q1"])
        a1, a2 = it["ac"][0], it["ac"][1]
        self.assertTrue(a1["open"] and not a2["open"], it["ac"])  # only what the question blocks waits
        self.assertTrue(any(a["text"] == "必须保持：报销单的提交和付款流程不变" for a in it["ac"]))
        self.assertEqual(s["state"], "asking")
        code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "answer", "answers": {"0": {"q1": "马上"}}, "wait": True})
        self.assertEqual(code, 200, s)
        it = s["items"][0]
        self.assertIn("系统应当马上在财务审核列表里显示这张单", it["ac"][0]["text"])  # read again with the answer
        self.assertFalse(any(a["open"] for a in it["ac"]))
        self.assertEqual((s["state"], it["questions"]), ("ready", []))
        self.assertEqual(it["slots"]["q1"]["value"], "马上")
        with mock.patch.object(self.P.flow, "submit") as sub:
            code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "confirm"})
        self.assertEqual(code, 200, s)
        t = self.P.store.ticket(s["tickets"][0])
        self.assertEqual((t["title"], t["type"]), ("报销单财务看不到", "bug"))
        self.assertEqual(sub.call_count, 1)
        rec = signoff.records(self.data, t["key"])[0]
        self.assertEqual((rec["kind"], rec["data"]["understood_by"]), ("intake", "智能体"))
        self.assertEqual(signoff.client_ac(self.data, t["key"])[0]["text"], it["ac"][0]["text"])
        self.assertIn("提交后，财务应该多久能在审核列表里看到？ 马上", t["body"])

    def test_whatever_the_agent_gets_wrong_the_rules_read_it(self):
        self.reading()
        for text, why in (("BROKEN " + EXPENSE, "items"), ("EXIT " + EXPENSE, "退出码")):
            code, s = self.call("POST", "/api/projects/OA/intake", {"text": text, "wait": True})
            self.assertEqual(code, 200, s)
            self.assertEqual(s["understood"]["by"], "规则", s["understood"])
            self.assertIn(why, s["understood"]["why"])
            self.assertEqual(s["items"][0]["slots"]["trigger"]["value"], "报销单提交后")
            self.assertEqual(s["state"], "asking")
        self.flow({"on": False, "understand": "agent", "understand_agent": "slow", "understand_timeout": 10})
        t0 = time.time()
        code, s = self.call("POST", "/api/projects/OA/intake", {"text": EXPENSE, "wait": True})
        self.assertLess(time.time() - t0, 40, "the reader's time limit holds")
        self.assertEqual(s["understood"]["by"], "规则")
        # a conversation whose reader vanished (a restart) is read by the rules once the time is up
        self.reading()
        code, s = self.call("POST", "/api/projects/OA/intake", {"text": EXPENSE, "model": False})
        f = intake.idir(self.data) / ("%s.json" % s["id"])
        x = json.loads(f.read_text(encoding="utf-8"))
        x.update(state="understanding", understanding_job={"agent": "reader", "t0": time.time() - 3600, "id": "gone"})
        f.write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.call("GET", "/api/intake/%s" % s["id"])[1]["state"], "asking")
        # the JSON is checked strictly
        for bad in ('{"items": []}', '{"items": [{"title": "x", "kind": "坏了", "restated": "我理解的是", "ac": [{"text": "当……"}]}]}',
                    '{"items": [{"title": "导出", "kind": "新功能", "restated": "我理解的是导出", "ac": [{"text": "调用 ExportService 导出"}]}]}',
                    '{"items": [{"title": "导出", "kind": "新功能", "restated": "我理解的是导出", "ac": []}]}', "没有 JSON"):
            with self.assertRaises(ValueError, msg=bad):
                intake.parse(bad)

    def test_a_big_requirement_read_by_the_agent_is_named_by_the_client_and_its_parts_are_not_duplicates(self):
        self.reading()
        code, s = self.call("POST", "/api/projects/OA/intake", {"text": OVERTIME, "wait": True})
        self.assertEqual((code, s["understood"]["by"], len(s["items"])), (200, "智能体", 4), s)
        self.assertEqual(sum(len(it["questions"]) for it in s["items"]), 1, "only what blocks building is asked")
        self.assertTrue(all(it["new_module"] and not it["flows"] for it in s["items"]))
        self.assertTrue(s["big"])
        spec = {"goal": "加班从申请到统计都在系统里走完", "keep": "现有功能和数据都不变", "out": "没有", "evidence": "两样都要"}
        code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "answer", "answers": {"spec": spec}})
        self.assertEqual(code, 200, s)
        with mock.patch.object(self.P.flow, "submit"):
            code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "confirm"})
        self.assertEqual(code, 200, s)
        par = self.P.store.ticket(s["epic"])
        self.assertEqual(par["title"], "大需求：加班管理")  # was: the answer to "目标"
        kids = [self.P.store.ticket(k) for k in s["children"]]
        self.assertEqual(kids[0]["title"], "员工提交加班申请")
        self.assertEqual(kids[0]["links"].get("open_ac"), 1)
        self.assertFalse(kids[1]["links"].get("open_ac"))
        for c in kids:
            code, r = self.call("GET", "/api/tickets/%s/similar" % c["key"])
            self.assertFalse({x["key"] for x in r["similar"]} & set(s["children"] + [par["key"]]), r)  # siblings are not duplicates
        # the open question of the first child goes to the client; their answer lets it go
        self.flow({"on": True, "agent": "fake", "understand": "agent", "understand_agent": "reader"})
        code, a = self.call("POST", "/api/tickets/%s/ask-client" % kids[0]["key"], {})
        self.assertEqual((code, a["questions"]), (200, 1), a)
        code, html = self.page(a["path"])
        self.assertIn("加班申请要填哪些内容？", html)
        self.assertNotIn("部门经理审批加班", html, "only this child's questions")
        with mock.patch.object(self.P.flow, "resume") as res:
            code, html = self.page(a["path"], {"a_0_q1": "日期、时长和事由", "name": "李经理"})
            self.assertEqual(code, 200, html)
            for _ in range(300):  # the reader rewrites the criteria with the answer, then the child goes on
                if res.call_count:
                    break
                time.sleep(0.05)
        self.assertEqual(res.call_count, 1, "released in batch 1 and nothing 待确认 left: on the line")
        c0 = self.P.store.ticket(kids[0]["id"])
        self.assertFalse(c0["links"].get("open_ac"), c0["links"])
        self.assertTrue(c0["body"].startswith("大需求「加班管理」"), "a child keeps its own head")
        self.assertIn("系统应当记录下来并能查到（填日期、时长和事由）", c0["body"])
        self.assertIn("（填日期、时长和事由）", signoff.client_ac(self.data, c0["key"])[0]["text"])
        self.assertEqual(intake.load(self.data, s["id"])["state"], "confirmed")

    # ------------------------------------------------------------ the client's questions

    def test_questions_go_to_the_client_and_their_answers_start_the_work(self):
        code, s = self.call("POST", "/api/projects/OA/intake", {"text": EXPENSE, "model": False})
        with mock.patch.object(self.P.flow, "submit"):
            code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "confirm"})
        key = s["tickets"][0]
        t = self.P.store.ticket(key)
        self.assertTrue(t["links"].get("open_ac"))
        self.assertEqual(self.call("POST", "/api/tickets/%s/ask-client" % key, {})[0], 200)
        code, a = self.call("POST", "/api/tickets/%s/ask-client" % key, {})  # a new link replaces the old one
        self.assertEqual(code, 200, a)
        old = [x for x in intake._asks(self.data).values() if x["session"] == s["id"]]
        self.assertEqual(sorted(bool(x["used"]) for x in old), [False, True])
        self.assertIn("把 ", self.P.store.events(t["id"])[-1]["body"])
        code, html = self.page(a["path"])
        self.assertEqual(code, 200)
        self.assertIn("报销单提交后财务那边看不到", html)  # their words
        self.assertIn("正确的结果应该是什么样？", html)
        self.assertNotIn("哪一块", html, "which flow is not the client's question")
        for w in ("EARS", "OA_", "flow:", "## "):
            self.assertNotIn(w, html)
        self.assertEqual(self.page(a["path"], {"name": "王总"})[0], 400, "at least one answer")
        self.flow({"on": True, "agent": "fake"})
        with mock.patch.object(self.P.flow, "resume") as res:
            code, html = self.page(a["path"], {"a_0_expected": "财务审核列表里马上出现这张单", "a_0_example": "李四提交 300 元报销，财务登录后看到", "name": "王总"})
        self.assertEqual(code, 200, html)
        self.assertIn("收到，谢谢", html)
        t = self.P.store.ticket(key)
        self.assertFalse(t["links"].get("open_ac"), t["links"])
        self.assertIn("系统应当财务审核列表里马上出现这张单", t["body"])
        self.assertEqual(res.call_count, 1, "nothing 待确认 left: on the line")
        rec = signoff.records(self.data, key)[-1]
        self.assertEqual((rec["kind"], rec["by"], rec["data"]["via"]), ("intake", "王总（客户）", "客户答复"))
        self.assertFalse(any(a["open"] for a in signoff.client_ac(self.data, key)))
        self.assertEqual(self.page(a["path"], {"a_0_expected": "再答一次"})[0], 410)
        self.assertEqual(self.page("/ask/" + "x" * 30)[0], 200)  # a page that says the link is wrong, not a crash
        self.assertEqual(self.call("POST", "/api/tickets/%s/ask-client" % key, {})[0], 409, "nothing left to ask")

    # ------------------------------------------------------------ the contract, through to the sign page

    def test_the_criteria_the_client_confirmed_are_what_the_package_checks_and_the_client_signs(self):
        code, s = self.call("POST", "/api/projects/OA/intake", {"text": EXPENSE, "model": False})
        ans = {"0": {"expected": "在财务审核列表里显示这张单", "example": "李四提交 300 元报销单，财务登录后在审核列表里看到"}}
        code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "answer", "answers": ans})
        if s["state"] != "ready":
            code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "answer", "answers": {
                "0": {q["slot"]: (q["options"][0] if q["options"] else "都是") for q in s["items"][0]["questions"]}}})
        self.assertEqual(s["state"], "ready", s["items"][0]["questions"])
        with mock.patch.object(self.P.flow, "submit"):
            code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "confirm"})
        key = s["tickets"][0]
        confirmed = signoff.client_ac(self.data, key)
        self.assertIn("在财务审核列表里显示这张单", confirmed[0]["text"])
        # the plan sees the contract
        code, r = self.call("POST", "/api/tickets/%s/runs" % key, {"agent": "team", "mode": "plan"})
        for _ in range(200):
            r = self.P.store.run(r["id"])
            if r["status"] not in ("queued", "running"):
                break
            time.sleep(0.05)
        self.assertIn("客户确认的验收标准", r["prompt"])
        self.assertIn(confirmed[0]["text"], r["prompt"])
        code, r = self.call("POST", "/api/tickets/%s/runs" % key, {"agent": "team", "mode": "fix"})
        for _ in range(400):
            r = self.P.store.run(r["id"])
            if r["status"] not in ("queued", "running"):
                break
            time.sleep(0.05)
        self.assertEqual(r["status"], "done", r["result"])
        code, d = self.call("POST", "/api/runs/%d/decide" % r["id"], {"decision": "accept"})
        self.assertEqual(code, 200, d)
        code, st = self.call("GET", "/api/tickets/%s/evidence" % key)
        snap = st["snapshot"]
        self.assertEqual(snap["ac_source"], "客户确认")
        self.assertEqual([a["text"] for a in snap["ac"]], [a["text"] for a in confirmed])  # not the plan's "提交后状态更新"
        self.assertEqual(snap["plan_ac"][0]["text"], "提交后状态更新")
        self.assertEqual(snap["asked"]["text"], "报销单提交后财务那边看不到，财务审核列表是空的。昨天开始的，财务部所有人。")
        pf = {p["id"]: p for p in st["proofs"]}
        self.assertEqual({p["kind"] for p in pf["A1"]["proofs"]}, {"test", "match", "preview"})
        self.assertEqual((pf["A1"]["state"], pf["A2"]["state"]), ("todo", "proven"))  # what must keep: shown by the tests
        code, ln = self.call("POST", "/api/tickets/%s/evidence" % key, {"kind": "link", "signer": "王总", "role": "财务负责人", "note": "先请王总看"})
        self.assertEqual(code, 200, ln)
        code, html = self.page(ln["path"])
        self.assertEqual(code, 200)
        plain = html.split("<details class=tech>")[0]
        self.assertIn("报销单提交后财务那边看不到", plain)  # what they asked for, in their words
        self.assertIn(confirmed[0]["text"], plain)
        self.assertIn("您确认过的标准", plain)
        self.assertNotIn("提交后状态更新", html)  # never the agent's plan text
        self.assertNotIn("跑请假测试", html)
        for w in ("## ", "EARS", "哈希", "验证门", "乙方复核"):
            self.assertNotIn(w, plain)  # all of that is folded under 技术细节
        self.assertIn("技术细节", html)
        self.assertIn("<h4>客户原话</h4>", html)  # the body as headings, not raw markdown
        self.assertNotIn(".java", html)
        self.assertIn("name='ac_A1' value=pass", html)
        code, body = self.page(ln["path"], {"action": "sign", "name": "王总", "ac_A1": "pass"})
        self.assertEqual(code, 400, "every criterion is ticked")
        code, body = self.page(ln["path"], {"action": "sign", "name": "王总", "ac_A1": "pass", "ac_A2": "pass"})
        self.assertEqual(code, 200, body)
        self.assertIn("已签收", body)
        rec = signoff.records(self.data, key)[-1]
        self.assertEqual((rec["kind"], rec["data"]["ac_source"]), ("sign", "客户确认"))
        self.assertEqual(rec["data"]["ac_text"]["A1"], confirmed[0]["text"])
        self.assertEqual(self.P.store.ticket(key)["status"], "closed")
        with urllib.request.urlopen(self.base + "/e/%s" % key) as r:
            full = r.read().decode("utf-8")
        self.assertIn("客户确认过的", full)
        self.assertIn("不作为验收依据", full)

    # ------------------------------------------------------------ 我来写

    def test_a_person_who_takes_a_ticket_gets_it_before_the_automatic_line(self):
        self.flow({"on": True, "agent": "slow"})
        try:
            code, t = self.call("POST", "/api/tickets", {"project": "OA", "title": "请假列表加导出", "body": "希望请假列表能导出 Excel", "handwork": True})
            self.assertEqual(code, 200, t)
            time.sleep(0.5)
            self.assertEqual(self.P.store.runs(ticket_id=t["id"]), [], "the line never touches a ticket claimed at birth")
            self.assertEqual((t["links"]["hold"], t["assignee"], t["type"]), ("tester", "tester", "feature"))
            self.assertIn("## 验收标准", t["body"])  # criteria read from the description, so the starter pack has them
            code, w = self.call("GET", "/api/tickets/%s/starter" % t["key"])
            self.assertIn("验收标准", w["markdown"])
            self.assertEqual(self.P.flow.next_step(self.P.store.ticket(t["id"]))[0], "")

            code, t2 = self.call("POST", "/api/tickets", {"project": "OA", "title": "审批通过后状态不对", "body": "审批通过后状态还是草稿"})
            self.assertEqual(t2["type"], "bug")
            for _ in range(200):
                runs = self.P.store.runs(ticket_id=t2["id"])
                if any(r["status"] == "running" for r in runs):
                    break
                time.sleep(0.05)
            self.assertTrue(runs, "the line picked it up")
            code, c = self.call("POST", "/api/tickets/%s/claim" % t2["key"], {})
            self.assertEqual(code, 200, c)
            self.assertEqual((c["links"]["hold"], c["assignee"], c["status"]), ("tester", "tester", "doing"))
            self.assertTrue(all(r["status"] == "cancelled" for r in self.P.store.runs(ticket_id=t2["id"])))
            self.assertIn("认领：我来写", self.P.store.events(t2["id"])[-1]["body"])
            self.assertEqual(self.P.flow.next_step(self.P.store.ticket(t2["id"]))[0], "")
        finally:
            self.flow({"on": False})
        # a confirmed item can be claimed before it is made, too
        code, s = self.call("POST", "/api/projects/OA/intake", {"text": "希望请假列表能导出 Excel", "model": False})
        self.flow({"on": True, "agent": "slow"})
        try:
            with mock.patch.object(self.P.flow, "submit") as sub:
                code, s = self.call("POST", "/api/intake/%s" % s["id"], {"action": "confirm", "hand": [0]})
            self.assertEqual(sub.call_count, 0)
            self.assertEqual(self.P.store.ticket(s["tickets"][0])["links"]["hold"], "tester")
        finally:
            self.flow({"on": False})


if __name__ == "__main__":
    unittest.main()
