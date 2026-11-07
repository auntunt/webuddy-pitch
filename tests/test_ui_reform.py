"""Run workspace handlers with the existing DOM fixture; not browser acceptance."""
import shutil
import subprocess
import unittest
from tests.test_ui_library import HARNESS
from tmh.platform.ui import page
from tmh.platform.ui_reform import REFORM_JS

SETUP = r'''
const pageHead=(title,subtitle,actions='')=>`<h1>${h(title)}</h1>${actions}`;
const paintTabs=()=>{},accessCanWrite=()=>true,accessCanExecute=()=>true,accessProjectRole=()=> 'manager';
const stopPolls=tag=>{S.polls=S.polls.filter(p=>p.tag!==tag)};
const storage=new Map();const sessionStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
document.querySelectorAll=s=>main.querySelectorAll(s);const toast=()=>{},rfForm=()=>{};
S.meta={};location.hash='#/projects/APP/reforms/plan-1';
const plan={id:'plan-1',title:'订单改造',revision:2,next_owner:'owner',batch:1,batch_label:'第 1 批',status_updated:'2026-11-07',
 counts:{total:4,released:1,closed:1,business_accepted:0,first_pass:0,first_verdict_total:1},items:[],log:[],criteria:[],domains:[],evidence:{integrated_delivery:'pending'},
 blocked:'环境未配置',paused:'已暂停',checkpoint:{id:7,source_commit:'a'.repeat(40)},deep_link:'#/projects/APP/reforms/plan-1'};
getHandler=()=>plan;
'''

@unittest.skipUnless(shutil.which('node'), 'Node required')
class ReformUiTest(unittest.TestCase):
    def run_js(self, checks):
        result=subprocess.run(['node','-'],input=HARNESS+REFORM_JS+SETUP+'\n(async()=>{'+checks+'})().catch(e=>{console.error(e);process.exitCode=1})',text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_complete_page_syntax(self):
        script=page().split('<script>')[1].split('</script>')[0]
        result=subprocess.run(['node','--check'],input=script,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_summary_uses_current_sample_and_no_closed_as_accepted(self):
        self.run_js(r"await rfWorkspace('APP','plan-1');assert.match(main.textContent,/owner/);assert.match(main.textContent,/环境未配置/);assert.match(main.textContent,/第 1 批/);assert.match(main.textContent,/已验收0 \/ 4/);assert.match(main.textContent,/首次验收通过样本0 \/ 1/);assert.match(main.textContent,/#7/);assert.ok(!main.textContent.includes('已整体验收'));")

    def test_late_response_does_not_replace_other_route(self):
        self.run_js("const wait=later();getHandler=()=>wait.promise;const pending=rfWorkspace('APP','plan-1');location.hash='#/projects/STD/reforms/other';main.innerHTML='其他计划';wait.resolve(plan);await pending;assert.equal(main.textContent,'其他计划');")

    def test_list_failure_is_not_empty_and_recovery_read_does_not_mutate(self):
        self.run_js("getHandler=()=>{throw Error('网络中断')};await rfList('APP');assert.match(main.textContent,/加载失败/);assert.ok(!main.textContent.includes('没有符合'));assert.equal(mutations.length,0);")

    def test_list_keeps_bound_deep_link_and_current_counts(self):
        self.run_js("getHandler=()=>({items:[{...plan,state:'paused'}],built:true,has_more:false});await rfList('APP');assert.ok(main.querySelector('[href=\"#/projects/APP/reforms/plan-1\"]'));assert.match(main.textContent,/已验收 0 [/] 4/);assert.match(main.textContent,/第 1 批/);assert.equal(mutations.length,0);")

    def test_scope_keeps_full_lead_dependencies_and_contract_text(self):
        self.run_js(r"plan.goal='完整目标';plan.keep='接口不变';plan.dependencies=['先核对退款规则'];plan.items=[{lead:true,title:'先导',body:'正文'.repeat(4000)+'尾部约束'}];await rfWorkspace('APP','plan-1','scope');assert.match(main.textContent,/完整目标/);assert.match(main.textContent,/接口不变/);assert.match(main.textContent,/先核对退款规则/);assert.match(main.textContent,/尾部约束/);")
