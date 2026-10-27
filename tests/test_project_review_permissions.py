"""Personal review identity, using disposable stores and public evidence only."""
from types import SimpleNamespace
import unittest
import os
import shutil
from pathlib import Path

from tmh import evidence
from tmh.platform import server, team, signoff
from tmh.platform.errors import ApiError
from tests import test_tenant_policy as fixture_module
from tests import test_tenant_gateway as gateway_fixture
from tmh.platform.tenant_runtime import TenantContext
from tmh.platform.store import Store


class ProjectReviewPermissionsTest(unittest.TestCase):
    def setUp(self):
        fixture = fixture_module.TenantPolicyTest('runTest')
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.P = fixture.P
        self.ticket = fixture.tickets['ALPHA']
        self.fixture = fixture
        team.schema(self.P)

    def request(self, actor, headers=None):
        return SimpleNamespace(h=SimpleNamespace(_who=actor, headers=headers or {}), user=actor)

    def assign(self, owner='alice', reviewer='bob'):
        old = team.assignment(self.P, self.P.store.ticket(self.ticket['id']))
        return team._assign(self.P, self.P.store.ticket(self.ticket['id']),
            dict(assignee=owner, reviewer=reviewer, revision=old['revision'], previous_assignee=old['assignee']), 'alice')

    def test_member_review_requires_explicit_independent_assignment(self):
        for actor in ('alice', 'bob'):
            with self.subTest(actor=actor), self.assertRaises(ApiError):
                server._human_action(self.P, self.request(actor), self.ticket)
        self.assign()
        self.assertEqual(server._human_action(self.P, self.request('bob'), self.ticket), 'bob')
        with self.assertRaises(ApiError):
            server._human_action(self.P, self.request('alice'), self.ticket)

    def test_reassignment_cannot_make_original_implementation_author_reviewer(self):
        run = self.P.store.create_run(self.ticket['project_id'], self.ticket['id'], 'codex', 'fix', 'alice', 'public fixture')
        # These are public fixture records, not actual model or test evidence.
        evidence.append(signoff.epath(self.P.data_dir, self.ticket['key']), 'pack', 'owner',
            {'snapshot': {'change': {'run': run['id']}}})
        self.assign(owner='bob', reviewer='alice')
        with self.assertRaisesRegex(ApiError, '实现'):
            server._human_action(self.P, self.request('alice'), self.ticket)
        with self.assertRaisesRegex(ApiError, '实现'):
            server._human_action(self.P, self.request('alice'), self.ticket, run=run)

    def test_forged_agent_identity_and_revoked_project_are_rejected(self):
        self.assign()
        with self.assertRaises(ApiError):
            server._human_action(self.P, self.request('bob', {'X-Webuddy-Agent': 'fixture'}), self.ticket)
        self.fixture.context.people['bob']['project_grants'] = {}
        with self.assertRaises(ApiError):
            server._human_action(self.P, self.request('bob'), self.ticket)

    def test_managed_agent_author_is_the_initiating_member_not_a_display_alias(self):
        from tmh.platform.agent_api import _actor
        author=_actor(self.request('alice',{'X-Webuddy-Agent':'public-cli-label'}),self.P)
        self.assertEqual(author,'agent:member:alice')
        run=self.P.store.create_run(self.ticket['project_id'],self.ticket['id'],'codex','fix',author,'public fixture')
        self.assign(owner='bob',reviewer='alice')
        with self.assertRaisesRegex(ApiError,'实现'):
            server._human_action(self.P,self.request('alice'),self.ticket,run=run)
        # An unrelated legacy alias is not a trustworthy personal principal.
        external=dict(run,author='agent:alice')
        self.assertEqual(server._human_action(self.P,self.request('alice'),self.ticket,run=external),'alice')

    def test_personal_review_does_not_grant_model_build_or_merge_execution(self):
        self.assign()
        self.assertEqual(server._human_action(self.P, self.request('bob'), self.ticket), 'bob')
        for path, body in (('/api/tickets/ALPHA-1/runs', {}),
                ('/api/team', {'action':'candidate_merge','ticket':'ALPHA-1'}),
                ('/api/tickets/ALPHA-1/accept', {'result':'pass'})):
            with self.subTest(path=path), self.assertRaises(ApiError):
                self.fixture.auth(path, actor='bob', method='POST', body=body)


class ProjectReviewHttpTest(unittest.TestCase):
    def test_real_sessions_review_without_execution_and_revocation_is_immediate(self):
        gateway = gateway_fixture.TenantGatewayTest('runTest')
        self.addCleanup(gateway.doCleanups)
        gateway.setUp()
        def retain():
            destination=os.environ.get('TMH_REVIEW_HTTP_SCENE')
            if destination:
                target=Path(destination);target.mkdir(parents=True,exist_ok=False)
                logs=gateway.data/'control/worker-logs'
                for log in logs.glob('*.log'):
                    shutil.copyfile(log,target/log.name)
                root=Path(gateway.reg.one('SELECT path FROM tenants WHERE id=?',(gateway.a,))['path'])
                for packet in signoff.epath(root, 'SAME-1').parent.glob('*.jsonl'):
                    shutil.copyfile(packet,target/packet.name)
        self.addCleanup(retain)
        gateway.change('member_set', tenant=gateway.a, user='bob', role='member')
        gateway.change('project_grant', tenant=gateway.a, user='bob', project_id=1, role='contributor')
        data = Path(gateway.reg.one('SELECT path FROM tenants WHERE id=?', (gateway.a,))['path'])
        store = Store(data/'platform.db')
        self.addCleanup(store.db.close)
        ticket = store.ticket('SAME-1')
        context = TenantContext(gateway.reg, gateway.a)
        P = SimpleNamespace(store=store, data_dir=data, tenant_context=context)
        context.platform = P
        team.schema(P)
        run = store.create_run(ticket['project_id'], ticket['id'], 'fixture', 'fix', 'alice', 'public synthetic implementation')
        evidence.append(signoff.epath(data, ticket['key']), 'pack', 'owner', {'snapshot': {
            'ac':[{'id':'A1','text':'Public synthetic criterion'}], 'change':{'run':run['id'],'diff':'public fixture','files':['fixture.txt']},
            'check':{'result':'pass'}, 'scope':{'beyond_plan':[]}, 'path':{'ok':True}, 'gates':None}})
        path='/t/'+gateway.a+'/api/tickets/SAME-1/evidence'
        body={'kind':'review','note':'Synthetic personal review only, not business acceptance'}
        def post(user, headers=None):
            return gateway.request('POST',path,user,body,token=gateway.token(user,gateway.a),headers={'X-TMH':'1', **(headers or {})})
        original=signoff.records(data,ticket['key'])
        status,_,result=post('alice')
        self.assertEqual(status,409,result)
        self.assertEqual(signoff.records(data,ticket['key']),original)
        code,_,state=gateway.request('GET',path,'alice',token=gateway.token('alice',gateway.a))
        self.assertEqual(code,200,state)
        self.assertIs(state['personal_review']['allowed'],False)
        team._assign(P,ticket,{'assignee':'alice','reviewer':'bob','revision':0,'previous_assignee':''},'owner')
        status,_,result=post('bob',{'X-TMH-User':'alice'})
        self.assertEqual(status,200,(result,[log.read_text() for log in (gateway.data/'control/worker-logs').glob('*.log')]))
        self.assertEqual(signoff.records(data,ticket['key'])[-1]['by'],'bob')
        code,_,state=gateway.request('GET',path,'bob',token=gateway.token('bob',gateway.a))
        self.assertEqual(code,200,state)
        self.assertIs(state['personal_review']['allowed'],True)
        self.assertEqual(gateway.reg.context('bob',gateway.a)['capabilities']['execution'],False)
        saved=signoff.records(data,ticket['key'])
        status,_,result=post('bob',{'X-Webuddy-Agent':'synthetic'})
        self.assertEqual(status,403,result)
        self.assertEqual(signoff.records(data,ticket['key']),saved)
        gateway.change('project_revoke',tenant=gateway.a,user='bob',project_id=1)
        status,_,result=post('bob')
        self.assertEqual(status,403,result)
        self.assertEqual(signoff.records(data,ticket['key']),saved)
        self.assertEqual(store.ticket(ticket['id'])['status'],ticket['status'])


if __name__ == '__main__':
    unittest.main()
