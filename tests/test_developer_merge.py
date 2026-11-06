"""Real local Git transitions, synthetic verification and CI (not business proof)."""
import unittest
from unittest.mock import patch
from tests import test_team_workspace as fixtures
from tmh.platform import candidates, development, project_ci
from tmh.platform.errors import ApiError


class DeveloperMergeTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.TeamWorkspaceTest('runTest');self.addCleanup(self.f.doCleanups);self.f.setUp()
        self.P=self.f.P;self.key=self.f.ticket['key']
        state=development.act(self.P,'agent:member:alice','start',{'ticket':self.key,'request_id':'select'})
        state=development.act(self.P,'agent:member:alice','propose',{'ticket':self.key,'request_id':'proposal',
            'revision':state['revision'],'summary':'Persist saved record','design':'Write and reload','test_plan':'Save then reload',
            'criteria':[{'id':'AC1','text':'保存后仍存在','check':'创建并刷新核对'}],'questions':[]})
        development.act(self.P,'alice','confirm',{'ticket':self.key,'request_id':'confirm',
            'revision':state['revision'],'digest':state['digest']},human=True)
        self.f.candidate();self.f.synthetic_checks();self.f.assess()
        current=candidates.view(self.P,self.f.cid)
        self.f.action('review','bob',candidate_id=self.f.cid,evidence_hash=current['evidence_hash'],decision='accept',note='Synthetic independent review')
        project_ci.save(self.P.data_dir,'TEAM',{'revision':project_ci.configuration(self.P.data_dir,'TEAM')['revision'],
            'config':{'repository':'example/repo','required_checks':['test']}})

    def merge(self,user='alice'):
        current=candidates.view(self.P,self.f.cid)
        return self.f.action('candidate_merge',user,candidate_id=self.f.cid,evidence_hash=current['evidence_hash'])

    def test_developer_merges_after_leader_and_ci_with_audited_commit(self):
        ci={'state':'pass','commit':self.f.commit,'checks':[{'name':'test','state':'pass'}]}
        with patch.object(project_ci,'check',return_value=ci):result=self.merge()
        self.assertEqual(self.f.git('rev-parse','HEAD'),self.f.commit)
        self.assertFalse(result['result']['pushed'])
        self.assertFalse(result['result']['deployed'])
        event=self.P.store.one("SELECT * FROM events WHERE kind='candidate_merge'")
        self.assertEqual(event['author'],'alice');self.assertEqual(event['data']['ci'],ci)
        self.assertNotEqual(self.P.store.ticket(self.key)['status'],'closed')

    def test_leader_cannot_replace_developers_final_confirmation(self):
        with self.assertRaises(ApiError):self.merge('bob')
        self.assertEqual(self.f.git('rev-parse','HEAD'),self.f.base)

    def test_failed_ci_keeps_main_unchanged(self):
        with patch.object(project_ci,'check',return_value={'state':'blocked'}),self.assertRaises(ApiError):self.merge()
        self.assertEqual(self.f.git('rev-parse','HEAD'),self.f.base)

    def test_leader_rejection_blocks_even_with_ci_success(self):
        current=candidates.view(self.P,self.f.cid)
        self.f.action('review','bob',candidate_id=self.f.cid,evidence_hash=current['evidence_hash'],decision='reject',note='Found bug')
        with patch.object(project_ci,'check',return_value={'state':'pass'}),self.assertRaises(ApiError):self.merge()
        self.assertEqual(self.f.git('rev-parse','HEAD'),self.f.base)

    def test_requirement_change_blocks_old_review_and_merge(self):
        self.P.store.comment(self.f.ticket['id'],'alice','New refund rule','new-rule')
        with patch.object(project_ci,'check',return_value={'state':'pass'}),self.assertRaises(ApiError):self.merge()
        self.assertEqual(self.f.git('rev-parse','HEAD'),self.f.base)

    def test_http_confirmation_requires_real_personal_session_and_assignee(self):
        server=self.f.start_http()
        state=development.read(self.P.store,self.P.store.ticket(self.key))
        body={'action':'confirm','ticket':self.key,'revision':state['revision'],'digest':state['digest'],'request_id':'http-confirm'}
        path='/api/tickets/'+self.key+'/development'
        for user,headers in ((None,{'X-TMH-User':'alice'}),('alice',{'X-Webuddy-Agent':'codex'}),('bob',{})):
            with self.subTest(user=user,headers=headers):
                status,result=self.f.http(server,'POST',path,body,user=user,headers=headers)
                self.assertEqual(status,403,result)
        status,result=self.f.http(server,'POST',path,body,user='alice')
        self.assertEqual(status,200,result)
        self.assertEqual(result['confirmed_by'],'alice')

    def test_confirmed_criteria_are_used_and_answer_changes_invalidate_report_contract(self):
        from tmh.platform.project_tests import criteria_contract
        run=candidates._row(self.P,self.f.cid)['run_id']
        before=criteria_contract(self.P.data_dir,run)
        self.assertEqual(before['source'],'development')
        self.assertEqual(before['criteria'],self.f.args['criteria'])
        self.P.store.comment(self.f.ticket['id'],'alice','Changed scope','scope-change')
        self.assertNotEqual(criteria_contract(self.P.data_dir,run)['version'],before['version'])

    def test_terminal_login_and_read_use_real_signed_session(self):
        from tmh.developer_terminal import HumanClient
        server=self.f.start_http()
        client=HumanClient('http://127.0.0.1:'+str(server.server_port))
        client.request('POST','/login',{'username':'alice','password':'temporary-fixture-password','next':'/'},login=True)
        self.assertTrue(client.cookie.startswith('tmh_session='))
        state=client.request('GET','/api/tickets/'+self.key+'/development')
        self.assertEqual(state['state'],'confirmed')
        self.assertEqual(state['work']['assignment']['assignee'],'alice')
