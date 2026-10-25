"""Explicit personal click binds its typed reason to the selected native report."""
import shutil
import unittest
import test_ui_learning as F


@unittest.skipUnless(shutil.which('node'),'Node required for shipped UI behavior')
class NativeLearningUiTests(unittest.TestCase):
    run_js=F.LearningUiTests.run_js

    def test_personal_submit_binds_exact_native_report_and_retains_plain_reason(self):
        self.run_js(r'''
const ref={schema:'native-learning-job-v1',root_pool:'a'.repeat(64),native_report_sha256:'b'.repeat(64)};
learningDetails.set(R1,learningRevision(R1,{revision:{...learningRevision().revision,kind:'lesson'},jobs:[learningJob({id:'NJ'+'c'.repeat(40),kind:'native_evaluate',options:{native_evaluation:ref},result:{passed:true}})]}));
await openLearning();assert.equal(mutations.length,0);assert.ok($('#learningDetailJobs').textContent.includes('原生文本双臂评测'));
$('#learningReason').value='本人核对确切报告，仅适用当前版本';$('#learningDecisionJob').value='NJ'+'c'.repeat(40);await submit('#learningDecision');
assert.equal(mutations.length,1);assert.deepEqual(JSON.parse(mutations[0].body.reason),{schema:'native-bc-decision-reference-v1',root_pool:ref.root_pool,native_report_sha256:ref.native_report_sha256,reason:'本人核对确切报告，仅适用当前版本'});
''')

    def test_missing_native_reference_is_not_silently_adopted(self):
        self.run_js(r'''
learningDetails.set(R1,learningRevision(R1,{jobs:[learningJob({id:'NJ'+'c'.repeat(40),kind:'native_evaluate',options:{},result:{passed:true}})]}));
await openLearning();$('#learningReason').value='缺失报告不能通过';$('#learningDecisionJob').value='NJ'+'c'.repeat(40);await submit('#learningDecision');assert.equal(mutations.length,0);assert.ok($('#learningNotice').textContent.includes('引用不完整'));
''')
