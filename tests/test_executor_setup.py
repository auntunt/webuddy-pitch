"""Executor scan, dedicated credential homes, secret isolation and connection probe."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmh.platform import agent_settings, agents, executor_setup
from tmh.platform.errors import ApiError


class BinEnvironmentValidationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)

    def save(self, **extra):
        view = agent_settings.view(self.data)
        conf = dict(title='Codex', models=[], defaults={}, timeout=60, **extra)
        return agent_settings.save(self.data, {'action': 'update', 'name': 'codex',
                                               'revision': view['revision'], 'config': conf})

    def test_bin_and_environment_saved(self):
        result = self.save(bin='C:\\Tools\\codex.exe', environment={'CODEX_HOME': 'D:\\cfg\\codex'})
        item = next(a for a in result['agents'] if a['name'] == 'codex')
        self.assertEqual(item['bin'], 'C:\\Tools\\codex.exe')
        self.assertEqual(item['environment'], {'CODEX_HOME': 'D:\\cfg\\codex'})
        raw = json.loads((self.data / 'agents.json').read_text())
        self.assertEqual(raw['codex']['bin'], 'C:\\Tools\\codex.exe')

    def test_validation(self):
        for bad in ('codex.exe;rm x', 'codex.exe|cat', 'codex$(x)', 'a"b'):
            with self.assertRaises(ApiError):
                self.save(bin=bad)
        for env in ({'PATH': '/x'}, {'CODEX_HOME': 'relative/dir'}, {'EVIL_KEY': '/x'}):
            with self.assertRaises(ApiError):
                self.save(environment=env)
        self.save(environment={})  # clears

    def test_view_exposes_no_secrets(self):
        executor_setup.set_secret(self.data, 'cursor', 'cursor', {'api_key': 'sk-fixture-secret-12345'})
        result = self.save(bin='agent')
        item = next(a for a in result['agents'] if a['name'] == 'cursor')
        self.assertTrue(item['secrets_set'])
        self.assertNotIn('sk-fixture-secret-12345', json.dumps(result))
        self.assertNotIn('sk-fixture-secret-12345', (self.data / 'agents.json').read_text())


class SecretHomesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)

    def test_secret_file_permissions(self):
        executor_setup.set_secret(self.data, 'cursor', 'cursor', {'api_key': 'k'})
        mode = stat.S_IMODE((self.data / 'executor-secrets.json').stat().st_mode)
        if os.name == 'posix':
            self.assertEqual(mode, 0o600)

    def test_codex_home_uses_env_key_not_raw_secret(self):
        env = executor_setup.set_secret(self.data, 'codex', 'codex',
                                        {'base_url': 'https://gw.example/v1', 'api_key': 'sk-real-key',
                                         'model': 'gpt-5', 'wire_api': 'responses'})
        home = Path(env['CODEX_HOME'])
        toml = (home / 'config.toml').read_text()
        self.assertIn('base_url = "https://gw.example/v1"', toml)
        self.assertIn('wire_api = "responses"', toml)
        self.assertIn('model = "gpt-5"', toml)
        self.assertIn('env_key = "WEBUDDY_KEY_CODEX"', toml)
        self.assertNotIn('sk-real-key', toml)
        self.assertEqual(executor_setup.spawn_env(self.data, 'codex', {'environment': env})['WEBUDDY_KEY_CODEX'], 'sk-real-key')
        with self.assertRaises(ApiError):
            executor_setup.set_secret(self.data, 'codex', 'codex', {'base_url': 'x'})
        with self.assertRaises(ApiError):
            executor_setup.set_secret(self.data, 'codex', 'codex', {'base_url': 'x', 'api_key': 'k', 'wire_api': 'sse'})

    def test_claude_home_and_cursor_env(self):
        env = executor_setup.set_secret(self.data, 'claude', 'claude',
                                        {'base_url': 'https://anth.example', 'api_key': 'tok', 'model': 'm'})
        settings = json.loads((Path(env['CLAUDE_CONFIG_DIR']) / 'settings.json').read_text())
        self.assertEqual(settings['env']['ANTHROPIC_BASE_URL'], 'https://anth.example')
        self.assertEqual(settings['env']['ANTHROPIC_AUTH_TOKEN'], 'tok')
        executor_setup.set_secret(self.data, 'cursor', 'cursor', {'api_key': 'ck'})
        self.assertEqual(executor_setup.spawn_env(self.data, 'cursor', {})['CURSOR_API_KEY'], 'ck')
        self.assertEqual(executor_setup.spawn_env(self.data, 'cursor', {'environment': {'X': '1'}})['X'], '1')

    def test_spawn_env_secret_never_in_prompt_or_output(self):
        executor_setup.set_secret(self.data, 'cursor', 'cursor', {'api_key': 'sk-never-visible-9'})
        env = executor_setup.spawn_env(self.data, 'cursor', {})
        self.assertIn('CURSOR_API_KEY', env)  # injected via env, never argv/prompt
        conf = agents.load_config(self.data)
        cmd = agents.command(conf, 'cursor', 'kb', 'p', Path('p'), Path('.'), Path('l'))
        self.assertNotIn('sk-never-visible-9', ' '.join(cmd))


class ScanTest(unittest.TestCase):
    def test_scan_finds_vendored_and_configured(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            npm = root / 'AppData' / 'Roaming' / 'npm'
            vendored = npm / 'node_modules' / '@openai' / 'codex' / 'vendor' / 'codex-win32-x64' / 'codex.exe'
            vendored.parent.mkdir(parents=True)
            vendored.touch()
            (npm / 'codex.cmd').touch()
            home = root / 'codex-home'
            home.mkdir()
            (home / 'auth.json').write_text('{}')
            (home / 'config.toml').write_text(
                'model = "gpt-5"\nmodel_provider = "gw"\n\n[model_providers.gw]\n'
                'base_url = "https://gw.example/v1"\nwire_api = "responses"\nenv_key = "GW_KEY"\n')
            env = {'APPDATA': str(npm.parent), 'LOCALAPPDATA': str(root / 'Local'),
                   'CODEX_HOME': str(home), 'CURSOR_API_KEY': 'x', 'PATH': ''}
            with patch.dict(os.environ, env, clear=True), patch.object(sys, 'platform', 'win32'), \
                    patch.object(executor_setup.subprocess, 'run', return_value=type('R', (), {'stdout': 'v1\n', 'stderr': '', 'returncode': 0})()):
                result = executor_setup.scan()
            codex = result['codex']
            self.assertTrue(any('codex' in Path(p).name for p in codex['executables']))
            self.assertEqual(codex['model'], 'gpt-5')
            self.assertEqual(codex['model_provider'], 'gw')
            self.assertEqual(codex['base_url'], 'https://gw.example/v1')
            self.assertTrue(codex['auth_present'])
            self.assertTrue(result['cursor']['api_key_set'])
            self.assertNotIn('sk-', json.dumps(result))


class ProbeTest(unittest.TestCase):
    def test_probe_marker_and_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'agent'
            exe.write_text('#!/bin/sh\ncat >/dev/null\necho \'{"type":"result","result":"TMH_OK"}\'\n')
            exe.chmod(0o755)
            report = executor_setup.probe('cursor', str(exe), dict(os.environ))
            self.assertTrue(report['ok'])
            exe.write_text('#!/bin/sh\ncat >/dev/null\necho done\n')
            report = executor_setup.probe('cursor', str(exe), dict(os.environ))
            self.assertFalse(report['ok'])
            self.assertIn('error_excerpt', report)
            with patch.object(executor_setup.subprocess, 'run', side_effect=executor_setup.subprocess.TimeoutExpired([], 45)):
                self.assertFalse(executor_setup.probe('codex', str(exe), {})['ok'])


if __name__ == '__main__':
    unittest.main()


class EndpointTest(unittest.TestCase):
    """The scan/test routes share the agent-settings admin gate."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        from types import SimpleNamespace as NS
        self.P = NS(data_dir=self.data, tenant_context=None)
        self.req = NS(user='demo', body={}, h=NS(_who='', headers={}, client_address=('127.0.0.1', 1),
                                                 server=NS(server_address=('127.0.0.1', 1))))

    def test_scan_gate_and_payload(self):
        from tmh.platform import server
        from unittest.mock import patch as _p
        with _p.object(executor_setup, 'scan', return_value={'codex': {'executables': ['/x/codex']}}):
            self.assertEqual(server.api_agent_scan(self.P, self.req), {'codex': {'executables': ['/x/codex']}})

    def test_test_route_errors_and_probe(self):
        from tmh.platform import server
        from unittest.mock import patch as _p
        with self.assertRaises(server.ApiError):
            server.api_agent_test(self.P, self.req)  # no name
        self.req.body = {'name': 'nope'}
        with self.assertRaisesRegex(server.ApiError, '没有'):
            server.api_agent_test(self.P, self.req)
        self.req.body = {'name': 'cursor'}
        with _p.object(executor_setup, 'probe', return_value={'ok': True}):
            self.assertEqual(server.api_agent_test(self.P, self.req), {'ok': True})
        # agent header must not reach the admin gate
        self.req.h.headers['X-Webuddy-Agent'] = '1'
        with self.assertRaises(server.ApiError):
            server.api_agent_test(self.P, self.req)


class AccessConfigTest(unittest.TestCase):
    """访问方式 card: loopback/LAN write of the bundle config file, token + preserved fields."""
    def setUp(self):
        import os
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.path = self.dir / 'Webuddy' / 'config.json'
        self._env = patch.dict(os.environ, {'WEBUDDY_BUNDLE_CONFIG': str(self.path)})
        self._env.start()
        self.addCleanup(self._env.stop)
        from tmh.platform import access_config
        self.ac = access_config

    def _P(self):
        from types import SimpleNamespace as NS
        return NS(data_dir=self.dir, tenant_context=None)

    def _req(self, body):
        from types import SimpleNamespace as NS
        return NS(user='demo', body=body, h=NS(_who='', headers={}, client_address=('127.0.0.1', 1),
                                               server=NS(server_address=('127.0.0.1', 1))))

    def test_unavailable_without_env(self):
        with patch.dict(__import__('os').environ, {}, clear=True):
            self.assertEqual(self.ac.view(), {'available': False})

    def test_lan_write_preserves_fields_and_returns_url_once(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({'data_dir': 'D:/keep', 'tools': {'codex': 'x.exe'},
                                         'environment': {'CODEX_HOME': 'D:/ch', 'TMH_TOKEN': 'old'}}))
        from tmh.platform import server
        out = server.api_access_config_save(self._P(), self._req({'mode': 'lan', 'port': 9000, 'public_url': ''}))
        self.assertTrue(out['restart_required'])
        self.assertNotIn('access_url', out)  # existing token preserved, not regenerated
        written = json.loads(self.path.read_text())
        self.assertEqual(written['data_dir'], 'D:/keep')
        self.assertEqual(written['tools'], {'codex': 'x.exe'})
        self.assertEqual(written['environment']['CODEX_HOME'], 'D:/ch')
        self.assertEqual(written['host'], '0.0.0.0')
        self.assertEqual(written['port'], 9000)
        self.assertEqual(written['environment']['TMH_TOKEN'], 'old')
        self.assertTrue(written['environment']['TMH_PUBLIC_URL'].startswith('http://'))
        view = server.api_access_config(self._P(), self._req({}))
        self.assertEqual(view['mode'], 'lan')
        self.assertTrue(view['token_set'])
        self.assertNotIn('access_url', view)
        # regenerate issues a new token and returns the full link exactly once
        out = server.api_access_config_save(self._P(), self._req({'mode': 'lan', 'port': 9000, 'public_url': '', 'regenerate': True}))
        self.assertIn('access_url', out)
        self.assertIn('token=', out['access_url'])
        self.assertNotEqual(json.loads(self.path.read_text())['environment']['TMH_TOKEN'], 'old')

    def test_local_clears_token_and_validation(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({'environment': {'TMH_TOKEN': 't', 'TMH_PUBLIC_URL': 'http://x'}}))
        from tmh.platform import server
        server.api_access_config_save(self._P(), self._req({'mode': 'local', 'port': 8790}))
        written = json.loads(self.path.read_text())
        self.assertEqual(written['host'], '127.0.0.1')
        self.assertNotIn('TMH_TOKEN', written['environment'])
        for bad in ({'mode': 'dmz'}, {'mode': 'lan', 'port': 'x'}, {'mode': 'lan', 'port': 70000},
                    {'mode': 'lan', 'port': 80, 'public_url': 'javascript:alert(1)'}):
            with self.assertRaises(server.ApiError):
                server.api_access_config_save(self._P(), self._req(bad))
