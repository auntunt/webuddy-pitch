import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh.platform import assistant
from tmh.platform.server import Platform
from tmh.platform.errors import ApiError
from tests.test_tenant_policy import Context


class WebAssistantTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.P = Platform(self.root / 'data')
        self.addCleanup(self.P.store.db.close)
        self.P.tenant_context = Context(self.root / 'repos')
        for key in ('ALPHA', 'BETA'):
            p = self.root / 'repos' / key
            p.mkdir(parents=True)
            self.P.store.add_project(key, key, str(p))
        self.project = self.P.store.project('ALPHA')
        self.session = self.P.store.session_create(self.project['id'], 'consult', '测试', 'alice')
        self.req = SimpleNamespace(user='alice', body={'question': '创建一条测试需求', 'request_id': 'intent-1'})
        self.addCleanup(patch.stopall)
        patch('tmh.platform.server._direct_api_allowed', return_value=True).start()
        patch('tmh.platform.assistant.kbqa.router_conf', return_value={'ready': True, 'model': 'fixture'}).start()

    def answer(self, operation=None, args=None, text='完成'):
        if operation:
            return {'choices': [{'message': {'tool_calls': [{'id': 'call-1', 'function': {'name': operation, 'arguments': json.dumps(args or {})}}]}}]}
        return {'choices': [{'message': {'content': text}}]}

    def advance(self, message, answer):
        self.req.body = {'message': message['message']['id'], 'step': message['step']}
        with patch.object(assistant.kbqa, '_post', return_value=answer):
            return assistant.step(self.P, self.req, self.session, message['message']['id'])

    def test_real_mcp_create_and_duplicate_step_have_one_receipt(self):
        r = assistant.start(self.P, self.req, self.session)
        again = assistant.start(self.P, self.req, self.session)
        self.assertEqual(r['message']['id'], again['message']['id'])
        answer = self.answer('ticket_create', {'project': 'ALPHA', 'title': '保留全文', 'body': '用户的完整需求'})
        out = self.advance(r, answer)
        self.assertEqual(out['message']['data']['trace'][0]['status'], 'done')
        self.advance(r, answer)
        rows = self.P.store.q('select * from tickets')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['body'], '用户的完整需求')
        self.assertEqual(self.P.store.q('select principal from agent_requests')[0]['principal'], 'alice')
        finished = self.advance(out, self.answer(text='已创建 ALPHA-1'))
        self.assertFalse(finished['pending'])

    def test_project_lists_are_filtered_before_model_sees_them(self):
        r = self.advance(assistant.start(self.P, self.req, self.session), self.answer('projects_list'))
        items = r['message']['data']['trace'][0]['result']['items']
        self.assertEqual([x['key'] for x in items], ['ALPHA'])

    def test_cross_project_tool_call_is_denied(self):
        with self.assertRaises(ApiError):
            assistant._call(self.P, 'alice', 'ticket_create', {'project': 'BETA', 'title': 'no', 'body': 'no', 'request_id': 'forbidden'})
        self.assertEqual(self.P.store.q('select * from tickets'), [])

    def test_human_approval_and_shell_are_never_tools(self):
        for operation in ('candidate_accept', 'release', 'shell'):
            with self.assertRaises(ApiError):
                assistant._call(self.P, 'alice', operation, {})

    def test_viewer_cannot_write(self):
        with self.assertRaises(ApiError):
            assistant._call(self.P, 'reader', 'ticket_create', {'project': 'ALPHA', 'title': 'no', 'body': 'no', 'request_id': 'forbidden'})

    def test_permissions_rechecked_after_model_reply(self):
        r = assistant.start(self.P, self.req, self.session)
        self.P.tenant_context.people['alice']['project_grants'] = {}
        out = self.advance(r, self.answer('ticket_create', {'project': 'ALPHA', 'title': 'no', 'body': 'no'}))
        self.assertEqual(out['message']['data']['trace'][0]['status'], 'failed')
        self.assertFalse(self.P.store.q('select * from tickets'))

    def test_network_failure_keeps_turn_for_resume(self):
        r = assistant.start(self.P, self.req, self.session)
        self.req.body = {'step': 0}
        with patch.object(assistant.kbqa, '_post', side_effect=TimeoutError), self.assertRaises(ApiError):
            assistant.step(self.P, self.req, self.session, r['message']['id'])
        self.assertTrue(assistant._view(self.P, r['message']['id'])['pending'])
        self.assertFalse(self.P.store.q('select * from tickets'))

    def test_stop_and_session_isolation(self):
        r = assistant.start(self.P, self.req, self.session)
        self.req.body = {'action': 'stop'}
        out = assistant.step(self.P, self.req, self.session, r['message']['id'])
        self.assertFalse(out['pending'])
        other = dict(self.session, id=999)
        with self.assertRaises(ApiError):
            assistant.step(self.P, self.req, other, r['message']['id'])

    def test_unknown_model_tool_and_parallel_calls_execute_nothing(self):
        r = assistant.start(self.P, self.req, self.session)
        with self.assertRaises(ApiError):
            self.advance(r, self.answer('shell', {'command': 'touch unwanted'}))
        self.assertFalse(self.P.store.q('select * from agent_requests') if self.P.store.one("select name from sqlite_master where name='agent_requests'") else [])

    def test_pending_call_replays_same_request_after_lost_receipt(self):
        r = assistant.start(self.P, self.req, self.session)
        real = assistant._call
        def lost(*args):
            real(*args)
            raise OSError('lost receipt')
        with patch.object(assistant, '_call', side_effect=lost), self.assertRaises(ApiError):
            self.advance(r, self.answer('ticket_create', {'project': 'ALPHA', 'title': 'one', 'body': 'one'}))
        out = self.advance(r, self.answer())
        self.assertEqual(len(self.P.store.q('select * from tickets')), 1)
        self.assertEqual(out['message']['data']['trace'][0]['status'], 'done')

    def test_limit_rejects_unsolicited_tool_and_stop_preserves_completed_answer(self):
        r = assistant.start(self.P, self.req, self.session)
        d = r['message']['data']; d['step'] = 16
        self.P.store.chat_update(r['message']['id'], 'working', d)
        r = assistant._view(self.P, r['message']['id'])
        with self.assertRaises(ApiError):
            self.advance(r, self.answer('projects_list'))
        out = self.advance(r, self.answer(text='完成结果'))
        self.req.body = {'action': 'stop'}
        stopped = assistant.step(self.P, self.req, self.session, out['message']['id'])
        self.assertEqual(stopped['message']['body'], '完成结果')

class CliAssistantTest(unittest.TestCase):
    setUp = WebAssistantTest.setUp

    def test_cli_route_starts_once_and_reconciles_finished_answer(self):
        with patch.object(assistant, '_backend', return_value='cursor'), \
                patch.object(assistant.tenant_policy, 'require_execution'), \
                patch.object(self.P.runner, 'start') as launch:
            run = self.P.store.create_run(self.project['id'], None, 'cursor', 'ask', 'alice', 'question')
            launch.return_value = run
            self.req.body['page'] = {'title': '设置', 'route': '#/settings'}
            first = assistant.start(self.P, self.req, self.session)
            again = assistant.start(self.P, self.req, self.session)
            self.assertEqual(first['message']['id'], again['message']['id'])
            launch.assert_called_once()
            self.assertEqual(launch.call_args.args[3], 'ask')
            self.assertIn('设置', launch.call_args.kwargs['question'])
            self.req.body = {'message': first['message']['id'], 'step': 0}
            pending = assistant.step(self.P, self.req, self.session, first['message']['id'])
            self.assertEqual(pending['poll_after_ms'], 1500)
            self.P.store.update_run(run['id'], status='done', result='AI助手已连接', exit_code=0)
            answer = assistant.step(self.P, self.req, self.session, first['message']['id'])
            self.assertFalse(answer['pending'])
            self.assertEqual(answer['message']['body'], 'AI助手已连接')
            launch.assert_called_once()

    def test_cli_cannot_bypass_execution_isolation(self):
        with patch.object(assistant, '_backend', return_value='cursor'), \
                patch.object(assistant.tenant_policy, 'require_execution', side_effect=ApiError(403, '未配置隔离')), \
                patch.object(self.P.runner, 'start') as launch:
            with self.assertRaises(ApiError):
                assistant.start(self.P, self.req, self.session)
            launch.assert_not_called()
            self.assertEqual(self.P.store.session_chats(self.session['id']), [])

    def test_explicit_cli_route_does_not_require_direct_model_api(self):
        with patch.object(assistant.agent_routes, 'route', return_value={'agent':'cursor','allowed_agents':['cursor'],'direct_api':False}), \
                patch.object(assistant.agents, 'available', return_value=[{'name':'cursor','available':True}]), \
                patch.object(assistant.kbqa, 'router_conf', return_value={'ready':False}):
            self.assertEqual(assistant._backend(self.P, self.project), 'cursor')

    def test_stop_cancels_cli_run_without_starting_another(self):
        run=self.P.store.create_run(self.project['id'],None,'cursor','ask','alice','question')
        with patch.object(assistant,'_backend',return_value='cursor'), \
                patch.object(assistant.tenant_policy,'require_execution'), \
                patch.object(self.P.runner,'start',return_value=run) as launch:
            turn=assistant.start(self.P,self.req,self.session)
            self.req.body={'action':'stop'}
            result=assistant.step(self.P,self.req,self.session,turn['message']['id'])
            self.assertFalse(result['pending'])
            self.assertEqual(self.P.store.run(run['id'])['status'],'cancelled')
            launch.assert_called_once()
