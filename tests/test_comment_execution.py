import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tmh.platform.api.runs import api_comment
from tmh.platform.agents import follow_up
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


class CommentExecutionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'platform.db')
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project('COMMENT', 'Comment', self.temp.name)
        self.ticket = self.store.create_ticket(self.project['id'], 'Continue')
        self.runner = SimpleNamespace(lock=threading.RLock(), start=Mock(return_value={'id': 42}), retry=Mock())
        self.P = SimpleNamespace(store=self.store, runner=self.runner, ticket=self.store.ticket)

    def send(self):
        return api_comment(self.P, SimpleNamespace(user='alice', body={
            'body': '继续修复，保留已有代码', 'request_id': 'once', 'continue': True}), self.ticket['key'])

    @patch('tmh.platform.app._routed_agent', return_value='cursor')
    def test_retry_returns_same_run_and_comment(self, route):
        first = self.send()
        self.assertEqual(first, self.send())
        self.assertEqual(first['run'], 42)
        self.runner.start.assert_called_once()
        self.assertEqual(len([e for e in self.store.events(self.ticket['id']) if e['kind'] == 'comment']), 1)

    @patch('tmh.platform.app._routed_agent', return_value='cursor')
    def test_validation_failure_keeps_comment_and_allows_retry(self, route):
        self.runner.start.side_effect = ValueError('route unavailable')
        with self.assertRaises(ApiError):
            self.send()
        self.runner.start.side_effect = None
        self.assertEqual(self.send()['run'], 42)
        self.assertEqual(len([e for e in self.store.events(self.ticket['id']) if e['kind'] == 'comment']), 1)

    def test_running_task_does_not_start_overlapping_work(self):
        with patch.object(self.store, 'runs', return_value=[{'status': 'running'}]):
            with self.assertRaises(ApiError):
                self.send()
        self.runner.start.assert_not_called()
        self.assertEqual(len([e for e in self.store.events(self.ticket['id']) if e['kind'] == 'comment']), 1)

    def test_interrupted_claim_does_not_start_duplicate(self):
        receipt = self.store.comment(self.ticket['id'], 'alice', '继续修复，保留已有代码', 'once')
        self.store.x('INSERT INTO idem VALUES(?,?,?)', ('comment-run:%s' % receipt['event_id'], '{}', 'now'))
        with self.assertRaises(ApiError):
            self.send()
        self.runner.start.assert_not_called()

    def test_followup_preserves_all_comments_during_previous_run(self):
        long = '要求' * 600 + '最后推送目标'
        for i in range(9):
            self.store.comment(self.ticket['id'], 'alice', f'{i}: {long}')
        prompt = follow_up(self.store, self.ticket, {'mode': 'analyze', 'started': '2000', 'ended': '2999'}, 'plan', 'here')
        for i in range(9):
            self.assertIn(f'{i}: {long}', prompt)
