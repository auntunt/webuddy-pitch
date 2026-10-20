"""Independent comment-draft regression cases against the shipped JavaScript.

The VM supplies browser storage/DOM boundaries; no real comments or models are run.
"""
import json
import shutil
import subprocess
import unittest

from tmh.platform.ui import JS
from tmh.platform.ui_drafts import DRAFT_JS


HARNESS = r'''
class Storage {
 constructor(){this.rows=new Map();this.failWrite=false;this.failRemove=false}
 getItem(key){return this.rows.has(key)?this.rows.get(key):null}
 setItem(key,value){if(this.failWrite)throw Error('quota');this.rows.set(key,value)}
 removeItem(key){if(this.failRemove)throw Error('remove unavailable');this.rows.delete(key)}
}
const sessionStorage=new Storage(),events={},nodes={},messages=[],requests=[],seen=[];
const window={addEventListener:(name,fn)=>events[name]=fn};
const S={user:'alice',meta:{user:'alice',data_dir:'/workspace/one'},cur:null};
const $=selector=>nodes[selector.slice(1)]||null;
let serial=0,refreshes=0,handler=async(url,body)=>({ok:true,event_id:91,request_id:body.request_id});
const crypto={randomUUID:()=>`independent-request-${++serial}`};
const toast=message=>messages.push(message);
const post=async(url,body)=>{requests.push({url,body:structuredClone(body)});return handler(url,body)};
const later=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
function ticket(key='APP-1'){return {project:{id:3,key:'APP'},ticket:{id:key,key,created:'2026-10-19 12:00:00'}}}
function element(){return {isConnected:true,value:'',textContent:'',hidden:false,disabled:false,dataset:{}}}
function mount(d=ticket()){
 for(const id of ['cm','cb','cmDraft','cmPending']){if(nodes[id])nodes[id].isConnected=false;nodes[id]=element()}
 S.cur=d;S.ticketRefresh=async()=>{refreshes++;seen.push(d.ticket.key)};ticketCommentWire(d);return nodes.cm;
}
function type(text){nodes.cm.value=text;nodes.cm.oninput()}
function reload(d=ticket()){S.commentDrafts=new Map();return mount(d)}
function receipt(body,event=91){return {ok:true,event_id:event,request_id:body.request_id}}
'''


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for the shipped handlers')
class CommentDraftIndependentTest(unittest.TestCase):
    def run_js(self, checks, extra=''):
        source = HARNESS + DRAFT_JS + extra + '\n(async()=>{\n' + checks + '\n})()'
        runner = ('const vm=require("node:vm"),assert=require("node:assert/strict");\n'
                  'Promise.resolve(vm.runInNewContext(' + json.dumps(source) + ', '
                  '{assert,structuredClone,console})).catch(error=>{console.error(error);process.exitCode=1});')
        result = subprocess.run([shutil.which('node'), '-'], input=runner, encoding="utf-8", errors="replace", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_late_receipt_after_leaving_and_returning_refreshes_the_current_ticket(self):
        self.run_js(r'''
mount();type('发送前的完整评论');const pending=later();handler=()=>pending.promise;
const sending=nodes.cb.onclick();mount(ticket('APP-2'));type('B 的未发送正文');mount();
const current=nodes.cm;pending.resolve(receipt(requests[0].body));await sending;
assert.equal(nodes.cm,current);assert.equal(nodes.cm.value,'');assert.equal(refreshes,1);
assert.deepEqual(seen,['APP-1']);assert.ok(messages.some(x=>x.includes('评论已发送')));
mount(ticket('APP-2'));assert.equal(nodes.cm.value,'B 的未发送正文');
''')

    def test_edit_away_and_back_during_send_is_a_new_draft_even_when_text_matches(self):
        self.run_js(r'''
const text='  原评论\n保留空格和 😀\n  ';mount();type(text);
const pending=later();handler=()=>pending.promise;const sending=nodes.cb.onclick();
type('中间修改');type(text);pending.resolve(receipt(requests[0].body));await sending;
assert.equal(nodes.cm.value,text);assert.equal(requests[0].body.body,text);
reload();assert.equal(nodes.cm.value,text);assert.equal(requests.length,1);
''')

    def test_pending_retry_never_sends_new_draft_and_new_send_gets_new_receipt(self):
        self.run_js(r'''
const original='原请求\n'+'完整正文'.repeat(12000)+'\n结束  ';
mount();type(original);handler=async()=>{throw Error('response lost after commit')};await nodes.cb.onclick();
const prior=requests[0].body;type('后来写的新评论');reload();
assert.equal(nodes.cmPending.textContent,original);assert.equal(nodes.cm.value,'后来写的新评论');assert.equal(requests.length,1);
handler=async(url,body)=>receipt(body);await nodes.cb.onclick();
assert.equal(requests[1].body.request_id,prior.request_id);assert.equal(requests[1].body.body,original);
assert.equal(nodes.cm.value,'后来写的新评论');assert.equal(nodes.cmPending.hidden,true);
await nodes.cb.onclick();assert.notEqual(requests[2].body.request_id,prior.request_id);
assert.equal(requests[2].body.body,'后来写的新评论');reload();assert.equal(nodes.cm.value,'');
''')

    def test_unmatched_receipt_preserves_pending_and_edited_body_after_reload(self):
        self.run_js(r'''
mount();type('原请求');const pending=later();handler=()=>pending.promise;const sending=nodes.cb.onclick();
type('新文字');pending.resolve({ok:true,event_id:99,request_id:'other-request'});await sending;
assert.equal(nodes.cm.value,'新文字');assert.ok(nodes.cmDraft.textContent.includes('未返回匹配'));
reload();assert.equal(nodes.cm.value,'新文字');assert.equal(nodes.cmPending.textContent,'原请求');
assert.equal(nodes.cb.textContent,'确认上次发送');
''')

    def test_failure_to_remove_completed_record_retries_same_receipt_without_loss(self):
        self.run_js(r'''
mount();type('已发送但本地删除失败');sessionStorage.failRemove=true;await nodes.cb.onclick();
assert.equal(requests.length,1);const sent=requests[0].body;
assert.equal(nodes.cm.value,'');assert.ok(nodes.cmDraft.textContent.includes('未能保存'));
sessionStorage.failRemove=false;reload();assert.equal(nodes.cmPending.textContent,sent.body);
await nodes.cb.onclick();assert.equal(requests[1].body.request_id,sent.request_id);
assert.equal(requests[1].body.body,sent.body);assert.equal(nodes.cm.value,'');assert.equal(sessionStorage.rows.size,0);
''')

    def test_corrupt_pending_metadata_never_overwrites_original_record(self):
        self.run_js(r'''
const key='tmh.comment.v1:'+commentDraftScope(ticket());
const raw=JSON.stringify({version:1,body:'仍可人工找回的原文字',revision:2,pending:{body:'原请求',request_id:'id',revision:8}});
sessionStorage.rows.set(key,raw);mount();assert.ok(nodes.cmDraft.textContent.includes('原记录未覆盖'));
type('本页临时编辑');await nodes.cb.onclick();assert.equal(requests.length,0);
assert.equal(nodes.cm.value,'本页临时编辑');assert.equal(sessionStorage.rows.get(key),raw);
let warned=false;events.beforeunload({preventDefault(){warned=true}});assert.equal(warned,true);
''')

    def test_identity_change_blocks_old_handler_and_keeps_both_scoped_bodies(self):
        self.run_js(r'''
mount();type('Alice 原文');const oldClick=nodes.cb.onclick;S.user='bob';await oldClick();assert.equal(requests.length,0);
mount();assert.equal(nodes.cm.value,'');type('Bob 原文');S.user='alice';mount();assert.equal(nodes.cm.value,'Alice 原文');
S.meta.data_dir='/workspace/two';mount();type('另一个数据目录');S.meta.data_dir='/workspace/one';mount();assert.equal(nodes.cm.value,'Alice 原文');
S.user='bob';reload();assert.equal(nodes.cm.value,'Bob 原文');
''')

    def test_long_unicode_author_matches_server_codepoint_identity_without_truncating_draft(self):
        self.run_js(r'''
S.user='😀'.repeat(41)+'A';mount();const original='  正文仍须完整\n'+'内容😀'.repeat(300)+'\n尾部  ';type(original);
await nodes.cb.onclick();assert.equal(requests.length,1);
assert.equal(requests[0].body.expected_author,'😀'.repeat(40));
assert.equal(Array.from(requests[0].body.expected_author).length,40);
assert.equal(S.user,'😀'.repeat(41)+'A');assert.equal(requests[0].body.body,original);
''')

    def test_authenticated_actor_uses_server_identity_not_stale_local_display_name(self):
        self.run_js(r'''
S.meta.login=true;S.meta.user='实际登录者😀';S.user='旧的本地显示名';mount();type('仅由实际登录者提交');
await nodes.cb.onclick();assert.equal(requests.length,1);
assert.equal(requests[0].body.expected_author,'实际登录者😀');assert.equal(S.user,'旧的本地显示名');
''')

    def test_changed_authenticated_identity_blocks_old_submit_handler(self):
        self.run_js(r'''
S.meta.login=true;S.meta.user='alice';S.user='保留的显示名';mount();type('只属于 Alice 的草稿');
const submit=nodes.cb.onclick;S.meta.user='bob';await submit();
assert.equal(requests.length,0,'a handler captured for Alice must not transmit after authenticated identity changes');
assert.equal(nodes.cm.value,'只属于 Alice 的草稿');
''')

    def test_quota_failure_never_posts_unrecoverable_request_or_truncates_body(self):
        self.run_js(r'''
const body='全量文字\n'+'长文😀'.repeat(12000)+'\n最后一行';mount();sessionStorage.failWrite=true;type(body);
await nodes.cb.onclick();assert.equal(requests.length,0);assert.equal(nodes.cm.value,body);
assert.ok(nodes.cmDraft.textContent.includes('未能保存'));assert.equal(sessionStorage.rows.size,0);
sessionStorage.failWrite=false;await nodes.cb.onclick();assert.equal(requests.length,1);assert.equal(requests[0].body.body,body);
''')

    def test_real_summary_refresh_updates_discussion_without_replacing_selected_file(self):
        summary = ('function ticketTimeline' + JS.split('function ticketTimeline', 1)[1]
                   .split('function watchIntakeRecovery', 1)[0])
        dependencies = r'''
let latest;const document={activeElement:null};
const get=async()=>latest,flowState=()=>({}),nextAction=()=>({text:'处理中',tone:'info'}),ticketTop=()=>'',stepper=()=>'';
const ticketRunCount=()=>'',ticketRunHistory=()=>'',stPill=s=>s,ticketTopWire=()=>{},isMachine=()=>false;
const evHtml=event=>event.body;
'''
        self.run_js(r'''
const d={...ticket(),runs:[],events:[],evidence:{},package:{status:'none'}};
d.ticket.status='doing';d.ticket.body='正文';
mount(d);latest=d;
for(const id of ['tTop','tSteps','tNextText','tNextActions','tRunCount','tRunHistory','tStatus','fs','tl','pkForm','pkNote','pkImg'])nodes[id]=element();
nodes.tTop.contains=()=>false;nodes.fs.value='doing';nodes.tl.dataset.f='talk';
nodes.tl.querySelectorAll=()=>[];nodes.pkNote.value='截图说明原文';
const image={name:'原始图片.png',bytes:new Uint8Array([0,255,34,0,128,17])};nodes.pkImg.files=[image];
const fileNode=nodes.pkImg,form=nodes.pkForm,note=nodes.pkNote,comment=nodes.cm;
S.ticketRefresh=ticketSummarySync(d,()=>{});
type('本次评论');const pending=later();handler=()=>pending.promise;const sending=nodes.cb.onclick();type('发送时仍在输入');
latest=structuredClone(d);latest.events.push({id:91,author:'alice',kind:'comment',body:'本次评论'});
pending.resolve(receipt(requests[0].body));await sending;
assert.equal(nodes.tl.innerHTML,'本次评论');assert.equal(nodes.tl.dataset.f,'talk');
assert.equal(nodes.cm,comment);assert.equal(nodes.cm.value,'发送时仍在输入');
assert.equal(nodes.pkForm,form);assert.equal(nodes.pkNote,note);assert.equal(nodes.pkNote.value,'截图说明原文');
assert.equal(nodes.pkImg,fileNode);assert.equal(nodes.pkImg.files[0],image);
assert.deepEqual(Array.from(image.bytes),[0,255,34,0,128,17]);
''', extra=dependencies + summary)


if __name__ == '__main__':
    unittest.main()
