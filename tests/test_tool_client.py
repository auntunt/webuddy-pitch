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


if __name__ == '__main__':
    unittest.main()
