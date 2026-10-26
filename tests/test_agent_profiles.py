"""Official-CLI profiles with a real local synthetic executable, never a model call."""
import json
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tmh.platform import agents
from tmh.platform.server import Platform, make_handler
from tmh.platform.store import Store


FIXTURE = r'''
import json, sys
from pathlib import Path
root = Path(__file__).parent
args = sys.argv[1:]
prompt = sys.stdin.read() if args[-1] == '-' else args[-1]
with (root / 'calls.jsonl').open('a') as out:
    out.write(json.dumps({'args': args, 'prompt': prompt}) + '\n')
print(json.dumps({'type': 'thread.started', 'thread_id': 'synthetic-thread'}), flush=True)
if '--fixture-busy' in args:
    print(json.dumps({'type': 'error', 'message': '429 rate limit'}), flush=True)
    sys.exit(1)
if '--fixture-incomplete' in args:
    print(json.dumps({'type': 'item.completed', 'item': {'type': 'reasoning', 'text': 'not a final answer'}}), flush=True)
    sys.exit(0)
if '--fixture-log-only' in args or '--fixture-empty-message' in args:
    print('WARNING synthetic executor returned no answer', flush=True)
    if '--fixture-empty-message' in args:
        print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '  \n'}}), flush=True)
    print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 120, 'output_tokens': 0}}), flush=True)
    sys.exit(0)
answer = 'synthetic complete answer'
if '--fixture-code-flow' in args:
    # Deterministic local stand-in: no SDK, credentials, network or model calls.
    workdir = Path(args[args.index('-C') + 1])
    source = workdir / 'app.py'
    if args[args.index('--sandbox') + 1] == 'workspace-write':
        assert source.read_text() == 'VALUE = 0\n'
        source.write_text('VALUE = 1\n')
        answer = 'Synthetic fixture changed app.py VALUE from 0 to 1; awaiting human review.'
    else:
        assert '诊断这次修改' in prompt
        assert source.read_text() == 'VALUE = 1\n'
        answer = 'Synthetic diagnosis only.\n```tmh-diag\n' + json.dumps({
            'verdict': 'pass', 'match': 'equivalent', 'match_why': 'Fixed fixture contract',
            'evidence': 'app.py contains VALUE = 1; the platform ran the project check',
            'cause': '', 'files': [], 'guide': ''}) + '\n```'
print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': answer}}), flush=True)
print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 120, 'cached_input_tokens': 80, 'output_tokens': 7}}), flush=True)
if '--fixture-failed' in args:
    print(json.dumps({'type': 'turn.failed', 'error': {'message': 'synthetic turn failed'}}), flush=True)
'''


class AgentProfilesTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='tmh-codex-profile-')
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        self.root = self.data / 'project'
        self.root.mkdir()
        self.exe = self.data / 'synthetic-codex'
        self.exe.write_text('#!' + sys.executable + '\n' + FIXTURE)
        self.exe.chmod(0o700)
        self.store = Store(self.data / 'platform.db')
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project('PROFILE', '隔离配置', str(self.root))
        self.runner = agents.Runner(self.store, self.data)
        self.config = {'engine': 'codex', 'bin': str(self.exe), 'profile': 'webuddy-cloudwave',
                       'prompt_transport': 'stdin', 'resume': False, 'retry_busy': False, 'timeout': 10}
        self.save_config()

    def save_config(self):
        self.conf = {'cloudwave-codex': self.config}
        (self.data / 'agents.json').write_text(json.dumps(self.conf))

    def call(self, prompt='synthetic prompt', **kwargs):
        run = self.store.create_run(self.project['id'], None, 'cloudwave-codex', 'ask', 'tester', prompt)
        self.store.update_run(run['id'], status='running')
        code, result = self.runner.invoke(run['id'], self.project, None, 'cloudwave-codex', self.conf,
                                         'ask', prompt, self.root, **kwargs)
        final = self.runner.finish_invocation(run['id'], code, result)
        return final, self.data / 'runs' / str(run['id'])

    def calls(self):
        return [json.loads(line) for line in (self.data / 'calls.jsonl').read_text().splitlines()]

    def test_profile_defaults_to_codex_binary_and_keeps_other_engines(self):
        self.config.pop('bin')
        self.save_config()
        seen = []
        with mock.patch.object(agents.shutil, 'which', side_effect=lambda name: seen.append(name) or '/synthetic/' + name):
            available = agents.available(self.data)
        self.assertEqual(seen, ['claude', 'codex', 'codex'])
        self.assertEqual({a['name'] for a in available}, {'claude', 'codex', 'cloudwave-codex'})
        alias = next(a for a in available if a['name'] == 'cloudwave-codex')
        self.assertTrue(alias['available'])
        self.assertEqual((alias['engine'], alias['profile']), ('codex', 'webuddy-cloudwave'))

    def test_profile_command_separates_identity_from_engine_and_keeps_permissions(self):
        paths = (self.data / 'prompt.md', self.root, self.data / 'last.md')
        for mode, sandbox in [('ask', 'read-only'), ('analyze', 'read-only'), ('fix', 'workspace-write')]:
            cmd = agents.command(self.conf, 'cloudwave-codex', mode, 'private task', *paths, model='gpt-5')
            self.assertEqual(cmd[cmd.index('--profile') + 1], 'webuddy-cloudwave')
            self.assertEqual(cmd[cmd.index('--sandbox') + 1], sandbox)
            self.assertEqual(cmd[cmd.index('-m') + 1], 'gpt-5')
            self.assertEqual(cmd[-1], '-')
            self.assertNotIn('private task', cmd)
            self.assertIn('--json', cmd)
        legacy = agents.command({'codex': {'bin': 'codex'}}, 'codex', 'ask', 'task', *paths)
        self.assertNotIn('--profile', legacy)
        self.assertNotIn('--json', legacy)
        custom = agents.command({'custom': {'cmd': ['custom', '{prompt}', '{model}']}}, 'custom', 'ask', 'task', *paths, model='m')
        self.assertEqual(custom, ['custom', 'task', 'm'])

    def test_invalid_profile_and_conflicts_fail_before_process_launch(self):
        for change in [{'profile': '../other'}, {'args': ['--profile', 'other']}, {'args': ['--profile=other']},
                       {'args': ['-pother']}, {'engine': 'claude'}, {'cmd': ['other']},
                       {'args': '--profile=other'}, {'args': [5]}, {'args': False}, {'args': {}}, {'resume': 'false'},
                       {'retry_busy': 'false'}, {'prompt_transport': 'other'}]:
            with self.subTest(change=change):
                conf = {'cloudwave-codex': dict(self.config, **change)}
                with self.assertRaises(ValueError):
                    agents.command(conf, 'cloudwave-codex', 'ask', 'task', self.data, self.root, self.data)
        self.assertFalse((self.data / 'calls.jsonl').exists())

    def test_real_stdin_json_reply_usage_and_original_evidence(self):
        prompt = '完整任务\n' * 50000  # larger than a safe single argv on common operating systems
        run, folder = self.call(prompt)
        self.assertEqual((run['status'], run['result']), ('done', 'synthetic complete answer'))
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['prompt'], prompt)
        self.assertNotIn(prompt, calls[0]['args'])
        self.assertEqual((folder / 'session.txt').read_text(), 'synthetic-thread')
        timing = json.loads((folder / 'timing.json').read_text())
        self.assertEqual(timing['tokens'], 127)  # cached input is already included in input_tokens
        self.assertEqual(timing['usage'], {'input_tokens': 120, 'cached_input_tokens': 80, 'output_tokens': 7})
        life = json.loads((folder / 'lifecycle.json').read_text())
        self.assertEqual(len(life['attempts']), 1)
        attempt = self.data / life['attempts'][0]['evidence']
        self.assertEqual(life['attempts'][0]['prompt_transport'], ['stdin'])
        self.assertEqual((attempt / 'prompt.md').read_bytes(), prompt.encode())
        original = (attempt / 'output.bin').read_bytes()
        self.assertIn(b'"type": "thread.started"', original)
        self.assertIn(b'"cached_input_tokens": 80', original)
        self.assertTrue(life['attempts'][0]['cleanup']['complete'])

    def test_resume_disabled_uses_full_fresh_task_and_never_retries_busy(self):
        self.config['args'] = ['--fixture-busy']
        self.save_config()
        with mock.patch.object(self.runner, '_pause', side_effect=AssertionError('must not retry')):
            run, folder = self.call('delta task', resume='old-thread', fresh='full current task')
        self.assertEqual(run['status'], 'failed')
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['prompt'], 'full current task')
        self.assertNotIn('resume', calls[0]['args'])
        self.assertNotIn('old-thread', calls[0]['args'])
        self.assertFalse(json.loads((folder / 'timing.json').read_text())['resumed'])
        with mock.patch.object(self.store, 'runs', side_effect=AssertionError('must not inherit a session')):
            self.assertEqual(agents.earlier_session(self.store, self.data, {'id': 1}, 'cloudwave-codex', 'plan'), ('', None))

    def test_zero_exit_without_complete_reply_or_with_failed_turn_is_not_success(self):
        for flag in ('--fixture-incomplete', '--fixture-failed'):
            with self.subTest(flag=flag):
                self.config['args'] = [flag]
                self.save_config()
                run, _ = self.call()
                self.assertEqual(run['status'], 'failed')
                self.assertNotEqual(run['exit_code'], 0)

    def test_zero_exit_completed_turn_with_only_logs_or_empty_message_fails(self):
        for flag in ('--fixture-log-only', '--fixture-empty-message'):
            with self.subTest(flag=flag):
                self.config['args'] = [flag]
                self.save_config()
                run, folder = self.call()
                self.assertEqual(run['status'], 'failed')
                self.assertNotEqual(run['exit_code'], 0)
                self.assertIn('没有返回完整的成功回执', run['result'])
                self.assertFalse((folder / 'last-message.md').exists())
                lifecycle = json.loads((folder / 'lifecycle.json').read_text())
                attempt = self.data / lifecycle['attempts'][0]['evidence']
                output = (attempt / 'output.bin').read_bytes()
                self.assertIn(b'WARNING synthetic executor returned no answer', output)
                self.assertIn(b'"type": "turn.completed"', output)
                self.assertIn(b'"output_tokens": 0', output)
                if flag == '--fixture-log-only':
                    self.assertNotIn(b'agent_message', output)

    def test_synthetic_api_ticket_fix_routes_profile_and_keeps_human_review_boundary(self):
        # This exercises production wiring with a local synthetic CLI, not an LLM.
        (self.root / 'app.py').write_text('VALUE = 0\n')
        (self.root / 'check.py').write_text(
            "from pathlib import Path\n"
            "namespace = {}\n"
            "exec(compile(Path('app.py').read_text(), 'app.py', 'exec'), namespace)\n"
            "assert type(namespace['VALUE']) is int\n"
            "print('project check VALUE=' + str(namespace['VALUE']))\n")
        for args in (['init', '-q'], ['add', 'app.py', 'check.py'],
                     ['-c', 'user.name=Synthetic Test', '-c', 'user.email=synthetic@example.invalid',
                      'commit', '-qm', 'Synthetic fixture baseline']):
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        original_head = agents.git(self.root, 'rev-parse', 'HEAD').strip()
        platform_data = (self.data / 'api-platform').resolve()
        platform_data.mkdir()
        config = dict(self.config, args=['--fixture-code-flow'])
        (platform_data / 'agents.json').write_text(json.dumps({'cloudwave-codex': config}))
        (platform_data / 'agent-routes.json').write_text(json.dumps({'schema': 1, 'projects': {
            'FLOW': {'agent': 'cloudwave-codex', 'allowed_agents': ['cloudwave-codex']}}}))
        (platform_data / 'autoflow.json').write_text(json.dumps({
            'on': False, 'rounds': 0, 'check': shlex.quote(sys.executable) + ' check.py'}))
        platform = Platform(platform_data, 'synthetic-operator')
        self.addCleanup(platform.store.db.close)
        platform.store.add_project('FLOW', 'Synthetic route flow', str(self.root))
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(platform))
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % httpd.server_address[1]

        def api(method, path, body=None):
            request = urllib.request.Request(base + path, method=method,
                headers={'X-TMH': '1', 'Content-Type': 'application/json'},
                data=json.dumps(body).encode() if body is not None else None)
            with urllib.request.urlopen(request, timeout=10) as response:
                self.assertEqual(response.status, 200)
                return json.loads(response.read())

        ticket = api('POST', '/api/tickets', {'project': 'FLOW', 'title': 'Set fixture VALUE to 1',
            'body': 'Change app.py VALUE from 0 to 1. Preserve check.py. Await human review.',
            'type': 'feature', 'auto': False})
        run = api('POST', '/api/tickets/%s/runs' % ticket['key'], {'mode': 'fix'})
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            run = api('GET', '/api/runs/%d' % run['id'])
            if run['status'] not in ('queued', 'running') and run['id'] not in platform.runner.busy:
                break
            time.sleep(.02)
        self.assertEqual((run['agent'], run['status'], run['exit_code']),
                         ('cloudwave-codex', 'done', 0), run['result'])
        self.assertEqual(run['decision'], '')
        self.assertEqual(platform.store.ticket(ticket['id'])['status'], 'doing')
        workdir = Path(run['workdir'])
        self.assertTrue(workdir.is_relative_to(platform_data / 'worktrees'))
        self.assertNotEqual(workdir, self.root)
        self.assertEqual((workdir / 'app.py').read_text(), 'VALUE = 1\n')
        self.assertEqual((self.root / 'app.py').read_text(), 'VALUE = 0\n')
        self.assertEqual((workdir / 'check.py').read_bytes(), (self.root / 'check.py').read_bytes())
        self.assertEqual(agents.git(self.root, 'rev-parse', 'HEAD').strip(), original_head)
        self.assertEqual(agents.git(workdir, 'rev-parse', 'HEAD').strip(), original_head)
        self.assertEqual(agents.git(self.root, 'status', '--porcelain').strip(), '')
        self.assertIn('-VALUE = 0', run['diff'])
        self.assertIn('+VALUE = 1', run['diff'])
        folder = platform_data / 'runs' / str(run['id'])
        verification = json.loads((folder / 'verify.json').read_text())
        self.assertEqual((verification['check'], verification['verdict']), ('pass', 'pass'))
        self.assertEqual(verification['files'], ['app.py'])
        self.assertEqual(len(verification['commands']), 1)
        check = verification['commands'][0]
        self.assertEqual(check['exit_code'], 0)
        self.assertIn('project check VALUE=1', check['output'])
        self.assertTrue(check['cleanup']['complete'])
        self.assertIn(b'project check VALUE=1', (platform_data / check['evidence'] / 'output.bin').read_bytes())
        baseline = list((platform_data / 'checks').glob('FLOW-*.json'))
        self.assertEqual(len(baseline), 1)
        self.assertIn('project check VALUE=0', json.loads(baseline[0].read_text())[0]['output'])
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual([call['args'][call['args'].index('--sandbox') + 1] for call in calls],
                         ['workspace-write', 'read-only'])
        for call in calls:
            self.assertEqual(call['args'][call['args'].index('--profile') + 1], 'webuddy-cloudwave')
            self.assertEqual(call['args'][call['args'].index('-C') + 1], str(workdir))
            self.assertNotIn('resume', call['args'])
            self.assertIn(ticket['title'], call['prompt'])
        lifecycle = json.loads((folder / 'lifecycle.json').read_text())
        self.assertTrue(lifecycle['finished'])
        for attempt in lifecycle['attempts']:
            evidence = platform_data / attempt['evidence']
            receipt = json.loads((evidence / 'process.json').read_text())
            self.assertTrue(receipt['supervised'])
            self.assertGreater(receipt['pid'], 0)
            self.assertTrue(receipt['cleanup']['complete'])
            self.assertTrue((evidence / 'output.bin').is_file())

    def test_start_uses_route_and_preserves_alias_in_run(self):
        (self.data / 'agent-routes.json').write_text(json.dumps({'schema': 1, 'projects': {
            'PROFILE': {'agent': 'cloudwave-codex', 'allowed_agents': ['cloudwave-codex']}}}))
        run = self.runner.start(self.project, None, '', 'ask', 'tester', question='Read this task')
        deadline = time.monotonic() + 12
        while self.store.run(run['id'])['status'] in ('queued', 'running') and time.monotonic() < deadline:
            time.sleep(.02)
        final = self.store.run(run['id'])
        self.assertEqual((final['agent'], final['status']), ('cloudwave-codex', 'done'), final['result'])
        self.assertEqual(len(self.calls()), 1)

    def test_direct_invoke_rechecks_project_route_before_execution(self):
        (self.data / 'agent-routes.json').write_text(json.dumps({'schema': 1, 'projects': {
            'PROFILE': {'agent': 'codex', 'allowed_agents': ['codex']}}}))
        with self.assertRaisesRegex(ValueError, '仅允许执行器'):
            self.call()
        self.assertFalse((self.data / 'calls.jsonl').exists())


if __name__ == '__main__':
    unittest.main()
