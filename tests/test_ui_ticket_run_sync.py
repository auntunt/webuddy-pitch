"""The ticket summary follows real run transitions without replacing editable fields."""
import shutil
import subprocess
import unittest

from tmh.platform.ui import JS
from tmh.platform.ui_work import WORK_JS
from tests.test_ui_run_preview import ASYNC_HARNESS


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for shipped ticket handlers")
class TicketRunSyncUiTest(unittest.TestCase):
    def run_js(self, checks):
        helpers = "const FLOW=[" + JS.split("const FLOW=[", 1)[1].split("async function vTicket", 1)[0]
        runs = JS.split("// ---------- runs\n", 1)[1].split("async function showPrompt", 1)[0]
        top = "function plainState" + WORK_JS.split("function plainState", 1)[1].split("async function ticketTopWire", 1)[0]
        chips = "const STL=" + WORK_JS.split("const STL=", 1)[1].split("const MODE=", 1)[0]
        wiring = "const wireNext=()=>{" + JS.split("  const wireNext=()=>{", 1)[1].split("  wireNext();pkgWire", 1)[0]
        harness = ASYNC_HARNESS.replace(
            "const $=selector=>selector==='#mbody'?body:selector==='#modal'?modalBox:null;",
            "const $=selector=>lookup(selector);")
        script = r"""
const assert=require('node:assert/strict');
const h=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
""" + harness + r"""
const document={activeElement:null,querySelectorAll:()=>[]};
const nodes={};
for(const id of ['tTop','tSteps','tNextText','tNextActions','tRunCount','tRunHistory','tStatus','fs','cm','accNote','be','ag','md','aiCard']){
 const n=nodes[id]=new TestElement();n.id=id;n.value='';n.contains=x=>x===n;n.focus=()=>document.activeElement=n;
}
body.scrollIntoView=()=>{};
const actionNodes={};
function lookup(selector){
 if(selector==='#runv'||selector==='#mbody')return body;
 if(selector==='#modal')return modalBox;
 if(!selector.startsWith('#'))return null;
 const id=selector.slice(1);if(nodes[id])return nodes[id];
 if(nodes.tNextActions.innerHTML.includes('id="'+id+'"'))return actionNodes[id]??=new TestElement();
 return null;
}
const stPill=h;
let topWires=0;const ticketTopWire=()=>{topWires++};
S.meta={autoflow:{on:false},agents:[]};
const initialRun={...detail(7),status:'running',ticket_key:'APP-7',lifecycle:{finished:false}};
const stoppedRun={...initialRun,status:'failed',can_retry:true,retry_blocked:[],lifecycle:{finished:true,stopped_reason:'timeout',attempts:[{attempt:1,pid:12345,cleanup:{complete:true}}]}};
const secondRun={...detail(8),ticket_key:'APP-7',status:'running',lifecycle:{finished:false}};
const doneRun={...secondRun,status:'done',lifecycle:{finished:true}};
function ticket(runs,state='doing',why='AI 正在修改代码'){
 return {ticket:{key:'APP-7',status:'doing',links:{},body:'保留事项编辑内容',title:'修改事项',created:'2026-10-18 21:00:00'},
  project:{key:'APP'},runs,events:[],evidence:{refs:0},plain_state:{state,why},package:{status:'none'}};
}
const key='APP-7';let d=ticket([initialRun]),latest=d,current=initialRun,summaryReads=0,applied=0;
let f,na;
const save=()=>{},run=()=>{},pvLoad=()=>{},hwLoad=()=>{};
getHandler=async url=>{
 if(url==='/api/tickets/APP-7'){summaryReads++;return latest}
 if(url.includes('/recheck'))return{running:false};
 if(url.startsWith('/api/runs/'))return current;
 throw new Error('unexpected request '+url);
};
""" + chips + top + helpers + runs + wiring + r"""
f=flowState(d);na=nextAction(d,f);S.cur=d;
nodes.fs.value=d.ticket.status;nodes.tTop.innerHTML=ticketTop(d,f,na);nodes.tSteps.innerHTML=stepper(f);
nodes.tNextText.innerHTML=na.text;nodes.tNextActions.innerHTML=na.btns;nodes.tRunCount.textContent=ticketRunCount(d.runs);
S.ticketRefresh=ticketSummarySync(d,n=>{applied++;d=n;f=flowState(n);na=nextAction(n,f);wireNext()});
wireNext();
""" + "\n(async()=>{\n" + checks + "\n})().catch(e=>{console.error(e);process.exitCode=1});"
        result = subprocess.run([shutil.which("node"), "-"], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failure_retry_and_completion_refresh_summary_and_preserve_typed_drafts(self):
        self.run_js(r"""
const drafts=['cm','accNote','be','ag','md'].map(id=>{const n=nodes[id];n.value='未保存：'+id;n.selectionStart=3;return[id,n,n.value]});
nodes.cm.focus();await showRun(7,true);
assert.ok(nodes.tTop.innerHTML.includes('智能体正在'));assert.equal(nodes.tRunCount.textContent,'1 次运行');
current=stoppedRun;latest=ticket([stoppedRun],'you','上次运行未完成');await S.polls[0].fn();
assert.ok(nodes.tTop.innerHTML.includes('上次运行未完成'));assert.ok(!nodes.tNextText.innerHTML.includes('智能体正在'));
assert.ok(nodes.tSteps.innerHTML.includes('失败'));assert.ok(nodes.tNextActions.innerHTML.includes('查看停止原因与恢复入口'));
postHandler=async url=>{assert.equal(url,'/api/runs/7/retry');current=secondRun;latest=ticket([secondRun,stoppedRun]);return{id:8}};
await body.querySelector('[data-run-resume]').onclick();
assert.equal(nodes.tRunCount.textContent,'2 次运行');assert.ok(nodes.tRunHistory.innerHTML.includes('#8 '));assert.ok(nodes.tRunHistory.innerHTML.includes('#7 '));
assert.ok(nodes.tNextText.innerHTML.includes('智能体正在'));
current=doneRun;latest=ticket([doneRun,stoppedRun],'you','代码改动等待审阅');await S.polls[0].fn();
assert.ok(nodes.tTop.innerHTML.includes('代码改动等待审阅'));assert.ok(nodes.tNextText.innerHTML.includes('等你审阅'));
assert.ok(!nodes.tNextText.innerHTML.includes('智能体正在'));assert.ok(nodes.tNextActions.innerHTML.includes('naReview'));
for(const [id,n,value] of drafts){assert.equal(nodes[id],n);assert.equal(n.value,value);assert.equal(n.selectionStart,3)}
assert.equal(document.activeElement,nodes.cm);
$('#naReview').onclick();await new Promise(setImmediate);assert.ok(body.innerHTML.includes('#8 '));
assert.equal(nodes.aiCard.open,true);assert.equal(applied,3);
""")

    def test_slow_older_refresh_cannot_replace_newer_summary(self):
        self.run_js(r"""
const old=later(),fresh=later();let call=0;
getHandler=()=>++call===1?old.promise:fresh.promise;
const first=S.ticketRefresh(),second=S.ticketRefresh();
fresh.resolve(ticket([doneRun,stoppedRun],'you','新运行等待审阅'));await second;
old.resolve(ticket([stoppedRun],'you','旧运行失败'));assert.equal(await first,null);
assert.equal(nodes.tRunCount.textContent,'2 次运行');assert.ok(nodes.tTop.innerHTML.includes('新运行等待审阅'));
assert.equal(applied,1);
""")

    def test_refresh_for_departed_ticket_does_not_touch_new_page(self):
        self.run_js(r"""
const pending=later();getHandler=()=>pending.promise;const request=S.ticketRefresh();
const old=nodes.tTop;nodes.tTop=new TestElement();nodes.tTop.innerHTML='另一个页面';old.isConnected=false;
S.cur={ticket:{key:'OTHER-1'}};pending.resolve(ticket([stoppedRun],'you','上次失败'));
assert.equal(await request,null);assert.equal(nodes.tTop.innerHTML,'另一个页面');assert.equal(applied,0);
""")

    def test_unchanged_summary_does_not_repaint_or_clear_focus(self):
        self.run_js(r"""
nodes.cm.value='还在输入';nodes.cm.focus();const html=nodes.tTop.innerHTML;
await S.ticketRefresh();await S.ticketRefresh();
assert.equal(topWires,0);assert.equal(applied,0);assert.equal(nodes.tTop.innerHTML,html);
assert.equal(document.activeElement,nodes.cm);assert.equal(nodes.cm.value,'还在输入');
""")

    def test_unrelated_run_modal_does_not_refresh_the_ticket(self):
        self.run_js(r"""
current={...stoppedRun,ticket_key:'OTHER-1'};
await showRun(7);assert.equal(summaryReads,0);assert.equal(applied,0);
""")

    def test_summary_refresh_does_not_overwrite_an_unsaved_status_choice(self):
        self.run_js(r"""
nodes.fs.value='confirm';nodes.fs.focus();latest=ticket([doneRun],'you','已等待验收');latest.ticket.status='verify';
await S.ticketRefresh();assert.equal(nodes.fs.value,'confirm');assert.equal(nodes.tStatus.innerHTML,'verify');
assert.equal(document.activeElement,nodes.fs);
""")

    def test_new_unadopted_fix_takes_precedence_over_old_verify_state(self):
        self.run_js(r"""
const old={...detail(3,'accepted:tmh/APP-7-r3@oldsha'),ticket_key:'APP-7'};
const fresh={...detail(6),ticket_key:'APP-7'};
// api_ticket omits full diffs, as in the recorded BOOTV2-1 failure response.
const freshSummary={...fresh};delete freshSummary.diff;
const plan={id:5,mode:'plan',status:'done',decision:'',agent:'local',result:'当前方案'};
const oldEvent={id:20,kind:'adopt',author:'自动流转',data:{run:3,branch:'tmh/APP-7-r3',commit:'oldsha'}};
latest=ticket([old],'you','等你验收');latest.ticket.status='verify';latest.events=[oldEvent];current=old;
await S.ticketRefresh();assert.ok(nodes.tTop.innerHTML.includes('id="ttOk"'));
latest=ticket([freshSummary,plan,old],'you','改好了，等你审阅');latest.ticket.status='verify';latest.events=[oldEvent];current=fresh;
await S.ticketRefresh();
assert.equal(f.fx.id,6);assert.equal(f.st.fix,'cur');assert.equal(f.st.verify,'todo');
assert.equal(adopted(latest),null);assert.ok(!na.acc);
assert.ok(nodes.tNextText.innerHTML.includes('#6'));assert.ok(nodes.tNextText.innerHTML.includes('等你审阅'));
assert.ok(!nodes.tNextText.innerHTML.includes('tmh/APP-7-r3'));assert.ok(!nodes.tNextText.innerHTML.includes('oldsha'));
assert.ok(!nodes.tTop.innerHTML.includes('id="ttOk"'));assert.ok(!nodes.tTop.innerHTML.includes('id="ttNo"'));
assert.ok(nodes.tNextActions.innerHTML.includes('naReview'));assert.ok(!nodes.tNextActions.innerHTML.includes('naVerify'));
const requested=[];getHandler=async url=>{requested.push(url);return url.includes('/recheck')?{running:false}:fresh};
$('#naReview').onclick();await new Promise(setImmediate);
assert.ok(requested.some(url=>url.startsWith('/api/runs/6')));assert.ok(!requested.some(url=>url.startsWith('/api/runs/3')));
assert.ok(body.innerHTML.includes('#6 '));assert.ok(body.querySelector('[data-run-decision="accept"]'));
""")

    def test_current_adopted_fix_never_uses_another_runs_branch_or_auto_claim(self):
        self.run_js(r"""
const currentFix={...detail(6,'accepted:tmh/APP-7-r6@newsha'),ticket_key:'APP-7'};
const old={...detail(3,'accepted:tmh/APP-7-r3@oldsha'),ticket_key:'APP-7'};
const value=ticket([currentFix,old],'you','等你验收');value.ticket.status='verify';
value.events=[{id:20,kind:'adopt',author:'自动流转',data:{run:3,branch:'tmh/APP-7-r3',commit:'oldsha'}}];
let state=flowState(value),action=nextAction(value,state);
assert.ok(action.acc);assert.ok(action.text.includes('tmh/APP-7-r6'));assert.ok(action.text.includes('newsha'));
assert.ok(!action.text.includes('tmh/APP-7-r3'));assert.ok(!action.text.includes('已自动'));
assert.equal(state.sub.fix,'已采纳');
value.events.push({id:21,kind:'adopt',author:'自动流转',data:{run:6,branch:'tmh/APP-7-r6',commit:'newsha'}});
state=flowState(value);action=nextAction(value,state);
assert.equal(state.sub.fix,'已自动提交');assert.ok(action.text.includes('已自动'));
assert.ok(action.text.includes('newsha'));
""")


if __name__ == '__main__':
    unittest.main()
