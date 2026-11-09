import shutil
import subprocess
import unittest
from pathlib import Path


class AssistantUITest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for UI checks')
    def test_async_input_isolation(self):
        root = Path(__file__).resolve().parents[1]
        subprocess.run(['node', str(root / 'tests/assistant_ui_checks.cjs')], cwd=root, check=True, capture_output=True, text=True)
