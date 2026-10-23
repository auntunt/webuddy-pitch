"""Exercise shipped task-handoff UI, especially evidence binding and race handling."""
import shutil
import subprocess
import unittest

from test_ui_library import HARNESS
from tmh.platform.ui import page
from tmh.platform.ui_handoffs import HANDOFFS_JS
from tmh.platform.ui_workspace import WORKSPACE_JS


SETUP = r"""
Element.prototype.setAttribute=function(key,value){this.attrs[key]=String(value)};
const workIcon=()=>'<svg></svg>',stPill=value=>'<span>'+h(value)+'</span>',ago=value=>value;
const ls={set(){}};S.scope='APP';S.meta={login:true};const scopeQ=()=>S.scope;
location.hash='#/workspace';
const source=(body='完整需求与验收标准')=>({requirement_hash:'r'.repeat(64),ticket:{title:'审批修复',body},candidate:{id:7,commit:'c'.repeat(40),evidence_hash:'e'.repeat(64),current:true,blocked:false},discussion:[{body:'完整讨论'}]});
const handoff=(extra={})=>({id:3,status:'waiting',stage:'testing',sender:'开发甲',receiver:'测试乙',next_actor:'测试乙',note:'请核对审批流程',materials:'执行步骤与未决问题',block_reason:'',sent_at:'2026-10-23T08:00:00Z',source:source('发送时的完整需求'),events:[{action:'send',actor:'开发甲',note:'请核对审批流程',revision:1,status:'waiting',next_actor:'测试乙'}],...extra});
const detail=(key='APP-1',extra={})=>({ticket:{key,title:key+' 审批修复',body:'完整需求与验收标准',status:'doing',assignee:'开发甲'},revision:1,current:handoff(),history:[handoff()],members:[{id:'开发甲',name:'开发甲'},{id:'测试乙',name:'测试乙'}],source:source(),source_token:'server-bound-source-token',next_actor:'测试乙',waiting_since:'2026-10-23T08:00:00Z',waiting_seconds:120,actions:{send:true,receive:false,return:false,block:false,resume:false,withdraw:false},work:{label:'待技术检查',technical:'pending',human:'not_requested',assignment:{assignee:'开发甲',reviewer:'复核丙'},candidate:{id:7,commit:'c'.repeat(40)}},boundary:'接收材料不等于业务验收。',...extra});
const task=(key='APP-1',extra={})=>({key,title:key+' 审批修复',project:'APP',status:'doing',assignee:'开发甲',reviewer:'复核丙',stage:'unrecorded',stage_label:'未登记阶段',work:{label:'待技术检查'},next_actor:'测试乙',waiting_seconds:null,handoff:null,action_label:'查看技术检查',action_href:'#/team/ticket/'+key,...extra});
const workspace=(extra={})=>({viewer:'开发甲',view:'mine',project:'APP',counts:{mine:1,review:0,unassigned:0,team:1},incoming_count:2,stage_counts:{requirement:0,development:0,testing:0,delivery:0,operations:0,unrecorded:1},items:[task()],total:1,offset:0,has_more:false,projects:[],...extra});
let wsData=workspace(),details=new Map([['APP-1',detail()],['APP-2',detail('APP-2')]]);
getHandler=url=>url.startsWith('/api/workspace')?wsData:details.get(new URL('http://local'+url).searchParams.get('ticket'));
postHandler=async(url,body)=>({...details.get(body.ticket),receipt:{request_id:body.request_id}});
const draftSend=()=>{for(const [field,value]of Object.entries({receiver:'测试乙',stage:'testing',note:'完整交接说明',materials:'完整测试和未决问题'})){const node=main.querySelector('[data-hf-field="'+field+'"]');node.value=value;node.fire('input')}};
const open=async()=>{await vWorkspace();assert.ok($('#hfForm'))};
"""


@unittest.skipUnless(shutil.which('node'), 'Node is needed for shipped handoff UI checks')
class HandoffUiTests(unittest.TestCase):
    def run_js(self, checks):
        script = HARNESS + SETUP + WORKSPACE_JS + HANDOFFS_JS + '\n(async()=>{\n' + checks + '\n})().catch(error=>{console.error(error);process.exitCode=1});'
        result = subprocess.run([shutil.which('node'), '-'], input=script, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_shipped_page_includes_handoff_handlers_and_compiles(self):
        self.assertIn('function handoffsOpen', page())
        result = subprocess.run([shutil.which('node'), '--check'], input=WORKSPACE_JS + HANDOFFS_JS, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_queue_uses_server_counts_stage_and_work_actions(self):
        self.run_js(r"""
await open();assert.ok($('#wsViews').textContent.includes('待我接手2'));assert.ok($('#wsQueue').textContent.includes('未登记阶段'));assert.ok($('#wsQueue').textContent.includes('等待时长未知'));assert.ok($('#wsQueue').textContent.includes('待技术检查'));assert.ok($('#wsQueue').innerHTML.includes('href="#/team/ticket/APP-1"'));
await main.querySelector('[data-ws-view="incoming"]').fire('click');assert.ok(requests.at(-1).includes('view=incoming'));
await main.querySelector('[data-ws-stage="testing"]').fire('click');assert.ok(requests.at(-1).includes('stage=testing'));
$('#wsHandoffState').value='withdrawn';await $('#wsHandoffState').fire('change');assert.ok(requests.at(-1).includes('handoff_state=withdrawn'));assert.equal(mutations.length,0);
""")

    def test_resolved_handoff_is_not_unknown_waiting_in_queue_and_detail(self):
        self.run_js(r"""
for(const status of ['received','returned','withdrawn']){assert.equal(wsHandoffWait({status},null),'当前不在等待')}assert.equal(wsHandoffWait(null,null),'等待时长未知');assert.equal(wsHandoffWait({status:'waiting'},null),'等待时长未知');assert.equal(wsHandoffWait({status:'blocked'},120),'等待 2 分钟');wsData=workspace({items:[task('APP-1',{handoff:{status:'received'},waiting_seconds:null})]});details.set('APP-1',detail('APP-1',{current:handoff({status:'received'}),waiting_since:null,waiting_seconds:null}));await open();assert.ok($('#wsQueue').textContent.includes('当前不在等待'));assert.ok($('#hfFacts').textContent.includes('当前不在等待'));assert.ok(!$('#hfFacts').textContent.includes('等待时长未知'));
""")

    def test_full_requirement_fixed_source_history_and_unsafe_text_are_preserved(self):
        self.run_js(r"""
const full='<script>never()</script>\n'+'完整正文'.repeat(12000)+'\n尾部标记';details.set('APP-1',detail('APP-1',{source:source(full),history:[handoff({note:full,materials:full,events:[{action:'return',note:full}]})]}));await open();
for(const id of ['#hfRequirement','#hfHistory']){assert.ok($(id).innerHTML.includes(h(full)));assert.ok($(id).textContent.includes('尾部标记'));assert.ok(!$(id).innerHTML.includes('<script>'))}
assert.ok($('#hfEvidence').textContent.includes('发送时的完整需求'));assert.ok($('#hfEvidence').textContent.includes('c'.repeat(40)));assert.ok($('#hfFacts').textContent.includes('当前负责人开发甲'));assert.ok($('#hfFacts').textContent.includes('下一责任人测试乙'));assert.ok($('#hfBoundary').textContent.includes('不等于业务验收'));assert.equal(mutations.length,0);
""")

    def test_inactive_historical_participants_are_marked_without_claiming_acceptance(self):
        self.run_js(r"""
details.set('APP-1',detail('APP-1',{current:handoff({receiver_active:false,next_actor_active:false}),history:[handoff({sender_active:false,receiver_active:false})]}));await open();assert.ok($('#hfFacts').textContent.includes('测试乙（账号已停用）'));assert.ok($('#hfFacts').textContent.includes('撤回后重发'));assert.ok($('#hfHistory').textContent.includes('开发甲（账号已停用）'));assert.ok($('#hfHistory').textContent.includes('测试乙（账号已停用）'));assert.equal(mutations.length,0);
""")

    def test_latest_return_reason_is_visible_in_detail_without_truncation(self):
        self.run_js(r"""
const note='<script>不会执行</script>\n'+'完整退回原因'.repeat(1000)+'END';details.set('APP-1',detail('APP-1',{current:handoff({status:'returned',events:[{action:'return',actor:'测试乙',ts:'2026-10-23',note}]})}));await open();assert.ok($('#hfFacts').textContent.includes('最近交接处理'));assert.ok($('#hfFacts').innerHTML.includes(h(note)));assert.ok(!$('#hfFacts').innerHTML.includes('<script>'));assert.equal(mutations.length,0);
""")

    def test_refresh_preserves_draft_nodes_focus_and_revision_binding(self):
        self.run_js(r"""
await open();draftSend();const note=main.querySelector('[data-hf-field="note"]'),materials=main.querySelector('[data-hf-field="materials"]');note.selectionStart=3;note.focus();
details.set('APP-1',detail('APP-1',{revision:2,source_token:'new-source-token'}));await $('#hfRefresh').fire('click');assert.equal(main.querySelector('[data-hf-field="note"]'),note);assert.equal(note.value,'完整交接说明');assert.equal(materials.value,'完整测试和未决问题');assert.equal(document.activeElement,note);assert.equal(note.selectionStart,3);assert.equal($('#hfSubmit').disabled,true);assert.equal(hfDraft(HANDOFFS.view,'send').revision,1);
await submit('#hfForm');assert.equal(mutations.length,0);await $('#hfRebind').fire('click');assert.equal(note.value,'完整交接说明');assert.equal(hfDraft(HANDOFFS.view,'send').revision,2);assert.equal(hfDraft(HANDOFFS.view,'send').source_token,'new-source-token');
await wsRefresh();assert.equal(main.querySelector('[data-hf-field="note"]'),note);assert.equal(document.activeElement,note);
""")

    def test_source_change_without_handoff_revision_requires_explicit_rebinding(self):
        self.run_js(r"""
await open();draftSend();details.set('APP-1',detail('APP-1',{source_token:'changed-requirement-same-handoff-revision'}));await $('#hfRefresh').fire('click');assert.equal(hfDraft(HANDOFFS.view,'send').revision,1);assert.equal($('#hfSubmit').disabled,true);assert.equal($('#hfRebind').disabled,false);await submit('#hfForm');assert.equal(mutations.length,0);await $('#hfRebind').fire('click');assert.equal(main.querySelector('[data-hf-field="note"]').value,'完整交接说明');await submit('#hfForm');assert.equal(mutations[0].body.source_token,'changed-requirement-same-handoff-revision');
""")

    def test_send_binds_latest_explicit_source_and_rejects_double_clicks(self):
        self.run_js(r"""
await open();draftSend();const pending=later();postHandler=()=>pending.promise;const first=submit('#hfForm');await submit('#hfForm');assert.equal(mutations.length,1);const body=mutations[0].body;assert.equal(body.source_token,'server-bound-source-token');assert.equal(body.revision,1);assert.equal(body.stage,'testing');assert.equal(body.receiver,'测试乙');assert.equal(body.materials,'完整测试和未决问题');assert.ok(body.request_id);assert.equal(body.commit,undefined);assert.equal($('#hfSubmit').disabled,true);
pending.resolve({...detail(),receipt:{request_id:body.request_id}});await first;assert.equal(HANDOFFS.pending.size,0);assert.equal(main.querySelector('[data-hf-field="note"]').value,'');
""")

    def test_success_with_incremented_revision_selects_next_allowed_action(self):
        self.run_js(r"""
await open();draftSend();postHandler=async(url,body)=>{const next=detail('APP-1',{revision:2,actions:{send:false,withdraw:true}});details.set('APP-1',next);return{...next,receipt:{request_id:body.request_id}}};await submit('#hfForm');assert.equal($('#hfAction').value,'withdraw');assert.equal($('#hfSubmit').disabled,false);assert.ok(!$('#hfBinding').textContent.includes('较早'));assert.equal(hfDraft(HANDOFFS.view,'withdraw').revision,2);
""")

    def test_uncertain_result_keeps_original_payload_and_request_id_across_refresh(self):
        self.run_js(r"""
await open();draftSend();postHandler=async()=>{throw Error('响应丢失')};await submit('#hfForm');const original=mutations[0].body;assert.equal(HANDOFFS.pending.size,1);assert.equal(main.querySelector('[data-hf-field="note"]').disabled,true);
details.set('APP-1',detail('APP-1',{revision:2,actions:{send:false,receive:true}}));await $('#hfRefresh').fire('click');assert.equal($('#hfRebind').disabled,true);assert.ok($('#hfPending').textContent.includes('重试原请求'));
postHandler=async(url,body)=>({...detail(),receipt:{request_id:body.request_id}});await $('#hfRetryMutation').fire('click');assert.deepEqual(mutations[1].body,original);assert.equal(HANDOFFS.pending.size,0);
""")

    def test_conflict_preserves_text_and_requires_explicit_rebinding(self):
        self.run_js(r"""
await open();draftSend();postHandler=async()=>{throw Object.assign(Error('记录版本冲突'),{status:409})};await submit('#hfForm');const original=mutations[0].body;assert.equal(HANDOFFS.pending.size,0);assert.equal(main.querySelector('[data-hf-field="note"]').value,'完整交接说明');assert.ok($('#hfNotice').textContent.includes('原始草稿已保留'));
details.set('APP-1',detail('APP-1',{revision:2,source_token:'fresh-token'}));await $('#hfRefresh').fire('click');assert.equal($('#hfSubmit').disabled,true);await $('#hfRebind').fire('click');postHandler=async(url,body)=>({...detail(),receipt:{request_id:body.request_id}});await submit('#hfForm');assert.notEqual(mutations[1].body.request_id,original.request_id);assert.equal(mutations[1].body.source_token,'fresh-token');assert.equal(mutations[1].body.note,original.note);
""")

    def test_timeout_and_malformed_success_remain_uncertain(self):
        self.run_js(r"""
await open();draftSend();postHandler=async()=>{throw Object.assign(Error('请求超时'),{status:408})};await submit('#hfForm');assert.equal(HANDOFFS.pending.size,1);const original=mutations[0].body;postHandler=async()=>({});await $('#hfRetryMutation').fire('click');assert.equal(HANDOFFS.pending.size,1);assert.deepEqual(mutations[1].body,original);assert.ok($('#hfNotice').textContent.includes('响应不完整'));
""")

    def test_receive_return_block_and_withdraw_follow_server_permissions(self):
        self.run_js(r"""
details.set('APP-1',detail('APP-1',{actions:{send:false,receive:true,return:true,block:true,resume:false,withdraw:true}}));await open();assert.equal($('#hfAction').value,'receive');assert.ok($('#hfForm').textContent.includes('接收材料'));assert.ok(!$('#hfForm').textContent.includes('验收通过'));
$('#hfAction').value='return';await $('#hfAction').fire('change');await submit('#hfForm');assert.equal(mutations.length,0);const note=main.querySelector('[data-hf-field="note"]');note.value='材料缺少回退步骤';note.fire('input');await submit('#hfForm');assert.equal(mutations[0].body.action,'return');assert.equal(mutations[0].body.handoff_id,3);assert.equal(mutations[0].body.note,'材料缺少回退步骤');
""")

    def test_latest_detail_wins_and_departed_failure_cannot_overwrite_page(self):
        self.run_js(r"""
await open();const old=later(),fresh=later();getHandler=url=>url.includes('APP-1')?old.promise:fresh.promise;const a=wsSelect(WS.page,'APP-1'),b=wsSelect(WS.page,'APP-2');fresh.resolve(detail('APP-2'));await b;old.reject(Error('旧任务错误'));await a;assert.ok($('#hfTitle').textContent.includes('APP-2'));assert.ok(!main.textContent.includes('旧任务错误'));
const gone=later();getHandler=()=>gone.promise;const read=hfRefresh(HANDOFFS.view);location.hash='#/projects';main.innerHTML='<div id="newPage">项目页面</div>';gone.reject(Error('迟到错误'));await read;assert.equal($('#newPage').textContent,'项目页面');
""")

    def test_mutation_completion_updates_remounted_same_task_without_stale_busy_controls(self):
        self.run_js(r"""
await open();draftSend();const receipt=later();postHandler=()=>receipt.promise;const sent=submit('#hfForm'),body=mutations[0].body;await wsSelect(WS.page,'APP-2');await wsSelect(WS.page,'APP-1');assert.equal($('#hfSubmit').disabled,true);receipt.resolve({...detail(),receipt:{request_id:body.request_id}});await sent;assert.equal(HANDOFFS.pending.size,0);assert.equal($('#hfSubmit').disabled,false);assert.equal($('#hfPending').textContent,'');assert.equal(main.querySelector('[data-hf-field="note"]').value,'');
""")

    def test_unknown_mutation_failure_on_remount_exposes_original_retry(self):
        self.run_js(r"""
await open();draftSend();const receipt=later();postHandler=()=>receipt.promise;const sent=submit('#hfForm');await wsSelect(WS.page,'APP-2');await wsSelect(WS.page,'APP-1');receipt.reject(Error('响应丢失'));await sent;assert.equal(HANDOFFS.pending.size,1);assert.equal($('#hfRetryMutation').disabled,false);assert.ok($('#hfNotice').textContent.includes('结果尚未确认'));assert.equal(main.querySelector('[data-hf-field="note"]').value,'完整交接说明');
""")

    def test_refresh_updates_permissions_and_inactive_member_without_replacing_draft_nodes(self):
        self.run_js(r"""
details.set('APP-1',detail('APP-1',{actions:{send:false,withdraw:true}}));await open();assert.equal($('#hfAction').value,'withdraw');const note=main.querySelector('[data-hf-field="note"]');note.value='保存撤回原因';note.fire('input');note.focus();details.set('APP-1',detail('APP-1',{revision:2,actions:{send:true,withdraw:false}}));await $('#hfRefresh').fire('click');assert.ok($('#hfAction').all().some(n=>n.attrs.value==='send'));assert.equal(main.querySelector('[data-hf-field="note"]'),note);assert.equal(document.activeElement,note);assert.equal(note.value,'保存撤回原因');$('#hfAction').value='send';await $('#hfAction').fire('change');draftSend();const receiver=main.querySelector('[data-hf-field="receiver"]');details.set('APP-1',detail('APP-1',{revision:2,members:[{id:'开发甲',name:'开发甲'}]}));await $('#hfRefresh').fire('click');assert.equal(main.querySelector('[data-hf-field="receiver"]'),receiver);assert.equal(receiver.value,'测试乙');assert.ok(receiver.textContent.includes('账号已不可用'));assert.equal($('#hfSubmit').disabled,true);assert.equal(main.querySelector('[data-hf-field="note"]').value,'完整交接说明');
""")

    def test_confirmed_mutation_followed_by_read_failure_cannot_resubmit_old_form(self):
        self.run_js(r"""
await open();draftSend();getHandler=async()=>{throw Error('刷新网络失败')};await submit('#hfForm');assert.equal(HANDOFFS.pending.size,0);assert.equal(main.querySelector('[data-hf-field="note"]').value,'');assert.equal($('#hfSubmit').disabled,true);await submit('#hfForm');assert.equal(mutations.length,1);getHandler=async()=>detail();await $('#hfRefresh').fire('click');assert.equal($('#hfSubmit').disabled,false);
""")

    def test_queue_errors_empty_state_and_scope_races_keep_current_page(self):
        self.run_js(r"""
wsData=workspace({items:[],total:0});await vWorkspace();assert.ok($('#wsQueue').textContent.includes('当前筛选没有任务'));getHandler=async()=>{throw Error('读取失败')};await wsRefresh();assert.ok($('#wsQueueNotice').textContent.includes('读取失败'));assert.ok($('#wsRetry'));
const old=later(),fresh=later();getHandler=url=>url.includes('project=APP')?old.promise:fresh.promise;const a=vWorkspace();S.scope='STD';const b=vWorkspace();fresh.resolve(workspace({project:'STD',items:[],total:0}));await b;old.resolve(workspace());await a;assert.ok($('#wsScope').textContent.includes('STD'));assert.ok(!$('#wsQueue').textContent.includes('APP-1'));
""")

    def test_switching_tasks_restores_complete_unsent_draft(self):
        self.run_js(r"""
await open();draftSend();await wsSelect(WS.page,'APP-2');await wsSelect(WS.page,'APP-1');assert.equal(main.querySelector('[data-hf-field="note"]').value,'完整交接说明');assert.equal(main.querySelector('[data-hf-field="materials"]').value,'完整测试和未决问题');assert.equal(mutations.length,0);
""")


if __name__ == '__main__':
    unittest.main()
