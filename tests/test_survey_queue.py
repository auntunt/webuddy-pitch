"""Survey queue diagnostics: live leases vs failed prerequisites; pending pages never end 'done'."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh import kb
from tmh.platform import survey


class QueueDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sv = survey.Survey(SimpleNamespace(data_dir=self.root),
                                {'id': 1, 'root': str(self.root)}, 'cursor', 2, 0, 'test')
        self.cp = self.root / 'claims.json'
        self.cp.write_text(json.dumps({'mod:pending': {'by': 'agent', 'at': time.time()}}), encoding='utf-8')
        self.raw = self.cp.read_bytes()
        for target, kwargs in [('_claims_path', {'return_value': self.cp}),
                               ('load_registry', {'return_value': {'mod:pending': {'status': kb.STATUS_NEW}}}),
                               ('pending', {'return_value': ['mod:pending']})]:
            p = patch.object(kb, target, **kwargs)
            p.start()
            self.addCleanup(p.stop)

    def test_held_page_is_not_dependency_failure(self):
        with patch.object(kb, 'next_jobs', return_value={'jobs': [], 'remaining': 1, 'waiting': [], 'claimed_by_others': 1}):
            self.assertEqual(self.sv._claim('w1'), ([], 'wait'))
        self.sv.say(self.sv._wait_message('w1'))
        self.assertIn('mod:pending', self.sv.log[-1])
        self.assertIn('领取者 agent', self.sv.log[-1])
        self.assertNotIn('前面失败', self.sv.log[-1])
        self.assertEqual(self.cp.read_bytes(), self.raw)  # active leases are never deleted

    def test_dependencies_reported(self):
        self.cp.write_text('{}', encoding='utf-8')
        with patch.object(kb, 'next_jobs', return_value={'jobs': [], 'remaining': 1, 'waiting': ['index']}):
            self.sv._claim('w1')
        self.sv.say(self.sv._wait_message('w1'))
        self.assertIn('等待前置内容：index', self.sv.log[-1])

    def test_unfinished_is_stopped_not_done(self):
        with patch.object(self.sv, '_save') as save:
            self.sv._end('done')
            self.assertEqual(self.sv.state, 'stopped')
            save.assert_called_once_with(False)
        self.assertIn('仍有 1 页待写', self.sv.log[-2])

    def test_empty_is_done(self):
        with patch.object(kb, 'pending', return_value=[]), patch.object(self.sv, '_save'):
            self.sv._end('done')
        self.assertEqual(self.sv.state, 'done')

    def test_limit_and_normal_claim(self):
        self.sv.limit = 1
        self.sv.finished = [{'ok': True}]
        with patch.object(kb, 'next_jobs') as claim:
            self.assertEqual(self.sv._claim('w1'), ([], 'limit'))
            claim.assert_not_called()
        self.sv.limit = 0
        self.sv.finished = []
        with patch.object(kb, 'next_jobs', return_value={'jobs': ['mod:pending'], 'remaining': 1}), \
                patch.object(self.sv, '_siblings', return_value=[]):
            self.assertEqual(self.sv._claim('w1'), (['mod:pending'], ''))

    def test_expired_claim_not_reported_active(self):
        self.cp.write_text(json.dumps({'mod:pending': {'by': 'agent', 'at': time.time() - 1900}}), encoding='utf-8')
        with patch.object(kb, 'next_jobs', return_value={'jobs': [], 'remaining': 1, 'waiting': []}):
            self.sv._claim('w1')
        self.assertEqual(self.sv.queue_wait['w1']['claims'], [])

    def test_view_exposes_queue_wait(self):
        with patch.object(kb, 'next_jobs', return_value={'jobs': [], 'remaining': 1, 'waiting': [], 'claimed_by_others': 1}), \
                patch.object(kb, 'coverage', return_value={}):
            self.sv._claim('w1')
            self.assertIn('w1', self.sv.view()['queue_wait'])


if __name__ == '__main__':
    unittest.main()
