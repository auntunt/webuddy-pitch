import contextlib
import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tmh import deployment


class DeploymentConfigTest(unittest.TestCase):
    def test_read_only_inventory_keeps_complete_files_and_does_not_echo_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            secret = 'synthetic-private-value'
            valid = json.dumps({'custom': secret, 'goal': '目标' * 10000}, ensure_ascii=False).encode()
            (root / 'agents.json').write_bytes(valid)
            (root / 'autoflow.json').write_text('{"secret":"' + secret + '", broken')
            (root / 'pricing.json').write_text('[]')
            report = deployment.check_config(root)
            self.assertFalse(report['ok'])
            states = {row['file']: row['state'] for row in report['files']}
            self.assertEqual(states['agents.json'], 'valid_object')
            self.assertEqual(states['autoflow.json'], 'invalid_json')
            self.assertEqual(states['pricing.json'], 'invalid_type')
            self.assertEqual(states['project-tests.json'], 'not_configured')
            self.assertNotIn(secret, json.dumps(report))
            self.assertEqual((root / 'agents.json').read_bytes(), valid)

    def test_check_command_does_not_load_secrets_or_create_data(self):
        from tmh import cli
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            'TMH_DATA_DIR': str(Path(folder) / 'absent'), 'TMH_TOKEN_FILE': '/missing-secret',
        }, clear=True), patch.object(deployment, 'load_secrets', side_effect=AssertionError('must stay read only')):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.main(['deployment-check']), 0)
            self.assertTrue(json.loads(output.getvalue())['ok'])
            self.assertFalse((Path(folder) / 'absent').exists())

    def test_environment_defaults_and_explicit_flags_use_same_data_directory(self):
        from tmh.cli import build_parser
        with patch.dict(os.environ, {'TMH_DATA_DIR': '/external/data', 'TMH_HOST': '127.0.0.2',
                                     'TMH_PORT': '8899'}, clear=True):
            for command in (['serve'], ['user', 'list'], ['deployment-check'], ['access-init', '--owner', 'fixture']):
                self.assertEqual(build_parser().parse_args(command).data, '/external/data')
                self.assertEqual(build_parser().parse_args(command + ['--data', '/explicit/data']).data, '/explicit/data')
            parsed = build_parser().parse_args(['serve'])
            self.assertEqual((parsed.host, parsed.port), ('127.0.0.2', 8899))
            parsed = build_parser().parse_args(['serve', '--host', '127.0.0.3', '--port', '8999'])
            self.assertEqual((parsed.host, parsed.port), ('127.0.0.3', 8999))

    def test_native_serve_loads_file_secret_before_startup(self):
        from tmh import cli
        with tempfile.TemporaryDirectory() as folder:
            secret = Path(folder) / 'token'
            secret.write_text('synthetic-token\n')
            data = Path(folder) / 'external data'
            with patch.dict(os.environ, {'TMH_TOKEN_FILE': str(secret), 'TMH_DATA_DIR': str(data)}, clear=True), patch('tmh.platform.server.serve', return_value=0) as serve:
                self.assertEqual(cli.main(['serve']), 0)
                self.assertEqual(serve.call_args.args[0], data)
                self.assertEqual(os.environ['TMH_TOKEN'], 'synthetic-token')
                self.assertNotIn('TMH_TOKEN_FILE', os.environ)
            self.assertFalse(data.exists())

    def test_conflicting_or_unreadable_secret_refuses_serve_without_echoing_secret(self):
        from tmh import cli
        for env in ({'TMH_TOKEN': 'private-value', 'TMH_TOKEN_FILE': '/missing'},
                    {'TMH_TOKEN_FILE': '/missing'}):
            with self.subTest(env_keys=list(env)), patch.dict(os.environ, env, clear=True), patch('tmh.platform.server.serve') as serve:
                with self.assertRaises(SystemExit) as exc:
                    cli.main(['serve'])
                self.assertNotIn('private-value', str(exc.exception))
                serve.assert_not_called()

    def test_legacy_defaults_are_preserved_without_environment_overrides(self):
        from tmh.cli import build_parser
        with patch.dict(os.environ, {}, clear=True):
            parsed = build_parser().parse_args(['serve'])
            self.assertEqual((parsed.data, parsed.host, parsed.port), ('~/.tmh/platform', '127.0.0.1', 8790))

    def test_real_native_http_uses_environment_and_file_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / 'external data'
            secret = root / 'token'
            secret.write_text('synthetic-http-token\n')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = dict(os.environ, TMH_DATA_DIR=str(data), TMH_HOST='127.0.0.1',
                       TMH_PORT=str(port), TMH_TOKEN_FILE=str(secret), PYTHONUNBUFFERED='1')
            env.pop('TMH_TOKEN', None)
            env.pop('TMH_FEISHU_APP_SECRET_FILE', None)
            env.pop('TMH_FEISHU_APP_SECRET', None)
            env.pop('TMH_PREVIEW_PORT', None)
            env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            url = 'http://127.0.0.1:%d' % port
            with (root / 'serve.log').open('w+') as log:
                process = subprocess.Popen([sys.executable, '-m', 'tmh', 'serve'], cwd=root,
                                           env=env, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 25
                    while True:
                        if process.poll() is not None:
                            log.seek(0)
                            self.fail('serve exited: ' + log.read())
                        try:
                            response = opener.open(url + '/login', timeout=1)
                        except (OSError, urllib.error.URLError):
                            if time.monotonic() >= deadline:
                                self.fail('serve did not become ready')
                            time.sleep(0.1)
                        else:
                            self.assertEqual(response.status, 200)
                            response.close()
                            break
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        opener.open(url + '/api/projects', timeout=3)
                    self.assertEqual(denied.exception.code, 401)
                    request = urllib.request.Request(url + '/api/projects',
                                                    headers={'X-TMH-Token': 'synthetic-http-token'})
                    with opener.open(request, timeout=3) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(json.load(response), [])
                    self.assertTrue((data / 'platform.db').is_file())
                    self.assertFalse((root / '.tmh').exists())
                finally:
                    process.terminate()
                    process.wait(timeout=10)
                log.seek(0)
                self.assertNotIn('synthetic-http-token', log.read())
