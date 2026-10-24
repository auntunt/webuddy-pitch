"""Atomic fixed-A ledger boundaries; only temporary personal tenant fixtures."""
import concurrent.futures
import copy
import json
import threading
import unittest
from unittest.mock import patch

from tests.experiment_fixture import ExperimentFixture
from tmh.platform import learn, learning as L, learning_eval as E, learning_runs as R
from tmh.platform import learning_experiments as X, learning_experiment_runs as XR
from tmh.platform.errors import ApiError


class ExperimentLedgerTests(ExperimentFixture, unittest.TestCase):
    def denied(self, code, call):
        with self.assertRaises(ApiError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_four_table_migration_rolls_back_each_statement(self):
        for statement in X.DDL:
            with self.subTest(statement=statement):
                for table in reversed(X.TABLES):
                    self.store.x('DROP TABLE ' + table)
                before = self.snapshot()
                with self.fault(statement), self.assertRaises(OSError):
                    X.schema(self.store)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(X.schema_state(self.store), 'absent')
                X.schema(self.store)
                self.assertEqual(X.schema_state(self.store), 'ready')

    def test_partial_table_or_false_partial_index_fails_without_ddl(self):
        before = self.snapshot()
        with L.transaction(self.store) as db:
            db.execute('DROP INDEX ix_experiment_job')
            db.execute('CREATE UNIQUE INDEX ix_experiment_job ON learning_experiments(job_id) WHERE 0')
        damaged = self.snapshot()
        self.denied(409, lambda: X.schema_state(self.store))
        self.denied(409, lambda: X.schema(self.store))
        self.assertEqual(self.snapshot(), damaged)
        self.assertNotEqual(before, damaged)
        self.store.x('DROP TABLE learning_experiment_events')
        damaged = self.snapshot()
        self.denied(409, lambda: X.job_owner(self.store, 'unknown'))
        self.assertEqual(self.snapshot(), damaged)

    def test_draft_and_metadata_replay_reauthorize_and_keep_full_material(self):
        body, request = self.body(), 'same-create'
        first = self.draft(body, actor='alice', request_id=request)
        exp = self.exp(first['experiment_id'])
        assets = X.assets_in_tx(self.store.db, exp['id'])
        candidate = next(a['content'] for a in assets if a['kind'] == 'candidate')
        self.assertEqual(candidate['content'], self.revision['content'])
        self.assertEqual(json.loads(candidate['content'])['fix'], self.card['fix'])
        self.assertNotIn(self.card['fix'], json.dumps(first, ensure_ascii=False))
        before = self.snapshot()
        self.assertTrue(self.draft(body, actor='alice', request_id=request)['replayed'])
        self.assertEqual(self.snapshot(), before)
        self.denied(409, lambda: self.draft(self.body(timeout_seconds=121), actor='alice', request_id=request))
        self.change('project_revoke', user='alice', project_id=self.p['id'])
        self.denied(403, lambda: self.draft(body, actor='alice', request_id=request))

    def test_strict_contract_rejects_paid_arbitrary_and_lossy_inputs_without_writes(self):
        variants = [({'executor_id': 'paid-provider'}, 403), ({'task_set': 'client-oracle'}, 403),
            ({'command': 'echo unsafe'}, 400), ({'repeats': True}, 400), ({'max_calls': 7}, 400),
            ({'timeout_seconds': float('nan')}, 400), ({'timeout_seconds': float('inf')}, 400),
            ({'curator': '\ud800'}, 400), ({'curator': 'outsider'}, 403)]
        for fields, code in variants:
            with self.subTest(fields=repr(fields)):
                before = self.snapshot()
                self.denied(code, lambda: self.draft(self.body(**fields)))
                self.assertEqual(self.snapshot(), before)

    def test_real_manager_can_prepare_but_cannot_bypass_execution_gate(self):
        draft = self.draft(actor='alice')
        sealed = X.seal(self.P, self.p, draft['experiment_id'], draft['contract_hash'], 'alice', 'seal-alice')
        before = self.snapshot()
        self.denied(403, lambda: XR.start_sealed(self.P, self.p, sealed['experiment_id'], 'alice', 'start-alice', launch=False))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.store.q('SELECT * FROM runs'), [])

    def test_t1_one_job_all_repeats_atomic_and_idempotent(self):
        d = self.draft(self.body(repeats=2, max_calls=12))
        for sql in ('INSERT INTO learning_jobs', 'INSERT INTO learning_experiment_slots', 'INSERT INTO learning_experiment_events'):
            before = self.snapshot()
            with self.fault(sql), self.assertRaises(OSError):
                self.seal(d)
            self.assertEqual(self.snapshot(), before)
        result = X.seal(self.P, self.p, d['experiment_id'], d['contract_hash'], 'owner', 'seal-once')
        rows = self.slots(d['experiment_id'])
        self.assertEqual(len(rows), 12)
        self.assertEqual([r['ordinal'] for r in rows], list(range(1, 13)))
        self.assertEqual([r['repeat'] for r in rows], [1] * 6 + [2] * 6)
        self.assertEqual([r['arm'] for r in rows], ['baseline', 'candidate'] * 6)
        self.assertEqual({r['job_id'] for r in rows}, {result['job_id']})
        before = self.snapshot()
        self.assertTrue(X.seal(self.P, self.p, d['experiment_id'], d['contract_hash'], 'owner', 'seal-once')['replayed'])
        self.assertEqual(self.snapshot(), before)
        self.denied(409, lambda: X.cancel(self.P, self.p, d['experiment_id'], 'owner', 'seal-once'))

    def test_concurrent_seal_same_request_creates_one_plan(self):
        d = self.draft()
        gate = threading.Barrier(2)
        def call():
            gate.wait(timeout=5)
            return X.seal(self.P, self.p, d['experiment_id'], d['contract_hash'], 'owner', 'concurrent-seal')
        with concurrent.futures.ThreadPoolExecutor(2) as executor:
            outputs = list(executor.map(lambda _: call(), range(2)))
        self.assertEqual({o['job_id'] for o in outputs}, {outputs[0]['job_id']})
        self.assertEqual(sorted(o['replayed'] for o in outputs), [False, True])
        self.assertEqual(len(self.slots(d['experiment_id'])), 6)
        self.assertEqual(len(self.store.q('SELECT * FROM learning_jobs')), 1)

    def test_second_draft_cannot_seal_same_or_declared_descendant_candidate(self):
        child = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '先创建的后代改法'}), 'owner')
        d1, d2 = self.draft(), self.draft(self.body(candidate_revision_id=child['id']))
        self.seal(d1)
        X.cancel(self.P, self.p, d1['experiment_id'], 'owner', 'finish-first')
        self.denied(409, lambda: self.seal(d2))
        self.denied(409, lambda: self.draft())
        self.assertEqual(len(self.store.q('SELECT * FROM learning_jobs')), 1)

    def test_ancestry_blocks_new_adoption_and_proposal_without_changing_old_reads(self):
        child = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '封存前合法后代'}), 'owner')
        manual = 'manual-history'
        self.store.x("""INSERT INTO learning_jobs(id,project_id,kind,revision_id,current_revision_id,request_id,request_hash,actor,status,options,binding,created,deadline)
          VALUES(?,?,'evaluate',?,?,?,'hash','owner','passed','{}','{}','fixture',0)""",
          (manual, self.p['id'], child['id'], child['id'], manual))
        d = self.seal()
        before = self.store.one('SELECT * FROM learning_jobs WHERE id=?', (manual,))
        self.assertIsNone(X.job_owner(self.store, manual))
        self.assertEqual(X.managed_lookup(self.store, revision_id=child['id'])[0]['experiment_id'], d['experiment_id'])
        with L.transaction(self.store) as db:
            self.denied(409, lambda: X.assert_adoptable_in_tx(db, self.p['id'], child['id']))
        self.denied(409, lambda: L.propose(self.P, self.p, child['id'], L.encoded({'fix': '不允许逃逸'}), 'owner'))
        self.assertEqual(self.store.one('SELECT * FROM learning_jobs WHERE id=?', (manual,)), before)
        self.assertEqual(R.get(self.P, self.p, manual)['status'], 'passed')

    def test_ancestry_missing_cross_project_and_cycles_fail_closed(self):
        child = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '子修订'}), 'owner')
        self.seal()
        other = self.store.add_project('OTHER', '其他', str(self.root))
        for parent, project in ((child['id'], self.p['id']), ('missing', self.p['id']), (self.revision['id'], other['id'])):
            with self.subTest(parent=parent, project=project):
                self.store.x('UPDATE learning_revisions SET parent_id=?,project_id=? WHERE id=?', (parent, project, child['id']))
                before = self.snapshot()
                self.denied(409, lambda: X.managed_lookup(self.store, revision_id=child['id']))
                self.assertEqual(self.snapshot(), before)

    def _assert_damaged_candidate_stays_managed(self, damage):
        child = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '封存前合法后代'}), 'owner')
        draft = self.seal()
        damage(draft['experiment_id'])
        before = self.snapshot()
        for rid in (self.revision['id'], child['id']):
            self.denied(409, lambda: X.managed_lookup(self.store, revision_id=rid))
            with L.transaction(self.store) as db:
                self.denied(409, lambda: X.assert_unmanaged_revision_in_tx(db, self.p['id'], rid))
                self.denied(409, lambda: X.assert_adoptable_in_tx(db, self.p['id'], rid))
        self.assertEqual(self.snapshot(), before)

    def test_missing_candidate_asset_cannot_downgrade_sealed_revision_to_manual(self):
        self._assert_damaged_candidate_stays_managed(lambda eid: self.store.x(
            "DELETE FROM learning_experiment_assets WHERE experiment_id=? AND kind='candidate'", (eid,)))

    def test_changed_candidate_asset_key_cannot_downgrade_sealed_revision_to_manual(self):
        self._assert_damaged_candidate_stays_managed(lambda eid: self.store.x(
            "UPDATE learning_experiment_assets SET revision_id='another-id' WHERE experiment_id=? AND kind='candidate'", (eid,)))

    def test_rehashed_candidate_inner_revision_cannot_claim_another_revision(self):
        def damage(eid):
            candidate = next(a for a in X.assets_in_tx(self.store.db, eid) if a['kind'] == 'candidate')
            candidate['content']['revision_id'] = 'another-id'
            self.store.x("UPDATE learning_experiment_assets SET content=?,content_hash=? WHERE experiment_id=? AND id=?",
                         (X.encoded(candidate['content']), X.digest(candidate['content']), eid, candidate['id']))
        self._assert_damaged_candidate_stays_managed(damage)

    def test_unsealed_contract_and_unrelated_revision_keep_manual_ownership(self):
        draft = self.draft()
        self.assertEqual(X.managed_lookup(self.store, revision_id=self.revision['id']), [])
        child = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '未封存草稿仍可提出修订'}), 'owner')
        self.seal(self.draft(self.body(candidate_revision_id=child['id'])))
        before = self.snapshot()
        self.assertEqual(X.managed_lookup(self.store, revision_id=self.revision['id']), [])
        self.assertEqual(X.managed_lookup(self.store, revision_id=child['id'])[0]['revision_id'], child['id'])
        self.assertEqual(self.snapshot(), before)

    def test_manual_start_rechecks_ownership_after_seal_barrier(self):
        d = self.draft()
        entered, released = threading.Event(), threading.Event()
        original = E.validate_options
        def blocked(*args, **kwargs):
            value = original(*args, **kwargs)
            entered.set()
            self.assertTrue(released.wait(5))
            return value
        opts = dict(max_calls=6, timeout_seconds=120, cases=[dict(id=t['id'], input=t['input'], expected=t['expected'], validator='exact', generation=False) for t in X._TASKS])
        errors = []
        def manual():
            try:
                R.start(self.P, self.p, 'evaluate', self.revision['id'], opts, 'owner', 'manual-race', launch=False)
            except BaseException as exc:
                errors.append(exc)
        with patch.object(R, '_configuration', return_value={}), patch.object(E, 'validate_options', side_effect=blocked):
            thread = threading.Thread(target=manual)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                self.seal(d)
                X.cancel(self.P, self.p, d['experiment_id'], 'owner', 'cancel-race')
            finally:
                released.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ApiError)
        self.assertEqual(errors[0].code, 409)
        self.assertFalse(self.store.q("SELECT * FROM learning_jobs WHERE request_id='manual-race'"))

    def test_t2_registers_run_inputs_step_slot_budget_in_one_commit(self):
        worker = self.worker()
        for sql in ('INSERT INTO runs', 'INSERT INTO knowledge_run_inputs', 'INSERT INTO learning_steps', 'UPDATE learning_jobs SET calls', 'UPDATE learning_experiment_slots SET state', 'INSERT INTO learning_experiment_events'):
            with self.subTest(sql=sql):
                before = self.snapshot()
                with self.fault(sql), self.assertRaises(OSError):
                    self.next_material(worker)
                self.assertEqual(self.snapshot(), before)
        material = self.next_material(worker)
        rid = material['slot']['run_id']
        self.assertEqual(X.run_owner(self.store, rid)['experiment_id'], worker.eid)
        self.assertEqual(self.store.run(rid)['prompt'], material['prompt'])
        self.assertTrue(self.store.q('SELECT * FROM knowledge_run_inputs WHERE run_id=?', (rid,)))
        slots = self.slots(worker.eid)
        self.assertEqual(sum(s['reserved_calls'] for s in slots), 1)
        self.assertEqual(self.store.one('SELECT calls FROM learning_jobs WHERE id=?', (slots[0]['job_id'],))['calls'], 1)
        self.denied(409, lambda: self.next_material(worker))

    def test_cancel_between_t2_and_intent_ends_all_registered_records(self):
        worker = self.worker()
        material = self.next_material(worker)
        entered, released = threading.Event(), threading.Event()
        errors = []
        original = worker.intent
        def paused(m):
            entered.set()
            self.assertTrue(released.wait(5))
            return original(m)
        def invoke():
            try:
                worker.run_slot(material)
            except BaseException as exc:
                errors.append(exc)
        with patch.object(worker, 'intent', side_effect=paused), patch.object(worker.runner, 'run_command') as command:
            thread = threading.Thread(target=invoke)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                X.cancel(self.P, self.p, worker.eid, 'owner', 'between-reserve-and-intent')
            finally:
                released.set()
                thread.join(5)
            command.assert_not_called()
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.exp(worker.eid)['state'], 'cancelled')
        self.assertEqual({s['state'] for s in self.slots(worker.eid)}, {'not_executed'})
        self.assertEqual(sum(s['reserved_calls'] for s in self.slots(worker.eid)), 0)
        self.assertEqual(self.store.run(material['slot']['run_id'])['status'], 'failed')
        self.assertEqual(self.store.one('SELECT status FROM learning_steps WHERE run_id=?', (material['slot']['run_id'],))['status'], 'failed')
        self.assertEqual(self.store.q("SELECT * FROM runs WHERE status IN ('queued','running')"), [])
        self.assertEqual(self.store.q("SELECT * FROM learning_steps WHERE status IN ('reserved','running')"), [])
        self.assertEqual(self.exp(worker.eid)['report']['planned_slots'], 6)

    def test_cancel_after_intent_keeps_job_running_until_stopping_evidence(self):
        worker = self.worker()
        material = self.next_material(worker)
        worker.intent(material)
        X.cancel(self.P, self.p, worker.eid, 'owner', 'after-intent')
        self.assertEqual(self.exp(worker.eid)['state'], 'cancelling')
        self.assertEqual(self.store.one('SELECT status FROM learning_jobs WHERE id=?', (material['slot']['job_id'],))['status'], 'running')
        XR._safety_finalize(self.P, self.p, worker.eid, worker.token, worker.fence, 'cancelled')
        exp = self.exp(worker.eid)
        self.assertEqual(exp['state'], 'unknown')
        self.assertEqual(exp['report']['planned_slots'], 6)
        self.assertEqual(exp['report']['budget']['reserved_calls'], 1)
        self.assertEqual(self.slots(worker.eid)[0]['state'], 'unknown')
        self.assertEqual(json.loads(self.slots(worker.eid)[0]['result'])['cleanup_status'], 'not_proven')

    def test_deadline_anchor_cannot_be_extended_or_recreated(self):
        value = self.seal()
        exp = self.exp(value['experiment_id'])
        with self.store.lock:
            remaining = X.remaining_in_tx(self.store.db, exp)
        with patch.object(X.time, 'time', return_value=exp['deadline']-10000):
            self.assertLessEqual(X.remaining_in_tx(self.store.db, exp), remaining)
        with patch.object(X, 'PROCESS_EPOCH', 'new-process'):
            before = self.snapshot()
            self.denied(409, lambda: XR.start_sealed(self.P, self.p, exp['id'], 'owner', 'restart-start', launch=False))
            self.assertEqual(self.snapshot(), before)

    def test_participant_epoch_change_prevents_replay_and_dispatch(self):
        value = self.seal()
        self.change('password_reset', user='curator', password='new-synthetic-password')
        before = self.snapshot()
        self.denied(403, lambda: XR.start_sealed(self.P, self.p, value['experiment_id'], 'owner', 'start-new-epoch', launch=False))
        self.assertEqual(self.snapshot(), before)
        X.cancel(self.P, self.p, value['experiment_id'], 'owner', 'safe-stop')
        self.assertEqual(self.exp(value['experiment_id'])['state'], 'cancelled')

    def test_exposure_is_explicit_actor_epoch_bound_and_atomic(self):
        value = self.seal()
        exp = self.exp(value['experiment_id'])
        ids = list(exp['contract']['asset_commitments'])
        before = self.snapshot()
        with self.fault('INSERT INTO learning_experiment_events'), self.assertRaises(OSError):
            X.expose(self.P, self.p, exp['id'], ids, exp['contract_hash'], 'alice', 'expose')
        self.assertEqual(self.snapshot(), before)
        X.expose(self.P, self.p, exp['id'], ids, exp['contract_hash'], 'alice', 'expose')
        row = self.store.one("SELECT payload FROM learning_experiment_events WHERE experiment_id=? AND kind='expose'", (exp['id'],))
        payload = json.loads(row['payload'])
        self.assertEqual(payload['recipient'], 'alice')
        self.assertEqual(payload['account_epoch'], self.reg.one("SELECT epoch FROM accounts WHERE name='alice'")['epoch'])
        self.assertFalse(payload['rsi_qualified'])
        self.denied(403, lambda: X.expose(self.P, self.p, exp['id'], ids, exp['contract_hash'], 'optimizer', 'not-curator'))

    def test_receipts_echo_exact_action_and_request_identity(self):
        d = self.draft(request_id='ui-create')
        self.assertEqual((d['action'], d['request_id']), ('create', 'ui-create'))
        eid, digest = d['experiment_id'], d['contract_hash']
        s = X.seal(self.P, self.p, eid, digest, 'owner', 'ui-seal')
        self.assertEqual((s['action'], s['request_id']), ('seal', 'ui-seal'))
        start = XR.start_sealed(self.P, self.p, eid, 'owner', 'ui-start', launch=False)
        self.assertEqual((start['action'], start['request_id']), ('start', 'ui-start'))
        expose = X.expose(self.P, self.p, eid, list(self.exp(eid)['contract']['asset_commitments']), digest, 'owner', 'ui-expose')
        self.assertEqual((expose['action'], expose['request_id']), ('expose', 'ui-expose'))
        cancel = X.cancel(self.P, self.p, eid, 'owner', 'ui-cancel')
        self.assertEqual((cancel['action'], cancel['request_id']), ('cancel', 'ui-cancel'))
        replay = X.cancel(self.P, self.p, eid, 'owner', 'ui-cancel')
        self.assertTrue(replay['replayed'])
        self.assertEqual((replay['action'], replay['request_id']), ('cancel', 'ui-cancel'))

    def test_not_written_only_after_absent_request_and_proven_rollback(self):
        before = self.snapshot()
        exc = ApiError(409, 'synthetic validation failure')
        with self.assertRaises(ApiError) as caught:
            with X.mutation(self.store, create_key=('default', self.p['id'], 'owner', 'new-request')) as db:
                db.execute('UPDATE projects SET name=? WHERE id=?', ('must rollback', self.p['id']))
                raise exc
        self.assertIs(caught.exception, exc)
        self.assertEqual(exc.reason, 'experiment_not_written')
        self.assertFalse(self.store.db.in_transaction)
        self.assertEqual(self.snapshot(), before)
        draft = self.draft(request_id='prior-request')
        for body in (self.body(timeout_seconds=121), self.body()):
            if body['timeout_seconds'] == 120:
                self.change('project_revoke', user='curator', project_id=self.p['id'])
            with self.assertRaises(ApiError) as prior:
                self.draft(body, request_id='prior-request')
            self.assertNotEqual(getattr(prior.exception, 'reason', ''), 'experiment_not_written')
        self.assertEqual(self.exp(draft['experiment_id'])['state'], 'draft')

    def test_unknown_request_query_commit_and_rollback_errors_never_claim_not_written(self):
        original = self.store.db
        for mode in ('begin', 'query', 'commit_after_write', 'rollback'):
            with self.subTest(mode=mode):
                class Proxy:
                    def __getattr__(self, name):
                        return getattr(original, name)
                    def execute(self, sql, args=()):
                        if mode == 'begin' and sql == 'BEGIN IMMEDIATE':
                            raise ApiError(409, 'BEGIN unknown')
                        if mode == 'query' and sql.startswith('SELECT 1 FROM learning_experiments'):
                            raise ApiError(409, 'request lookup unknown')
                        return original.execute(sql, args)
                    def commit(self):
                        original.commit()
                        if mode == 'commit_after_write':
                            raise ApiError(409, 'commit completed but response lost')
                    def rollback(self):
                        original.rollback()
                        if mode == 'rollback':
                            raise ValueError('rollback outcome unavailable')
                self.store.db = Proxy()
                try:
                    with self.assertRaises((ApiError, ValueError)) as caught:
                        with X.mutation(self.store, create_key=('default', self.p['id'], 'owner', 'unknown-' + mode)) as db:
                            db.execute('UPDATE projects SET name=? WHERE id=?', ('write-' + mode, self.p['id']))
                            if mode == 'rollback':
                                raise ApiError(400, 'validation failure')
                    self.assertNotEqual(getattr(caught.exception, 'reason', ''), 'experiment_not_written')
                finally:
                    self.store.db = original
                    original.rollback()
                if mode == 'commit_after_write':
                    self.assertEqual(self.store.project(self.p['id'])['name'], 'write-' + mode)

    def test_authorization_exit_after_commit_keeps_unknown_not_rollback_classification(self):
        from contextlib import contextmanager
        from tmh.platform import tenant_policy as TP
        original = TP.experiment_guard
        @contextmanager
        def exit_failure(*args, **kwargs):
            with original(*args, **kwargs) as who:
                yield who
                raise ApiError(409, 'authorization guard exit unavailable')
        d = self.draft()
        with patch.object(TP, 'experiment_guard', exit_failure), self.assertRaises(ApiError) as caught:
            X.seal(self.P, self.p, d['experiment_id'], d['contract_hash'], 'owner', 'committed-then-exit')
        self.assertNotEqual(getattr(caught.exception, 'reason', ''), 'experiment_not_written')
        self.assertEqual(self.exp(d['experiment_id'])['state'], 'sealed')
        self.assertEqual(len(self.slots(d['experiment_id'])), 6)

    def test_experiment_material_uses_own_capture_not_a_fake_manual_job(self):
        d = self.draft()
        exp = self.exp(d['experiment_id'])
        with patch.object(E, 'current', side_effect=AssertionError('manual job capture is a separate contract')):
            frozen = X.material_current(self.P, self.p, exp)
            self.assertEqual(frozen['candidate_revision_id'], self.revision['id'])
            self.seal(d)
        # Recompute the mutable outer commitment: the independent creation
        # event must still reject it instead of accepting another self-hash.
        exp = self.exp(d['experiment_id'])
        forged = copy.deepcopy(exp['contract'])
        forged['renderer'] = dict(forged['renderer'], invented='not-captured')
        self.store.x('UPDATE learning_experiments SET contract=?,contract_hash=? WHERE id=?',
                     (X.encoded(forged), X.digest(forged), exp['id']))
        before = self.snapshot()
        self.denied(409, lambda: X.material_current(self.P, self.p, self.exp(exp['id'])))
        self.assertEqual(self.snapshot(), before)


    @staticmethod
    def _manual_options():
        return dict(max_calls=6, timeout_seconds=120, cases=[dict(id=t['id'], input=t['input'],
            expected=t['expected'], validator='exact', generation=False) for t in X._TASKS])

    def _manual_job(self, revision):
        with patch.object(R, '_configuration', return_value={}):
            return R.start(self.P, self.p, 'evaluate', revision['id'], self._manual_options(),
                           'owner', self.request('manual'), launch=False)

    def test_active_claimed_descendant_manual_blocks_parent_seal_until_terminal(self):
        child = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '封存前已存在的后代人工候选'}), 'owner')
        draft = self.draft()
        job = self._manual_job(child)
        entered, released = threading.Event(), threading.Event()
        failures = []
        def blocked(P, p, current, step):
            entered.set()
            self.assertTrue(released.wait(5))
            # No model/step is invoked: the real generic worker claim and final
            # state are what this concurrency test needs to exercise.
            return {'passed': False, 'reason': 'synthetic-manual-finished'}
        def invoke():
            try:
                R._work(self.P, self.p, job['id'])
            except BaseException as exc:
                failures.append(exc)
        with patch.object(R, '_configuration', return_value={}), patch.object(E, 'run', blocked):
            thread = threading.Thread(target=invoke)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                row = self.store.one('SELECT * FROM learning_jobs WHERE id=?', (job['id'],))
                self.assertEqual(row['status'], 'running')
                self.assertTrue(row['owner'])
                before = self.exp(draft['experiment_id'])
                self.denied(409, lambda: self.seal(draft))
                self.assertEqual(self.exp(draft['experiment_id']), before)
                self.assertEqual(self.slots(draft['experiment_id']), [])
                unchanged = self.store.one('SELECT * FROM learning_jobs WHERE id=?', (job['id'],))
                self.assertEqual((unchanged['status'], unchanged['owner'], unchanged['calls']),
                                 (row['status'], row['owner'], row['calls']))
            finally:
                released.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(self.store.one('SELECT status FROM learning_jobs WHERE id=?', (job['id'],))['status'], 'not_passed')
        terminal = R.get(self.P, self.p, job['id'])
        self.seal(draft)
        self.assertEqual(R.get(self.P, self.p, job['id']), terminal)

    def test_active_ancestor_manual_blocks_descendant_seal_without_mutating_job(self):
        child = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '祖先仍在人工运行的后代'}), 'owner')
        job = self._manual_job(self.revision)
        draft = self.draft(self.body(candidate_revision_id=child['id']))
        before = self.snapshot()
        self.denied(409, lambda: self.seal(draft))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.store.one('SELECT status FROM learning_jobs WHERE id=?', (job['id'],))['status'], 'queued')

    def test_active_sibling_and_unrelated_manual_do_not_block_seal(self):
        candidate = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '兄弟候选 A'}), 'owner')
        sibling = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '兄弟候选 B'}), 'owner')
        card = learn.add_lesson(self.data, {'project': 'APP', 'ticket': 'APP-2', 'status': 'candidate',
            'title': '无关来源', 'symptom': '独立检查', 'fix': '独立修复', 'verify': '独立验证',
            'applicability': '合成流程', 'non_applicability': '真实生产结论'})
        origin = L._origin(self.P, self.p, 'lesson:' + card['id'])
        other = L.capture(self.P, self.p, origin['key'], origin['fingerprint'], 'owner')
        jobs = [self._manual_job(sibling), self._manual_job(other)]
        draft = self.draft(self.body(candidate_revision_id=candidate['id']))
        before = [self.store.one('SELECT * FROM learning_jobs WHERE id=?', (job['id'],)) for job in jobs]
        self.seal(draft)
        self.assertEqual([self.store.one('SELECT * FROM learning_jobs WHERE id=?', (job['id'],)) for job in jobs], before)
        self.assertEqual(len(self.slots(draft['experiment_id'])), 6)

    def test_descendant_manual_registration_loses_to_parent_seal_commit(self):
        child = L.propose(self.P, self.p, self.revision['id'], L.encoded({'fix': '提交前被封存的后代候选'}), 'owner')
        draft = self.draft()
        entered, released = threading.Event(), threading.Event()
        errors = []
        original = E.validate_options
        def blocked(*args, **kwargs):
            value = original(*args, **kwargs)
            entered.set()
            self.assertTrue(released.wait(5))
            return value
        def manual():
            try:
                self._manual_job(child)
            except BaseException as exc:
                errors.append(exc)
        with patch.object(E, 'validate_options', side_effect=blocked):
            thread = threading.Thread(target=manual)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                self.seal(draft)
            finally:
                released.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ApiError)
        self.assertEqual(errors[0].code, 409)
        self.assertEqual(len(self.store.q('SELECT * FROM learning_jobs')), 1)
        self.assertEqual(self.exp(draft['experiment_id'])['state'], 'sealed')
