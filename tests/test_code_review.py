import hashlib
import json
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from tests import test_run_handoff as helpers
from tmh.platform import code_review
from tmh.platform.fixloop import recheck, recheck_operations, verified
from tmh.platform.agents import worktree_diff


class CoverageTest(unittest.TestCase):
    def loop(self, answers):
        return SimpleNamespace(diagnose_part=mock.Mock(side_effect=answers), agent='writer',
                               agents={'diagnose': 'reviewer'}, models={'diagnose': 'model'}, wt='fixture')

    def test_complete_large_diff_and_last_part_failure(self):
        diff = 'diff --git a/a b/a\n' + '+long line\n' * 4000 + 'diff --git a/b b/b\n+last bug\n'
        chunks = code_review.parts(diff)
        self.assertEqual(''.join(x[1] for x in chunks), diff)
        self.assertTrue(all(len(x[1]) <= 14000 for x in chunks))
        answers = [{'verdict': 'pass', 'blocking': []} for _ in chunks]
        answers[-1] = {'verdict': 'fail', 'blocking': [{'ac': 'A1', 'scenario': 'last bug'}]}
        loop = self.loop(answers)
        with mock.patch('tmh.platform.fixloop.git', return_value='a' * 40):
            result = code_review.review(loop, diff, [], '', None)
        self.assertEqual(result['verdict'], 'fail')
        self.assertTrue(result['review']['complete'])
        self.assertEqual(result['review']['diff_sha256'], hashlib.sha256(diff.encode()).hexdigest())
        self.assertIn('last bug', loop.diagnose_part.call_args.args[0])
        self.assertEqual(result['blocking'][0]['scenario'], 'last bug')

    def test_partial_unknown_and_binary_never_pass(self):
        for diff, answer in [('diff --git a/a b/a\n'+'x'*16000, {'verdict':'unknown'}),
                             ('diff --git a/a b/a\nGIT binary patch\nliteral 10', {'verdict':'pass'})]:
            loop = self.loop([answer] * len(code_review.parts(diff)))
            with mock.patch('tmh.platform.fixloop.git', return_value='a'*40):
                result = code_review.review(loop, diff, [], '', None)
            self.assertEqual(result['verdict'], 'unknown')
            self.assertFalse(result['review']['complete'])


class ManualReviewTest(unittest.TestCase):
    def setUp(self):
        fixture = helpers.RunHandoffTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.data, self.runner, self.store = fixture.data, fixture.runner, fixture.store
        self.root, self.run, self.wt, self.folder, self.diff = fixture.recheck_fixture('pass')
        self.rid = self.run['id']
        self.store.x('UPDATE runs SET agent=? WHERE id=?', ('review-fixture', self.rid))
        script = self.data / 'review-fixture.py'
        script.write_text("import json\nprint('```tmh-diag\\n'+json.dumps({'verdict':'pass','blocking':[], 'evidence':'SYNTHETIC review process'})+'\\n```')\n")
        (self.data / 'agents.json').write_text(json.dumps({'review-fixture': {'cmd':[sys.executable, str(script)], 'run_timeout':15}}))
        self.addCleanup(self.cleanup)

    def cleanup(self):
        ops = getattr(self.runner, 'rechecks', None)
        if ops:
            for oid in list(ops.runner.owners):
                ops.runner._release(oid)
            for guard in ops._source_guards.values():
                guard.__exit__(None, None, None)
            ops._source_guards.clear()

    def test_real_review_only_preserves_tests_and_source_output(self):
        tested = recheck(self.runner, self.rid)
        before = self.store.run(self.rid)
        result = recheck(self.runner, self.rid, kind='review')
        self.assertTrue(result['verification_current'])
        self.assertEqual(result['commands'], tested['commands'])
        self.assertEqual(result['check'], 'pass')
        self.assertEqual(result['diagnosis']['verdict'], 'pass')
        self.assertTrue(result['diagnosis']['review']['complete'])
        self.assertEqual(result['diagnosis']['review']['writer'], 'review-fixture')
        self.assertEqual(self.store.run(self.rid), before)
        self.assertEqual(worktree_diff(self.wt), self.diff)
        operation = recheck_operations(self.runner).status(self.rid)
        self.assertEqual(operation['source']['kind'], 'review')
        self.assertEqual(len(operation['lifecycle']['attempts']), 1)
        self.assertTrue(operation['lifecycle']['attempts'][0]['cleanup']['complete'])

    def test_changed_code_does_not_inherit_old_test_pass(self):
        recheck(self.runner, self.rid)
        (self.wt/'app.py').write_text('VALUE = 2\n')
        result = recheck(self.runner, self.rid, kind='review')
        self.assertEqual(result['check'], 'skip')
        self.assertEqual(result['commands'], [])
        self.assertEqual(result['diagnosis']['verdict'], 'pass')
        self.assertNotIn('diagnosis_invalidated', result)
        self.assertEqual(result['checked_diff'], worktree_diff(self.wt))

    def test_all_executes_tests_and_review(self):
        result = recheck(self.runner, self.rid, kind='all')
        self.assertEqual(result['check'], 'pass')
        self.assertTrue(result['commands'])
        self.assertTrue(result['diagnosis']['review']['complete'])
        self.assertEqual(verified(self.data, self.rid), result)

    def test_configured_build_preserves_quoted_paths_and_arguments(self):
        import os
        import shlex
        from tmh import config
        script = self.root / 'check with spaces.py'
        script.write_text('import sys\nassert sys.argv[1] == "value with spaces"\nprint("quoted build passed")\n')
        argv = [sys.executable, str(script), 'value with spaces']
        cfg = config.load(self.root)
        cfg['commands']['build'] = subprocess.list2cmdline(argv) if os.name == 'nt' else shlex.join(argv)
        config.save(self.root, cfg)
        result = recheck(self.runner, self.rid)
        self.assertEqual(result['check'], 'pass', result)
        self.assertIn('quoted build passed', result['commands'][0]['output'])

    def test_build_configuration_change_invalidates_before_review_and_prevents_reuse(self):
        from tmh import config
        tested = recheck(self.runner, self.rid)
        cfg = config.load(self.root)
        cfg['commands']['build'] = 'python -c "raise SystemExit(23)"'
        config.save(self.root, cfg)
        stale = verified(self.data, self.rid)
        self.assertFalse(stale['verification_current'])
        self.assertEqual(stale['previous_current_verification']['commands'], tested['commands'])
        result = recheck(self.runner, self.rid, kind='review')
        self.assertEqual(result['check'], 'skip')
        self.assertEqual(result['commands'], [])
        self.assertFalse(result['test_reuse']['reused'])
        self.assertEqual(result['diagnosis']['verdict'], 'pass')

    def test_configuration_changed_during_review_cannot_publish_current_pass(self):
        recheck(self.runner, self.rid)
        config_path = self.root / '.tmh' / 'config.json'
        with (self.data/'review-fixture.py').open('a') as f:
            f.write("from pathlib import Path\np=Path(%r)\nv=json.loads(p.read_text())\nv['commands']['build']='exit 23'\np.write_text(json.dumps(v))\n" % str(config_path))
        result = recheck(self.runner, self.rid, kind='review')
        self.assertFalse(result['verification_current'])
        self.assertEqual(result['check'], 'unknown')

    def test_review_failure_does_not_reuse_previous_pass(self):
        (self.data/'review-fixture.py').write_text('raise SystemExit(7)\n')
        result = recheck(self.runner, self.rid, kind='review')
        self.assertEqual(result['diagnosis']['verdict'], 'unknown')
        self.assertFalse(result['diagnosis']['review']['complete'])

    def test_reviewer_modifying_code_cannot_publish_pass(self):
        with (self.data/'review-fixture.py').open('a') as stream:
            stream.write("from pathlib import Path\nPath('app.py').write_text('VALUE = 5\\n')\n")
        result = recheck(self.runner, self.rid, kind='review')
        self.assertEqual(result['check'], 'fail')
        self.assertEqual(result['diagnosis'], {})
        self.assertTrue(result['code_changed_during_check'])


class ReviewUiTest(unittest.TestCase):
    def test_baseline_blocked_and_unexecuted_are_visible_without_signoff_claim(self):
        from tests.test_ui_run_preview import RunPreviewUiTest
        RunPreviewUiTest().run_js(r'''
const r=detail(7);
r.verification={check:'fail',verdict:'unknown',outcome:'blocked',baseline:{base:'original',state:'fail',commands:[{output:'original assertion failed'}]},commands:[]};
const html=runVerificationRecordHtml(r);
assert.ok(html.includes('验证受阻，补齐条件后重测'));
assert.ok(html.includes('修改前基线 · 未通过'));
assert.ok(html.includes('original assertion failed'));
r.verification.scope={declared:{new:['A1'],regression:['A2'],invariants:['A3'],gaps:[]},reviewed:{}};
assert.ok(runVerificationRecordHtml(r).includes('受影响的旧功能'));
assert.ok(!html.includes('可提交人工业务验收'));
const report={criteria:[],criterion_evidence:{},stages:[{id:'timeout',status:'fail',execution_status:'blocked',required:true,cases:[],output:'timed out'}, {id:'dependent',status:'fail',execution_status:'not_run',required:true,cases:[],output:''}],uncovered_criteria:[],status:'fail'};
const stages=projectTestsReportHtml([{project_tests:report}]);
assert.ok(stages.includes('timeout · 验证受阻'));
assert.ok(stages.includes('dependent · 未执行'));
''', controller=True)

    def test_manual_buttons_share_lock_and_send_distinct_actions(self):
        from tests.test_ui_run_preview import RunPreviewUiTest
        RunPreviewUiTest().run_js(r'''
let current=detail(7),state={running:false};
getHandler=async url=>url.endsWith('/recheck')?state:current;
for(const [selector,kind]of [['[data-run-review]','review'],['[data-run-verify-all]','all'],['[data-run-recheck]','tests']]){
 state={running:false};await showRun(7);let count=0;const deferred=later();
 postHandler=(url,data)=>{assert.equal(url,'/api/runs/7/recheck');assert.equal(data.kind,kind);count++;return deferred.promise};
 const button=body.querySelector(selector),pending=button.onclick();await button.onclick();assert.equal(count,1);
 state={running:true};deferred.resolve({started:true});await pending;
 assert.equal(body.querySelector('[data-run-review]').disabled,true);
 assert.equal(body.querySelector('[data-run-verify-all]').disabled,true);
}
''', controller=True)
