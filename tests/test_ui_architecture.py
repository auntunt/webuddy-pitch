"""Shipped architecture overview, complete data and navigation."""
import shutil
import subprocess
import unittest
from tests.test_ui_library import HARNESS
from tmh.platform.ui import JS


@unittest.skipUnless(shutil.which('node'), 'Node required')
class ArchitectureUiTest(unittest.TestCase):
    def run_js(self, check):
        source=JS[JS.index('async function vMap(did){'):JS.index('async function archDomain(did){')]
        setup=r'''
location.hash='#/map';const pageHead=(title,subtitle,actions)=>`<h1>${h(title)}</h1>${actions}`;
const kst=status=>`<span class="tag">${h(status)}</span>`;
const data={built:true,built_at:'2026-11-04 08:16',flows:339,tables:33,classes:20,methods:50,unresolved:4,report:true,overview_status:'待确认',
 domains:Array.from({length:24},(_,i)=>({id:'dom:area'+i,title:'业务域 '+i,flows:i+1,tables:3,status:'仅事实',summary:'完整业务说明 '+i})),
 entries:Array.from({length:5},(_,i)=>['入口'+i,i+1]),top_tables:[['JSH_USER',42],['JSH_LOG',30]],
 ext:Array.from({length:5},(_,i)=>({title:'外部调用'+i,users:i+1}))};getHandler=()=>data;
'''
        r=subprocess.run(['node','-'],input=HARNESS+source+setup+'\n(async()=>{'+check+'})().catch(e=>{console.error(e);process.exitCode=1})',text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_complete_overview_and_real_navigation_without_invented_edges(self):
        self.run_js(r'''
await vMap();
assert.equal($('#archDomains').querySelectorAll('[href]').length,24);
assert.ok(main.querySelector('[href="#/map/dom%3Aarea23"]'));
assert.ok(main.querySelector('[href="#/kb/tbl%3AJSH_USER"]'));
assert.match(main.textContent,/入口4/);assert.match(main.textContent,/外部调用4/);
assert.match(main.textContent,/完整业务说明 23/);assert.match(main.textContent,/339/);
assert.ok(!main.innerHTML.includes('<svg'));assert.ok(!main.textContent.includes('另有'));
''')

    def test_search_empty_and_clear_preserve_all_domains(self):
        self.run_js(r'''
await vMap();$('#archSearch').value='area23';$('#archSearch').oninput();
assert.equal($('#archDomains').querySelectorAll('[href]').length,1);assert.equal($('#archCount').textContent,'1 / 24');
$('#archSearch').value='找不到';$('#archSearch').oninput();assert.match($('#archDomains').textContent,/没有匹配/);
$('#archClear').onclick();assert.equal($('#archDomains').querySelectorAll('[href]').length,24);
''')

    def test_escape_long_titles_and_empty_analysis(self):
        self.run_js(r'''
data.domains[0].title='<script>not executable</script>';await vMap();
assert.ok($('#archDomains').innerHTML.includes('&lt;script&gt;'));assert.ok(!$('#archDomains').innerHTML.includes('<script>'));
data.built=false;await vMap();assert.match(main.textContent,/还没有代码分析结果/);assert.ok(main.querySelector('[href="#/kb"]'));
''')

    def test_late_project_response_does_not_repaint(self):
        self.run_js(r'''
const wait=later();getHandler=()=>wait.promise;main.innerHTML='<p>当前页面</p>';const pending=vMap();S.proj='OTHER';wait.resolve(data);await pending;assert.equal(main.textContent,'当前页面');
''')
