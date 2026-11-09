"""enabled:false removes an executor from catalog, dispatch, readiness and launcher probes."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tmh.platform import agents, learning_experiment_views, readiness


class EnabledExecutorsTest(unittest.TestCase):
    def test_disabled_excluded_and_dispatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'agents.json').write_text(json.dumps({'claude': {'enabled': False}, 'legacy-claude': {'bin': 'claude.exe', 'enabled': False}}))
            conf = agents.load_config(root)
            self.assertIn('claude', conf)
            names = {a['name'] for a in agents.available(root)}
            self.assertNotIn('claude', names)
            self.assertNotIn('legacy-claude', names)
            self.assertIn('cursor', names)
            with self.assertRaisesRegex(ValueError, '禁用'):
                agents.command(conf, 'claude', 'ask', 'test', root, root, root)
            with self.assertRaisesRegex(ValueError, '禁用'):
                agents.command(conf, 'legacy-claude', 'ask', 'test', root, root, root)

    def test_default_claude_stays_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertIn('claude', {a['name'] for a in agents.available(root)})

    def _store(self, rows):
        db = sqlite3.connect(':memory:')
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE runs(id INTEGER,agent TEXT,status TEXT,output TEXT,result TEXT,started TEXT,ended TEXT)')
        db.executemany('INSERT INTO runs VALUES(?,?,?,?,?,?,NULL)', rows)
        return db

    def _platform(self, root, db):
        def q(sql, args=()):
            return [dict(r) for r in db.execute(sql, args)]
        def one(sql, args=()):
            return next(iter(q(sql, args)), None)
        return SimpleNamespace(data_dir=root, store=SimpleNamespace(q=q, one=one))

    def test_readiness_only_enabled_executors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'agents.json').write_text(json.dumps({'claude': {'enabled': False}}))
            db = self._store([(1, 'cursor', 'done', 'CURSOR_OK', 'ok', ''),
                              (2, 'claude', 'failed', 'Not logged in', 'Not logged in', ''),
                              (3, 'claude', 'failed', 'Not logged in', 'Not logged in', '')])
            available = [{'name': 'cursor', 'title': 'Cursor Agent', 'available': True},
                         {'name': 'codex', 'title': 'Codex', 'available': True}]
            with patch.object(agents, 'available', return_value=available), \
                    patch.object(learning_experiment_views, 'unmanaged_run_clause', return_value='1=1'):
                rows = readiness._agents(self._platform(root, db))
                self.assertFalse(any(r['key'] == 'agent:claude' for r in rows))
                self.assertEqual(next(r for r in rows if r['key'] == 'runs')['state'], 'ok')
                # Disabled-executor history must not feed the streak.
                for i in range(4, 7):
                    db.execute("INSERT INTO runs VALUES(?,'claude','failed','Not logged in','Not logged in','',NULL)", (i,))
                rows = readiness._agents(self._platform(root, db))
                self.assertEqual(next(r for r in rows if r['key'] == 'runs')['state'], 'ok')
            db.close()

    def test_workspace_trust_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = self._store([(1, 'cursor', 'failed', 'Workspace Trust Required', 'failure', '')])
            available = [{'name': 'cursor', 'title': 'Cursor Agent', 'available': True}]
            with patch.object(agents, 'available', return_value=available), \
                    patch.object(learning_experiment_views, 'unmanaged_run_clause', return_value='1=1'):
                rows = readiness._agents(self._platform(root, db))
                bad = next(r for r in rows if r['key'] == 'agent:cursor')
                self.assertEqual(bad['state'], 'bad')
                self.assertIn('工作区尚未信任', bad['detail'])
            db.close()

    def test_interrupted_streak_not_blamed_on_login(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = self._store([(i, 'cursor', 'failed', 'KeyboardInterrupt', 'cancelled', '') for i in range(1, 4)])
            available = [{'name': 'cursor', 'title': 'Cursor Agent', 'available': True}]
            with patch.object(agents, 'available', return_value=available), \
                    patch.object(learning_experiment_views, 'unmanaged_run_clause', return_value='1=1'):
                rows = readiness._agents(self._platform(root, db))
                runs = next(r for r in rows if r['key'] == 'runs')
                self.assertEqual(runs['state'], 'bad')
                self.assertNotIn('登录', runs['fix'])
                self.assertNotIn('claude', runs['fix'])
            db.close()

    def test_signin_streak_message_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = self._store([(i, 'cursor', 'failed', 'Not logged in', 'Not logged in', '') for i in range(1, 4)])
            available = [{'name': 'cursor', 'title': 'Cursor Agent', 'available': True}]
            with patch.object(agents, 'available', return_value=available), \
                    patch.object(learning_experiment_views, 'unmanaged_run_clause', return_value='1=1'):
                runs = next(r for r in readiness._agents(self._platform(root, db)) if r['key'] == 'runs')
                self.assertIn('启用的执行器', runs['fix'])
            db.close()


if __name__ == '__main__':
    unittest.main()
