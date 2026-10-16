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
