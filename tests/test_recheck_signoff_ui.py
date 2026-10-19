"""Invalid current proof disables every ticket sign-off entry without erasing drafts."""
import shutil
import subprocess
import unittest

from tmh.platform.ui import JS
from tmh.platform.ui_work import WORK_JS


@unittest.skipUnless(shutil.which("node"), "Node.js needed for shipped sign-off handlers")
class RecheckSignoffUiTest(unittest.TestCase):
    def run_js(self, checks):
        summary = "function ticketSummarySync" + JS.split("function ticketSummarySync", 1)[1].split("function watchIntakeRecovery", 1)[0]
        package = "const PKC=" + JS.split("const PKC=", 1)[1].split("function upCard", 1)[0]
        top = "function plainState" + WORK_JS.split("function plainState", 1)[1]
        acceptance = "const acc=async res=>" + JS.split("const acc=async res=>", 1)[1].split("  $('#accDraft')", 1)[0]
        acceptance_html = "const accUi=" + JS.split("const accUi=", 1)[1].split("  const reviewing=", 1)[0]
        script = r'''
const assert=require('node:assert/strict');
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nodes={},document={activeElement:null,querySelectorAll:()=>[]};
class Element{
 constructor(id){this.id=id;this.isConnected=true;this.value='';this.hidden=false;this.controls=[];this.disabled=false;this.childElementCount=0;this.html='';this.files=[]}
 set innerHTML(value){for(const c of this.controls)delete nodes[c.id];this.controls=[];this.html=value;
  for(const m of value.matchAll(/<(?:button|input|textarea)\b([^>]*)>/g)){
   const id=/\bid="([^"]*)"/.exec(m[1]);if(!id)continue;const c=new Element(id[1]);c.disabled=/\bdisabled\b/.test(m[1]);this.controls.push(c);nodes[c.id]=c;
  }this.childElementCount=this.controls.length;
 }
 get innerHTML(){return this.html}
 contains(n){return this===n} focus(){document.activeElement=this} scrollIntoView(){}
 click(){if(!this.disabled)return this.onclick?.()}
}
for(const id of ['tTop','tSteps','tNextText','tNextActions','tRunCount','tRunHistory','tStatus','fs','cm','accNote','accOk','accNo','pkSummary','pkActions','pkForm','pkDraftNotice','pkg'])nodes[id]=new Element(id);
const $=s=>nodes[s.slice(1)]||null;
const stChip=h,secOf=()=>'',symptomOf=t=>t.title,clip=(v,n)=>v.slice(0,n),md=h,stPill=h;
const flowState=()=>({}),nextAction=()=>({tone:'warn',text:'旧结果已失效',acc:true}),stepper=()=>'',ticketRunCount=()=>'',ticketRunHistory=()=>'';
const state=()=>({ticket:{key:'APP-1',status:'verify',links:{},title:'候选修改',body:'原需求'},events:[],runs:[{id:1,mode:'fix',status:'done',verify:{verification_current:true}}],evidence:{},plain_state:{state:'you',why:'待验收'},
 package:{status:'incomplete',label:'证据不齐',intact:true,records:4,hash:'a'.repeat(64),missing:['人工复核'],gates:[],binding_blocked:[]}});
let d=state(),latest=d;const key=d.ticket.key,S={cur:d},posts=[],messages=[];
const toast=t=>messages.push(t),vTicket=()=>{throw Error('unexpected full page replacement')};
let postHandler=async()=>({path:'/sign/test',signer:'客户',expires:'2026-10-20 12:00'});
const post=async(url,payload)=>{posts.push({url,payload});return postHandler(url,payload)};
const later=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
const get=async url=>url.endsWith('/preview')?{preview:{state:'none'}}:latest;
const location={origin:'http://localhost'},navigator={clipboard:{writeText:async()=>{}}};
''' + summary + package + top + r'''
async function paint(){nodes.tTop.innerHTML=ticketTop(d,{},nextAction(d));nodes.pkActions.innerHTML=pkgActions(d);await ticketTopWire(d,nextAction(d));pkgWire(d)}
function bindAcceptance(){
''' + acceptance + r'''
}
function acceptanceMarkup(){
''' + acceptance_html + r'''
return accUi}
(async()=>{
''' + checks + r'''
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run([shutil.which("node"), "-"], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_binding_failure_disables_and_guards_every_signoff_entry(self):
        self.run_js(r'''
d.package.binding_blocked=['旧证据 <script> 与候选不匹配'];await paint();bindAcceptance();
for(const id of ['ttSend','ttOk','pkLink','accOk'])assert.equal(nodes[id].disabled,true,id);
assert.ok(/id="accOk"[^>]*disabled/.test(acceptanceMarkup()));
for(const id of ['ttSend','ttOk','pkLink','accOk'])await nodes[id].onclick();
assert.deepEqual(posts,[]);assert.equal(nodes.pkForm.childElementCount,0);
assert.ok(nodes.pkActions.innerHTML.includes('/e/APP-1'));assert.equal(nodes.pkShot.disabled,false);
assert.ok(!nodes.pkActions.innerHTML.includes('<script>'));assert.ok(messages.some(x=>x.includes('候选不匹配')));
''')

    def test_known_recheck_invalid_blocks_without_package_flag_and_old_history_does_not(self):
        self.run_js(r'''
for(const field of ['verify','recheck']){
 d=state();d.runs[0][field]=field==='verify'?{verification_current:false}:{invalid:true};S.cur=d;
 await paint();bindAcceptance();assert.equal(nodes.ttSend.disabled,true);await nodes.accOk.onclick();assert.deepEqual(posts,[]);
}
d=state();d.runs.push({id:0,mode:'fix',status:'done',verify:{verification_current:false}});S.cur=d;
await paint();bindAcceptance();assert.equal(nodes.ttSend.disabled,false);assert.equal(nodes.pkLink.disabled,false);assert.equal(nodes.accOk.disabled,false);
''')

    def test_refresh_blocks_an_already_open_link_form_without_replacing_draft_nodes(self):
        self.run_js(r'''
await paint();bindAcceptance();await nodes.pkLink.onclick();
const submit=nodes.pkLgo.onclick,form=nodes.pkForm,signer=nodes.pkS,note=nodes.pkN,comment=nodes.cm,accept=nodes.accNote;
signer.value='尚未提交的签收人';note.value='完整签收说明';comment.value='未发送评论';accept.value='验收草稿';
const file=new Element('testScreenshot');file.files=[{name:'原始截图.png',size:12345}];form.file=file;
S.ticketRefresh=ticketSummarySync(d,n=>{d=n});latest=structuredClone(d);latest.package.binding_blocked=['重新验证已中断，请检查停止回执'];
await S.ticketRefresh();
for(const id of ['ttSend','ttOk','pkLink','pkLgo','accOk'])assert.equal(nodes[id].disabled,true,id);
await submit();await nodes.accOk.onclick();assert.deepEqual(posts,[]);
assert.equal(nodes.pkForm,form);assert.equal(nodes.pkS,signer);assert.equal(nodes.pkN,note);assert.equal(nodes.cm,comment);assert.equal(nodes.accNote,accept);
assert.equal(signer.value,'尚未提交的签收人');assert.equal(note.value,'完整签收说明');assert.equal(comment.value,'未发送评论');assert.equal(accept.value,'验收草稿');assert.equal(form.file,file);assert.equal(file.files[0].name,'原始截图.png');
latest=structuredClone(d);latest.package.binding_blocked=[];await S.ticketRefresh();assert.equal(nodes.pkLgo.disabled,false);assert.equal(nodes.accOk.disabled,false);
''')

    def test_repack_is_visible_only_for_stale_package_and_requires_current_stopped_verification(self):
        self.run_js(r'''
await paint();assert.equal(nodes.pkPack,undefined);
d.package.stale=true;d.package.binding_blocked=['旧包依据已过期 <script>'];d.runs[0].verify.verification_current=false;await paint();
assert.equal(nodes.pkPack.disabled,true);await nodes.pkPack.onclick();assert.deepEqual(posts,[]);
d.runs[0].verify.verification_current=true;d.runs[0].recheck={running:true};await paint();assert.equal(nodes.pkPack.disabled,true);await nodes.pkPack.onclick();assert.deepEqual(posts,[]);
d.runs[0].recheck={running:false};await paint();assert.equal(nodes.pkPack.disabled,false,'stale package is the reason to repack, not a permanent block');
assert.ok(nodes.pkActions.innerHTML.includes('按当前验证重新打包'));assert.equal(nodes.pkLink.disabled,true);
const summary=pkgSummary(d);assert.ok(!summary.includes('<script>'));assert.ok(summary.includes('&lt;script&gt;'));
''')

    def test_repack_refreshes_only_summary_preserves_file_and_retains_customer_missing_items(self):
        self.run_js(r'''
d.package.stale=true;d.package.binding_blocked=['旧包需重新生成'];await paint();
nodes.pkShot.onclick();const form=nodes.pkForm,file=nodes.pkImg,note=nodes.pkNote,comment=nodes.cm,accept=nodes.accNote;
const image={name:'完整截图.png',size:12345};file.files=[image];note.value='图片证据草稿';comment.value='未发送评论';accept.value='验收草稿';
S.ticketRefresh=ticketSummarySync(d,n=>{d=n});postHandler=async()=>{latest=structuredClone(d);latest.package={...latest.package,stale:false,binding_blocked:[],hash:'b'.repeat(64),records:5,link:null,decision:null,review:null,missing:['人工复核','客户业务验收']};return{package:latest.package}};
await nodes.pkPack.onclick();assert.deepEqual(posts,[{url:'/api/tickets/APP-1/evidence',payload:{kind:'pack'}}]);
assert.equal(nodes.pkPack,undefined);assert.ok(nodes.pkSummary.innerHTML.includes('5 条记录'));assert.ok(nodes.pkSummary.innerHTML.includes('客户业务验收'));assert.ok(nodes.pkSummary.innerHTML.includes('人工复核'));
assert.equal(S.cur.package.review,null);assert.equal(S.cur.package.decision,null);assert.equal(S.cur.package.link,null);
assert.equal(nodes.pkForm,form);assert.equal(nodes.pkImg,file);assert.equal(nodes.pkNote,note);assert.equal(nodes.cm,comment);assert.equal(nodes.accNote,accept);
assert.equal(file.files[0],image);assert.equal(note.value,'图片证据草稿');assert.equal(comment.value,'未发送评论');assert.equal(accept.value,'验收草稿');
''')

    def test_repack_busy_survives_rewiring_and_errors_are_retryable_without_late_page_mutation(self):
        self.run_js(r'''
d.package.stale=true;await paint();S.ticketRefresh=async()=>{};const first=later();postHandler=()=>first.promise;const pending=nodes.pkPack.onclick();
await paint();assert.equal(nodes.pkPack.disabled,true);await nodes.pkPack.onclick();assert.equal(posts.length,1);
first.reject(new Error('完整失败 <raw> '+('原始错误'.repeat(400))+'结束'));await pending;
assert.equal(nodes.pkPack.disabled,false);assert.ok(messages.some(x=>x.endsWith('结束')));
const second=later();postHandler=()=>second.promise;let refreshes=0;S.ticketRefresh=async()=>{refreshes++};const retry=nodes.pkPack.onclick();assert.equal(posts.length,2);
S.cur={ticket:{key:'OTHER-1'}};const other=new Element('pkForm');nodes.pkForm=other;second.resolve({});await retry;
assert.equal(refreshes,0);assert.equal(nodes.pkForm,other);assert.equal(other.innerHTML,'');
''')
