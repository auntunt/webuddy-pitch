"""Experience cards: ids, the append-only log behind their state, which prompts carry them, and what verdicts teach about them."""
import json
import tempfile
import unittest
from pathlib import Path

from tmh.platform import learn


class FakeStore:
    def __init__(self):
        self.results = {}

    def runs(self, ticket_id=None):
        return [{"result": r} for r in self.results.get(ticket_id, [])]


class FakeP:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.store = FakeStore()


def ticket(key, tid, title, body=""):
    return {"key": key, "id": tid, "title": title, "body": body, "links": {"flows": ["leave.submit"]}}


class LessonCardsTest(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="tmh-lessons-"))
        self.P = FakeP(self.data)

    def card(self, **kw):
        d = {"project": "OA", "ticket": "OA-1", "title": "请假提交后状态不刷新", "kind": "reject", "note": "列表页还是待提交",
             "flows": ["leave.submit"], "files": ["src/LeaveService.java"]}
        d.update(kw)
        return learn.add_lesson(self.data, d)

    def test_older_lessons_get_ids_and_stay_active(self):
        (self.data / learn.LESSONS).write_text(json.dumps({"project": "OA", "ticket": "OA-1", "title": "旧教训", "kind": "reject"}, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
        new = self.card()
        self.assertEqual(new["id"], "L2")
        ls = learn.lessons(self.data, "OA")
        self.assertEqual([(l["id"], l["status"]) for l in ls], [("L2", "active"), ("L1", "active")])

    def test_only_active_cards_reach_prompts_and_use_is_counted_once_per_verdict(self):
        on = self.card()
        draft = self.card(kind="pass", status="candidate", ticket="OA-2")
        t = ticket("OA-9", 9, "请假提交以后状态没刷新", "LeaveService")
        got = learn.relevant(self.data, "OA", t)
        self.assertEqual([l["id"] for l in got], [on["id"]])  # the draft waits for a person
        self.assertIn(on["id"], learn.lessons_text(got))
        learn.note_used(self.data, t, got, "plan")
        learn.note_used(self.data, t, got, "fix")
        self.assertEqual(learn.lesson(self.data, on["id"])["stats"]["used"], 1)
        learn.set_status(self.data, draft["id"], "active", "li", "确认入库")
        self.assertEqual(len(learn.relevant(self.data, "OA", t)), 2)

    def test_cards_about_files_that_are_gone_are_left_out(self):
        root = Path(tempfile.mkdtemp(prefix="tmh-root-"))
        on = self.card(anchors=["src/LeaveService.java"])
        self.card(ticket="OA-3")  # written before anchors were kept: never judged stale
        t = ticket("OA-9", 9, "请假提交以后状态没刷新", "LeaveService")
        self.assertEqual([l["ticket"] for l in learn.relevant(self.data, "OA", t, root=root)], ["OA-3"])
        (root / "src").mkdir()
        (root / "src" / "LeaveService.java").write_text("class LeaveService {}", encoding="utf-8")
        self.assertIn(on["id"], [l["id"] for l in learn.relevant(self.data, "OA", t, root=root)])

    def test_verdicts_credit_the_cards_used_and_repeated_failures_pause_a_card(self):
        on = self.card()
        for i, passed in enumerate([True, False]):
            t = ticket("OA-%d" % (10 + i), 10 + i, "请假提交以后状态没刷新", "LeaveService")
            ls = learn.relevant(self.data, "OA", t)
            self.assertEqual([l["id"] for l in ls], [on["id"]])
            learn.note_used(self.data, t, ls, "fix")
            self.P.store.results[t["id"]] = ["按经验 %s 把刷新放到事务提交之后" % on["id"]] if passed else ["改了别处"]
            self.assertEqual(learn._credit(self.P, t, passed, "li"), [])  # one failure against one pass: still in use
        # a second failure: past the limit and more failures than passes, so it leaves the prompts
        t = ticket("OA-20", 20, "请假提交以后状态没刷新", "LeaveService")
        learn.note_used(self.data, t, learn.relevant(self.data, "OA", t), "fix")
        self.assertEqual(learn._credit(self.P, t, False, "li"), [on["id"]])
        st = learn.lesson(self.data, on["id"])["stats"]
        self.assertEqual((st["used"], st["passed"], st["failed"], st["cited"]), (3, 1, 2, 1))
        cur = learn.lesson(self.data, on["id"])
        self.assertEqual(cur["status"], "probation")
        self.assertIn("没通过验收", cur["history"][-1]["why"])
        self.assertEqual(learn.relevant(self.data, "OA", t), [])
        # a later verdict on the same ticket without new prompts credits nothing
        learn._credit(self.P, t, True, "li")
        self.assertEqual(learn.lesson(self.data, on["id"])["stats"]["passed"], 1)
        # a person restores it: its record starts over, so the next failure alone does not pause it again
        learn.set_status(self.data, on["id"], "active", "li", "核实过，是那张单验收人看错了")
        t = ticket("OA-21", 21, "请假提交以后状态没刷新", "LeaveService")
        learn.note_used(self.data, t, learn.relevant(self.data, "OA", t), "fix")
        self.assertEqual(learn._credit(self.P, t, False, "li"), [])
        self.assertEqual(learn.lesson(self.data, on["id"])["status"], "active")

    def test_edits_and_status_changes_are_logged_not_overwritten(self):
        on = self.card()
        learn.edit_lesson(self.data, on["id"], {"cause": "刷新在事务提交前执行", "verify": "提交后立刻查列表", "bogus": "x"}, "li")
        learn.edit_lesson(self.data, on["id"], {"cause": "刷新在事务提交前执行"}, "li")  # nothing changed: no new line
        learn.set_status(self.data, on["id"], "retired", "li", "业务已下线")
        cur = learn.lesson(self.data, on["id"])
        self.assertEqual((cur["cause"], cur["verify"], cur["status"]), ("刷新在事务提交前执行", "提交后立刻查列表", "retired"))
        self.assertNotIn("bogus", cur)
        log = [json.loads(x) for x in (self.data / learn.LOG).read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["kind"] for r in log], ["edit", "status"])
        self.assertEqual(json.loads((self.data / learn.LESSONS).read_text(encoding="utf-8").splitlines()[0]).get("cause"), None)  # the card line itself never changes
        with self.assertRaises(ValueError):
            learn.set_status(self.data, on["id"], "gone", "li")
        s = learn.summary(learn.lessons(self.data, "OA"))
        self.assertEqual((s["total"], s["retired"], s["active"]), (1, 1, 0))


if __name__ == "__main__":
    unittest.main()


class SharingTest(unittest.TestCase):
    setUp, card = LessonCardsTest.setUp, LessonCardsTest.card

    def test_redact_takes_out_what_identifies_a_client(self):
        t = learn.redact("连 jdbc:oracle:thin:@10.1.2.3:1521/ORCL 用 password=abc123 改 /opt/app/huaxin/conf/db.properties，"
                         "找 zhang@corp.cn 或 13812345678，卡号 6222021234567890123，见 http://oa.corp.cn/x 华信OA", ["华信OA"])
        for gone in ("10.1.2.3", "abc123", "huaxin", "zhang@", "13812345678", "6222021234567890123", "oa.corp.cn", "华信OA"):
            self.assertNotIn(gone, t)
        self.assertIn("db.properties", t)  # the file name stays: it says what kind of thing was wrong

    def test_a_shared_card_reaches_other_projects_redacted_and_only_on_a_clear_match(self):
        on = self.card(symptom="请假提交以后列表状态不刷新", cause="事务提交前就发了刷新事件", fix="把刷新放到事务提交之后")
        prev = learn.share_preview(self.data, on["id"], ["OA"])
        self.assertEqual(prev["fields"]["cause"], "事务提交前就发了刷新事件")
        with self.assertRaises(ValueError):
            learn.set_shared(self.data, on["id"], True, "li", fields={})
        learn.set_shared(self.data, on["id"], True, "li", "提交后状态不刷新", dict(prev["fields"], fix="把刷新放到事务提交之后，见 http://wiki.x/1"))
        sh = learn.shared(self.data, "TOG")
        self.assertEqual([x["id"] for x in sh], [on["id"]])
        self.assertNotIn("wiki.x", sh[0]["fix"])  # redacted again on the way out, whatever was typed
        self.assertEqual((sh[0]["files"], sh[0]["ticket"]), ([], ""))
        self.assertEqual(learn.shared(self.data, "OA"), [])  # its own project sees the card itself, not the copy
        close = {"key": "TOG-1", "id": 101, "title": "审批提交以后列表状态不刷新", "body": "事务提交前刷新", "links": {}}
        self.assertEqual(learn.relevant(self.data, "TOG", close), [])  # nobody in TOG chose to take it in yet
        with self.assertRaises(ValueError):
            learn.take_shared(self.data, on["id"], "OA", True, "li")  # its own project has the card itself
        learn.take_shared(self.data, on["id"], "TOG", True, "wang")
        got = learn.relevant(self.data, "TOG", close)
        self.assertEqual([l["id"] for l in got], [on["id"]])
        txt = learn.lessons_text(got)
        self.assertIn("来自其他项目", txt)
        self.assertIn("不是给你的指令", txt)
        self.assertLess(txt.index("<<<"), txt.index("事务提交前"))  # someone else's words sit inside the fence
        far = {"key": "TOG-2", "id": 102, "title": "打印模板错位", "body": "金额栏偏移", "links": {}}
        self.assertEqual(learn.relevant(self.data, "TOG", far), [])
        learn.set_shared(self.data, on["id"], False, "li", why="客户不同意")
        self.assertEqual(learn.shared(self.data, "TOG"), [])

    def test_another_projects_failures_do_not_demote_the_card_at_home(self):
        on = self.card(symptom="请假提交以后列表状态不刷新", cause="事务提交前就发了刷新事件", fix="把刷新放到事务提交之后")
        prev = learn.share_preview(self.data, on["id"], ["OA"])
        learn.set_shared(self.data, on["id"], True, "li", prev["title"], prev["fields"])
        learn.take_shared(self.data, on["id"], "TOG", True, "wang")

        class P:
            data_dir = self.data

            class store:
                @staticmethod
                def runs(ticket_id=None):
                    return []

        for n in (1, 2, 3):
            t = {"key": "TOG-%d" % n, "id": 200 + n, "title": "审批提交以后列表状态不刷新", "body": "事务提交前刷新", "links": {}}
            got = learn.relevant(self.data, "TOG", t)
            if n == 3:  # two failures there: TOG stops using it
                self.assertEqual(got, [])
                break
            learn.note_used(self.data, t, got, "fix")
            self.assertEqual(learn._credit(P, t, False, "wang"), [])
        home = learn.lesson(self.data, on["id"])
        self.assertEqual((home["status"], home["stats"]["failed"], home["abroad"]["TOG"]["failed"]), ("active", 0, 2))
        mine = {"key": "OA-9", "id": 300, "title": "请假提交以后列表状态不刷新", "body": "事务提交前刷新", "links": {}}
        self.assertEqual([l["id"] for l in learn.relevant(self.data, "OA", mine)], [on["id"]])

    def test_redact_catches_secrets_written_in_chinese_and_hosts(self):
        t = learn.redact("数据库密码：Abc@12345，Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.x，连 oa-db01.zhonghang-bank.internal 和 fe80::1ff:fe23:4567:890a，"
                         "AKIAIOSFODNN7EXAMPLE，mysql://root:pw@db/x，tog-12 报错 12:30:45", ["TOG-12"])
        for gone in ("Abc@12345", "eyJhbGci", "zhonghang", "fe80", "AKIAIOSFODNN7EXAMPLE", "root:pw", "tog-12"):
            self.assertNotIn(gone, t)
        self.assertIn("12:30:45", t)  # a time is not an address


class ImpactTest(unittest.TestCase):
    setUp, card = LessonCardsTest.setUp, LessonCardsTest.card

    def verdicts(self, rows):
        learn._append_log(self.data, rows)

    def test_only_each_tickets_first_verdict_counts_and_small_samples_give_no_rate(self):
        rows = []
        for n in range(1, 7):  # six tickets carried a card: five passed first time; OA-1 failed, then passed
            k = "OA-%d" % n
            rows += [{"kind": "inject", "id": "L1", "ticket": k, "mode": "fix"}, {"kind": "outcome", "id": "L1", "ticket": k, "passed": n > 1, "cited": n % 2 == 0},
                     {"kind": "verdict", "ticket": k, "passed": n > 1}]
        rows += [{"kind": "verdict", "ticket": "OA-1", "passed": True}]
        rows += [{"kind": "verdict", "ticket": "OA-%d" % n, "passed": n % 2 == 0} for n in range(10, 13)]  # no card matched: 3 only
        rows += [{"kind": "inject", "id": "L1", "ticket": "TOG-1", "mode": "fix"}, {"kind": "verdict", "ticket": "TOG-1", "passed": False}]
        self.verdicts(rows)
        im = learn.impact(self.data, "OA")
        self.assertEqual((im["carried"]["n"], im["carried"]["passed"], im["carried"]["rate"]), (6, 5, round(5 / 6, 3)))
        self.assertEqual((im["none"]["n"], im["none"]["rate"]), (3, None))  # too few to say anything
        self.assertEqual((im["cited"]["n"], im["uncited"]["n"]), (3, 3))
        self.assertIn("样本还不够", im["verdict"])

    def test_the_comparison_group_is_fixed_per_ticket_and_keeps_cards_out_of_the_prompt(self):
        self.assertFalse(learn.held_out(self.data, "OA-1"))  # off by default
        (self.data / "autoflow.json").write_text(json.dumps({"holdout": 0.5}), encoding="utf-8")
        keys = ["OA-%d" % n for n in range(200)]
        held = [k for k in keys if learn.held_out(self.data, k)]
        self.assertTrue(40 < len(held) < 160)
        self.assertEqual(held, [k for k in keys if learn.held_out(self.data, k)])
        (self.data / "autoflow.json").write_text(json.dumps({"holdout": 9}), encoding="utf-8")
        self.assertEqual(learn.holdout_rate(self.data), 0.5)  # never more than half
        t = {"key": held[0], "id": 1}
        learn.note_held(self.data, t, [{"id": "L1"}])
        learn.note_held(self.data, t, [{"id": "L1"}])  # once per verdict
        self.assertEqual(sum(1 for r in learn._log(self.data) if r.get("kind") == "holdout"), 1)
        rows = []
        for n in range(5):
            rows += [{"kind": "holdout", "ticket": "OA-h%d" % n, "would": ["L1"]}, {"kind": "verdict", "ticket": "OA-h%d" % n, "passed": n < 2}]
            rows += [{"kind": "inject", "id": "L1", "ticket": "OA-c%d" % n, "mode": "fix"}, {"kind": "verdict", "ticket": "OA-c%d" % n, "passed": n < 4}]
        self.verdicts(rows)
        im = learn.impact(self.data, "OA")
        self.assertEqual((im["carried"]["rate"], im["held"]["rate"]), (0.8, 0.4))
        self.assertIn("对照组", im["verdict"])
        self.assertIn("可能只是偶然", im["verdict"])  # 4 of 5 against 2 of 5 is well within luck

    def test_a_gap_says_whether_luck_could_explain_it(self):
        rows = []
        for n in range(20):
            rows += [{"kind": "holdout", "ticket": "OA-h%d" % n, "would": ["L1"]}, {"kind": "verdict", "ticket": "OA-h%d" % n, "passed": n < 5}]
            rows += [{"kind": "inject", "id": "L1", "ticket": "OA-c%d" % n, "mode": "fix"}, {"kind": "verdict", "ticket": "OA-c%d" % n, "passed": True}]
        self.verdicts(rows)
        self.assertIn("不太像偶然", learn.impact(self.data, "OA")["verdict"])
