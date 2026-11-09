"""The supervised-process worker runs when the script directory is not on sys.path."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmh.platform import supervised_process
from tmh.platform.supervised_process import run_supervised

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tmh' / 'platform' / 'supervised_process.py'


class SupervisorLaunchTest(unittest.TestCase):
    def test_script_imports_without_script_dir_or_pythonpath(self):
        env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
        result = subprocess.run([sys.executable, '-P', str(SCRIPT)], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertNotIn('ModuleNotFoundError', result.stderr)
        self.assertNotIn('ImportError', result.stderr)

    def test_run_supervised_without_pythonpath(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
            result = run_supervised([sys.executable, '-c', "print('child-ok')"],
                                    folder=Path(folder) / 'receipt',
                                    owner={'token': 'test', 'run_id': 0, 'data_dir': folder},
                                    cwd=folder, env=env, stdin=None, timeout=30)
            self.assertEqual(result.returncode, 0)
            self.assertIn('child-ok', result.output)

    def test_supervisor_env_is_not_modified(self):
        """The spawned supervisor must not gain a PYTHONPATH it then leaks to agents."""
        with tempfile.TemporaryDirectory() as folder:
            env = {'PATH': os.environ['PATH']}
            seen = []
            real = supervised_process.subprocess.Popen
            def spy(*args, **kwargs):
                seen.append(kwargs.get('env'))
                return real(*args, **kwargs)
            with patch.object(supervised_process.subprocess, 'Popen', side_effect=spy):
                run_supervised([sys.executable, '-c', "print('x')"],
                               folder=Path(folder) / 'receipt',
                               owner={'token': 'test', 'run_id': 0, 'data_dir': folder},
                               cwd=folder, env=env, stdin=None, timeout=30)
            self.assertTrue(seen)
            self.assertIs(seen[0], env)  # same object: nothing injected


if __name__ == '__main__':
    unittest.main()
