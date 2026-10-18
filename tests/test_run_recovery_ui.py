"""The public run view preserves stop evidence and follows the runner's retry policy."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh.platform.agents import Runner
from tmh.platform.errors import ApiError
from tmh.platform.server import api_retry_run, api_run
from tmh.platform.store import Store
from tmh.platform.ui import JS
from tests.test_ui_run_preview import ASYNC_HARNESS


class RunRecoveryApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-recovery-api-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        p = self.store.add_project("API", "恢复API测试", str(self.data))
        self.ticket = self.store.create_ticket(p["id"], "保留现有改动", "tester", auto=False)
        self.run = self.store.create_run(p["id"], self.ticket["id"], "fixture", "fix", "tester", "完整提示")
        self.store.update_run(self.run["id"], status="cancelled", output="原始输出\n完整末尾", diff="保留全部差异")
        self.runner = SimpleNamespace(retry_state=mock.Mock(return_value={"can_retry": False, "retry_blocked": ["仍在回收"],
            "delivery_id": "", "delivery_stage": ""}), retry=mock.Mock())
        self.P = SimpleNamespace(store=self.store, data_dir=self.data, runner=self.runner)
        self.req = SimpleNamespace(arg=lambda key: "3" if key == "since" else "", user="tester", body={})
        self.folder = self.data / "runs" / str(self.run["id"])
        self.folder.mkdir(parents=True)

    def test_get_returns_full_receipt_and_shared_policy_without_business_writes(self):
        receipt = {"started_at": "2026-10-18 20:00:00", "timeout_seconds": 600, "stopped_reason": "cancelled", "finished": False,
            "attempts": [{"attempt": 1, "returncode": 125, "cleanup": {"complete": False, "errors": ["完整错误" * 500]}}]}
        (self.folder / "lifecycle.json").write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
        before = self.store.db.total_changes
        result = api_run(self.P, self.req, str(self.run["id"]))
        self.assertEqual(result["lifecycle"], receipt)
        self.assertFalse(result["can_retry"])
        self.assertEqual(result["retry_blocked"], ["仍在回收"])
        self.assertEqual(result["output"], "原始输出\n完整末尾"[3:])
        self.assertEqual(result["output_len"], len("原始输出\n完整末尾"))
        self.runner.retry_state.assert_called_once_with(self.run["id"])
        self.assertEqual(self.store.db.total_changes, before)

    def test_missing_legacy_receipt_stays_unknown_and_uses_runner_policy(self):
        self.runner.retry_state.return_value.update(retry_blocked=["旧记录缺少回收证据"])
        result = api_run(self.P, self.req, str(self.run["id"]))
        self.assertIsNone(result["lifecycle"])
        self.assertEqual(result["lifecycle_error"], "")
        self.assertEqual(result["retry_blocked"], ["旧记录缺少回收证据"])

    def test_unreadable_receipt_cannot_offer_a_retry_or_claim_finished(self):
        self.runner.retry_state.return_value.update(can_retry=True, retry_blocked=[])
        for raw in (b"not-json", b"[]", b"\xff corrupt receipt"):
            with self.subTest(raw=raw):
                (self.folder / "lifecycle.json").write_bytes(raw)
                result = api_run(self.P, self.req, str(self.run["id"]))
                self.assertIsNone(result["lifecycle"])
                self.assertFalse(result["can_retry"])
                self.assertIn("回执不可读", result["lifecycle_error"])
                self.assertIn(result["lifecycle_error"], result["retry_blocked"])

    def test_retry_delegates_to_preserving_runner_and_returns_the_new_run(self):
        self.runner.retry.return_value = {"id": self.run["id"] + 1, "status": "queued"}
        self.assertEqual(api_retry_run(self.P, self.req, str(self.run["id"])), self.runner.retry.return_value)
        self.runner.retry.assert_called_once_with(self.run["id"], "tester")
        self.assertEqual(self.store.run(self.run["id"])["diff"], "保留全部差异")

    def test_real_runner_blocks_malformed_nested_receipts_without_breaking_get(self):
        self.P.runner = Runner(self.store, self.data)
        for attempts in (None, "damaged", [None], [{"pid": 123, "cleanup": "damaged"}]):
            with self.subTest(attempts=attempts):
                receipt = {"finished": True, "attempts": attempts}
                (self.folder / "lifecycle.json").write_text(json.dumps(receipt), encoding="utf-8")
                result = api_run(self.P, self.req, str(self.run["id"]))
                self.assertEqual(result["lifecycle"], receipt, "keep the complete original evidence readable")
                self.assertFalse(result["can_retry"])
                self.assertTrue(result["retry_blocked"])

    def test_delivery_retry_rejection_remains_a_state_conflict(self):
        self.runner.retry_state.return_value.update(delivery_id="a" * 12, delivery_stage="quality", retry_blocked=["请从交付阶段继续"])
        result = api_run(self.P, self.req, str(self.run["id"]))
        self.assertEqual((result["delivery_id"], result["delivery_stage"]), ("a" * 12, "quality"))
        self.runner.retry.side_effect = ValueError("请从交付阶段继续")
        with self.assertRaises(ApiError) as caught:
            api_retry_run(self.P, self.req, str(self.run["id"]))
        self.assertEqual(caught.exception.code, 409)
        self.assertIn("交付阶段", str(caught.exception))


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for shipped run recovery handlers")
class RunRecoveryUiTest(unittest.TestCase):
    def run_js(self, checks):
        source = JS.split("// ---------- runs\n", 1)[1].split("async function showPrompt", 1)[0]
        harness = ASYNC_HARNESS.replace("toast=()=>{}", "toast=message=>notifications.push(message)")
        script = r"""
const assert=require('node:assert/strict');
const h=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const notifications=[];
""" + harness + source + r"""
const stopped={...detail(7),status:'cancelled',exit_code:124,can_retry:false,retry_blocked:['进程还在回收'],
 lifecycle:{started_at:'2026-10-18 20:00:00',timeout_seconds:600,stopped_reason:'cancelled',attempts:[],finished:false}};
const finished={...stopped,can_retry:true,retry_blocked:[],lifecycle:{...stopped.lifecycle,finished:true,
 attempts:[{attempt:1,kind:'model',returncode:124,cleanup:{complete:true}}]}};
""" + "\n(async()=>{\n" + checks + "\n})().catch(e=>{console.error(e);process.exitCode=1});"
        result = subprocess.run([shutil.which("node"), "-"], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cancelled_run_keeps_polling_until_collection_finishes(self):
        self.run_js(r"""
let current=stopped;
getHandler=async url=>{assert.ok(!url.includes('/recheck'));return current};
await showRun(7);
assert.ok(body.innerHTML.includes('正在回收运行进程'));
assert.equal(body.querySelector('[data-run-resume]'),null);
assert.equal(S.polls.length,1);
current=finished;
await S.polls[0].fn();
assert.ok(body.innerHTML.includes('进程回收完成'));
assert.ok(body.querySelector('[data-run-resume]'));
assert.equal(S.polls.length,0,'polling stops only after lifecycle completion');
""")

    def test_stopping_toast_is_a_request_not_a_claim_of_cleanup(self):
        self.run_js(r"""
let current={...detail(7),status:'running',lifecycle:{...stopped.lifecycle,stopped_reason:''}};
getHandler=async()=>current;
postHandler=async(url,data)=>{assert.equal(url,'/api/runs/7/cancel');current=stopped;return current};
await showRun(7);
await body.querySelector('[data-run-cancel]').onclick();
assert.deepEqual(notifications,['已请求停止']);
assert.ok(body.innerHTML.includes('正在回收运行进程'));
assert.ok(!body.innerHTML.includes('进程回收完成'));
assert.equal(S.polls.length,1);
""")

    def test_retry_double_click_creates_one_run_and_opens_its_record(self):
        self.run_js(r"""
getHandler=async url=>url.includes('/8?')?{...detail(8),status:'running'}:finished;
const delayed=later();let calls=0;
postHandler=(url,data)=>{assert.equal(url,'/api/runs/7/retry');calls++;return delayed.promise};
await showRun(7);
const button=body.querySelector('[data-run-resume]');
const first=button.onclick();await button.onclick();
assert.equal(calls,1);assert.equal(button.disabled,true);
delayed.resolve({id:8,status:'queued'});await first;
assert.ok(body.innerHTML.includes('#8 '));
assert.ok(!body.innerHTML.includes('#7 '));
""")

    def test_late_retry_does_not_replace_a_different_open_run(self):
        self.run_js(r"""
getHandler=async url=>url.includes('/9?')?{...detail(9),status:'running'}:finished;
const delayed=later();postHandler=()=>delayed.promise;
await showRun(7);const pending=body.querySelector('[data-run-resume]').onclick();
await showRun(9);delayed.resolve({id:8,status:'queued'});await pending;
assert.ok(body.innerHTML.includes('#9 '));assert.ok(!body.innerHTML.includes('#8 '));
""")

    def test_retry_failure_keeps_original_record_and_allows_retry(self):
        self.run_js(r"""
getHandler=async()=>finished;postHandler=async()=>{throw new Error('保留快照失败，原现场仍在')};
await showRun(7);const button=body.querySelector('[data-run-resume]');await button.onclick();
assert.equal(button.disabled,false);assert.equal(button.textContent,'保留改动并重新运行');
assert.ok(body.innerHTML.includes('#7 '));
assert.equal(body.querySelector('[data-run-error]').textContent,'保留快照失败，原现场仍在');
""")

    def test_delivery_recovery_never_offers_generic_retry(self):
        self.run_js(r"""
const html=runRecoveryHtml({...finished,delivery_id:'abc123',delivery_stage:'quality',can_retry:true});
assert.ok(html.includes('href="#/delivery/abc123/quality"'));
assert.ok(html.includes('核对当前资料与复核条件'));
assert.ok(!html.includes('data-run-resume'));
""")

    def test_failed_changes_have_no_recheck_button_but_done_changes_do(self):
        self.run_js(r"""
let current={...finished,status:'failed'};let checks=0;
getHandler=async url=>{if(url.includes('/recheck')){checks++;return{running:false}}return current};
await showRun(7);assert.equal(body.querySelector('[data-run-recheck]'),null);assert.equal(checks,0);
current=detail(8);await showRun(8);assert.ok(body.querySelector('[data-run-recheck]'));assert.equal(checks,1);
""")

    def test_complete_receipt_is_escaped_without_truncating_failure_details(self):
        self.run_js(r"""
const full='保留原始错误'.repeat(1000)+'<script>end</script>';
const receipt={...finished.lifecycle,stopped_reason:'timeout',attempts:[{attempt:1,kind:'model',returncode:124,cleanup:{complete:false,errors:[full]}}]};
const html=runLifecycleHtml({...finished,lifecycle:receipt});
assert.ok(html.includes('达到整次任务总时限'));assert.ok(html.includes('600 秒'));
assert.ok(html.includes('退出码 124'));assert.ok(html.includes('回收未完成'));
assert.ok(html.includes(h(full)));assert.ok(!html.includes('<script>'));
assert.ok(html.includes(h(JSON.stringify(receipt,null,2))));
assert.equal(runLifecycleHtml(detail(1)),'');
assert.equal(runStillActive({...detail(1),status:'cancelled'}),false);
""")

    def test_malformed_attempts_leave_the_original_receipt_visible(self):
        self.run_js(r"""
for(const attempts of [null,'damaged',[null],['damaged'],[[]]]){
 const receipt={...finished.lifecycle,attempts};
 const html=runLifecycleHtml({...finished,lifecycle:receipt});
 assert.ok(html.includes('回执格式异常'));
 assert.ok(html.includes(h(JSON.stringify(receipt,null,2))));
 assert.ok(!html.includes('进程回收完成。'));
}
const missingCleanup=runLifecycleHtml({...finished,lifecycle:{...finished.lifecycle,attempts:[{attempt:1,pid:123,cleanup:'damaged'}]}});
assert.ok(missingCleanup.includes('尚无回收回执'));
assert.ok(!missingCleanup.includes('进程回收完成。'));
""")


if __name__ == "__main__":
    unittest.main()
