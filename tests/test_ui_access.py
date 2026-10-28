"""Execute tenant boundary and administration handlers from the shipped UI."""
import shutil
import subprocess
import unittest

from test_ui_library import HARNESS
from tmh.platform.ui import JS, page
from tmh.platform.ui_access import ACCESS_BOOT_JS, ACCESS_JS
from tmh.platform.ui_delivery import DELIVERY_JS
from tmh.platform.ui_team import TEAM_JS


SETUP = r"""
const nativeStore=()=>{const values=new Map();return{values,get length(){return values.size},key:i=>[...values.keys()][i]??null,getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k)}};
globalThis.localStorage=nativeStore();globalThis.sessionStorage=nativeStore();globalThis.crypto=require('node:crypto').webcrypto;
const window={addEventListener(){},_inPoll:null};document.hidden=false;document.addEventListener=()=>{};document.body=main;
const originalQuery=Element.prototype.querySelector;
Element.prototype.setAttribute=function(k,v){this.attrs[k]=String(v)};
Element.prototype.querySelector=function(s){if(s.startsWith('.'))return this.all().find(x=>(x.attrs.class||'').split(' ').includes(s.slice(1)))||null;return originalQuery.call(this,s)};
Object.defineProperty(Element.prototype,'tagName',{get(){return this.tag.toUpperCase()}});
document.querySelector=s=>s==='#main'?main:main.querySelector(s);document.querySelectorAll=s=>main.querySelectorAll(s);const notices=[];const toast=t=>notices.push(t);const stopPolls=()=>{S.polls=[]};
const assigned=[];location.assign=url=>assigned.push(url);location.pathname='/';
"""

UI_FIXTURE = r"""
location.hash='#/access';S.meta={login:true,user:'alice',access:{can_manage:true,tenant:{id:'alpha',name:'甲租户'},user:'alice',tenants:[{id:'alpha',name:'甲租户',url:'/t/alpha/'},{id:'beta',name:'乙租户',url:'/t/beta/'}]}};
const accessData=(extra={})=>({revision:4,viewer:'alice',current_tenant:{id:'alpha',name:'甲租户',status:'active'},members:[{id:'alice',name:'Alice',role:'admin',active:true,actions:{member_set:true,member_remove:false}},{id:'bob',name:'Bob',role:'member',active:true,actions:{member_set:true,member_remove:true}}],accounts:[{id:'alice',name:'Alice',active:true},{id:'bob',name:'Bob',active:true}],projects:[{id:'1',key:'APP',name:'项目'}],project_grants:[{project_id:'1',user:'bob',role:'contributor'}],permissions:{member_manage:true,project_manage:true,tenant_manage:true,tenant_create:false,account_manage:false},roles:{tenant:['admin','member','viewer'],project:['manager','contributor','viewer']},audit:[],...extra});
let directory=accessData();getHandler=()=>directory;postHandler=(path,body)=>({revision:5,operation:body.action,tenant_id:'alpha',changed:true,replayed:false,request_id:body.request_id});
const choose=async action=>{await vAccess();$('#accessAction').value=action;await $('#accessAction').fire('change')};
const change=(field,value)=>{const node=main.querySelector('[data-access-field="'+field+'"]');node.value=value;node.fire('input');return node};
"""


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for shipped access UI checks')
class AccessUiTest(unittest.TestCase):
    def run_js(self, checks, core=False):
        harness = HARNESS.split('const requests=[]', 1)[0] if core else HARNESS
        api = JS.split('async function api(m,p,b,extraHeaders={}){', 1)[1].split('function toast(', 1)[0]
        api = 'async function api(m,p,b,extraHeaders={}){' + api
        source = harness + SETUP + ACCESS_BOOT_JS
        if core:
            source += "\nconst navigator={onLine:true};\n" + api
        else:
            source += ACCESS_JS + DELIVERY_JS + TEAM_JS + UI_FIXTURE + 'async function boot(){' + JS.split('async function boot(){', 1)[1].split('async function loadProjects(){', 1)[0]
        result = subprocess.run([shutil.which('node'), '-'], input=source + '\n(async()=>{\n' + checks + '\n})().catch(error=>{console.error(error);process.exitCode=1});', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_page_wires_access_and_full_script_parses(self):
        html = page()
        self.assertIn('access:vAccess', html)
        self.assertIn('id="tenantSel"', html)
        self.assertIn('X-Webuddy-Context', html)
        source = html.split('<script>', 1)[1].split('</script>', 1)[0]
        result = subprocess.run([shutil.which('node'), '--check'], input=source, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_partial_diagnostic_button_uses_actual_ticket_key(self):
        self.run_js(r"""
const c={current:true,partial_diagnostic:null};
assert.match(teamDiagnosticPanel({ticket:{key:'JB-7'},candidate:c}),/检查当前候选/);
assert.equal(teamDiagnosticPanel({ticket:{key:'RW-7'},candidate:c}),'');
const stale={...c,current:false,partial_diagnostic:{actor:'alice',updated:'now',commit:'a',vue_files:1,templates_checked:1,bad:[],skipped:[]}};
assert.match(teamDiagnosticPanel({ticket:{key:'JB-7'},candidate:stale}),/历史结果：候选依据已变化/);
""")

    def test_team_workspace_uses_only_visible_projects_for_members(self):
        self.run_js(r"""
globalThis.scopeQ=()=>S.scope;globalThis.ls={set(){}};location.hash='#/team/team';
S.scope='*';S.proj='HIDDEN';S.meta.access.role='member';
let projects=[{key:'JB',name:'开发项目'},{key:'PPT',name:'演示项目'}];
const empty={viewer:'alice',members:[],items:[],counts:{mine:0,team:0,review:0,unassigned:0},boundary:'',has_more:false};
getHandler=url=>url==='/api/projects'?projects:empty;
await vTeam('team');assert.equal(S.scope,'JB');assert.equal(S.proj,'JB');
assert.deepEqual(requests,['/api/projects','/api/team?view=team&project=JB']);
assert.equal($('#team-project').value,'JB');assert.ok(!$('#team-project').textContent.includes('所有项目'));
$('#team-project').value='PPT';await $('#team-project').fire('change');await new Promise(setImmediate);
assert.equal(S.scope,'PPT');assert.ok(requests.includes('/api/team?view=team&project=PPT'));
projects=[];requests.length=0;await vTeam('team');assert.deepEqual(requests,['/api/projects']);assert.match(main.textContent,/尚未获得项目访问权限/);
projects=[{key:'JB',name:'开发项目'}];S.meta.access.role='admin';S.scope='*';requests.length=0;await vTeam('team');
assert.ok(requests.includes('/api/team?view=team&project=*'));assert.ok($('#team-project').textContent.includes('所有项目'));
""")

    def test_team_ticket_lookup_does_not_wire_departed_page(self):
        self.run_js(r"""
globalThis.scopeQ=()=>S.scope;globalThis.ls={set(){}};location.hash='#/team/team/JB-41';S.scope='*';S.meta.access.role='member';
const pending=later();getHandler=url=>url==='/api/projects'?[{key:'JB',name:'开发项目'}]:url.includes('&ticket=')?pending.promise:{viewer:'alice',members:[],items:[],counts:{},boundary:''};
const loading=vTeam('team','JB-41');await new Promise(setImmediate);location.hash='#/tickets';main.innerHTML='工单列表';pending.resolve({items:[]});await loading;
assert.equal(main.textContent,'工单列表');
""")

    def test_default_paths_storage_and_api_remain_compatible(self):
        self.run_js(r"""
assert.equal(appPath('/api/projects'),'/api/projects');localStorage.setItem('tmh.draft.7','old');assert.equal(ACCESS_RAW_LOCAL.getItem('tmh.draft.7'),'old');
globalThis.fetch=async(path,options)=>{assert.equal(path,'/api/projects');assert.equal(options.headers['X-Webuddy-Context'],undefined);return{ok:true,json:async()=>[{key:'APP'}]}};
assert.deepEqual(await get('/api/projects'),[{key:'APP'}]);
""", core=True)

    def test_context_binds_all_api_calls_and_discards_late_responses(self):
        self.run_js(r"""
ACCESS.base='/t/alpha';accessBind({access:{tenant:{id:'alpha'},context_token:'fixed-alpha',user:'alice'}});let resolve;globalThis.fetch=(path,options)=>{assert.equal(path,'/t/alpha/api/projects');assert.equal(options.headers['X-Webuddy-Context'],'fixed-alpha');return new Promise(r=>resolve=r)};
const request=get('/api/projects');ACCESS.epoch++;resolve({ok:true,json:async()=>[{key:'SECRET'}]});await assert.rejects(request,e=>e.access);assert.equal(ACCESS.inflight.size,0);
assert.equal(appPath('/e/APP-1'),'/t/alpha/e/APP-1');assert.equal(appPath('/p/APP/code.bundle'),'/t/alpha/p/APP/code.bundle');assert.equal(appPath('https://example.com/x'),'https://example.com/x');
""", core=True)

    def test_storage_isolated_by_tenant_and_user_and_legacy_not_read(self):
        self.run_js(r"""
ACCESS_RAW_LOCAL.setItem('tmh.delivery.create','legacy');ACCESS.base='/t/alpha';assert.equal(localStorage.getItem('tmh.delivery.create'),null);
accessBind({access:{tenant:{id:'alpha'},context_token:'a',user:'alice'}});localStorage.setItem('tmh.delivery.create','alice-alpha');
ACCESS.user='bob';assert.equal(localStorage.getItem('tmh.delivery.create'),null);localStorage.setItem('tmh.delivery.create','bob-alpha');ACCESS.user='alice';ACCESS.base='/t/beta';assert.equal(localStorage.getItem('tmh.delivery.create'),null);localStorage.setItem('tmh.delivery.create','alice-beta');ACCESS.base='/t/alpha';assert.equal(localStorage.getItem('tmh.delivery.create'),'alice-alpha');accessClearStorage();assert.equal(localStorage.getItem('tmh.delivery.create'),null);assert.equal(ACCESS_RAW_LOCAL.getItem('tmh.delivery.create'),'legacy');ACCESS.user='bob';assert.equal(localStorage.getItem('tmh.delivery.create'),'bob-alpha');
""", core=True)

    def test_revocation_removes_old_dom_and_cached_data_without_returning_payload(self):
        self.run_js(r"""
ACCESS.base='/t/alpha';accessBind({access:{tenant:{id:'alpha'},context_token:'a',user:'alice'}});localStorage.setItem('tmh.draft.1','secret');main.innerHTML='<article id="secret">private source</article>';
globalThis.fetch=async()=>({ok:false,status:403,json:async()=>({code:'membership_revoked',error:'租户成员已撤销'})});await assert.rejects(get('/api/projects'),e=>e.access&&e.status===403);assert.equal(ACCESS.blocked,true);assert.equal(main.querySelector('#secret'),null);assert.ok(main.textContent.includes('访问权限已变化'));assert.equal(localStorage.getItem('tmh.draft.1'),null);assert.equal(main.querySelector('#accessReload').href,'/');
""", core=True)

    def test_resource_denial_does_not_erase_tenant_and_bootstrap_validates_path(self):
        self.run_js(r"""
ACCESS.base='/t/alpha';assert.throws(()=>accessBind({access:{tenant:{id:'beta'},context_token:'b',user:'alice'}}));accessBind({access:{tenant:{id:'alpha'},context_token:'a',user:'alice'}});main.innerHTML='<article id="current">allowed page</article>';
globalThis.fetch=async()=>({ok:false,status:403,json:async()=>({code:'permission_denied',error:'不能修改此项目'})});await assert.rejects(post('/api/projects/APP',{}),e=>e.status===403&&!e.access);assert.equal(ACCESS.blocked,false);assert.equal(main.querySelector('#current').textContent,'allowed page');
""", core=True)

    def test_renders_real_members_and_full_audit_escaped(self):
        self.run_js(r"""
directory=accessData({audit:[{note:'<script>attack</script>'+ '完整'.repeat(6000)}]});await vAccess();assert.ok(main.textContent.includes('Alice'));assert.ok(main.textContent.includes('完整'.repeat(6000)));assert.ok($('#accessRecords').innerHTML.includes('&lt;script&gt;'));assert.ok(!$('#accessRecords').innerHTML.includes('<script>'));assert.ok(main.textContent.includes('项目协作者'));
""")

    def test_readonly_permissions_prevent_mutations(self):
        self.run_js(r"""
directory=accessData({permissions:{},accounts:[]});await vAccess();assert.equal($('#accessSubmit').disabled,true);await submit('#accessForm');assert.equal(mutations.length,0);assert.ok(main.textContent.includes('当前身份不能管理租户成员'));assert.ok(!main.textContent.includes('重设密码'));
""")

    def test_member_request_is_revision_bound_and_double_submit_is_single(self):
        self.run_js(r"""
await choose('member_set');change('user','bob');change('role','viewer');const waiting=later();postHandler=()=>waiting.promise;const first=submit('#accessForm');await submit('#accessForm');assert.equal(mutations.length,1);const b=mutations[0].body;assert.equal(b.tenant,'alpha');assert.equal(b.revision,4);assert.equal(b.action,'member_set');assert.equal(b.user,'bob');assert.equal(b.role,'viewer');assert.ok(b.request_id);directory=accessData({revision:5});waiting.resolve({revision:5,operation:b.action,tenant_id:'alpha',changed:true,request_id:b.request_id});await first;assert.equal(ACCESS.view.pending,null);assert.equal(ACCESS.view.data.revision,5);
""")

    def test_refresh_preserves_input_focus_and_requires_rebind_after_conflict(self):
        self.run_js(r"""
await choose('tenant_rename');const field=change('name','完整的新租户名');field.focus();field.selectionStart=3;directory=accessData({revision:5});await $('#accessRefresh').fire('click');assert.equal(main.querySelector('[data-access-field="name"]'),field);assert.equal(field.value,'完整的新租户名');assert.equal(document.activeElement,field);assert.equal(field.selectionStart,3);assert.equal($('#accessSubmit').disabled,true);await submit('#accessForm');assert.equal(mutations.length,0);await $('#accessRebind').fire('click');assert.equal($('#accessSubmit').disabled,false);postHandler=()=>{throw Object.assign(Error('revision conflict'),{status:409})};await submit('#accessForm');assert.equal(field.value,'完整的新租户名');assert.equal(ACCESS.view.pending,null);
""")

    def test_uncertain_request_retries_original_id_and_payload(self):
        self.run_js(r"""
await choose('project_grant');change('project_id','1');change('user','bob');change('role','viewer');postHandler=()=>{throw Object.assign(Error('timeout'),{status:504})};await submit('#accessForm');const original=JSON.stringify(mutations[0].body);assert.ok(ACCESS.view.pending);assert.equal(main.querySelector('[data-access-field="user"]').disabled,true);await $('#accessRefresh').fire('click');await $('#accessRetry').fire('click');assert.equal(mutations.length,2);assert.equal(JSON.stringify(mutations[1].body),original);
""")

    def test_malformed_success_does_not_clear_input_or_pending(self):
        self.run_js(r"""
await choose('tenant_rename');change('name','原名完整保留');postHandler=()=>({ok:true});await submit('#accessForm');assert.ok(ACCESS.view.pending);assert.equal(main.querySelector('[data-access-field="name"]').value,'原名完整保留');
""")

    def test_old_read_cannot_replace_new_route(self):
        self.run_js(r"""
const waiting=later();getHandler=()=>waiting.promise;const open=vAccess();location.hash='#/workspace';main.innerHTML='<div id="newPage">工作台</div>';waiting.resolve(accessData());await open;assert.equal($('#newPage').textContent,'工作台');
""")

    def test_unauthorized_management_route_does_not_fetch_directory(self):
        self.run_js(r"""
S.meta.access.can_manage=false;await vAccess();assert.equal(requests.length,0);assert.ok(main.textContent.includes('没有管理权限'));assert.equal($('#accessForm'),null);
""")

    def test_individual_member_prohibition_blocks_manual_submission(self):
        self.run_js(r"""
await choose('member_remove');change('user','alice');assert.equal($('#accessSubmit').disabled,true);await submit('#accessForm');assert.equal(mutations.length,0);assert.ok($('#accessBinding').textContent.includes('禁止调整'));
""")

    def test_member_or_project_removed_during_refresh_stays_selected_but_cannot_submit(self):
        self.run_js(r"""
await choose('project_grant');change('user','bob');change('project_id','1');change('role','contributor');directory=accessData({members:[accessData().members[0]],projects:[]});await $('#accessRefresh').fire('click');assert.equal(main.querySelector('[data-access-field="user"]').value,'bob');assert.equal(main.querySelector('[data-access-field="project_id"]').value,'1');assert.equal($('#accessSubmit').disabled,true);await submit('#accessForm');assert.equal(mutations.length,0);
""")

    def test_pending_request_completion_updates_remounted_management_form(self):
        self.run_js(r"""
await choose('tenant_rename');change('name','已保存的新名');const waiting=later();postHandler=()=>waiting.promise;const sent=submit('#accessForm');const original=mutations[0].body;location.hash='#/workspace';main.innerHTML='<p>工作台</p>';location.hash='#/access';await vAccess();assert.ok(ACCESS.view.pending);directory=accessData({revision:5});waiting.resolve({revision:5,operation:original.action,tenant_id:'alpha',changed:true,request_id:original.request_id});await sent;assert.equal(ACCESS.view.pending,null);assert.equal(ACCESS.view.data.revision,5);assert.equal($('#accessSubmit').disabled,false);
""")

    def test_pending_failure_remount_keeps_original_retry(self):
        self.run_js(r"""
await choose('tenant_rename');change('name','未确认的新名');const waiting=later();postHandler=()=>waiting.promise;const sent=submit('#accessForm');const original=JSON.stringify(mutations[0].body);location.hash='#/workspace';main.innerHTML='<p>工作台</p>';location.hash='#/access';await vAccess();waiting.reject(Error('connection closed'));await sent;assert.ok(ACCESS.view.pending);assert.equal($('#accessRetry').disabled,false);postHandler=()=>{throw Error('offline')};await $('#accessRetry').fire('click');assert.equal(JSON.stringify(mutations[1].body),original);
""")

    def test_success_followed_by_refresh_failure_blocks_duplicate_stale_action(self):
        self.run_js(r"""
await choose('tenant_rename');change('name','登记成功但刷新失败');postHandler=(url,body)=>{getHandler=()=>{throw Error('refresh failed')};return{revision:5,operation:body.action,request_id:body.request_id,tenant_id:'alpha',changed:true}};await submit('#accessForm');assert.equal(ACCESS.view.pending,null);assert.equal(ACCESS.view.needsRefresh,true);assert.equal($('#accessSubmit').disabled,true);await submit('#accessForm');assert.equal(mutations.length,1);getHandler=()=>accessData({revision:5});await $('#accessRefresh').fire('click');assert.equal(ACCESS.view.needsRefresh,false);
""")

    def test_wrong_receipt_request_or_tenant_is_unknown_and_never_rebound(self):
        self.run_js(r"""
await choose('tenant_rename');change('name','完整新名');postHandler=(url,body)=>({revision:5,operation:body.action,request_id:'different',tenant_id:'alpha',changed:true});await submit('#accessForm');assert.ok(ACCESS.view.pending);const original=mutations[0].body;postHandler=(url,body)=>({revision:5,operation:body.action,request_id:body.request_id,tenant_id:'beta',changed:true});await $('#accessRetry').fire('click');assert.ok(ACCESS.view.pending);assert.deepEqual(mutations[1].body,original);
""")

    def test_only_allowed_tenant_url_can_be_navigated_and_pending_prevents_switch(self):
        self.run_js(r"""
ACCESS.base='/t/alpha';accessBind({access:{tenant:{id:'alpha'},user:'alice',context_token:'a'}});assert.equal(accessTenantUrl('beta'),'/t/beta/');S.meta.access.tenants.push({id:'bad',url:'https://example.com/steal'});accessSwitch('bad');assert.equal(assigned.length,0);await choose('tenant_rename');change('name','新名');postHandler=()=>{throw Error('offline')};await submit('#accessForm');accessSwitch('beta');assert.equal(assigned.length,0);assert.equal(ACCESS.blocked,false);
""")

    def test_context_change_and_session_expiry_show_correct_safe_destination(self):
        self.run_js(r"""
ACCESS.base='/t/alpha';accessBind({access:{tenant:{id:'alpha'},context_token:'a',user:'alice'}});globalThis.fetch=async()=>({ok:false,status:409,json:async()=>({code:'context_changed',error:'权限版本变化'})});await assert.rejects(get('/api/projects'),e=>e.access);assert.equal(main.querySelector('#accessReload').href,'/t/alpha/');
""", core=True)
        self.run_js(r"""
ACCESS.base='/t/alpha';accessBind({access:{tenant:{id:'alpha'},context_token:'a',user:'alice'}});globalThis.fetch=async()=>({ok:false,status:401,json:async()=>({code:'session_invalid'})});await assert.rejects(get('/api/projects'),e=>e.access);assert.equal(main.querySelector('#accessReload').href,'/login?next=%2Ft%2Falpha%2F');assert.equal(main.querySelector('#accessReload').textContent,'重新登录');
""", core=True)

    def test_management_target_is_independent_of_open_workspace_and_uses_numeric_project_id(self):
        self.run_js(r"""
directory=accessData({tenants:[{id:'alpha',name:'甲',status:'active'},{id:'beta',name:'乙',status:'disabled'}]});await vAccess();getHandler=url=>{assert.equal(url,'/api/access?tenant=beta');return accessData({current_tenant:{id:'beta',name:'乙',status:'disabled'},tenants:directory.tenants})};$('#accessTarget').value='beta';await $('#accessTarget').fire('change');assert.equal(S.meta.access.tenant.id,'alpha');assert.equal(ACCESS.view.target,'beta');assert.ok($('#accessTargetInfo').textContent.includes('乙'));$('#accessAction').value='project_grant';await $('#accessAction').fire('change');change('user','bob');change('project_id','1');change('role','viewer');postHandler=()=>{throw Object.assign(Error('conflict'),{status:409})};await submit('#accessForm');assert.equal(mutations[0].body.tenant,'beta');assert.equal(mutations[0].body.project_id,'1');assert.equal(assigned.length,0);
""")

    def test_old_management_target_read_cannot_show_directory_in_new_target(self):
        self.run_js(r"""
directory=accessData({tenants:[{id:'alpha',name:'甲',status:'active'},{id:'beta',name:'乙',status:'active'}]});await vAccess();const old=later();getHandler=()=>old.promise;const reading=$('#accessRefresh').fire('click');getHandler=()=>accessData({current_tenant:{id:'beta',name:'乙'},tenants:directory.tenants,members:[{id:'beta-user',name:'乙用户',role:'member',active:true}]});$('#accessTarget').value='beta';await $('#accessTarget').fire('change');old.resolve(accessData());await reading;assert.equal(ACCESS.view.target,'beta');assert.ok($('#accessRecords').textContent.includes('乙用户'));assert.ok(!$('#accessRecords').textContent.includes('Alice'));
""")

    def test_password_is_only_in_pending_request_and_never_browser_storage_or_audit(self):
        self.run_js(r"""
directory=accessData({permissions:{account_manage:true}});await choose('password_reset');change('user','bob');change('password','synthetic-password-only');postHandler=()=>{throw Error('offline')};await submit('#accessForm');assert.equal(mutations[0].body.password,'synthetic-password-only');assert.equal(ACCESS_RAW_LOCAL.length,0);assert.equal(ACCESS_RAW_SESSION.length,0);assert.ok(!$('#accessRecords').textContent.includes('synthetic-password-only'));assert.ok(!$('#accessPending').innerHTML.includes('synthetic-password-only'));
""")

    def test_handoff_draft_and_uncertain_receipt_restore_only_inside_original_tenant(self):
        self.run_js(r"""
ACCESS.base='/t/alpha';accessBind({access:{tenant:{id:'alpha'},context_token:'a',user:'alice'}});
globalThis.HANDOFFS={view:null,drafts:new Map([['APP-1',new Map([['send',{revision:2,note:'完整交接材料',materials:'完整步骤'}]])]]),pending:new Map([['APP-1',{body:{action:'send',request_id:'same-request',materials:'原请求材料'},busy:true}]])};
globalThis.LIB={drafts:new Map([['APP',{libPurpose:'完整引用目的'}]])};accessSaveMemoryDrafts();HANDOFFS.drafts.clear();HANDOFFS.pending.clear();LIB.drafts.clear();ACCESS.base='/t/beta';accessRestoreMemoryDrafts();assert.equal(HANDOFFS.drafts.size,0);assert.equal(LIB.drafts.size,0);ACCESS.base='/t/alpha';accessRestoreMemoryDrafts();assert.equal(HANDOFFS.pending.get('APP-1').body.request_id,'same-request');assert.equal(HANDOFFS.pending.get('APP-1').busy,false);assert.equal(HANDOFFS.drafts.get('APP-1').get('send').materials,'完整步骤');assert.equal(LIB.drafts.get('APP').libPurpose,'完整引用目的');

""", core=True)

    def test_disabled_account_clears_dom_and_invalidates_inflight_reads(self):
        self.run_js(r"""
ACCESS.base='/t/alpha';accessBind({access:{tenant:{id:'alpha'},context_token:'a',user:'alice'}});let release;globalThis.fetch=path=>path.endsWith('/api/projects')?new Promise(r=>release=r):Promise.resolve({ok:false,status:403,json:async()=>({code:'identity_revoked',error:'账号停用'})});main.innerHTML='<p id="secret">私有数据</p>';sessionStorage.setItem('tmh.f','private-filter');const old=get('/api/projects');await assert.rejects(get('/api/meta'),e=>e.access);release({ok:true,json:async()=>[{name:'迟到私有数据'}]});await assert.rejects(old,e=>e.access);assert.equal(main.querySelector('#secret'),null);assert.equal(sessionStorage.getItem('tmh.f'),null);assert.equal(main.querySelector('#accessReload').href,'/login?next=%2Ft%2Falpha%2F');
""", core=True)

    def test_tenant_admin_can_add_existing_username_without_global_account_directory(self):
        self.run_js(r"""
directory=accessData({accounts:[]});await choose('member_set');const user=change('user','existing-user');assert.equal(user.tag,'input');change('role','member');postHandler=()=>{throw Object.assign(Error('version conflict'),{status:409})};await submit('#accessForm');assert.equal(mutations.length,1);assert.equal(mutations[0].body.user,'existing-user');assert.ok(main.textContent.includes('不提供全平台账号目录'));
""")

    def test_project_write_checks_do_not_infer_all_projects_from_tenant_write(self):
        self.run_js(r"""
S.projects=[{id:1,key:'APP'},{id:2,key:'VIEW'},{id:3,key:'NONE'}];S.meta.access={...S.meta.access,role:'member',capabilities:{write:true,execution:false},project_grants:[{project_id:'1',role:'contributor'},{project_id:'2',role:'viewer'}]};assert.equal(accessCanWrite('APP'),true);assert.equal(accessCanWrite('VIEW'),false);assert.equal(accessCanWrite('NONE'),false);assert.ok(accessProjectNote('APP').includes('执行不可用'));assert.ok(accessProjectNote('VIEW').includes('仅有查看权限'));S.meta.access.role='viewer';assert.equal(accessCanWrite('APP'),false);
""")

    def test_delivery_readonly_blocks_mutation_and_execution_denial_keeps_manual_materials_available(self):
        self.run_js(r"""
S.projects=[{id:1,key:'APP'}];S.meta.access={...S.meta.access,role:'member',capabilities:{write:true,execution:false},project_grants:[{project_id:'1',role:'viewer'}]};main.innerHTML='<button id="dlSaveArtifact">保存</button><button id="dlReviewGo">复核</button><button id="dlLinkGo">关联</button><button id="dlRunGo">执行</button><div id="error"></div>';dlApplyAccess('APP');assert.equal($('#dlSaveArtifact').disabled,true);await dlAct({project:'APP'}, {},{action:'save_artifact'},$('#dlSaveArtifact'),$('#error'));assert.equal(mutations.length,0);assert.ok($('#error').textContent.includes('只读'));
S.meta.access.project_grants=[{project_id:'1',role:'contributor'}];assert.equal(dlAccessReason('APP'), '');assert.ok(dlAccessReason('APP',true).includes('执行不可用'));await dlAct({project:'APP'}, {},{action:'start'},$('#dlRunGo'),$('#error'));assert.equal(mutations.length,0);
""")

    def test_control_plane_only_boot_never_reads_business_projects(self):
        self.run_js(r"""
main.innerHTML='<div id="brandName"></div><button id="me"></button><a id="logout"></a><div id="projSel"></div><div id="nav5"></div><div id="accessContextNotice"></div><form id="say"></form><button id="ptsBtn"></button><button id="astToggle"></button><div id="tabs"></div>';
ACCESS.base='/t/alpha';globalThis.ls={get:()=>null};accessInit=()=>{};location.hash='#/workspace';const meta={brand:'测试平台',user:'alice',login:true,access:{...S.meta.access,context_token:'owner-control',role:null,capabilities:{read:false,write:false},tenant:{id:'alpha',name:'未加入租户',status:'active'}}};getHandler=url=>{if(url==='/api/meta')return meta;if(url==='/api/access?tenant=alpha')return accessData();throw Error('Unexpected business request '+url)};await boot();assert.deepEqual(requests,['/api/meta','/api/access?tenant=alpha']);assert.equal(location.hash,'#/access');assert.ok(main.textContent.includes('成员与权限'));assert.equal(S.meta.access.capabilities.read,false);
S.meta.access={...S.meta.access,role:'admin',capabilities:{read:true},tenant:{id:'alpha',status:'disabled'}};assert.equal(accessControlOnly(),true);
""")

    def test_managed_public_capabilities_are_blocked_even_when_owner_execution_is_enabled(self):
        self.run_js(r"""
ACCESS.base='/t/alpha';S.meta={access:{capabilities:{write:true,execution:true}}};accessBind({access:{tenant:{id:'alpha'},context_token:'a',user:'owner'}});let calls=0;globalThis.fetch=async()=>{calls++;return{ok:true,json:async()=>({ok:true})}};for(const [url,body] of [['/api/tickets/SAME-1/preview',{action:'start'}],['/api/projects/SAME/standing',{action:'start'}],['/api/projects/SAME/shares',{}],['/api/tickets/SAME-1/ask-client',{}],['/api/projects/SAME/capture-token',{}],['/api/team',{action:'candidate_preview'}]])await assert.rejects(post(url,body),e=>e.status===403);assert.equal(calls,0);await post('/api/tickets/SAME-1/preview',{action:'stop'});await get('/api/tickets/SAME-1/preview');assert.equal(calls,2);
""",core=True)

    def test_nonsecret_management_drafts_restore_only_in_original_tenant(self):
        self.run_js(r"""
ACCESS.base='/t/alpha';accessBind({access:{tenant:{id:'alpha'},context_token:'a',user:'alice'}});await choose('tenant_rename');change('name','未提交的完整租户名称');accessSaveMemoryDrafts();ACCESS.view=null;ACCESS.base='/t/beta';accessRestoreMemoryDrafts();assert.equal(ACCESS.restoredAdmin,null);ACCESS.base='/t/alpha';accessRestoreMemoryDrafts();await vAccess();assert.equal(main.querySelector('[data-access-field="name"]').value,'未提交的完整租户名称');
""")

    def test_password_draft_prevents_tenant_switch_without_persisting_password(self):
        self.run_js(r"""
ACCESS.base='/t/alpha';accessBind({access:{tenant:{id:'alpha'},context_token:'a',user:'alice'}});directory=accessData({permissions:{account_manage:true}});await choose('password_reset');change('user','bob');change('password','test-secret-not-persisted');accessSwitch('beta');assert.equal(assigned.length,0);assert.ok(notices.at(-1).includes('密码不会保存'));accessSaveMemoryDrafts();assert.ok(![...ACCESS_RAW_SESSION.values.values()].join('').includes('test-secret-not-persisted'));
""")

    def test_execution_controls_keep_human_gates_and_manual_collaboration_separate(self):
        self.run_js(r"""
S.projects=[{id:1,key:'APP'}];S.meta.access={...S.meta.access,role:'member',capabilities:{read:true,write:true,execution:false},project_grants:[{project_id:'1',role:'contributor'}]};main.innerHTML='<button id="team-submit"></button><button id="team-verify"></button><button id="team-preview"></button><button id="team-accept"></button><button id="team-comment-send"></button><button id="team-assign"></button><button id="team-claim"></button><p id="team-access-note"></p><button id="nIn"></button><button id="naAn"></button>';const x={ticket:{key:'APP-1',pkey:'APP'}};teamAccessGuard(main,x);for(const id of ['team-submit','team-verify','team-preview','team-accept'])assert.equal($('#'+id).disabled,true);assert.equal($('#team-comment-send').disabled,false);assert.equal(teamAccessReason(x,'comment'),'');assert.equal($('#team-assign').disabled,true);assert.equal($('#team-claim').disabled,true);assert.ok(teamAccessReason(x,'assign').includes('项目管理员'));assert.ok(teamAccessReason(x,'review').includes('Git'));assert.ok($('#team-access-note').textContent.includes('暂不可用'));accessFenceControls(main);assert.equal($('#nIn').disabled,true);assert.equal($('#naAn').disabled,true);S.meta.access.capabilities.execution=true;$('#team-accept').disabled=true;teamAccessGuard(main,x);assert.equal($('#team-accept').disabled,true,'execution capability must not enable a human approval gate');assert.equal($('#team-preview').disabled,true);
""")

    def test_personal_candidate_verification_shows_actual_project_support(self):
        self.run_js(r"""
S.projects=[{id:1,key:'APP'}];S.meta.access={...S.meta.access,role:'member',capabilities:{read:true,write:true,execution:false},project_grants:[{project_id:'1',role:'contributor'}]};
const x={ticket:{key:'APP-1',pkey:'APP'},personal_decisions_available:true,personal_verification_reason:''};
assert.equal(teamAccessReason(x,'candidate_verify'),'');
assert.ok(teamAccessReason(x,'candidate_preview').includes('不支持'));
x.personal_preview_reason='此项目尚未配置预览命令；租户隔离预览通道也尚未接入。';
assert.ok(teamAccessReason(x,'candidate_preview').includes('尚未配置预览命令'));
x.personal_verification_reason='请管理员配置 test 命令';
assert.ok(teamAccessReason(x,'candidate_verify').includes('test'));
x.repository_reason='当前项目不是 Git 仓库';
assert.ok(teamAccessReason(x,'candidate_verify').includes('不是 Git'));
""")

    def test_knowledge_answer_uses_session_identity_and_preserves_full_original_text(self):
        answer = 'function kbAnswer(n,q){' + JS.split('function kbAnswer(n,q){', 1)[1].split('function kbTriage(){', 1)[0]
        self.run_js(answer + r"""
let refreshed=0;const kbReview=()=>{refreshed++};S.user='untrusted-display-name';S.meta.user='真实账号 <person>';kbAnswer(7,'问题 <script>');
assert.equal($('#ansB').value,'真实账号 <person>');assert.ok(Object.hasOwn($('#ansB').attrs,'readonly'));assert.ok(!body.innerHTML.includes('<person>'));assert.ok(body.textContent.includes('业务方姓名请写在答复正文中'));
$('#ansB').value='不能冒充业务方';const original='  业务方：王老师\n'+ '完整原话。'.repeat(300)+'\n第二行与结尾空白保留  ';$('#ansT').value=original;postHandler=()=>({pages:['index']});await $('#ansOk').fire('click');
assert.deepEqual(mutations,[{url:'/api/projects/APP/kb/answer',body:{n:7,text:original}}]);assert.equal(refreshed,1);assert.equal(overlay.hidden,true);
""")

    def test_knowledge_answer_failure_keeps_original_text_and_ignores_display_identity(self):
        answer = 'function kbAnswer(n,q){' + JS.split('function kbAnswer(n,q){', 1)[1].split('function kbTriage(){', 1)[0]
        self.run_js(answer + r"""
const kbReview=()=>{throw Error('must not refresh a failed save')};S.user='local-only-name';S.meta={login:false};kbAnswer(8,'原始问题');assert.equal($('#ansB').value,'未登录个人账号');$('#ansT').value='  \n  ';await $('#ansOk').fire('click');assert.equal(mutations.length,0);
const original='业务方：原始提供者\n失败后完整保留  ';$('#ansT').value=original;postHandler=()=>{throw Object.assign(Error('请使用个人账号登录'),{status:403})};await $('#ansOk').fire('click');assert.equal($('#ansT').value,original);assert.equal(overlay.hidden,false);assert.equal(Object.hasOwn(mutations[0].body,'by'),false);assert.ok(notices.at(-1).includes('个人账号'));
""")

    def test_package_downloads_use_real_tenant_path_helper_and_keep_legacy_paths(self):
        package_actions = 'function pkgActions(d){' + JS.split('function pkgActions(d){', 1)[1].split('function pkgCard(d){', 1)[0]
        self.run_js(package_actions + r"""
const ticket={ticket:{key:'APP-7',status:'new'},package:{status:'incomplete'}};ACCESS.base='/t/alpha';let html=pkgActions(ticket);
assert.ok(html.includes('href="/t/alpha/e/APP-7"'));assert.ok(html.includes('href="/t/alpha/e/APP-7.intoto.json"'));assert.ok(!html.includes('href="/e/'));
ACCESS.base='';html=pkgActions(ticket);assert.ok(html.includes('href="/e/APP-7"'));assert.ok(html.includes('href="/e/APP-7.intoto.json"'));
""")
