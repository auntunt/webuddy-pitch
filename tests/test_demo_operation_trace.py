"""The demo recorder retains errors and raw bytes; it never grants acceptance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'examples/project-testing/jsherp/jenkins-demo/capture_step.py'


class OperationTraceTest(unittest.TestCase):
    def test_receipts_preserve_success_failure_timeout_and_launch_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            cases = [
                ('success', [sys.executable, '-c', 'import sys;sys.stdout.buffer.write(bytes([0,255,13,10]));sys.stderr.write("detail")'], 0, 'completed', 10),
                ('failure', [sys.executable, '-c', 'import sys;print("failure");sys.exit(7)'], 7, 'completed', 10),
                ('timeout', [sys.executable, '-c', 'import time;time.sleep(30)'], 124, 'timeout', .1),
                ('launch', [str(Path(directory)/'missing-executable')], 1, 'launch_failed', 10),
            ]
            for label, command, code, state, timeout in cases:
                with self.subTest(label=label):
                    result = subprocess.run([sys.executable, str(SCRIPT), '--output', directory,
                        '--label', label, '--actor', 'synthetic-agent', '--actor-type', 'agent',
                        '--timeout', str(timeout), '--', *command], capture_output=True, text=True)
                    self.assertEqual(result.returncode, code, result.stderr)
                    folder = Path(result.stdout.strip())
                    record = json.loads((folder/'step.json').read_text())
                    self.assertEqual(record['state'], state)
                    self.assertFalse(record['identity_verified'])
                    self.assertFalse(record['acceptance'])
                    self.assertEqual(record['actor_type'], 'agent')
                    for name, metadata in record['artifacts'].items():
                        content = (folder/name).read_bytes()
                        self.assertEqual(len(content), metadata['bytes'])
                        self.assertEqual(hashlib.sha256(content).hexdigest(), metadata['sha256'])
                    if label == 'success':
                        self.assertEqual((folder/'stdout.bin').read_bytes(), bytes([0,255,13,10]))
                    if label == 'failure':
                        self.assertIn(b'failure', (folder/'stdout.bin').read_bytes())
            self.assertEqual(len(list(Path(directory).iterdir())), 4)
