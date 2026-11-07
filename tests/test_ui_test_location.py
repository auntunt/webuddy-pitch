import shutil
import subprocess
import unittest
from tmh.platform.ui import JS
from tests.test_ui_library import HARNESS


@unittest.skipUnless(shutil.which('node'), 'Node required')
class TestLocationUi(unittest.TestCase):
    def test_selection_save_and_failed_save_preserve_input(self):
        source = JS[JS.index('async function testbox(d)'):JS.index('function newProject()')]
        check = r'''
main.innerHTML='<div id="tbx"></div>';
await testbox({conf:{}});
assert.equal($('#tbMode').value,'local');assert.equal($('#tbRemote').hidden,true);
assert.equal($('#tbC').disabled,false);
$('#tbMode').value='testbox';$('#tbMode').onchange();
assert.equal($('#tbRemote').hidden,false);assert.equal($('#tbC').disabled,true);
$('#tbH').value='build-alias';$('#tbH').oninput();
postHandler=()=>{throw Error('保存失败')};await $('#tbS').onclick();
assert.equal($('#tbH').value,'build-alias');assert.equal($('#tbC').disabled,true);assert.equal(notices.at(-1),'保存失败');
postHandler=()=>({executor:'testbox',conf:{host:'build-alias'}});await $('#tbS').onclick();
assert.equal(mutations.at(-1).body.executor,'testbox');assert.equal($('#tbC').disabled,false);
$('#tbMode').value='local';$('#tbMode').onchange();
postHandler=()=>({executor:'local',conf:{}});await $('#tbS').onclick();
assert.equal(mutations.at(-1).body.host,'');assert.equal($('#tbMode').value,'local');
'''
        result = subprocess.run(['node','-'],input=HARNESS+'const notices=[];const toast=(message)=>notices.push(message);\n'+source+'\n(async()=>{'+check+'})().catch(e=>{console.error(e);process.exitCode=1})',text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
