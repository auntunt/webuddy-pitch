"""User-facing navigation decisions for the delivery workbench.

These exercise the shipped JavaScript against lifecycle states, not CSS values.
"""
import shutil
import subprocess
import unittest

from tmh.platform.ui_delivery import DELIVERY_JS


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for delivery UI behavior checks")
class DeliveryDesignBehaviorTest(unittest.TestCase):
    def check_js(self, checks):
        helpers = r"""
const assert=require('node:assert/strict');
const ls={get:()=>null,set:()=>{}};
const S={meta:{agents:[{name:'codex',title:'Codex',available:true}]}};
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const md=h;
const stage={key:'research',name:'研究调研',state:'not_started',artifact:null,review:null,runs:[],blocked:[],run_blocked:[],review_blocked:[],can_start:true,can_review:false,allowed_modes:['ask']};
"""
        # Node reads stdin as UTF-8; the shipped JS + fixtures contain Chinese, and Windows default
        # text mode would encode them with the ANSI code page (GBK) and corrupt the source.
        result = subprocess.run([shutil.which("node"), "-"], input=helpers+DELIVERY_JS+"\n"+checks,
                                encoding="utf-8", errors="replace", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_running_work_links_to_observation_not_review(self):
        self.check_js(r"""
for(const status of ['queued','running']){
  const actual={...stage,artifact:{version:1},can_review:false,runs:[{status}]};
  assert.equal(dlNextStep(actual).target,'dlRuns');
  assert.ok(!dlNextStep(actual).label.includes('复核'));
}
""")

    def test_collection_requires_current_success_and_not_stale_result(self):
        self.check_js(r"""
const completed={...stage,state:'review',can_start:false,blocked:['先收集已完成的运行结果'],
  runs:[{status:'done',exit_code:0,collected:false,base_version:0}]};
assert.equal(dlNextStep(completed).target,'dlRuns');
for(const edit of [
  {issue:'运行依据已变化，需要基于当前依据重新执行',can_start:true,blocked:[]},
  {runs:[{status:'failed',exit_code:1,collected:false,base_version:0}],can_start:true,blocked:[]},
  {runs:[{status:'done',exit_code:0,collected:true,base_version:0}],can_start:true,blocked:[]},
  {artifact:{version:2},can_review:true,runs:[{status:'done',exit_code:0,collected:false,base_version:1}],can_start:true,blocked:[]}
])assert.notEqual(dlNextStep({...completed,...edit}).label,'检查并采集结果');
const staleUpstream={...completed,blocked:['先复核：需求与验收','先收集已完成的运行结果']};
assert.equal(dlNextStep(staleUpstream).target,'dlConditions');
""")

    def test_review_uses_explicit_current_version_permission(self):
        self.check_js(r"""
const draft={...stage,artifact:{version:3},can_review:true};
assert.equal(dlNextStep(draft).target,'dlReviewSection');
for(const can_review of [false,undefined]){
 const blocked={...draft,can_review,review_blocked:['缺少当前版本验证']};
 assert.notEqual(dlNextStep(blocked).label,'复核本版本');
}
const approved={...draft,state:'approved',review:{version:3}};
assert.equal(dlNextStep(approved).label,'查看复核依据');
assert.ok(!JSON.stringify(dlNextStep(approved)).includes('发布成功'));
""")

    def test_approved_plan_leads_to_implementation_not_stage_completion(self):
        self.check_js(r"""
const plan={...stage,key:'develop',artifact:{version:1},review:{version:1},plan_approved:true,allowed_modes:['plan','fix']};
assert.equal(dlNextStep(plan).target,'dlRunTools');
assert.equal(dlNextStep(plan).label,'准备执行实现');
assert.notEqual(dlNextStep({...plan,allowed_modes:['plan']}).label,'准备执行实现');
assert.equal(dlNextStep(stage,false).target,'dlArtifactSection');
""")

    def test_search_and_state_filters_keep_full_source_records(self):
        self.check_js(r"""
const rows=[
 {id:1,title:'客户门户',goal:'支持 SSO 登录并保留审计',project:'PORTAL',project_name:'服务平台',type_name:'新功能',state:'draft'},
 {id:2,title:'性能验证',goal:'查询延迟',project:'ERP',project_name:'业务系统',type_name:'质量与安全',state:'approved'}
],snapshot=JSON.stringify(rows);
for(const query of ['门户','sso',' portal ','服务平台','新功能'])assert.deepEqual(dlFilterRows(rows,query,''),[rows[0]]);
assert.deepEqual(dlFilterRows(rows,'','approved'),[rows[1]]);
assert.deepEqual(dlFilterRows(rows,'客户','approved'),[]);
assert.deepEqual(dlFilterRows(rows,'不存在',''),[]);
assert.deepEqual(dlFilterRows(rows,'',''),rows);
assert.equal(JSON.stringify(rows),snapshot);
""")

    def test_first_action_reorders_without_removing_artifacts_or_guards(self):
        self.check_js(r"""
const d={id:'delivery-1'};
let html=dlStageBody(d,stage);
assert.ok(html.indexOf('id="dlRunTools"')<html.indexOf('id="dlArtifactSection"'));
assert.ok(html.includes('id="dlArtifactForm"'));
assert.ok(html.includes('id="dlReviewSection"'));
const body='完整正文 <script>alert(1)</script>\n'+('长内容与证据\n'.repeat(2000));
html=dlStageBody(d,{...stage,artifact:{version:2,title:'方案',body},can_review:false,can_start:false,review_blocked:['缺少验证证据']});
assert.ok(html.indexOf('id="dlArtifactSection"')<html.indexOf('id="dlRunTools"'));
assert.ok(html.includes(h(body)),'the full artifact is still present');
assert.ok(!html.includes('<script>'));
assert.match(html,/id="dlRunGo"\s+disabled/);
assert.match(html,/id="dlReviewGo" type="submit"\s+disabled/);
assert.ok(html.includes('缺少验证证据'));
for(const id of ['dlArtifactForm','dlRunForm','dlReviewForm','dlStageError','dlConditions','dlRuns']){
 assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id+' must remain unique');
}
""")

    def test_missing_source_receipt_offers_retry_instead_of_impossible_collection(self):
        self.check_js(r"""
const missing='运行缺少可核对的固定版本回执';
const actual={...stage,key:'quality',state:'review',can_start:true,
 issue:missing+'；请重新运行当前阶段',
 runs:[{id:4,mode:'ask',status:'done',exit_code:0,collected:false,base_version:0,
 can_collect:false,collect_blocked:[missing],result:'完整的旧运行输出'}]};
const next=dlNextStep(actual),html=dlStageBody({id:'source-fixture'},actual);
assert.equal(next.target,'dlRunTools');
assert.ok(!next.label.includes('采集'));
assert.ok(!html.includes('data-dl-collect='),'invalid evidence cannot offer collection');
assert.match(html,/<span class="dl-muted">运行缺少可核对的固定版本回执。请基于当前版本重新运行。<\/span>/);
for(const [,value] of html.matchAll(/class="([^"]*)"/g)){
 assert.ok(!value.includes('<')&&!value.includes('>'),'recovery prose must not be inserted into a class attribute');
}
assert.ok(html.includes('完整的旧运行输出'),'failed evidence remains inspectable');
const ready={...actual,issue:'',runs:[{...actual.runs[0],can_collect:true,collect_blocked:[]}]};
assert.equal(dlNextStep(ready).target,'dlRuns');
assert.ok(dlStageBody({id:'source-fixture'},ready).includes('data-dl-collect="4"'));
""")

    def test_source_identity_is_complete_and_untrusted_receipt_text_is_escaped(self):
        self.check_js(r"""
const commit='0123456789abcdef0123456789abcdef01234567';
const hostile='<script>alert("wrong evidence")</script>';
const source={commit,implementation_run:2,plan_run:1};
const actual={...stage,key:'quality',source,state:'review',
 runs:[{id:4,mode:'ask',status:'done',exit_code:0,collected:false,base_version:0,
 can_collect:false,collect_blocked:[hostile],binding:source,
 source_receipt:{actual_commit:commit,code_unchanged:false,error:hostile},result:hostile}]};
let html=dlStageBody({id:'source-fixture'},actual);
assert.ok(html.includes('<code>'+commit+'</code>'),'the full SHA must be visible');
assert.ok(html.includes('实现运行 #2 · 已复核方案 #1'));
assert.ok(html.includes('实现 #2 · 方案 #1'));
assert.ok(html.includes(h(JSON.stringify(actual.runs[0].source_receipt,null,2))),'the full receipt remains readable');
assert.ok(html.includes(h(hostile)));
assert.ok(!html.includes('<script>'));
const hostileSource={...source,commit:hostile,plan_run:hostile,implementation_run:hostile};
html=dlStageBody({id:'source-fixture'},{...actual,source:hostileSource,runs:[{...actual.runs[0],binding:hostileSource}]});
assert.ok(!html.includes('<script>'));
assert.ok(html.includes('<code>'+h(hostile)+'</code>'));
""")


if __name__ == "__main__":
    unittest.main()
