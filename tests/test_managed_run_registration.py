"""A managed budget receipt and its ordinary run must commit together."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tmh.platform import learning as L
from tmh.platform.store import Store


class ManagedRunRegistrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = Store(root / 'platform.db')
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project('APP', 'APP', str(root))
        self.other = Store(root / 'platform.db')
        self.addCleanup(self.other.db.close)
        self.store.x('CREATE TABLE synthetic_slot (id INTEGER PRIMARY KEY, run_id INTEGER UNIQUE NOT NULL)')

    def register(self, **kw):
        return self.store._create_run_in_tx(self.project['id'], None, 'synthetic',
                                            'learning', 'owner', '完整输入\r\n末尾  ', **kw)

    def test_run_and_inputs_are_not_visible_before_caller_commits_slot(self):
        with L.transaction(self.store) as db:
            rid = self.register()
            self.assertIsNone(self.other.run(rid))
            self.assertEqual(self.other.q('SELECT * FROM knowledge_run_inputs'), [])
            db.execute('INSERT INTO synthetic_slot VALUES(?,?)', (1, rid))
            self.assertEqual(self.other.q('SELECT * FROM synthetic_slot'), [])
        self.assertEqual(self.other.run(rid)['prompt'], '完整输入\r\n末尾  ')
        self.assertEqual(self.other.one('SELECT run_id FROM synthetic_slot')['run_id'], rid)
        self.assertEqual(self.other.one('SELECT run_id FROM knowledge_run_inputs')['run_id'], rid)

    def test_late_slot_failure_rolls_back_run_inputs_and_retry_reservation(self):
        original = self.store.create_run(self.project['id'], None, 'synthetic', 'ask', 'owner', 'original')
        before_runs = self.other.q('SELECT * FROM runs')
        before_inputs = self.other.q('SELECT * FROM knowledge_run_inputs')
        with self.assertRaises(sqlite3.IntegrityError):
            with L.transaction(self.store) as db:
                rid = self.register(retry_of=original['id'])
                db.execute('INSERT INTO synthetic_slot VALUES(?,?)', (1, rid))
                db.execute('INSERT INTO synthetic_slot VALUES(?,?)', (1, rid))
        self.assertEqual(self.other.q('SELECT * FROM runs'), before_runs)
        self.assertEqual(self.other.q('SELECT * FROM knowledge_run_inputs'), before_inputs)
        self.assertEqual(self.other.q('SELECT * FROM synthetic_slot'), [])
        retry = self.other.create_run(self.project['id'], None, 'synthetic', 'ask', 'owner',
                                      'retry', retry_of=original['id'])
        self.assertEqual(retry['retry_of'], original['id'])
        with self.assertRaisesRegex(ValueError, '已创建后续运行'):
            self.store.create_run(self.project['id'], None, 'synthetic', 'ask', 'owner',
                                  'another', retry_of=original['id'])

    def test_eligibility_failure_does_not_commit_callers_prior_write(self):
        with self.assertRaisesRegex(ValueError, '工作区已变化'):
            with L.transaction(self.store) as db:
                db.execute('INSERT INTO synthetic_slot VALUES(?,?)', (1, 999))
                self.register(expected_root='/different/workspace')
        self.assertEqual(self.other.q('SELECT * FROM synthetic_slot'), [])
        self.assertEqual(self.other.q('SELECT * FROM runs'), [])
        self.assertEqual(self.other.q('SELECT * FROM knowledge_run_inputs'), [])

    def test_private_registration_rejects_autocommit(self):
        with self.assertRaisesRegex(RuntimeError, 'transaction'):
            self.register()
        self.assertEqual(self.other.q('SELECT * FROM runs'), [])
        self.assertEqual(self.other.q('SELECT * FROM knowledge_run_inputs'), [])
