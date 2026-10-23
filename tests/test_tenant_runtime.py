"""Managed initialization and filtering use temporary synthetic stores only."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tmh.platform import login, server, workspace
from tmh.platform.store import Store
from tmh.platform.tenancy import Registry
from tmh.platform.tenant_runtime import TenantContext, sign_request, verify_request
from tmh.platform.errors import ApiError


class TenantRuntimeTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='tmh-tenant-runtime-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.data = self.root / 'data'
        self.data.mkdir()
        login.set_user(self.data, 'owner', 'synthetic-owner-password')
        login.set_user(self.data, 'alice', 'synthetic-alice-password')
        self.registry = Registry(self.data, bootstrap_owner='owner')
        self.addCleanup(self.registry.close)
        self.context = TenantContext(self.registry, 'default')
        with patch('tmh.platform.agents.Runner.recover'), patch('tmh.platform.learning_runs.recover'), patch('tmh.platform.preview.resume'), patch('tmh.platform.survey.Survey.resume_all'):
            self.P = server.Platform(self.data, tenant_context=self.context)
        self.addCleanup(self.P.store.db.close)
        self.seq = 0

    def action(self, **body):
        self.seq += 1
        return self.registry.dispatch('owner', dict(tenant='default', revision=self.registry.context('owner')['revision'], request_id='runtime-%s' % self.seq, **body))

    def req(self, actor='alice', query=None, body=None):
        return SimpleNamespace(h=SimpleNamespace(_who=actor, headers={}), user=actor, query=query or {}, body=body or {}, arg=lambda k: (query or {}).get(k, ''))

    def projects(self):
        for key in ('ALPHA', 'BETA'):
            root = self.data / 'repositories' / key
            root.mkdir(parents=True)
            self.P.store.add_project(key, key, str(root))
        a, b = [self.P.project(k) for k in ('ALPHA', 'BETA')]
        self.action(action='project_grant', user='alice', project_id=str(a['id']), role='contributor')
        return a, b

    def test_no_recovery_background_or_automatic_execution_during_constructor(self):
        with patch('tmh.platform.agents.Runner.recover') as runs, patch('tmh.platform.learning_runs.recover') as learning, patch('tmh.platform.preview.resume') as preview, patch('tmh.platform.survey.Survey.resume_all') as surveys, patch('threading.Thread.start') as threads:
            P = server.Platform(self.data, tenant_context=TenantContext(self.registry, 'default'))
        self.addCleanup(P.store.db.close)
        for spy in (runs, learning, preview, surveys, threads):
            spy.assert_not_called()
        self.assertFalse(P.flow.autoflow()['on'])
        self.assertFalse(P.flow.autoflow()['merge'])

    def test_filters_precede_limit_counts_and_hidden_projection(self):
        a, b = self.projects()
        own = self.P.store.create_ticket(a['id'], 'visible task', 'alice')
        own_run = self.P.store.create_run(a['id'], own['id'], 'fixture', 'ask', 'alice', 'visible')
        # Hidden rows dominate the most-recent page; they must not evict own rows.
        for i in range(205):
            t = self.P.store.create_ticket(b['id'], 'secret %s' % i, 'owner')
            self.P.store.create_run(b['id'], t['id'], 'fixture', 'ask', 'owner', 'secret')
        req = self.req(query={'limit': '1'})
        self.assertEqual([p['key'] for p in server.api_projects(self.P, req)], ['ALPHA'])
        self.assertEqual([t['key'] for t in server.api_tickets(self.P, req)], [own['key']])
        self.assertEqual([r['id'] for r in server.api_runs(self.P, req)], [own_run['id']])
        with patch('tmh.platform.team.item', wraps=__import__('tmh.platform.team', fromlist=['item']).item) as item:
            value = workspace.read(self.P, {'view': 'team'}, 'alice')
        self.assertEqual(value['total'], 1)
        self.assertEqual(value['counts']['team'], 1)
        self.assertEqual([p['key'] for p in value['projects']], ['ALPHA'])
        self.assertEqual(item.call_count, 1)
        self.assertEqual(item.call_args.args[1]['project_id'], a['id'])
        self.action(action='project_revoke', user='alice', project_id=str(a['id']))
        self.assertEqual(server.api_projects(self.P, req), [])
        self.assertEqual(server.api_tickets(self.P, req), [])
        self.assertEqual(server.api_runs(self.P, req), [])
        self.assertEqual(workspace.read(self.P, {'view': 'team'}, 'alice')['total'], 0)

    def test_project_revocation_marks_assignment_unavailable_even_with_tenant_membership(self):
        a, b = self.projects()
        t = self.P.store.create_ticket(a['id'], 'needs reassignment', 'alice', assignee='alice')
        self.assertEqual(workspace.read(self.P, {'view': 'unassigned'}, 'owner')['total'], 0)
        self.action(action='project_revoke', user='alice', project_id=str(a['id']))
        self.action(action='project_grant', user='alice', project_id=str(b['id']), role='contributor')
        value = workspace.read(self.P, {'view': 'unassigned'}, 'owner')
        self.assertEqual(value['total'], 1)
        self.assertEqual(value['counts']['unassigned'], 1)
        self.assertEqual(value['items'][0]['key'], t['key'])
        self.action(action='project_grant', user='alice', project_id=str(a['id']), role='contributor')
        self.action(action='member_set', user='alice', role='viewer')
        self.assertEqual(workspace.read(self.P, {'view': 'unassigned'}, 'owner')['total'], 1)

    def test_rules_intake_never_starts_agent_and_ticket_does_not_autoflow(self):
        a, b = self.projects()
        req = self.req(body={'project': a['key'], 'text': '记录一个需求', 'model': False})
        with patch('tmh.platform.intake.start', return_value={'id': 'synthetic'}) as start:
            server.api_intake_start(self.P, req, a['key'])
            self.assertIs(start.call_args.kwargs['agent'], False)
            server.api_workbench_intake(self.P, req)
            self.assertIs(start.call_args.kwargs['agent'], False)
        with patch.object(self.P.flow, 'submit') as submit:
            server.api_new_ticket(self.P, self.req(body={'project': a['key'], 'title': 'manual', 'type': 'bug'}))
        submit.assert_not_called()

    def test_internal_proof_binds_actor_tenant_method_path_and_body(self):
        key = b'x' * 32
        raw = b'{"action":"send"}'
        proof = sign_request(key, 'default', 'alice', 'POST', '/api/handoffs', raw)
        self.assertEqual(verify_request(key, proof, 'default', 'POST', '/api/handoffs', raw), 'alice')
        for tenant, method, path, body in (('other', 'POST', '/api/handoffs', raw), ('default', 'GET', '/api/handoffs', raw), ('default', 'POST', '/api/team', raw), ('default', 'POST', '/api/handoffs', b'{}')):
            with self.subTest(tenant=tenant, method=method, path=path), self.assertRaises(ApiError):
                verify_request(key, proof, tenant, method, path, body)
        with patch('tmh.platform.tenant_runtime.time.time', return_value=0), self.assertRaises(ApiError):
            verify_request(key, proof, 'default', 'POST', '/api/handoffs', raw)

    def test_tool_proof_cannot_be_removed_replaced_or_added_to_browser_request(self):
        key = b'x' * 32
        args = ('default', 'alice', 'POST', '/api/agent/status', b'{}', 'context')
        connection = 'a' * 32
        proof = sign_request(key, *args, connection)
        self.assertEqual(verify_request(key, proof, args[0], *args[2:], connection), 'alice')
        for altered in ('', 'b' * 32):
            with self.subTest(connection=altered), self.assertRaises(ApiError):
                verify_request(key, proof, args[0], *args[2:], altered)
        normal = sign_request(key, *args)
        with self.assertRaises(ApiError):
            verify_request(key, normal, args[0], *args[2:], connection)

    def test_tool_actor_context_narrows_admin_and_always_resets_after_error(self):
        a, _ = self.projects()
        tool = dict(id='a' * 32, user='owner', tenant='default', scope='read', project_ids=[a['id']])
        with self.context.acting('owner'):
            self.assertTrue(self.context.current_actor('owner')['platform_owner'])
            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                with self.context.acting('owner', tool):
                    current = self.context.current_actor('owner')
                    self.assertFalse(current['platform_owner'])
                    self.assertFalse(current['capabilities']['execution'])
                    self.assertEqual(current['role'], 'viewer')
                    self.assertEqual(current['project_grants'], {'ALPHA': 'viewer'})
                    raise RuntimeError('synthetic')
            current = self.context.current_actor('owner')
            self.assertTrue(current['platform_owner'])
            self.assertNotIn('tool_connection', current)

    def test_workspace_symlink_and_unregistered_roots_fail_closed(self):
        a, b = self.projects()
        self.assertTrue(self.context.workspace_allowed(a['root']))
        self.assertFalse(self.context.workspace_allowed(self.root))
        link = self.data / 'repositories' / 'escape'
        link.symlink_to(self.root, target_is_directory=True)
        self.assertFalse(self.context.workspace_allowed(link / 'elsewhere'))
        self.assertFalse(self.context.runtime_allowed('alice'))
        self.assertTrue(self.context.runtime_allowed('owner'))
        self.assertFalse(self.context.runtime_allowed('unknown'))

    def test_evidence_page_download_and_original_image_stay_in_tenant(self):
        from tmh.platform import signoff
        a, _ = self.projects()
        ticket = self.P.store.create_ticket(a['id'], 'synthetic evidence', 'owner')
        snapshot = signoff.snapshot(self.P, ticket)
        snapshot['ac'] = [{'id': 'A1', 'text': 'synthetic criterion', 'layer': 'L4'}]
        signoff._add(signoff.epath(self.data, ticket['key']), 'pack', 'owner', {'snapshot': snapshot})
        attached = signoff.attach(self.P, ticket, 'owner', 'A1', 'original synthetic bytes', 'data:image/png;base64,aGVsbG8=')
        name = attached['data']['file']
        with patch.object(signoff, 'signer_fingerprint', return_value=''):
            html = signoff.package_page(self.P, ticket['key'])
        self.assertIn('href="/t/default/e/%s.intoto.json"' % ticket['key'], html)
        self.assertIn("src='/t/default/e/%s/f/%s'" % (ticket['key'], name), html)
        self.assertEqual(signoff.file_bytes(self.data, name)[0], b'hello')
        self.assertNotIn('href="/e/', html)
        self.assertNotIn("src='/e/", html)


@unittest.skipUnless(__import__('os').name == 'posix', 'tenant workers require POSIX Unix sockets')
class WorkerLifecycleTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='tmh-worker-lifecycle-')
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name).resolve()
        login.set_user(self.data, 'alice', 'synthetic-password')
        self.registry = Registry(self.data, bootstrap_owner='alice')
        self.addCleanup(self.registry.close)

    def test_lifetime_lock_and_constructor_failure_release_ownership(self):
        from tmh.platform.tenant_runtime import Workers
        with patch.object(Path, 'mkdir', side_effect=PermissionError('synthetic failure')):
            with self.assertRaises(PermissionError):
                Workers(self.registry)
        workers = Workers(self.registry)
        self.addCleanup(workers.close)
        with self.assertRaises(BlockingIOError):
            Workers(self.registry)
        workers.close()
        next_workers = Workers(self.registry)
        next_workers.close()

    def test_failed_spawn_and_early_exit_remove_private_credentials(self):
        import subprocess, sys
        from tmh.platform.tenant_runtime import Workers
        workers = Workers(self.registry)
        self.addCleanup(workers.close)
        with patch.object(Path, 'mkdir', side_effect=PermissionError('synthetic log directory error')):
            with self.assertRaises(PermissionError):
                workers.ensure('default')
        self.assertEqual(workers.live, {})
        self.assertEqual(list(workers.socket_dir.iterdir()), [])
        with patch('tmh.platform.tenant_runtime.subprocess.Popen', side_effect=OSError('synthetic spawn error')):
            with self.assertRaises(OSError):
                workers.ensure('default')
        self.assertEqual(workers.live, {})
        self.assertEqual(list(workers.socket_dir.iterdir()), [])
        real = subprocess.Popen
        children = []
        def early(*args, **kwargs):
            child = real([sys.executable, '-c', 'raise SystemExit(3)'], **kwargs)
            children.append(child)
            return child
        with patch('tmh.platform.tenant_runtime.subprocess.Popen', side_effect=early):
            with self.assertRaises(ApiError):
                workers.ensure('default')
        self.assertEqual(children[0].wait(timeout=3), 3)
        self.assertEqual(workers.live, {})
        self.assertEqual(list(workers.socket_dir.iterdir()), [])

    def test_worker_holds_authorization_until_real_business_commit(self):
        import concurrent.futures, json, time, threading
        from tmh.platform.tenant_runtime import Workers
        from tmh.platform import filelock
        login.set_user(self.data, 'bob', 'synthetic-password')
        # CLI-created account is not implicitly a member after control-plane migration.
        def action(name, **body):
            revision = self.registry.context('alice')['revision']
            return self.registry.dispatch('alice', dict(action=name, tenant='default', revision=revision, request_id='barrier-%s' % revision, **body))
        action('member_set', user='bob', role='member')
        repo = self.data / 'repositories' / 'repo'
        repo.mkdir(parents=True)
        store = Store(self.data / 'platform.db')
        self.addCleanup(store.db.close)
        project = store.add_project('BARRIER', 'barrier', str(repo))
        ticket = store.create_ticket(project['id'], 'real commit barrier', 'alice')
        action('project_grant', user='bob', project_id=str(project['id']), role='contributor')
        token = self.registry.context('bob')['context_token']
        workers = Workers(self.registry)
        self.addCleanup(workers.close)
        workers.ensure('default')
        headers = {'X-TMH': '1', 'X-Webuddy-Context': token}
        raw = json.dumps({'body': 'accepted before revoke', 'request_id': 'real-comment'}).encode()
        store.db.execute('BEGIN IMMEDIATE')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            request = pool.submit(workers.request, 'default', 'bob', 'POST', '/api/tickets/BARRIER-1/comments', body=raw, headers=headers, require_live=True)
            try:
                # The business database is blocked. The separate worker, not the
                # gateway/calling process, must own the authorization lock now.
                deadline = time.monotonic() + 3
                held = False
                with (self.registry.path.parent / 'authorization.lock').open('a+b') as stream:
                    while time.monotonic() < deadline:
                        try:
                            filelock.try_lock(stream)
                        except BlockingIOError:
                            held = True
                            break
                        else:
                            filelock.unlock(stream)
                        time.sleep(.01)
                self.assertTrue(held, 'worker did not acquire authorization guard')
                begun = threading.Event()
                def revoke():
                    begun.set()
                    return action('account_disable', user='bob')
                revocation = pool.submit(revoke)
                self.assertTrue(begun.wait(1))
                self.assertFalse(revocation.done())
            finally:
                store.db.rollback()
            response = request.result(timeout=5)
            self.assertEqual(response[0], 200, response)
            revocation.result(timeout=5)
        events = store.q("SELECT * FROM events WHERE ticket_id=? AND kind='comment'", (ticket['id'],))
        self.assertEqual([e['body'] for e in events], ['accepted before revoke'])
        denied = workers.request('default', 'bob', 'POST', '/api/tickets/BARRIER-1/comments', body=raw, headers=headers, require_live=True)
        self.assertEqual(denied[0], 403, denied)
        self.assertEqual(store.q("SELECT * FROM events WHERE ticket_id=? AND kind='comment'", (ticket['id'],)), events)

    def test_real_worker_close_and_crash_never_restart_inside_authorization_guard(self):
        import os, signal
        from tmh.platform.tenant_runtime import Workers
        workers = Workers(self.registry)
        self.addCleanup(workers.close)
        current = workers.ensure('default')
        process = current['proc']
        status, headers, raw = workers.request('default', 'alice', 'GET', '/api/meta', headers={'X-Webuddy-Context': self.registry.context('alice')['context_token']}, require_live=True)
        self.assertEqual(status, 200, raw)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
        with self.registry.authorization_guard(), self.assertRaises(ApiError) as result:
            workers.request('default', 'alice', 'GET', '/api/meta', headers={'X-Webuddy-Context': self.registry.context('alice')['context_token']}, require_live=True)
        self.assertEqual(result.exception.code, 503)
        current = workers.ensure('default')
        self.assertNotEqual(current['proc'].pid, process.pid)
        workers.close()
        self.assertIsNotNone(current['proc'].poll())
        self.assertFalse(current['keyfile'].exists())
        self.assertFalse(current['socket'].exists())


if __name__ == '__main__':
    unittest.main()
