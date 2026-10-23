"""Personal tool grants through the actual gateway and independent tenant workers."""
import concurrent.futures
import json
import os
import unittest
from unittest.mock import patch

from tests import test_tenant_gateway as gateway_tests


@unittest.skipUnless(os.name == 'posix', 'tenant workers require POSIX Unix sockets')
class ToolGatewayTest(unittest.TestCase):
    setUp = gateway_tests.TenantGatewayTest.setUp
    change = gateway_tests.TenantGatewayTest.change
    request = gateway_tests.TenantGatewayTest.request
    token = gateway_tests.TenantGatewayTest.token

    def connections(self, user='alice', tenant=None, body=None):
        tenant = tenant or self.a
        return self.request('POST' if body is not None else 'GET', '/t/' + tenant + '/api/tool-connections',
                            user, body, token=self.token(user, tenant), headers={'X-TMH': '1'})

    def grant(self, user='alice', tenant=None, scope='content', projects=None, rid='grant-1'):
        tenant = tenant or self.a
        status, _, result = self.connections(user, tenant, {'action': 'create', 'label': 'my-tool',
            'project_ids': projects or [1], 'scope': scope, 'expires_days': 7, 'request_id': rid})
        self.assertEqual(status, 200, result)
        self.assertIn('token', result)
        return result

    def call(self, grant, operation, body=None, tenant=None, label='claude', headers=None):
        return self.request('POST', '/t/' + (tenant or self.a) + '/api/agent/' + operation,
            body=body or {}, headers={'X-TMH': '1', 'Authorization': 'Bearer ' + grant['token'],
                                     'X-Webuddy-Agent': label, **(headers or {})})

    def test_member_connects_to_only_granted_projects_and_identity_is_not_tool_label(self):
        grant = self.grant()
        for label in ('claude', 'cursor', 'owner'):
            status, _, result = self.call(grant, 'status', label=label)
            self.assertEqual(status, 200, result)
            self.assertEqual(result['tool_connection']['user'], 'alice')
            self.assertEqual(result['tool_connection']['tenant'], self.a)
            self.assertFalse(result['tool_connection']['execution'])
            self.assertEqual(result['engines'], [])
        status, _, result = self.call(grant, 'projects_list')
        self.assertEqual(status, 200, result)
        self.assertEqual([r['key'] for r in result['items']], ['SAME'])
        self.assertNotIn('PRIVATE', json.dumps(result))
        status, _, result = self.call(grant, 'tickets_list')
        self.assertEqual(status, 200, result)
        self.assertEqual([r['title'] for r in result['items']], ['甲的真实记录'])
        status, _, packet = self.call(grant, 'ticket_get', {'ticket': 'SAME-1'})
        self.assertEqual(status, 200, packet)
        self.assertEqual(packet['repository']['head_status'], 'not_checked')
        self.assertEqual(packet['repository']['head'], '')
        self.assertIn('knowledge', packet)
        self.assertNotIn('run_start', packet['supported_actions'])
        self.assertEqual(self.call(grant, 'tickets_list', {'project': 'PRIVATE'})[0], 403)
        self.assertIn(self.call(grant, 'ticket_get', {'ticket': 'SAME-1'}, tenant=self.b)[0], (401, 403))

    def test_historical_preview_is_readable_but_never_claims_current_verification(self):
        from pathlib import Path
        from tmh.platform.store import Store
        target = Path(self.reg.one('SELECT path FROM tenants WHERE id=?', (self.a,))['path'])
        st = Store(target / 'platform.db')
        try:
            run = st.create_run(1, 1, 'fixture', 'fix', 'owner', 'historical record')
            st.x("UPDATE runs SET status='done',decision=? WHERE id=?", ('accepted:historical-branch@' + 'a' * 40, run['id']))
            st.event(1, 'owner', 'adopt', 'synthetic historical adoption', {'branch': 'historical-branch', 'commit': 'a' * 40, 'run': run['id']})
        finally:
            st.db.close()
        (target / 'previews').mkdir(exist_ok=True)
        saved = {'state': 'up', 'commit_full': 'a' * 40, 'pid': 99999999}
        (target / 'previews' / 'state.json').write_text(json.dumps({'SAME-1': saved}))
        grant = self.grant()
        for operation, args in [('ticket_get', {'ticket': 'SAME-1'}), ('preview_get', {'ticket': 'SAME-1'}),
                                ('preview_get', {'ticket': 'SAME-1', 'run_id': run['id']})]:
            with self.subTest(operation=operation, args=args):
                status, _, result = self.call(grant, operation, args)
                self.assertEqual(status, 200, result)
                preview = result['preview'] if operation == 'ticket_get' else result
                self.assertEqual(preview['verification_status'], 'not_checked')
                self.assertEqual(preview['preview']['state'], 'not_checked')
                self.assertEqual(preview['preview']['recorded'], saved)
                self.assertEqual(preview['historical_binding']['commit'], 'a' * 40)
                self.assertEqual(preview['expected_commit'], '')
                self.assertEqual(preview['url'], '')
                self.assertIsNone(preview['matches_run'])
        self.assertEqual(self.call(grant, 'preview_get', {'ticket': 'SAME-1', 'run_id': run['id'] + 1})[0], 404)
        self.assertEqual(json.loads((target / 'previews' / 'state.json').read_text())['SAME-1'], saved)

    def test_real_candidate_read_never_probes_health_or_rewrites_records(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import hashlib
        from pathlib import Path
        import subprocess
        import threading
        from types import SimpleNamespace
        from tmh.platform import agent_api, candidates, preview
        from tmh.platform.store import Store
        from tmh.workbench_client import Client
        from tests.sqlite_snapshot import dump_store

        hits = []
        class Observer(BaseHTTPRequestHandler):
            def do_GET(inner):
                hits.append(inner.path)
                inner.send_response(200)
                inner.send_header('Content-Length', '2')
                inner.end_headers()
                inner.wfile.write(b'ok')
            def log_message(inner, *_):
                pass
        observer = ThreadingHTTPServer(('127.0.0.1', 0), Observer)
        observer.daemon_threads = True
        thread = threading.Thread(target=observer.serve_forever, daemon=True)
        thread.start()
        try:
            for tenant, user in ((self.a, 'alice'), ('default', 'owner')):
                with self.subTest(tenant=tenant):
                    target = Path(self.reg.one('SELECT path FROM tenants WHERE id=?', (tenant,))['path'])
                    st = Store(target / 'platform.db')
                    try:
                        agent_api._schema(st)
                        root = target / 'repositories' / 'same'
                        root.mkdir(parents=True, exist_ok=True)
                        p = st.project('SAME') or st.add_project('SAME', 'synthetic', str(root))
                        ticket = st.ticket('SAME-1') or st.create_ticket(p['id'], 'synthetic', 'owner')
                        empty = target / 'empty-candidate-template'
                        empty.mkdir()
                        env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0',
                                   GIT_AUTHOR_NAME='Synthetic', GIT_AUTHOR_EMAIL='fixture@localhost',
                                   GIT_COMMITTER_NAME='Synthetic', GIT_COMMITTER_EMAIL='fixture@localhost')
                        def git(*args):
                            result = subprocess.run(['git', '-C', str(root), '-c', 'commit.gpgsign=false',
                                '-c', 'core.hooksPath=' + str(empty), *args], env=env, capture_output=True, text=True, timeout=10)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            return result.stdout.strip()
                        git('init', '--template=' + str(empty))
                        (root / 'fixture.txt').write_text('base\n')
                        git('add', 'fixture.txt'); git('commit', '-m', 'synthetic base')
                        base = git('rev-parse', 'HEAD')
                        (root / 'fixture.txt').write_text('candidate\n')
                        git('add', 'fixture.txt'); git('commit', '-m', 'synthetic candidate')
                        head = git('rev-parse', 'HEAD')
                        st.x('UPDATE tickets SET links=? WHERE id=?', (json.dumps({'hold': 'fixture'}), ticket['id']))
                        ticket = st.ticket(ticket['id'])
                        P = SimpleNamespace(store=st, data_dir=target, public_url='', runner=SimpleNamespace(procs={}))
                        summary = '完整历史候选说明\r\n' * 1200
                        registered = candidates.submit(P, 'agent:fixture', {'ticket': ticket['key'], 'base_commit': base,
                            'commit': head, 'requirement_hash': agent_api._requirement(ticket, st), 'summary': summary,
                            'criteria': [{'id': 'A1', 'text': 'synthetic only'}]}, lambda: None)
                        saved = {'state': 'up', 'pid': os.getpid(), 'port': observer.server_address[1],
                                 'prefix': preview.bound_prefix(ticket['key'], head), 'commit_full': head,
                                 'ready': '/', 'started': 'synthetic', 'cmd': 'fixture-only'}
                        (target / 'previews').mkdir(exist_ok=True)
                        (target / 'previews' / 'state.json').write_text(json.dumps({ticket['key']: saved}))
                        # A real positive control: original verification path
                        # can resolve this Git candidate and reaches the observer.
                        control = candidates.view(P, registered['candidate_id'])
                        self.assertTrue(control['current'], control)
                        self.assertTrue(control['preview_ready'], control)
                        self.assertTrue(hits)
                        hits.clear()
                        grant = self.grant(user=user, tenant=tenant, scope='read', projects=[p['id']], rid='candidate-' + tenant)
                        client = Client(endpoint='http://127.0.0.1:%s/t/%s' % (self.port, tenant), agent='fixture',
                                        tool_token=grant['token'], credential_file='')
                        client.connection_status()  # Complete existing startup migrations before observing reads.
                        before_db = dump_store(st)
                        def files():
                            return {str(path.relative_to(target)): hashlib.sha256(path.read_bytes()).hexdigest()
                                    for path in target.rglob('*') if path.is_file() and not path.is_symlink()
                                    and not path.name.startswith('platform.db') and 'control' not in path.relative_to(target).parts}
                        before_files = files()
                        for operation, args in [('candidate_get', {'candidate_id': registered['candidate_id']}),
                                                ('candidates_list', {'ticket': ticket['key']}),
                                                ('ticket_get', {'ticket': ticket['key']}),
                                                ('run_get', {'run_id': registered['run_id']})]:
                            value = client.call(operation, args)
                            self.assertEqual(hits, [], operation)
                            if operation.startswith('candidate'):
                                item = value['items'][0] if operation == 'candidates_list' else value
                                self.assertEqual(item['state'], 'not_checked')
                                self.assertIsNone(item['current'])
                                self.assertIsNone(item['human_accepted'])
                                self.assertEqual(item['summary'], summary)
                                self.assertEqual(item['history']['candidate']['summary'], summary)
                                self.assertEqual(item['history']['ticket_preview']['recorded'], saved)
                                self.assertEqual(item['history']['ticket_preview']['binding_status'], 'not_checked')
                                self.assertEqual(item['preview_url'], '')
                        self.assertEqual(dump_store(st), before_db)
                        self.assertEqual(files(), before_files)
                        if tenant == self.a:
                            self.assertEqual(self.call(grant, 'candidates_list', {'ticket': 'PRIVATE-1'})[0], 404)
                            self.change('project_revoke', tenant=tenant, user=user, project_id=p['id'])
                            self.assertIn(self.call(grant, 'candidate_get', {'candidate_id': registered['candidate_id']})[0], (401, 403))
                    finally:
                        st.db.close()
        finally:
            observer.shutdown()
            observer.server_close()
            thread.join(5)
            self.assertFalse(thread.is_alive())

    def test_durable_receipts_are_personal_project_bound_and_alias_cannot_reexecute(self):
        grant = self.grant()
        body = {'ticket': 'SAME-1', 'body': '完整回执\r\n保留正文', 'request_id': 'shared-id'}
        first = self.call(grant, 'message_send', body)
        self.assertEqual(first[0], 200, first)
        second = self.call(grant, 'message_send', body, label='cursor')
        self.assertEqual(second[0], 200, second)
        self.assertEqual(first[2], second[2])
        receipt = self.call(grant, 'request_get', {'request_id': 'shared-id'})
        self.assertEqual(receipt[0], 200, receipt)
        self.assertEqual(receipt[2]['state'], 'complete')
        self.assertEqual(receipt[2]['principal'], 'alice')
        self.assertEqual(receipt[2]['arguments']['body'], body['body'])
        self.assertEqual(self.call(grant, 'message_send', dict(body, body='different'))[0], 409)
        self.change('member_set', tenant=self.a, user='bob', role='member')
        self.change('project_grant', tenant=self.a, user='bob', project_id=1, role='contributor')
        other = self.grant('bob', rid='grant-bob')
        self.assertEqual(self.call(other, 'request_get', {'request_id': 'shared-id'})[0], 404)
        response = self.call(other, 'message_send', body)
        self.assertEqual(response[0], 200, response)
        self.assertNotEqual(response[2]['event_id'], first[2]['event_id'])

    def test_receipt_stays_inside_current_connection_projects_and_legacy_alias_is_not_ownership(self):
        grant = self.grant()
        body = {'ticket': 'SAME-1', 'body': 'private receipt', 'request_id': 'own-project-one'}
        self.assertEqual(self.call(grant, 'message_send', body)[0], 200)
        self.change('project_grant', tenant=self.a, user='alice', project_id=2, role='contributor')
        narrow = self.grant(projects=[2], rid='project-two')
        self.assertEqual(self.call(narrow, 'request_get', {'request_id': body['request_id']})[0], 403)
        self.assertEqual(self.call(narrow, 'messages_list')[2]['items'], [])
        from pathlib import Path
        from tmh.platform.store import Store
        target = Path(self.reg.one('SELECT path FROM tenants WHERE id=?', (self.a,))['path'])
        st = Store(target / 'platform.db')
        try:
            # Neither a matching alias nor legacy rows without a recorded
            # personal principal can be adopted as this member's receipt.
            st.x("UPDATE agent_requests SET principal='' WHERE request_id=?", (body['request_id'],))
        finally:
            st.db.close()
        self.assertEqual(self.call(grant, 'request_get', {'request_id': body['request_id']})[0], 404)

    def test_expiry_in_transit_prevents_content_write(self):
        grant = self.grant()
        original = self.workers.request
        def expired(*args, **kwargs):
            with self.reg.transaction() as db:
                db.execute('UPDATE tool_connections SET expires_at=0 WHERE id=?', (grant['connection_id'],))
            return original(*args, **kwargs)
        with patch.object(self.workers, 'request', side_effect=expired):
            result = self.call(grant, 'message_send', {'ticket': 'SAME-1', 'body': 'expired write', 'request_id': 'expired'})
            self.assertEqual(result[0], 401, result)
        from pathlib import Path
        import sqlite3
        target = Path(self.reg.one('SELECT path FROM tenants WHERE id=?', (self.a,))['path'])
        with sqlite3.connect(target / 'platform.db') as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE body='expired write'").fetchone()[0], 0)

    def test_read_scope_and_even_owner_tool_credentials_cannot_execute_or_confirm(self):
        read = self.grant(scope='read')
        self.assertEqual(self.call(read, 'message_send', {'ticket': 'SAME-1', 'body': 'x', 'request_id': 'blocked'})[0], 403)
        owner = self.grant('owner', rid='owner-tool')
        operations = {
            'run_start': {'ticket': 'SAME-1', 'mode': 'analyze', 'engine': 'claude', 'request_id': 'x'},
            'candidate_assess': {}, 'candidate_decide': {}, 'library_reference': {},
        }
        for operation, body in operations.items():
            with self.subTest(operation=operation):
                response = self.call(owner, operation, body, headers={'X-Webuddy-Execution': '1', 'X-Webuddy-Operator': '1'})
                self.assertEqual(response[0], 403, response)
        self.assertEqual(self.call(owner, 'tickets_list', {'project': 'PRIVATE'})[0], 403)

    def test_revoke_and_regrant_does_not_resurrect_old_credentials_or_replay(self):
        grant = self.grant()
        body = {'ticket': 'SAME-1', 'body': 'persisted before revocation', 'request_id': 'old'}
        self.assertEqual(self.call(grant, 'message_send', body)[0], 200)
        self.change('project_revoke', tenant=self.a, user='alice', project_id=1)
        for op, args in [('status', {}), ('message_send', body), ('request_get', {'request_id': 'old'})]:
            self.assertIn(self.call(grant, op, args)[0], (401, 403))
        self.change('project_grant', tenant=self.a, user='alice', project_id=1, role='contributor')
        self.assertIn(self.call(grant, 'status')[0], (401, 403))
        fresh = self.grant(rid='new-grant')
        self.assertEqual(self.call(fresh, 'request_get', {'request_id': 'old'})[0], 200)

    def test_fixed_reference_read_is_complete_and_sharing_revocation_is_live(self):
        from pathlib import Path
        import hashlib
        import subprocess
        import time
        from tmh.platform import project_library as library
        from tmh.platform.store import Store
        from tmh.platform.supervised_process import read_receipt
        target = Path(self.reg.one('SELECT path FROM tenants WHERE id=?', (self.a,))['path'])
        st = Store(target / 'platform.db')
        self.addCleanup(st.db.close)
        source, consumer = st.project('PRIVATE'), st.project('SAME')
        root = Path(source['root']); empty = target / 'empty-template'; empty.mkdir()
        env = dict(os.environ, GIT_AUTHOR_NAME='Synthetic', GIT_AUTHOR_EMAIL='fixture@localhost',
                   GIT_COMMITTER_NAME='Synthetic', GIT_COMMITTER_EMAIL='fixture@localhost',
                   GIT_TERMINAL_PROMPT='0', GIT_NO_LAZY_FETCH='1')
        def git(*args):
            result = subprocess.run(['git', '-C', str(root), '-c', 'commit.gpgsign=false',
                '-c', 'core.hooksPath=' + str(empty), *args], env=env, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return result.stdout.decode().strip()
        git('init', '--template=' + str(empty))
        original = ('完整组织知识，包含需要保留的中文与换行。\r\n' * 1000).encode()
        (root / 'rules.md').write_bytes(original)
        git('add', 'rules.md'); git('commit', '-m', 'Synthetic immutable reference')
        commit = git('rev-parse', 'HEAD')
        revision = library.start(st, source, commit, 'fixture')
        deadline = time.monotonic() + 20
        row = None
        try:
            while time.monotonic() < deadline:
                row = st.one('SELECT * FROM knowledge_revisions WHERE id=?', (revision['id'],))
                if row['status'] not in ('queued', 'building'): break
                time.sleep(.025)
            self.assertEqual(row['status'], 'ready', row)
            attempt = target / 'project-library' / 'revisions' / revision['id'] / 'attempts' / row['attempt']
            owner = json.loads((attempt / 'owner.json').read_text())
            receipt = read_receipt(attempt, owner)
            self.assertTrue(receipt['cleanup']['complete'], receipt)
            self.assertTrue(receipt['cleanup']['output_complete'], receipt)
        finally:
            if row and row['status'] in ('queued', 'building'):
                library.cancel(st, source, revision['id'])
        library.grant(st, source, consumer['key'], [], 'fixture')
        library.reference(st, consumer, revision['id'], [], 'synthetic shared standard', 'fixture')
        grant = self.grant(scope='read')
        (root / 'rules.md').write_text('later source content must not replace pinned evidence')
        git('add', 'rules.md'); git('commit', '-m', 'Advance source independently')
        args = {'project': 'SAME', 'revision_id': revision['id'], 'path': 'rules.md'}
        status, _, result = self.call(grant, 'library_read', args)
        self.assertEqual(status, 200, result)
        self.assertEqual(result['content'].encode(), original)
        self.assertEqual(result['sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(result['commit'], commit)
        self.assertEqual(self.call(grant, 'library_read', dict(args, project='PRIVATE'))[0], 403)
        library.act(__import__('types').SimpleNamespace(store=st), source,
                    {'action': 'revoke', 'project': consumer['key']}, 'fixture')
        result = self.call(grant, 'library_read', args)
        self.assertEqual(result[0], 403, result)
        self.assertNotIn(original.decode(), json.dumps(result[2], ensure_ascii=False))

    def test_personal_connection_page_and_no_tool_token_access_to_browser_routes(self):
        status, _, page = self.request('GET', '/t/' + self.a + '/tools', 'alice')
        self.assertEqual(status, 200, page)
        self.assertIn('工具连接', page)
        grant = self.grant()
        for path in ('/api/tool-connections', '/api/access', '/api/meta', '/tools'):
            response = self.request('GET', '/t/' + self.a + path,
                headers={'Authorization': 'Bearer ' + grant['token']})
            self.assertEqual(response[0], 403, response)
        status, _, replay = self.connections(body={'action': 'create', 'label': 'my-tool', 'project_ids': [1],
            'scope': 'content', 'expires_days': 7, 'request_id': 'grant-1'})
        self.assertEqual(status, 200, replay)
        self.assertTrue(replay['credential_unavailable'])
        self.assertNotIn('token', replay)

    def test_concurrent_alias_retries_produce_one_event(self):
        grant = self.grant()
        body = {'ticket': 'SAME-1', 'body': 'one event', 'request_id': 'parallel'}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda label: self.call(grant, 'message_send', body, label=label),
                                    ['one', 'two', 'three', 'four']))
        for response in replies:
            self.assertEqual(response[0], 200, response)
        self.assertEqual(len({r[2]['event_id'] for r in replies}), 1)

    def test_unrelated_authority_change_in_transit_does_not_reject_tool_but_revocation_does(self):
        grant = self.grant()
        original = self.workers.request
        def unrelated(*args, **kwargs):
            self.change('member_set', tenant=self.b, user='bob', role='admin')
            return original(*args, **kwargs)
        with patch.object(self.workers, 'request', side_effect=unrelated):
            response = self.call(grant, 'status')
            self.assertEqual(response[0], 200, response)
        def revoked(*args, **kwargs):
            self.change('project_revoke', tenant=self.a, user='alice', project_id=1)
            return original(*args, **kwargs)
        with patch.object(self.workers, 'request', side_effect=revoked):
            response = self.call(grant, 'message_send', {'ticket': 'SAME-1', 'body': 'must not write', 'request_id': 'blocked-in-transit'})
            self.assertEqual(response[0], 401, response)
        target = self.reg.one('SELECT path FROM tenants WHERE id=?', (self.a,))['path']
        import sqlite3
        from pathlib import Path
        with sqlite3.connect(Path(target) / 'platform.db') as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE body='must not write'").fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
