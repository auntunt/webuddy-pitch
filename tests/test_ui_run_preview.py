"""Browser-independent checks for matching the visible preview to a specific implementation."""
import shutil
import subprocess
import unittest

from tmh.platform.ui import JS


# A minimal DOM double drives the shipped event handlers; no browser or real API is used.
ASYNC_HARNESS = r"""
const S={polls:[]};
class TestElement {
  constructor(attrs=''){this.attrs=attrs;this.dataset={};this.disabled=/\bdisabled\b/.test(attrs);this.hidden=/\bhidden\b/.test(attrs);this.isConnected=true;this.classList={toggle(){}};for(const m of attrs.matchAll(/data-([\w-]+)(?:="([^"]*)")?/g))this.dataset[m[1].replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=m[2]||'';this.nodes=[];this._html=''}
  set innerHTML(html){this._html=html;this.nodes=[...html.matchAll(/<[^/!][^>]*\bdata-[^>]*>/g)].map(m=>new TestElement(m[0]));const pv=this.nodes.find(n=>'runPreview' in n.dataset);if(pv){const start=html.indexOf('<div data-run-preview>')+22;const end=html.lastIndexOf('</div></section>');pv.innerHTML=html.slice(start,end)}}
  get innerHTML(){return this._html}
  querySelectorAll(selector){const m=selector.match(/^\[data-([\w-]+)(?:="([^"]*)")?\]$/);if(!m)return[];const key=m[1].replace(/-([a-z])/g,(_,c)=>c.toUpperCase());const pv=this.nodes.find(n=>'runPreview' in n.dataset);const own=this.nodes.filter(n=>key in n.dataset&&(m[2]===undefined||n.dataset[key]===m[2]));if(key.startsWith('runPreview')&&key!=='runPreview'&&pv)return pv.querySelectorAll(selector);return own}
  querySelector(s){return this.querySelectorAll(s)[0]||null}
  setAttribute(){}
  focus(){}
  click(){return this.onclick?.()}
}
const body=new TestElement(), modalBox={hidden:true};
const $=selector=>selector==='#mbody'?body:selector==='#modal'?modalBox:null;
const modal=html=>{body.innerHTML=html;modalBox.hidden=false};
const stopPolls=tag=>{S.polls=S.polls.filter(p=>p.tag!==tag)};
let timerId=0;const poll=(fn,ms,tag)=>{const id=++timerId;S.polls.push({id,fn,tag});return id};
const clearInterval=()=>{};
const md=h,diffHtml=h,mTag=()=>'',moLabel=h,ago=()=>'',toast=()=>{};
let getHandler,postHandler;
const get=url=>getHandler(url),post=(url,data)=>postHandler(url,data);
const later=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
const detail=(id,decision='')=>({id,mode:'fix',ticket_key:'APP-'+id,decision,status:'done',exit_code:0,diff:'diff --git a/app.py b/app.py\n+edited',result:'implementation',output:'',output_len:0,agent:'local',author:'test',created:''});
"""

@unittest.skipUnless(shutil.which("node"), "Node.js is needed to check the shipped UI functions")
class RunPreviewUiTest(unittest.TestCase):
    def run_js(self, checks, controller=False):
        helpers = JS.split("// ---------- runs\n", 1)[1].split("async function showRun", 1)[0]
        if controller:
            helpers = JS.split("// ---------- runs\n", 1)[1].split("async function showPrompt", 1)[0]
        script = r"""
const assert = require('node:assert/strict');
const h = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const run = {id:7,mode:'fix',ticket_key:'APP-1',decision:'accepted:tmh/APP-1@abc123'};
const ready = {run_id:7,expected_commit:'abc123',matches_run:true,preview:{state:'up',commit:'abc123'},url:'/pv/APP-1/',cmd:'python3 app.py',own_address:true};
""" + (ASYNC_HARNESS if controller else "") + helpers + "\n(async()=>{\n" + checks + "\n})().catch(e=>{console.error(e);process.exitCode=1});"
        result = subprocess.run([shutil.which("node"), "-"], input=script, encoding="utf-8", errors="replace", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unaccepted_and_discarded_changes_never_reuse_ticket_preview(self):
        self.run_js(r"""
for (const decision of ['', 'discarded']) {
  const r={...run,decision};
  assert.equal(runPreviewPath(r),'');
  const html=runPreviewHtml(r,ready,'');
  assert.ok(!html.includes('href="/pv/'));
  assert.ok(!html.includes('data-run-preview-start'));
}
assert.ok(runPreviewHtml({...run,decision:''},ready,'').includes('采纳不会合并主干'));
""")

    def test_open_link_requires_same_run_and_ready_matching_commit(self):
        self.run_js(r"""
assert.ok(runPreviewHtml(run,ready,'').includes('href="/pv/APP-1/"'));
for (const d of [
  {...ready,matches_run:false},
  {...ready,run_id:8},
  {...ready,expected_commit:''},
  {...ready,preview:{state:'starting',commit:'abc123'}},
  {...ready,preview:{state:'failed',commit:'abc123'}},
  {...ready,url:'javascript:alert(1)'}
]) assert.ok(!runPreviewHtml(run,d,'').includes('打开本次改动预览'));
const previous={...ready,matches_run:false,preview:{state:'up',commit:'previous'}};
const html=runPreviewHtml(run,previous,'');
assert.ok(html.includes('无法确认对应本次改动'));
assert.ok(html.includes('切换到本次预览'));
assert.ok(!html.includes('href="/pv/'));
""")


    def test_commit_bound_open_path_is_preserved(self):
        self.run_js(r"""
const sha='a'.repeat(40),url='/pv/APP-1/__commit/'+sha+'/';
const bound={...ready,expected_commit:sha,url,preview:{state:'up',commit:sha}};
assert.ok(runPreviewHtml(run,bound,'').includes('href="'+url+'"'),'the UI must preserve the immutable server prefix');
assert.ok(!runPreviewHtml(run,{...bound,matches_run:false},'').includes('打开本次改动预览'));
""")

    def test_failed_and_unavailable_preview_keep_diagnostics_and_recovery(self):
        self.run_js(r"""
const html=runPreviewHtml(run,{...ready,preview:{state:'failed',commit:'abc123',why:'<script>bad</script>',tail:'line1\nline2'}},'');
assert.ok(html.includes('重试本次预览'));
assert.ok(html.includes('line1\nline2'));
assert.ok(html.includes('&lt;script&gt;bad&lt;/script&gt;'));
assert.ok(!html.includes('<script>'));
const failedRead=runPreviewHtml(run,null,'连接失败');
assert.ok(failedRead.includes('连接失败'));
assert.ok(failedRead.includes('data-run-preview-refresh'));
assert.ok(!failedRead.includes('data-run-preview-start'));
const unknown=runPreviewHtml(run,{...ready,run_id:null},'');
assert.ok(unknown.includes('无法确认'));
assert.ok(unknown.includes('data-run-preview-refresh'));
""")

    def test_unhealthy_preview_hides_open_but_preserves_refresh_and_recovery(self):
        self.run_js(r"""
for (const state of ['unhealthy', 'checking']) {
  const html=runPreviewHtml(run,{...ready,url:'',preview:{state,commit:'abc123',why:'HTTP 503 <db>'}},'');
  assert.ok(html.includes('预览暂不可用'));
  assert.ok(html.includes('HTTP 503 &lt;db&gt;'));
  assert.ok(html.includes('data-run-preview-refresh'));
  assert.ok(html.includes('重新启动本次预览'));
  assert.ok(!html.includes('打开本次改动预览'));
  assert.ok(!html.includes('预览尚未启动'));
}
assert.ok(runPreviewHtml(run,ready,'').includes('打开本次改动预览'));
""")

    def test_preview_request_target_is_bound_to_run_ticket_not_active_page(self):
        self.run_js(r"""
assert.equal(runPreviewPath(run),'/api/tickets/APP-1/preview');
assert.equal(runPreviewPath({...run,ticket_key:'OTHER-2'}),'/api/tickets/OTHER-2/preview');
assert.equal(runPreviewPath({...run,ticket_key:''}),'');
assert.equal(runPreviewPath({...run,mode:'plan'}),'');
assert.ok(!runPreviewHtml({...run,ticket_key:''},ready,'').includes('href="/pv/'));
""")


    def test_old_failed_decision_does_not_enable_new_views_busy_buttons(self):
        self.run_js(r"""
getHandler=async url=>url.includes('/recheck')?{running:url.includes('/8/')}:detail(url.includes('/8?')?8:7);
const delayed=later();postHandler=()=>delayed.promise;
await showRun(7);
const oldDecision=body.querySelector('[data-run-decision="accept"]');
const pending=oldDecision.onclick();
await showRun(8); // this other run is currently rechecking, so its decisions stay disabled
const currentDecision=body.querySelector('[data-run-decision="accept"]');
assert.equal(currentDecision.disabled,true);
delayed.reject(new Error('old request failed'));
await pending;
assert.equal(currentDecision.disabled,true,'a previous view must not re-enable these buttons');
assert.ok(body.innerHTML.includes('#8 '));
""", controller=True)

    def test_slow_preview_read_cannot_overwrite_a_later_start_response(self):
        self.run_js(r"""
const current=detail(7,'accepted:tmh/APP-7@abc123');
const idle={...ready,url:'',preview:{state:'stopped',commit:'abc123'}};
let reads=0;const delayed=later();
getHandler=async url=>url.includes('/preview?')?(++reads===1?idle:delayed.promise):url.includes('/recheck')?{running:false}:current;
postHandler=async (url,data)=>{assert.equal(url,'/api/tickets/APP-7/preview');assert.deepEqual(data,{action:'start',run_id:7});return ready};
await showRun(7);
const refreshing=body.querySelector('[data-run-preview-refresh]').onclick();
await body.querySelector('[data-run-preview-start]').onclick();
assert.ok(body.querySelector('[data-run-preview]').innerHTML.includes('打开本次改动预览'));
delayed.resolve({...ready,matches_run:false,url:'',preview:{state:'up',commit:'old'}});
await refreshing;
assert.ok(body.querySelector('[data-run-preview]').innerHTML.includes('打开本次改动预览'),'late GET must not replace the completed start result');
assert.ok(!body.querySelector('[data-run-preview]').innerHTML.includes('当前预览属于另一版'));
""", controller=True)

    def test_verification_distinguishes_missing_skipped_failed_and_real_commands(self):
        self.run_js(r"""
assert.ok(runVerificationHtml({}).includes('没有实际验证记录'));
const skipped=runVerificationHtml({verification:{check:'skip',skip:'项目没有验证命令',commands:[]}});
assert.ok(skipped.includes('未执行'));
assert.ok(skipped.includes('项目没有验证命令'));
assert.ok(skipped.includes('不能据此判断测试通过'));
const actual=runVerificationHtml({verification:{check:'fail',verdict:'fail',commands:[{kind:'build',command:'make <target>',exit_code:2,tail:'first\nlast'}]}});
assert.ok(actual.includes('命令检查：<b>失败</b>'));
assert.ok(actual.includes('build · 未通过 · 退出码 2'));
assert.ok(actual.includes('make &lt;target&gt;'));
assert.ok(actual.includes('first\nlast'));
assert.ok(actual.includes('查看完整验证记录'));
const buildOnly=runVerificationHtml({verification:{check:'pass',verdict:'pass',commands:[{kind:'build',command:'make build',exit_code:0}]}});
assert.ok(buildOnly.includes('build · 通过'));
assert.ok(!buildOnly.includes('测试通过'));
""")

    def test_invalidated_conclusion_shows_current_checks_before_preserved_history(self):
        self.run_js(r"""
const original='验证：构建测试通过，诊断认为已解决。\n保留全部原始结论与细节。';
for (const [check,label,exit] of [['pass','通过',0],['fail','失败',1],['skip','未执行',null]]) {
  const changed={...detail(7),result:original,verification:{check,verdict:'pass',diagnosis_invalidated:'代码已变化 <重新核对>',commands:exit===null?[]:[{kind:'build',command:'make build',exit_code:exit}]}};
  getHandler=async url=>url.includes('/recheck')?{running:false}:changed;
  await showRun(7);
  const conclusion=body.innerHTML.split('<div data-pane="res" ')[1].split('<div data-pane="diff" ')[0];
  assert.ok(conclusion.includes('当前结论已失效'));
  assert.ok(conclusion.includes('代码已变化 &lt;重新核对&gt;'));
  assert.ok(conclusion.includes('命令检查：<b>'+label+'</b>'));
  assert.ok(conclusion.includes('实现诊断：<b>未知（待重新诊断）</b>'));
  assert.ok(!conclusion.includes('实现诊断：<b>通过</b>'));
  assert.ok(conclusion.includes('<details class="run-check"><summary>原运行历史输出（仅供参考）</summary>'+h(original)+'</details>'),'the complete original output must remain in a labelled, initially collapsed historical section');
  assert.ok(conclusion.indexOf('当前结论已失效')<conclusion.indexOf(h(original)));
}
""", controller=True)

    def test_current_conclusion_without_invalidation_keeps_existing_presentation(self):
        self.run_js(r"""
const current={...detail(7),result:'当前运行结论\n完整第二行',verification:{check:'pass',verdict:'pass',commands:[]}};
getHandler=async url=>url.includes('/recheck')?{running:false}:current;
await showRun(7);
const conclusion=body.innerHTML.split('<div data-pane="res" ')[1].split('<div data-pane="diff" ')[0];
assert.ok(conclusion.includes(h(current.result)));
assert.ok(!conclusion.includes('当前结论已失效'));
assert.ok(!conclusion.includes('原运行历史输出'));
""", controller=True)


if __name__ == "__main__":
    unittest.main()
