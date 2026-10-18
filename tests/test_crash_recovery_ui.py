"""Crash recovery receipts are stop evidence, never business success or implicit retries."""
import shutil
import unittest

from tests import test_run_recovery_ui as recovery_tests


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for shipped crash recovery handlers")
class CrashRecoveryUiTest(unittest.TestCase):
    run_js = recovery_tests.RunRecoveryUiTest.run_js

    def test_owner_loss_and_restart_explain_process_cleanup_without_claiming_success(self):
        self.run_js(r'''
for(const [reason,label] of [['owner_lost','平台连接中断，受管进程已停止'],['restarted','平台重启后恢复停止记录']]){
 const current={...finished,status:'failed',exit_code:125,lifecycle:{...finished.lifecycle,stopped_reason:reason,
  attempts:[{attempt:1,pid:4321,returncode:125,cleanup:{complete:true}}],recovery:{state:'complete',reason:'守护回执已核对',evidence:['attempt-1/receipt.json'],output_complete:true,errors:[]}}};
 getHandler=async()=>current;await showRun(7);
 assert.ok(body.innerHTML.includes(label));assert.ok(body.innerHTML.includes('不代表业务成功'));
 assert.ok(body.querySelector('[data-run-resume]'));assert.equal(body.querySelector('[data-run-decision="accept"]'),null);
 assert.equal(S.polls.length,0);
}
''')

    def test_blocked_receipt_has_no_spinner_or_retry_and_preserves_full_errors(self):
        self.run_js(r'''
const error='完整回收错误'.repeat(900)+'<script>最后</script>';
const receipt={...stopped.lifecycle,stopped_reason:'owner_lost',recovery:{state:'blocked',reason:error,evidence:['attempt-1/receipt.json'],output_complete:false,errors:[error]}};
const current={...stopped,status:'failed',can_retry:true,lifecycle:receipt};getHandler=async()=>current;await showRun(7);
assert.ok(body.innerHTML.includes('无法确认'));assert.ok(body.innerHTML.includes('不能重新运行'));assert.ok(body.innerHTML.includes('检查完整回执'));
assert.ok(!body.innerHTML.includes('正在回收运行进程'));assert.ok(!body.innerHTML.includes('class="spin"'));assert.equal(S.polls.length,0);
assert.equal(body.querySelector('[data-run-resume]'),null);assert.ok(body.querySelector('[data-run-recover]'));
assert.ok(body.innerHTML.includes(h(error)));assert.ok(!body.innerHTML.includes('<script>'));
assert.ok(body.innerHTML.includes(h(JSON.stringify(receipt,null,2))));assert.ok(body.innerHTML.includes('输出尚未确认完整'));
''')

    def test_incomplete_or_malformed_receipts_never_offer_retry_even_if_flag_is_true(self):
        self.run_js(r'''
for(const lifecycle of [null,{finished:true},{finished:true,attempts:[{pid:99}]},{finished:true,attempts:[{pid:99,cleanup:{complete:false}}]},
 {finished:true,attempts:'broken'},{finished:true,attempts:[null]},
 {...finished.lifecycle,recovery:{state:'blocked'}},{...finished.lifecycle,recovery:{state:'pending'}},
 {...finished.lifecycle,recovery:'damaged'},{...finished.lifecycle,stopped_reason:'recovery_pending'}]){
 const html=runRecoveryHtml({...finished,status:'failed',can_retry:true,lifecycle});
 assert.ok(!html.includes('data-run-resume'),JSON.stringify(lifecycle));assert.ok(html.includes('不能重新运行'));
}
''')

    def test_pending_recovery_polls_read_only_then_stops_when_blocked(self):
        self.run_js(r'''
let current={...stopped,status:'failed',can_retry:true,lifecycle:{...stopped.lifecycle,stopped_reason:'recovery_pending'}};
const calls=[];getHandler=async url=>{calls.push(url);return current};postHandler=()=>{throw new Error('GET polling must not POST recovery')};
await showRun(7);assert.ok(body.innerHTML.includes('平台重启后的停止回执尚未核对完成'));assert.equal(body.querySelector('[data-run-resume]'),null);assert.equal(S.polls.length,1);
current={...current,lifecycle:{...current.lifecycle,recovery:{state:'blocked',reason:'缺少持久回执',output_complete:false,errors:[]}}};
await S.polls[0].fn();assert.equal(S.polls.length,0);assert.ok(body.querySelector('[data-run-recover]'));
assert.ok(calls.every(url=>url.startsWith('/api/runs/7?')));assert.ok(body.innerHTML.includes('缺少持久回执'));
''')

    def test_manual_receipt_recheck_posts_once_and_preserves_ticket_drafts(self):
        self.run_js(r'''
const draft={comment:'保留未发送评论',note:'保留截图说明',file:{name:'原始截图.png'}};S.cur={ticket:{key:'APP-7'},draft};
let current={...stopped,status:'failed',lifecycle:{...stopped.lifecycle,recovery:{state:'blocked',reason:'等待完整回执',output_complete:false,errors:[]}}};
getHandler=async()=>current;const delayed=later();let calls=0;
postHandler=(url,data)=>{assert.equal(url,'/api/runs/7/recover');assert.deepEqual(data,{});calls++;return delayed.promise};
await showRun(7);const button=body.querySelector('[data-run-recover]');const pending=button.onclick();await button.onclick();assert.equal(calls,1);
current={...finished,status:'failed',lifecycle:{...finished.lifecycle,stopped_reason:'restarted',recovery:{state:'complete',reason:'已读取守护回执',output_complete:true,errors:[]}}};
delayed.resolve(current);await pending;assert.ok(body.querySelector('[data-run-resume]'));assert.equal(body.querySelector('[data-run-recover]'),null);
assert.equal(S.cur.draft,draft);assert.equal(draft.comment,'保留未发送评论');assert.equal(draft.file.name,'原始截图.png');
''')

    def test_manual_recheck_error_and_late_response_keep_the_current_view(self):
        self.run_js(r'''
const blocked={...stopped,status:'failed',lifecycle:{...stopped.lifecycle,recovery:{state:'blocked',reason:'回执不完整',output_complete:false,errors:[]}}};
getHandler=async url=>url.includes('/9?')?{...detail(9),status:'running'}:blocked;
postHandler=async()=>{throw new Error('完整核对错误 <保留>')};await showRun(7);const button=body.querySelector('[data-run-recover]');await button.onclick();
assert.equal(button.disabled,false);assert.equal(body.querySelector('[data-run-error]').textContent,'完整核对错误 <保留>');
const delayed=later();postHandler=()=>delayed.promise;const pending=button.onclick();await showRun(9);delayed.resolve(finished);await pending;
assert.ok(body.innerHTML.includes('#9 '));assert.ok(!body.innerHTML.includes('#7 '));assert.ok(!body.querySelector('[data-run-resume]'));
''')
