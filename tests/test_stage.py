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
    def test_boolean_handwork_is_not_a_person(self):
        t = T(handwork=True, hold=True)
        self.assertEqual(decide(t, ON)['label'], '待分配 在写')
        t['assignee'] = 'developer'
        self.assertEqual(decide(t, ON)['label'], 'developer 在写')
        t['links']['handwork'] = 'historical-owner'
        self.assertEqual(decide(t, ON)['label'], 'historical-owner 在写')
        self.assertEqual(decide(t, dict(ON, live={'mode':'fix','status':'running'}))['key'], 'running')

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
        self.assertEqual(decide(T("closed"), dict(f, version="v3"))["label"], "已上线 v3")

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
        self.assertEqual((g["key"], g["who"], g["label"]), ("signing", "client", "等王总签字"))
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
        self.assertEqual((g["key"], g["who"], g["label"]), ("idle", "person", "方案好了，等你决定怎么做"))
        g = decide(T("new"), dict(ON, auto=False, stall="自动处理关着，没人接手"))
        self.assertEqual((g["key"], g["who"], g["label"]), ("stalled", "person", "自动处理关着，没人接手"))

    def test_an_ops_ticket_waits_for_ops_not_the_automatic_line(self):
        g = decide(dict(T("new"), type="ops"), ON)
        self.assertEqual((g["key"], g["who"]), ("ops", "person"))
        self.assertEqual(decide(dict(T("new"), type="ops"), dict(ON, auto=False))["key"], "ops")
        self.assertEqual(decide(dict(T("new", open_ac=1), type="ops"), ON)["key"], "open_ac")

    def test_confirm_and_cancelled(self):
        self.assertEqual(decide(T("confirm"), ON)["key"], "confirm")
        self.assertEqual(decide(T("doing"), dict(ON, last={"mode": "fix", "status": "cancelled"}))["key"], "cancelled")

    def test_a_merge_waiting_on_a_person_outranks_closed_and_released(self):
        g = decide(T("closed"), dict(ON, version="v3", release_wait="验收通过了，还没合并进主干：这个项目不在全自动模式"))
        self.assertEqual((g["key"], g["who"], g["step"], g["state"]), ("release_waiting", "person", "closed", "done"))
        self.assertIn("全自动模式", g["note"])

    def test_an_adopted_change_waits_to_be_handed_to_acceptance(self):
        f = dict(ON, last={"mode": "fix", "status": "done", "dl": 10, "decision": "accepted:tmh/JB-1-r9@abc123"})
        g = decide(T("doing"), f)
        self.assertEqual((g["key"], g["who"], g["step"]), ("accepted", "person", "verify"))
        self.assertIn("tmh/JB-1-r9", g["label"])
        self.assertEqual(decide(T("verify"), f)["key"], "verify")
        self.assertEqual(decide(T("doing", hold="li"), f)["key"], "hold")
        rejected = dict(f, ev={"status": "rejected", "decision": {"via": "签收链接", "signer": "王总"}})
        self.assertEqual(decide(T("doing"), rejected)["key"], "returned")


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



class SurfacesAgreeTest(unittest.TestCase):
    """The inbox, the ticket API and the requirement/client state read one stage for the same ticket."""
    from tests.test_workbench_states import WorkbenchStatesTest as W
    setUp, tearDown, ticket, update, record_run, state, same_everywhere = (
        W.setUp, W.tearDown, W.ticket, W.update, W.record_run, W.state, W.same_everywhere)
    del W

    def check(self, t, reason, state, includes):
        from tmh.platform.server import api_ticket
        self.same_everywhere(t, state, includes)
        item = next(x for x in self.P.inbox(self.project)["mine"] if x["key"] == t["key"])
        g = api_ticket(self.P, None, t["key"])["stage"]
        self.assertEqual((item["reason"], item["label"]), (reason, g["label"]))
        self.assertEqual(g["key"], reason)

    def test_closed_ticket_whose_merge_waits(self):
        t = self.ticket()
        self.update(t, status="closed")
        self.P.store.event(t["id"], "自动流转", "flow", "验收通过了，还没合并进主干：这个项目不在全自动模式", {"release": "waiting"})
        self.check(t, "release_waiting", "done", "等你确认上线")
        self.assertEqual(self.P.inbox(self.project)["open"], 0)
        self.P.store.event(t["id"], "li", "release", "已合并进主干 main，版本 v1", {"version": "v1"})
        self.assertFalse(any(x["key"] == t["key"] for x in self.P.inbox(self.project)["mine"]))
        self.assertEqual(self.state(t)["state"], "shipped")

    def test_adopted_change_waiting_to_be_handed_on(self):
        t = self.update(self.ticket(), status="doing")
        r = self.record_run(t, status="done")
        self.P.store.update_run(r["id"], diff="+value\n", decision="accepted:tmh/STATE-1-r1@abc")
        self.check(t, "accepted", "you", "tmh/STATE-1-r1")


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class NextActionTest(unittest.TestCase):
    """The ticket page's next-step card is picked by the stage, not by a second chain of its own."""
    def run_js(self, body):
        from tmh.platform.ui import JS
        helpers = "const FLOW=[" + JS.split("const FLOW=[", 1)[1].split("async function vTicket", 1)[0]
        script = ("const assert=require('node:assert/strict'),h=s=>String(s??'');const S={meta:{autoflow:{on:true}}},moLabel=h,ago=()=>'';"
                  + helpers + "\nconst D=(status,stage,extra)=>Object.assign({ticket:{key:'T-1',status,links:{}},events:[],evidence:{refs:2},"
                  "runs:[],project:{key:'T'},stage},extra||{});const N=d=>nextAction(d,flowState(d));\n" + body)
        r = subprocess.run(["node", "-"], input=script, encoding="utf-8", capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_cards_follow_the_stage(self):
        self.run_js(r'''
let a=N(D('closed',{key:'release_waiting',who:'person',label:'验收通过了，还没合并进主干'},{events:[{id:1,kind:'flow',body:'验收通过了，还没合并进主干：要人来做',data:{release:'waiting'}}]}));
assert.match(a.btns,/naShip/);assert.match(a.text,/要人来做/);
a=N(D('closed',{key:'shipped',who:'none',label:'已出版本 v1'},{events:[{id:2,kind:'release',body:'已合并进主干 main，版本 v1',data:{}}]}));
assert.ok(!a.btns.includes('naShip'));assert.equal(a.tone,'ok');
a=N(D('doing',{key:'returned',who:'person',label:'王总退回了',note:'余额没刷新'}));
assert.match(a.text,/王总退回了/);assert.match(a.text,/余额没刷新/);assert.match(a.btns,/naPlan/);assert.equal(a.tone,'bad');
a=N(D('verify',{key:'signing',who:'client',label:'等王总签收'}));
assert.match(a.text,/^<b>等王总签收<\/b>。/);assert.equal(a.acc,true);
a=N(D('doing',{key:'running',who:'agent',label:'等待智能体开始修改代码'}));
assert.match(a.text,/等待智能体开始修改代码/);assert.ok(!a.acc);
const plan={id:3,mode:'plan',status:'done',agent:'opus'};
a=N(D('doing',{key:'hold',who:'person',label:'li 已接管，自动处理暂停'},{runs:[plan]}));
assert.match(a.text,/^<b>li 已接管，自动处理暂停<\/b>。修改方案已经出来了/);assert.match(a.btns,/naFix/);
a=N(D('doing',{key:'accepted',who:'person',label:'改动已提交到分支 b，等转待验证'},{runs:[{id:4,mode:'fix',status:'done',decision:'accepted:b@c',diff:'+x'}]}));
assert.match(a.btns,/naVerify/);
// the same ticket without a stage still gets a card (an old payload)
a=N(D('doing',undefined,{runs:[plan]}));assert.match(a.btns,/naFix/);
''')


if __name__ == "__main__":
    unittest.main()
