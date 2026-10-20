"""Behavior regressions for the agent-run list and historical output disclosure."""
import shutil
import subprocess
import unittest

from tmh.platform.ui import JS


HARNESS = r"""
const assert=require('node:assert/strict');
const h=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const S={proj:'REALRUN',runItems:[]};
const elements={main:{innerHTML:''},rf:{onchange:null}};
const $=selector=>elements[selector.replace(/^#/,'')];
const stored=new Map();
const sessionStorage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)};
let records=[],requests=[],opened=[],scheduled=[];
const get=async url=>{requests.push(url);return records};
const moLabel=mode=>({ask:'研究与生成产物',fix:'修改代码',kb:'知识库撰写'}[mode]||mode);
const mTag=()=>'',ago=()=> '刚刚';
const pageHead=(title,sub,right)=>`<header><h1>${h(title)}</h1><p>${h(sub)}</p>${right||''}</header>`;
const location={hash:'#/runs'};
const poll=(fn,ms)=>{scheduled.push({fn,ms})};
const showRun=id=>opened.push(id);
const base={id:1,mode:'ask',status:'done',target:'研究阶段',agent:'codex',author:'测试用户',created:'2026-10-18 10:00:00',result:'原始研究结论',session_id:null,batch:'',ticket:'',exit_code:0};
const row=(id,extra={})=>({...base,id,...extra});
const render=async rs=>{records=rs;await vRuns();return elements.main.innerHTML};
const filtered=async value=>{elements.rf.onchange({target:{value}});await new Promise(setImmediate);return elements.main.innerHTML};
const visibleIds=()=>[...elements.main.innerHTML.matchAll(/onclick="showRun\((\d+)\)"/g)].map(m=>Number(m[1]));
"""


@unittest.skipUnless(shutil.which("node"), "Node.js is needed to check shipped list behavior")
class RunsListBehaviorTest(unittest.TestCase):
    def run_js(self, checks):
        listing = JS.split("async function vRuns(){", 1)[1].split("async function retryKb", 1)[0]
        listing = "async function vRuns(){" + listing
        markdown = "function md(src){" + JS.split("function md(src){", 1)[1].split("function diffHtml", 1)[0]
        # Keep batch rendering real too; it is called by vRuns for evaluation batches.
        batches = "function evBatch(" + JS.split("function evBatch(", 1)[1].split("// ---------- 重构升级", 1)[0]
        script = HARNESS + markdown + listing + batches + "\n(async()=>{\n" + checks + "\n})().catch(e=>{console.error(e);process.exitCode=1});"
        result = subprocess.run([shutil.which("node"), "-"], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_delivery_ask_without_session_is_visible_and_opens_actual_run(self):
        self.run_js(r"""
const phase=row(41,{target:'delivery/first/research',session_id:null});
const html=await render([phase]);
assert.deepEqual(requests,['/api/runs?project=REALRUN']);
assert.deepEqual(S.runItems,[phase]);
assert.deepEqual(visibleIds(),[41]);
assert.ok(html.includes('delivery/first/research'));
assert.ok(!html.includes('还没有运行过智能体'));
assert.ok(!html.includes('打开所属会话'));
const handler=html.match(/<button onclick="(showRun\(41\))">查看运行<\/button>/)[1];
new Function('showRun',handler)(showRun);
assert.deepEqual(opened,[41]);
""")

    def test_long_output_and_target_remain_complete_but_are_labelled_history(self):
        self.run_js(r"""
const target='交付研究目标'.repeat(120)+'—目标末尾';
const output='开头结论：原模型判断通过。\n\n'+('证据段落与限定条件。'.repeat(800))+'\n\n最后结论：仍需当前版本验证。';
const html=await render([row(42,{target,result:output})]);
assert.ok(html.includes(h(target)),'the full target must remain readable');
assert.ok(html.includes(md(output)),'all paragraphs of the original output must remain available');
assert.ok(html.includes('最后结论：仍需当前版本验证。'));
const disclosure=html.match(/<details class="run-check">([\s\S]*?)<\/details>/);
assert.ok(disclosure,'history must be available in a disclosure');
assert.ok(disclosure[1].includes('原运行输出 · 历史记录'));
assert.ok(disclosure[1].includes('历史输出中的判断不代表当前验证结果'));
assert.ok(disclosure[1].includes(md(output)));
assert.ok(!html.includes('<div class="out">产出：'));
assert.deepEqual(visibleIds(),[42]);
""")

    def test_real_markdown_escapes_html_in_output_and_metadata(self):
        self.run_js(r"""
const payload='<img src=x onerror="alert(1)"><script>alert(2)</script>';
const output='## 原运行输出\n\n'+payload+'\n\n[x](javascript:alert(3))\n\n```html\n'+payload+'\n```';
const html=await render([row(43,{target:payload,agent:payload,author:payload,result:output,ticket:'REALRUN-1',ticket_title:payload})]);
assert.ok(!html.includes('<img'));
assert.ok(!html.includes('<script>'));
assert.ok(!html.includes('href="javascript:'));
assert.ok(html.includes(h(payload)));
assert.ok(html.includes('<pre><code>'+h(payload)+'</code></pre>'));
assert.ok(html.includes('<h2>原运行输出</h2>'),'the shipped Markdown renderer is exercised');
assert.deepEqual(visibleIds(),[43]);
""")

    def test_status_filters_include_sessionless_asks_and_preserve_recovery(self):
        self.run_js(r"""
await render([
 row(51,{status:'running',result:'尚未形成结果'}),
 row(52,{status:'queued',result:''}),
 row(53,{status:'failed',exit_code:2,result:'故障原因原文'}),
 row(54,{status:'done'}),
 row(55,{status:'done',session_id:7,session_title:'沟通会话'})
]);
assert.deepEqual(visibleIds(),[51,52,53,54,55]);
assert.ok(elements.main.innerHTML.includes('A.switchTo(7)'));
assert.equal(scheduled.length,1);
assert.equal(scheduled[0].ms,5000);
let html=await filtered('live');
assert.equal(stored.get('tmh.rf'),'live');
assert.deepEqual(visibleIds(),[51,52]);
assert.ok(!html.includes('尚未形成结果'),'running output is read in the live details');
html=await filtered('bad');
assert.deepEqual(visibleIds(),[53]);
assert.ok(html.includes('故障原因原文'));
await filtered('all');
assert.deepEqual(visibleIds(),[51,52,53,54,55]);
assert.equal(S.runItems.length,5,'filtering must not discard the retained records');
await render([row(54)]);
html=await filtered('bad');
assert.ok(html.includes('没有符合条件的任务'));
assert.ok(!html.includes('还没有运行过智能体'));
await filtered('all');
assert.deepEqual(visibleIds(),[54]);
""")

    def test_batches_keep_their_children_and_filters_do_not_duplicate_runs(self):
        self.run_js(r"""
await render([
 row(61,{mode:'kb',batch:'kb-first',status:'done',target:'domains/one'}),
 row(62,{mode:'kb',batch:'kb-first',status:'failed',target:'domains/two'}),
 row(63,{mode:'ask',batch:'',status:'done',session_id:null}),
 row(64,{mode:'ask',batch:'eval-suite',status:'done',target:'验收用例'}),
 row(65,{mode:'ask',batch:'eval-suite',status:'running',target:'运行用例'})
]);
assert.equal(S.runItems.length,3);
assert.deepEqual(S.runItems.find(x=>x.batch==='kb-first').runs.map(x=>x.id),[61,62]);
assert.deepEqual(S.runItems.find(x=>x.batch==='eval-suite').runs.map(x=>x.id),[64,65]);
assert.deepEqual(visibleIds(),[61,62,63,64,65]);
assert.ok(elements.main.innerHTML.includes('业务说明仍需人工确认'));
await filtered('bad');
assert.deepEqual(visibleIds(),[61,62],'a failed batch remains one inspectable group');
await filtered('live');
assert.deepEqual(visibleIds(),[64,65]);
await filtered('all');
assert.deepEqual(visibleIds(),[61,62,63,64,65]);
""")


if __name__ == "__main__":
    unittest.main()
