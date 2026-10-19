"""Drive shipped UI with persisted recheck operations without running a model/server."""
import shutil
import unittest

from tests import test_ui_run_preview as preview_tests


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for shipped recheck handlers")
class RecheckLifecycleUiTest(unittest.TestCase):
    def run_js(self, checks):
        setup = r'''
const oldProof={check:'pass',verdict:'pass',commands:[{kind:'test',command:'old test',exit_code:0,output:'OLD PROOF'}]};
const receipt={finished:true,attempts:[{attempt:1,pid:9876,returncode:125,cleanup:{complete:true}}],stopped_reason:'owner_lost',
 recovery:{state:'complete',reason:'已核对受管进程',errors:[],output_complete:true}};
const operation={id:21,source_run:7,status:'failed',can_retry:true,result:'重新验证因平台中断而失败',output:'完整重新验证输出',lifecycle:receipt};
let current={...detail(7),verification:oldProof},state={running:false,operation};
getHandler=async url=>url.endsWith('/recheck')?state:current;
'''
        preview_tests.RunPreviewUiTest.run_js(self, setup + checks, controller=True)

    def test_failed_recheck_keeps_original_done_but_invalidates_old_proof_and_adoption(self):
        self.run_js(r'''
await showRun(7);
assert.equal(current.status,'done');assert.equal(current.verification.check,'pass');
assert.ok(body.innerHTML.includes('重新验证已中断'));
assert.ok(body.innerHTML.includes('旧验证结果已失效'));
assert.ok(body.innerHTML.includes('上次验证记录（仅供历史参考）'));
assert.ok(body.innerHTML.includes('OLD PROOF'));assert.ok(body.innerHTML.includes(h(operation.output)));
assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,true);
assert.equal(body.querySelector('[data-run-recheck]').disabled,false);assert.equal(S.polls.length,0);
let posts=0;postHandler=async()=>{posts++};await body.querySelector('[data-run-decision="accept"]').onclick();assert.equal(posts,0);
''')

    def test_blocked_recheck_stops_polling_preserves_full_escaped_receipts_and_disables_actions(self):
        self.run_js(r'''
const full='完整输出'.repeat(1000)+'<script>不可执行</script>';
state={running:true,operation:{...operation,can_retry:true,output:full,result:full,lifecycle:{...receipt,finished:false,
 recovery:{state:'blocked',reason:full,errors:[full],output_complete:false}}}};
await showRun(7);assert.equal(S.polls.length,0);assert.ok(!body.innerHTML.includes('class="spin"'));
assert.ok(body.innerHTML.includes('重新验证停止回执不完整'));assert.ok(body.innerHTML.includes(h(full)));
assert.ok(!body.innerHTML.includes('<script>'));assert.ok(body.innerHTML.includes(h(JSON.stringify(state.operation,null,2))));
assert.equal(body.querySelector('[data-run-recheck]').disabled,true);
assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,true);
assert.ok(body.querySelector('[data-run-recheck-recover]'));assert.ok(body.innerHTML.includes('不代表业务成功'));
''')

    def test_running_recheck_polls_get_only_and_updates_interruption_without_infinite_spinner(self):
        self.run_js(r'''
state={running:true,operation:{...operation,status:'running',can_retry:false,lifecycle:{finished:false,attempts:[]},output:'进行中输出'}};
let posts=0;postHandler=async()=>{posts++;throw new Error('GET must not write')};
await showRun(7);assert.equal(S.polls.length,1);assert.equal(body.querySelector('[data-run-recheck]').disabled,true);
assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,true);assert.ok(body.innerHTML.includes('进行中输出'));
state={running:false,operation};await S.polls[0].fn();assert.equal(S.polls.length,0);assert.equal(posts,0);
assert.ok(body.innerHTML.includes('重新验证已中断'));assert.equal(body.querySelector('[data-run-recheck]').disabled,false);
''')

    def test_missing_cleanup_never_allows_new_recheck_even_when_server_flag_is_true(self):
        self.run_js(r'''
for(const lifecycle of [null,{finished:true},{finished:true,attempts:[{pid:99}]},{finished:true,attempts:[{pid:99,cleanup:{complete:false}}]}]){
 state={running:false,operation:{...operation,lifecycle}};await showRun(7);
 assert.equal(body.querySelector('[data-run-recheck]').disabled,true,JSON.stringify(lifecycle));
 assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,true);
}
''')

    def test_explicit_receipt_recovery_posts_once_and_keeps_drafts(self):
        self.run_js(r'''
state={running:false,operation:{...operation,lifecycle:{...receipt,finished:false,recovery:{state:'blocked',reason:'缺少回执',errors:[]}}}};
const drafts={comment:'未发送评论',file:{name:'完整图片.png'}};S.cur={ticket:{key:'APP-7'},drafts};
const delayed=later();let posts=0;postHandler=(url,data)=>{assert.equal(url,'/api/runs/7/recheck/recover');assert.deepEqual(data,{});posts++;return delayed.promise};
await showRun(7);const button=body.querySelector('[data-run-recheck-recover]');const pending=button.onclick();await button.onclick();assert.equal(posts,1);
state={running:false,operation};delayed.resolve(state);await pending;
assert.equal(body.querySelector('[data-run-recheck-recover]'),null);assert.equal(body.querySelector('[data-run-recheck]').disabled,false);
assert.equal(S.cur.drafts,drafts);assert.equal(drafts.comment,'未发送评论');assert.equal(drafts.file.name,'完整图片.png');
''')

    def test_manual_recheck_creates_new_operation_and_preserves_old_receipts(self):
        self.run_js(r'''
const original=JSON.stringify(operation);let posts=0;
postHandler=async(url,data)=>{assert.equal(url,'/api/runs/7/recheck');posts++;state={running:true,operation:{...operation,id:22,status:'running',can_retry:false,lifecycle:{finished:false,attempts:[]},output:'新过程'}};return state};
await showRun(7);await body.querySelector('[data-run-recheck]').onclick();assert.equal(posts,1);assert.equal(S.polls.length,1);
assert.ok(body.innerHTML.includes('重新验证记录 #22'));assert.equal(JSON.stringify(operation),original);
state={running:false,operation:{...state.operation,status:'done',can_retry:true,lifecycle:{finished:true,attempts:[{pid:9877,cleanup:{complete:true}}]},output:'新的完整输出'}};
current={...current,verification:{check:'pass',verdict:'unknown',commands:[{kind:'test',command:'new test',exit_code:0,output:'NEW PROOF'}]}};
await S.polls[0].fn();assert.equal(S.polls.length,0);assert.ok(body.innerHTML.includes('NEW PROOF'));assert.ok(!body.innerHTML.includes('旧验证结果已失效'));
assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,false);
''')

    def test_recheck_read_failure_is_actionable_and_old_view_cannot_override_navigation(self):
        self.run_js(r'''
getHandler=async url=>{if(url.endsWith('/recheck'))throw new Error('完整读取错误 <保留>');return current};
await showRun(7);assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,true);
assert.equal(body.querySelector('[data-run-recheck]').disabled,true);assert.ok(body.innerHTML.includes('完整读取错误 &lt;保留&gt;'));
const refresh=body.querySelector('[data-run-recheck-refresh]');assert.ok(refresh);
getHandler=async url=>url.endsWith('/recheck')?state:current;await refresh.onclick();assert.equal(body.querySelector('[data-run-recheck]').disabled,false);
state={running:false,operation:{...operation,lifecycle:{...receipt,finished:false,recovery:{state:'blocked'}}}};await showRun(7);
const delayed=later();postHandler=()=>delayed.promise;const pending=body.querySelector('[data-run-recheck-recover]').onclick();
getHandler=async url=>url.endsWith('/recheck')?{running:false}:detail(9);await showRun(9);delayed.resolve({running:false,operation});await pending;
assert.ok(body.innerHTML.includes('#9 '));assert.ok(!body.innerHTML.includes('重新验证记录 #21'));
''')

    def test_operation_free_legacy_state_keeps_existing_actions(self):
        self.run_js(r'''
state={running:false};await showRun(7);
assert.equal(body.querySelector('[data-run-recheck]').disabled,false);assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,false);
assert.ok(!body.innerHTML.includes('旧验证结果已失效'));assert.ok(!body.querySelector('[data-run-recheck-recover]'));
''')

    def test_server_invalidated_verification_keeps_full_previous_record_in_history(self):
        self.run_js(r'''
const evidence='旧记录全部字段'.repeat(900)+'<history-end>';
const previous={...oldProof,extra_evidence:evidence};
current={...current,verification:{check:'unknown',verdict:'unknown',verification_current:false,
 recheck_operation:{id:21,status:'failed'},previous_current_verification:previous,commands:[],diagnosis:{}}};
const rendered=runVerificationHtml({...current,recheck:state});
assert.ok(rendered.startsWith('<div class="hint"'));assert.ok(rendered.includes('旧验证结果已失效'));
assert.ok(!rendered.split('<summary>上次验证记录')[0].includes('命令检查：<b>通过'));
assert.ok(rendered.includes(h(JSON.stringify(previous,null,2))));assert.ok(rendered.includes(h(evidence)));
await showRun(7);assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,true);
''')

    def test_operation_only_transition_refreshes_ticket_summary_without_clearing_drafts(self):
        self.run_js(r'''
const draft={comment:'保存未发出的评论',evidence:'截图说明',file:{name:'original.png'}};
S.cur={ticket:{key:'APP-7'},draft};let updates=0;S.ticketRefresh=async()=>{updates++;return true};
state={running:true,operation:{...operation,status:'running',can_retry:false,lifecycle:{finished:false,attempts:[]}}};
await showRun(7);assert.equal(updates,1);
state={running:false,operation:{...operation,lifecycle:{...receipt,finished:false,recovery:{state:'blocked',reason:'回执缺失',errors:[]}}}};
await S.polls[0].fn();assert.equal(updates,2);assert.equal(S.polls.length,0);
assert.equal(S.cur.draft,draft);assert.equal(draft.comment,'保存未发出的评论');assert.equal(draft.file.name,'original.png');
postHandler=async()=>{throw new Error('完整恢复错误 <retry>')};const button=body.querySelector('[data-run-recheck-recover]');await button.onclick();
assert.equal(button.disabled,false);assert.equal(body.querySelector('[data-run-error]').textContent,'完整恢复错误 <retry>');
assert.equal(S.cur.draft,draft);
''')

    def test_current_failed_commands_are_current_evidence_but_cannot_be_adopted(self):
        self.run_js(r'''
current={...current,verification:{check:'fail',verdict:'unknown',verification_current:true,
 recheck_operation:{id:21,source_run:7},commands:[{kind:'test',command:'actual failing test',exit_code:1,output:'ACTUAL FAILURE'}]}};
await showRun(7);assert.ok(body.innerHTML.includes('重新验证已结束，实际检查未通过'));
assert.ok(body.innerHTML.includes('命令检查：<b>失败</b>'));assert.ok(body.innerHTML.includes('ACTUAL FAILURE'));
assert.ok(!body.innerHTML.includes('上次验证记录（仅供历史参考）'));assert.ok(!body.innerHTML.includes('OLD PROOF'));
assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,true);assert.equal(body.querySelector('[data-run-recheck]').disabled,false);
''')

    def test_terminal_unowned_blocked_proof_never_spins_or_allows_retry(self):
        self.run_js(r'''
for(const lifecycle of [{...receipt,finished:false,recovery:null},{...receipt,recovery:null}]){
 state={running:true,operation:{...operation,status:'done',owner_active:false,can_retry:false,blocked:['版本证据不可验证 <完整>'],lifecycle}};
 await showRun(7);assert.equal(S.polls.length,0);assert.ok(!body.innerHTML.includes('class="spin"'));
 assert.ok(body.innerHTML.includes('版本证据不可验证 &lt;完整&gt;'));assert.ok(body.querySelector('[data-run-recheck-recover]'));
 assert.equal(body.querySelector('[data-run-recheck]').disabled,true);assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,true);
}
state={running:true,operation:{...state.operation,owner_active:true,status:'running'}};
await showRun(7);assert.equal(S.polls.length,1,'an active owner is still collecting, not a final blocked record');
let summaries=0;S.cur={ticket:{key:'APP-7'}};S.ticketRefresh=async()=>{summaries++;return true};
state={running:false,operation:{...operation,status:'done',owner_active:false,can_retry:false,blocked:['版本证据待核对'],lifecycle:receipt}};
await showRun(7);assert.equal(summaries,1);
postHandler=async()=>{state={running:false,operation:{...state.operation,can_retry:true,blocked:[]}};return state};
await body.querySelector('[data-run-recheck-recover]').onclick();assert.equal(summaries,2,'same operation status/finished with changed proof must refresh package gates');
''')

    def test_blocked_or_unreadable_recheck_prevents_discard_without_posting(self):
        self.run_js(r'''
let posts=0;postHandler=async()=>{posts++};
state={running:false,operation:{...operation,can_retry:false,lifecycle:{...receipt,finished:false,recovery:{state:'blocked'}}}};
await showRun(7);let discard=body.querySelector('[data-run-decision="discard"]');assert.equal(discard.disabled,true);
await discard.onclick();assert.equal(posts,0);
getHandler=async url=>{if(url.endsWith('/recheck'))throw new Error('不能读取验证状态');return current};
await showRun(7);discard=body.querySelector('[data-run-decision="discard"]');assert.equal(discard.disabled,true);
await discard.onclick();assert.equal(posts,0);
state={running:false,operation};getHandler=async url=>url.endsWith('/recheck')?state:current;
postHandler=async()=>{posts++;throw new Error('操作拒绝')};await showRun(7);
discard=body.querySelector('[data-run-decision="discard"]');assert.equal(discard.disabled,false);await discard.onclick();
assert.equal(posts,1);assert.equal(body.querySelector('[data-run-decision="discard"]').disabled,false);
assert.equal(body.querySelector('[data-run-decision="accept"]').disabled,true,'failed discard must not enable invalid adoption');
''')
