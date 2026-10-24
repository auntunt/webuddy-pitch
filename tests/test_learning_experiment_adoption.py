"""Synthetic experiments cannot launder manual approvals; old durable receipts survive."""
from contextlib import contextmanager
import sqlite3
import unittest
from unittest.mock import patch

from tests import test_learning_decisions as fixtures
from tmh.platform import login, learn, learning as L, learning_decisions as D
from tmh.platform import learning_experiments as X, learning_runs as R
from tmh.platform.tenancy import Registry
from tmh.platform.tenant_runtime import TenantContext
from tmh.platform.errors import ApiError


class ManagedAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.LearningDecisionsTests('runTest')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        f = self.f
        password = login.hash_password('synthetic-adoption-password')
        login._save_users(f.data, {name: {'pw': password} for name in ('owner', 'curator', 'optimizer', 'selector')})
        self.registry = Registry(f.data, bootstrap_owner='owner')
        self.addCleanup(self.registry.close)
        context = TenantContext(self.registry, 'default')
        context.platform = f.P
        f.P.tenant_context = context
        for name in ('curator', 'optimizer', 'selector'):
            self.registry.dispatch('owner', dict(action='project_grant', tenant='default', user=name,
                project_id=f.p['id'], role='viewer', request_id='grant-' + name,
                revision=self.registry.context('owner')['revision']))

    def managed(self, revision=None):
        f = self.f
        body = dict(candidate_revision_id=(revision or f.r)['id'], repeats=1, max_calls=6, timeout_seconds=120,
                    curator='curator', optimizer='optimizer', selector='selector',
                    executor_id=X.EXECUTOR_ID, task_set=X.TASK_SET)
        draft = X.create_draft(f.P, f.p, body, 'owner', 'synthetic-draft')
        return X.seal(f.P, f.p, draft['experiment_id'], draft['contract_hash'], 'owner', 'synthetic-seal')

    def test_old_manual_passed_job_remains_readable_but_cannot_authorize_new_adoption(self):
        f = self.f
        job = f.passed()
        before = R.get(f.P, f.p, job['id'])
        self.managed()
        self.assertEqual(R.get(f.P, f.p, job['id']), before)
        with self.assertRaises(ApiError) as error:
            f.decide(job, actor='owner')
        self.assertEqual(error.exception.code, 409)
        self.assertEqual(f.store.q('SELECT * FROM learning_decisions'), [])
        self.assertIsNone(learn.active_revision(f.data, f.card['id']))

    def test_existing_pending_intent_without_file_receipt_cannot_project_after_seal(self):
        f = self.f
        pending = f.pending(f.passed(), actor='owner')
        self.managed()
        before = learn._log(f.data)
        with self.assertRaises(ApiError) as error:
            D.project_decision(f.P, f.p, pending['id'])
        self.assertEqual(error.exception.code, 409)
        self.assertEqual(learn._log(f.data), before)
        self.assertIsNone(learn.projection_receipt(f.data, pending['id']))
        self.assertEqual(f.store.one('SELECT status FROM learning_decisions WHERE id=?', (pending['id'],))['status'], 'conflict')

    def test_durable_preexisting_file_receipt_bypasses_only_the_new_adoption_gate(self):
        f = self.f
        job = f.passed()
        real = L.transaction
        calls = 0
        @contextmanager
        def fail_ack(store):
            nonlocal calls
            calls += 1
            call = calls
            with real(store) as db:
                yield db
                if call == 2:
                    raise sqlite3.OperationalError('synthetic after-file before-ack')
        with patch.object(L, 'transaction', side_effect=fail_ack):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'after-file'):
                f.decide(job, actor='owner')
        pending = f.store.one('SELECT * FROM learning_decisions')
        self.assertEqual(pending['status'], 'pending')
        receipt = learn.projection_receipt(f.data, pending['id'])
        self.assertIsNotNone(receipt)
        # Recovery must acknowledge the original durable receipt even if a
        # later adoption gate would reject a new decision for this revision.
        before = learn._log(f.data)
        with patch.object(X, 'assert_adoptable_in_tx', side_effect=AssertionError('must not re-adopt durable file receipt')):
            result = D.project_decision(f.P, f.p, pending['id'])
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(learn._log(f.data), before)
        self.assertEqual(learn.projection_receipt(f.data, pending['id']), receipt)

    def test_unmanaged_manual_adoption_still_uses_original_evidence_and_human(self):
        f = self.f
        job = f.passed()
        result = f.decide(job, actor='owner')
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(result['actor'], 'owner')
        self.assertEqual(learn.active_revision(f.data, f.card['id']), f.r['id'])
