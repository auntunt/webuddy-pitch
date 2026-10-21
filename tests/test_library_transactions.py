"""Real SQLite rollback, legacy provenance and external-candidate integration.

All repositories and platform state are temporary. Independent connections and
zero-wait lock probes control commit ordering, without simulated transactions,
weakened assertions or relaxed product/test deadlines.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import sqlite_compat
from tests import test_external_candidates as candidate_fixtures
from tests import test_library_review as review_fixtures
from tests import test_project_library as fixtures
from tmh.platform import agent_api, candidates, project_library as library
from tmh.platform.errors import ApiError
from tmh.platform.server import Platform
from tmh.platform.store import Store


@unittest.skipUnless(os.name == 'posix' and shutil.which('git'), 'requires POSIX supervision and local Git')
class LibraryTransactionTest(unittest.TestCase):
    setUp = fixtures.ProjectLibraryTest.setUp
    tearDown = fixtures.ProjectLibraryTest.tearDown
    git = fixtures.ProjectLibraryTest.git
    project = fixtures.ProjectLibraryTest.project
    commit = fixtures.ProjectLibraryTest.commit
    start = fixtures.ProjectLibraryTest.start
    wait_terminal = fixtures.ProjectLibraryTest.wait_terminal
    build = fixtures.ProjectLibraryTest.build
    pair = review_fixtures.LibraryReviewTest.pair
    legacy_inputs = review_fixtures.LibraryReviewTest.legacy_inputs
    call = candidate_fixtures.ExternalCandidateTest.call
    submit = candidate_fixtures.ExternalCandidateTest.submit
    verify = candidate_fixtures.ExternalCandidateTest.verify

    def other_store(self):
        other = Store(self.store.path)
        self.addCleanup(other.db.close)
        other.db.execute('PRAGMA busy_timeout=0')
        return other

    def candidate_project(self, *, maintain=False):
        self.store.db.close()
        self.P = Platform(self.root / 'platform', user='fixture-human')
        self.store = self.P.store
        project = self.project('EXT', {
            'app.py': 'VALUE = 1\n',
            '.gitignore': '__pycache__/\n',
            'tests/test_app.py': ('import unittest\nfrom app import VALUE\n'
                                  'class Test(unittest.TestCase):\n'
                                  ' def test_value(self): self.assertEqual(VALUE, 1)\n'),
            '.tmh/config.json': json.dumps({'commands': {
                'build': sys.executable + ' -m py_compile app.py',
                'test': sys.executable + ' -m unittest discover -s tests -v'}}),
        })
        if maintain:
            revision = self.build(project)
            library.configure(self.store, project, ['reference'], 'reference')
            project = library.derive(self.store, project, revision['id'], '', '',
                                     'fixture operator', maintain=True)['project']
        self.p = project
        self.repo = Path(project['root'])
        self.base = self.git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'app.py').write_text('VALUE = 2\n')
        test = self.repo / 'tests/test_app.py'
        test.write_text(test.read_text().replace('assertEqual(VALUE, 1)', 'assertEqual(VALUE, 2)'))
        self.sha = self.commit(project, 'Synthetic candidate')
        self.ticket = self.call('ticket_create', {
            'project': project['key'], 'title': 'Use value 2', 'body': 'Return value 2',
            'request_id': 'create'})['ticket']
        self.criteria = [{'id': 'A1', 'text': 'Value 2 is returned', 'check': 'Run its test'}]

    def arguments(self):
        return {'ticket': self.ticket['key'], 'base_commit': self.base, 'commit': self.sha,
                'requirement_hash': agent_api._requirement(self.store.ticket(self.ticket['id']), self.store),
                'criteria': self.criteria, 'summary': 'Synthetic external candidate'}

    def test_new_candidate_in_maintained_workspace_can_really_verify(self):
        self.candidate_project(maintain=True)
        submitted = self.submit()
        self.assertTrue(library.run_current(self.store, self.p, submitted['run_id']),
                        'a newly registered candidate must not be mistaken for unknown legacy evidence')
        inputs = self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (submitted['run_id'],))
        self.assertEqual(inputs['project_root'], self.p['root'])
        self.assertEqual(json.loads(inputs['bindings']), [])
        verified = self.verify(submitted['candidate_id'])
        self.assertTrue(verified['current'])
        self.assertTrue(verified['verification_passed'], verified['verification'])
        self.assertEqual(verified['verification']['checked_commit'], self.sha)
        self.assertEqual(verified['verification']['checked_base'], self.base)
        self.assertFalse(verified['human_accepted'])

    def test_candidate_input_failure_rolls_back_run_candidate_event_and_ticket(self):
        self.candidate_project()
        ticket = self.store.ticket(self.ticket['id'])
        events = self.store.events(ticket['id'])
        self.store.x("CREATE TRIGGER reject_candidate_input BEFORE INSERT ON knowledge_run_inputs "
                     "BEGIN SELECT RAISE(ABORT, 'synthetic candidate input failure'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'synthetic candidate input failure'):
            candidates.submit(self.P, 'agent:writer', self.arguments(), lambda: None)
        self.assertEqual(self.store.q('SELECT * FROM runs'), [])
        self.assertEqual(self.store.q('SELECT * FROM knowledge_run_inputs'), [])
        self.assertEqual(self.store.q('SELECT * FROM code_candidates'), [])
        self.assertEqual(self.store.ticket(ticket['id']), ticket)
        self.assertEqual(self.store.events(ticket['id']), events)
        self.assertFalse(self.store.db.in_transaction)
        patches = list((self.P.data_dir / 'candidates').glob('*/change.patch'))
        self.assertEqual(len(patches), 1)
        self.assertTrue(patches[0].read_bytes(), 'the failed attempt must keep its complete original patch')
        self.store.x('DROP TRIGGER reject_candidate_input')
        retry = candidates.submit(self.P, 'agent:writer', self.arguments(), lambda: None)
        self.assertTrue(library.run_current(self.store, self.p, retry['run_id']))
        self.assertEqual(len(self.store.q('SELECT * FROM runs')), 1)

    def test_candidate_rejects_workspace_switched_after_git_preparation(self):
        self.candidate_project()
        revision = self.build(self.p)
        other = self.other_store()
        original = candidates._git
        switched = []

        def switch_after_ref(root, *args, **kwargs):
            result = original(root, *args, **kwargs)
            if args[0] == 'update-ref' and not switched:
                library.configure(other, self.p, ['reference'], 'reference')
                switched.append(library.derive(other, self.p, revision['id'], '', '',
                                               'fixture operator', maintain=True)['project'])
            return result

        with patch.object(candidates, '_git', side_effect=switch_after_ref):
            with self.assertRaisesRegex(ApiError, '工作区'):
                candidates.submit(self.P, 'agent:writer', self.arguments(), lambda: None)
        self.assertEqual(len(switched), 1)
        self.assertNotEqual(switched[0]['root'], self.p['root'])
        self.assertEqual(self.store.q('SELECT * FROM runs'), [])
        self.assertEqual(self.store.q('SELECT * FROM knowledge_run_inputs'), [])
        self.assertEqual(self.store.q('SELECT * FROM code_candidates'), [])
        self.assertFalse(self.store.db.in_transaction)
        other.db.execute('BEGIN IMMEDIATE')
        other.db.rollback()  # rejection must release the database writer too

    def test_missing_legacy_binding_cannot_be_filled_with_current_workspace(self):
        project = self.project('STD')
        revision = self.build(project)
        run = self.store.create_run(project['id'], None, 'synthetic', 'plan', 'fixture', 'old plan')
        self.store.update_run(run['id'], status='done', exit_code=0)
        self.store.x('DELETE FROM knowledge_run_inputs WHERE run_id=?', (run['id'],))
        library.configure(self.store, project, ['reference'], 'reference')
        maintained = library.derive(self.store, project, revision['id'], '', '',
                                   'fixture operator', maintain=True)['project']
        before = self.store.run(run['id'])
        self.assertFalse(library.run_current(self.store, maintained, run['id']))
        with self.assertRaisesRegex(ValueError, '历史|原始证据'):
            library.bind_run(self.store, maintained, run['id'], [])
        self.assertFalse(library.run_current(self.store, maintained, run['id']))
        self.assertIsNone(self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (run['id'],)))
        self.assertEqual(self.store.run(run['id']), before)
        self.assertFalse(self.store.db.in_transaction)

    def test_legacy_fallback_still_requires_a_real_run_from_this_project(self):
        first, second = self.project('FIRST'), self.project('SECOND')
        run = self.store.create_run(first['id'], None, 'synthetic', 'ask', 'fixture', 'old prompt')
        self.store.x('DELETE FROM knowledge_run_inputs WHERE run_id=?', (run['id'],))
        self.assertTrue(library.run_current(self.store, first, run['id']))
        self.assertFalse(library.run_current(self.store, second, run['id']),
                         'empty references cannot identify another project as the source')
        self.assertFalse(library.run_current(self.store, first, run['id'] + 999))

    def test_currentness_cannot_mix_grants_from_different_database_snapshots(self):
        first, customer, _, _ = self.pair()
        second = self.project('OTHER')
        revision = self.build(second)
        library.grant(self.store, second, customer['key'], [], 'fixture operator')
        library.reference(self.store, customer, revision['id'], [], 'second source', 'fixture operator')
        run = self.store.create_run(customer['id'], None, 'synthetic', 'ask', 'fixture', 'both sources')
        self.store.x('DELETE FROM knowledge_grants WHERE source_project=?', (second['id'],))
        self.assertFalse(library.run_current(self.store, customer, run['id']))
        other = self.other_store()
        original = self.store.one
        attempts = []

        def swap_after_first_grant(sql, args=()):
            value = original(sql, args)
            if sql.startswith('SELECT scopes FROM knowledge_grants') and args[0] == first['id'] and not attempts:
                self.assertIsNotNone(value)
                try:
                    with other.db:
                        other.db.execute('BEGIN IMMEDIATE')
                        other.db.execute('DELETE FROM knowledge_grants WHERE source_project=?', (first['id'],))
                        other.db.execute("INSERT INTO knowledge_grants VALUES(?,?,'[]','fixture','fixture')",
                                         (second['id'], customer['id']))
                except sqlite3.OperationalError as exc:
                    self.assertTrue(sqlite_compat.is_busy(exc), exc)
                    attempts.append('serialized')
                else:
                    attempts.append('swapped')
            return value

        with patch.object(self.store, 'one', side_effect=swap_after_first_grant):
            self.assertFalse(library.run_current(self.store, customer, run['id']),
                             'there was never a database snapshot with both sources authorized')
        self.assertEqual(len(attempts), 1)
        self.assertFalse(self.store.db.in_transaction)
        self.assertFalse(other.db.in_transaction)

    def test_legacy_candidate_is_usable_only_before_workspace_replacement(self):
        self.candidate_project()
        old = self.submit()
        row = candidates._row(self.P, old['candidate_id'])
        # Reproduce the shipped legacy fingerprint and absent input record.
        fingerprint = candidates._hash({
            'ticket': self.ticket['id'], 'base': self.base, 'commit': self.sha,
            'requirement': row['requirement_hash'], 'configuration': row['configuration_hash'],
            'criteria': self.criteria})
        self.store.x('UPDATE code_candidates SET fingerprint=? WHERE id=?', (fingerprint, row['id']))
        self.store.x('DELETE FROM knowledge_run_inputs WHERE run_id=?', (old['run_id'],))
        self.assertTrue(candidates.view(self.P, row['id'])['current'])
        original = self.store.run(old['run_id'])
        replay = self.submit(request_id='legacy-replay')
        self.assertEqual(replay['candidate_id'], old['candidate_id'])
        self.assertTrue(replay['reused'])
        self.assertEqual(len(self.store.q('SELECT * FROM code_candidates')), 1)
        self.assertIsNone(self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (old['run_id'],)))
        revision = self.build(self.p)
        library.configure(self.store, self.p, ['reference'], 'reference')
        maintained = library.derive(self.store, self.p, revision['id'], '', '',
                                   'fixture operator', maintain=True)['project']
        # Local object transfer explicitly restores the same Git evidence and
        # ref. Its presence cannot prove which workspace produced the run.
        self.git(maintained['root'], 'fetch', '--no-tags', '--no-write-fetch-head',
                 self.p['root'], row['ref'] + ':' + row['ref'])
        self.assertEqual(self.git(maintained['root'], 'rev-parse', row['ref']), self.sha)
        self.assertEqual(candidates.configuration(self.P, maintained), row['configuration_hash'])
        self.assertFalse(candidates.view(self.P, row['id'])['current'])
        new = self.submit(request_id='current-workspace')
        self.assertNotEqual(new['candidate_id'], row['id'])
        self.assertTrue(library.run_current(self.store, maintained, new['run_id']))
        self.assertIsNone(self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (old['run_id'],)))
        self.assertEqual(self.store.run(old['run_id']), original)

    def test_candidate_records_exact_references_and_rejects_revocation(self):
        self.candidate_project()
        source = self.project('STD')
        revision = self.build(source)
        library.grant(self.store, source, self.p['key'], ['modules'], 'fixture operator')
        library.reference(self.store, self.p, revision['id'], ['modules'], 'implementation input', 'fixture operator')
        expected = library.bindings(self.store, self.p)
        submitted = self.submit()
        self.assertTrue(library.run_current(self.store, self.p, submitted['run_id']))
        original = self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (submitted['run_id'],))
        self.assertEqual(json.loads(original['bindings']), expected)
        self.store.x('DELETE FROM knowledge_grants WHERE source_project=?', (source['id'],))
        self.assertFalse(candidates.view(self.P, submitted['candidate_id'])['current'])
        with self.assertRaisesRegex(ApiError, '授权'):
            candidates.submit(self.P, 'agent:writer', self.arguments(), lambda: None)
        self.assertEqual(self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (submitted['run_id'],)), original)
        self.assertEqual(len(self.store.q('SELECT * FROM runs')), 1)
        self.assertFalse(self.store.db.in_transaction)

    def test_candidate_preview_obeys_currentness_recheck_after_source_lock(self):
        self.candidate_project()
        source = self.project('STD')
        revision = self.build(source)
        library.grant(self.store, source, self.p['key'], [], 'fixture operator')
        library.reference(self.store, self.p, revision['id'], [], 'implementation input', 'fixture operator')
        submitted = self.submit()
        verified = self.verify(submitted['candidate_id'])
        self.assertTrue(verified['verification_passed'], verified['verification'])
        other = self.other_store()
        view = candidates.view
        observed = []

        def revoke_after_first_view(*args, **kwargs):
            value = view(*args, **kwargs)
            observed.append(value)
            if len(observed) == 1:
                self.assertTrue(value['current'])
                other.x('DELETE FROM knowledge_grants WHERE source_project=?', (source['id'],))
            return value

        # Only the final service dispatch is intercepted; the verification,
        # grant mutation, both evidence reads and source lock are real.
        with patch.object(candidates, 'view', side_effect=revoke_after_first_view), \
                patch('tmh.platform.preview.start', return_value={'state': 'up'}) as launch:
            with self.assertRaises(ApiError):
                candidates.execute(self.P, 'agent:writer', 'candidate_preview',
                                   {'candidate_id': submitted['candidate_id']})
            launch.assert_not_called()
        self.assertEqual(len(observed), 2)
        self.assertFalse(observed[1]['current'])
        self.assertEqual(self.store.q("SELECT * FROM events WHERE kind='preview'"), [])

    def test_grant_merge_and_reference_are_rolled_back_together(self):
        source, customer, revision, _ = self.pair()
        library.grant(self.store, source, customer['key'], ['private'], 'fixture operator')
        grants = self.store.q('SELECT * FROM knowledge_grants')
        refs = self.store.q('SELECT * FROM knowledge_references')
        self.store.x("CREATE TRIGGER reject_reference BEFORE INSERT ON knowledge_references "
                     "BEGIN SELECT RAISE(ABORT, 'synthetic reference failure'); END")
        other = self.other_store()
        args = {'action': 'reference', 'revision_id': revision['id'], 'scopes': ['public'],
                'purpose': 'new public scope', 'grant': True}
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'synthetic reference failure'):
            library.act(SimpleNamespace(store=self.store), customer, args, 'fixture operator')
        self.assertEqual(other.q('SELECT * FROM knowledge_grants'), grants)
        self.assertEqual(other.q('SELECT * FROM knowledge_references'), refs)
        self.assertFalse(self.store.db.in_transaction)
        other.db.execute('BEGIN IMMEDIATE')
        other.db.rollback()
        self.store.x('DROP TRIGGER reject_reference')
        self.assertTrue(library.act(SimpleNamespace(store=self.store), customer, args, 'fixture operator')['available'])
        self.assertTrue(library._allowed(other, source['id'], customer['id'], ['public', 'private']))

    def test_commit_busy_rolls_back_run_inputs_and_retry_slot(self):
        project = self.project('CLIENT')
        run = self.store.create_run(project['id'], None, 'synthetic', 'ask', 'fixture', 'original')
        self.store.update_run(run['id'], status='failed', exit_code=1)
        before_runs = self.store.q('SELECT * FROM runs')
        before_inputs = self.store.q('SELECT * FROM knowledge_run_inputs')
        other = self.other_store()
        self.store.db.execute('PRAGMA busy_timeout=0')
        try:
            other.db.execute('BEGIN')
            other.q('SELECT * FROM runs')  # a real shared lock prevents COMMIT
            with self.assertRaises(sqlite3.OperationalError) as caught:
                self.store.create_run(project['id'], None, 'synthetic', 'ask', 'fixture', 'retry', retry_of=run['id'])
            self.assertTrue(sqlite_compat.is_busy(caught.exception), caught.exception)
            self.assertFalse(self.store.db.in_transaction)
            self.assertEqual(other.q('SELECT * FROM runs'), before_runs)
            self.assertEqual(other.q('SELECT * FROM knowledge_run_inputs'), before_inputs)
        finally:
            other.db.rollback()
        retry = self.store.create_run(project['id'], None, 'synthetic', 'ask', 'fixture', 'retry', retry_of=run['id'])
        self.assertEqual(retry['retry_of'], run['id'])
        self.assertTrue(library.run_current(other, project, retry['id']))

    def test_failed_migration_preserves_legacy_rows_and_can_be_retried(self):
        project = self.project('CLIENT')
        run = self.store.create_run(project['id'], None, 'synthetic', 'ask', 'fixture', 'legacy')
        other = self.other_store()
        self.store.db.execute('PRAGMA busy_timeout=0')
        for failure in ('statement', 'commit'):
            with self.subTest(failure=failure):
                self.legacy_inputs()
                original = self.store.q('SELECT * FROM knowledge_run_inputs')
                try:
                    if failure == 'statement':
                        self.store.db.set_authorizer(
                            lambda action, *args: sqlite_compat.SQLITE_DENY if action == sqlite_compat.SQLITE_ALTER_TABLE else sqlite_compat.SQLITE_OK)
                    else:
                        other.db.execute('BEGIN')
                        other.q('SELECT * FROM knowledge_run_inputs')
                    with self.assertRaises(sqlite3.DatabaseError) as caught:
                        library.schema(self.store)
                    if failure == 'statement':
                        self.assertTrue(sqlite_compat.is_auth_denied(caught.exception), caught.exception)
                    else:
                        self.assertTrue(sqlite_compat.is_busy(caught.exception), caught.exception)
                finally:
                    # CPython 3.10 + SQLite 3.37 ignores set_authorizer(None) after a callback
                    # denied by return code, so restore a permissive authorizer instead: the
                    # retry below and the teardown must be real writes, not silently denied.
                    self.store.db.set_authorizer(lambda action, *args: sqlite_compat.SQLITE_OK)
                    other.db.rollback()
                self.assertFalse(self.store.db.in_transaction)
                self.assertNotIn('project_root', {r['name'] for r in self.store.q('PRAGMA table_info(knowledge_run_inputs)')})
                self.assertEqual(other.q('SELECT * FROM knowledge_run_inputs'), original)
                other.db.execute('BEGIN IMMEDIATE')
                other.db.rollback()
                library.schema(self.store)
                self.assertEqual(self.store.q('SELECT * FROM knowledge_run_inputs'),
                                 [dict(row, project_root='') for row in original])
                self.assertTrue(library.run_current(other, project, run['id']))
                self.assertFalse(self.store.db.in_transaction)

    def test_currentness_snapshot_never_commits_its_callers_transaction(self):
        project = self.project('CLIENT')
        run = self.store.create_run(project['id'], None, 'synthetic', 'ask', 'fixture', 'prompt')
        other = self.other_store()
        before = other.project(project['id'])
        try:
            self.store.db.execute('BEGIN IMMEDIATE')
            self.store.db.execute("UPDATE projects SET name='uncommitted' WHERE id=?", (project['id'],))
            self.assertTrue(library.run_current(self.store, project, run['id']))
            self.assertFalse(library.run_current(self.store, project, run['id'] + 999))
            self.assertTrue(self.store.db.in_transaction)
            self.assertEqual(other.project(project['id']), before)
            with patch.object(library, 'bindings', side_effect=OSError('synthetic read failure')):
                with self.assertRaisesRegex(OSError, 'synthetic read failure'):
                    library.run_current(self.store, project, run['id'])
            self.assertTrue(self.store.db.in_transaction)
            self.assertEqual(self.store.project(project['id'])['name'], 'uncommitted')
        finally:
            self.store.db.rollback()
        self.assertEqual(self.store.project(project['id']), before)
        with patch.object(library, 'bindings', side_effect=OSError('synthetic read failure')):
            with self.assertRaisesRegex(OSError, 'synthetic read failure'):
                library.run_current(self.store, project, run['id'])
        self.assertFalse(self.store.db.in_transaction)
        other.db.execute('BEGIN IMMEDIATE')
        other.db.rollback()


if __name__ == '__main__':
    unittest.main()
