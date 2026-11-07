"""Current evidence and checkpoint references never inherit historical acceptance."""
import json
import os
import unittest
from unittest.mock import patch
from tests import test_external_candidates as fixtures
from tmh.platform import reform, reform_state


class ReformStateTest(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ExternalCandidateTest('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.P,self.p=self.fixture.P,self.fixture.p
        self.atlas={'built':'fixed','domains':[{'id':'sales','title':'Sales','tables':1}]}
        self.plan=reform.create(self.P.data_dir,'EXT',self.atlas,dict(title='Sales',goal='Full scope',
            source_version=self.fixture.sha,target_environment='fixture',criteria=['Preserve refunds'],
            scope_mode='selected',domains=['sales'],wave=1),'owner')

    def test_checkpoint_is_persistent_protected_and_does_not_assert_pass(self):
        with patch.object(self.P.flow,'submit'):
            reform.release(self.P,self.p,self.plan['id'],None,'owner')
        saved=reform.plan(self.P.data_dir,'EXT',self.plan['id'])
        cp=saved['checkpoint']
        self.assertEqual(cp['source_commit'],self.fixture.sha)
        self.assertEqual(cp['verification'],'not_checked')
        self.assertEqual(cp['contract']['criteria'],['Preserve refunds'])
        refs=self.fixture.git('for-each-ref','--format=%(objectname)','refs/webuddy/reforms/'+saved['uid']+'/checkpoints')
        self.assertIn(self.fixture.sha,refs)
        preflight=reform_state.checkpoint_preflight(self.P,self.p,saved)
        self.assertEqual(preflight['status'],'accessible')
        saved['target_environment']='different'
        self.assertIn('target_environment',reform_state.checkpoint_preflight(self.P,self.p,saved)['changed_inputs'])
        with patch.object(reform_state,'test_configuration',return_value='different-test-profile'):
            self.assertIn('test_configuration',reform_state.checkpoint_preflight(self.P,self.p,saved)['changed_inputs'])
        saved['checkpoint']['source_commit']='f'*40
        preflight=reform_state.checkpoint_preflight(self.P,self.p,saved)
        self.assertEqual(preflight['status'],'blocked')
        self.assertIn('f'*40,preflight['blocked'][0])

    def test_verify_status_without_code_is_not_ready_for_acceptance(self):
        ticket=self.P.store.update_ticket(self.fixture.ticket['id'],'fixture',status='verify')
        current=reform_state.ticket(self.P,self.p,ticket)
        self.assertEqual(current['evidence_validity'],'not_checked')
        self.assertEqual(current['label'],'待核对代码与当前证据')
        self.assertNotEqual(current['state'],'awaiting_acceptance')
        closed=self.P.store.update_ticket(ticket['id'],'fixture',status='closed')
        historical=reform_state.ticket(self.P,self.p,closed)
        self.assertTrue(historical['historical_acceptance'])
        self.assertEqual(historical['integrated_delivery'],'not_checked')
        self.assertEqual(historical['evidence_validity'],'not_checked')

    @unittest.skipUnless(os.name=='posix','supervised candidate verification requires POSIX')
    def test_real_candidate_verification_is_invalidated_by_configuration_and_history_remains(self):
        submitted=self.fixture.submit()
        verified=self.fixture.verify(submitted['candidate_id'])
        self.assertTrue(verified['verification_passed'])
        current=reform_state.ticket(self.P,self.p,self.P.store.ticket(self.fixture.ticket['id']))
        self.assertEqual(current['evidence_validity'],'valid')
        closed=self.P.store.update_ticket(self.fixture.ticket['id'],'fixture',status='closed')
        history=reform_state.ticket(self.P,self.p,closed)
        self.assertTrue(history['historical_acceptance'])
        self.assertEqual(history['evidence_validity'],'valid')
        original=(self.fixture.repo/'.tmh/config.json').read_text()
        conf=json.loads(original)
        conf['commands']['test']+=' --verbose'
        (self.fixture.repo/'.tmh/config.json').write_text(json.dumps(conf))
        stale=reform_state.ticket(self.P,self.p,closed)
        self.assertEqual(stale['evidence_validity'],'invalid')
        self.assertTrue(stale['historical_acceptance'])
        self.assertEqual(stale['integrated_delivery'],'not_checked')

    def test_external_accepted_candidate_is_preserved_in_checkpoint(self):
        submitted=self.fixture.submit()
        candidate=self.P.store.one('SELECT commit_sha FROM code_candidates WHERE id=?',(submitted['candidate_id'],))
        self.P.store.event(self.fixture.ticket['id'],'fixture','accept','synthetic fixed external acceptance',
            {'candidate':submitted['candidate_id'],'commit':candidate['commit_sha']})
        saved=dict(self.plan,items=[{'ticket':self.fixture.ticket['key'],'batch':1}])
        cp=reform_state.checkpoint(self.P,self.p,saved,'synthetic acceptance checkpoint')
        self.assertEqual(cp['items'][0]['commit'],candidate['commit_sha'])
        self.assertIn(candidate['commit_sha'],cp['available_commits'])

    def test_pause_prevents_new_run_but_keeps_existing_run_authority(self):
        from tmh.platform.reform_authority import run
        from tmh.platform.errors import ApiError
        with patch.object(self.P.flow,'submit'):
            first=reform.release(self.P,self.p,self.plan['id'],None,'owner')[0]
        saved=reform.plan(self.P.data_dir,'EXT',self.plan['id'])
        with reform._transaction(self.P.data_dir,self.P.store) as db:
            plans=reform._load(self.P.data_dir,'EXT',db)
            plans[0]['paused']='fixture paused'
            reform._save(self.P.data_dir,'EXT',plans,db)
        t=self.P.store.ticket(first)
        run(self.P.runner,self.p,t)
        with self.assertRaises(ApiError) as caught:
            run(self.P.runner,self.p,t,new_run=True)
        self.assertEqual(caught.exception.code,409)

    def test_pending_resume_blocks_missing_checkpoint_without_floating_head(self):
        with patch.object(reform,'_dispatch',side_effect=OSError('injected disconnect')):
            with self.assertRaises(OSError):
                reform.release(self.P,self.p,self.plan['id'],None,'owner')
        with reform._transaction(self.P.data_dir,self.P.store) as db:
            plans=reform._load(self.P.data_dir,'EXT',db)
            plans[0]['checkpoint']['source_commit']='e'*40
            reform._save(self.P.data_dir,'EXT',plans,db)
        with patch.object(self.P.flow,'submit') as submit:
            resumed=reform.resume(self.P,self.p,self.plan['id'],'owner')
            self.assertEqual(resumed['opened'],[])
            self.assertIn('检查点提交不可访问',resumed['blocked'])
            submit.assert_not_called()
