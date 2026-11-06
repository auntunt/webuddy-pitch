import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import test_testbox as fixtures
from tmh.platform.testbox_mcp import Bridge, latest_result, config_args
from tmh.platform.store import Store


class TestboxBridgeTest(unittest.TestCase):
    def setUp(self):
        fixtures.TestBoxTest.setUp(self)
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.addCleanup(lambda: fixtures.TestBoxTest.tearDown(self))
        self.data = self.tmp / 'data'; self.data.mkdir()
        (self.data / 'autoflow.json').write_text(json.dumps({'testbox': {'host': 'fixture', 'dir': str(self.tmp / 'remote'), 'timeout': 30}}))
        self.store = Store(self.data / 'platform.db'); self.addCleanup(self.store.db.close)
        self.store.add_project('P', 'fixture', str(self.repo))
        self.rid = self.store.create_run(self.store.project('P')['id'], None, 'codex', 'fix', 'tester', 'test')['id']
        self.store.update_run(self.rid, status='running', workdir=str(self.repo))
        self.bridge = Bridge(self.data, self.rid, self.repo); self.addCleanup(self.bridge.store.db.close)

    def test_actual_transport_patch_exit_and_stale_receipt(self):
        (self.repo / 'check.sh').write_text('test "$(cat result.txt)" = fixed\n')
        (self.repo / 'result.txt').write_text('fixed\n')
        out = self.bridge.call('testbox_run', {'script': 'check.sh'})
        self.assertEqual(out['results'][0]['exit_code'], 0)
        self.assertEqual(latest_result(self.data, self.rid, self.repo)['exit_code'], 0)
        (self.repo / 'result.txt').write_text('broken\n')
        self.assertNotEqual(latest_result(self.data, self.rid, self.repo)['exit_code'], 0)
        out = self.bridge.call('testbox_run', {'script': 'check.sh'})
        self.assertNotEqual(out['results'][0]['exit_code'], 0)
        self.assertNotEqual(latest_result(self.data, self.rid, self.repo)['exit_code'], 0)

    def test_missing_test_cancel_and_path_escape_are_not_success(self):
        self.assertNotEqual(latest_result(self.data, self.rid, self.repo)['exit_code'], 0)
        outside = self.tmp / 'outside.sh'; outside.write_text('exit 0')
        (self.repo / 'link.sh').symlink_to(outside)
        for path in ('../outside.sh', 'link.sh', 'missing.sh'):
            with self.assertRaises(ValueError):self.bridge.call('testbox_run', {'script': path})
        self.store.update_run(self.rid, status='cancelled')
        with self.assertRaises(ValueError):self.bridge.call('testbox_info', {})

    def test_mcp_script_import_and_protocol(self):
        args = json.loads(config_args(self.data, self.rid, self.repo)[3].split('=', 1)[1])
        messages = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
        p = subprocess.run([sys.executable] + args, input='\n'.join(json.dumps(m) for m in messages)+'\n', capture_output=True, text=True, check=True)
        replies = [json.loads(line) for line in p.stdout.splitlines()]
        self.assertEqual([t['name'] for t in replies[1]['result']['tools']], ['testbox_info', 'testbox_run'])

    def test_fixloop_requires_actual_remote_receipt_even_when_build_and_model_pass(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from tmh.platform.fixloop import FixLoop
        folder = self.data / 'runs' / str(self.rid); folder.mkdir(parents=True)
        loop = FixLoop.__new__(FixLoop)
        loop.r, loop.rid, loop.t = SimpleNamespace(data_dir=self.data), self.rid, None
        loop.p, loop.base = self.store.project(self.store.run(self.rid)['project_id']), 'baseline'
        loop.wt, loop.set = self.repo, {'rounds': 0, 'split_from': 3}
        loop.box, loop.nobuild, loop.ok, loop.remote_testing = self.bridge.box, '', True, True
        loop.brought, loop.log, loop.notes = set(), [], {}
        loop.commands = Mock(return_value=([('build', 'compile')], ''))
        loop.baseline = Mock(return_value='')
        loop.execute = Mock(return_value=[{'kind': 'build', 'command': 'compile', 'exit_code': 0}])
        loop.cancelled = Mock(return_value=False); loop.whole = Mock(); loop.say = Mock()
        loop.diagnose = Mock(return_value={'verdict': 'pass'})
        with patch('tmh.platform.fixloop.worktree_diff', return_value='diff --git a/app.js b/app.js\n+edit'):
            loop.run()
        saved = json.loads((folder / 'verify.json').read_text())
        self.assertEqual(saved['check'], 'fail')
        self.assertEqual(saved['verdict'], 'fail')

    def test_recheck_reruns_remote_script_and_keeps_failure(self):
        from tmh.platform.agents import Runner, worktree_diff
        from tmh.platform.fixloop import _recheck
        (self.repo / 'check.sh').write_text('test "$(cat result.txt)" = fixed\n')
        (self.repo / 'result.txt').write_text('fixed\n')
        self.bridge.call('testbox_run', {'script': 'check.sh'})
        self.store.update_run(self.rid, status='done', diff=worktree_diff(self.repo))
        folder = self.data / 'runs' / str(self.rid)
        (folder / 'verify.json').write_text(json.dumps({'check': 'pass', 'verdict': 'pass', 'remote_test_required': True}))
        (self.repo / 'result.txt').write_text('broken\n')
        result = _recheck(Runner(self.store, self.data), self.rid)
        self.assertEqual(result['check'], 'fail')
        self.assertEqual(result['verdict'], 'unknown')
        self.assertIn('check.sh', result['commands'][-1]['command'])
        self.assertNotEqual(result['commands'][-1]['exit_code'], 0)
