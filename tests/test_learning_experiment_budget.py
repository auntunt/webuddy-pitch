"""New budgets use both directions of declared lineage; history ownership does not."""
import concurrent.futures
import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from tests.experiment_fixture import ExperimentFixture
from tmh.platform import learning as L, learning_eval as E, learning_runs as R
from tmh.platform import learning_experiments as X
from tmh.platform.errors import ApiError


_SEAL_CHILD = r'''
import json,socket,sys
from pathlib import Path
from types import SimpleNamespace
from tmh.platform import learning_experiments as X
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tmh.platform.tenancy import Registry
from tmh.platform.tenant_runtime import TenantContext
data=Path(sys.argv[1]);reg=Registry(data);store=Store(data/'platform.db')
context=TenantContext(reg,'default');P=SimpleNamespace(store=store,data_dir=data,tenant_context=context)
context.platform=P;p=store.project('APP');barrier=socket.socket(fileno=int(sys.argv[4]))
try:
    barrier.sendall(b'R')
    if barrier.recv(1)!=b'S':raise RuntimeError('missing release')
    try:
        result={'receipt':X.seal(P,p,sys.argv[2],sys.argv[3],'owner','independent-seal')}
    except ApiError as error:
        result={'code':error.code,'reason':getattr(error,'reason',None)}
    print(json.dumps(result),flush=True)
finally:
    barrier.close();store.db.close();reg.close()
'''


class ExperimentBudgetLineageTests(ExperimentFixture, unittest.TestCase):
    def child(self, parent=None, text='child'):
        return L.propose(self.P, self.p, (parent or self.revision)['id'], L.encoded({'fix': text}), 'owner')

    def reject(self, call):
        before = self.snapshot()
        with self.assertRaises(ApiError) as error:
            call()
        self.assertEqual(error.exception.code, 409)
        self.assertEqual(self.snapshot(), before)

    def options(self):
        return dict(max_calls=6, timeout_seconds=120, cases=[dict(id=t['id'], input=t['input'],
            expected=t['expected'], validator='exact', generation=False) for t in X._TASKS])

    def test_sealed_child_blocks_new_parent_budget_without_reclassifying_history(self):
        child = self.child()
        sealed = self.seal(self.draft(self.body(candidate_revision_id=child['id'])))
        self.reject(lambda: self.draft())
        self.assertEqual(X.managed_lookup(self.store, revision_id=self.revision['id']), [])
        self.assertEqual(len(self.store.q('SELECT * FROM learning_jobs')), 1)
        self.assertEqual(len(self.slots(sealed['experiment_id'])), 6)

    def test_preexisting_parent_draft_cannot_seal_after_descendant(self):
        child = self.child(); grandchild = self.child(child, 'grandchild')
        old = self.draft(request_id='parent-before-seal')
        self.seal(self.draft(self.body(candidate_revision_id=grandchild['id'])))
        self.reject(lambda: self.seal(old))
        replay = self.draft(request_id='parent-before-seal')
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['experiment_id'], old['experiment_id'])
        self.assertEqual(replay['state'], 'draft')

    def test_reverse_lineage_blocks_new_manual_budget_before_configuration(self):
        child = self.child()
        self.seal(self.draft(self.body(candidate_revision_id=child['id'])))
        with patch.object(R, '_configuration', return_value={}) as config, patch.object(R, '_launch') as launch:
            self.reject(lambda: R.start(self.P, self.p, 'evaluate', self.revision['id'], self.options(),
                                        'owner', 'manual-new', launch=False))
        config.assert_not_called(); launch.assert_not_called()

    def test_siblings_and_legacy_terminal_manual_receipts_keep_original_contract(self):
        child = self.child()
        with patch.object(R, '_configuration', return_value={}):
            old = R.start(self.P, self.p, 'evaluate', self.revision['id'], self.options(),
                          'owner', 'old-manual', launch=False)
        self.store.x("UPDATE learning_jobs SET status='not_passed' WHERE id=?", (old['id'],))
        self.seal(self.draft(self.body(candidate_revision_id=child['id'])))
        before = self.store.one('SELECT * FROM learning_jobs WHERE id=?', (old['id'],))
        with patch.object(R, '_launch') as launch:
            replay = R.start(self.P, self.p, 'evaluate', self.revision['id'], self.options(), 'owner', 'old-manual')
        launch.assert_not_called()
        self.assertEqual(replay['id'], old['id'])
        self.assertEqual(self.store.one('SELECT * FROM learning_jobs WHERE id=?', (old['id'],)), before)
        self.assertIsNone(X.job_owner(self.store, old['id']))
        sibling = self.child(text='sibling after sealed child')
        self.assertEqual(X.managed_lookup(self.store, revision_id=sibling['id']), [])
        sibling_options = self.options()
        for case in sibling_options['cases']:
            case['id'] += '-independent'
            case['input'] += ' 独立兄弟候选样本，未用于前一修订。'
        with patch.object(R, '_configuration', return_value={}):
            manual = R.start(self.P, self.p, 'evaluate', sibling['id'], sibling_options, 'owner', 'sibling', launch=False)
        self.assertIsNone(X.job_owner(self.store, manual['id']))
        self.store.x("UPDATE learning_jobs SET status='cancelled' WHERE id=?", (manual['id'],))
        other = self.seal(self.draft(self.body(candidate_revision_id=sibling['id'])))
        self.assertEqual(len(self.slots(other['experiment_id'])), 6)

    def test_manual_registration_rechecks_reverse_lineage_inside_writer_transaction(self):
        child = self.child(); draft = self.draft(self.body(candidate_revision_id=child['id']))
        entered, release = threading.Event(), threading.Event()
        original = E.validate_options
        def hold(*args, **kwargs):
            result = original(*args, **kwargs)
            entered.set()
            self.assertTrue(release.wait(5))
            return result
        with patch.object(R, '_configuration', return_value={}), patch.object(E, 'validate_options', side_effect=hold):
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                future = pool.submit(R.start, self.P, self.p, 'evaluate', self.revision['id'],
                                     self.options(), 'owner', 'manual-race', False)
                try:
                    self.assertTrue(entered.wait(5))
                    self.seal(draft)
                finally:
                    release.set()
                with self.assertRaises(ApiError) as error:
                    future.result(timeout=5)
                self.assertEqual(error.exception.code, 409)
        self.assertIsNone(self.store.one("SELECT id FROM learning_jobs WHERE request_id='manual-race'"))

    def test_legacy_queued_parent_cannot_resume_claim_or_register_a_step(self):
        child = self.child()
        with patch.object(R, '_configuration', return_value={}):
            job = R.start(self.P, self.p, 'evaluate', self.revision['id'], self.options(),
                          'owner', 'legacy-parent', launch=False)
        self.store.x("UPDATE learning_jobs SET status='cancelled' WHERE id=?", (job['id'],))
        self.seal(self.draft(self.body(candidate_revision_id=child['id'])))
        # Reconstruct the unsafe queued shape that the old start API allowed
        # after child seal; this is a legacy ledger fixture, not a new API step.
        self.store.x("UPDATE learning_jobs SET status='queued' WHERE id=?", (job['id'],))
        with patch.object(R, '_launch') as launch:
            self.reject(lambda: R.resume(self.P, self.p, job['id'], 'owner'))
            self.reject(lambda: R.start(self.P, self.p, 'evaluate', self.revision['id'],
                                       self.options(), 'owner', 'legacy-parent'))
        launch.assert_not_called()
        before = self.snapshot()
        with patch.object(R, '_Worker') as construct:
            R._work(self.P, self.p, job['id'])
        construct.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.store.x("UPDATE learning_jobs SET status='running',owner='legacy-owner',lease_until=? WHERE id=?",
                     (time.time()+20, job['id']))
        worker = R._Worker(self.P, self.p, job['id'], 'legacy-owner')
        before = self.snapshot()
        with patch.object(worker.runner, 'invoke') as invoke, self.assertRaises(R._Stopped) as stopped:
            worker.step('legacy-step', '完整合成提示词，不调用模型')
        self.assertEqual(stopped.exception.status, 'stale')
        invoke.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.store.q('SELECT * FROM runs'), [])

    def test_active_manual_step_still_blocks_child_seal_at_invoke_boundary(self):
        child = self.child();draft = self.draft(self.body(candidate_revision_id=child['id']))
        configuration = dict(agent='claude', model='synthetic', executable=sys.executable,
                             configuration={}, prompt_version=R.PROMPT_VERSION)
        class BoundaryReached(RuntimeError):pass
        reached = []
        with patch.object(R, '_configuration', return_value=configuration):
            job = R.start(self.P, self.p, 'evaluate', self.revision['id'], self.options(),
                          'owner', 'active-parent', launch=False)
            self.store.x("UPDATE learning_jobs SET status='running',owner='active-owner',lease_until=? WHERE id=?",
                         (time.time()+20, job['id']))
            worker = R._Worker(self.P, self.p, job['id'], 'active-owner')
            def before_real_invoke(*args, **kwargs):
                reached.append(args[0])
                self.reject(lambda: self.seal(draft))
                raise BoundaryReached('test stops before any model process')
            with patch.object(worker.runner, 'invoke', side_effect=before_real_invoke), self.assertRaises(BoundaryReached):
                worker.step('active-step', '完整合成提示词，不调用模型')
        self.assertEqual(len(reached), 1)
        self.assertEqual(self.exp(draft['experiment_id'])['state'], 'draft')
        self.assertEqual(self.slots(draft['experiment_id']), [])
        self.assertEqual(self.store.one('SELECT calls FROM learning_jobs WHERE id=?', (job['id'],))['calls'], 1)

    def test_damaged_parent_chain_cannot_be_used_to_admit_reverse_budget(self):
        child = self.child();self.seal(self.draft(self.body(candidate_revision_id=child['id'])))
        for broken in ('missing-revision', child['id']):
            with self.subTest(parent=broken):
                self.store.x('UPDATE learning_revisions SET parent_id=? WHERE id=?', (broken, child['id']))
                self.reject(lambda: self.draft())

    @unittest.skipUnless(os.name == 'posix', 'two real interpreters use inherited socket barriers')
    def test_two_independent_processes_sealing_reverse_lineage_create_one_budget(self):
        child = self.child()
        drafts = [self.draft(), self.draft(self.body(candidate_revision_id=child['id']))]
        children = []
        try:
            for draft in drafts:
                parent, peer = socket.socketpair();parent.settimeout(5)
                try:
                    proc = subprocess.Popen([sys.executable, '-c', _SEAL_CHILD, str(self.data),
                        draft['experiment_id'], draft['contract_hash'], str(peer.fileno())],
                        pass_fds=(peer.fileno(),), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                except BaseException:
                    parent.close();raise
                finally:
                    peer.close()
                children.append((proc, parent))
            for _, parent in children:self.assertEqual(parent.recv(1), b'R')
            for _, parent in children:parent.sendall(b'S')
            outputs = []
            for proc, _ in children:
                stdout, stderr = proc.communicate(timeout=5)
                self.assertEqual(proc.returncode, 0, stderr)
                outputs.append(json.loads(stdout))
            (self.home / 'two-process-seal.json').write_text(json.dumps(outputs))
            self.assertEqual(sum('receipt' in x for x in outputs), 1)
            self.assertEqual([x['code'] for x in outputs if 'code' in x], [409])
            self.assertEqual(len(self.store.q('SELECT * FROM learning_jobs')), 1)
            self.assertEqual(len(self.store.q('SELECT * FROM learning_experiment_slots')), 6)
        finally:
            for proc, parent in children:
                if proc.poll() is None:proc.kill()
                proc.communicate(timeout=5);parent.close()


if __name__ == '__main__':unittest.main()
