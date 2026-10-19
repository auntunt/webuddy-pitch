"""Behavioral coverage for authenticated agent operations and durable receipts."""
import concurrent.futures
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from tmh.platform import agent_api
from tmh.platform.errors import ApiError
from tmh.platform.server import Platform, Req, make_handler


WORKER = '''
import json, sys
from pathlib import Path
from types import SimpleNamespace
from tmh.platform.agent_api import dispatch
from tmh.platform.store import Store
from tmh.platform.errors import ApiError
p=json.load(sys.stdin)
st=Store(Path(p['database']))
P=SimpleNamespace(store=st)
req=SimpleNamespace(h=SimpleNamespace(headers={'X-Webuddy-Agent':'codex'}),body=p['args'],user='human')
try:
    result=dispatch(P,req,'ticket_create')
    print(json.dumps({'ok':result}))
except ApiError as e:
    print(json.dumps({'error':str(e),'code':e.code}))
st.db.close()
'''


class AgentAPITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tmh-agent-api-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@localhost')
        (self.repo / 'app.txt').write_text('fixture\n')
        self.git('add', 'app.txt')
        self.git('commit', '-m', 'fixture')
        self.P = Platform(self.root / 'data', user='a real person')
        self.addCleanup(self.P.store.db.close)
        self.project = self.P.store.add_project('AGENT', 'Agent fixture', str(self.repo))
        self.args = {'project': 'AGENT', 'title': '保留需求全文', 'body': '保存后刷新仍可编辑\n失败时保留草稿', 'type': 'feature', 'request_id': 'create-1'}

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True, text=True).stdout.strip()

    def call(self, operation, args=None, agent='codex', execution=False):
        headers = {'X-Webuddy-Agent': agent}
        if execution:
            headers['X-Webuddy-Execution'] = '1'
        req = Req(SimpleNamespace(headers=headers), {}, args or {}, 'human-login')
        return agent_api.dispatch(self.P, req, operation)

    def create(self, **extras):
        return self.call('ticket_create', dict(self.args, **extras))['ticket']

    def run_record(self, t, mode='plan', status='done', result=None):
        r = self.P.store.create_run(t['project_id'], t['id'], 'codex', mode, 'agent:codex', 'prompt')
        self.P.store.update_run(r['id'], status=status, exit_code=0 if status == 'done' else None,
                                result=result or '```tmh-plan\n{"ac":[{"text":"持久保存","check":"重启后读回"}]}\n```')
        return self.P.store.run(r['id'])

    def test_create_is_held_agent_attributed_and_replayed_exactly(self):
        one = self.call('ticket_create', self.args)
        two = self.call('ticket_create', self.args)
        self.assertEqual(one, two)
        t = one['ticket']
        self.assertEqual(t['reporter'], 'agent:codex')
        self.assertEqual(t['links']['hold'], 'agent:codex')
        self.assertEqual(t['links']['handwork'], 'agent:codex')
        self.assertEqual(t['body'], self.args['body'])
        self.assertFalse(one['execution_started'])
        self.assertEqual(len(self.P.store.tickets()), 1)
        self.assertEqual(self.P.store.runs(), [])
        self.assertEqual(self.call('request_get', {'request_id': 'create-1'})['state'], 'complete')

    def test_new_agent_task_waits_without_claiming_execution(self):
        t = self.create()
        packet = self.call('ticket_get', {'ticket': t['key']})
        self.assertEqual(packet['plain_state']['state'], 'you')
        self.assertIn('CLI / MCP', packet['plain_state']['why'])
        self.assertEqual(packet['runs'], [])

    def test_handwork_scan_never_executes_agent_created_ticket_matching_existing_branch(self):
        from tmh.platform import handwork
        self.git('checkout', '-b', 'wb/AGENT-1')
        (self.repo / 'app.txt').write_text('candidate that predates the ticket\n')
        self.git('add', 'app.txt')
        self.git('commit', '-m', 'existing candidate')
        sha = self.git('rev-parse', 'HEAD')
        self.git('checkout', 'main')
        t = self.create()
        self.assertEqual(t['key'], 'AGENT-1')
        self.assertEqual(handwork.settings(self.P.data_dir)['handwork'], 'auto')
        with patch.object(handwork, '_check') as check:
            self.assertEqual(handwork.scan(self.P, self.project), [])
            check.assert_not_called()
        self.assertEqual(self.P.store.runs(ticket_id=t['id']), [])
        self.assertEqual(self.P.store.ticket(t['id'])['status'], 'new')
        # Ordinary human branch intake still runs its existing path.
        human = self.P.store.create_ticket(self.project['id'], 'human task', 'person', links={'hold': 'person', 'handwork': 'person'})
        self.git('branch', 'wb/' + human['key'], sha)
        entered = threading.Event()
        with patch.object(handwork, '_check', side_effect=lambda *args: entered.set()) as check:
            try:
                results = handwork.scan(self.P, self.project)
                self.assertTrue(entered.wait(2))
                self.assertEqual([result['ticket'] for result in results], [human['key']])
                check.assert_called_once()
            finally:
                with handwork._LOCK:
                    handwork._BUSY.discard(human['key'])
        self.assertEqual(len(self.P.store.runs(ticket_id=human['id'])), 1)
        self.assertEqual(self.P.store.runs(ticket_id=t['id']), [])

    def test_same_request_different_payload_or_operation_conflicts(self):
        t = self.create()
        for op, args in [('ticket_create', dict(self.args, title='different')),
                         ('message_send', {'ticket': t['key'], 'body': 'different operation', 'request_id': 'create-1'})]:
            with self.subTest(op=op), self.assertRaises(ApiError) as caught:
                self.call(op, args)
            self.assertEqual(caught.exception.code, 409)
        self.assertEqual(len(self.P.store.tickets()), 1)

    def test_actor_header_is_required_and_cannot_be_human_identity(self):
        for actor in ('', 'human login', 'agent:codex', '人', 'x' * 33):
            with self.subTest(actor=actor), self.assertRaises(ApiError) as caught:
                self.call('ticket_create', self.args, agent=actor)
            self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.P.store.tickets(), [])

    def test_receipts_are_scoped_to_agent_not_caller_human(self):
        self.create()
        with self.assertRaises(ApiError) as caught:
            self.call('request_get', {'request_id': 'create-1'}, agent='cursor')
        self.assertEqual(caught.exception.code, 404)
        other = self.call('ticket_create', self.args, agent='cursor')
        self.assertEqual(other['ticket']['reporter'], 'agent:cursor')
        self.assertEqual(len(self.P.store.tickets()), 2)

    def test_message_preserves_complete_text_and_replay_with_reply_chain(self):
        t = self.create()
        body = '  第一段\n' + '完整内容。' * 2000 + '\n最后一行  '
        args = {'ticket': t['key'], 'body': body, 'to_agent': 'cursor', 'kind': 'handoff', 'request_id': 'message-1'}
        sent = self.call('message_send', args)
        self.assertEqual(self.call('message_send', args), sent)
        answer = self.call('message_send', {'ticket': t['key'], 'body': '已读取，等待执行授权', 'to_agent': 'codex',
                                            'kind': 'result', 'reply_to': sent['event_id'], 'request_id': 'message-2'}, agent='cursor')
        feed = self.call('messages_list', {'ticket': t['key'], 'to_agent': 'cursor'})
        self.assertEqual([m['body'] for m in feed['items']], [body])
        events = self.P.store.events(t['id'])
        comments = [e for e in events if e['kind'] == 'comment']
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]['author'], 'agent:codex')
        self.assertEqual(answer['data']['reply_to'], sent['event_id'])

    def test_cross_ticket_reply_is_refused_without_message(self):
        one = self.create()
        two = self.create(title='second', request_id='create-2')
        sent = self.call('message_send', {'ticket': one['key'], 'body': 'first', 'request_id': 'm1'})
        with self.assertRaises(ApiError) as caught:
            self.call('message_send', {'ticket': two['key'], 'body': 'wrong thread', 'reply_to': sent['event_id'], 'request_id': 'm2'})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.call('messages_list', {'ticket': two['key']})['items'], [])

    def test_message_cursor_has_no_loss_or_duplicate_with_broadcast(self):
        t = self.create()
        for n in range(5):
            self.call('message_send', {'ticket': t['key'], 'body': str(n), 'request_id': 'msg-%d' % n})
        values, after = [], 0
        while True:
            page = self.call('messages_list', {'to_agent': 'cursor', 'after': after, 'limit': 2})
            values.extend(m['body'] for m in page['items'])
            if not page['has_more']:
                break
            after = page['next_after']
        self.assertEqual(values, ['0', '1', '2', '3', '4'])
        last = page['next_after']
        empty = self.call('messages_list', {'after': last})
        self.assertEqual(empty['items'], [])
        self.assertEqual(empty['next_after'], last)

    def test_ticket_list_pagination_and_literal_search(self):
        for n in range(4):
            self.create(title='Task_%d' % n, request_id='create-%d' % n)
        first = self.call('tickets_list', {'project': 'AGENT', 'q': '_', 'limit': 2})
        second = self.call('tickets_list', {'after': first['next_after'], 'limit': 2})
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertEqual(len({t['id'] for t in first['items'] + second['items']}), 4)
        self.assertEqual(self.call('tickets_list', {'q': '%'})['items'], [])

    def test_pending_or_uncertain_request_never_reexecutes(self):
        t = self.create()
        args = {'ticket': t['key'], 'body': 'once', 'request_id': 'uncertain'}
        execute = agent_api._execute
        def crash_after_write(P, req, actor, operation, data):
            result = execute(P, req, actor, operation, data)
            if operation == 'message_send':
                raise RuntimeError('reply lost after durable write')
            return result
        with patch.object(agent_api, '_execute', crash_after_write):
            with self.assertRaises(ApiError) as caught:
                self.call('message_send', args)
        self.assertIn('needs_reconcile', str(caught.exception))
        with self.assertRaises(ApiError):
            self.call('message_send', args)
        receipt = self.call('request_get', {'request_id': 'uncertain'})
        self.assertEqual(receipt['state'], 'uncertain')
        self.assertTrue(receipt['needs_reconcile'])
        self.assertEqual(len(self.call('messages_list', {})['items']), 1)

    def test_api_error_after_write_is_uncertain_and_blocks_replay(self):
        t = self.create()
        execute = agent_api._execute
        def error_after_write(P, req, actor, operation, data):
            result = execute(P, req, actor, operation, data)
            if operation == 'message_send':
                raise ApiError(409, 'downstream side effect returned an error')
            return result
        args = {'ticket': t['key'], 'body': 'persisted before error', 'request_id': 'after-write'}
        with patch.object(agent_api, '_execute', error_after_write), self.assertRaises(ApiError):
            self.call('message_send', args)
        self.assertEqual(self.call('request_get', {'request_id': 'after-write'})['state'], 'uncertain')
        with self.assertRaises(ApiError):
            self.call('message_send', args)
        self.assertEqual(len(self.call('messages_list', {})['items']), 1)

    def test_uncertain_run_launch_can_be_cancelled_and_discussed(self):
        t = self.create()
        execute = agent_api._execute
        def error_after_start(P, req, actor, operation, data):
            result = execute(P, req, actor, operation, data)
            if operation == 'run_start':
                raise ApiError(500, 'lost launch response')
            return result
        def start(p, ticket, engine, mode, author, **kw):
            return self.run_record(ticket, mode, status='queued')
        with patch.object(self.P.runner, 'start', side_effect=start), patch.object(agent_api, '_execute', error_after_start), self.assertRaises(ApiError):
            self.call('run_start', {'ticket': t['key'], 'mode': 'plan', 'engine': 'codex', 'request_id': 'lost-launch'}, execution=True)
        run = self.P.store.runs(ticket_id=t['id'])[0]
        self.assertEqual(self.call('request_get', {'request_id': 'lost-launch'})['state'], 'uncertain')
        message = self.call('message_send', {'ticket': t['key'], 'body': '运行已创建但响应丢失，正在停止', 'request_id': 'explain'})
        self.assertIn('event_id', message)
        stopped = self.call('run_cancel', {'run_id': run['id'], 'request_id': 'stop'}, execution=True)
        self.assertEqual(stopped['status'], 'cancelled')
        with patch.object(self.P.runner, 'start') as restart, self.assertRaises(ApiError) as caught:
            self.call('run_start', {'ticket': t['key'], 'mode': 'plan', 'engine': 'codex', 'request_id': 'unsafe-restart'}, execution=True)
        self.assertIn('needs_reconcile', str(caught.exception))
        restart.assert_not_called()

    def test_cross_process_retry_creates_one_ticket(self):
        payload = json.dumps({'database': str(self.P.store.path), 'args': self.args})
        def run_worker(_):
            proc = subprocess.run([sys.executable, '-c', WORKER], input=payload, text=True, capture_output=True, timeout=20)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(run_worker, range(4)))
        self.assertTrue(any('ok' in row for row in outcomes))
        self.assertEqual(len(self.P.store.tickets()), 1)
        repeated = self.call('ticket_create', self.args)
        self.assertEqual(repeated['ticket']['id'], self.P.store.tickets()[0]['id'])

    def test_executions_require_explicit_transport_capability(self):
        t = self.create()
        with patch.object(self.P.runner, 'start') as start:
            with self.assertRaises(ApiError) as caught:
                self.call('run_start', {'ticket': t['key'], 'mode': 'plan', 'engine': 'codex', 'request_id': 'start-1'})
        self.assertEqual(caught.exception.code, 403)
        start.assert_not_called()

    def test_invalid_engine_is_known_precondition_failure_not_uncertain_lock(self):
        t = self.create()
        with self.assertRaises(ApiError) as caught:
            self.call('run_start', {'ticket': t['key'], 'mode': 'plan', 'engine': 'nonexistent-engine', 'request_id': 'bad-engine'}, execution=True)
        self.assertEqual(caught.exception.code, 400)
        receipt = self.call('request_get', {'request_id': 'bad-engine'})
        self.assertEqual(receipt['state'], 'failed')
        self.assertFalse(receipt['needs_reconcile'])
        self.assertEqual(receipt['arguments']['engine'], 'nonexistent-engine')
        self.call('message_send', {'ticket': t['key'], 'body': '仍可讨论', 'request_id': 'after-known-failure'})

    def test_active_closed_delivery_and_unreleased_tickets_refuse_runs(self):
        cases = ('active', 'closed', 'delivery', 'later', 'unheld')
        for n, case in enumerate(cases):
            t = self.create(title=case, request_id='case-%d' % n)
            if case == 'active':
                self.run_record(t, status='running')
            elif case == 'closed':
                self.P.store.x("UPDATE tickets SET status='closed' WHERE id=?", (t['id'],))
            else:
                links = dict(t['links'])
                if case == 'unheld':
                    links.pop('hold')
                else:
                    links[case] = 'blocked'
                self.P.store.update_ticket(t['id'], links=links)
            with self.subTest(case=case), patch.object(self.P.runner, 'start') as start:
                with self.assertRaises(ApiError) as caught:
                    self.call('run_start', {'ticket': t['key'], 'mode': 'plan', 'engine': 'codex', 'request_id': 'start-%d' % n}, execution=True)
                self.assertEqual(caught.exception.code, 409)
                start.assert_not_called()

    def test_new_run_cannot_bypass_unfinished_process_cleanup(self):
        t = self.create()
        r = self.run_record(t, mode='plan', status='cancelled')
        folder = self.P.data_dir / 'runs' / str(r['id'])
        folder.mkdir(parents=True)
        (folder / 'lifecycle.json').write_text(json.dumps({'finished': False, 'attempts': [{'pid': 1234, 'cleanup': {'complete': False}}]}))
        with patch.object(self.P.runner, 'start') as start, self.assertRaises(ApiError) as caught:
            self.call('run_start', {'ticket': t['key'], 'mode': 'plan', 'engine': 'codex', 'request_id': 'new-after-cancel'}, execution=True)
        self.assertEqual(caught.exception.code, 409)
        self.assertIn('进程回收', str(caught.exception))
        start.assert_not_called()
        (folder / 'lifecycle.json').write_text(json.dumps({'finished': True, 'attempts': [{'pid': 1234, 'cleanup': {'complete': True}}]}))
        with patch.object(self.P.runner, 'start', side_effect=lambda p, ticket, engine, mode, author, **kw: self.run_record(ticket, mode)):
            result = self.call('run_start', {'ticket': t['key'], 'mode': 'plan', 'engine': 'codex', 'request_id': 'after-cleanup'}, execution=True)
        self.assertIn('run', result)

    def test_plan_binds_requirement_and_fix_refuses_stale_body(self):
        t = self.create()
        def start(p, ticket, engine, mode, author, **kw):
            return self.run_record(ticket, mode)
        with patch.object(self.P.runner, 'start', side_effect=start):
            planned = self.call('run_start', {'ticket': t['key'], 'mode': 'plan', 'engine': 'codex', 'request_id': 'plan-1'}, execution=True)
        source = self.P.store.one('SELECT * FROM agent_run_sources WHERE run_id=?', (planned['run']['id'],))
        self.assertEqual(source['requirement_hash'], agent_api._requirement(t, self.P.store))
        self.P.store.update_ticket(t['id'], body='changed requirement')
        with patch.object(self.P.runner, 'start') as start, self.assertRaises(ApiError) as caught:
            self.call('run_start', {'ticket': t['key'], 'mode': 'fix', 'engine': 'codex', 'request_id': 'fix-1'}, execution=True)
        self.assertEqual(caught.exception.code, 409)
        start.assert_not_called()

    def test_new_conversation_requirement_invalidates_plan_without_body_edit(self):
        t = self.create()
        with patch.object(self.P.runner, 'start', side_effect=lambda p, ticket, engine, mode, author, **kw: self.run_record(ticket, mode)):
            self.call('run_start', {'ticket': t['key'], 'mode': 'plan', 'engine': 'codex', 'request_id': 'plan'}, execution=True)
        self.call('message_send', {'ticket': t['key'], 'body': '新增要求：删除事项前必须二次确认', 'kind': 'handoff', 'request_id': 'new-requirement'})
        self.assertEqual(self.P.store.ticket(t['id'])['body'], t['body'])
        with patch.object(self.P.runner, 'start') as start, self.assertRaises(ApiError) as caught:
            self.call('run_start', {'ticket': t['key'], 'mode': 'fix', 'engine': 'codex', 'request_id': 'fix'}, execution=True)
        self.assertEqual(caught.exception.code, 409)
        start.assert_not_called()

    def test_requirement_fingerprint_precedes_runner_prompt_and_late_message(self):
        t = self.create()
        before = agent_api._requirement(t, self.P.store)
        def late_comment(p, ticket, engine, mode, author, **kw):
            r = self.run_record(ticket, mode)
            # Simulates a message arriving after prompt creation but before
            # Runner.start returns its persisted run to the adapter.
            self.P.store.comment(ticket['id'], 'client', '新增权限要求不能被旧方案覆盖')
            return r
        with patch.object(self.P.runner, 'start', side_effect=late_comment):
            result = self.call('run_start', {'ticket': t['key'], 'mode': 'plan', 'engine': 'codex', 'request_id': 'plan'}, execution=True)
        source = self.P.store.one('SELECT * FROM agent_run_sources WHERE run_id=?', (result['run']['id'],))
        self.assertEqual(source['requirement_hash'], before)
        self.assertNotEqual(source['requirement_hash'], agent_api._requirement(t, self.P.store))
        with patch.object(self.P.runner, 'start') as start, self.assertRaises(ApiError):
            self.call('run_start', {'ticket': t['key'], 'mode': 'fix', 'engine': 'codex', 'request_id': 'fix'}, execution=True)
        start.assert_not_called()

    def test_rejection_and_customer_contract_changes_invalidate_source_fingerprint(self):
        from tmh.platform import signoff
        t = self.create()
        before = agent_api._requirement(t, self.P.store)
        self.P.store.event(t['id'], 'client', 'reject', '重启后数据丢失，不能验收')
        rejected = agent_api._requirement(t, self.P.store)
        self.assertNotEqual(before, rejected)
        signoff._add(signoff.epath(self.P.data_dir, t['key']), 'intake', 'client',
                     {'ac': [{'id': 'A1', 'text': '保留全部历史记录', 'check': '重启后读回全部数据'}]})
        self.assertNotEqual(rejected, agent_api._requirement(t, self.P.store))

    def test_fix_requires_bound_successful_plan_and_resolves_base_without_adoption(self):
        t = self.create()
        old = self.run_record(t)
        args = {'ticket': t['key'], 'mode': 'fix', 'engine': 'codex', 'request_id': 'old-plan'}
        with self.assertRaises(ApiError):
            self.call('run_start', args, execution=True)
        self.P.store.x('INSERT INTO agent_run_sources VALUES(?,?,?,?,?)', (old['id'], t['id'], agent_api._requirement(t, self.P.store), 'agent:codex', 'now'))
        received = {}
        def start(p, ticket, engine, mode, author, **kw):
            received.update(kw)
            return self.run_record(ticket, mode)
        with patch.object(self.P.runner, 'start', side_effect=start):
            result = self.call('run_start', dict(args, request_id='bound-plan'), execution=True)
        self.assertEqual(received['base'], self.git('rev-parse', 'HEAD'))
        self.assertNotIn('then', received)
        self.assertFalse(result['human_acceptance'])
        self.assertEqual(self.P.store.ticket(t['id'])['links']['hold'], 'agent:codex')

    def test_fix_fails_closed_when_upstream_baseline_callback_fails(self):
        t = self.create()
        r = self.run_record(t)
        agent_api._schema(self.P.store)
        self.P.store.x('INSERT INTO agent_run_sources VALUES(?,?,?,?,?)', (r['id'], t['id'], agent_api._requirement(t, self.P.store), 'agent:codex', 'now'))
        self.P.flow.bases = [lambda *_: (_ for _ in ()).throw(RuntimeError('cannot resolve dependency'))]
        with patch.object(self.P.runner, 'start') as start, self.assertRaises(ApiError) as caught:
            self.call('run_start', {'ticket': t['key'], 'mode': 'fix', 'engine': 'codex', 'request_id': 'fix'}, execution=True)
        self.assertEqual(caught.exception.code, 409)
        start.assert_not_called()

    def test_recheck_unheld_ticket_cannot_trigger_automatic_adoption(self):
        t = self.create()
        r = self.run_record(t, mode='fix')
        self.P.store.update_ticket(t['id'], links={})
        with patch.object(self.P.flow, 'recheck') as recheck, self.assertRaises(ApiError) as caught:
            self.call('run_recheck', {'run_id': r['id'], 'request_id': 'recheck'}, execution=True)
        self.assertEqual(caught.exception.code, 409)
        recheck.assert_not_called()

    def test_retry_fix_without_source_binding_cannot_skip_current_plan(self):
        t = self.create()
        r = self.run_record(t, mode='fix', status='failed')
        with patch.object(self.P.runner, 'retry') as retry, self.assertRaises(ApiError) as caught:
            self.call('run_retry', {'run_id': r['id'], 'request_id': 'retry'}, execution=True)
        self.assertEqual(caught.exception.code, 409)
        retry.assert_not_called()

    def test_ticket_packet_keeps_requirement_and_more_than_100_run_references(self):
        t = self.create(body='完整原文\n' * 2000)
        for _ in range(102):
            self.run_record(t)
        packet = self.call('ticket_get', {'ticket': t['key']})
        self.assertEqual(packet['ticket']['body'], t['body'])
        self.assertEqual(len(packet['runs']), 102)
        self.assertEqual(packet['repository']['head'], self.git('rev-parse', 'HEAD'))
        self.assertIn('approval', packet['boundaries'])

    def test_real_http_preserves_auth_and_agent_identity(self):
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.P, token='test-token'))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        url = 'http://127.0.0.1:%d/api/agent/ticket_create' % httpd.server_port
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        headers = {'Content-Type': 'application/json', 'X-TMH': '1', 'X-Webuddy-Agent': 'cursor', 'X-TMH-User': 'spoofed human'}
        data = json.dumps(self.args).encode()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            opener.open(urllib.request.Request(url, data, headers), timeout=10)
        self.assertEqual(caught.exception.code, 401)
        caught.exception.close()
        headers['X-TMH-Token'] = 'test-token'
        with opener.open(urllib.request.Request(url, data, headers), timeout=10) as response:
            result = json.load(response)
        self.assertEqual(result['ticket']['reporter'], 'agent:cursor')
        self.assertEqual(len(self.P.store.tickets()), 1)


if __name__ == '__main__':
    unittest.main()
