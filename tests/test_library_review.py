"""Cross-connection review of fixed knowledge authorization and run evidence.

All Git repositories, SQLite connections and supervised builders are real and
temporary. Model invocation or thread dispatch is intercepted at the last seam.
No clocks or production timeouts are changed; competing writes use zero-wait SQLite probes so their
ordering is explicit instead of depending on a sleep.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_library_integration as integration_fixtures
from tests import test_project_library as fixtures
from tmh.platform import agents, handwork, intake, learn, login, project_library as library, supervised_process
from tmh.platform.errors import ApiError
from tmh.platform.store import Store


@unittest.skipUnless(os.name == 'posix' and shutil.which('git'), 'requires POSIX supervision and local Git')
class LibraryReviewTest(unittest.TestCase):
    setUp = fixtures.ProjectLibraryTest.setUp
    tearDown = fixtures.ProjectLibraryTest.tearDown
    git = fixtures.ProjectLibraryTest.git
    project = fixtures.ProjectLibraryTest.project
    commit = fixtures.ProjectLibraryTest.commit
    snapshot = fixtures.ProjectLibraryTest.snapshot
    start = fixtures.ProjectLibraryTest.start
    wait_terminal = fixtures.ProjectLibraryTest.wait_terminal
    build = fixtures.ProjectLibraryTest.build

    def runner(self):
        (self.store.path.parent / 'agents.json').write_text(json.dumps({'synthetic': {
            'cmd': [sys.executable, '-c', "raise AssertionError('must not invoke a model')"]}}))
        runner = agents.Runner(self.store, self.store.path.parent)
        self.addCleanup(lambda: [runner._release(rid) for rid in list(runner.owners)])
        return runner

    def pair(self):
        source = self.project('STD', {'public/rules.txt': 'Approval public rules',
                                      'private/rules.txt': 'Approval private rules'})
        customer = self.project('CLIENT')
        revision = self.build(source)
        library.grant(self.store, source, customer['key'], [], 'fixture operator')
        reference = library.reference(self.store, customer, revision['id'], ['public'], 'public rules', 'fixture operator')
        return source, customer, revision, reference

    def legacy_inputs(self):
        # The exact five-column shape shipped in 2c1cd53, with all evidence
        # preserved. Only this temporary fixture database is downgraded.
        self.store.db.executescript("""
            CREATE TABLE legacy_inputs (
                run_id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
                bindings TEXT NOT NULL, digest TEXT NOT NULL, created TEXT NOT NULL);
            INSERT INTO legacy_inputs
                SELECT run_id,project_id,bindings,digest,created FROM knowledge_run_inputs;
            DROP TABLE knowledge_run_inputs;
            ALTER TABLE legacy_inputs RENAME TO knowledge_run_inputs;
        """)

    def test_independent_connections_can_migrate_the_same_legacy_database(self):
        project = self.project('CLIENT')
        run = self.store.create_run(project['id'], None, 'synthetic', 'ask', 'fixture', 'old prompt')
        self.legacy_inputs()
        original = self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (run['id'],))
        barrier, mutex = threading.Barrier(2), threading.Lock()
        seen, opened, errors = set(), [], []
        query = Store.q

        def synchronized_read(store, sql, args=()):
            result = query(store, sql, args)
            if sql == 'PRAGMA table_info(knowledge_run_inputs)':
                with mutex:
                    first = id(store) not in seen
                    if first:
                        seen.add(id(store))
                        opened.append(store)  # close even an incompletely initialized Store
                if first:
                    self.assertNotIn('project_root', {r['name'] for r in result})
                    barrier.wait(timeout=3)  # both genuinely observed the old schema
            return result

        def open_store():
            try:
                Store(self.store.path)
            except Exception as exc:
                errors.append(repr(exc))

        workers = [threading.Thread(target=open_store) for _ in range(2)]
        try:
            with patch.object(Store, 'q', synchronized_read):
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join(10)
            self.assertFalse(any(worker.is_alive() for worker in workers))
            self.assertEqual(errors, [], 'parallel schema upgrades must recheck under the writer lock')
            self.assertEqual(len(opened), 2)
            self.assertEqual(self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (run['id'],)),
                             dict(original, project_root=''))
            self.assertTrue(library.run_current(self.store, project, run['id']))
            self.assertTrue(all(not store.db.in_transaction for store in opened))
        finally:
            for store in opened:
                store.db.close()

    def test_legacy_evidence_keeps_unknown_workspace_identity_after_maintain(self):
        project = self.project('STD')
        revision = self.build(project)
        run = self.store.create_run(project['id'], None, 'synthetic', 'plan', 'fixture', 'legacy plan')
        self.store.update_run(run['id'], status='done', exit_code=0)
        self.legacy_inputs()
        old = self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (run['id'],))
        library.schema(self.store)
        self.assertTrue(library.run_current(self.store, project, run['id']))
        library.configure(self.store, project, ['reference'], 'reference')
        maintained = library.derive(self.store, project, revision['id'], '', '', 'fixture operator', maintain=True)['project']
        self.assertFalse(library.run_current(self.store, maintained, run['id']))
        with self.assertRaisesRegex(ValueError, '不能改写原始证据'):
            library.bind_run(self.store, maintained, run['id'], [])
        self.assertEqual(self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (run['id'],)),
                         dict(old, project_root=''))
        new = self.store.create_run(maintained['id'], None, 'synthetic', 'plan', 'fixture', 'new plan')
        self.assertTrue(library.run_current(self.store, maintained, new['id']))

    def test_fixed_run_inputs_cannot_be_replaced_with_a_new_reference(self):
        _, customer, revision, _ = self.pair()
        run = self.store.create_run(customer['id'], None, 'synthetic', 'ask', 'fixture', 'old prompt')
        values = library.bindings(self.store, customer)
        original = self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (run['id'],))
        library.bind_run(self.store, customer, run['id'], values)  # identical replay is harmless
        library.reference(self.store, customer, revision['id'], ['private'], 'new scope', 'fixture operator')
        self.assertFalse(library.run_current(self.store, customer, run['id']))
        with self.assertRaisesRegex(ValueError, '不能改写原始证据'):
            library.bind_run(self.store, customer, run['id'], library.bindings(self.store, customer))
        self.assertEqual(self.store.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (run['id'],)), original)
        self.assertFalse(self.store.db.in_transaction)

    def test_input_insert_failure_rolls_back_run_and_retry_link(self):
        project = self.project('CLIENT')
        runner = self.runner()
        old = self.store.create_run(project['id'], None, 'synthetic', 'ask', 'fixture', 'original prompt')
        self.store.update_run(old['id'], status='failed', exit_code=1)
        previous = self.store.runs(project_id=project['id'])
        self.store.x("CREATE TRIGGER reject_library_input BEFORE INSERT ON knowledge_run_inputs "
                     "BEGIN SELECT RAISE(ABORT, 'synthetic input persistence failure'); END")
        with patch.object(agents.threading, 'Thread') as launch:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'synthetic input persistence failure'):
                runner.start(project, None, 'synthetic', 'ask', 'fixture', question='Approval', retry_of=old['id'])
            launch.assert_not_called()
        self.assertEqual(self.store.runs(project_id=project['id']), previous,
                         'input failure must not leave a queued successor with no owner')
        self.assertEqual(self.store.q('SELECT id FROM runs WHERE retry_of=?', (old['id'],)), [])
        self.assertEqual(runner.owners, {})
        self.assertFalse(self.store.db.in_transaction)
        self.store.x('DROP TRIGGER reject_library_input')
        with patch.object(agents.threading, 'Thread'):
            new = runner.start(project, None, 'synthetic', 'ask', 'fixture', question='Approval', retry_of=old['id'])
        self.assertEqual(self.store.one('SELECT run_id FROM knowledge_run_inputs WHERE run_id=?', (new['id'],)),
                         {'run_id': new['id']})

    def test_an_independent_reader_never_sees_run_without_its_input_binding(self):
        _, customer, _, _ = self.pair()
        runner = self.runner()
        other = Store(self.store.path)
        real_run = self.store.run
        observations = []

        def observe(rid):
            run = real_run(rid)
            visible = other.run(rid)
            if visible:
                observations.append((visible['id'], other.one('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (rid,))))
            return run

        try:
            with patch.object(self.store, 'run', side_effect=observe), patch.object(agents.threading, 'Thread'):
                result = runner.start(customer, None, 'synthetic', 'ask', 'fixture', question='Approval')
            self.assertTrue(observations)
            for rid, binding in observations:
                self.assertIsNotNone(binding, 'committed run was visible before its fixed inputs: %s' % rid)
                self.assertEqual(json.loads(binding['bindings']), library.bindings(other, customer))
                self.assertEqual(binding['run_id'], result['id'])
        finally:
            other.db.close()

    def test_changed_reference_at_registration_rejects_before_any_run_is_committed(self):
        _, customer, _, reference = self.pair()
        runner = self.runner()
        other = Store(self.store.path)
        create = self.store.create_run

        def change_then_register(*args, **kwargs):
            library.unlink(other, customer, reference['id'])
            return create(*args, **kwargs)

        try:
            with patch.object(self.store, 'create_run', side_effect=change_then_register), \
                    patch.object(agents.threading, 'Thread') as launch:
                with self.assertRaisesRegex(ValueError, '参考知识.*变化'):
                    runner.start(customer, None, 'synthetic', 'ask', 'fixture', question='Approval')
                launch.assert_not_called()
            self.assertEqual(self.store.runs(project_id=customer['id']), [])
            self.assertEqual(self.store.q('SELECT * FROM knowledge_run_inputs'), [])
            self.assertFalse(self.store.db.in_transaction)
        finally:
            other.db.close()

    def evaluation(self, project, change):
        runner = self.runner()
        platform = SimpleNamespace(store=self.store, data_dir=self.store.path.parent,
                                   root=lambda p: Path(p['root']), runner=runner)
        build = learn.build_prompt
        prompts = []

        def prepare_then_change(*args, **kwargs):
            prompt = build(*args, **kwargs)
            prompts.append(prompt)
            change()
            return prompt

        case = {'id': 'fixture-case', 'title': 'Approval evaluation', 'body': 'Approval behavior', 'gold': []}
        with patch.object(learn, 'build_prompt', side_effect=prepare_then_change), \
                patch.object(runner, 'invoke', return_value=(0, 'synthetic result')) as invoke:
            with self.assertRaisesRegex(ValueError, '参考知识.*变化|工作区已变化'):
                learn._run_case(platform, project, case, 'synthetic', '', {}, 'fixture', 'fixture-batch')
            invoke.assert_not_called()
        self.assertEqual(len(prompts), 1)
        self.assertEqual(self.store.runs(project_id=project['id']), [])
        self.assertEqual(self.store.q('SELECT * FROM knowledge_run_inputs'), [])

    def test_evaluation_cannot_label_an_old_prompt_with_new_references(self):
        _, customer, revision, _ = self.pair()
        self.evaluation(customer, lambda: library.reference(
            self.store, customer, revision['id'], ['private'], 'changed during evaluation prompt', 'fixture operator'))

    def test_evaluation_rejects_a_workspace_replaced_after_prompt_preparation(self):
        project = self.project('STD')
        revision = self.build(project)

        def maintain():
            library.configure(self.store, project, ['reference'], 'reference')
            library.derive(self.store, project, revision['id'], '', '', 'fixture operator', maintain=True)

        self.evaluation(project, maintain)

    def test_intake_rejects_business_map_from_a_replaced_workspace(self):
        project = self.project('STD')
        revision = self.build(project)
        runner = self.runner()
        data = self.store.path.parent
        (data / 'autoflow.json').write_text('{"on":false,"understand":"rules"}')
        platform = SimpleNamespace(store=self.store, data_dir=data, runner=runner,
                                   root=lambda p: Path(p['root']), project=self.store.project)
        state = intake.start(platform, project, '保存记录后提示错误，希望保存后看到原事项。', 'fixture', agent=False)
        state['state'] = 'understanding'
        state['understanding_job'] = {'id': 'fixture-job', 't0': time.time(), 'agent': 'synthetic'}
        intake._save(data, state)
        prompt = intake.prompt
        prepared = []

        def prepare_then_maintain(*args):
            text = prompt(*args)
            prepared.append(text)
            library.configure(self.store, project, ['reference'], 'reference')
            library.derive(self.store, project, revision['id'], '', '', 'fixture operator', maintain=True)
            return text

        with patch.object(intake, 'prompt', side_effect=prepare_then_maintain), \
                patch.object(runner, 'invoke', return_value=(1, 'synthetic unexpected invocation')) as invoke:
            intake._understand(platform, project, state['id'], 'fixture-job', 'synthetic')
            invoke.assert_not_called()
        self.assertEqual(len(prepared), 1)
        self.assertEqual(self.store.runs(project_id=project['id']), [])
        self.assertNotEqual(self.store.project(project['id'])['root'], project['root'])

    def test_handwritten_commit_cannot_be_registered_in_a_replacement_workspace(self):
        project = self.project('STD')
        revision = self.build(project)
        main = self.git(project['root'], 'branch', '--show-current')
        self.git(project['root'], 'checkout', '-b', 'fixture-change')
        (Path(project['root']) / 'modules/approval.py').write_text("def Approval():\n    return 'human change'\n")
        sha = self.commit(project)
        self.git(project['root'], 'checkout', main)
        ticket = self.store.create_ticket(project['id'], 'Approval change', 'fixture')
        ticket = self.store.update_ticket(ticket['id'], 'fixture', status='doing', links={'hold': 'fixture'})
        platform = SimpleNamespace(store=self.store, data_dir=self.store.path.parent)
        create = self.store.create_run

        def maintain_then_register(*args, **kwargs):
            library.configure(self.store, project, ['reference'], 'reference')
            library.derive(self.store, project, revision['id'], '', '', 'fixture operator', maintain=True)
            return create(*args, **kwargs)

        try:
            with patch.object(self.store, 'create_run', side_effect=maintain_then_register), \
                    patch.object(handwork.threading, 'Thread') as launch:
                with self.assertRaisesRegex(ValueError, '工作区已变化'):
                    handwork.take(platform, project, ticket, 'fixture-change', sha, 'fixture')
                launch.assert_not_called()
            self.assertEqual(self.store.runs(project_id=project['id']), [])
            self.assertFalse(handwork.busy(ticket['key']))
            self.assertEqual(self.store.ticket(ticket['id'])['status'], 'doing')
        finally:
            handwork._BUSY.discard(ticket['key'])

    def test_maintain_cannot_reuse_plans_from_the_original_workspace(self):
        source = self.project('STD')
        revision = self.build(source)
        before = self.snapshot(source)
        ticket = self.store.create_ticket(source['id'], 'Approval plan', 'fixture')
        plan = self.store.create_run(source['id'], ticket['id'], 'synthetic', 'plan', 'fixture', 'old workspace prompt')
        library.bind_run(self.store, source, plan['id'], [])
        self.store.update_run(plan['id'], status='done', exit_code=0, result='old workspace conclusion')
        ticket = self.store.update_ticket(ticket['id'], 'fixture', links={'delivery_plan_run': plan['id']})
        self.assertEqual(agents.reviewed_delivery_plan(self.store, ticket)['id'], plan['id'])
        library.configure(self.store, source, ['reference'], 'reference')
        result = library.derive(self.store, source, revision['id'], '', '', 'fixture operator', maintain=True)
        project = result['project']
        self.assertEqual(project['id'], source['id'])
        self.assertNotEqual(project['root'], source['root'])
        self.assertFalse(library.run_current(self.store, project, plan['id']),
                         'matching empty references cannot validate another workspace')
        with self.assertRaisesRegex(ValueError, '工作区|知识版本'):
            agents.reviewed_delivery_plan(self.store, ticket)
        self.assertEqual(self.store.run(plan['id'])['result'], 'old workspace conclusion')
        self.assertEqual(self.snapshot(source), before)
        fresh = self.store.create_run(project['id'], None, 'synthetic', 'plan', 'fixture', 'new workspace prompt')
        self.assertTrue(library.run_current(self.store, project, fresh['id']))

    def test_grant_merge_cannot_resurrect_scope_revoked_by_another_connection(self):
        source, customer, revision, _ = self.pair()
        library.grant(self.store, source, customer['key'], ['private'], 'fixture operator')
        other = Store(self.store.path)
        other.db.execute('PRAGMA busy_timeout=0')
        original = self.store.one
        attempts = []

        def revoke():
            other.x('DELETE FROM knowledge_grants WHERE source_project=? AND target_project=?', (source['id'], customer['id']))

        def observe(sql, args=()):
            value = original(sql, args)
            if sql.startswith('SELECT scopes FROM knowledge_grants') and not attempts:
                try:
                    revoke()
                except sqlite3.OperationalError as exc:
                    self.assertEqual(exc.sqlite_errorcode, sqlite3.SQLITE_BUSY)
                    attempts.append('serialized')
                else:
                    attempts.append('revoked_before_merge')
            return value

        try:
            with patch.object(self.store, 'one', side_effect=observe):
                library.act(SimpleNamespace(store=self.store), customer, {
                    'action': 'reference', 'revision_id': revision['id'], 'scopes': ['public'],
                    'purpose': 'operator permits public only', 'grant': True}, 'fixture operator')
            self.assertEqual(len(attempts), 1)
            if attempts == ['serialized']:
                revoke()  # waiting revocation runs after the merge transaction
            self.assertFalse(library._allowed(self.store, source['id'], customer['id'], ['private']),
                             'a concurrent revocation was overwritten by stale grant scopes: ' + repr(attempts))
            self.assertFalse(library.reference_state(self.store, customer)[0]['available'])
            with self.assertRaises(ApiError) as denied:
                library.read(self.store, customer, revision['id'], 'public/rules.txt')
            self.assertEqual(denied.exception.code, 403)
            self.assertFalse(self.store.db.in_transaction)
            self.assertFalse(other.db.in_transaction)
        finally:
            other.db.close()

    def test_cancel_from_another_connection_cannot_be_acknowledged_then_published(self):
        source = self.project('STD')
        other = Store(self.store.path)
        other.db.execute('PRAGMA busy_timeout=0')
        original_row, supervised = library._row, supervised_process.run_supervised
        completed, attempts = [], []

        def supervise(*args, **kwargs):
            result = supervised(*args, **kwargs)
            completed.append(result)
            return result

        class PublicationRow(dict):
            def __getitem__(row, key):
                value = super().__getitem__(key)
                if key == 'cancel_requested' and completed and not attempts:
                    attempts.append('trying')
                    try:
                        response = library.cancel(other, source, row['id'])
                    except sqlite3.OperationalError as exc:
                        self.assertEqual(exc.sqlite_errorcode, sqlite3.SQLITE_BUSY)
                        attempts[:] = ['serialized']
                    else:
                        attempts[:] = ['acknowledged', response['status']]
                return value

        def row(store, rid):
            value = original_row(store, rid)
            return PublicationRow(value) if store is self.store else value

        try:
            with patch.object(library, '_row', side_effect=row), \
                    patch.object(supervised_process, 'run_supervised', side_effect=supervise):
                revision = self.start(source)
                final = self.wait_terminal(source, revision['id'])
            self.assertEqual(len(completed), 1)
            self.assertTrue(completed[0].cleanup['complete'])
            self.assertTrue(attempts)
            if attempts[0] == 'acknowledged':
                self.assertEqual(attempts[1], 'building')
                self.assertEqual(final['status'], 'cancelled', 'acknowledged pre-publication cancel lost')
            else:
                self.assertEqual(attempts, ['serialized'])
                self.assertEqual(final['status'], 'ready')
                self.assertEqual(library.cancel(other, source, revision['id'])['status'], 'ready')
        finally:
            other.db.close()


@unittest.skipUnless(os.name == 'posix' and shutil.which('git'), 'requires POSIX supervision and local Git')
class LibraryAuthorityReviewTest(unittest.TestCase):
    setUp = fixtures.ProjectLibraryTest.setUp
    tearDown = integration_fixtures.LibraryIntegrationTest.tearDown
    git = fixtures.ProjectLibraryTest.git
    project = fixtures.ProjectLibraryTest.project
    start = fixtures.ProjectLibraryTest.start
    wait_terminal = fixtures.ProjectLibraryTest.wait_terminal
    build = fixtures.ProjectLibraryTest.build
    start_http = integration_fixtures.LibraryIntegrationTest.start_http
    http = integration_fixtures.LibraryIntegrationTest.http

    def test_agent_requests_cannot_use_human_credentials_for_library_management(self):
        self.start_http()
        source, customer = self.project('STD'), self.project('CLIENT')
        revision = self.build(source)
        login.set_user(self.store.path.parent, 'fixture-human', 'temporary-test-password')
        session = login.make_session(self.store.path.parent, 'fixture-human')
        actions = [
            ('STD', {'action': 'configure', 'roles': ['product'], 'workflow': 'development'}),
            ('STD', {'action': 'add_source', 'root': customer['root']}),
            ('STD', {'action': 'grant', 'project': 'CLIENT', 'scopes': []}),
            ('STD', {'action': 'revoke', 'project': 'CLIENT'}),
            ('CLIENT', {'action': 'reference', 'revision_id': revision['id'], 'scopes': [],
                        'purpose': 'reference', 'grant': True}),
            ('STD', {'action': 'derive', 'revision_id': revision['id'], 'key': 'BAD'}),
            ('STD', {'action': 'maintain', 'revision_id': revision['id']}),
        ]
        for credential in ({'operator': True}, {'session': session}):
            for project, action in actions:
                with self.subTest(credential=next(iter(credential)), action=action['action']):
                    status, result = self.http('POST', '/api/projects/' + project + '/library', action,
                                               agent='synthetic', **credential)
                    self.assertEqual(status, 403, result)
                    self.assertIn('操作者发起', result['error'])
        self.assertEqual(library.profile(self.store, source), {'roles': [], 'workflow': 'development'})
        self.assertEqual(len(library.view(self.store, source)['sources']), 1)
        for table in ('knowledge_grants', 'knowledge_references', 'project_workspaces', 'project_derivations'):
            self.assertEqual(self.store.q('SELECT * FROM ' + table), [])
        self.assertIsNone(self.store.project('BAD'))
        # The same valid signed session can authorize an actual human request.
        status, result = self.http('POST', '/api/projects/STD/library',
                                   {'action': 'grant', 'project': 'CLIENT', 'scopes': ['modules']}, session=session)
        self.assertEqual(status, 200, result)
        self.assertTrue(library._allowed(self.store, source['id'], customer['id'], ['modules']))
        self.assertFalse(library._allowed(self.store, source['id'], customer['id'], []))


if __name__ == '__main__':
    unittest.main()
