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
        self.P.store.update_ticket(self.fixture.ticket['id'],'fixture',assignee='developer',links=dict(self.P.store.ticket(self.key)['links'],base=self.fixture.base))
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
        confirmed = development.act(self.P,'developer','confirm',dict(ticket=self.key,revision=state['revision'],
             digest=state['digest'],request_id='human-'+str(self.n)),human=True)
        return development.act(self.P,'developer','execution',dict(ticket=self.key,revision=confirmed['revision'],digest=confirmed['digest'],mode='local',request_id='mode-'+str(self.n)),human=True)

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

    def choose(self,state,mode,actor='developer',request_id='choice'):
        return development.act(self.P,actor,'execution',dict(ticket=self.key,revision=state['revision'],
            digest=state['digest'],mode=mode,request_id=request_id),human=True)

    def test_choice_requires_current_human_confirmation_and_owner(self):
        state=self.propose()
        with self.assertRaises(ApiError):self.choose(state,'local')
        state=self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'12.50','resolved':True}])
        state=self.confirm(state)
        with self.assertRaises(ApiError):self.choose(state,'system',actor='someone-else')
        with self.assertRaises(ApiError):
            development.act(self.P,'agent','execution',dict(ticket=self.key,revision=state['revision'],digest=state['digest'],mode='system',request_id='forged-mode'))
        self.P.store.event(self.fixture.ticket['id'],'customer','comment','Changed rule')
        with self.assertRaises(ApiError):self.choose(state,'system')

    def test_explicit_choice_does_not_execute_and_replays(self):
        state=self.propose()
        state=self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'12.50','resolved':True}])
        state=self.confirm(state)
        before=agent_api._requirement(self.P.store.ticket(self.key),self.P.store)
        state=self.choose(state,'system')
        self.assertEqual(self.P.store.runs(ticket_id=self.fixture.ticket['id']),[])
        self.assertEqual(state['execution']['base_commit'],self.fixture.base)
        self.assertNotEqual(before,agent_api._requirement(self.P.store.ticket(self.key),self.P.store))
        self.assertTrue(self.choose(state,'system')['replayed'])
        with self.assertRaises(ValueError):development.require_execution(self.P.store,self.P.store.ticket(self.key),'local')
        self.assertTrue(development.require_execution(self.P.store,self.P.store.ticket(self.key),'system'))
        with self.assertRaises(ApiError):self.fixture.submit(request_id='wrong-mode')
        self.assertTrue(self.P.store.ticket(self.key)['links']['hold'])
        self.assertFalse(self.P.store.ticket(self.key)['links']['handwork'])

    def test_confirmation_without_choice_cannot_start_writer(self):
        state=self.propose()
        state=self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'12.50','resolved':True}])
        state=development.act(self.P,'developer','confirm',dict(ticket=self.key,revision=state['revision'],digest=state['digest'],request_id='confirm-only'),human=True)
        self.assertEqual(state['next_action'],'choose_execution')
        with self.assertRaises(ValueError):development.require_execution(self.P.store,self.P.store.ticket(self.key),'system')
        with self.assertRaises(ApiError):self.fixture.submit()

    def test_execution_baseline_uses_personal_git_scope(self):
        from unittest.mock import patch
        from tmh.platform import agents, project_git
        state=self.propose()
        state=self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'12.50','resolved':True}])
        state=self.confirm(state)
        original=agents.git
        def checked(*args,**kwargs):
            self.assertEqual(project_git.SCOPE.get()['user'],'developer')
            self.assertIs(project_git.SCOPE.get()['platform'],self.P)
            return original(*args,**kwargs)
        with patch.object(agents,'git',side_effect=checked):self.choose(state,'system')

    def test_reassignment_invalidates_execution_choice(self):
        state=self.propose()
        state=self.act('answer',revision=state['revision'],answers=[{'question_id':'amount','answer':'12.50','resolved':True}])
        self.confirm(state)
        self.P.store.update_ticket(self.fixture.ticket['id'],'fixture',assignee='new-developer')
        current=self.P.store.ticket(self.key)
        self.assertFalse(development.read(self.P.store,current)['execution']['current'])
        with self.assertRaises(ValueError):development.require_execution(self.P.store,current,'local')
