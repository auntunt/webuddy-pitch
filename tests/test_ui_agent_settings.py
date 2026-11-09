import shutil
import subprocess
import unittest
from tmh.platform.ui import JS
from tests.test_ui_library import HARNESS


@unittest.skipUnless(shutil.which('node'), 'Node required')
class AgentSettingsUiTest(unittest.TestCase):
    def run_js(self, check):
        source=JS[JS.index('async function agentSettingsLoad()'):JS.index('async function vSettings()')]
        setup=r'''
S.meta={access:{can_manage:true}};
const data={can_edit:true,revision:'one',route:{agent:'codex'},modes:['fix','analyze'],agents:[{name:'codex',title:'Codex',engine:'codex',available:true,models:[['m1','Model']],defaults:{fix:'m1'},timeout:1800}]};
main.innerHTML='<div id="agentSettings"></div>';
getHandler=url=>url==='/api/meta'?{agents:[]}:data;
'''
        r=subprocess.run(['node','-'],input=HARNESS+source+setup+'\n(async()=>{'+check+'})().catch(e=>{console.error(e);process.exitCode=1})',text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_edit_and_save_actual_payload(self):
        self.run_js(r'''
await agentSettingsLoad();assert.match(main.textContent,/命令已安装/);
await main.querySelector('[data-agent-edit="codex"]').onclick();
$('#agentTitle').value='团队';$('#agentModels').value='m2 Model Two';
$('#agentForm').querySelector('[data-agent-mode="fix"]').value='m2';
postHandler=()=>({...data,revision:'two'});await submit('#agentForm');
assert.equal(mutations[0].url,'/api/agent-settings');assert.equal(mutations[0].body.config.defaults.fix,'m2');
assert.deepEqual(mutations[0].body.config.models,[['m2','Model Two']]);
assert.match($('#agentSaveState').textContent,/已保存/);assert.equal(data.revision,'two');
''')

    def test_failure_preserves_form_and_member_does_not_request(self):
        self.run_js(r'''
await agentSettingsLoad();agentSettingsEdit(data,data.agents[0]);$('#agentTitle').value='保留输入';
postHandler=()=>{throw new Error('配置已被更新')};await submit('#agentForm');
assert.equal($('#agentTitle').value,'保留输入');assert.equal($('#agentSave').disabled,false);
assert.match($('#agentSaveState').textContent,/配置已被更新/);
S.meta.access.can_manage=false;requests.length=0;await agentSettingsLoad();assert.equal(requests.length,0);assert.match(main.textContent,/联系管理员/);
''')

    def test_load_error_and_readonly(self):
        self.run_js(r'''
getHandler=()=>{throw new Error('无权读取')};await agentSettingsLoad();assert.match(main.textContent,/无权读取/);assert.ok($('#agentRefresh'));
data.can_edit=false;agentSettingsEdit(data,data.agents[0]);assert.equal($('#agentSave'),null);assert.equal($('#agentModels').disabled,true);
''')

    def test_saved_result_survives_refresh_failure_and_create_becomes_update(self):
        self.run_js(r'''
await agentSettingsLoad();agentSettingsEdit(data,null);$('#agentName').value='new-codex';
postHandler=()=>({...data,revision:'two'});
getHandler=url=>{if(url==='/api/meta')throw Error('刷新失败');return data};await submit('#agentForm');
assert.equal(mutations[0].body.action,'create');assert.match($('#agentSaveState').textContent,/配置已保存；状态刷新失败/);
await submit('#agentForm');assert.equal(mutations[1].body.action,'update');assert.equal(mutations[1].body.revision,'two');
''')

    def test_cursor_create_uses_engine_without_codex_profile(self):
        self.run_js(r'''
await agentSettingsLoad();agentSettingsEdit(data,null);
$('#agentEngine').value='cursor';$('#agentEngine').onchange();
assert.equal($('#agentProfile').disabled,true);
$('#agentName').value='team-cursor';$('#agentTitle').value='Cursor';
postHandler=()=>({...data,revision:'two'});await submit('#agentForm');
assert.equal(mutations[0].body.config.engine,'cursor');
assert.equal('profile' in mutations[0].body.config,false);
assert.equal($('#agentEngine').disabled,true);
''')
