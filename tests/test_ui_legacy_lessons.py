"""Exercise the actual legacy vLearn entry point and shared lesson decisions."""
import shutil
import subprocess
import unittest

from test_ui_library import HARNESS
from test_ui_memory import SETUP
from test_ui_lesson_decisions import DECISION_SETUP
from tmh.platform.ui import JS
from tmh.platform.ui_memory import MEMORY_JS


LEGACY_SETUP = r"""
document.querySelectorAll=s=>main.querySelectorAll(s);document.querySelector=s=>main.querySelector(s);
const CSS={escape:s=>s},pageHead=(title,sub)=>'<h1>'+h(title)+'</h1><p>'+h(sub)+'</p>',agentOptions=()=>'',ago=s=>s,stPill=s=>h(s);
const notices=[];const toast=s=>notices.push(s);let prompted;const prompt2=(title,value,callback)=>{prompted=callback};
location.origin='https://example.invalid';S.meta.agents=[];
const legacyData=(lessons=[listed(currentSnapshot)])=>({batches:[],cases:[],lessons,alerts:{path:'/alerts',configured:false,tickets:[]},lesson_summary:{},shared_in:[],impact:{},running:false});
let legacyResponse=legacyData();getHandler=url=>url.endsWith('/learn')?legacyResponse:url.includes('/lessons/L1')?currentSnapshot:memoryResponse;
const mountLegacy=()=>{location.hash='#/learn';return vLearn()};
"""
LEGACY_JS = 'async function vLearn(){' + JS.split('async function vLearn(){', 1)[1].split('// ---------- full-project analysis:', 1)[0]


@unittest.skipUnless(shutil.which('node'), 'Node needed for shipped legacy lesson UI')
class LegacyLessonUiTests(unittest.TestCase):
    def run_js(self, checks):
        source = HARNESS + SETUP + DECISION_SETUP + LEGACY_SETUP + MEMORY_JS + LEGACY_JS
        result = subprocess.run([shutil.which('node'), '-'], input=source + '\n(async()=>{\n' + checks +
                                '\n})().catch(e=>{console.error(e);process.exitCode=1});', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_confirmation_uses_same_version_receipt_contract(self):
        self.run_js(r"""
await mountLegacy();await main.querySelector('[data-ls="L1"]').fire('click');assert.equal(mutations.length,1);
assert.equal(mutations[0].url,'/api/projects/APP/lessons/L1');assert.equal(mutations[0].body.action,'confirm');
assert.equal(mutations[0].body.expected_token,currentSnapshot.expected_token);assert.ok(mutations[0].body.request_id);
assert.ok(main.textContent.includes('不能用于财务'));assert.ok(main.textContent.includes('src/full-8.py'));
""")

    def test_late_legacy_read_cannot_paint_another_project(self):
        self.run_js(r"""
const barrier=later();getHandler=()=>barrier.promise;const reading=mountLegacy();S.proj='STD';main.innerHTML='<div id="otherProject">另一项目</div>';
barrier.resolve(legacyData());await reading;assert.equal($('#otherProject').textContent,'另一项目');assert.equal(mutations.length,0);
""")

    def test_memory_unknown_request_blocks_same_legacy_card_and_retries_original_route(self):
        self.run_js(r"""
await mount();postHandler=async()=>{throw new Error('响应未知')};await main.querySelector('[data-mem-act="lesson_confirm"]').fire('click');const original=JSON.stringify(mutations[0]);
await mountLegacy();const confirm=main.querySelector('[data-ls="L1"]');assert.equal(confirm.disabled,true);await confirm.fire('click');assert.equal(mutations.length,1);
await main.querySelector('[data-lesson-retry]').fire('click');assert.equal(mutations.length,2);assert.equal(JSON.stringify(mutations[1]),original);
""")

    def test_late_reason_callback_cannot_mutate_new_project(self):
        self.run_js(r"""
currentSnapshot=snapshot({status:'retired'});legacyResponse=legacyData();await mountLegacy();await main.querySelector('[data-ls="L1"]').fire('click');assert.equal(mutations.length,0);
S.proj='STD';await prompted('切换前的原因');assert.equal(mutations.length,0);
""")

    def test_legacy_dirty_edit_is_preserved_during_eval_refresh(self):
        self.run_js(r"""
legacyResponse={...legacyData(),running:true};await mountLegacy();const field=main.querySelector('[data-lf="L1"]').parent.querySelector('[data-lf="L1"]');
field.value='尚未保存的新正文';field.focus();getHandler=()=>({...legacyData(),running:false});await S.polls[0].fn();await Promise.resolve();
assert.equal(field.isConnected,true);assert.equal(field.value,'尚未保存的新正文');assert.equal(document.activeElement,field);
""")

    def test_legacy_restore_sends_distinct_action_with_complete_reason(self):
        self.run_js(r"""
currentSnapshot=snapshot({status:'retired'});legacyResponse=legacyData();await mountLegacy();await main.querySelector('[data-ls="L1"]').fire('click');await prompted(' 核对来源\r\n完整原因  ');
assert.equal(mutations[0].body.action,'restore');assert.equal(mutations[0].body.reason,' 核对来源\r\n完整原因  ');assert.equal(mutations[0].body.expected_token,currentSnapshot.expected_token);
""")

    def test_legacy_save_uses_only_its_own_card_fields(self):
        self.run_js(r"""
await mountLegacy();body.innerHTML='<textarea data-lf="L1" data-k="fix">别的页面</textarea>';main.querySelector('[data-lf="L1"]').value='新现象';await main.querySelector('[data-lsave="L1"]').fire('click');
assert.deepEqual(mutations[0].body.fields,{symptom:'新现象'});assert.equal(mutations[0].body.action,'edit');assert.equal([...LESSON_DECISIONS.pending.values()][0].phase,'recorded');
""")

    def test_legacy_contributor_is_not_promoted_to_manager(self):
        self.run_js(r"""
S.meta.access={role:'member'};globalThis.accessCanWrite=()=>true;globalThis.accessProjectRole=()=> 'contributor';await mountLegacy();const button=main.querySelector('[data-ls="L1"]');assert.equal(button.disabled,true);await button.fire('click');assert.equal(mutations.length,0);
""")
