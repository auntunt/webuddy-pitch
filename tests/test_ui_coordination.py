"""Execute the shipped coordination UI with real access/storage helpers."""
import shutil
import subprocess
import unittest

from test_ui_library import HARNESS
from test_ui_access import SETUP
from tmh.platform.ui import page
from tmh.platform.ui_access import ACCESS_BOOT_JS
from tmh.platform.ui_coordination import COORDINATION_JS
from tmh.platform.ui_delivery import DELIVERY_JS

FIXTURE = r"""
Element.prototype.contains=function(node){return node===this||this.all().includes(node)};
const selectors=Element.prototype.querySelectorAll;
Element.prototype.querySelectorAll=function(s){if(s.includes(','))return [...new Set(s.split(',').flatMap(x=>this.querySelectorAll(x.trim())))];const match=s.match(/^([a-z]+)(\[.+\])?$/);if(match)return this.all().filter(n=>n.tag===match[1]&&(!match[2]||selectors.call(this,match[2]).includes(n)));return selectors.call(this,s)};
Element.prototype.setSelectionRange=function(a,b){this.selectionStart=a;this.selectionEnd=b};
let legacyDraft=null;const dlRead=(key,fallback)=>legacyDraft||fallback;const ls={set(){}};const DL={detail:{delivery:{id:'d1'}}};const dlHref=id=>'#/delivery/'+id;const deliveryNavigations=[];const vDelivery=(...args)=>deliveryNavigations.push(args);document.createElement=tag=>new Element(tag);Element.prototype.appendChild=function(n){n.parent=this;this.children.push(n)};
S.scope='APP';S.meta={login:true,user:'alice'};S.projects[0].id=1;location.hash='#/meetings';
const memberList=[{id:'alice',name:'Alice'},{id:'bob',name:'Bob'}];
const meetingData=(extra={})=>({id:1,project:'APP',revision:1,meeting:{id:1,title:'产品对齐会',body:'完整原文\nTODO: 核对部署说明\n尾行',occurred_on:'2026-10-23',created_by:'alice',created:'2026-10-23',extraction:{notice:'明确标记产生规则草稿'}},actions:[{id:2,title:'核对部署说明',owner:'bob',due_date:'',deliverable:'部署说明',criteria:'列明回滚步骤',source_start:2,source_end:2,source_quote:'TODO: 核对部署说明',note:'',status:'draft',history:[]}],members:memberList,can_edit:true,...extra});
const listData=()=>({project:'APP',items:[{id:1,title:'产品对齐会',action_counts:{draft:1,published:0}}],total:1,offset:0,limit:50,members:memberList,can_edit:true});
const briefData=(extra={})=>({ticket:{key:'APP-1'},revision:0,source_token:'source-a',source:{requirement:'完整需求'},current:null,history:[],members:memberList,can_edit:true,...extra});
const coverageData=(extra={})=>({delivery:{id:'d1',project:'APP'},revision:0,items:[{id:3,title:'运维说明',requirement:'完整回滚步骤',required:true,artifact_id:5,status:'pending',source_token:'material-a',can_verify:true}],artifacts:[{id:5,title:'运维材料',version:1,body:'全部步骤',current:true}],history:[],can_edit:true,counts:{pending:1},template:{id:'software-delivery-v1',available:true},...extra});
const contentData=(extra={})=>({delivery:{id:'d1',project:'APP'},revision:0,source_token:'content-a',can_edit:true,stages:[{key:'requirements',name:'需求',can_save:true,artifact:null,history:[]}],...extra});let content=contentData();
let meeting=meetingData(),brief=briefData(),coverage=coverageData();
getHandler=url=>url.includes('/content')?content:url.includes('/brief')?brief:url.includes('/coverage')?coverage:url.endsWith('/meetings/1')?meeting:listData();
postHandler=(url,body)=>({...meeting,receipt:{request_id:body.request_id,revision:2}});
const view=()=>[...COORD.views.values()].at(-1);
const field=name=>main.querySelector('[data-co-field="'+name+'"]');
const change=(name,value)=>{const el=field(name);el.value=value;el.fire('input');return el};
const save=()=>main.querySelector('[data-co-form]').fire('submit');
const openMeeting=async()=>{location.hash='#/meetings/1';await vMeetings('1')};
const openBrief=async()=>{main.innerHTML='<div id="brief"></div>';const v=briefingOpen($('#brief'),'APP-1','APP');await v.ready;return v};
const openCoverage=async()=>{main.innerHTML='<div id="coverage"></div>';const v=coverageOpen($('#coverage'),{id:'d1',project:'APP'});await v.ready;return v};
"""


@unittest.skipUnless(shutil.which('node'), 'Node.js is required for shipped UI behavior')
class CoordinationUiTest(unittest.TestCase):
    def run_js(self, checks):
        result = subprocess.run([shutil.which('node'), '-'], input=HARNESS + SETUP + ACCESS_BOOT_JS + COORDINATION_JS + FIXTURE + '\n(async()=>{\n' + checks + '\n})().catch(e=>{console.error(e);process.exitCode=1});', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_complete_page_wires_surfaces_and_parses(self):
        html = page()
        for content in ['meetings:()=>vMeetings', 'id="hfBrief"', 'id="dlCoverage"', '会议与行动', 'COORD.views.clear()']:
            self.assertIn(content, html)
        result = subprocess.run(['node', '--check'], input=html.split('<script>')[1].split('</script>')[0], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_projects_requires_explicit_project_before_read(self):
        self.run_js("S.scope='*';await vMeetings();assert.equal(requests.length,0);assert.ok(main.textContent.includes('请选择项目'));await meetingProject('APP');assert.equal(requests[0],'/api/projects/APP/meetings?offset=0');")

    def test_readonly_has_no_write_or_file_import(self):
        self.run_js("S.meta.access={role:'viewer',capabilities:{write:false}};await vMeetings();assert.equal(field('title').disabled,true);assert.equal(main.querySelector('[data-co-import]').disabled,true);await save();assert.equal(mutations.length,0);await openMeeting();assert.equal(main.querySelector('[data-co-add]').disabled,true);")

    def test_complete_utf8_file_and_xss_preserved_without_loss(self):
        self.run_js(r"""await vMeetings();const text='\ufeff完整\r\n<script>alert(1)</script>\n'+'尾行'.repeat(5000);await meetingImport(view(),{name:'记录.txt',arrayBuffer:async()=>new TextEncoder().encode(text).buffer});assert.equal(field('body').value,text);assert.ok(view().host.innerHTML.includes('&lt;script&gt;'));change('title','会议');await save();assert.equal(mutations[0].body.body,text);assert.equal(location.hash,'#/meetings/1/APP');""")

    def test_bad_utf8_and_late_import_do_not_overwrite_input(self):
        self.run_js(r"""await vMeetings();change('body','原输入');await meetingImport(view(),{name:'bad.txt',arrayBuffer:async()=>new Uint8Array([0xff]).buffer});assert.equal(field('body').value,'原输入');const reading=later();const task=meetingImport(view(),{name:'new.txt',arrayBuffer:()=>reading.promise});change('body','读取中手工输入');reading.resolve(new TextEncoder().encode('文件').buffer);await task;assert.equal(field('body').value,'读取中手工输入');assert.ok(main.textContent.includes('正文已改变'));""")

    def test_refresh_preserves_input_and_keyboard_focus(self):
        self.run_js("await openMeeting();const n=change('title','未提交完整行动');n.selectionStart=3;n.selectionEnd=5;n.focus();await coRefresh(view());assert.equal(field('title').value,'未提交完整行动');assert.equal(document.activeElement,field('title'));assert.equal(field('title').selectionStart,3);")

    def test_action_switch_preserves_distinct_editor_drafts(self):
        self.run_js("await openMeeting();change('title','新行动草稿');meetingEdit(view(),meeting.actions[0],'edit_action');change('deliverable','编辑已有草稿');meetingEdit(view());assert.equal(field('title').value,'新行动草稿');meetingEdit(view(),meeting.actions[0],'edit_action');assert.equal(field('deliverable').value,'编辑已有草稿');")

    def test_publish_uses_existing_action_and_actual_ticket_assignee(self):
        self.run_js("await openMeeting();meetingEdit(view(),meeting.actions[0],'publish_action');await save();assert.deepEqual(Object.keys(mutations[0].body).sort(),['action','action_id','request_id','revision']);assert.equal(mutations[0].body.action,'publish_action');meeting.actions[0]={...meeting.actions[0],status:'published',ticket:{key:'APP-8',assignee:'alice',status:'new'}};await coRefresh(view());assert.ok(main.textContent.includes('任务负责人alice'));assert.ok(!main.querySelector('[data-co-act=\"publish_action\"]'));")

    def test_unknown_mutation_retries_identical_body_after_remount(self):
        self.run_js("await openBrief();change('summary','完整简报');postHandler=()=>{throw Error('connection lost')};await save();const original=JSON.stringify(mutations[0].body);assert.equal(COORD.pending.size,1);await openBrief();postHandler=(u,b)=>({...brief,receipt:{request_id:b.request_id,revision:1}});await main.querySelector('[data-co-retry]').fire('click');assert.equal(JSON.stringify(mutations[1].body),original);assert.equal(COORD.pending.size,0);")

    def test_success_refresh_failure_does_not_duplicate_write(self):
        self.run_js("await openBrief();change('summary','已保存正文');postHandler=(u,b)=>({...brief,receipt:{request_id:b.request_id,revision:1}});getHandler=()=>{throw Error('read unavailable')};const v=view();await save();assert.equal(mutations.length,1);assert.equal(COORD.pending.size,0);assert.equal(v.needsRefresh,true);await coWrite(v,{summary:'重复'});assert.equal(mutations.length,1);assert.ok(main.textContent.includes('read unavailable'));")

    def test_malformed_receipt_remains_unknown_and_double_submit_is_single(self):
        self.run_js("await openBrief();change('summary','输入');const p=later();postHandler=()=>p.promise;const first=save();await save();assert.equal(mutations.length,1);p.resolve({receipt:{request_id:mutations[0].body.request_id,revision:1}});await first;assert.equal(COORD.pending.size,1);assert.equal(field('summary').value,'输入');assert.ok(main.textContent.includes('保存回执不完整'));")

    def test_late_success_refreshes_remounted_live_view(self):
        self.run_js("await openBrief();change('summary','完整简报');const p=later();postHandler=()=>p.promise;const first=save();await openBrief();p.resolve({...brief,receipt:{request_id:mutations[0].body.request_id,revision:1}});await first;assert.equal(COORD.pending.size,0);assert.equal(main.querySelector('[data-co-write]').disabled,false);")

    def test_conflict_keeps_draft_and_never_automatically_rebinds(self):
        self.run_js("await openBrief();change('summary','保留输入');postHandler=()=>{throw Object.assign(Error('来源变化'),{status:409})};await save();brief=briefData({source_token:'source-b'});await coRefresh(view());assert.equal(field('summary').value,'保留输入');assert.equal(main.querySelector('[data-co-write]').disabled,true);assert.equal(coDraft(view()).source_token,'source-a');await main.querySelector('[data-co-rebind]').fire('click');assert.equal(coDraft(view()).source_token,'source-b');assert.equal(main.querySelector('[data-co-write]').disabled,false);assert.equal(mutations.length,1);")

    def test_context_or_route_change_discards_late_reads(self):
        self.run_js("const pending=later();getHandler=()=>pending.promise;const task=vMeetings();ACCESS.epoch++;main.innerHTML='<p id=\"other\">另一页面</p>';pending.resolve(listData());await task;assert.equal($('#other').textContent,'另一页面');")

    def test_draft_namespace_is_tenant_user_project_and_object(self):
        self.run_js("await openBrief();change('summary','甲项目');const first=view().key;assert.notEqual(first,coIdentity('APP','brief','APP-2'));assert.notEqual(first,coIdentity('STD','brief','APP-1'));S.meta.user='bob';await openBrief();assert.equal(field('summary').value,'');S.meta.user='alice';ACCESS.base='/t/other';await openBrief();assert.equal(field('summary').value,'');ACCESS.base='';await openBrief();assert.equal(field('summary').value,'甲项目');")

    def test_coverage_binds_exact_version_and_source_and_requires_note(self):
        self.run_js("await openCoverage();assert.ok(main.textContent.includes('运维材料 · v1'));coverageEdit(view(),coverage.items[0],'verify');change('note','逐项核对回滚路径');postHandler=(u,b)=>({...coverage,receipt:{request_id:b.request_id,revision:1}});await save();assert.equal(mutations[0].body.source_token,'material-a');assert.equal(mutations[0].body.note,'逐项核对回滚路径');assert.equal(mutations[0].body.action,'verify');assert.equal(mutations[0].body.item_id,3);")

    def test_stale_material_cannot_be_verified_and_template_is_explicit(self):
        self.run_js("coverage.items[0]={...coverage.items[0],status:'stale',can_verify:false,stale_reasons:['材料已有新版']};coverage.artifacts[0].current=false;coverage.artifacts.push({id:6,title:'运维材料',version:2,current:true,body:'新版'});await openCoverage();assert.equal(mutations.length,0);assert.equal(main.querySelector('[data-co-act=\"verify\"]').disabled,true);change('title','我的要求草稿');postHandler=(u,b)=>({...coverage,receipt:{request_id:b.request_id,revision:1}});await main.querySelector('[data-co-template]').fire('click');assert.equal(mutations[0].body.action,'seed_template');assert.equal(field('title').value,'我的要求草稿');coverageEdit(view(),coverage.items[0],'update');assert.ok(field('artifact_id').textContent.includes('v2'));")

    def test_historical_sources_are_full_and_escaped(self):
        self.run_js("brief.history=[{revision:1,summary:'旧摘要',source:{body:'<img src=x>'+'完整'.repeat(6000)}}];await openBrief();assert.ok(view().host.innerHTML.includes('&lt;img src=x&gt;'));assert.ok(main.textContent.includes('完整'.repeat(6000)));")

    def test_manual_material_preserves_full_body_and_exact_basis(self):
        self.run_js("main.innerHTML='<section id=\"manual\"></section>';const v=deliveryContentOpen($('#manual'),{id:'d1',project:'APP'},'requirements');await v.ready;change('title','完整需求');change('body','全文\\n'+ '完整材料'.repeat(6000));postHandler=(u,b)=>({...content,receipt:{request_id:b.request_id,revision:1}});await save();assert.equal(mutations[0].url,'/api/deliveries/d1/content');assert.equal(mutations[0].body.source_token,'content-a');assert.equal(mutations[0].body.body,'全文\\n'+'完整材料'.repeat(6000));assert.deepEqual(deliveryNavigations,[['d1','requirements']]);")

    def test_manual_creation_unknown_result_has_one_fixed_request(self):
        self.run_js("main.innerHTML='<section id=\"dlCreate\"><select id=\"dlProject\"><option value=\"APP\">APP</option></select><button id=\"dlCreateGo\">创建</button></section>';postHandler=()=>{throw Error('connection lost')};await deliveryContentCreate('APP',{type:'research',title:'交付目标',goal:'完整目标'});assert.equal($('#dlCreateGo').disabled,true);const original=JSON.stringify(mutations[0].body);await deliveryContentCreate('APP',{type:'research',title:'不应重复',goal:'目标'});assert.equal(mutations.length,1);postHandler=(u,b)=>({...content,receipt:{request_id:b.request_id,revision:1}});await main.querySelector('[data-co-retry]').fire('click');assert.equal(JSON.stringify(mutations[1].body),original);assert.equal(location.hash,'#/delivery/d1');assert.equal(mutations[0].body.action,'create');")

    def test_imported_crlf_survives_browser_textarea_normalization(self):
        self.run_js("await vMeetings();const original='首行\\r\\n第二行\\r\\n';await meetingImport(view(),{name:'record.txt',arrayBuffer:async()=>new TextEncoder().encode(original).buffer});field('body').value='首行\\n第二行\\n';change('title','原文');await save();assert.equal(mutations[0].body.body,original);")

    def test_explicit_meeting_project_link_never_falls_back_to_other_scope(self):
        self.run_js("S.scope='REF';location.hash='#/meetings/1/APP';await vMeetings('1','APP');assert.equal(S.scope,'APP');assert.equal(requests.at(-1),'/api/projects/APP/meetings/1');const count=requests.length;await vMeetings('1','NOACCESS');assert.equal(requests.length,count);assert.ok(main.textContent.includes('不在当前授权范围'));assert.ok(!main.textContent.includes('完整原文'));")

    def test_revocation_clears_new_caches_and_outstanding_views(self):
        self.run_js("ACCESS.base='/t/alpha';accessBind({access:{tenant:{id:'alpha'},context_token:'token',user:'alice'}});await openBrief();change('summary','敏感草稿');postHandler=()=>{throw Error('network')};await save();assert.equal(COORD.pending.size,1);accessLock('成员已撤销','membership_revoked');assert.equal(COORD.views.size,0);assert.equal(COORD.drafts.size,0);assert.equal(COORD.pending.size,0);assert.ok(!main.textContent.includes('敏感草稿'));assert.equal(ACCESS_RAW_SESSION.length,0);")

    def test_legacy_execution_controls_disabled_while_manual_content_remains_writable(self):
        helpers = 'function dlAccessReason' + DELIVERY_JS.split('function dlAccessReason', 1)[1].split('function dlBusy', 1)[0]
        self.run_js(helpers + "S.meta.access={role:'member',capabilities:{write:true,execution:false},project_grants:[{project_id:'1',role:'contributor'}]};main.innerHTML='<button id=\"dlReviewGo\">复核</button><button id=\"dlLinkGo\">关联</button><button id=\"dlRunGo\">运行</button><button data-dl-collect=\"1\">采集</button>';dlApplyAccess('APP');assert.equal($('#dlReviewGo').disabled,true);assert.equal($('#dlLinkGo').disabled,true);assert.equal($('#dlRunGo').disabled,true);assert.equal(main.querySelector('[data-dl-collect]').disabled,true);main.innerHTML='<section id=\"manual\"></section>';const v=deliveryContentOpen($('#manual'),{id:'d1',project:'APP'},'requirements');await v.ready;assert.equal(main.querySelector('[data-co-write]').disabled,false);")

    def test_pending_replay_available_when_remount_initial_read_fails(self):
        self.run_js("await openBrief();change('summary','原始请求');postHandler=()=>{throw Error('lost reply')};await save();const body=JSON.stringify(mutations[0].body);getHandler=()=>{throw Error('read unavailable')};await openBrief();assert.ok(main.querySelector('[data-co-retry]'));postHandler=(u,b)=>({...brief,receipt:{request_id:b.request_id,revision:1}});await main.querySelector('[data-co-retry]').fire('click');assert.equal(JSON.stringify(mutations[1].body),body);assert.equal(COORD.pending.size,0);assert.ok(main.textContent.includes('read unavailable'));")

    def test_success_cleanup_storage_failure_never_reopens_creation(self):
        self.run_js("await vMeetings();change('title','一次会议');change('body','完整正文');const original=ACCESS_RAW_SESSION.removeItem;ACCESS_RAW_SESSION.removeItem=k=>{if(k.includes('draft'))throw Error('storage unavailable');original(k)};await save();assert.equal(mutations.length,1);assert.equal(COORD.pending.size,1);assert.ok(coPending(view().key).completed);assert.equal(main.querySelector('[data-co-write]').disabled,true);await save();assert.equal(mutations.length,1);ACCESS_RAW_SESSION.removeItem=original;await main.querySelector('[data-co-retry]').fire('click');assert.equal(mutations.length,1);assert.equal(location.hash,'#/meetings/1/APP');")

    def test_unavailable_storage_blocks_write_with_visible_preserved_input(self):
        self.run_js("await vMeetings();field('title').value='保留会议';field('body').value='完整正文';const original=ACCESS_RAW_SESSION.setItem;ACCESS_RAW_SESSION.setItem=()=>{throw Error('quota')};await save();assert.equal(mutations.length,0);assert.ok(main.textContent.includes('浏览器无法保存草稿'));assert.equal(field('body').value,'完整正文');await meetingImport(view(),{name:'x.txt',arrayBuffer:async()=>new TextEncoder().encode('文件').buffer});assert.ok(main.textContent.includes('浏览器无法保存草稿'));ACCESS_RAW_SESSION.setItem=original;")

    def test_existing_manual_material_crlf_survives_title_only_edit(self):
        self.run_js("content.stages[0].artifact={title:'旧标题',version:1,body:'首行\\r\\n第二行\\r\\n'};main.innerHTML='<section id=\"manual\"></section>';const v=deliveryContentOpen($('#manual'),{id:'d1',project:'APP'},'requirements');await v.ready;field('body').value='首行\\n第二行\\n';change('title','只改标题');postHandler=(u,b)=>({...content,receipt:{request_id:b.request_id,revision:1}});await save();assert.equal(mutations[0].body.body,'首行\\r\\n第二行\\r\\n');")

    def test_upgrade_restores_full_old_material_draft_without_silent_binding(self):
        self.run_js("legacyDraft={title:'旧编辑标题',body:'完整旧草稿\\n尾行',version:1};main.innerHTML='<section id=\"manual\"></section>';const v=deliveryContentOpen($('#manual'),{id:'d1',project:'APP'},'requirements');await v.ready;assert.equal(field('body').value,'完整旧草稿\\n尾行');assert.equal(main.querySelector('[data-co-write]').disabled,true);assert.ok(main.textContent.includes('升级前'));await main.querySelector('[data-co-rebind]').fire('click');assert.equal(main.querySelector('[data-co-write]').disabled,false);assert.equal(field('body').value,'完整旧草稿\\n尾行');")

    def test_unreadable_saved_receipt_fails_closed_without_new_creation(self):
        self.run_js("ACCESS_RAW_SESSION.getItem=()=>{throw Error('read denied')};await vMeetings();field('title').value='不可重复';field('body').value='完整输入';await save();assert.equal(mutations.length,0);assert.ok(main.textContent.includes('避免重复创建'));assert.equal(main.querySelector('[data-co-write]').disabled,true);")
