"""Cursor kb bridge: narrow tmh-kb.cmd entry, cli.json permissions, Windows kb prompt."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmh import install
from tmh.platform import agents
from tmh.platform.store import Store


def bridge_module(repo):
    import importlib.util
    path = repo / '.tmh' / 'tool' / 'tmh_kb_bridge.py'
    spec = importlib.util.spec_from_file_location('tmh_kb_bridge', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CursorKbBridgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        install.install(self.root, ['cursor'])
        self.bridge = bridge_module(self.root)
        self.store = Store(self.root / 'data' / 'platform.db')

    def test_cli_json_permissions_merged(self):
        cli = self.root / '.cursor' / 'cli.json'
        permissions = json.loads(cli.read_text(encoding='utf-8'))['permissions']
        self.assertIsInstance(permissions['allow'], list)
        self.assertIsInstance(permissions['deny'], list)
        for token in ('Shell(tmh-kb.cmd)', 'Write(.tmh/knowledge/**)'):
            self.assertIn(token, permissions['allow'])
        # Existing entries and deny rules are preserved.
        cli.write_text(json.dumps({'permissions': {'allow': ['Shell(ls)'], 'deny': ['Shell(rm)']}, 'other': True}))
        install._write_cursor_permissions(self.root)
        permissions = json.loads(cli.read_text(encoding='utf-8'))['permissions']
        self.assertIn('Shell(ls)', permissions['allow'])
        self.assertEqual(permissions['deny'], ['Shell(rm)'])
        self.assertNotIn('Shell(python)', permissions['allow'])

    def test_command_validation(self):
        for args in (['notes'], ['status'], ['next', '--page', 'dom:index'], ['done', 'dom:sensitivewords']):
            self.bridge.validate(args)
        for args in ([], ['next'], ['done', '../../x'], ['done', 'dom:x', '--force'], ['-c', 'print(1)'], ['confirm', 'dom:x']):
            with self.assertRaises(ValueError):
                self.bridge.validate(args)

    def test_dispatch_and_status(self):
        with patch.object(Path, 'cwd', return_value=self.root), \
                patch('subprocess.call', return_value=0) as call:
            self.assertEqual(self.bridge.main(['done', 'dom:index']), 0)
            argv = call.call_args.args[0]
            self.assertEqual(argv[-5:], ['kb', 'done', 'dom:index', '--repo', str(self.root.resolve())])
            self.assertNotIn('python3', argv[0])
        with patch.object(Path, 'cwd', return_value=self.root):
            self.assertEqual(self.bridge.main(['status']), 0)

    def test_windows_cursor_kb_prompt_uses_bridge(self):
        project = {'name': 'T', 'root': str(self.root), 'key': 'T', 'id': 1}
        with patch.object(sys, 'platform', 'win32'):
            prompt = agents.build_prompt(self.store, project, None, 'kb', target='dom:x', engine='cursor',
                                         reference_inputs=[])
            self.assertIn('tmh-kb.cmd next --page', prompt)
            self.assertIn('tmh-kb.cmd done', prompt)
            self.assertIn('tmh-kb.cmd status', prompt)
            self.assertNotIn('`python3 ', prompt)
            # Other engines on Windows get the real interpreter, quoted.
            prompt2 = agents.build_prompt(self.store, project, None, 'kb', target='dom:x', engine='claude',
                                          reference_inputs=[])
            self.assertIn('"%s"' % __import__('sys').executable, prompt2)
            self.assertNotIn('python3 ', prompt2)

    def test_posix_prompt_unchanged(self):
        project = {'name': 'T', 'root': str(self.root), 'key': 'T', 'id': 1}
        with patch.object(sys, 'platform', 'darwin'):
            prompt = agents.build_prompt(self.store, project, None, 'kb', target='dom:x', engine='cursor',
                                         reference_inputs=[])
            self.assertIn('python3 ', prompt)
            self.assertNotIn('tmh-kb.cmd', prompt)

    def test_steer_hint_per_platform(self):
        posix = agents.steer_hint('kb')
        self.assertIn('cat "$TMH_NOTES" 2>/dev/null', posix)
        with patch.object(sys, 'platform', 'win32'):
            self.assertIn('tmh-kb.cmd notes', agents.steer_hint('kb', 'cursor'))
            other = agents.steer_hint('kb', 'codex')
            self.assertIn('TMH_NOTES', other)
            self.assertIn(__import__('sys').executable, other)
            self.assertNotIn('cat ', other)
        with patch.object(sys, 'platform', 'darwin'):
            self.assertEqual(agents.steer_hint('kb', 'cursor'), posix)


if __name__ == '__main__':
    unittest.main()
