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
