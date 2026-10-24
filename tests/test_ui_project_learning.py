"""Current authorized project links to its narrow learning reader."""
import shutil
import subprocess
import unittest

from test_ui_library import HARNESS
from test_ui_learning import SETUP
from tmh.platform.ui_workspace import WORKSPACE_JS
from tmh.platform.ui_memory import MEMORY_JS
from tmh.platform.ui_learning import LEARNING_JS


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for shipped project navigation checks")
class ProjectLearningUiTests(unittest.TestCase):
    def run_js(self, checks):
        setup = r"""
const apiErr=message=>Error(message);
getHandler=url=>url.startsWith('/api/workspace?')?{counts:{team:0},items:[],has_more:false}:learningData;
const follow=async link=>{const result=await link.fire('click');if(result!==false){location.hash=link.attrs.href;await vLearning()}return result};
"""
        result = subprocess.run([shutil.which("node"), "-"], input=HARNESS+SETUP+WORKSPACE_JS+MEMORY_JS+LEARNING_JS+setup+"\n(async()=>{\n"+checks+"\n})().catch(error=>{console.error(error);process.exitCode=1});", text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_current_project_link_uses_only_project_learning_without_organization_catalog(self):
        self.run_js(r"""
location.hash='#/projects/APP';S.scope='*';await vProjects('APP');
const link=$('#projectLearningLink');assert.ok(link,'authorized project needs a reachable learning entry');assert.equal(link.attrs.href,'#/memory/learning');
S.scope='STD';await follow(link);assert.equal(S.scope,'APP');assert.equal(scopeStorage.get('tmh.scope'),'APP');
assert.deepEqual(requests,['/api/workspace?project=APP&view=team','/api/learning?project=APP&kind=fact&q=']);assert.equal(mutations.length,0);
assert.ok($('#learningExperimentsOpen'));assert.ok(!requests.some(url=>url.startsWith('/api/memory')));
""")

    def test_detached_or_revoked_project_link_cannot_load_another_scope(self):
        self.run_js(r"""
location.hash='#/projects/APP';await vProjects('APP');const link=$('#projectLearningLink');assert.ok(link);
const prior=requests.length;location.hash='#/projects/STD';S.proj='STD';S.scope='STD';assert.equal(await follow(link),false);assert.equal(S.scope,'STD');assert.equal(requests.length,prior);
location.hash='#/projects/APP';S.proj='APP';S.projects=S.projects.filter(p=>p.key!=='APP');assert.equal(await follow(link),false);assert.equal(requests.length,prior);assert.equal(mutations.length,0);
""")

    def test_unavailable_project_has_no_learning_load(self):
        self.run_js(r"""
location.hash='#/projects/FOREIGN';await assert.rejects(vProjects('FOREIGN'),/没有这个项目/);assert.equal(requests.length,0);assert.equal($('#projectLearningLink'),null);assert.equal(mutations.length,0);
""")
