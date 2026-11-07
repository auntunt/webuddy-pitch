"""Isolated batch gates; synthetic acceptance is fixture data, never a product action."""
import unittest
from unittest.mock import patch
from tests import test_external_candidates as fixtures
from tmh.platform import reform


class ReformIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ExternalCandidateTest('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.P,self.p=self.fixture.P,self.fixture.p
        atlas={'built':'fixed','domains':[{'id':str(i),'title':str(i),'tables':0} for i in range(2)]}
        self.plan=reform.create(self.P.data_dir,'EXT',atlas,dict(title='Two waves',goal='Preserve both modules',keep='No API changes',
            source_version=self.fixture.sha,target_environment='fixture',criteria=['Both modules work'],wave=1),'fixture-owner')
        self.dispatch=patch.object(self.P.flow,'submit')
        self.dispatch.start();self.addCleanup(self.dispatch.stop)

    def accepted_fixture(self,key,sha):
        t=self.P.store.ticket(key)
        self.P.store.event(t['id'],'fixture','adopt','fixture fixed commit',{'commit':sha})
        self.P.store.event(t['id'],'fixture','accept','synthetic unit fixture acceptance',{})
        return self.P.store.update_ticket(t['id'],'fixture',status='closed')

    def test_batch_registers_one_integration_and_next_uses_accepted_fixed_base(self):
        first=reform.release(self.P,self.p,self.plan['id'],None,'fixture-owner')[0]
        child=self.accepted_fixture(first,self.fixture.sha)
        opened=reform.outcome(self.P,self.p,child,True,'synthetic fixture')
        self.assertEqual(len(opened),1)
        integrated=self.P.store.ticket(opened[0])
        self.assertEqual(integrated['links']['reform']['role'],'integration')
        self.assertEqual(reform.outcome(self.P,self.p,child,True,'synthetic fixture'),[])
        self.assertEqual(len(self.P.store.tickets()),4) # fixture ticket + epic parent + child + integration
        with self.assertRaisesRegex(ValueError,'集成任务'):
            reform.release(self.P,self.p,self.plan['id'],None,'fixture-owner')
        fixed=self.accepted_fixture(integrated['key'],self.fixture.sha)
        # Isolate the gate from technical verification here; actual verification is tested separately.
        with patch('tmh.platform.reform_state.ticket',return_value={'evidence_validity':'valid'}):
            next_batch=reform.outcome(self.P,self.p,fixed,True,'synthetic integration fixture')
        self.assertEqual(len(next_batch),1)
        self.assertEqual(self.P.store.ticket(next_batch[0])['links']['base'],self.fixture.sha)
        saved=reform.plan(self.P.data_dir,'EXT',self.plan['id'])
        self.assertEqual(saved['batch'],2)
        self.assertEqual(len(saved['integrations']),1)

    def test_paused_fixed_batch_completion_resumes_integration_then_one_next_part(self):
        first=reform.release(self.P,self.p,self.plan['id'],None,'fixture-owner')[0]
        def pause():
            with reform._transaction(self.P.data_dir,self.P.store) as db:
                plans=reform._load(self.P.data_dir,'EXT',db)
                plans[0]['paused']='synthetic pause: current executor may continue'
                reform._save(self.P.data_dir,'EXT',plans,db)
        pause()
        self.assertEqual(reform.outcome(self.P,self.p,self.accepted_fixture(first,self.fixture.sha),True,'fixture'),[])
        registered=reform.resume(self.P,self.p,self.plan['id'],'fixture-owner')
        self.assertEqual(len(registered['opened']),1)
        integration=self.P.store.ticket(registered['opened'][0])
        self.assertEqual(integration['links']['reform']['role'],'integration')
        self.assertEqual(reform.resume(self.P,self.p,self.plan['id'],'fixture-owner')['opened'],[])
        pause()
        accepted=self.accepted_fixture(integration['key'],self.fixture.sha)
        with patch('tmh.platform.reform_state.ticket',return_value={'evidence_validity':'valid'}):
            self.assertEqual(reform.outcome(self.P,self.p,accepted,True,'fixture'),[])
            resumed=reform.resume(self.P,self.p,self.plan['id'],'fixture-owner')
            self.assertEqual(len(resumed['opened']),1)
            self.assertEqual(self.P.store.ticket(resumed['opened'][0])['links']['base'],self.fixture.sha)
            self.assertEqual(reform.resume(self.P,self.p,self.plan['id'],'fixture-owner')['opened'],[])
        saved=reform.plan(self.P.data_dir,'EXT',self.plan['id'])
        self.assertEqual(saved['batch'],2)
        self.assertEqual(len(saved['integrations']),1)

    def test_closed_integration_without_current_evidence_never_releases_next_batch(self):
        first=reform.release(self.P,self.p,self.plan['id'],None,'fixture-owner')[0]
        opened=reform.outcome(self.P,self.p,self.accepted_fixture(first,self.fixture.sha),True,'fixture')
        done=self.accepted_fixture(opened[0],self.fixture.sha)
        self.assertEqual(reform.outcome(self.P,self.p,done,True,'fixture'),[])
        current=reform.view(self.P,self.p,reform.plan(self.P.data_dir,'EXT',self.plan['id']))
        self.assertIn('当前验证',current['blocked'])
        self.assertEqual(current['batch'],1)

    def test_final_integration_waits_for_whole_acceptance_and_rejection_creates_linked_repair(self):
        # Use a one-domain plan to isolate the final boundary.
        with reform._transaction(self.P.data_dir,self.P.store) as db:
            plans=reform._load(self.P.data_dir,'EXT',db)
            plans[0]['items']=plans[0]['items'][:1]
            reform._save(self.P.data_dir,'EXT',plans,db)
        first=reform.release(self.P,self.p,self.plan['id'],None,'fixture-owner')[0]
        opened=reform.outcome(self.P,self.p,self.accepted_fixture(first,self.fixture.sha),True,'fixture')
        integrated=self.accepted_fixture(opened[0],self.fixture.sha)
        with patch('tmh.platform.reform_state.ticket',return_value={'evidence_validity':'valid'}):
            self.assertEqual(reform.outcome(self.P,self.p,integrated,True,'fixture'),[])
            saved=reform.plan(self.P.data_dir,'EXT',self.plan['id'])
            parent=self.P.store.ticket(saved['parent'])
            self.assertEqual(parent['status'],'verify')
            self.assertNotEqual(parent['status'],'closed')
            self.assertEqual(parent['links']['reform_integration_commit'],self.fixture.sha)
            from tmh.platform.reform_delivery import guard
            self.assertEqual(guard(self.P,parent),self.fixture.sha)
            self.P.store.event(parent['id'],'fixture','reject','synthetic cross-module failure',{})
            parent=self.P.store.update_ticket(parent['id'],'fixture',status='doing')
            repair=reform.outcome(self.P,self.p,parent,False,'Cross-module refund regression')
            self.assertEqual(len(repair),1)
            replay=reform.outcome(self.P,self.p,parent,False,'Cross-module refund regression')
            self.assertEqual(replay,[])
        saved=reform.plan(self.P.data_dir,'EXT',self.plan['id'])
        self.assertFalse(saved['overall']['passed'])
        self.assertEqual(saved['batch'],2)
        self.assertIn('Cross-module refund regression',self.P.store.ticket(repair[0])['body'])
        self.assertEqual(self.P.store.ticket(repair[0])['links']['base'],self.fixture.sha)

    def test_invalid_evidence_blocks_pass_but_not_explicit_rejection(self):
        from tmh.platform.reform_delivery import guard
        with reform._transaction(self.P.data_dir,self.P.store) as db:
            plans=reform._load(self.P.data_dir,'EXT',db)
            from tmh.platform.reform_delivery import ensure
            ensure(self.P,self.p,plans[0],'fixture')
            reform._save(self.P.data_dir,'EXT',plans,db)
        saved=reform.plan(self.P.data_dir,'EXT',self.plan['id'])
        parent=self.P.store.ticket(saved['parent'])
        with self.assertRaisesRegex(ValueError,'固定集成'):
            guard(self.P,parent)
        self.assertIsNone(guard(self.P,parent,passed=False))

    def test_shared_signoff_refuses_parent_without_current_integration(self):
        from tmh.platform import signoff
        from tmh.platform.errors import ApiError
        with reform._transaction(self.P.data_dir,self.P.store) as db:
            plans=reform._load(self.P.data_dir,'EXT',db)
            from tmh.platform.reform_delivery import ensure
            ensure(self.P,self.p,plans[0],'fixture')
            reform._save(self.P.data_dir,'EXT',plans,db)
        saved=reform.plan(self.P.data_dir,'EXT',self.plan['id'])
        with self.assertRaises(ApiError) as caught:
            signoff.record_accept(self.P,self.P.store.ticket(saved['parent']),'fixture',True,'synthetic test')
        self.assertEqual(caught.exception.code,409)
        self.assertFalse(any(e['kind']=='accept' for e in self.P.store.events(self.P.store.ticket(saved['parent'])['id'])))

    def test_fixed_lead_does_not_move_integration_base_to_unaccepted_branch_tip(self):
        plan=reform.create(self.P.data_dir,'EXT',{'built':'fixed','domains':[{'id':'one','title':'One','tables':0}]},
            dict(title='Fixed lead',goal='Keep authorized base',source_version=self.fixture.base,target_environment='fixture',
                criteria=['Only accepted code'],lead={'title':'Foundation','body':'Preserve the fixed baseline'},wave=1),'fixture-owner')
        lead=reform.release(self.P,self.p,plan['id'],None,'fixture-owner')[0]
        t=self.P.store.ticket(lead)
        self.P.store.event(t['id'],'fixture','adopt','synthetic fixed lead',{'commit':self.fixture.sha,'branch':'main'})
        self.P.store.event(t['id'],'fixture','accept','synthetic lead acceptance',{})
        t=self.P.store.update_ticket(t['id'],'fixture',status='closed')
        (self.fixture.repo/'app.py').write_text('VALUE = 3\n')
        self.fixture.git('commit','-am','unaccepted branch movement fixture')
        unaccepted=self.fixture.git('rev-parse','HEAD')
        self.assertNotEqual(unaccepted,self.fixture.sha)
        opened=reform.outcome(self.P,self.p,t,True,'synthetic fixed lead acceptance')
        self.assertEqual(len(opened),1)
        integration=self.P.store.ticket(opened[0])
        self.assertEqual(integration['links']['base'],self.fixture.base)
        saved=reform.plan(self.P.data_dir,'EXT',plan['id'])
        self.assertEqual(saved['integrations'][0]['inputs'],[self.fixture.sha])
        self.assertNotIn(unaccepted,saved['checkpoint']['available_commits'])
