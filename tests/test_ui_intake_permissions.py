"""Exercise actual intake form permission and client loading branches in Node."""
import shutil
import subprocess
import unittest

from tests.test_ui_library import HARNESS
from tmh.platform.ui_work import WORK_JS
from tmh.platform.ui import JS
from tmh.platform.ui_access import ACCESS_BOOT_JS
from tmh.platform.ui_drafts import DRAFT_JS


@unittest.skipUnless(shutil.which('node'), 'Node is required for form checks')
class IntakePermissionTests(unittest.TestCase):
    def run_js(self, checks):
        source = WORK_JS[WORK_JS.index('async function pasteModal('):WORK_JS.index('// the existing requirement conversation')]
        capabilities = ACCESS_BOOT_JS.split('function accessProjectRole', 1)[1].split('function accessProjectNote', 1)[0]
        drafts = DRAFT_JS.split('function commentDraftActor', 1)[0]
        harness = HARNESS + drafts + r'''
document.createElement=tag=>new Element(tag);
Object.defineProperty(Element.prototype,'parentElement',{get(){return this.parent}});
Element.prototype.insertAdjacentElement=function(where,node){assert.equal(where,'afterend');const index=this.parent.children.indexOf(this);node.parent=this.parent;this.parent.children.splice(index+1,0,node);return node};
Element.prototype.remove=function(){const index=this.parent.children.indexOf(this);this.parent.children.splice(index,1);this.parent=null};
const notices=[];const toast=t=>notices.push(t),ls={get:()=>'',set(){}};
const isCross=()=>true,pk0=()=>S.proj;
const accessCanExecute=p=>!S.meta.access||S.meta.access.capabilities.execution&&accessCanWrite(p);
const newTicket=()=>{};const intakeOpen=()=>{};
S.projects=[{id:1,key:'APP',name:'项目A'},{id:2,key:'STD',name:'项目B'}];S.scope='*';
S.meta={access:{role:'member',capabilities:{write:true,execution:false},project_grants:[{project_id:1,role:'contributor'},{project_id:2,role:'viewer'}]}};
getHandler=url=>url.endsWith('/systems')?{systems:[]}: {clients:[]};
'''
        result = subprocess.run(['node', '-'], input=harness + '\nfunction accessProjectRole' + capabilities + source + '\n(async()=>{' + checks + '\n})().catch(e=>{console.error(e);process.exitCode=1});', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_member_records_without_client_or_execution_and_retry_keeps_label(self):
        self.run_js(r'''
await pasteModal('客户原话');
assert.equal(requests.includes('/api/clients'),false);
assert.equal($('#pmC').disabled,true);assert.equal($('#pmC').value,'');
assert.equal($('#pmGo').textContent,'记录并归档');
postHandler=()=>{throw Error('offline')};await $('#pmGo').onclick();
assert.equal(mutations[0].body.model,false);assert.equal(mutations[0].body.text,'客户原话');
assert.equal(mutations[0].body.client_name,undefined);
assert.equal($('#pmGo').textContent,'记录并归档');assert.equal($('#pmGo').disabled,false);
$('#pmP').value='STD';$('#pmP').fire('change');
assert.equal($('#pmGo').disabled,true);assert.equal($('#pmOld').disabled,true);
assert.equal($('#pmGo').textContent,'仅可查看');
''')

    def test_readonly_never_opens_write_form(self):
        self.run_js(r'''
S.meta.access.capabilities.write=false;
assert.equal(await pasteModal('原话'),false);assert.equal(overlay.hidden,true);
assert.equal(requests.length,0);assert.match(notices[0],/查看权限/);
''')

    def test_client_failure_is_not_empty_or_new_client(self):
        self.run_js(r'''
S.meta.access.role='admin';
for(const status of [403,503]){
 getHandler=url=>{if(url==='/api/clients')throw Object.assign(Error('failed'),{status});return {systems:[]}};
 await pasteModal('原话');
 assert.equal($('#pmC').disabled,true);assert.equal($('#pmC').value,'');
 assert.ok(!$('#pmC').innerHTML.includes('__new'));
 assert.ok($('#pmClientRetry'));assert.match(body.textContent,status===403?/没有读取客户目录的权限/:/客户目录读取失败/);
}
''')

    def test_same_session_restore_and_project_identity_are_executed(self):
        self.run_js(r'''
assert.equal(await pasteModal('长文本需求'),true);
$('#pmT').value='修改后的长文本需求';$('#pmT').fire('input');closeModal();
await pasteModal('');assert.equal($('#pmRestore').hidden,false);
$('#pmRestore').onclick();assert.equal($('#pmT').value,'修改后的长文本需求');
$('#pmP').value='STD';$('#pmP').fire('change');
assert.equal($('#pmT').value,'');assert.equal($('#pmRestore').hidden,true);
closeModal();S.user='someone-else';await pasteModal('');
assert.equal($('#pmRestore').hidden,true);
''')

    def test_system_load_keeps_current_project_and_reports_failure(self):
        self.run_js(r'''
const old=later();getHandler=url=>url.includes('/APP/')?old.promise:{systems:[{id:22,name:'B系统'}]};
await pasteModal('原文');$('#pmP').value='STD';$('#pmP').fire('change');await Promise.resolve();
assert.match($('#pmS').innerHTML,/B系统/);
old.resolve({systems:[{id:11,name:'过期A系统'}]});await Promise.resolve();await Promise.resolve();
assert.ok(!$('#pmS').innerHTML.includes('过期A系统'));
getHandler=()=>{throw Error('系统请求失败')};$('#pmP').value='APP';$('#pmP').fire('change');await Promise.resolve();
assert.match($('#pmS').innerHTML,/系统读取失败/);assert.equal($('#pmS').disabled,true);assert.equal($('#pmS').value,'');
''')

    def test_filtered_empty_tickets_have_clear_action_and_stale_results_do_not_paint(self):
        source = JS.split('async function vTickets(){', 1)[1].split('function boardHtml', 1)[0]
        self.run_js('async function vTickets(){' + source + r'''
const scopeQ=()=>S.scope,sessionStorage={value:'{"q":"missing"}',getItem(){return this.value},removeItem(){this.value='{}'},setItem(k,v){this.value=v}};
const ticketTable=()=>'<table></table>';S.meta.statuses=[];
getHandler=()=>[];await vTickets();
assert.match(main.textContent,/没有匹配的工单/);assert.ok($('#clearTicketFilters'));
await $('#clearTicketFilters').onclick();await Promise.resolve();
assert.equal(sessionStorage.value,'{}');assert.match(main.textContent,/当前范围还没有工单/);
const response=later();getHandler=()=>response.promise;const pending=vTickets();
S.scope='STD';main.innerHTML='new scope';response.resolve([]);await pending;
assert.equal(main.textContent,'new scope');
''')

    def test_scope_and_empty_state_do_not_fall_back_to_recent_project(self):
        scope = JS.split('const scopeQ=', 1)[1].split('async function loadPoints', 1)[0]
        empty = JS.split('function firstRun(L)', 1)[1].split('// What waits for me', 1)[0]
        self.run_js('const scopeQ=' + scope + '\nfunction firstRun(L)' + empty + r'''
assert.equal(boardQ(),'*');
S.scope='STD';assert.equal(boardQ(),'STD');
assert.match(firstRun({}),/当前项目还没有工单/);
assert.ok(!firstRun({}).includes('新建工单'));
S.scope='*';assert.match(firstRun({}),/当前授权项目还没有工单/);
''')

    def test_late_response_cannot_overwrite_another_project_draft(self):
        self.run_js(r'''
S.meta.access.role='admin';await pasteModal('A原文');const pending=later();postHandler=()=>pending.promise;
const sending=$('#pmGo').onclick();$('#pmP').value='STD';$('#pmP').fire('change');
$('#pmT').value='B新原文';$('#pmT').fire('input');closeModal();
pending.resolve({id:'A-task',project:'APP',client:null,system:null});await sending;
assert.ok(S.intakeDraft.scope.includes('STD'));assert.equal(S.intakeDraft.text,'B新原文');assert.equal(S.intakeDraft.taskId,'');
''')
