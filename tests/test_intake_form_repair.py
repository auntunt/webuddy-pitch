"""Run shipped intake handlers with controlled file reads and network responses."""
import shutil
import subprocess
import unittest
from tests.test_ui_library import HARNESS
from tmh.platform.ui import JS
from tmh.platform.ui_drafts import DRAFT_JS
from tmh.platform.ui_work import WORK_JS


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class IntakeFormRepairTests(unittest.TestCase):
    def run_js(self, checks):
        source=JS[JS.index('const IKIND='):JS.index('// ---------- the change itself, running:')]
        draft=DRAFT_JS[:DRAFT_JS.index('function commentDraftActor')]
        harness=HARNESS+r'''
const window={};let timerId=0;const timers=new Map();
const setTimeout=(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId};const clearTimeout=id=>timers.delete(id);
const nextTimer=async()=>{const [id,t]=[...timers][0];timers.delete(id);await t.fn()};
const notices=[],toast=t=>notices.push(t);const clip=(s,n)=>String(s).slice(0,n);
Element.prototype.appendChild=function(e){e.parent=this;this.children.push(e);return e};
Element.prototype.insertAdjacentElement=function(_,e){return this.parent.appendChild(e)};
Element.prototype.remove=function(){this.parent.children=this.parent.children.filter(x=>x!==this);this.parent=null};
document.createElement=tag=>new Element(tag);
const readers=[];class FileReader{constructor(){readers.push(this)}readAsDataURL(f){this.file=f}finish(){this.result='data:text/plain;base64,'+Buffer.from(this.file.name).toString('base64');this.onload()}}
S.meta={user:'alice',login:true,data_dir:'/synthetic',access:{tenant:{id:1}}};
const accessCanExecute=()=>false;const talkOpen=id=>requests.push('reopen:'+id);
const task=(id,state='understanding')=>({id,project:'APP',text:'原始需求',state,items:[],attachments:[],tickets:[]});
const addFiles=(...names)=>$('#inF').onchange({target:{files:names.map(name=>({name,type:'text/plain'}))}});
const removeFile=id=>$('#inFiles').querySelector('[data-file="'+id+'"]').onclick();
'''
        r=subprocess.run(['node','-'],input=harness+draft+source+'\n(async()=>{'+checks+'\n})().catch(e=>{console.error(e);process.exitCode=1})',text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_delete_by_identity_and_exact_payload(self):
        self.run_js(r'''
intakeModal('APP','需求');addFiles('A','B','C');readers.forEach(x=>x.finish());
removeFile(1);removeFile(2);postHandler=()=>task('one');await $('#inGo').onclick();
assert.deepEqual(mutations[0].body.attachments.map(x=>x.name),['C']);
assert.equal(mutations[0].body.attachments[0].data,'data:text/plain;base64,Qw==');
''')

    def test_pending_failure_duplicate_and_late_deleted_file(self):
        self.run_js(r'''
intakeModal('APP','需求');addFiles('same','same');assert.equal($('#inGo').disabled,true);
await $('#inGo').onclick();assert.equal(mutations.length,0);
removeFile(1);readers[0].finish();assert.equal($('#inFiles').querySelectorAll('[data-file]').length,1);
readers[1].onerror();assert.match($('#inFiles').textContent,/读取失败/);assert.equal($('#inGo').disabled,true);
removeFile(2);addFiles('same');readers[2].finish();assert.equal($('#inGo').disabled,false);
postHandler=()=>task('one');await $('#inGo').onclick();assert.equal(mutations[0].body.attachments.length,1);
''')

    def test_paste_and_drop_share_file_state(self):
        self.run_js(r'''
intakeModal('APP','需求');const input=$('#inT');
input.listeners.paste[0]({clipboardData:{files:[{name:'截图.png',type:'image/png'}]}});
input.listeners.drop[0]({dataTransfer:{files:[{name:'B',type:'text/plain'}]},preventDefault(){}});
readers.forEach(x=>x.finish());removeFile(1);postHandler=()=>task('one');await $('#inGo').onclick();
assert.deepEqual(mutations[0].body.attachments.map(x=>x.name),['B']);
''')

    def test_poll_recovers_after_failure_and_caps_backoff(self):
        self.run_js(r'''
intakeModal('APP','需求');intakePaint(task('one'));let reads=0;
getHandler=()=>{reads++;if(reads<7)throw Error('offline');return task('one','confirmed')};
for(let n=0;n<6;n++){await nextTimer();assert.match($('#inConnection').textContent,/暂时断连/);assert.ok([...timers.values()][0].ms<=15000)}
await nextTimer();assert.equal(reads,7);assert.equal(mutations.length,0);assert.equal(timers.size,0);
assert.equal(intakeDraftFor('APP').taskId,'');
''')

    def test_denied_stops_and_old_response_does_not_replace_new_task(self):
        self.run_js(r'''
intakeModal('APP','需求');intakePaint(task('one'));getHandler=()=>{throw Object.assign(Error('权限失效'),{status:403})};
await nextTimer();assert.equal(timers.size,0);assert.match($('#inConnection').textContent,/权限失效/);
intakePaint(task('one'));const pending=later();getHandler=()=>pending.promise;const reading=nextTimer();
intakeModal('APP','第二条');intakePaint(task('two'));const second=$('#inBox');
pending.resolve(task('one','confirmed'));await reading;assert.equal($('#inBox'),second);assert.equal(second.taskId,'two');
''')

    def test_cancel_failure_keeps_task_and_closed_view_ignores_response(self):
        self.run_js(r'''
intakeModal('APP','需求');intakePaint(task('one'));postHandler=()=>{throw Error('取消拒绝')};
await $('#inNo').onclick();assert.equal(overlay.hidden,false);assert.match($('#inConnection').textContent,/取消未完成/);
const pending=later();getHandler=()=>pending.promise;const reading=nextTimer();closeModal();
pending.resolve(task('one','confirmed'));await reading;assert.equal(intakeDraftFor('APP').taskId,'one');
assert.equal($('#inBox').taskId,'one');
''')

    def test_same_session_restore_and_identity_scope(self):
        self.run_js(r'''
intakeModal('APP','长文本');$('#inT').value='更新后的完整文本';$('#inT').oninput();closeModal();
intakeModal('APP','');const button=$('#inBox').children[0];button.onclick();assert.equal($('#inT').value,'更新后的完整文本');
S.meta.user='bob';assert.equal(intakeDraftFor('APP').text,'');
intakeDraftFor('APP').text='bob内容';assert.equal(intakeDraftFor('STD').text,'');
S.meta.access.tenant.id=2;assert.equal(intakeDraftFor('APP').text,'');
''')

    def test_shortcut_clears_only_after_successful_handoff(self):
        source=WORK_JS[WORK_JS.index('async function sayOpen'):WORK_JS.index('async function pasteModal')]
        self.run_js(source+r'''
main.innerHTML='<input id="sayIn">';$('#sayIn').value='重要原话';let fail=true;
const pasteModal=async()=>{if(fail)throw Error('打开失败');return true};
await sayOpen();assert.equal($('#sayIn').value,'重要原话');fail=false;await sayOpen();assert.equal($('#sayIn').value,'');
''')
