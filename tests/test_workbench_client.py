"""Black-box HTTP and CLI regression tests for the external agent bridge.

Only disposable local fixtures are contacted. These checks prove transport and
argument behavior, not actual model implementation or customer acceptance.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from tmh.workbench_client import Client, ClientError


ROOT = Path(__file__).resolve().parents[1]


class WorkbenchClientTest(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.respond = self.normal_response
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append({'path': self.path, 'body': body,
                                       'headers': {k.lower(): v for k, v in self.headers.items()}})
                owner.respond(self, body)

        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever,
                                       kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.endpoint = 'http://127.0.0.1:%d' % self.http.server_port
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.http.shutdown)

    @staticmethod
    def reply(h, value, status=200):
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        h.send_response(status)
        h.send_header('Content-Type', 'application/json')
        h.send_header('Content-Length', str(len(raw)))
        h.end_headers()
        h.wfile.write(raw)

    def normal_response(self, h, body):
        self.reply(h, {'ok': True, 'body': body, 'status': 'done'})

    def test_candidate_link_uses_actual_workbench_endpoint(self):
        entry = '/pv/EXT-1/__commit/' + 'a' * 40 + '/'
        self.respond = lambda h, body: self.reply(h, {'preview_entry_path': entry, 'preview_url': entry})
        value = Client(self.endpoint).call('candidate_get', {'candidate_id': 1})
        self.assertEqual(value['preview_url'], self.endpoint + entry)

    def test_tenant_connection_uses_personal_bearer_without_legacy_headers(self):
        client = Client(self.endpoint + '/t/default', tool_token='wbt_fixture.secret',
                        token='must-not-forward', agent='cursor')
        client.call('status')
        request = self.requests[-1]
        self.assertEqual(request['path'], '/t/default/api/agent/status')
        self.assertEqual(request['headers']['authorization'], 'Bearer wbt_fixture.secret')
        self.assertEqual(request['headers']['x-webuddy-agent'], 'cursor')
        for header in ('x-tmh-token', 'cookie', 'x-webuddy-context', 'x-webuddy-execution'):
            self.assertNotIn(header, request['headers'])

    def test_tenant_without_credential_has_actionable_error(self):
        with self.assertRaises(ClientError) as caught:
            Client(self.endpoint + '/t/default', token='legacy-token')
        self.assertEqual(caught.exception.code, 'tool_credential_required')
        self.assertIn('connect', caught.exception.message)
        self.assertEqual(self.requests, [])

    def test_tenant_credentials_cannot_enable_execution_or_human_decision(self):
        client = Client(self.endpoint + '/t/default', tool_token='wbt_fixture.secret',
                        allow_execution=True, operator=True, operator_token='operator')
        for operation, args in (
            ('run_start', dict(ticket='AGENT-1', mode='analyze', engine='codex', request_id='never')),
            ('candidate_decide', dict(candidate_id=1, evidence_hash='a' * 64,
                                     decision='reject', note='no', request_id='never')),
            ('library_unlink', dict(project='AGENT', binding_id=1, request_id='never')),
        ):
            with self.subTest(operation=operation), self.assertRaises(ClientError) as caught:
                client.call(operation, args)
            self.assertEqual(caught.exception.code, 'tool_operation_forbidden')
        self.assertEqual(self.requests, [])

    def test_tenant_error_redacts_secret_and_retains_unknown_request_id(self):
        secret = 'wbt_fixture.secret'
        self.respond = lambda h, body: self.reply(h, {'error': 'echo ' + secret}, status=503)
        with self.assertRaises(ClientError) as caught:
            Client(self.endpoint + '/t/default', tool_token=secret).call('message_send',
                {'ticket': 'AGENT-1', 'body': 'once', 'request_id': 'tenant-unknown'})
        error = caught.exception.as_dict()
        self.assertTrue(error['uncertain'])
        self.assertEqual(error['request_id'], 'tenant-unknown')
        self.assertNotIn(secret, json.dumps(error))
        self.assertEqual(len(self.requests), 1)

    @unittest.skipUnless(os.name == 'posix', 'credential files require POSIX permission checks')
    def test_real_cli_connect_then_read_and_write_retains_member_scope(self):
        tenant_endpoint = self.endpoint + '/t/default'
        token = 'wbt_fixture.secret'
        def respond(h, body):
            if h.path.endswith('/status'):
                self.reply(h, dict(tool_connection=dict(id='fixture', user='member', tenant='default', scope='content',
                    project_ids=[1], expires_at=1800000000, status='active', execution=False),
                    allowed_operations=['status', 'ticket_get', 'ticket_create', 'message_send', 'request_get']))
            else:
                self.normal_response(h, body)
        self.respond = respond
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'member.json'
            imported = self.cli('connect', '--endpoint', tenant_endpoint, '--stdin', '--save-to', str(path),
                                input=json.dumps(dict(schema=1, endpoint=tenant_endpoint, token=token)).encode())
            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertEqual(json.loads(imported.stdout)['tool_connection']['user'], 'member')
            self.assertNotIn(token.encode(), imported.stdout + imported.stderr)
            read = self.cli('ticket', 'AGENT-1', '--endpoint', tenant_endpoint, '--credential-file', str(path))
            self.assertEqual(read.returncode, 0, read.stderr)
            written = self.cli('send', 'AGENT-1', '--endpoint', tenant_endpoint, '--credential-file', str(path),
                               '--body', 'work receipt', '--request-id', 'member-receipt', '--agent', 'claude')
            self.assertEqual(written.returncode, 0, written.stderr)
        self.assertEqual([request['path'] for request in self.requests],
                         ['/t/default/api/agent/' + op for op in ('status', 'ticket_get', 'message_send')])
        self.assertEqual(self.requests[-1]['body']['request_id'], 'member-receipt')
        for request in self.requests:
            self.assertEqual(request['headers']['authorization'], 'Bearer ' + token)
            self.assertNotIn('x-tmh-token', request['headers'])

    def test_tenant_redirect_does_not_forward_bearer_or_repeat_write(self):
        def redirect(h, body):
            h.send_response(307)
            h.send_header('Location', self.endpoint + '/t/other/api/agent/message_send')
            h.send_header('Content-Length', '0')
            h.end_headers()
        self.respond = redirect
        with self.assertRaises(ClientError) as caught:
            Client(self.endpoint + '/t/default', tool_token='wbt_fixture.secret').call('message_send',
                dict(ticket='AGENT-1', body='once', request_id='redirect-tenant'))
        self.assertEqual(caught.exception.status, 307)
        self.assertEqual(caught.exception.request_id, 'redirect-tenant')
        self.assertEqual([request['path'] for request in self.requests], ['/t/default/api/agent/message_send'])

    def test_tenant_success_never_echoes_bearer_from_upstream(self):
        token = 'wbt_fixture.secret'
        self.respond = lambda h, body: self.reply(h, {'token': token, 'nested': [{token: 'Bearer ' + token}]})
        result = Client(self.endpoint + '/t/default', tool_token=token).call('status')
        self.assertNotIn(token, json.dumps(result))

    def test_operator_secret_is_required_and_never_sent_with_agent_calls(self):
        args = dict(candidate_id=1, evidence_hash='a' * 64, decision='reject', note='isolated fixture', request_id='decision')
        with self.assertRaises(ClientError):
            Client(self.endpoint, operator=True).call('candidate_decide', args)
        self.assertEqual(self.requests, [])
        client = Client(self.endpoint, operator=True, operator_token='fixture-operator-token')
        client.call('status')
        self.assertNotIn('x-webuddy-operator-token', self.requests[-1]['headers'])
        client.call('candidate_decide', args)
        self.assertNotIn('x-webuddy-agent', self.requests[-1]['headers'])
        self.assertEqual(self.requests[-1]['headers']['x-webuddy-operator-token'], 'fixture-operator-token')

    def test_noninteractive_cli_cannot_create_human_decision(self):
        r = self.cli('approve', '1', '--evidence-hash', 'a' * 64, '--body', 'fixture', '--request-id', 'approval', input=b'accept\n')
        self.assertEqual(r.returncode, 1)
        self.assertEqual(json.loads(r.stderr)['code'], 'interactive_operator_required')
        self.assertEqual(self.requests, [])

    def test_nested_candidate_schema_rejects_unknown_and_empty_criteria(self):
        from tmh.agent_contract import validate
        args = dict(ticket='EXT-1', base_commit='a' * 40, commit='b' * 40, requirement_hash='c' * 64,
                    criteria=[{'id': 'A1', 'text': 'Business behavior', 'check': 'HTTP observation'}], summary='fixture', request_id='submit')
        for criteria in ([], [dict(args['criteria'][0], arbitrary_url='http://other')], [dict(args['criteria'][0], text=' ')], [True]):
            with self.assertRaises(ValueError):
                validate('candidate_submit', dict(args, criteria=criteria))

    def cli(self, *args, input=None, cwd=None):
        env = dict(os.environ, PYTHONPATH=str(ROOT), WEBUDDY_TOKEN='fixture-secret-token')
        return subprocess.run([sys.executable, '-m', 'tmh.workbench', '--endpoint', self.endpoint, *args],
                              input=input, capture_output=True, cwd=cwd or ROOT, env=env, timeout=5)

    def test_local_request_bypasses_proxy_and_preserves_headers(self):
        # A deliberately unusable proxy must not affect a local workbench call.
        from unittest.mock import patch
        with patch.dict(os.environ, {'http_proxy': 'http://127.0.0.1:1', 'HTTP_PROXY': 'http://127.0.0.1:1',
                                     'NO_PROXY': '', 'no_proxy': ''}):
            result = Client(self.endpoint, agent='codex', token='fixture-token').call('status')
        self.assertTrue(result['ok'])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]['headers']['x-webuddy-agent'], 'codex')
        self.assertEqual(self.requests[0]['headers']['x-tmh-token'], 'fixture-token')
        self.assertNotIn('x-webuddy-execution', self.requests[0]['headers'])
        self.assertNotIn('cookie', self.requests[0]['headers'])

    def test_redirect_never_forwards_token_or_replays_mutation(self):
        def redirect(h, _body):
            h.send_response(307)
            h.send_header('Location', self.endpoint + '/credential-sink')
            h.send_header('Content-Length', '0')
            h.end_headers()
        self.respond = redirect
        with self.assertRaises(ClientError) as caught:
            Client(self.endpoint, token='fixture-token').call('message_send',
                {'ticket': 'AGENT-1', 'body': 'once', 'request_id': 'redirect-once'})
        self.assertEqual(caught.exception.status, 307)
        self.assertEqual([x['path'] for x in self.requests], ['/api/agent/message_send'])

    def test_lost_write_response_is_uncertain_and_never_auto_retried(self):
        def lost(h, _body):
            h.close_connection = True
            h.connection.shutdown(socket.SHUT_RDWR)
            h.connection.close()
        self.respond = lost
        with self.assertRaises(ClientError) as caught:
            Client(self.endpoint).call('message_send',
                {'ticket': 'AGENT-1', 'body': 'once', 'request_id': 'lost-once'})
        self.assertTrue(caught.exception.uncertain)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]['body']['request_id'], 'lost-once')

    def test_execution_disabled_and_bad_arguments_do_not_contact_server(self):
        client = Client(self.endpoint)
        with self.assertRaises(ClientError) as caught:
            client.call('run_start', {'ticket': 'AGENT-1', 'mode': 'analyze',
                                    'engine': 'codex', 'request_id': 'never'})
        self.assertEqual(caught.exception.code, 'execution_disabled')
        for operation, args in [('run_get', {'run_id': True}),
                                ('ticket_get', {'ticket': '../bad'}),
                                ('status', {'url': 'https://example.org'}),
                                ('message_send', {'ticket': 'AGENT-1', 'body': 'missing id'})]:
            with self.subTest(operation=operation), self.assertRaises(ClientError) as bad:
                client.call(operation, args)
            self.assertEqual(bad.exception.code, 'invalid_arguments')
        self.assertEqual(self.requests, [])

    def test_non_object_success_is_structured_error_instead_of_cli_traceback(self):
        for value in (None, [], 'not an object'):
            with self.subTest(value=value):
                self.respond = lambda h, body, value=value: self.reply(h, value)
                result = self.cli('run', '17', '--wait', '.1')
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                error = json.loads(result.stderr)
                self.assertIn(error['code'], ('invalid_response', 'connection_error'))
                self.assertNotIn(b'Traceback', result.stderr)

    def test_non_object_error_response_still_preserves_http_status(self):
        for value in (None, [], 'upstream error'):
            with self.subTest(value=value):
                self.respond = lambda h, body, value=value: self.reply(h, value, status=503)
                with self.assertRaises(ClientError) as caught:
                    Client(self.endpoint).call('message_send',
                        {'ticket': 'AGENT-1', 'body': 'once', 'request_id': 'error-response'})
                self.assertEqual(caught.exception.status, 503)
                self.assertTrue(caught.exception.uncertain)

    def test_http_timeout_is_total_deadline_even_when_server_drips_body(self):
        def dripping(h, _body):
            raw = b'{"ok":true,"padding":"' + b'x' * 50 + b'"}'
            h.send_response(200)
            h.send_header('Content-Type', 'application/json')
            h.send_header('Content-Length', str(len(raw)))
            h.end_headers()
            try:
                for char in raw:
                    h.wfile.write(bytes([char]))
                    h.wfile.flush()
                    time.sleep(.025)
            except (BrokenPipeError, ConnectionResetError):
                pass
        self.respond = dripping
        started = time.monotonic()
        with self.assertRaises(ClientError):
            Client(self.endpoint, timeout=.15).call('status')
        self.assertLess(time.monotonic() - started, .8)
        self.assertEqual(len(self.requests), 1)

    def test_cli_file_body_is_full_utf8_with_original_line_endings(self):
        body = '  完整正文\r\n保留 tab\t和末尾空格  \r\n' * 3000
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / '需求 原文.txt'
            filename.write_bytes(body.encode('utf-8'))
            result = self.cli('send', 'AGENT-1', '--body-file', str(filename),
                              '--request-id', 'full-file', '--agent', 'cursor')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['body']['body'], body)
        self.assertEqual(self.requests[0]['body']['body'], body)
        self.assertEqual(self.requests[0]['headers']['x-webuddy-agent'], 'cursor')

    def test_cli_stdin_body_preserves_crlf_and_trailing_whitespace(self):
        body = '  第一行\r\n第二行\t \r\n最后一行  '
        result = self.cli('send', 'AGENT-1', '--body-file', '-', '--request-id', 'full-stdin',
                          input=body.encode('utf-8'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.requests[0]['body']['body'], body)
        self.assertEqual(json.loads(result.stdout)['body']['body'], body)

    def test_cli_auth_failure_reports_json_without_leaking_token(self):
        self.respond = lambda h, body: self.reply(h, {'error': 'unauthorized'}, status=401)
        result = self.cli('status')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        error = json.loads(result.stderr)
        self.assertEqual(error['status'], 401)
        self.assertFalse(error['uncertain'])
        self.assertNotIn(b'fixture-secret-token', result.stderr)
        self.assertNotIn(b'Traceback', result.stderr)

    def test_reconcile_conflict_keeps_uncertain_machine_readable(self):
        # Existing platform ApiError responses contain only `error`; preserve
        # the durable journal's uncertainty even without an added response flag.
        self.respond = lambda h, body: self.reply(h, {'error': 'needs_reconcile: 原请求结果未确认'}, status=409)
        with self.assertRaises(ClientError) as caught:
            Client(self.endpoint).call('message_send',
                {'ticket': 'AGENT-1', 'body': 'once', 'request_id': 'journal-uncertain'})
        self.assertEqual(caught.exception.code, 'needs_reconcile')
        self.assertEqual(caught.exception.status, 409)
        self.assertTrue(caught.exception.uncertain)
        self.assertEqual(len(self.requests), 1)

    def test_bounded_cli_wait_returns_live_run_without_cancelling_it(self):
        self.respond = lambda h, body: self.reply(h, {'id': 17, 'status': 'running', 'output': '仍在执行', 'output_len': 4})
        started = time.monotonic()
        result = self.cli('run', '17', '--wait', '.12')
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'running')
        self.assertTrue(self.requests)
        self.assertTrue(all(x['path'] == '/api/agent/run_get' for x in self.requests))
        self.assertTrue(all('x-webuddy-execution' not in x['headers'] for x in self.requests))

    def test_cli_wait_does_not_poll_again_after_deadline(self):
        from contextlib import redirect_stdout, redirect_stderr
        import io
        from unittest.mock import patch, Mock
        from tmh.workbench import main
        clock = [0.0]
        def sleep(seconds):
            clock[0] += seconds
        client = Mock()
        client.call.side_effect = [{'id': 17, 'status': 'running', 'output': '真实最新快照'},
                                   ClientError('expired second poll', 'connection_error')]
        out, err = io.StringIO(), io.StringIO()
        with patch('tmh.workbench.Client', return_value=client), patch('tmh.workbench.time.monotonic', side_effect=lambda: clock[0]), patch('tmh.workbench.time.sleep', side_effect=sleep), redirect_stdout(out), redirect_stderr(err):
            result = main(['run', '17', '--wait', '.12'])
        self.assertEqual(result, 0, err.getvalue())
        self.assertEqual(client.call.call_count, 1)
        self.assertEqual(json.loads(out.getvalue())['output'], '真实最新快照')

    def test_cli_preview_start_requires_run_and_request_id_before_http(self):
        for flags in ([], ['--run-id', '17'], ['--request-id', 'preview']):
            with self.subTest(flags=flags):
                result = self.cli('preview', 'AGENT-1', '--start', *flags)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stderr)['code'], 'invalid_arguments')
        self.assertEqual(self.requests, [])

    def test_generated_config_is_launchable_from_unrelated_cwd_without_secret(self):
        result = self.cli('config', 'cursor', '--read-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)['mcpServers']['webuddy']
        self.assertTrue(Path(config['command']).is_absolute())
        self.assertTrue(Path(config['args'][0]).is_file())
        self.assertNotIn('fixture-secret-token', result.stdout.decode())
        with tempfile.TemporaryDirectory() as directory:
            # Exercise the same absolute script configuration uses, without
            # requiring the separately tested optional MCP SDK here.
            executed = subprocess.run([config['command'], config['args'][0], 'status', '--endpoint', self.endpoint],
                                      cwd=directory, capture_output=True, timeout=5)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertTrue(json.loads(executed.stdout)['ok'])

    def test_endpoint_rejects_remote_plaintext_and_embedded_credentials(self):
        for endpoint in ('http://example.org', 'http://user:password@127.0.0.1:8791',
                         'https://example.org/path', 'https://example.org?token=secret',
                         'file:///tmp/database'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ClientError):
                Client(endpoint)
        self.assertEqual(self.requests, [])

    def test_malformed_endpoint_reports_json_instead_of_traceback(self):
        for endpoint in ('http://127.0.0.1:bad', 'http://127.0.0.1:99999', 'http://[::1'):
            with self.subTest(endpoint=endpoint):
                result = self.cli('status', '--endpoint', endpoint)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                error = json.loads(result.stderr)
                self.assertEqual(error['code'], 'invalid_endpoint')
                self.assertNotIn(b'Traceback', result.stderr)
        self.assertEqual(self.requests, [])

    def test_missing_optional_sdk_has_actionable_error_and_clean_stdout(self):
        # -S intentionally hides site packages while retaining this repository;
        # this models a dependency-free CLI installation, without uninstalling
        # or modifying anything in the user's Python environment.
        result = subprocess.run([sys.executable, '-S', '-m', 'tmh.workbench', 'mcp'],
                                cwd=ROOT, capture_output=True, input=b'', timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        error = json.loads(result.stderr)
        self.assertEqual(error['code'], 'missing_mcp_sdk')
        self.assertIn('mcp', error['error'].lower())
        self.assertNotIn(b'Traceback', result.stderr)
