import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from tmh.platform import stage
from tmh.platform.stage import decide

ON = {"auto": True, "agent": "codex", "next_step": lambda t: "analyze"}


def T(status="doing", **links):
    return {"id": 1, "status": status, "links": links, "assignee": ""}


class TableTest(unittest.TestCase):
    def test_every_row_is_known_and_once(self):
        keys = [r[0] for r in stage.TABLE]
        self.assertEqual(len(keys), len(set(keys)))
        for _, who, step, label, _ in stage.TABLE:
            self.assertIn(who, ("person", "client", "agent", "assignee", "none"))
            self.assertIn(step, ("", "intake", "analyze", "plan", "fix", "verify", "closed"))
            self.assertTrue(label)

    def test_closed_wins_over_everything(self):
        f = dict(ON, live={"mode": "fix", "status": "running"}, last={"status": "failed"})
        self.assertEqual(decide(T("closed", hold="li"), f)["key"], "closed")
        self.assertEqual(decide(T("closed"), dict(f, version="v3"))["label"], "已出版本 v3")

    def test_a_live_run_wins_over_waiting_on_people(self):
        g = decide(T("verify", hold="li", open_ac=2), dict(ON, live={"mode": "fix", "status": "running"}))
        self.assertEqual((g["key"], g["who"], g["step"]), ("running", "agent", "fix"))
        self.assertIn("当前步骤结束后暂停", g["label"])

    def test_open_criteria_wait_on_the_client_before_the_automatic_line(self):
        g = decide(T("new", open_ac=2), ON)
        self.assertEqual((g["key"], g["who"]), ("open_ac", "client"))
        self.assertEqual(decide(T("new", open_ac=2, client_change=1), ON)["key"], "client_change")

    def test_stale_verification_wins_over_review_and_acceptance(self):
        f = dict(ON, last={"mode": "fix", "status": "done", "dl": 10}, wait={"why": "旧结果失效", "state": "doing"})
        g = decide(T("verify"), f)
        self.assertEqual((g["key"], g["label"], g["state"]), ("recheck", "旧结果失效", "doing"))

    def test_review_before_acceptance(self):
        f = dict(ON, last={"mode": "fix", "status": "done", "dl": 10, "decision": ""})
        self.assertEqual(decide(T("verify"), f)["key"], "review")
        f["last"]["decision"] = "accepted:auto"
        g = decide(T("verify"), f)
        self.assertEqual((g["key"], g["who"], g["step"]), ("verify", "person", "verify"))
        f["last"] = {"mode": "fix", "status": "done", "dl": 0}  # no change made: nothing to review
        self.assertEqual(decide(T("verify"), f)["key"], "verify")

    def test_signing_and_expired_links(self):
        link = {"signer": "王总", "expires": "2099-01-01 00:00:00", "ts": "2026-01-01"}
        g = decide(T("verify"), dict(ON, ev={"status": "ready", "links": [link]}))
        self.assertEqual((g["key"], g["who"], g["label"]), ("signing", "client", "等王总签收"))
        g = decide(T("verify"), dict(ON, ev={"status": "ready", "links": [dict(link, expires="2000-01-01")]}))
        self.assertEqual((g["key"], g["who"]), ("expired", "person"))

    def test_returned_by_client_versus_rejected_by_team(self):
        ev = {"status": "rejected", "decision": {"via": "签收链接", "signer": "王总", "note": "不对"}}
        self.assertEqual(decide(T("doing"), dict(ON, ev=ev))["key"], "returned")
        ev["decision"]["via"] = "平台"
        self.assertEqual(decide(T("doing"), dict(ON, ev=ev))["key"], "rejected")

    def test_failed_run_waits_on_a_person_even_when_taken_over(self):
        g = decide(T("doing", hold="li"), dict(ON, last={"mode": "plan", "status": "failed"}))
        self.assertEqual((g["key"], g["who"], g["step"]), ("failed", "person", "plan"))

    def test_take_over_stops_the_automatic_line(self):
        g = decide(T("doing", hold="li"), dict(ON, last={"mode": "analyze", "status": "done"}))
        self.assertEqual((g["key"], g["who"]), ("hold", "person"))
        self.assertEqual(decide(T("doing", handwork="李工"), ON)["who"], "assignee")
        g = decide(T("doing", handwork="李工"), dict(ON, check={"verdict": "fail"}))
        self.assertEqual((g["key"], g["who"]), ("handwork_failed", "person"))

    def test_automatic_line_queue_versus_nothing_to_do(self):
        self.assertEqual(decide(T("new"), ON)["key"], "queued")
        self.assertEqual(decide(T("new"), dict(ON, next_step=lambda t: ""))["key"], "queued")  # untouched: the line picks it up
        self.assertEqual(decide(T("new", later="等前一批"), ON)["key"], "later")
        g = decide(T("doing"), dict(ON, next_step=lambda t: "", last={"mode": "plan", "status": "done"}))
        self.assertEqual((g["key"], g["who"], g["label"]), ("idle", "person", "方案已完成，等你决定如何实现"))
        g = decide(T("new"), dict(ON, auto=False, stall="自动处理关着，没人接手"))
        self.assertEqual((g["key"], g["who"], g["label"]), ("stalled", "person", "自动处理关着，没人接手"))

    def test_confirm_and_cancelled(self):
        self.assertEqual(decide(T("confirm"), ON)["key"], "confirm")
        self.assertEqual(decide(T("doing"), dict(ON, last={"mode": "fix", "status": "cancelled"}))["key"], "cancelled")


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class StepperTest(unittest.TestCase):
    def test_bar_marks_the_stage_step_and_who(self):
        from tmh.platform import ui
        src = Path(ui.__file__).read_text(encoding="utf-8")
        flow = re.search(r"const FLOW=\[.*?\];", src).group(0)
        who = re.search(r"const WHO=\{.*?\};", src).group(0)
        fn = re.search(r"function stepper\(f\)\{.*?\n", src).group(0)
        st = {k: "todo" for k in ("intake", "analyze", "plan", "fix", "verify", "closed")}
        f = {"st": dict(st, intake="done"), "sub": {}, "stage": {"step": "verify", "who": "person", "label": "改好了，等你验收"}}
        js = ("const h=s=>String(s??'');%s%s%s\nconst f=%s;process.stdout.write(stepper(f));" % (flow, who, fn, json.dumps(f)))
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.count('class="who'), 1)
        self.assertRegex(out, r'<li class="todo now" title="改好了，等你验收">.*?<b>验收</b><em class="who person">等你</em>')
        f["stage"] = {"key": "closed", "step": "closed", "who": "none", "label": "已关闭"}
        out = subprocess.run(["node", "-e", "const h=s=>String(s??'');%s%s%s\nprocess.stdout.write(stepper(%s));" % (flow, who, fn, json.dumps(f))],
                             capture_output=True, text=True, check=True).stdout
        self.assertNotIn("now", out)


if __name__ == "__main__":
    unittest.main()
