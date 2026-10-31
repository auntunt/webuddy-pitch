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
        status, out = self.call(content, 'ticket_hold', {'ticket': ticket['key'], 'hold': True, 'request_id': 'c1'})
        self.assertEqual(status, 403, out)
        status, out = self.call(content, 'run_start', dict(start, request_id='c2'), execution=True)
        self.assertEqual(status, 403, out)

        self.change('member_set', tenant='default', user='alice', role='member')
        self.change('project_grant', tenant='default', user='alice', project_id=project['id'], role='contributor')
        alice = self.grant('alice', project, 'execute')
        status, out = self.call(alice, 'status', {})
        self.assertEqual(status, 200, out)
        status, out = self.call(alice, 'ticket_hold', {'ticket': ticket['key'], 'hold': True, 'request_id': 'a1'})
        self.assertEqual(status, 200, out)
        self.assertEqual(self.hold(data, ticket['id']), 'alice')
        status, out = self.call(alice, 'ticket_hold', {'ticket': ticket['key'], 'hold': False, 'request_id': 'a2'})
        self.assertEqual(status, 403, out)
        status, out = self.call(alice, 'run_start', dict(start, request_id='a3'), execution=True)
        self.assertEqual(status, 403, out)
        self.assertEqual(self.hold(data, ticket['id']), 'alice')


if __name__ == '__main__':
    unittest.main()
