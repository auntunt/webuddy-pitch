"""Exercise shipped draft storage and submission handlers with persisted state."""
import shutil
import subprocess
import unittest
from tmh.platform.ui_drafts import DRAFT_JS
from tmh.platform.ui import page

@unittest.skipUnless(shutil.which('node'), 'Node is needed for shipped JavaScript')
class CommentDraftTest(unittest.TestCase):
    def run_js(self, checks):
        script=r'''
const assert=require('node:assert/strict');
const events={};const window={addEventListener:(k,f)=>events[k]=f};
const S={meta:{data_dir:'/one',user:'alice'},user:'alice',cur:null};
class Storage{constructor(){this.data=new Map();this.fail=false}getItem(k){return this.data.get(k)??null}setItem(k,v){if(this.fail)throw Error('quota');this.data.set(k,v)}removeItem(k){if(this.fail)throw Error('quota');this.data.delete(k)}}
const sessionStorage=new Storage(),nodes={},$=s=>nodes[s.slice(1)]||null,toast=()=>{},crypto={randomUUID:()=>String(++sequence)};
let sequence=0,requests=[],handler=async(url,b)=>({ok:true,event_id:12,request_id:b.request_id}),refreshes=0;
const post=async(url,b)=>{requests.push({url,b});return handler(url,b)};
const later=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};
function ticket(key='APP-1'){return{ticket:{id:key,key,created:'2026-10-19'},project:{id:1,key:'APP'}}}
function mount(d){for(const id of ['cm','cb','cmDraft','cmPending']){if(nodes[id])nodes[id].isConnected=false;nodes[id]={isConnected:true,value:'',textContent:'',hidden:false,disabled:false}}S.cur=d;S.ticketRefresh=async()=>{refreshes++};ticketCommentWire(d);return nodes.cm}
function input(text){nodes.cm.value=text;nodes.cm.oninput()}
''' + DRAFT_JS + r'''
(async()=>{
''' + checks + r'''
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        # Windows defaults subprocess text mode to the ANSI code page (GBK here); the page
        # copy below contains emoji/Chinese that GBK cannot encode, so pin UTF-8 on both
        # directions instead of letting the locale decide. Assertions stay unchanged.
        r=subprocess.run([shutil.which('node'),'-'],input=script,encoding='utf-8',errors='replace',capture_output=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_shipped_page_includes_wiring(self):
        html=page()
        self.assertIn('ticketCommentWire(d);',html)
        self.assertIn('function ticketCommentWire(d)',html)
        self.assertIn('不同标签页各自保存',html)
        self.assertIn('证据截图及其他表单不包含在内',html)

    def test_full_text_survives_reload_with_no_post(self):
        self.run_js(r'''
const text='  完整正文\n<script>原文</script>😀\n'+'长文'.repeat(20000)+'\n尾部  ';
mount(ticket());input(text);S.commentDrafts=new Map();mount(ticket());assert.equal(nodes.cm.value,text);assert.equal(requests.length,0);assert.ok(nodes.cmDraft.textContent.includes('已保存'));
''')

    def test_ticket_workspace_user_and_tab_isolation(self):
        self.run_js(r'''
mount(ticket());input('A');mount(ticket('APP-2'));assert.equal(nodes.cm.value,'');input('B');mount(ticket());assert.equal(nodes.cm.value,'A');
S.user='bob';mount(ticket());assert.equal(nodes.cm.value,'');input('Bob');S.user='alice';S.meta.data_dir='/two';mount(ticket());assert.equal(nodes.cm.value,'');
S.meta.data_dir='/one';mount(ticket());assert.equal(nodes.cm.value,'A');
const otherTab=new Storage();const independent=commentDraftOpen(commentDraftScope(ticket()),otherTab,new Map());assert.equal(independent.record.body,'');commentDraftChange(independent,'other tab');assert.equal(nodes.cm.value,'A');
''')

    def test_success_clears_only_sent_version_and_updates_without_replacing_form(self):
        self.run_js(r'''
const original=mount(ticket());input('  原评论\n  ');const pending=later();handler=()=>pending.promise;
const request=nodes.cb.onclick();await nodes.cb.onclick();assert.equal(requests.length,1);assert.equal(nodes.cb.disabled,true);input('发送过程中新增草稿');pending.resolve({ok:true,event_id:3,request_id:requests[0].b.request_id});await request;
assert.equal(nodes.cm,original);assert.equal(nodes.cm.value,'发送过程中新增草稿');assert.equal(refreshes,1);assert.equal(requests[0].b.body,'  原评论\n  ');
S.commentDrafts=new Map();mount(ticket());assert.equal(nodes.cm.value,'发送过程中新增草稿');
handler=async(url,b)=>({ok:true,event_id:4,request_id:b.request_id});await nodes.cb.onclick();assert.equal(nodes.cm.value,'');S.commentDrafts=new Map();mount(ticket());assert.equal(nodes.cm.value,'');
''')

    def test_failed_send_restores_outbox_and_deduplicates_after_reload(self):
        self.run_js(r'''
mount(ticket());input('原评论');handler=async()=>{throw Error('response lost')};await nodes.cb.onclick();const first=requests[0];assert.equal(nodes.cm.value,'原评论');assert.equal(nodes.cb.textContent,'确认上次发送');
input('新的草稿');S.commentDrafts=new Map();mount(ticket());assert.equal(nodes.cm.value,'新的草稿');assert.equal(nodes.cmPending.textContent,'原评论');assert.equal(requests.length,1);
handler=async(url,b)=>({ok:true,event_id:5,request_id:b.request_id});await nodes.cb.onclick();assert.equal(requests[1].b.request_id,first.b.request_id);assert.equal(requests[1].b.body,'原评论');assert.equal(nodes.cm.value,'新的草稿');assert.equal(nodes.cmPending.hidden,true);
''')

    def test_late_reply_does_not_repaint_other_ticket(self):
        self.run_js(r'''
mount(ticket());input('A');const p=later();handler=()=>p.promise;const send=nodes.cb.onclick();mount(ticket('APP-2'));input('B');const other=nodes.cm;p.resolve({ok:true,event_id:6,request_id:requests[0].b.request_id});await send;assert.equal(nodes.cm,other);assert.equal(nodes.cm.value,'B');assert.equal(refreshes,0);mount(ticket());assert.equal(nodes.cm.value,'');
''')

    def test_storage_failure_warns_keeps_text_and_never_sends_unpersisted_outbox(self):
        self.run_js(r'''
mount(ticket());sessionStorage.fail=true;input('不能丢失');assert.ok(nodes.cmDraft.textContent.includes('未能保存'));await nodes.cb.onclick();assert.equal(requests.length,0);assert.equal(nodes.cm.value,'不能丢失');let prevented=false;events.beforeunload({preventDefault(){prevented=true}});assert.equal(prevented,true);
sessionStorage.fail=false;await nodes.cb.onclick();assert.equal(requests.length,1);assert.equal(nodes.cm.value,'');
''')

    def test_corrupt_record_is_not_overwritten_and_wrong_receipt_keeps_pending(self):
        self.run_js(r'''
const scope=commentDraftScope(ticket()),key='tmh.comment.v1:'+scope;sessionStorage.data.set(key,'{broken');mount(ticket());assert.ok(nodes.cmDraft.textContent.includes('未覆盖'));input('新文字');await nodes.cb.onclick();assert.equal(sessionStorage.data.get(key),'{broken');assert.equal(requests.length,0);
const d=ticket('APP-2');mount(d);input('B');handler=async()=>({ok:true,event_id:2,request_id:'wrong'});await nodes.cb.onclick();assert.equal(nodes.cm.value,'B');assert.equal(nodes.cmPending.hidden,false);assert.ok(nodes.cmDraft.textContent.includes('未返回匹配'));
''')

    def test_user_switch_during_request_does_not_clear_another_identity(self):
        self.run_js(r'''
mount(ticket());input('Alice');const p=later();handler=()=>p.promise;const sending=nodes.cb.onclick();S.user='bob';mount(ticket());input('Bob');p.resolve({ok:true,event_id:7,request_id:requests[0].b.request_id});await sending;assert.equal(nodes.cm.value,'Bob');assert.equal(requests[0].b.expected_author,'alice');assert.equal(refreshes,0);
''')

if __name__=='__main__':unittest.main()
