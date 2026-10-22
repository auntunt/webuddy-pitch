"""Exercise learning workspace handlers, source binding and operator-only choices."""
import shutil
import subprocess
import unittest

from test_ui_library import HARNESS
from tmh.platform.ui_learning import LEARNING_JS
from tmh.platform.ui_memory import MEMORY_JS


SETUP = r"""
const workIcon=()=>'<svg></svg>';
const scopeStorage=new Map(),ls={set:(key,value)=>scopeStorage.set(key,value)};
location.hash='#/memory/learning';S.scope='APP';S.meta={operator_authenticated:true,agents:[{name:'claude',title:'独立评审',available:true},{name:'codex',title:'其他 Agent',available:true},{name:'missing',title:'未安装',available:false}]};
const R1='1'.repeat(32),R2='2'.repeat(32),R3='3'.repeat(32);
const learningItem=(extra={})=>({key:'fact:index',kind:'fact',title:'审批流程',content:'完整事实正文',fingerprint:'f'.repeat(64),source:{project:'APP',commit:'a'.repeat(40),path:'.tmh/knowledge/index.md'},human:{status:'none'},machine:{status:'none'},revision_id:R1,stale:false,...extra});
const learningOverview=(extra={})=>({project:{id:1,key:'APP',name:'审批系统'},items:[learningItem()],jobs:[],policy_specs:{context_budget:{min:4000,max:12000,default:6000,label:'上下文预算'}},readonly:true,...extra});
const learningRevision=(id=R1,extra={})=>({revision:{id,kind:'fact',origin_id:'fact:index',title:'审批流程',content:'固定完整事实',source:{project:'APP',commit:'a'.repeat(40),path:'src/approval.py'},parent_id:null,created:'2026-10-22',author:'记录者'},current:true,expected_active:null,active_revision_id:null,jobs:[],history:[],decisions:[],...extra});
const learningJob=(extra={})=>({id:17,kind:'review',status:'passed',revision_id:R1,current_revision_id:R1,options:{max_revisions:2,max_calls:6,timeout_seconds:600},steps:[],result:{},created:'2026-10-22',updated:'2026-10-22',...extra});
let learningData=learningOverview(),learningDetails=new Map([[R1,learningRevision()],[R2,learningRevision(R2)],[R3,learningRevision(R3)]]);
getHandler=url=>{const query=new URL('http://local'+url).searchParams;return query.has('revision')?learningDetails.get(query.get('revision')):learningData};
postHandler=async()=>({ok:true});
const openLearning=async(id=R1)=>{await vLearning();await learningOpen(LEARNING.view,id)};
"""


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for shipped learning UI checks")
class LearningUiTests(unittest.TestCase):
    def run_js(self, checks):
        result = subprocess.run(
            [shutil.which("node"), "-"],
            input=HARNESS + SETUP + MEMORY_JS + LEARNING_JS +
                  "\n(async()=>{\n" + checks +
                  "\n})().catch(error=>{console.error(error);process.exitCode=1});",
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reloadable_route_project_scope_and_three_filters_are_read_only(self):
        self.run_js(r"""
await vMemory('learning');assert.equal(MEM.section,'learning');assert.ok($('#learningPage'));assert.equal(requests[0],'/api/learning?project=APP&kind=fact&q=');
assert.equal(main.querySelectorAll('[data-learning-kind]').length,3);$('#learningQuery').value='审批 <draft>';
await main.querySelector('[data-learning-kind="lesson"]').fire('click');assert.equal(LEARNING.kind,'lesson');assert.equal($('#learningQuery').value,'审批 <draft>');assert.ok(requests.at(-1).includes('kind=lesson'));
$('#learningProject').value='STD';await $('#learningProject').fire('change');assert.equal(S.scope,'STD');assert.equal(S.proj,'STD');assert.equal(scopeStorage.get('tmh.scope'),'STD');assert.ok(requests.at(-1).includes('project=STD'));
await main.querySelector('[data-learning-tab="knowledge"]').fire('click');assert.equal(location.hash,'#/memory/knowledge');assert.equal(mutations.length,0);
location.hash='#/memory/learning';S.scope='*';const count=requests.length;await vLearning();assert.equal(requests.length,count);assert.equal($('#learningProject').value,'');assert.ok($('#learningList').textContent.includes('请先选择项目'));assert.equal(mutations.length,0);
""")

    def test_catalog_keeps_full_content_and_separates_machine_from_human(self):
        self.run_js(r"""
const unsafe='<img src=x onerror="alert(1)"><script>unsafe()</script>',full=unsafe+'\n'+'完整内容'.repeat(18000)+'\n末尾完整标记';
learningData=learningOverview({items:[learningItem({title:unsafe,content:full,source:{project:'STD',commit:'b'.repeat(40),body:full},machine:{status:'passed'},human:{status:'none'},stale:true})]});await vLearning();const html=$('#learningList').innerHTML;
assert.ok(html.includes(h(full)));assert.ok(html.includes('末尾完整标记'));assert.ok(html.includes(h('b'.repeat(40))));assert.ok(!html.includes('<img'));assert.ok(!html.includes('<script>'));assert.ok(html.includes('来源或内容已变化'));assert.ok(html.includes('机器验证'));assert.ok(html.includes('未登记人工采用'));assert.ok(!html.includes('已人工采用'));assert.equal(mutations.length,0);
""")

    def test_detail_preserves_every_raw_round_and_history_without_executing_markup(self):
        self.run_js(r"""
const raw='BEGIN <script>raw()</script>\n'+'原始输出'.repeat(16000)+'\nEND',job=learningJob({steps:[{round:0,output:raw},{round:1,output:'末轮未截断'}],result:{output:raw,cost:null}});
learningDetails.set(R1,learningRevision(R1,{jobs:[job],history:[{id:R1,content:raw}],decisions:[{action:'reject',reason:raw}]}));await openLearning();
const root=$('#learningDetail'),jobs=$('#learningDetailJobs').innerHTML;assert.ok(jobs.includes(h(learningText(job.steps))));assert.ok(jobs.includes(h(learningText(job.result))));assert.ok(root.innerHTML.includes(h(learningText([{action:'reject',reason:raw}]))));assert.ok(jobs.includes('费用为未知'));assert.ok(!jobs.includes('<script>'));assert.equal(mutations.length,0);
""")

    def test_final_model_text_and_raw_process_stream_are_separately_preserved(self):
        self.run_js(r"""
const final='最终正文 <script>final()</script>\n'+'最终完整内容'.repeat(5000)+'FINAL-END',raw='进程事件 <script>event()</script>\n'+'原始事件流'.repeat(6000)+'RAW-END';
learningDetails.set(R1,learningRevision(R1,{jobs:[learningJob({status:'failed',steps:[{seq:3,role:'reviewer',status:'failed',run_id:81,output:final,raw_output:raw,error:'执行失败'}]})]}));await openLearning();const html=$('#learningDetailJobs').innerHTML;assert.ok(html.includes('模型最终正文'));assert.ok(html.includes('进程完整原始输出'));assert.ok(html.includes(h(final)));assert.ok(html.includes(h(raw)));assert.ok(html.includes('FINAL-END'));assert.ok(html.includes('RAW-END'));assert.ok(!html.includes('<script>'));assert.equal($('#learningAdopt').disabled,true);assert.equal(mutations.length,0);
""")

    def test_latest_project_read_wins_and_departed_errors_are_discarded(self):
        self.run_js(r"""
const old=later(),latest=later();getHandler=url=>url.includes('project=APP')?old.promise:latest.promise;const a=vLearning();S.scope='STD';const b=vLearning();latest.resolve(learningOverview({items:[learningItem({title:'当前标品目录'})]}));await b;old.resolve(learningOverview({items:[learningItem({title:'迟到的客户目录'})]}));await a;assert.ok($('#learningList').textContent.includes('当前标品目录'));assert.ok(!$('#learningList').textContent.includes('迟到'));
const gone=later();getHandler=()=>gone.promise;const read=vLearning();location.hash='#/workspace';main.innerHTML='<div id="currentPage">当前工作区</div>';gone.reject(Error('旧请求失败'));await read;assert.equal($('#currentPage').textContent,'当前工作区');
""")

    def test_latest_revision_read_wins_and_late_failure_cannot_replace_it(self):
        self.run_js(r"""
await vLearning();const older=later(),latest=later();getHandler=url=>url.includes(R1)?older.promise:latest.promise;const a=learningOpen(LEARNING.view,R1),b=learningOpen(LEARNING.view,R2);latest.resolve(learningRevision(R2));await b;older.reject(Error('旧修订迟到的错误'));await a;assert.equal(LEARNING.view.detail.id,R2);assert.ok($('#learningDetail').textContent.includes(R2));assert.ok(!$('#learningDetail').textContent.includes('迟到'));
""")

    def test_capture_is_fingerprint_bound_deduplicated_across_refresh_and_reuses_retry_id(self):
        self.run_js(r"""
await vLearning();const pending=later();postHandler=()=>pending.promise;const first=main.querySelector('[data-learning-capture="0"]').fire('click');await main.querySelector('[data-learning-capture="0"]').fire('click');assert.equal(mutations.length,1);assert.equal(mutations[0].body.expected_fingerprint,'f'.repeat(64));assert.equal(mutations[0].body.project,'APP');assert.ok(mutations[0].body.request_id);
await learningRefresh(LEARNING.view);assert.equal(main.querySelector('[data-learning-capture="0"]').disabled,true);await main.querySelector('[data-learning-capture="0"]').fire('click');assert.equal(mutations.length,1);
pending.reject(Error('响应中断，结果未知'));await first;assert.equal(main.querySelector('[data-learning-capture="0"]').disabled,false);const id=mutations[0].body.request_id;postHandler=async()=>({revision_id:R1});await main.querySelector('[data-learning-capture="0"]').fire('click');assert.equal(mutations.length,2);assert.equal(mutations[1].body.request_id,id);assert.equal(LEARNING.view.detail.id,R1);assert.equal(LEARNING.pending.size,0);
""")

    def test_proposal_is_bound_to_original_revision_and_failure_preserves_the_full_draft(self):
        self.run_js(r"""
await openLearning();const full='修订 <script>不会执行</script>\n'+'完整正文'.repeat(4000);$('#learningContent').value=full;postHandler=async()=>{throw Error('版本冲突')};await submit('#learningPropose');assert.equal(mutations[0].body.revision_id,R1);assert.equal(mutations[0].body.content,full);assert.equal($('#learningContent').value,full);assert.ok($('#learningNotice').textContent.includes('版本冲突'));
$('#learningReason').value='尚未提交的人工原因';await $('#learningDetailRefresh').fire('click');assert.equal($('#learningContent').value,full);assert.equal($('#learningReason').value,'尚未提交的人工原因');postHandler=async()=>({revision:{id:R2}});await submit('#learningPropose');assert.equal(LEARNING.view.detail.id,R2);assert.equal(mutations[1].body.revision_id,R1);
""")

    def test_review_sends_bounded_settings_and_no_hidden_human_confirmation(self):
        self.run_js(r"""
await openLearning();assert.equal($('#learningAgent').querySelectorAll('[value="codex"]').length,0);assert.ok($('#learningDetail').textContent.includes('支持隔离参数的 Claude'));$('#learningModel').value='review-model';$('#learningRevisions').value='0';await submit('#learningRun');const body=mutations[0].body;assert.equal(body.action,'review');assert.equal(body.revision_id,R1);assert.equal(body.agent,'claude');assert.equal(body.model,'review-model');assert.equal(body.max_revisions,0);assert.equal(body.max_calls,6);assert.equal(body.timeout_seconds,600);assert.equal(body.confirm,undefined);assert.equal(body.adopt,undefined);
$('#learningCalls').value='7';await submit('#learningRun');assert.equal(mutations.length,1);assert.ok($('#learningNotice').textContent.includes('1–6'));$('#learningCalls').value='6';$('#learningTimeout').value='';await submit('#learningRun');assert.equal(mutations.length,1);
S.meta.agents=[];await openLearning();assert.equal($('#learningRunGo').disabled,true);await submit('#learningRun');assert.equal(mutations.length,1);
""")

    def test_evaluation_validates_and_freezes_complete_cases_without_claiming_execution(self):
        self.run_js(r"""
const detail=learningRevision();detail.revision.kind='lesson';learningDetails.set(R1,detail);await openLearning();assert.ok($('#learningDetail').textContent.includes('没有实际执行'));assert.equal($('#learningCases').value,'');
for(const value of ['not json','[]','[{"id":"one"}]']){$('#learningCases').value=value;await submit('#learningRun');assert.equal(mutations.length,0)}
const cases=[{id:'heldout',input:'完整任务输入 <script>data</script>',expected:['确定结论','完整输出末尾'],validator:'contains_all',generation:false},{id:'generation',input:'用于生成的输入',expected:['探索'],validator:'contains_all',generation:true}];$('#learningCases').value=JSON.stringify(cases);await submit('#learningRun');assert.equal(mutations[0].body.action,'evaluate');assert.deepEqual(mutations[0].body.cases,cases);assert.equal(mutations[0].body.max_calls,12);assert.equal(mutations[0].body.timeout_seconds,600);assert.equal($('#learningCases').value,JSON.stringify(cases));
$('#learningCases').value=JSON.stringify([cases[0],cases[0]]);await submit('#learningRun');assert.equal(mutations.length,1);assert.ok($('#learningNotice').textContent.includes('不同'));
""")

    def test_machine_pass_never_enables_unauthenticated_human_actions(self):
        self.run_js(r"""
S.meta.operator_authenticated=false;learningDetails.set(R1,learningRevision(R1,{expected_active:R1,active_revision_id:R1,jobs:[learningJob()]}));await openLearning();assert.equal($('#learningAdopt').disabled,true);assert.equal($('#learningRevoke').disabled,true);$('#learningReason').value='我不是人工操作者';$('#learningDecisionJob').value='17';await submit('#learningDecision');await $('#learningRevoke').fire('click');assert.equal(mutations.length,0);assert.ok($('#learningNotice').textContent.includes('人工操作者身份'));assert.ok($('#learningDetail').textContent.includes('机器通过不会自动确认'));
""")

    def test_adoption_sends_exact_revision_job_and_expected_active_without_guessing(self):
        self.run_js(r"""
learningDetails.set(R1,learningRevision(R1,{expected_active:R2,active_revision_id:R2,jobs:[learningJob()]}));await openLearning();assert.equal($('#learningAdopt').disabled,false);assert.equal($('#learningRevoke').disabled,true);$('#learningReason').value='仅适用 APP 当前版本';await submit('#learningDecision');assert.equal(mutations.length,0);$('#learningDecisionJob').value='17';await submit('#learningDecision');const body=mutations[0].body;assert.equal(body.action,'adopt');assert.equal(body.revision_id,R1);assert.equal(body.job_id,17);assert.equal(body.expected_active,R2);assert.equal(body.reason,'仅适用 APP 当前版本');assert.equal(body.project,'APP');
const unknown=learningRevision(R1,{jobs:[learningJob()]});delete unknown.expected_active;delete unknown.active_revision_id;learningDetails.set(R1,unknown);await learningOpen(LEARNING.view,R1);assert.equal($('#learningAdopt').disabled,true);assert.equal($('#learningRevoke').disabled,true);assert.ok($('#learningDetail').textContent.includes('缺少当前采用版本'));
""")

    def test_non_passed_jobs_and_final_revision_mismatch_cannot_be_adopted(self):
        self.run_js(r"""
const statuses=['done','completed','failed','cancelled','timed_out','not_passed','needs_resume'];learningDetails.set(R1,learningRevision(R1,{jobs:statuses.map((status,index)=>learningJob({id:index,status,verdict:'pass'}))}));await openLearning();assert.equal($('#learningAdopt').disabled,true);
learningDetails.set(R1,learningRevision(R1,{jobs:[learningJob({current_revision_id:R2})]}));await learningOpen(LEARNING.view,R1);assert.equal($('#learningAdopt').disabled,true);const final=$('#learningDetailJobs').querySelector('[data-learning-job-open="'+R2+'"]');assert.ok(final);learningDetails.set(R2,learningRevision(R2,{jobs:[learningJob({current_revision_id:R2})]}));await final.fire('click');assert.equal(LEARNING.view.detail.id,R2);assert.equal($('#learningAdopt').disabled,false);
""")

    def test_stale_source_blocks_new_runs_and_adoption_but_allows_revoking_its_active_revision(self):
        self.run_js(r"""
learningDetails.set(R1,learningRevision(R1,{current:false,expected_active:R1,active_revision_id:R1,jobs:[learningJob()]}));await openLearning();assert.equal($('#learningProposeGo').disabled,true);assert.equal($('#learningRunGo').disabled,true);assert.equal($('#learningAdopt').disabled,true);assert.equal($('#learningRevoke').disabled,false);$('#learningReason').value='来源变更，撤销使用';await $('#learningRevoke').fire('click');assert.equal(mutations[0].body.action,'revoke');assert.equal(mutations[0].body.expected_active,R1);assert.equal(mutations[0].body.revision_id,R1);
S.meta.operator_authenticated=false;await $('#learningRevoke').fire('click');assert.equal(mutations.length,1,'authentication is checked again at click time');
""")

    def test_cancel_resume_and_insufficient_evidence_are_distinct_and_reading_never_runs(self):
        self.run_js(r"""
learningData=learningOverview({jobs:[learningJob({id:18,status:'running'}),learningJob({id:19,status:'needs_resume'}),learningJob({id:20,status:'not_passed',verdict:'insufficient'})]});await vLearning();assert.equal(mutations.length,0);assert.ok($('#learningJobs').textContent.includes('证据不足'));assert.ok($('#learningJobs').textContent.includes('未执行'));const cards=$('#learningJobs').querySelectorAll('[data-learning-job]');const pending=later();postHandler=()=>pending.promise;const run=cards[0].querySelector('[data-learning-job-action="cancel"]').fire('click');await cards[0].querySelector('[data-learning-job-action="cancel"]').fire('click');assert.equal(mutations.length,1);assert.equal(mutations[0].body.job_id,18);assert.equal(mutations[0].body.action,'cancel');pending.resolve({ok:true});await run;postHandler=async()=>({ok:true});await $('#learningJobs').querySelectorAll('[data-learning-job]')[1].querySelector('[data-learning-job-action="resume"]').fire('click');assert.equal(mutations[1].body.job_id,19);assert.equal(mutations[1].body.action,'resume');
""")

    def test_policy_form_uses_only_server_allowlisted_parameter_and_keeps_drafts(self):
        self.run_js(r"""
LEARNING.kind='policy';learningData=learningOverview({items:[],policy_specs:{context_budget:{min:4000,max:12000,default:6000,label:'上下文预算'},shell:{min:0,max:1,default:1}}});await vLearning();assert.equal($('#learningPolicyValue').value,'6000');assert.ok(!$('#learningPolicy').innerHTML.includes('shell'));
$('#learningPolicyName').value='context-budget-8000';$('#learningPolicyTitle').value='较长上下文';$('#learningPolicyScope').value='限 APP 的复杂任务';$('#learningPolicyValue').value='12001';await submit('#learningPolicyForm');assert.equal(mutations.length,0);$('#learningPolicyValue').value='8000';await learningRefresh(LEARNING.view);assert.equal($('#learningPolicyName').value,'context-budget-8000');assert.equal($('#learningPolicyScope').value,'限 APP 的复杂任务');await submit('#learningPolicyForm');assert.deepEqual(mutations[0].body.parameters,{context_budget:8000});assert.equal(mutations[0].body.name,'context-budget-8000');assert.equal(mutations[0].body.applicability,'限 APP 的复杂任务');
$('#learningPolicyName').value='../guard';await submit('#learningPolicyForm');assert.equal(mutations.length,1);learningData=learningOverview({items:[],policy_specs:{}});await learningRefresh(LEARNING.view);assert.equal($('#learningPolicyForm'),null);assert.ok($('#learningPolicy').textContent.includes('没有可创建'));
""")

    def test_late_mutation_cannot_refresh_or_open_revision_in_a_different_project(self):
        self.run_js(r"""
await openLearning();const pending=later();postHandler=()=>pending.promise;$('#learningContent').value='旧项目草稿';const write=submit('#learningPropose');S.scope='STD';await vLearning();const count=requests.length;pending.resolve({revision_id:R2});await write;assert.equal(requests.length,count);assert.equal(LEARNING.view.key,'STD');assert.equal(LEARNING.view.detail,null);assert.equal(LEARNING.pending.size,0);assert.ok(!$('#learningNotice').textContent.includes('已登记'));
""")

    def test_pending_decision_retry_keeps_original_id_and_requires_operator(self):
        self.run_js(r"""
learningDetails.set(R1,learningRevision(R1,{decisions:[{id:'decision-pending',status:'pending',actor:'人工复核人',result:{error:'文件保存失败'}},{id:'decision-conflict',status:'conflict',actor:'旧人工'}]}));await openLearning();const retries=$('#learningDetail').querySelectorAll('[data-learning-retry]');assert.equal(retries.length,1);const pending=later();postHandler=()=>pending.promise;const retry=retries[0].fire('click');await retries[0].fire('click');assert.equal(mutations.length,1);assert.equal(mutations[0].body.action,'retry_decision');assert.equal(mutations[0].body.decision_id,'decision-pending');assert.equal(mutations[0].body.project,'APP');assert.equal(mutations[0].body.reason,undefined);pending.resolve({ok:true});await retry;
S.meta.operator_authenticated=false;await learningRefreshDetail(LEARNING.view,LEARNING.view.detail);const button=$('#learningDetail').querySelector('[data-learning-retry]');assert.equal(button.disabled,true);await button.fire('click');assert.equal(mutations.length,1);
""")

    def test_abandon_requires_current_token_reason_and_original_pending_decision(self):
        self.run_js(r"""
const decisions=[{id:'pending-original',status:'pending',actor:'人工复核人'},{id:'conflict-original',status:'conflict',actor:'人工复核人'},{id:'applied-original',status:'applied',actor:'人工复核人'}];learningDetails.set(R1,learningRevision(R1,{expected_token:'exact-current-page-token',decisions}));await openLearning();const buttons=$('#learningDetail').querySelectorAll('[data-learning-abandon]');assert.equal(buttons.length,2);assert.ok($('#learningDetail').textContent.includes('保留当前正文与历史'));
await buttons[0].fire('click');assert.equal(mutations.length,0);assert.ok($('#learningNotice').textContent.includes('请写明'));$('#learningReason').value='保留现场，来源变化后重新评审';const pending=later();postHandler=()=>pending.promise;const write=buttons[0].fire('click');await buttons[0].fire('click');const retry=$('#learningDetail').querySelector('[data-learning-retry]');assert.equal(retry.disabled,true);await retry.fire('click');assert.equal(mutations.length,1);assert.equal(mutations[0].body.action,'abandon_decision');assert.equal(mutations[0].body.decision_id,'pending-original');assert.equal(mutations[0].body.expected_token,'exact-current-page-token');assert.equal(mutations[0].body.reason,'保留现场，来源变化后重新评审');assert.equal(mutations[0].body.project,'APP');
learningDetails.set(R1,learningRevision(R1,{expected_token:'new-token',decisions:[{id:'pending-original',status:'abandoned',actor:'人工复核人'}]}));pending.resolve({status:'abandoned'});await write;assert.equal($('#learningDetail').querySelectorAll('[data-learning-abandon]').length,0);assert.ok($('#learningDetail').textContent.includes('放弃不代表确认'));assert.ok($('#learningNotice').textContent.includes('待人工确认'));
""")

    def test_abandon_disabled_without_personal_identity_token_or_fact_kind(self):
        self.run_js(r"""
const detail=learningRevision(R1,{decisions:[{id:'conflict-original',status:'conflict',actor:'人工复核人'}]});learningDetails.set(R1,detail);await openLearning();let button=$('#learningDetail').querySelector('[data-learning-abandon]');assert.equal(button.disabled,true);$('#learningReason').value='人工原因';await button.fire('click');assert.equal(mutations.length,0);
detail.expected_token='current';S.meta.operator_authenticated=false;await learningOpen(LEARNING.view,R1);button=$('#learningDetail').querySelector('[data-learning-abandon]');assert.equal(button.disabled,true);await button.fire('click');assert.equal(mutations.length,0);S.meta.operator_authenticated=true;detail.revision.kind='lesson';await learningOpen(LEARNING.view,R1);assert.equal($('#learningDetail').querySelector('[data-learning-abandon]'),null);
""")

    def test_other_available_agents_do_not_enable_nonisolated_learning_execution(self):
        self.run_js(r"""
S.meta.agents=[{name:'codex',title:'Codex',available:true},{name:'claude',title:'Claude',available:false}];await openLearning();assert.equal($('#learningAgent').value,'');assert.equal($('#learningRunGo').disabled,true);assert.ok($('#learningDetail').textContent.includes('执行器不可用时保留草稿'));await submit('#learningRun');assert.equal(mutations.length,0);
""")

    def test_capture_result_does_not_steal_a_newer_detail_selection(self):
        self.run_js(r"""
await vLearning();const pending=later();postHandler=()=>pending.promise;const capture=main.querySelector('[data-learning-capture="0"]').fire('click');await learningOpen(LEARNING.view,R3);pending.resolve({revision_id:R2});await capture;assert.equal(LEARNING.view.detail.id,R3);assert.ok($('#learningDetail').textContent.includes(R3));
""")


if __name__ == "__main__":
    unittest.main()
