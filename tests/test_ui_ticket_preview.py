"""Exercise the shipped ticket preview handlers with deferred HTTP responses."""
import shutil
import subprocess
import unittest

from tmh.platform.ui import JS
from tmh.platform.ui_work import WORK_JS


@unittest.skipUnless(shutil.which("node"), "Node.js needed for shipped preview handlers")
class TicketPreviewUiTest(unittest.TestCase):
    def run_js(self, checks):
        preview = "const PVL=" + JS.split("const PVL=", 1)[1].split("// ---------- 我来写", 1)[0]
        top = "async function ticketTopWire" + WORK_JS.split("async function ticketTopWire", 1)[1]
        script = r'''
const assert=require('node:assert/strict');
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
class Element {
 constructor(id){this.id=id;this.html='';this.hidden=false;this.controls=[];this.value=''}
 unregister(){for(const c of this.controls)c.unregister();if(nodes[this.id]===this)delete nodes[this.id]}
 register(){nodes[this.id]=this;for(const c of this.controls)c.register()}
 set innerHTML(value){for(const c of this.controls)c.unregister();this.controls=[];this.html=value;
   for(const m of value.matchAll(/\bid="([^"]+)"/g)){const c=new Element(m[1]);c.parent=this;c.register();this.controls.push(c)}}
 get innerHTML(){return this.html}
 querySelector(s){for(const c of this.controls){if('#'+c.id===s)return c;const n=c.querySelector(s);if(n)return n}return null}
 replaceWith(other){this.unregister();this.parent.controls[this.parent.controls.indexOf(this)]=other;other.parent=this.parent;other.register()}
}
const nodes={},$=s=>nodes[s.slice(1)]||null;
function page(key){for(const id of Object.keys(nodes))delete nodes[id];for(const id of ['pvc','ttPv','cm','accNote'])nodes[id]=new Element(id);S.cur={ticket:{key,links:{}}}}
const S={};page('APP-1');let view='t';const curView=()=>view,clip=(s,n)=>s.slice(0,n),toast=()=>{};
const get=url=>getHandler(url),post=async()=>({}),timers=[];const setTimeout=fn=>timers.push(fn);
const later=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
const healthy={preview:{state:'up',commit:'abc'},url:'/pv/APP-1/__commit/abc/',cmd:'python app.py',branch:'candidate',own_address:true};
const failed={...healthy,url:'',preview:{state:'unhealthy',commit:'abc',why:'HTTP 503 <db>'}};
let getHandler=async()=>failed;
''' + preview + top + "\n(async()=>{\n" + checks + "\n})().catch(e=>{console.error(e);process.exitCode=1});"
        result = subprocess.run([shutil.which("node"), "-"], input=script, encoding="utf-8", errors="replace", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_refresh_updates_both_views_without_replacing_drafts(self):
        self.run_js(r'''
const comment=nodes.cm,note=nodes.accNote;comment.value='完整未发送评论';note.value='尚未提交验收';
await ticketTopWire(S.cur,{});
for(const id of ['ttPv','pvc']){assert.ok(nodes[id].innerHTML.includes('503'));assert.ok(!nodes[id].innerHTML.includes('href="/pv/'));assert.ok(!nodes[id].innerHTML.includes('<db>'))}
getHandler=async()=>healthy;await nodes.pvRefresh.onclick();
for(const id of ['ttPv','pvc']){assert.ok(nodes[id].innerHTML.includes('href="/pv/APP-1/__commit/abc/"'));assert.ok(!nodes[id].innerHTML.includes('503'))}
assert.equal(nodes.cm,comment);assert.equal(nodes.accNote,note);assert.equal(comment.value,'完整未发送评论');assert.equal(note.value,'尚未提交验收');
getHandler=async()=>failed;await pvLoad('APP-1');
for(const id of ['ttPv','pvc'])assert.ok(!nodes[id].innerHTML.includes('href="/pv/'));
''')

    def test_older_health_response_cannot_replace_a_newer_refresh(self):
        self.run_js(r'''
const delayed=later();getHandler=()=>delayed.promise;const older=ticketTopWire(S.cur,{});
getHandler=async()=>healthy;await pvLoad('APP-1');delayed.resolve(failed);await older;
for(const id of ['ttPv','pvc']){assert.ok(nodes[id].innerHTML.includes('href="/pv/'));assert.ok(!nodes[id].innerHTML.includes('503'))}
''')

    def test_late_response_cannot_paint_a_different_ticket_or_reopened_page(self):
        self.run_js(r'''
for(const key of ['APP-2','APP-1']){
 page('APP-1');const delayed=later();getHandler=()=>delayed.promise;const older=pvLoad('APP-1');
 page(key);nodes.ttPv.innerHTML='new summary';nodes.pvc.innerHTML='new preview';delayed.resolve(failed);await older;
 assert.equal(nodes.ttPv.innerHTML,'new summary');assert.equal(nodes.pvc.innerHTML,'new preview');
}
''')

    def test_read_failure_removes_old_open_links_in_both_views_and_can_retry(self):
        self.run_js(r'''
getHandler=async()=>healthy;await pvLoad('APP-1');
getHandler=async()=>{throw Error('connection closed <unsafe>')};await pvLoad('APP-1');
for(const id of ['ttPv','pvc']){assert.ok(!nodes[id].innerHTML.includes('href="/pv/'));assert.ok(nodes[id].innerHTML.includes('connection closed'));assert.ok(!nodes[id].innerHTML.includes('<unsafe>'))}
getHandler=async()=>healthy;await nodes.pvRefresh.onclick();
for(const id of ['ttPv','pvc'])assert.ok(nodes[id].innerHTML.includes('href="/pv/'));
''')

    def test_background_summary_refresh_preserves_preview_configuration_draft(self):
        self.run_js(r'''
const stopped={...healthy,url:'',preview:{state:'stopped'}};
getHandler=async url=>url.endsWith('/preview-conf')?{cmd:'python app.py',ready:'/health'}:stopped;
await ticketTopWire(S.cur,{});await nodes.pvCfg.onclick();
const form=nodes.pvF,cmd=nodes.pvCmd,ready=nodes.pvReady,save=nodes.pvSave.onclick;
cmd.value='完整未保存启动命令';ready.value='/尚未保存的健康路径';
nodes.ttPv=new Element('ttPv');await ticketTopWire(S.cur,{});
assert.equal(nodes.pvF,form);assert.equal(nodes.pvCmd,cmd);assert.equal(nodes.pvReady,ready);assert.equal(nodes.pvSave.onclick,save);
assert.equal(cmd.value,'完整未保存启动命令');assert.equal(ready.value,'/尚未保存的健康路径');
''')

    def test_delayed_configuration_load_does_not_fill_another_ticket(self):
        self.run_js(r'''
getHandler=async()=>({...healthy,url:'',preview:{state:'stopped'}});await pvLoad('APP-1');
const delayed=later();getHandler=()=>delayed.promise;const pending=nodes.pvCfg.onclick();
page('APP-2');getHandler=async()=>({...healthy,url:'',preview:{state:'stopped'}});await pvLoad('APP-2');
delayed.resolve({cmd:'old command',ready:'/old-health'});await pending;
assert.equal(nodes.pvF.innerHTML,'');assert.equal(nodes.pvCmd,undefined);
''')
