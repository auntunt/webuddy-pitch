"""Shipped retry/identity logic with a mocked renderer, not a browser claim."""
import shutil
import subprocess
import unittest

from tmh.platform.ui import page
from tmh.platform.ui_pilots import PILOTS_JS

HARNESS=r"""
const assert=require('node:assert/strict');
const {randomUUID}=require('node:crypto');const crypto={randomUUID};
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const apiErr=message=>Object.assign(new Error(message),{api:1});
const ACCESS={base:'/t/synthetic',epoch:1,blocked:false};
const location={origin:'https://fixture.invalid',hash:'#/pilots/APP/pilot1'};
const values=new Map();const sessionStorage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
const notice={textContent:'',innerHTML:'',className:'',appendChild(){},querySelector:()=>({onclick:null})};
const host={isConnected:true,querySelector:s=>s==='#piNotice'?notice:null,querySelectorAll:()=>[]};
const document={createElement:()=>({})};const S={proj:'APP'};
let posts=[],gets=[],postHandler=async()=>({id:'pilot1',receipt:{event_id:1}}),getHandler=async()=>({id:'pilot1'}),painted=0;
const post=async(path,body)=>{posts.push({path,body:JSON.parse(JSON.stringify(body))});return postHandler(path,body)};
const get=async path=>{gets.push(path);return getHandler(path)};
"""
SETUP=r"""
piPaint=()=>{painted++};
const view=()=>({host,actor:'alice',project:'APP',id:'pilot1',route:location.hash,epoch:ACCESS.epoch,data:{id:'pilot1',version:3,revision:1,protocol_hash:'exact-hash',protocol:{title:'完整原文\r\n尾部  '}}});
let v=view();PI.page=v;
"""


@unittest.skipUnless(shutil.which('node'),'Node required for shipped client logic')
class PilotUITest(unittest.TestCase):
    def run_js(self,checks):
        result=subprocess.run(['node','-'],input=HARNESS+'\n'+PILOTS_JS+'\n'+SETUP+'\n(async()=>{'+checks+'})().catch(e=>{console.error(e);process.exitCode=1});',text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_unknown_post_reuses_identical_request_after_remount(self):
        self.run_js("postHandler=async()=>{throw Error('unknown transport result')};await piWrite(v,{action:'confirm'});const raw=JSON.stringify(posts[0].body);assert.ok(piLoad(piKey(v)+'|pending'));v=view();PI.page=v;postHandler=async()=>({id:'pilot1',receipt:{event_id:2}});await piWrite(v,null);assert.equal(JSON.stringify(posts[1].body),raw);assert.equal(posts[1].body.expected_actor,'alice');assert.equal(piLoad(piKey(v)+'|pending'),null);assert.equal(painted,1);")

    def test_read_failure_after_receipt_does_not_resubmit_mutation(self):
        self.run_js("getHandler=async()=>{throw Error('read failed')};await piWrite(v,{action:'confirm'});assert.equal(posts.length,1);assert.equal(piLoad(piKey(v)+'|pending'),null);assert.ok(notice.textContent.includes('无需重新提交'));assert.equal(painted,0);")

    def test_pending_request_prevents_changed_body_and_actor_replay(self):
        self.run_js("postHandler=async()=>{throw Error('lost')};await piWrite(v,{action:'confirm'});await piWrite(v,{action:'freeze'});assert.equal(posts.length,1);const old=piLoad(piKey(v)+'|pending');old.actor='bob';piPut(piKey(v)+'|pending',old);await piWrite(v,null);assert.equal(posts.length,1);assert.ok(notice.textContent.includes('身份已变化'));")

    def test_late_result_never_renders_after_identity_or_route_change(self):
        self.run_js("getHandler=async()=>{ACCESS.epoch++;return {id:'pilot1'}};await piWrite(v,{action:'confirm'});assert.equal(painted,0);assert.equal(posts.length,1);ACCESS.epoch=v.epoch;location.hash='#/projects';await piWrite(v,{action:'confirm'});assert.equal(posts.length,1);")

    def test_storage_and_drafts_bind_tenant_actor_project_object_and_source(self):
        self.run_js(r"const original=piKey(v);for(const [key,val] of [['actor','bob'],['project','OTHER'],['id','another']])assert.notEqual(piKey({...v,[key]:val}),original);ACCESS.base='/t/other';assert.notEqual(piKey(v),original);ACCESS.base='/t/synthetic';piPut(piKey(v)+'|draft',{base:'exact-hash',protocol:{title:'完整草稿\r\n  '}});assert.equal(piDraft(v).title,'完整草稿\r\n  ');v.data.protocol_hash='new-hash';assert.equal(piDraft(v).title,'完整原文\r\n尾部  ');")

    def test_successful_labor_clears_only_own_pending_draft(self):
        self.run_js("piPut(piKey(v)+'|labor',{note:'原草稿'});await piWrite(v,{action:'labor',labor:{note:'完整记录'}});assert.equal(piLoad(piKey(v)+'|labor'),null);assert.equal(posts[0].body.protocol_hash,'exact-hash');assert.ok(piField('note','说明','<script>raw</script>',true).includes('&lt;script&gt;'));assert.ok(!piField('note','说明','<script>raw</script>',true).includes('<script>'));")

    def test_unchanged_textarea_preserves_original_line_endings(self):
        self.run_js(r"assert.equal(piPreserve('完整\r\n尾部  ','完整\n尾部  '),'完整\r\n尾部  ');assert.equal(piPreserve('旧原文','新原文'),'新原文');")

    def test_complete_shipped_page_javascript_parses(self):
        shipped=page();script=shipped.split('<script>',1)[1].rsplit('</script>',1)[0]
        result=subprocess.run(['node','--check'],input=script,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('vPilots(',script)
        self.assertIn('登记本次投入 / 团队试点',script)


if __name__=='__main__':unittest.main()
