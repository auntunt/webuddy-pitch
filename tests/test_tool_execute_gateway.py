"""Execute-scope tool connections through the real signed gateway and worker."""
import os
import unittest
from pathlib import Path

from tests import test_tenant_gateway as gateway
from tmh.platform.store import Store


@unittest.skipUnless(os.name == 'posix', 'private workers require Unix sockets')
class ToolExecuteGatewayTests(unittest.TestCase):
    setUp = gateway.TenantGatewayTest.setUp
    change = gateway.TenantGatewayTest.change
    request = gateway.TenantGatewayTest.request
    token = gateway.TenantGatewayTest.token

    def seed(self):
        data = Path(self.reg.one("SELECT path FROM tenants WHERE id='default'")['path'])
        root = data / 'repositories' / 'exec'
        root.mkdir(parents=True, exist_ok=True)
        store = Store(data / 'platform.db')
        try:
            p = store.add_project('EXEC', '执行范围', str(root))
            t = store.create_ticket(p['id'], '合成工单', author='owner')
            return p, t, data
        finally:
            store.db.close()

    def grant(self, user, project, scope):
        status, _, out = self.request('POST', '/t/default/api/tool-connections', user,
            {'action': 'create', 'label': 'cli-' + scope, 'project_ids': [project['id']], 'scope': scope,
             'expires_days': 7, 'request_id': f'grant-{user}-{scope}'}, token=self.token(user, 'default'), headers={'X-TMH': '1'})
        self.assertEqual(status, 200, out)
        return out['token']

    def call(self, token, operation, body, execution=False):
        headers = {'X-TMH': '1', 'Authorization': 'Bearer ' + token, 'X-Webuddy-Agent': 'cli'}
        if execution:
            headers['X-Webuddy-Execution'] = '1'
        status, _, out = self.request('POST', '/t/default/api/agent/' + operation, body=body, headers=headers)
        return status, out

    def hold(self, data, tid):
        store = Store(data / 'platform.db')
        try:
            return (store.ticket(tid).get('links') or {}).get('hold')
        finally:
            store.db.close()

    def test_execute_scope_runs_only_where_the_member_may_run_in_the_web(self):
        project, ticket, data = self.seed()
        owner = self.grant('owner', project, 'execute')
        status, out = self.call(owner, 'status', {})
        self.assertEqual(status, 200, out)
        self.assertTrue(out['tool_connection']['execution'])
        self.assertIn('run_start', out['allowed_operations'])
        self.assertIn('ticket_hold', out['allowed_operations'])
        from tmh.platform.agents import available
        self.assertTrue(available(data))
        self.assertEqual([e['name'] for e in out['engines']], [e['name'] for e in available(data)])
        status, out = self.call(owner, 'ticket_hold', {'ticket': ticket['key'], 'hold': True, 'request_id': 'h1'})
        self.assertEqual(status, 200, out)
        self.assertEqual(self.hold(data, ticket['id']), 'owner')
        status, out = self.call(owner, 'ticket_hold', {'ticket': ticket['key'], 'hold': False, 'request_id': 'h2'})
        self.assertEqual(status, 200, out)
        self.assertFalse(self.hold(data, ticket['id']))
        start = {'ticket': ticket['key'], 'mode': 'analyze', 'engine': 'no-such-engine', 'request_id': 's1'}
        status, out = self.call(owner, 'run_start', start)
        self.assertEqual(status, 403, out)
        status, out = self.call(owner, 'run_start', dict(start, request_id='s2'), execution=True)
        self.assertNotEqual(status, 403, out)
        self.assertNotIn('隔离', out.get('error', ''))

        content = self.grant('owner', project, 'content')
        self.assertEqual(self.call(content, 'status', {})[1]['engines'], [])
        status, out = self.call(content, 'ticket_hold', {'ticket': ticket['key'], 'hold': True, 'request_id': 'c1'})
        self.assertEqual(status, 403, out)
        status, out = self.call(content, 'run_start', dict(start, request_id='c2'), execution=True)
        self.assertEqual(status, 403, out)

        self.change('member_set', tenant='default', user='alice', role='member')
        self.change('project_grant', tenant='default', user='alice', project_id=project['id'], role='contributor')
        alice = self.grant('alice', project, 'execute')
        status, out = self.call(alice, 'status', {})
        self.assertEqual(status, 200, out)
        self.assertEqual(out['engines'], [])
        status, out = self.call(alice, 'ticket_hold', {'ticket': ticket['key'], 'hold': True, 'request_id': 'a1'})
        self.assertEqual(status, 200, out)
        self.assertEqual(self.hold(data, ticket['id']), 'alice')
        status, out = self.call(alice, 'ticket_hold', {'ticket': ticket['key'], 'hold': False, 'request_id': 'a2'})
        self.assertEqual(status, 403, out)
        status, out = self.call(alice, 'run_start', dict(start, request_id='a3'), execution=True)
        self.assertEqual(status, 403, out)
        self.assertEqual(self.hold(data, ticket['id']), 'alice')

    def test_reform_preflight_uses_actual_worker_identity_and_connection_scope(self):
        import subprocess
        import concurrent.futures
        from tmh.platform import reform
        project, _, data = self.seed()
        (data/'autoflow.json').write_text(__import__('json').dumps({'on':False,'understand':'rules'}))
        root = Path(project['root'])
        subprocess.run(['git','init','-q',str(root)],check=True)
        subprocess.run(['git','-C',str(root),'-c','user.name=fixture','-c','user.email=fixture@example.invalid',
                        'commit','-q','--allow-empty','-m','fixed source'],check=True)
        sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        plan=reform.create(data,'EXEC',{'built':'fixture','domains':[{'id':'sales','title':'Sales'}]},
            dict(title='Identity',goal='Preserve behavior',source_version=sha,criteria=['Preserved'],target_environment='fixture'), 'owner')
        resource={'project':'EXEC','plan_id':plan['id']}
        execute=self.grant('owner',project,'execute')
        content=self.grant('owner',project,'content')
        read=self.grant('owner',project,'read')
        def check(token):
            status,result=self.call(token,'reform_resume_preview',resource)
            self.assertEqual(status,200,result)
            return result
        self.assertIn('start',check(execute)['allowed_actions'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(check,[execute,content,read]*2))
        for i,result in enumerate(results):
            self.assertEqual('start' in result['allowed_actions'],i%3==0,result)
        status,paused=self.call(execute,'reform_control',dict(resource,action='pause',
            expected_revision=plan['revision'],request_id='pause-identity'),execution=True)
        self.assertEqual(status,200,paused)
        self.assertTrue(paused['paused'])
        self.assertIn('resume',check(execute)['allowed_actions'])
        self.assertEqual(self.call(content,'reform_control',dict(resource,action='resume',
            expected_revision=paused['revision'],request_id='deny-content'),execution=True)[0],403)
        self.assertNotIn('start',check(read)['allowed_actions'])
        status,started=self.call(execute,'reform_control',dict(resource,action='resume',
            expected_revision=paused['revision'],request_id='start-after-preflight'),execution=True)
        self.assertEqual(status,200,started)
        self.assertEqual(started['counts']['released'],1)
        store=Store(data/'platform.db')
        try:self.assertEqual(store.runs(),[]) # auto execution off: no paid model or human decision
        finally:store.db.close()


if __name__ == '__main__':
    unittest.main()
