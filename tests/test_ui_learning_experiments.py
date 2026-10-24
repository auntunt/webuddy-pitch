"""Shipped experiment UI with deterministic responses, no services or models."""
import shutil
import subprocess
import unittest

from test_ui_library import HARNESS
from test_ui_learning import SETUP as LEARNING_SETUP
from test_ui_access import SETUP as ACCESS_SETUP
from tmh.platform.ui_access import ACCESS_BOOT_JS
from tmh.platform.ui_learning import LEARNING_JS
from tmh.platform.ui_memory import MEMORY_JS


SETUP = r"""
S.projects=[{id:1,key:'APP',name:'项目'},{id:2,key:'STD',name:'标品'}];
S.meta.user='alice';S.meta.access={tenants:[{id:'alpha',url:'/t/alpha/'},{id:'beta',url:'/t/beta/'}],tenant:{id:'alpha'},context_token:'context-a',user:'alice',role:'admin',capabilities:{write:true}};
ACCESS.base='/t/alpha';accessBind(S.meta);
const EID='e'.repeat(32),CH='f'.repeat(64);
let accountEpoch='alice-epoch';
const requestIdentity=()=>({tenant_id:S.meta.access.tenant.id,actor:S.meta.access.user,account_epoch:accountEpoch});
const experiment=(extra={})=>({id:EID,tenant_id:'alpha',project_id:1,state:'sealed',contract_hash:CH,planned_slots:6,recorded_slots:6,
 rsi_qualified:false,production_prompt_equivalence:false,protected:true,can_adopt:false,request_identity:requestIdentity(),
 scientific_contract:{candidate_revision_id:R1,baseline_revision_id:R2,source:{project_id:1,commit:'a'.repeat(40)},roles:{curator:'alice',optimizer:'bob',selector:'carol'},known_custodians:['alice'],repeats:1,planned_slots:6,task_count:3,synthetic_source_families:3,budget:{max_calls:6,timeout_seconds:120,concurrency:1},task_set:'synthetic-three-families-v1',executor:{id:'synthetic-fixed-a-v1'}},
 budget:{max_calls:6,reserved_calls:1,settled_calls:2,synthetic_units:2},capabilities:{seal:false,start:true,cancel:true,expose:true},
 assets:[{id:'a1',kind:'oracle',family:'family-a',protected:true},{id:'a2',kind:'task',family:'family-a',protected:true}],
 slots:Array.from({length:6},(_,i)=>({id:'slot'+i,ordinal:i+1,arm:i%2?'candidate':'baseline',repeat:1,state:i===0?'unknown':i<3?'completed':'not_executed',reserved_calls:i===0?1:0,settled_calls:i>0&&i<3?1:0})),...extra});
let experimentData=experiment();
getHandler=url=>{const q=new URL('http://local'+url).searchParams;return q.has('experiment')?experimentData:q.has('experiments')?{experiments:[experimentData],can_create:true,request_identity:requestIdentity()}:q.has('revision')?learningDetails.get(q.get('revision')):learningData};
const experimentReply=(body,e=experimentData)=>({receipt:{experiment_id:e.id,contract_hash:e.contract_hash,job_id:'b'.repeat(32),state:e.state,replayed:false,request_id:body.request_id,action:body.action.slice('experiment_'.length)}});
postHandler=async(path,body)=>experimentReply(body);
const openExperiments=async()=>{await vLearning();await $('#learningExperimentsOpen').fire('click')};
const openExperiment=async()=>{await openExperiments();await main.querySelector('[data-experiment-open="0"]').fire('click')};
"""


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for shipped experiment UI checks")
class ExperimentUiTests(unittest.TestCase):
    def run_js(self, checks):
        result = subprocess.run([shutil.which("node"), "-"], input=HARNESS + ACCESS_SETUP + ACCESS_BOOT_JS + LEARNING_SETUP + MEMORY_JS + LEARNING_JS + SETUP +
            "\n(async()=>{\n" + checks + "\n})().catch(error=>{console.error(error);process.exitCode=1});", text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reading_does_not_create_execute_expose_or_claim_real_benefit(self):
        self.run_js(r"""
await vLearning();assert.equal(requests.length,1);assert.equal(mutations.length,0);
await $('#learningExperimentsOpen').fire('click');await main.querySelector('[data-experiment-open="0"]').fire('click');
const box=$('#learningExperiments');assert.equal(box.querySelectorAll('[data-experiment-asset]').length,2);assert.ok(box.textContent.includes('计划总数'));assert.ok(box.textContent.includes('结果未知'));assert.ok(box.textContent.includes('未执行'));assert.ok(box.textContent.includes('RSI 资格未开放'));assert.ok(box.textContent.includes('真实费用与 Token 未测量'));assert.ok(box.textContent.includes('完整科学合同摘要'));assert.equal(mutations.length,0);
""")

    def test_full_granted_material_is_lossless_and_escaped(self):
        self.run_js(r"""
const raw='<script>oracle()</script>\r\n'+'完整原文Ω'.repeat(12000)+'\r\nTAIL';experimentData=experiment({protected:false,assets:[{id:'a1',kind:'oracle',family:'family-a',protected:false,content:{raw}}],report:{full:raw}});
await openExperiment();const html=$('#learningExperiments').innerHTML;assert.ok(html.includes(h(learningText({raw}))));assert.ok(html.includes('TAIL'));assert.ok(!html.includes('<script>'));assert.equal(mutations.length,0);
""")

    def test_unknown_freezes_original_body_and_request_across_reload(self):
        self.run_js(r"""
await openExperiment();postHandler=async()=>{throw Error('连接中断')};await main.querySelector('[data-experiment-action="start"]').fire('click');
assert.equal(mutations.length,1);const original=structuredClone(mutations[0].body);assert.equal(original.action,'experiment_start');assert.ok(original.request_id);
assert.equal(main.querySelector('[data-experiment-action="cancel"]').disabled,true);await experimentSend(EXPERIMENT_UI.view,{action:'experiment_cancel',experiment_id:EID});assert.equal(mutations.length,1);
learningExperimentsClear();EXPERIMENT_UI.requests.clear();await learningExperimentsLoad(LEARNING.view);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,1);
postHandler=async(path,body)=>experimentReply(body);await main.querySelector('[data-experiment-retry="0"]').fire('click');assert.equal(mutations.length,2);assert.deepEqual(mutations[1].body,original);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);
""")

    def test_wrong_request_or_contract_receipt_does_not_clear_unknown(self):
        self.run_js(r"""
experimentData=experiment({state:'draft',capabilities:{seal:true,start:false,cancel:true,expose:true}});await openExperiment();
postHandler=async(path,body)=>({receipt:{...experimentReply(body).receipt,request_id:'wrong-request'}});await main.querySelector('[data-experiment-action="seal"]').fire('click');assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,1);const original=structuredClone(mutations[0].body);assert.equal(original.expected_hash,CH);
postHandler=async(path,body)=>experimentReply(body,experiment({...experimentData,contract_hash:'different'}));await main.querySelector('[data-experiment-retry="0"]').fire('click');assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,1);assert.deepEqual(mutations[1].body,original);
""")

    def test_explicit_exposure_sends_only_selected_ids_and_no_grant_to_other_person(self):
        self.run_js(r"""
await openExperiment();assert.equal(mutations.length,0);main.querySelector('[data-experiment-asset="1"]').checked=true;await $('#experimentExpose').fire('submit');
assert.equal(mutations.length,1);assert.equal(mutations[0].body.action,'experiment_expose');assert.deepEqual(mutations[0].body.asset_ids,['a2']);assert.equal(mutations[0].body.expected_hash,CH);assert.equal(mutations[0].body.recipient,undefined);assert.equal(mutations[0].body.actor,undefined);
""")

    def test_three_access_clear_hooks_discard_late_old_identity_reads(self):
        for hook in ("bind", "lock", "switch"):
            with self.subTest(hook=hook):
                action = {"bind": "accessBind({access:{tenant:{id:'alpha'},user:'bob',context_token:'context-b'}});S.meta.access.user='bob';S.meta.access.context_token='context-b'",
                          "lock": "accessLock('权限已撤销')",
                          "switch": "accessSwitch('beta')"}[hook]
                self.run_js(r"""
await openExperiments();const late=later();getHandler=()=>late.promise;const request=learningExperimentOpen(LEARNING.view,EID);const prior=EXPERIMENT_UI.view;
""" + action + r""";
assert.equal(EXPERIMENT_UI.view,null);late.resolve(experiment({protected:false,assets:[{id:'secret',kind:'oracle',protected:false,content:'LATE-SECRET'}]}));await request;assert.ok(!main.textContent.includes('LATE-SECRET'));assert.equal(experimentCurrent(prior),false);assert.equal(mutations.length,0);
""")

    def test_late_write_response_does_not_fill_changed_person_page(self):
        self.run_js(r"""
await openExperiment();const pending=later();postHandler=()=>pending.promise;const request=main.querySelector('[data-experiment-action="start"]').fire('click');
accessBind({access:{tenant:{id:'alpha'},user:'bob',context_token:'context-b'}});S.meta.access.user='bob';S.meta.access.context_token='context-b';
pending.resolve(experimentReply(mutations[0].body,experiment({protected:false,assets:[{id:'a',kind:'oracle',content:'OLD-WRITE-SECRET'}]})));await request;assert.ok(!main.textContent.includes('OLD-WRITE-SECRET'));assert.equal(EXPERIMENT_UI.view,null);
""")

    def test_managed_job_never_renders_manual_retry_or_adopt_controls(self):
        self.run_js(r"""
learningData=learningOverview({jobs:[learningJob({managed:true,protected:true,status:'running',experiment_ids:[EID]})]});await vLearning();const jobs=$('#learningJobs');assert.equal(jobs.querySelectorAll('[data-learning-job-action]').length,0);assert.ok(jobs.textContent.includes('合成机制演练'));assert.equal(learningJobPassed({managed:true,status:'passed'}),false);
learningDetails.set(R1,learningRevision(R1,{managed:true,protected:true,revision:{id:R1,managed:true,protected:true,experiment_ids:[EID]},jobs:[]}));await learningOpen(LEARNING.view,R1);assert.equal($('#learningAdopt'),null);assert.equal($('#learningRunGo'),null);assert.equal($('#learningProposeGo'),null);assert.equal(mutations.length,0);
""")

    def test_storage_failure_stops_before_post(self):
        self.run_js(r"""
await openExperiment();ACCESS_RAW_SESSION.setItem=()=>{throw Error('storage full')};await main.querySelector('[data-experiment-action="start"]').fire('click');assert.equal(mutations.length,0);assert.ok($('#learningExperiments').textContent.includes('无法保存原请求'));assert.equal(main.querySelector('[data-experiment-action="cancel"]').disabled,true);
""")

    def test_create_form_checks_complete_contract_before_registering_request(self):
        self.run_js(r"""
await openExperiments();await $('#experimentCreate').fire('submit');assert.equal(mutations.length,0);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);
$('#experimentRevision').value=R1;await $('#experimentCreate').fire('submit');assert.equal(mutations.length,0);
$('#experimentCurator').value='alice';$('#experimentOptimizer').value='bob';$('#experimentSelector').value='carol';$('#experimentRepeats').value='11';await $('#experimentCreate').fire('submit');assert.equal(mutations.length,0);
$('#experimentRepeats').value='2';postHandler=async()=>{throw Error('响应中断')};await $('#experimentCreate').fire('submit');assert.equal(mutations.length,1);const c=mutations[0].body.contract;assert.deepEqual(Object.keys(c).sort(),['candidate_revision_id','repeats','max_calls','timeout_seconds','curator','optimizer','selector','executor_id','task_set'].sort());assert.equal(c.max_calls,12);assert.equal(c.repeats,2);assert.equal(c.executor_id,'synthetic-fixed-a-v1');assert.equal(c.task_set,'synthetic-three-families-v1');assert.ok($('#learningExperiments').textContent.includes('核对原操作与完整请求'));
""")

    def test_create_accepts_real_captured_revision_id_without_rewriting_it(self):
        self.run_js(r"""
await openExperiments();$('#experimentCurator').value='alice';$('#experimentOptimizer').value='bob';$('#experimentSelector').value='carol';$('#experimentRevision').value='   ';await $('#experimentCreate').fire('submit');assert.equal(mutations.length,0);
const actual='LR'+'a'.repeat(40);$('#experimentRevision').value=actual;postHandler=async()=>{throw Error('结果未知')};await $('#experimentCreate').fire('submit');assert.equal(mutations.length,1);assert.equal(mutations[0].body.contract.candidate_revision_id,actual);assert.equal(experimentUnknown(EXPERIMENT_UI.view)[0][1].body.contract.candidate_revision_id,actual);
""")

    def test_successful_record_read_replaces_loading_notice(self):
        self.run_js(r"""
await openExperiment();await main.querySelector('[data-experiment-action="start"]').fire('click');
assert.equal(mutations.length,1);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);
assert.ok($('#experimentNotice').textContent.includes('当前记录已读取'));assert.ok(!$('#experimentNotice').textContent.includes('正在读取'));
const count=mutations.length;await $('#experimentRefresh').fire('click');assert.equal(mutations.length,count);
""")

    def test_committed_receipt_then_get_failure_never_resends_post(self):
        self.run_js(r"""
await openExperiment();getHandler=async()=>{throw Object.assign(Error('读取暂不可用'),{status:503})};await main.querySelector('[data-experiment-action="start"]').fire('click');
assert.equal(mutations.length,1);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);assert.ok($('#learningExperiments').textContent.includes('操作已登记，视图待刷新'));assert.equal(main.querySelector('[data-experiment-retry="0"]'),null);
await $('#experimentReceiptRefresh').fire('click');assert.equal(mutations.length,1);
learningExperimentsClear();EXPERIMENT_UI.requests.clear();getHandler=url=>new URL('http://local'+url).searchParams.has('experiment')?experimentData:{experiments:[experimentData],can_create:true,request_identity:requestIdentity()};await learningExperimentsLoad(LEARNING.view);
assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);assert.ok($('#experimentReceiptRefresh'));await $('#experimentReceiptRefresh').fire('click');assert.equal(mutations.length,1);
""")

    def test_only_explicit_not_written_code_releases_a_failed_request(self):
        self.run_js(r"""
await openExperiment();postHandler=async()=>{throw Object.assign(Error('拒绝'),{status:403})};await main.querySelector('[data-experiment-action="start"]').fire('click');const original=structuredClone(mutations[0].body);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,1);
postHandler=async()=>{throw Object.assign(Error('原请求未提交，事务已回滚'),{status:409,code:'experiment_not_written'})};await main.querySelector('[data-experiment-retry="0"]').fire('click');assert.deepEqual(mutations[1].body,original);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);assert.ok($('#learningExperiments').textContent.includes('服务器确认原请求未写入'));
postHandler=async(path,body)=>experimentReply(body);await main.querySelector('[data-experiment-action="start"]').fire('click');assert.notEqual(mutations[2].body.request_id,original.request_id);
""")

    def test_access_lock_and_reload_preserve_same_person_original_unknown_request(self):
        self.run_js(r"""
await openExperiment();postHandler=async()=>{throw Error('写入结果未知')};await main.querySelector('[data-experiment-action="start"]').fire('click');const original=structuredClone(mutations[0].body),identity=EXPERIMENT_UI.view.identity;
accessLock('权限已变化');assert.equal(EXPERIMENT_UI.view,null);assert.ok(!main.textContent.includes(original.request_id));
assert.ok(ACCESS_RAW_SESSION.getItem(experimentStorageKey(identity)),'accessLock must retain isolated pending receipt');
// A page reload discards all in-memory requests; only the native session ledger survives.
EXPERIMENT_UI.requests.clear();LEARNING.view=null;ACCESS.ready=false;ACCESS.blocked=false;S.projects=[{id:1,key:'APP',name:'项目'}];S.scope='APP';S.meta.access.context_token='context-after-reauthorization';accessBind(S.meta);
getHandler=url=>new URL('http://local'+url).searchParams.has('experiments')?{experiments:[experimentData],can_create:true,request_identity:requestIdentity()}:learningData;
await openExperiments();assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,1);assert.equal(mutations.length,1);assert.deepEqual(experimentUnknown(EXPERIMENT_UI.view)[0][1].body,original);
postHandler=async(path,body)=>experimentReply(body);await main.querySelector('[data-experiment-retry="0"]').fire('click');assert.equal(mutations.length,2);assert.deepEqual(mutations[1].body,original);
""")

    def test_saved_unknown_is_not_shown_to_other_person_or_recreated_account(self):
        self.run_js(r"""
await openExperiment();postHandler=async()=>{throw Error('未知')};await main.querySelector('[data-experiment-action="start"]').fire('click');const original=structuredClone(mutations[0].body);
const login=async(user,epoch)=>{learningExperimentsClear();EXPERIMENT_UI.requests.clear();LEARNING.view=null;ACCESS.ready=false;ACCESS.blocked=false;S.projects=[{id:1,key:'APP',name:'项目'}];S.scope='APP';S.meta.user=user;S.meta.access.user=user;S.meta.access.context_token='context-'+epoch;accountEpoch=epoch;accessBind(S.meta);experimentData=experiment();await openExperiments()};
await login('bob','bob-epoch');assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);assert.ok(!main.textContent.includes(original.request_id));assert.equal(mutations.length,1);
await login('alice','alice-recreated');assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);assert.ok(!main.textContent.includes(original.request_id));assert.equal(mutations.length,1);
await login('alice','alice-epoch');assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,1);assert.deepEqual(experimentUnknown(EXPERIMENT_UI.view)[0][1].body,original);assert.equal(mutations.length,1);
""")

    def test_pending_restore_waits_for_authorized_get_and_rejects_foreign_identity(self):
        self.run_js(r"""
await openExperiment();postHandler=async()=>{throw Error('未知')};await main.querySelector('[data-experiment-action="start"]').fire('click');const original=structuredClone(mutations[0].body);
learningExperimentsClear();EXPERIMENT_UI.requests.clear();getHandler=async()=>{throw Object.assign(Error('项目权限已撤销'),{status:403})};await learningExperimentsLoad(LEARNING.view);assert.equal(EXPERIMENT_UI.view.identity,'');assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);assert.ok(!main.textContent.includes(original.request_id));assert.equal(mutations.length,1);
getHandler=()=>({experiments:[],can_create:true,request_identity:{tenant_id:'alpha',actor:'bob',account_epoch:'bob-epoch'}});await learningExperimentsLoad(LEARNING.view);assert.equal(EXPERIMENT_UI.view.identity,'');assert.equal(mutations.length,1);assert.ok(main.textContent.includes('当前个人身份'));
""")

    def test_late_not_written_from_old_context_cannot_erase_restored_unknown(self):
        self.run_js(r"""
await openExperiment();const pending=later();postHandler=()=>pending.promise;const postRequest=main.querySelector('[data-experiment-action="start"]').fire('click');const original=structuredClone(mutations[0].body),identity=EXPERIMENT_UI.view.identity;
accessBind({access:{tenant:{id:'alpha'},user:'alice',context_token:'context-new'}});S.meta.access.context_token='context-new';await learningExperimentsLoad(LEARNING.view);const fresh=EXPERIMENT_UI.view,stored=ACCESS_RAW_SESSION.getItem(experimentStorageKey(identity));assert.equal(experimentUnknown(fresh).length,1);
pending.reject(Object.assign(Error('旧请求未写入'),{status:409,code:'experiment_not_written'}));await postRequest;
assert.equal(EXPERIMENT_UI.view,fresh);assert.equal(experimentUnknown(fresh).length,1);assert.deepEqual(experimentUnknown(fresh)[0][1].body,original);assert.equal(ACCESS_RAW_SESSION.getItem(experimentStorageKey(identity)),stored);assert.equal(mutations.length,1);
""")

    def test_detached_retry_callback_cannot_turn_recorded_intent_into_new_post(self):
        self.run_js(r"""
await openExperiment();postHandler=async()=>{throw Error('未知')};await main.querySelector('[data-experiment-action="start"]').fire('click');const original=structuredClone(mutations[0].body),oldRetry=main.querySelector('[data-experiment-retry="0"]').onclick;
postHandler=async(path,body)=>experimentReply(body);await oldRetry();assert.equal(mutations.length,2);assert.deepEqual(mutations[1].body,original);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);
await oldRetry();assert.equal(mutations.length,2);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);
""")

    def test_detached_retry_callback_cannot_revive_definitely_not_written_intent(self):
        self.run_js(r"""
await openExperiment();postHandler=async()=>{throw Error('未知')};await main.querySelector('[data-experiment-action="start"]').fire('click');const oldRetry=main.querySelector('[data-experiment-retry="0"]').onclick;
postHandler=async()=>{throw Object.assign(Error('原请求确证未写入'),{code:'experiment_not_written'})};await oldRetry();assert.equal(mutations.length,2);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);
postHandler=async(path,body)=>experimentReply(body);await oldRetry();assert.equal(mutations.length,2);assert.equal(experimentUnknown(EXPERIMENT_UI.view).length,0);
""")

    def test_detached_retry_cannot_dispatch_later_intent_reusing_action_key(self):
        self.run_js(r"""
await openExperiment();postHandler=async()=>{throw Error('未知')};await main.querySelector('[data-experiment-action="start"]').fire('click');const oldRetry=main.querySelector('[data-experiment-retry="0"]').onclick,original=structuredClone(mutations[0].body);
postHandler=async()=>{throw Object.assign(Error('原请求未写入'),{code:'experiment_not_written'})};await oldRetry();
postHandler=async()=>{throw Error('新意图结果未知')};await main.querySelector('[data-experiment-action="start"]').fire('click');assert.equal(mutations.length,3);assert.notEqual(mutations[2].body.request_id,original.request_id);const next=structuredClone(mutations[2].body);
await oldRetry();assert.equal(mutations.length,3);assert.deepEqual(experimentUnknown(EXPERIMENT_UI.view)[0][1].body,next);
""")

    def test_managed_catalog_never_turns_unchecked_source_into_current_claim(self):
        self.run_js(r"""
const html=learningStatuses({managed:true,revision_id:R1,stale:null,currentness:'not_checked',kind:'lesson',machine:{status:'managed'},human:{status:'historical'}});
assert.ok(html.includes('受管实验历史，未核验当前来源'));assert.ok(html.includes('受管实验历史'));assert.ok(!html.includes('本次来源可用'));assert.equal(mutations.length,0);
""")

    def test_manual_target_with_managed_history_keeps_manual_controls(self):
        self.run_js(r"""
const body='旧手工正文\r\n完整保留',job=learningJob({steps:[],result:{output:'原手工评审结果'}});
learningDetails.set(R1,learningRevision(R1,{jobs:[job],history:[{id:R1,content:body},{id:R2,managed:true,protected:true,content:null,experiment_ids:[EID]}],decisions:[{id:'decision',action:'adopt',result:{recorded:'完整决定'}}]}));await openLearning(R1);
const root=$('#learningDetail');assert.ok(root.querySelector('#learningRunGo'));assert.equal(root.querySelector('#learningRunGo').disabled,false);assert.equal(root.querySelector('#learningProposeGo').disabled,false);assert.equal(root.querySelector('#learningAdopt').disabled,false);assert.ok(root.textContent.includes('完整决定'));assert.ok(root.innerHTML.includes('旧手工正文'));assert.ok(!root.textContent.includes('此修订已用于合成机制演练'));assert.equal(mutations.length,0);
""")
