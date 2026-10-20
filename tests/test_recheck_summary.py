"""A stale recheck never becomes a review/sign-off invitation in ticket summaries."""
import json
import shutil
import subprocess
import unittest
from unittest import mock

from tests import test_workbench_states as shared
from tmh.platform.server import api_ticket
from tmh.platform.ui import JS


class RecheckSummaryTest(unittest.TestCase):
    setUp = shared.WorkbenchStatesTest.setUp
    tearDown = shared.WorkbenchStatesTest.tearDown
    ticket = shared.WorkbenchStatesTest.ticket
    update = shared.WorkbenchStatesTest.update
    record_run = shared.WorkbenchStatesTest.record_run
    state = shared.WorkbenchStatesTest.state
    same_everywhere = shared.WorkbenchStatesTest.same_everywhere

    def test_current_recheck_wait_is_shared_by_inbox_ticket_requirements_and_client(self):
        t = self.update(self.ticket(), status="verify")
        r = self.record_run(t, status="done")
        self.P.store.update_run(r["id"], diff="diff --git a/F.java b/F.java\n+value\n")
        for op, expected, text in [
            ({"id": 8, "status": "running", "owner_active": True, "can_retry": False, "lifecycle": {"finished": False}}, "doing", "等待本次检查完成"),
            ({"id": 8, "status": "failed", "can_retry": True, "lifecycle": {"finished": True}}, "you", "重新验证已中断"),
            ({"id": 8, "status": "failed", "owner_active": False, "can_retry": False, "blocked": ["缺少回执"], "lifecycle": {"finished": False}}, "you", "检查停止回执"),
        ]:
            with self.subTest(op=op), mock.patch("tmh.platform.fixloop.verified", return_value={"check": "unknown", "verdict": "unknown", "verification_current": False, "recheck_operation": {"id": 8, "status": op["status"]}}), mock.patch("tmh.platform.recheck_operations.read_status", return_value=op):
                before = self.P.store.db.total_changes
                wanted = self.same_everywhere(t, expected, text)
                self.assertNotIn("改好了", wanted["why"])
                self.assertNotIn("等你审阅", wanted["why"])
                inbox = self.P.inbox(self.project)
                item = next(x for x in inbox["mine"] if x["key"] == t["key"])
                self.assertEqual(item["reason"], "recheck")
                self.assertFalse(any(x["key"] == t["key"] for x in inbox["others"]))
                d = api_ticket(self.P, None, t["key"])
                self.assertIs(d["runs"][0]["verify"]["verification_current"], False)
                self.assertEqual(d["runs"][0]["recheck_wait"]["why"], wanted["why"])
                self.assertEqual(self.P.store.db.total_changes, before, "summary GETs must not write recovery or start work")

    def test_invalid_recheck_blocks_automatic_commit_and_malformed_receipt_stays_unknown(self):
        t = self.update(self.ticket(), status="doing")
        r = self.record_run(t, status="done")
        self.P.store.update_run(r["id"], diff="diff --git a/F.java b/F.java\n+value\n")
        conf = dict(self.P.flow.autoflow(), on=True)
        with mock.patch("tmh.platform.fixloop.verified", return_value={"verification_current": False}), mock.patch("tmh.platform.recheck_operations.read_status", return_value={"status": "failed", "lifecycle": {"recovery": "damaged"}}):
            self.assertEqual(self.P.flow.next_step(t, conf)[0], "")
            self.assertIn("停止回执", self.P.flow.fix_gate(self.project, "+value", conf, r["id"]))
            self.assertEqual(self.P.flow.verification_wait(r["id"])["status"], "blocked")
        with mock.patch("tmh.platform.fixloop.verified", return_value={"check": "pass", "verification_current": True}):
            self.assertEqual(self.P.flow.verification_wait(r["id"]), {})

    @unittest.skipUnless(shutil.which("node"), "Node.js needed for shipped ticket summary")
    def test_ticket_next_action_never_offers_review_or_signoff_on_old_proof(self):
        helpers = "const FLOW=[" + JS.split("const FLOW=[", 1)[1].split("async function vTicket", 1)[0]
        script = r'''
const assert=require('node:assert/strict'),h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const S={meta:{autoflow:{on:true}}},moLabel=h,ago=()=>'';
''' + helpers + r'''
for(const status of ['running','failed','blocked'])for(const decision of ['', 'accepted:tmh/STATE-1@123456']){
 const d={ticket:{key:'STATE-1',status:'verify',links:{}},events:[],evidence:{refs:1},runs:[{id:1,mode:'fix',status:'done',decision,diff:'+value',verify:{verification_current:false,check:'unknown',verdict:'unknown'},recheck_wait:{status,why:status==='running'?'等待本次检查完成':'旧验证结果已失效；请检查停止回执'}}]};
 const flow=flowState(d),action=nextAction(d,flow);
 assert.equal(flow.review,false);assert.equal(action.acc,undefined);assert.ok(action.btns.includes('查看当前重新验证'));
 assert.ok(!action.text.includes('等你审阅'));assert.ok(!action.text.includes('等你验收'));assert.ok(!action.text.includes('转给验收人'));
 assert.ok(!action.btns.includes('naVerify'));assert.ok(vfy(d.runs[0]).includes('旧验证结果已失效'));
 assert.ok(!flow.sub.verify.includes('等验收'));
}
'''
        result = subprocess.run([shutil.which("node"), "-"], input=script, encoding="utf-8", errors="replace", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
