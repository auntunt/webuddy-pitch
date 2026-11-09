"""The downloadable personal-tool wheel installs the CLI and MCP bridge only."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tmh.platform.tool_client import MODULES, wheel


class ToolClientWheelTest(unittest.TestCase):
    def test_wheel_is_deterministic_and_contains_only_client_modules(self):
        name, data = wheel()
        self.assertEqual(wheel(), (name, data))
        self.assertRegex(name, r'^webuddy_client-[0-9.]+-py3-none-any\.whl$')
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = archive.namelist()
        self.assertEqual(sorted(n for n in names if n.startswith('tmh/')), sorted('tmh/' + m for m in MODULES))
        info = name.split('-py3')[0] + '.dist-info/'
        self.assertIn(b'Requires-Dist: mcp<2,>=1.30', archive.read(info + 'METADATA'))
        self.assertIn(b'webuddy = tmh.workbench:main', archive.read(info + 'entry_points.txt'))
        record = archive.read(info + 'RECORD').decode()
        self.assertEqual(len(record.splitlines()), len(names))

    def test_cli_runs_from_wheel_without_repository(self):
        name, data = wheel()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, name)
            with open(path, 'wb') as f:
                f.write(data)
            env = dict(os.environ, PYTHONPATH=path)
            result = subprocess.run([sys.executable, '-m', 'tmh.workbench', 'config', '--help'], cwd=tmp, env=env,
                                    capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('codex', result.stdout)
            terminal = subprocess.run([sys.executable, '-m', 'tmh.workbench', 'develop', 'ERP-1', '--action', 'status'],
                cwd=tmp, env=env, input='', capture_output=True, text=True, timeout=60)
            self.assertEqual(terminal.returncode, 1, terminal.stderr)
            self.assertEqual(__import__('json').loads(terminal.stderr)['code'], 'human_terminal_required')
            self.assertNotIn('ModuleNotFoundError', terminal.stderr)


    def test_downloaded_client_knows_its_server_and_imports_to_the_default_file(self):
        import json

        from tmh import workbench_credentials as credentials
        endpoint = 'https://ops.example.com/t/alpha'
        name, data = wheel(endpoint)
        self.assertNotEqual(data, wheel()[1])
        archive = zipfile.ZipFile(io.BytesIO(data))
        self.assertEqual(json.loads(archive.read('tmh/workbench_site.json')), {'endpoint': endpoint})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, name)
            with open(path, 'wb') as f:
                f.write(data)
            env = dict(os.environ, PYTHONPATH=path, HOME=tmp)
            for key in ('WEBUDDY_URL', 'WEBUDDY_CREDENTIAL_FILE', 'WEBUDDY_TOKEN'):
                env.pop(key, None)
            bare = subprocess.run([sys.executable, '-m', 'tmh.workbench'], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(bare.returncode, 0, bare.stderr)
            shown = json.loads(bare.stdout)
            self.assertEqual(shown['endpoint'], endpoint)
            self.assertIn(endpoint + '/tools', shown['next'][0])
            status = subprocess.run([sys.executable, '-m', 'tmh.workbench', 'status'], cwd=tmp, env=env,
                                    capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(json.loads(status.stderr)['code'], 'tool_credential_required')
            self.assertIn(endpoint + '/tools', status.stderr)
            self.assertNotIn('127.0.0.1', status.stdout + status.stderr)
        with tempfile.TemporaryDirectory() as home:
            old = os.environ.get('HOME')
            os.environ['HOME'] = home
            mask = os.umask(0o002)
            try:
                value = {'schema': 1, 'endpoint': endpoint, 'token': 'wbt_' + 'a' * 16 + '.' + 'a' * 32}
                first = credentials.save_default(value)
                second = credentials.save_default(dict(value, token='wbt_' + 'b' * 16 + '.' + 'b' * 32))
                self.assertEqual(first, second)
                self.assertEqual(credentials.default_file(), first)
                self.assertEqual(credentials.load(first)['token'], 'wbt_' + 'b' * 16 + '.' + 'b' * 32)
                self.assertEqual(sorted(os.listdir(os.path.dirname(first))), ['credential.json'])
                self.assertEqual(os.stat(os.path.join(home, '.config')).st_mode & 0o777, 0o700)
            finally:
                os.umask(mask)
                os.environ['HOME'] = old


if __name__ == '__main__':
    unittest.main()
