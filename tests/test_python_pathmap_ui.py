"""The shipped candidate-path panel records only version-bound technical links."""
import shutil
import subprocess
import unittest

from tmh.platform.ui import JS
from tmh.platform.ui_access import ACCESS_BOOT_JS


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for shipped path-map handlers")
class PythonPathMapUiTest(unittest.TestCase):
    def run_js(self, checks):
        source = JS.split("// ---------- candidate code paths:", 1)[1]
        source = source.split("\n", 1)[1].split("// ---------- ticket page", 1)[0]
        harness = r'''
const assert=require('node:assert/strict');
const h=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
class Panel{
 constructor(){this.isConnected=true;this.controls=[];this.html=''}
 set innerHTML(value){this.html=value;this.controls=[];
  for(const match of value.matchAll(/<(button|input)\b([^>]*)>/g)){
   const attributes=match[2],control={disabled:/\bdisabled\b/.test(attributes),checked:/\bchecked\b/.test(attributes),dataset:{}};
   for(const attr of attributes.matchAll(/\b(data-[\w-]+)(?:="([^"]*)")?/g)){
    control[attr[1]]=attr[2]??'';
    control.dataset[attr[1].slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=attr[2]??'';
   }
   this.controls.push(control);
  }
 }
 get innerHTML(){return this.html}
 querySelectorAll(selector){return this.controls.filter(c=>Object.hasOwn(c,selector.slice(1,-1)))}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null}
}
const fold={open:false},panel=new Panel(),draft={value:'客户补充：不要丢失这一段\n<原话>',selectionStart:9};
let currentPanel=panel,refreshes=0,gets=[],posts=[];
const $=selector=>selector==='#pathMapDetails'?fold:selector==='#pathMapPanel'?currentPanel:selector==='#cm'?draft:null;
const S={cur:{ticket:{key:'APP-7'}},ticketRefresh:async()=>{refreshes++}};
const mapping={source:{commit:'8be50de6b4b4200dc6d792c2a7f0b871f9288da4',diff_sha256:'b'.repeat(64)},digest:'c'.repeat(64),
 status:'partial',can_record:true,why:'仅建立方法级关联',scope:'候选提交内 HTTP dispatcher 整方法关联',
 limitations:['不解析每个 URL 的条件分支'],diagnostics:[],
 changes:[{file:'app.py',lines:[85,92,125],functions:['app.Handler.get','app.Handler.post'],flow_ids:['flow:get','flow:post'],status:'mapped',why:'函数可达'}],
 flows:[{id:'flow:get',trigger:'GET dispatcher',handler:'app.Handler.do_GET',nodes:[{key:'app.Handler.get',file:'app.py',line:92,end_line:117}],unresolved:[]},
 {id:'flow:post',trigger:'POST dispatcher',handler:'app.Handler.do_POST',nodes:[{key:'app.Handler.post',file:'app.py',line:125,end_line:200}],unresolved:[{call:'dynamic_lookup',why:'动态调用未知'}]}],
 suggested:['flow:get','flow:post'],selected:[]};
let getHandler=async()=>structuredClone(mapping),postHandler=async(url,payload)=>({...structuredClone(mapping),selected:payload.flows});
const get=async url=>{gets.push(url);return getHandler(url)};
const post=async(url,payload)=>{posts.push({url,payload});return postHandler(url,payload)};
const later=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
const open=async()=>{fold.open=true;await fold.ontoggle()};
const tick=()=>new Promise(setImmediate);
''' + source + "\n(async()=>{\n" + checks + "\n})().catch(e=>{console.error(e);process.exitCode=1});"
        result = subprocess.run([shutil.which("node"), "-"], input=harness, encoding="utf-8", errors="replace", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_loading_is_on_demand_cached_and_manually_refreshable(self):
        self.run_js(r'''
ticketPathMapWire('APP-7');assert.deepEqual(gets,[]);await fold.ontoggle();assert.deepEqual(gets,[]);
await open();assert.deepEqual(gets,['/api/tickets/APP-7/path-map']);assert.ok(panel.innerHTML.includes(mapping.source.commit));
fold.open=false;await fold.ontoggle();await open();assert.equal(gets.length,1,'reopening is not a polling loop');
await panel.querySelector('[data-path-reload]').onclick();assert.equal(gets.length,2);
assert.ok(panel.innerHTML.includes('不代表业务验收通过'));
assert.ok(panel.innerHTML.includes('不确认业务范围'));
''')

    def test_full_mapping_evidence_is_escaped_without_truncation(self):
        self.run_js(r'''
const raw='<img src=x onerror="danger()">\n'+('完整诊断'.repeat(900))+'末尾必须保留';
const unsafe={...structuredClone(mapping),status:'<unsafe-status>',why:raw,scope:raw,limitations:[raw],
 diagnostics:[{file:'<file>.py',line:73,message:raw}],changes:[{file:'<changed>.py',lines:[1,99999],functions:[raw],flow_ids:[raw],status:'<unknown>',why:raw}],
 flows:[{id:raw,trigger:raw,handler:raw,nodes:[{key:raw,file:'<node>.py',line:7,end_line:500}],unresolved:[{call:raw}]}],suggested:[raw]};
getHandler=async()=>unsafe;ticketPathMapWire('APP-7');await open();
assert.ok(!panel.innerHTML.includes('<img'));assert.ok(!panel.innerHTML.includes('<unsafe-status>'));assert.ok(panel.innerHTML.includes('&lt;unsafe-status&gt;'));
assert.ok(panel.innerHTML.includes(h(raw)));assert.ok(panel.innerHTML.includes(h(JSON.stringify({call:raw},null,2))));
assert.ok(panel.innerHTML.includes('99999'));assert.ok(panel.innerHTML.includes('7–500'));
assert.ok(panel.innerHTML.includes(mapping.source.commit));assert.ok(panel.innerHTML.includes(mapping.source.diff_sha256));assert.ok(panel.innerHTML.includes(mapping.digest));
''')

    def test_records_current_selection_with_version_and_only_refreshes_summary(self):
        self.run_js(r'''
const before=draft.value;ticketPathMapWire('APP-7');await open();
const boxes=panel.querySelectorAll('[data-path-flow]');assert.equal(boxes.length,2);assert.ok(boxes.every(x=>x.checked));
boxes[0].checked=false;boxes[0].onchange();await panel.querySelector('[data-path-record]').onclick();
assert.deepEqual(posts,[{url:'/api/tickets/APP-7/path-map',payload:{commit:mapping.source.commit,digest:mapping.digest,flows:['flow:post']}}]);
assert.equal(refreshes,1);assert.equal(gets.length,1);assert.equal(draft.value,before);assert.equal(draft.selectionStart,9);
assert.ok(panel.innerHTML.includes('代码关联已记录'));assert.ok(panel.innerHTML.includes('仍需独立验证和业务验收'));
assert.ok(!Object.hasOwn(posts[0].payload,'flows_ok'));assert.equal(panel.querySelectorAll('[data-path-flow]')[0].checked,false);
''')

    def test_server_policy_and_nonempty_selection_control_recording(self):
        self.run_js(r'''
getHandler=async()=>({...mapping,status:'mapped',can_record:false,why:'旧候选不能关联'});ticketPathMapWire('APP-7');await open();
assert.equal(panel.querySelector('[data-path-record]').disabled,true);await panel.querySelector('[data-path-record]').onclick();assert.equal(posts.length,0);
getHandler=async()=>({...mapping,selected:['flow:get','flow:no-longer-available']});await panel.querySelector('[data-path-reload]').onclick();
let boxes=panel.querySelectorAll('[data-path-flow]');assert.equal(boxes[0].checked,true);assert.equal(boxes[1].checked,false,'existing selection wins over suggestions');
boxes[0].checked=false;boxes[0].onchange();assert.equal(panel.querySelector('[data-path-record]').disabled,true);
await panel.querySelector('[data-path-record]').onclick();assert.equal(posts.length,0);
boxes[1].checked=true;boxes[1].onchange();assert.equal(panel.querySelector('[data-path-record]').disabled,false);
''')

    def test_unavailable_mapping_does_not_claim_no_business_impact(self):
        self.run_js(r'''
getHandler=async()=>({source:{},status:'unsupported',why:'Python 语法无法解析',can_record:false,diagnostics:[],changes:[],flows:[],limitations:['解析范围未知']});
ticketPathMapWire('APP-7');await open();assert.ok(panel.innerHTML.includes('当前解析不支持'));assert.ok(panel.innerHTML.includes('Python 语法无法解析'));
assert.ok(panel.innerHTML.includes('这不表示业务没有影响'));assert.ok(panel.innerHTML.includes('解析范围未知'));
assert.equal(panel.querySelector('[data-path-record]').disabled,true);await panel.querySelector('[data-path-record]').onclick();assert.equal(posts.length,0);
''')

    def test_full_request_error_is_readable_and_retry_loads_again(self):
        self.run_js(r'''
const error='<网络错误>\n'+('完整失败原因'.repeat(800))+'尾部';getHandler=async()=>{throw new Error(error)};
ticketPathMapWire('APP-7');await open();assert.ok(panel.innerHTML.includes(h(error)));assert.ok(!panel.innerHTML.includes('<网络错误>'));
getHandler=async()=>mapping;await panel.querySelector('[data-path-reload]').onclick();assert.equal(gets.length,2);assert.ok(panel.innerHTML.includes(mapping.source.commit));
postHandler=async()=>{throw new Error(error)};await panel.querySelector('[data-path-record]').onclick();
assert.ok(panel.innerHTML.includes(h(error)));assert.equal(panel.querySelector('[data-path-record]').disabled,true);assert.equal(refreshes,0);
assert.equal(panel.querySelectorAll('[data-path-flow]').filter(x=>x.checked).length,2);
await panel.querySelector('[data-path-reload]').onclick();assert.equal(gets.length,3);assert.equal(panel.querySelector('[data-path-record]').disabled,false);
''')

    def test_duplicate_actions_and_late_results_cannot_mutate_another_ticket(self):
        self.run_js(r'''
const pending=later();getHandler=()=>pending.promise;ticketPathMapWire('APP-7');const first=open();await fold.ontoggle();assert.equal(gets.length,1);
pending.resolve(mapping);await first;const posting=later();postHandler=()=>posting.promise;
const button=panel.querySelector('[data-path-record]');const saving=button.onclick();await button.onclick();assert.equal(posts.length,1);
S.cur={ticket:{key:'OTHER-8'}};currentPanel=new Panel();currentPanel.innerHTML='另一张工单';panel.isConnected=false;
posting.resolve({...mapping,selected:['flow:get']});await saving;
assert.equal(currentPanel.innerHTML,'另一张工单');assert.equal(refreshes,0);
''')

    def test_a_departed_page_does_not_receive_late_load_or_summary_error(self):
        self.run_js(r'''
const pending=later();getHandler=()=>pending.promise;ticketPathMapWire('APP-7');const loading=open();
currentPanel=new Panel();currentPanel.innerHTML='同编号新页面';panel.isConnected=false;pending.resolve(mapping);await loading;
assert.equal(currentPanel.innerHTML,'同编号新页面');assert.equal(refreshes,0);
''')

    def test_successful_record_is_not_reclassified_when_summary_refresh_fails(self):
        self.run_js(r'''
S.ticketRefresh=async()=>{refreshes++;throw new Error('完整摘要错误 <保留>')};ticketPathMapWire('APP-7');await open();
await panel.querySelector('[data-path-record]').onclick();assert.equal(posts.length,1);assert.equal(refreshes,1);
assert.ok(panel.innerHTML.includes('代码关联已记录；工单摘要刷新未完成'));assert.ok(panel.innerHTML.includes('完整摘要错误 &lt;保留&gt;'));
assert.equal(draft.value,'客户补充：不要丢失这一段\n<原话>');
''')

    def test_deleted_lines_keep_complete_old_function_location_evidence(self):
        self.run_js(r'''
const removed=Array.from({length:350},(_,i)=>10000+i);
const functionName='old.Handler.<img src=x onerror="danger()">'+('完整旧函数'.repeat(500))+'末尾';
const locations=removed.map(line=>({line,side:'old',function:functionName,flow_ids:['flow:old-delete','flow:<旧入口>']}));
const changed={file:'app.py',lines:[],removed_lines:removed,functions:[functionName],flow_ids:['flow:old-delete'],status:'unknown',why:'删除了旧函数体',locations};
getHandler=async()=>({...mapping,changes:[changed],can_record:false});ticketPathMapWire('APP-7');await open();
assert.ok(panel.innerHTML.includes('新增或修改行（候选版本）：无'));
assert.ok(panel.innerHTML.includes('删除行（旧版本）：'+removed.join('、')));
assert.ok(panel.innerHTML.includes('<details'));assert.ok(panel.innerHTML.includes('查看新旧行定位证据'));
assert.ok(panel.innerHTML.includes(h(JSON.stringify(locations,null,2))),'all old-side locations, functions, and flow IDs remain inspectable');
assert.ok(!panel.innerHTML.includes('<img'));assert.equal(panel.querySelector('[data-path-record]').disabled,true);
''')


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for package synchronization")
class PythonPathMapPackageUiTest(unittest.TestCase):
    def run_js(self, checks):
        summary = "function ticketSummarySync" + JS.split("function ticketSummarySync", 1)[1].split("function watchIntakeRecovery", 1)[0]
        package = "const PKC=" + JS.split("const PKC=", 1)[1].split("function upCard", 1)[0]
        paths = JS.split("// ---------- candidate code paths:", 1)[1].split("\n", 1)[1].split("// ---------- ticket page", 1)[0]
        harness = r'''
const assert=require('node:assert/strict');
const h=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clip=(v,n)=>v.slice(0,n),document={activeElement:null,querySelectorAll:()=>[]};
class Element{
 constructor(){this.isConnected=true;this.controls=[];this.html='';this.value='';this.childElementCount=0;this.hidden=true}
 set innerHTML(value){this.html=value;this.controls=[];
  for(const m of value.matchAll(/<(button|input)\b([^>]*)>/g)){
   const a=m[2],c={disabled:/\bdisabled\b/.test(a),checked:/\bchecked\b/.test(a),dataset:{}};
   for(const x of a.matchAll(/\b(data-[\w-]+|id)(?:="([^"]*)")?/g)){c[x[1]]=x[2]??'';c.dataset[x[1].slice(5).replace(/-([a-z])/g,(_,v)=>v.toUpperCase())]=x[2]??''}
   this.controls.push(c);
  }
 }
 get innerHTML(){return this.html}
 querySelectorAll(selector){return this.controls.filter(c=>Object.hasOwn(c,selector.slice(1,-1)))}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null}
 contains(other){return this===other}
 focus(){document.activeElement=this}
}
const nodes={};for(const id of ['tTop','tSteps','tNextText','tNextActions','tRunCount','tRunHistory','tStatus','fs','cm','bodyv','pkSummary','pkActions','pkForm','pkDraftNotice','pkImg','pkAc','pkNote','pkRn','pkWaive','pkGo','pathMapDetails','pathMapPanel'])nodes[id]=new Element();
const $=selector=>nodes[selector.slice(1)]||nodes.pkActions.controls.find(c=>c.id===selector.slice(1))||null;
const fixedSubmit=()=>{};nodes.pkGo.onclick=fixedSubmit;
nodes.cm.value='未发送评论';nodes.cm.selectionStart=4;nodes.cm.focus();
nodes.pkForm.childElementCount=5;nodes.pkNote.value='截图说明草稿';nodes.pkAc.value='A2';nodes.pkRn.value='复核草稿';nodes.pkWaive.value='尚未提交的例外理由';
const selectedFile={name:'原始完整截图.png',size:999999,type:'image/png'};nodes.pkImg.files=[selectedFile];nodes.pkWaive.checked=true;
const stableDrafts=['cm','pkForm','pkImg','pkAc','pkNote','pkRn','pkWaive','pkGo'].map(id=>[id,nodes[id]]);
function state(records,path){return{ticket:{key:'APP-7',status:'verify',body:'合同原文',links:{}},runs:[],events:[],evidence:{},plain_state:{why:'仍待业务验证'},
 package:{status:'incomplete',label:'证据不齐',intact:true,records,hash:String(records).repeat(64),missing:['独立复核'],gates:[{id:'path',name:'代码入口关联',state:path,why:path==='pass'?'两个分派方法已关联':'只关联GET，POST改动未覆盖'}]}}}
const initial=state(4,'unknown');let latest=initial,refreshes=0,posts=[],reads=[];
const S={cur:initial};const flowState=()=>({}),nextAction=d=>({text:d.plain_state.why,tone:'info',btns:''}),ticketTop=d=>h(d.plain_state.why),stepper=()=>'',ticketRunCount=()=>'',ticketRunHistory=()=>'',stPill=h,ticketTopWire=()=>{},md=h;
const mapping={source:{commit:'a'.repeat(40),diff_sha256:'b'.repeat(64)},digest:'c'.repeat(64),status:'mapped',can_record:true,changes:[],diagnostics:[],limitations:[],
 flows:[{id:'flow:get',trigger:'GET',nodes:[],unresolved:[]},{id:'flow:post',trigger:'POST',nodes:[],unresolved:[]}],suggested:['flow:get','flow:post'],selected:[]};
const get=async url=>{reads.push(url);return url.endsWith('/path-map')?structuredClone(mapping):latest};
const post=async(url,payload)=>{posts.push({url,payload});latest=state(posts.length+4,payload.flows.includes('flow:post')?'pass':'unknown');return{...structuredClone(mapping),selected:payload.flows}};
''' + "const location={pathname:'/'};\n" + ACCESS_BOOT_JS + summary + package + paths + r'''
nodes.pkSummary.innerHTML=pkgCard(initial);nodes.tTop.innerHTML=ticketTop(initial);nodes.fs.value=initial.ticket.status;
S.ticketRefresh=ticketSummarySync(initial,()=>{refreshes++});ticketPathMapWire('APP-7');
function preserved(){for(const [id,node] of stableDrafts)assert.equal(nodes[id],node,id+' DOM identity');
 assert.equal(nodes.cm.value,'未发送评论');assert.equal(nodes.cm.selectionStart,4);assert.equal(document.activeElement,nodes.cm);
 assert.equal(nodes.pkImg.files[0],selectedFile);assert.equal(nodes.pkAc.value,'A2');assert.equal(nodes.pkNote.value,'截图说明草稿');
 assert.equal(nodes.pkRn.value,'复核草稿');assert.equal(nodes.pkWaive.value,'尚未提交的例外理由');assert.equal(nodes.pkWaive.checked,true);assert.equal(nodes.pkGo.onclick,fixedSubmit)}
''' + "\n(async()=>{\n" + checks + "\n})().catch(e=>{console.error(e);process.exitCode=1});"
        result = subprocess.run([shutil.which("node"), "-"], input=harness, encoding="utf-8", errors="replace", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_record_updates_package_then_get_only_selection_reverts_gate_without_losing_drafts(self):
        self.run_js(r'''
nodes.pathMapDetails.open=true;await nodes.pathMapDetails.ontoggle();
await nodes.pathMapPanel.querySelector('[data-path-record]').onclick();
assert.ok(nodes.pkSummary.innerHTML.includes('5 条记录'),'recording must update the visible package, not only the ticket summary');
assert.ok(nodes.pkSummary.innerHTML.includes('>通过</span>'));preserved();
const boxes=nodes.pathMapPanel.querySelectorAll('[data-path-flow]');boxes[1].checked=false;boxes[1].onchange();
await nodes.pathMapPanel.querySelector('[data-path-record]').onclick();
assert.deepEqual(posts[1].payload.flows,['flow:get']);assert.ok(nodes.pkSummary.innerHTML.includes('6 条记录'));
assert.ok(nodes.pkSummary.innerHTML.includes('>未知</span>'));assert.ok(!nodes.pkSummary.innerHTML.includes('>通过</span>'));
assert.equal(nodes.pkDraftNotice.hidden,false);preserved();
''')

    def test_package_only_transition_with_same_status_and_records_is_not_ignored(self):
        self.run_js(r'''
latest=state(4,'pass');await S.ticketRefresh();assert.ok(nodes.pkSummary.innerHTML.includes('>通过</span>'));
latest=state(4,'unknown');await S.ticketRefresh();assert.ok(nodes.pkSummary.innerHTML.includes('>未知</span>'));
assert.ok(!nodes.pkSummary.innerHTML.includes('>通过</span>'));assert.equal(refreshes,2);preserved();
''')
