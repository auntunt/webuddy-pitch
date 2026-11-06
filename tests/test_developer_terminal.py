"""Human terminal actions preserve the server's review contract."""
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tmh import developer_terminal as terminal, agent_contract
from tmh.workbench_client import ClientError


class DeveloperTerminalTest(unittest.TestCase):
    def run_action(self, action, answers, *, ci='pass', candidate_id=7):
        candidate={'id':7,'evidence_hash':'a'*64,'verification_hash':'b'*64,'preview_hash':'c'*64,
                   'criteria':[{'id':'A1','text':'Refund correct','check':'Read saved amount'}]}
        calls=[]
        class Client:
            prefix='/t/example'
            def __init__(self,endpoint):pass
            def request(self,method,path,body=None,**kwargs):
                calls.append((method,path,body))
                if kwargs.get('login'):return None
                if method=='GET':
                    if '/ci?' in path:return {'state':ci}
                    return {'work':{'candidate':candidate}}
                op='candidate_decide' if body['action']=='review' else body['action']
                if op in ('candidate_decide','candidate_assess'):
                    agent_contract.validate(op,{k:v for k,v in body.items() if k not in ('action','ticket')})
                return {'ok':True}
        args=SimpleNamespace(command='develop',endpoint='https://example.test/t/example',user='leader',
                             ticket='ERP-1',action=action,candidate_id=candidate_id)
        with patch.object(terminal,'HumanClient',Client),patch('sys.stdin.isatty',return_value=True),\
             patch('builtins.input',side_effect=answers),patch.object(terminal.getpass,'getpass',return_value='private'),\
             patch('sys.stdout',new_callable=io.StringIO) as output:
            terminal.run(args)
            self.assertNotIn('private',output.getvalue())
        return calls

    def test_leader_approval_uses_accept_and_bound_evidence(self):
        calls=self.run_action('review',['REVIEW ERP-1 '+ 'a'*12,'Read diff and verified refund'])
        body=calls[-1][2]
        self.assertEqual(body['decision'],'accept')
        self.assertEqual(body['evidence_hash'],'a'*64)
        self.assertEqual(body['candidate_id'],7)

    def test_leader_rejection_preserves_reason(self):
        calls=self.run_action('reject',['REJECT ERP-1 '+'a'*12,'Refund rounding is incorrect'])
        self.assertEqual(calls[-1][2]['decision'],'reject')
        self.assertEqual(calls[-1][2]['note'],'Refund rounding is incorrect')

    def test_assessment_keeps_unknown_and_exact_verification(self):
        calls=self.run_action('assess',['unknown','Database unavailable','Need database','ASSESS ERP-1 '+'a'*12])
        body=calls[-1][2]
        self.assertEqual(body['results'][0]['status'],'unknown')
        self.assertEqual(body['verification_hash'],'b'*64)
        self.assertEqual(body['preview_hash'],'c'*64)

    def test_cancel_does_not_submit(self):
        calls=self.run_action('review',['no'])
        self.assertFalse(any(path=='/api/team' for _,path,_ in calls))

    def test_stale_candidate_rejected_before_confirmation(self):
        with self.assertRaises(ClientError):self.run_action('review',[],candidate_id=6)

    def test_missing_ci_prevents_merge(self):
        with self.assertRaises(ClientError):self.run_action('merge',[],ci='blocked')

    def test_empty_reason_cannot_approve(self):
        with self.assertRaises(ClientError):self.run_action('review',['REVIEW ERP-1 '+'a'*12,'  '])

    def test_pipe_cannot_submit_human_actions(self):
        with patch('sys.stdin.isatty',return_value=False),self.assertRaises(ClientError):
            terminal.run(SimpleNamespace())
