"""Durable clarification and human confirmation bind the candidate requirement."""
import unittest
from tmh.platform import development, agent_api
from tmh.platform.errors import ApiError
from tests import test_external_candidates as fixtures


class DevelopmentTest(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ExternalCandidateTest('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.P=self.fixture.P
        self.key=self.fixture.ticket['key']
        self.P.store.update_ticket(self.fixture.ticket['id'],'fixture',assignee='developer')
        self.n=0

    def act(self,action,**body):
        self.n+=1
        return self.fixture.call('development_'+action,dict(ticket=self.key,request_id='dev-'+str(self.n),**body))

    def propose(self):
        state=self.act('start')
        self.assertEqual(state['next_action'],'development_propose')
        return self.act('propose',revision=state['revision'],summary='Refund correctly',design='Validate before write',
            test_plan='Check saved amount and duplicate submission',criteria=self.fixture.criteria,
            questions=[{'id':'amount','question':'Expected amount?','options':['12.50','Other'],'required':True}])

    def confirm(self,state):
        return development.act(self.P,'developer','confirm',dict(ticket=self.key,revision=state['revision'],
             digest=state['digest'],request_id='human-'+str(self.n)),human=True)

    def test_historical_prompt_never_reads_current_ticket_confirmation(self):
        from unittest.mock import patch
        from tmh.platform.agents import build_prompt
        ticket = self.P.store.ticket(self.key)
        project = self.P.store.project(ticket['project_id'])
        historical = {k:v for k,v in ticket.items() if k != 'id'}
        with patch.object(development, 'read', side_effect=AssertionError('history must not read live confirmation')):
            prompt = build_prompt(self.P.store, project, historical, 'plan', historical_case=True)
        self.assertIn(ticket['title'], prompt)
        with self.assertRaises(KeyError):
            build_prompt(self.P.store, project, historical, 'plan')

    def test_roundtrip_answers_and_human_confirmation(self):
        proposed=self.propose()
        with self.assertRaises(ApiError):self.confirm(proposed)
        state=self.act('answer',revision=proposed['revision'],answers=[{'question_id':'amount','answer':'12.50','resolved':True}])
        self.assertEqual(state['state'],'awaiting_confirmation')
        confirmed=self.confirm(state)
        self.assertEqual(confirmed['state'],'confirmed')
        self.assertEqual(confirmed['confirmed_by'],'developer')
        self.assertEqual(self.fixture.call('development_get',{'ticket':self.key})['digest'],confirmed['digest'])

    def test_agent_cannot_confirm(self):
        state=self.propose()
        with self.assertRaises(ApiError):
            development.act(self.P,'agent','confirm',{'ticket':self.key,'revision':state['revision'],
                 'digest':state['digest'],'request_id':'forged'})

    def test_unresolved_answer_does_not_unlock(self):
        state=self.propose()
        state=self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'Not known','resolved':False}])
        self.assertEqual(state['state'],'clarifying')
        with self.assertRaises(ApiError):self.confirm(state)

    def test_stale_revision_does_not_overwrite(self):
        state=self.propose()
        self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'12.50','resolved':True}])
        with self.assertRaises(ApiError):
            self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'1','resolved':True}])

    def test_candidate_blocked_until_confirmation_and_bound_to_it(self):
        state=self.propose()
        with self.assertRaises(ApiError):self.fixture.submit()
        state=self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'12.50','resolved':True}])
        self.confirm(state)
        before=agent_api._requirement(self.P.store.ticket(self.key),self.P.store)
        candidate=self.fixture.submit(request_id="confirmed-submit")
        from tmh.platform.candidates import view
        self.assertTrue(view(self.P,candidate['candidate_id'])['current'])
        self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'13','resolved':True}])
        self.assertNotEqual(before,agent_api._requirement(self.P.store.ticket(self.key),self.P.store))
        from tmh.platform.candidates import view
        self.assertFalse(view(self.P,candidate['candidate_id'])['current'])

    def test_changed_source_requires_answer_again(self):
        state=self.propose()
        state=self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'12.50','resolved':True}])
        self.confirm(state)
        self.P.store.event(self.fixture.ticket['id'],'customer','comment','Changed refund rule')
        old=development.read(self.P.store,self.P.store.ticket(self.key))
        self.assertEqual(old['state'],'stale')
        payload=old['payload']
        revised=self.act('propose',revision=old['revision'],**{k:payload[k] for k in ('summary','design','test_plan','criteria','questions')})
        self.assertEqual(revised['state'],'clarifying')
        self.assertFalse(revised['payload']['answers'])
