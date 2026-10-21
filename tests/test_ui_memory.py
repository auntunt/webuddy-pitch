"""Shipped memory UI actions, stale response handling and full export."""
import shutil
import subprocess
import unittest

from test_ui_library import HARNESS
from tmh.platform.ui_memory import MEMORY_JS


SETUP = r"""
const originalQuery=Element.prototype.querySelectorAll;
Element.prototype.querySelectorAll=function(selector){if(/^[a-z]+$/.test(selector))return this.all().filter(n=>n.tag===selector);return originalQuery.call(this,selector)};
const md=s=>'<div class="md">'+h(s)+'</div>',workIcon=()=>'<svg></svg>';
location.hash='#/memory';
const memoryData=(extra={})=>({projects:S.projects,section:'overview',lessons:[],knowledge:[],summary:{lessons:0,active:0,knowledge:0,shared:0},scope_notice:'按项目与明确共享范围使用',brief:{status:'preview',stale:false,stale_reasons:[],warnings:[]},clusters:{items:[]},...extra});
const ownLesson=(extra={})=>({id:'L1',title:'审批重复回调',symptom:'同一回调重复写入',fix:'检查幂等键',status:'candidate',scope:'project',scope_label:'本项目记忆',applicability:'相近任务',stats:{used:2,passed:1,failed:0},...extra});
const memoryBrief=(extra={})=>({project:{key:'APP',name:'审批系统'},exists:true,revision:1,markdown:'# 完整交接\n\n完整原文 <script>危险脚本</script>',sections:[{id:'overview',title:'项目与代码',kind:'markdown',body:extra.markdown||'项目概览'}],sources:[],history:[{revision:1,created:'2026-10-22',confirmed:null}],status:'draft',fingerprint:'v1',current_fingerprint:'v1',stale:false,stale_reasons:[],warnings:[],...extra});
let memoryResponse=memoryData();getHandler=url=>memoryResponse;
postHandler=async()=>({ok:true});
let exportedBlob,downloaded;
let ticketDraft;const newTicket=value=>{ticketDraft=value};
URL.createObjectURL=blob=>{exportedBlob=blob;return'blob:memory-export'};URL.revokeObjectURL=()=>{};
document.createElement=()=>({click(){downloaded={href:this.href,name:this.download}}});
"""


@unittest.skipUnless(shutil.which("node"), "Node needed for shipped UI")
class MemoryUiTests(unittest.TestCase):
    def run_js(self, checks):
        result = subprocess.run([shutil.which("node"), "-"], input=HARNESS + SETUP + MEMORY_JS +
                                "\n(async()=>{\n" + checks + "\n})().catch(e=>{console.error(e);process.exitCode=1});",
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_global_scope_and_project_switch_are_explicit(self):
        self.run_js(r"""
await vMemory();assert.ok(requests[0].includes('project=&section=overview'));assert.equal($('#memProject').value,'');
$('#memProject').value='APP';await $('#memProject').fire('change');assert.ok(requests.at(-1).includes('project=APP'));assert.equal(MEM.project,'APP');
$('#memQuery').value='<img onerror=attack>';await $('#memSearch').fire('submit');assert.equal($('#memQuery').value,'<img onerror=attack>');assert.ok(main.innerHTML.includes('&lt;img'));
""")

    def test_brief_navigation_uses_reloadable_route(self):
        self.run_js(r"""
MEM.project='APP';await vMemory();$('#memBriefGo').fire('click');assert.equal(location.hash,'#/handoff/APP');memoryResponse=memoryBrief();await vProjectBrief('APP');$('#memBack').fire('click');assert.equal(location.hash,'#/memory');
""")

    def test_late_reads_cannot_replace_a_departed_page(self):
        self.run_js(r"""
const stale=later();getHandler=()=>stale.promise;const reading=vMemory();location.hash='#/today';main.innerHTML='<div id="today">今天</div>';stale.resolve(memoryData());await reading;assert.equal($('#today').textContent,'今天');
""")

    def test_confirm_double_click_sends_once_and_failure_preserves_editor(self):
        self.run_js(r"""
MEM.project='APP';memoryResponse=memoryData({lessons:[ownLesson()]});await vMemory('lessons');
const confirm=main.querySelector('[data-mem-act="lesson_confirm"]'),pending=later();postHandler=()=>pending.promise;const first=confirm.fire('click'),second=confirm.fire('click');assert.equal(mutations.length,1);assert.equal(confirm.disabled,true);
pending.reject(new Error('保存失败，保留原内容'));await first;await second;assert.ok($('#memNotice').textContent.includes('保存失败'));assert.equal(confirm.disabled,false);
const edit=main.querySelector('[data-mem-edit]'),fix=edit.querySelector('[data-mem-field="fix"]');fix.value='用户尚未保存的完整修改';postHandler=async()=>{throw new Error('网络中断')};await edit.fire('submit');assert.equal(fix.value,'用户尚未保存的完整修改');assert.ok($('#memNotice').textContent.includes('网络中断'));
""")

    def test_share_requires_readable_copy_and_sends_project_actor_route(self):
        self.run_js(r"""
MEM.project='APP';memoryResponse=memoryData({lessons:[ownLesson({status:'active'})]});await vMemory('lessons');
getHandler=url=>url.endsWith('/share')?{title:'共享标题',fields:{symptom:'脱敏现象',fix:'脱敏做法'}}:memoryResponse;
await main.querySelector('[data-mem-share]').fire('click');assert.equal(mutations.length,0,'preview must not share');
const form=main.querySelector('[data-mem-share-form]');form.querySelector('[data-mem-field="fix"]').value='人工核对后的做法';await form.fire('submit');assert.equal(mutations.length,1);assert.equal(mutations[0].url,'/api/memory');assert.equal(mutations[0].body.project,'APP');assert.equal(mutations[0].body.action,'lesson_share');assert.equal(mutations[0].body.fields.fix,'人工核对后的做法');
""")

    def test_cluster_confirmation_and_exclusion_bind_visible_fingerprint(self):
        self.run_js(r"""
MEM.project='APP';memoryResponse={items:[{id:'C-1',title:'重复回调',status:'candidate',revision:1,fingerprint:'inputs-1',members:[{key:'APP-1',title:'a',status:'new',body:'原文一'},{key:'APP-2',title:'b',status:'new',body:'原文二'}],matches:[{tickets:['APP-1','APP-2'],reasons:['同业务流']}]}],tickets_scanned:2};await vMemory('clusters');
await main.querySelector('[data-mem-confirm]').fire('click');assert.equal(mutations[0].body.expected_fingerprint,'inputs-1');
await main.querySelector('[data-mem-exclude="APP-2"]').fire('click');const form=main.querySelector('[data-mem-editor]').querySelector('form');form.querySelector('[data-mem-reason]').value='不同根因';await form.fire('submit');assert.equal(mutations[1].body.ticket_key,'APP-2');assert.equal(mutations[1].body.reason,'不同根因');assert.equal(mutations[1].body.expected_fingerprint,'inputs-1');
""")

    def test_full_markdown_export_and_stale_confirmation_disabled(self):
        self.run_js(r"""
memoryResponse=memoryBrief({stale:true,status:'stale',stale_reasons:[{label:'业务知识页',reason:'来源变化'}]});await vProjectBrief('APP');assert.equal($('#memBriefConfirm').disabled,true);assert.ok(main.innerHTML.includes('来源变化'));assert.ok(!main.innerHTML.includes('<script>危险脚本</script>'));
$('#memBriefDownload').fire('click');assert.equal(await exportedBlob.text(),memoryResponse.markdown);assert.equal(downloaded.name,'APP-项目交接-1.md');
""")

    def test_chapters_do_not_flatten_source_headings_and_render_pages_only_when_open(self):
        self.run_js(r"""
const raw='---\nid: page1\n---\n# 页面标题\n## 原页面内部章节\n专属全文正文';memoryResponse=memoryBrief({sections:[{id:'overview',title:'项目与代码',kind:'markdown',body:'简短概览'},{id:'knowledge',title:'业务知识',kind:'entries',items:[{id:'page1',title:'审批流程',source:'flows/approval.md',body:raw}]},{id:'sources',title:'来源清单',kind:'entries',items:[{id:'source1',title:'代码版本',body:'{"commit":"123"}',format:'json'}]}]});await vProjectBrief('APP');
assert.ok($('#memBriefChapter').innerHTML.includes('简短概览'));assert.ok(!$('#memBriefChapter').innerHTML.includes('专属全文正文'));
await main.querySelector('[data-mem-chapter="knowledge"]').fire('click');assert.ok($('#memBriefChapter').innerHTML.includes('审批流程'));assert.ok(!$('#memBriefChapter').innerHTML.includes('专属全文正文'));
const details=main.querySelector('[data-mem-entry="0"]');details.open=true;details.fire('toggle');assert.ok(details.querySelector('[data-mem-entry-content]').innerHTML.includes('专属全文正文'));assert.ok(details.querySelector('[data-mem-entry-content]').innerHTML.includes('原页面内部章节'));
assert.equal(main.querySelectorAll('[data-mem-chapter]').length,3,'source headings cannot become navigation chapters');
""")

    def test_cluster_reuse_opens_draft_with_sources_without_creating_ticket(self):
        self.run_js(r"""
MEM.project='APP';memoryResponse={items:[{id:'C-1',title:'重复回调',status:'confirmed',revision:2,fingerprint:'inputs-1',members:[{key:'APP-1',title:'a',status:'closed',body:'原文一'},{key:'APP-2',title:'b',status:'closed',body:'原文二'}],matches:[],lessons:[{id:'L1',status:'active',title:'幂等处理',fix:'检查回调键',verify:'重复两次只写一次'},{id:'L2',status:'retired',title:'错误办法',fix:'不应该再次引用的内容'}]}],tickets_scanned:2};await vMemory('clusters');
await main.querySelector('[data-mem-reuse]').fire('click');assert.equal(mutations.length,0);assert.equal(ticketDraft.title,'');assert.ok(ticketDraft.body.includes('[APP-1](#/t/APP-1)'));assert.ok(ticketDraft.body.includes('检查回调键'));assert.ok(!ticketDraft.body.includes('不应该再次引用的内容'));assert.equal(S.proj,'APP');
""")

    def test_superseded_history_response_does_not_replace_current_revision(self):
        self.run_js(r"""
memoryResponse=memoryBrief({history:[{revision:1,created:'old'},{revision:2,created:'new'}]});await vProjectBrief('APP');
const old=later(),latest=later();getHandler=url=>url.endsWith('revision=1')?old.promise:latest.promise;
const select=$('#memBriefHistory');select.value='1';const a=select.fire('change');select.value='2';const b=select.fire('change');latest.resolve(memoryBrief({revision:2,markdown:'最新交接'}));await b;old.resolve(memoryBrief({revision:1,markdown:'旧交接'}));await a;assert.equal(MEM.view.brief.revision,2);assert.ok(main.querySelector('#memBriefChapter').innerHTML.includes('最新交接'));
""")


if __name__ == "__main__":
    unittest.main()
