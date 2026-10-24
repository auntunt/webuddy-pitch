"""Run the shipped lesson decision UI with controlled response barriers."""
import shutil
import subprocess
import json
import tempfile
from pathlib import Path
import unittest

from test_ui_library import HARNESS
from test_ui_memory import SETUP
from tmh.platform.ui_memory import MEMORY_JS


DECISION_SETUP = r"""
globalThis.crypto=require('node:crypto').webcrypto;
const sessionValues=new Map();const sessionStorage={getItem:k=>sessionValues.get(k)||null,setItem:(k,v)=>sessionValues.set(k,v),removeItem:k=>sessionValues.delete(k)};
S.meta={user:'alice',operator_authenticated:true};
const ACCESS={base:'/t/alpha',user:'alice',ready:true,blocked:false,epoch:1};
const sortJSON=v=>Array.isArray(v)?v.map(sortJSON):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sortJSON(v[k])])):v;
const hashJSON=v=>require('node:crypto').createHash('sha256').update(JSON.stringify(sortJSON(v))).digest('hex');
const rawContent=c=>Object.fromEntries(Object.entries(c).filter(([k])=>!['status','stats','abroad','history','shared','taken','active_revision','flags'].includes(k)));
const snapshot=(extra={},token='a'.repeat(64))=>{const card={id:'L1',project:'APP',title:'完整经验',symptom:'现象\r\n原行  ',cause:'原因',fix:'修法',verify:'验证',anti:'限制',applicability:'只有审批业务\r\n条件二',non_applicability:'不能用于财务',note:'完整备注',files:Array.from({length:9},(_,i)=>'src/full-'+i+'.py'),source:{nested:'完整来源'},status:'candidate',...extra};return{schema:1,project:card.project,lesson_id:card.id,card,expected_token:token,content_digest:hashJSON({schema:'lesson_content_v1',content:rawContent(card)})}};
const listed=s=>({...s.card,scope:'project',scope_label:'本项目记忆',usage_hint:'相近任务',snapshot:s});
const success=(s,body,extra={})=>{const action=body.action.replace(/^lesson_/,''),content={...rawContent(s.card),...(body.fields||{})},after=action==='retire'?'retired':['confirm','restore'].includes(action)?'active':s.card.status,current=snapshot({...s.card,...(body.fields||{}),status:after},'b'.repeat(64));return{schema:1,project:s.project,lesson_id:s.lesson_id,request_id:body.request_id,action,replayed:false,superseded:false,receipt:{schema:1,namespace:'human_lesson',project:s.project,lesson_id:s.lesson_id,actor:'alice',request_id:body.request_id,action,base_token:body.expected_token,reviewed_content:content,reviewed_content_digest:hashJSON({schema:'lesson_content_v1',content}),before_status:s.card.status,after_status:after,fields:body.fields||{},reason:body.reason||'',changed:true,at:'2026-10-24T12:00:00',decision_token:current.expected_token},current,...extra}};
let currentSnapshot=snapshot();memoryResponse=memoryData({lessons:[listed(currentSnapshot)]});S.scope='APP';S.proj='APP';location.hash='#/memory/lessons';
getHandler=url=>url.includes('/lessons/L1')?currentSnapshot:memoryResponse;
postHandler=async(url,body)=>success(currentSnapshot,body);
const mount=()=>vMemory('lessons');
"""


@unittest.skipUnless(shutil.which('node'), 'Node needed for shipped lesson UI')
class LessonDecisionUiTests(unittest.TestCase):
    def run_js(self, checks):
        result = subprocess.run([shutil.which('node'), '-'], input=HARNESS + SETUP + DECISION_SETUP + MEMORY_JS +
                                '\n(async()=>{\n' + checks + '\n})().catch(e=>{console.error(e);process.exitCode=1});',
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_confirm_binds_the_displayed_snapshot(self):
        self.run_js(r"""
await mount();await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');
assert.equal(mutations.length,1);assert.equal(mutations[0].body.expected_token,currentSnapshot.expected_token);
assert.match(mutations[0].body.request_id,/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
assert.equal(mutations[0].body.project,'APP');assert.equal(mutations[0].body.lesson_id,'L1');
assert.equal(mutations[0].headers['X-Webuddy-Lesson-Actor'],'alice');
""")

    def test_unknown_result_retries_exact_original_intent(self):
        self.run_js(r"""
await mount();const barrier=later();postHandler=()=>barrier.promise;const button=main.querySelector('[data-mem-act="lesson_confirm"]');
const first=button.fire('click');const duplicate=button.fire('click');assert.equal(mutations.length,1);
const original=JSON.stringify(mutations[0]);barrier.reject(new Error('网络中断'));await first;await duplicate;
assert.equal(button.disabled,true);const retry=main.querySelector('[data-lesson-retry]');assert.ok(retry);
currentSnapshot=snapshot({fix:'后来的正文'},'c'.repeat(64));postHandler=async()=>{throw new Error('仍未收到回执')};await retry.fire('click');
assert.equal(mutations.length,2);assert.equal(JSON.stringify(mutations[1]),original);
""")

    def test_review_includes_complete_conditions_files_and_source(self):
        self.run_js(r"""
await mount();for(const value of ['只有审批业务','条件二','不能用于财务','完整备注','完整来源',...currentSnapshot.card.files])assert.ok(main.textContent.includes(value),value);
assert.ok(main.querySelector('[data-lesson-full]').querySelector('pre').attrs.class.includes('mem-raw'));
""")

    def test_stale_version_requires_explicit_reread_and_never_rebinds(self):
        self.run_js(r"""
await mount();postHandler=async()=>{throw Object.assign(new Error('已变更'),{status:409,code:'lesson_changed'})};
await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');const old=JSON.stringify(mutations[0]);
currentSnapshot=snapshot({fix:'版本 B'},'c'.repeat(64));assert.equal(requests.length,1);assert.equal(mutations.length,1);
await main.querySelector('[data-lesson-read]').fire('click');assert.ok(main.textContent.includes('版本 B'));assert.equal(mutations.length,1);
assert.equal(JSON.stringify(mutations[0]),old);assert.equal(main.querySelector('[data-mem-act="lesson_confirm"]').disabled,true);
""")

    def test_malformed_or_misbound_receipts_remain_unknown(self):
        self.run_js(r"""
const corrupt=[r=>({}),r=>({...r,request_id:'other'}),r=>({...r,project:'STD'}),r=>({...r,action:'restore'}),r=>({...r,superseded:true}),r=>({...r,receipt:{...r.receipt,actor:'bob'}}),r=>({...r,receipt:{...r.receipt,base_token:'f'.repeat(64)}}),r=>({...r,receipt:{...r.receipt,reviewed_content:{...r.receipt.reviewed_content,fix:'错正文'}}}),r=>({...r,receipt:{...r.receipt,reviewed_content_digest:'d'.repeat(64)}}),r=>({...r,receipt:{...r.receipt,fields:{fix:'另一意图'}}}),r=>({...r,receipt:{...r.receipt,reason:'另一原因'}}),r=>({...r,receipt:{...r.receipt,changed:false}}),r=>({...r,current:{...r.current,project:'STD'}})];
for(const mutate of corrupt){lessonDecisionsClear();await mount();postHandler=async(url,body)=>mutate(success(currentSnapshot,body));await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');assert.ok(main.querySelector('[data-lesson-retry]'));assert.equal([...LESSON_DECISIONS.pending.values()][0].phase,'unknown')}
""")

    def test_replayed_receipt_cannot_claim_retired_card_is_active(self):
        self.run_js(r"""
await mount();postHandler=async(url,body)=>{const r=success(currentSnapshot,body);r.replayed=true;r.superseded=true;r.current=snapshot({status:'retired'},'c'.repeat(64));return r};
await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');assert.equal([...LESSON_DECISIONS.pending.values()][0].phase,'recorded');
assert.ok(main.textContent.includes('不代表当前仍在使用'));assert.ok(main.textContent.includes('retired'));assert.equal(mutations.length,1);
""")

    def test_storage_failure_prevents_post(self):
        self.run_js(r"""
await mount();sessionStorage.setItem=()=>{throw new Error('存储不可用')};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');
assert.equal(mutations.length,0);assert.ok($('#memNotice').textContent.includes('尚未提交'));assert.equal(LESSON_DECISIONS.pending.size,0);
""")

    def test_missing_snapshot_only_reads_without_automatically_confirming(self):
        self.run_js(r"""
memoryResponse=memoryData({lessons:[{...listed(currentSnapshot),snapshot:null}]});await mount();assert.equal(main.querySelector('[data-mem-act="lesson_confirm"]').disabled,true);
await main.querySelector('[data-lesson-read]').fire('click');assert.equal(mutations.length,0);assert.ok(main.querySelector('[data-lesson-reopen]'));
""")

    def test_permission_clear_scrubs_pending_drafts_and_late_response(self):
        self.run_js(r"""
await mount();const edit=main.querySelector('[data-mem-edit]');edit.querySelector('[data-mem-field="fix"]').value='私有草稿';edit.querySelector('[data-mem-field="fix"]').fire('input');
const barrier=later();postHandler=()=>barrier.promise;const sending=main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');const body=mutations[0].body;
ACCESS.epoch++;ACCESS.blocked=true;lessonDecisionsClear();main.innerHTML='<div id="locked">权限已变更</div>';barrier.resolve(success(currentSnapshot,body));await sending;
assert.equal(LESSON_DECISIONS.pending.size,0);assert.equal(LESSON_DECISIONS.drafts.size,0);assert.equal(sessionValues.size,0);assert.equal($('#locked').textContent,'权限已变更');
""")

    def test_restore_is_separate_and_preserves_full_reason(self):
        self.run_js(r"""
currentSnapshot=snapshot({status:'retired'});memoryResponse=memoryData({lessons:[listed(currentSnapshot)]});await mount();assert.equal(main.querySelector('[data-mem-act="lesson_confirm"]'),null);
await main.querySelector('[data-mem-act="lesson_restore"]').fire('click');assert.equal(mutations.length,0);const form=main.querySelector('[data-mem-editor]').querySelector('form');
await form.fire('submit');assert.equal(mutations.length,0);form.querySelector('[data-mem-reason]').value=' 人工复核\r\n完整理由  ';await form.fire('submit');
assert.equal(mutations[0].body.action,'lesson_restore');assert.equal(mutations[0].body.reason,' 人工复核\r\n完整理由  ');
""")

    def test_unchanged_browser_normalized_crlf_is_not_written_as_edit(self):
        self.run_js(r"""
const descriptor=Object.getOwnPropertyDescriptor(Element.prototype,'value');Object.defineProperty(Element.prototype,'value',{get(){const v=descriptor.get.call(this);return this.tag==='textarea'?v.replace(/\r\n?/g,'\n'):v},set(v){descriptor.set.call(this,this.tag==='textarea'?String(v).replace(/\r\n?/g,'\n'):v)}});
await mount();const form=main.querySelector('[data-mem-edit]');assert.equal(form.querySelector('[data-mem-field="symptom"]').value,'现象\n原行  ');
form.querySelector('[data-mem-field="fix"]').value='新办法\n完整末行  ';await form.fire('submit');assert.deepEqual(mutations[0].body.fields,{fix:'新办法\n完整末行  '});
assert.equal([...LESSON_DECISIONS.pending.values()][0].snapshot.card.symptom,'现象\r\n原行  ');assert.equal([...LESSON_DECISIONS.pending.values()][0].phase,'recorded');
""")

    def test_unknown_request_survives_remount_and_rechecks_server(self):
        self.run_js(r"""
await mount();postHandler=async()=>{throw new Error('响应丢失')};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');const original=JSON.stringify(mutations[0]);
LESSON_DECISIONS.views.clear();LESSON_DECISIONS.pending.clear();LESSON_DECISIONS.identity='';await mount();assert.ok(main.querySelector('[data-lesson-retry]'));
postHandler=async(url,body)=>success(currentSnapshot,body,{replayed:true});await main.querySelector('[data-lesson-retry]').fire('click');assert.equal(JSON.stringify(mutations[1]),original);assert.equal([...LESSON_DECISIONS.pending.values()][0].phase,'recorded');
""")

    def test_saved_receipt_is_not_trusted_without_server_revalidation(self):
        self.run_js(r"""
await mount();await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');assert.equal([...LESSON_DECISIONS.pending.values()][0].phase,'recorded');
LESSON_DECISIONS.views.clear();LESSON_DECISIONS.pending.clear();LESSON_DECISIONS.identity='';await mount();assert.equal([...LESSON_DECISIONS.pending.values()][0].phase,'unknown');assert.ok(main.querySelector('[data-lesson-retry]'));assert.equal(mutations.length,1);
""")

    def test_untrusted_saved_target_does_not_write_another_resource(self):
        self.run_js(r"""
await mount();postHandler=async()=>{throw new Error('未知')};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');const saved=JSON.parse(sessionValues.get(lessonStorageName()));saved.pending[0][1].path='/api/projects/STD/lessons/L1';sessionValues.set(lessonStorageName(),JSON.stringify(saved));
LESSON_DECISIONS.views.clear();LESSON_DECISIONS.pending.clear();LESSON_DECISIONS.identity='';await mount();await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');assert.equal(mutations.length,1);assert.ok(LESSON_DECISIONS.storageError);
""")

    def test_noop_empty_field_receipt_keeps_original_missing_field(self):
        self.run_js(r"""
delete currentSnapshot.card.cause;currentSnapshot.content_digest=hashJSON({schema:'lesson_content_v1',content:rawContent(currentSnapshot.card)});memoryResponse=memoryData({lessons:[listed(currentSnapshot)]});await mount();
postHandler=async(url,body)=>{const r=success(currentSnapshot,body);r.receipt.reviewed_content=rawContent(currentSnapshot.card);r.receipt.reviewed_content_digest=currentSnapshot.content_digest;r.receipt.changed=false;r.receipt.decision_token=currentSnapshot.expected_token;r.current=currentSnapshot;return r};
await lessonDecisionSubmit([...LESSON_DECISIONS.views][0],'edit',{cause:''});assert.equal([...LESSON_DECISIONS.pending.values()][0].phase,'recorded');assert.equal(Object.hasOwn([...LESSON_DECISIONS.pending.values()][0].result.receipt.reviewed_content,'cause'),false);
""")

    def test_request_conflict_and_history_error_cannot_generate_new_intent(self):
        self.run_js(r"""
for(const code of ['request_id_conflict','lesson_history_unreadable']){lessonDecisionsClear();await mount();postHandler=async()=>{throw Object.assign(new Error(code),{status:409,code})};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');assert.ok(main.querySelector('[data-lesson-retry]'));assert.equal(main.querySelector('[data-lesson-read]'),null);assert.equal(main.querySelector('[data-mem-act="lesson_confirm"]').disabled,true)}
""")

    def test_reopen_storage_failure_preserves_original_request_and_snapshot(self):
        self.run_js(r"""
await mount();postHandler=async()=>{throw Object.assign(new Error('版本变化'),{status:409,code:'lesson_changed'})};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');
const pending=[...LESSON_DECISIONS.pending.values()][0],view=[...LESSON_DECISIONS.views][0],original=view.snapshot;currentSnapshot=snapshot({fix:'新版'},'c'.repeat(64));await main.querySelector('[data-lesson-read]').fire('click');
sessionStorage.setItem=()=>{throw new Error('磁盘不可写')};await main.querySelector('[data-lesson-reopen]').fire('click');assert.equal(LESSON_DECISIONS.pending.get(view.key),pending);assert.equal(view.snapshot,original);assert.equal(mutations.length,1);assert.ok($('#memNotice').textContent.includes('尚未重新打开'));
""")

    def test_same_version_draft_restores_but_new_version_never_inherits_it(self):
        self.run_js(r"""
await mount();const edit=main.querySelector('[data-mem-edit]'),field=edit.querySelector('[data-mem-field="fix"]');field.value='原版本的未提交修改';field.fire('input');await mount();assert.equal(main.querySelector('[data-mem-edit]').querySelector('[data-mem-field="fix"]').value,'原版本的未提交修改');
currentSnapshot=snapshot({fix:'别人保存的新版'},'c'.repeat(64));memoryResponse=memoryData({lessons:[listed(currentSnapshot)]});await mount();assert.equal(main.querySelector('[data-mem-edit]').querySelector('[data-mem-field="fix"]').value,'别人保存的新版');assert.ok(main.textContent.includes('不会自动套用'));assert.ok(main.textContent.includes('原版本的未提交修改'));assert.equal(mutations.length,0);
""")

    def test_confirm_binds_actual_dirty_fields_and_review_keeps_real_line_breaks(self):
        self.run_js(r"""
await mount();const view=main.querySelector('[data-lesson-full]');assert.ok(view.textContent.includes('现象\r\n原行  '));
main.querySelector('[data-mem-edit]').querySelector('[data-mem-field="fix"]').value='本人修订后的办法';await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');assert.deepEqual(mutations[0].body.fields,{fix:'本人修订后的办法'});assert.equal([...LESSON_DECISIONS.pending.values()][0].result.receipt.reviewed_content.fix,'本人修订后的办法');
""")

    def test_server_identity_change_clears_original_request_instead_of_retrying_as_new_user(self):
        self.run_js(r"""
await mount();postHandler=async()=>{throw Object.assign(new Error('当前会话已是另一人'),{status:409,code:'lesson_identity_changed'})};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');
assert.equal(LESSON_DECISIONS.pending.size,0);assert.equal(LESSON_DECISIONS.drafts.size,0);assert.equal(sessionValues.size,0);assert.equal(main.querySelector('[data-lesson-retry]'),null);assert.ok($('#memNotice').textContent.includes('登录身份已变化'));assert.equal(mutations[0].headers['X-Webuddy-Lesson-Actor'],'alice');
""")

    def test_readonly_role_cannot_submit_even_by_invoking_handler(self):
        self.run_js(r"""
S.meta.access={role:'viewer'};globalThis.accessCanWrite=()=>false;await mount();const confirm=main.querySelector('[data-mem-act="lesson_confirm"]');assert.equal(confirm.disabled,true);await confirm.fire('click');await lessonDecisionSubmit([...LESSON_DECISIONS.views][0],'confirm');assert.equal(mutations.length,0);
""")

    def test_late_reread_cannot_expose_discard_button_for_unknown_post(self):
        self.run_js(r"""
await mount();const reading=later();getHandler=()=>reading.promise;const read=main.querySelector('[data-lesson-read]').fire('click');postHandler=async()=>{throw new Error('响应丢失')};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');
reading.resolve(snapshot({fix:'后来内容'},'c'.repeat(64)));await read;assert.equal(main.querySelector('[data-lesson-reopen]'),null);assert.ok(main.querySelector('[data-lesson-retry]'));assert.equal([...LESSON_DECISIONS.pending.values()][0].phase,'unknown');
""")

    def test_existing_reread_cannot_discard_a_later_unknown_intent(self):
        self.run_js(r"""
await mount();await main.querySelector('[data-lesson-read]').fire('click');const stale=main.querySelector('[data-lesson-reopen]');postHandler=async()=>{throw new Error('未收到回执')};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');await stale.fire('click');
assert.equal([...LESSON_DECISIONS.pending.values()][0].phase,'unknown');assert.equal(main.querySelector('[data-lesson-reopen]'),null);assert.equal(mutations.length,1);
""")

    def test_legacy_session_expiry_also_clears_private_lesson_state(self):
        self.run_js(r"""
ACCESS.base='';await mount();postHandler=async()=>{throw Object.assign(new Error('登录过期'),{status:401})};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');assert.equal(LESSON_DECISIONS.pending.size,0);assert.equal(sessionValues.size,0);assert.equal(main.querySelector('[data-lesson-retry]'),null);
""")

    def test_legacy_account_change_uses_separate_storage_and_keeps_original_retry(self):
        self.run_js(r"""
ACCESS.base='';await mount();postHandler=async()=>{throw new Error('响应未知')};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');const original=JSON.stringify(mutations[0]),aliceStorage=lessonStorageName();
lessonDecisionsClear(false);S.meta.user='bob';await mount();assert.equal(LESSON_DECISIONS.storageError,'');assert.equal(LESSON_DECISIONS.pending.size,0);assert.equal(main.querySelector('[data-mem-act="lesson_confirm"]').disabled,false);assert.notEqual(lessonStorageName(),aliceStorage);assert.ok(sessionValues.has(aliceStorage));
lessonDecisionsClear(false);S.meta.user='alice';await mount();await main.querySelector('[data-lesson-retry]').fire('click');assert.equal(JSON.stringify(mutations[1]),original);
""")

    def test_changed_identity_without_page_reload_mounts_new_context_once(self):
        self.run_js(r"""
ACCESS.base='';await mount();S.meta.user='bob';await mount();const view=[...LESSON_DECISIONS.views][0];assert.equal(lessonDecisionCurrent(view),true);assert.equal(JSON.parse(view.context.identity)[1],'bob');assert.equal(main.querySelector('[data-mem-act="lesson_confirm"]').disabled,false);
""")

    def test_real_ledger_receipt_is_accepted_and_later_retire_is_not_reversed(self):
        from tmh.platform import learn

        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            card = learn.add_lesson(data, {"project": "APP", "title": "真实账本回执", "status": "candidate",
                                          "symptom": "保留\r\n原文  ", "fix": "原办法", "cause": None,
                                          "applicability": "条件\u2028第二行", "source": {"number": 1.0},
                                          "files": [f"full-{i}.py" for i in range(12)]})
            original = learn.lesson_snapshot(data, "APP", card["id"])
            fields = {"fix": "此次人工修订"}
            learn.human_decision(data, "APP", card["id"], "alice", "confirm", original["expected_token"],
                                 "lesson-real-ledger", fields=fields)
            learn.set_status(data, card["id"], "retired", "owner", "后续明确停用")
            replay = learn.human_decision(data, "APP", card["id"], "alice", "confirm", original["expected_token"],
                                         "lesson-real-ledger", fields=fields)
        fixture = json.dumps({"snapshot": original, "result": replay}, ensure_ascii=True)
        self.run_js("const fixture=" + fixture + r""";
currentSnapshot=fixture.snapshot;memoryResponse=memoryData({lessons:[listed(currentSnapshot)]});crypto.randomUUID=()=> 'real-ledger';await mount();
main.querySelector('[data-mem-edit]').querySelector('[data-mem-field="fix"]').value='此次人工修订';postHandler=async()=>{throw new Error('实际结果未收到')};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');
postHandler=async()=>fixture.result;await main.querySelector('[data-lesson-retry]').fire('click');const p=[...LESSON_DECISIONS.pending.values()][0];assert.equal(p.phase,'recorded');assert.equal(p.result.replayed,true);assert.equal(p.result.superseded,true);assert.equal(p.result.current.card.status,'retired');assert.equal(p.result.receipt.reviewed_content.symptom,'保留\r\n原文  ');
""")
