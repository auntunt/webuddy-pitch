"""Real supervised synthetic children, deterministic ledger barriers, no models."""
import concurrent.futures
import copy
import json
import os
import sqlite3
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from tests.experiment_fixture import ExperimentFixture
from tmh.platform import learn, learning as L, learning_runs as R, tenant_policy as TP
from tmh.platform import learning_experiments as X, learning_experiment_runs as XR
from tmh.platform.errors import ApiError


@unittest.skipUnless(os.name == 'posix', 'existing supervised-process proof requires POSIX')
class ExperimentExecutionTests(ExperimentFixture, unittest.TestCase):
    def test_one_job_executes_every_repeat_with_real_receipts_and_no_rsi_claim(self):
        value = self.running(repeats=2, max_calls=12)
        with patch.object(R.IndependentRunner, 'invoke', side_effect=AssertionError('no model invocation')):
            XR.work(self.P, self.p, value['experiment_id'])
        exp = self.exp(value['experiment_id'])
        self.assertEqual(exp['state'], 'mechanism_passed')
        report = exp['report']
        self.assertTrue(report['mechanism_passed'])
        self.assertFalse(report['rsi_qualified'])
        self.assertFalse(report['production_prompt_equivalence'])
        self.assertEqual((report['planned_slots'], report['repeats'], report['independent_real_sources']), (12, 2, 0))
        self.assertEqual(report['synthetic_source_families'], 3)
        self.assertEqual(report['budget'], dict(max_calls=12, reserved_calls=0, settled_calls=12, synthetic_units=12))
        self.assertEqual(report['actual_cost']['status'], 'unavailable')
        self.assertEqual(report['actual_tokens']['status'], 'unavailable')
        self.assertEqual(len(self.store.q('SELECT * FROM learning_jobs')), 1)
        self.assertEqual(self.store.one('SELECT status FROM learning_jobs WHERE id=?', (value['job_id'],))['status'], 'not_passed')
        for slot in self.slots(exp['id']):
            life = R._sealed_run(self.P, slot['run_id'])
            self.assertTrue(life['finished'])
            self.assertEqual(len(life['attempts']), 1)
            self.assertTrue(life['attempts'][0]['cleanup']['complete'])
            self.assertEqual(life['attempts'][0]['prompt_sha256'], slot['prompt_hash'])
            self.assertEqual(self.store.run(slot['run_id'])['session_id'], None)
        before = self.snapshot()
        XR.work(self.P, self.p, exp['id'])
        self.assertEqual(self.snapshot(), before)

    def test_first_failure_stops_but_preserves_complete_planned_denominator(self):
        wrong = "import sys,json;json.loads(sys.stdin.read());sys.stdout.write('WRONG')"
        with patch.object(X, 'SYNTHETIC_CODE', wrong):
            value = self.running(repeats=2, max_calls=12)
            XR.work(self.P, self.p, value['experiment_id'])
        exp = self.exp(value['experiment_id'])
        self.assertEqual(exp['state'], 'not_passed')
        self.assertEqual(exp['report']['planned_slots'], 12)
        self.assertEqual(exp['report']['budget']['settled_calls'], 1)
        self.assertEqual(len(self.store.q('SELECT * FROM runs')), 1)
        self.assertEqual([r['state'] for r in self.slots(exp['id'])][1:], ['not_executed'] * 11)
        self.assertEqual(exp['report']['slots'][0]['result']['output'], 'WRONG')

    def test_oversize_whole_pair_is_not_dispatched_and_keeps_all_slots(self):
        tasks = tuple(dict(t, input=t['input'] + '界' * 22000) for t in X._TASKS)
        with patch.object(X, '_TASKS', tasks):
            value = self.running()
            with patch.object(R.IndependentRunner, 'run_command') as command:
                XR.work(self.P, self.p, value['experiment_id'])
                command.assert_not_called()
        exp = self.exp(value['experiment_id'])
        self.assertEqual(exp['state'], 'not_passed')
        self.assertEqual(exp['report']['planned_slots'], 6)
        self.assertEqual({s['state'] for s in self.slots(exp['id'])}, {'not_executed'})
        self.assertEqual(self.store.q('SELECT * FROM runs'), [])
        self.assertEqual(exp['report']['budget']['settled_calls'], 0)

    def test_control_creation_replays_stop_latched_before_control_existed(self):
        worker = self.worker()
        material = self.next_material(worker)
        entered, released = threading.Event(), threading.Event()
        errors = []
        original = worker.runner._control
        def paused_control(*args, **kwargs):
            entered.set()
            self.assertTrue(released.wait(5))
            return original(*args, **kwargs)
        def invoke():
            try:
                worker.run_slot(material)
            except BaseException as exc:
                errors.append(exc)
        with patch.object(worker.runner, '_control', side_effect=paused_control), patch.object(worker.runner, 'run_command') as command:
            thread = threading.Thread(target=invoke)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                X.cancel(self.P, self.p, worker.eid, 'owner', 'control-window')
                watcher = threading.Thread(target=worker.watch)
                watcher.start()
                watcher.join(3)
                self.assertFalse(watcher.is_alive())
                self.assertEqual(worker.stop_reason, 'cancelled')
                self.assertNotIn(material['slot']['run_id'], worker.runner.controls)
            finally:
                released.set()
                thread.join(5)
                worker.stop.set()
            command.assert_not_called()
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        control = worker.runner.controls[material['slot']['run_id']]
        self.assertTrue(control['event'].is_set())
        self.assertEqual(control['stopped_reason'], 'cancelled')
        XR._safety_finalize(self.P, self.p, worker.eid, worker.token, worker.fence, 'cancelled')
        self.assertFalse(self.exp(worker.eid)['report']['mechanism_passed'])

    def _interrupt_real_child(self, action, expected_state):
        # Readiness comes from the actual child output, never a scheduling sleep.
        code = "import sys,json,time;json.loads(sys.stdin.read());sys.stdout.write('READY\\n');sys.stdout.flush();time.sleep(60)"
        ready = threading.Event()
        original = R.IndependentRunner.run_command
        workers, failures = [], []
        def observed(runner, *args, **kwargs):
            workers.append((runner, args[0]))
            chunks = []
            def output(text):
                chunks.append(text)
                if 'READY\n' in ''.join(chunks):
                    ready.set()
            kwargs['on_output'] = output
            return original(runner, *args, **kwargs)
        with patch.object(X, 'SYNTHETIC_CODE', code):
            value = self.running()
            def run():
                try:
                    XR.work(self.P, self.p, value['experiment_id'])
                except BaseException as exc:
                    failures.append(exc)
            with patch.object(R.IndependentRunner, 'run_command', observed):
                thread = threading.Thread(target=run)
                thread.start()
                try:
                    self.assertTrue(ready.wait(10), 'actual synthetic child never announced readiness')
                    action(value)
                    thread.join(10)
                    self.assertFalse(thread.is_alive(), 'cancellation/revocation did not stop the real child')
                finally:
                    for runner, rid in workers:
                        runner._stopped(rid, 'cancelled')
                    thread.join(10)
        self.assertEqual(failures, [])
        exp = self.exp(value['experiment_id'])
        self.assertEqual(exp['state'], expected_state)
        self.assertEqual(exp['report']['planned_slots'], 6)
        self.assertFalse(exp['report']['mechanism_passed'])
        slot = self.slots(exp['id'])[0]
        life = R._sealed_run(self.P, slot['run_id'])
        self.assertTrue(life['attempts'][0]['cleanup']['complete'])
        self.assertEqual(life['stopped_reason'], 'cancelled')
        self.assertEqual(exp['report']['budget']['reserved_calls'], 0)
        self.assertEqual(exp['report']['budget']['settled_calls'], 1)
        return value, slot

    def test_actual_cancellation_proves_cleanup_and_keeps_all_failures(self):
        self._interrupt_real_child(lambda v: X.cancel(self.P, self.p, v['experiment_id'], 'owner', 'cancel-live'), 'cancelled')

    def test_actual_participant_revocation_stops_owned_child_without_publishing_success(self):
        value, slot = self._interrupt_real_child(lambda _: self.change('project_revoke', user='curator', project_id=self.p['id']), 'stale')
        result = json.loads(slot['result'])
        self.assertEqual(result['cleanup_status'], 'confirmed')
        self.assertFalse(result['passed'])
        before = self.snapshot()
        with self.assertRaises(ApiError):
            XR.start_sealed(self.P, self.p, value['experiment_id'], 'owner', 'not-a-resume', launch=False)
        self.assertEqual(self.snapshot(), before)

    def test_original_deadline_after_intent_is_not_restarted(self):
        worker = self.worker()
        material = self.next_material(worker)
        # Control the clock boundary after T2, preserving original contract and
        # limits; no real process is necessary to prove no new dispatch occurs.
        worker.start_mono -= worker.initial_remaining + 1
        before = self.snapshot()
        with patch.object(worker.runner, 'run_command') as command, self.assertRaises(R._Stopped):
            worker.run_slot(material)
        command.assert_not_called()
        self.assertEqual(self.slots(worker.eid)[0]['dispatch_id'], '')
        XR._safety_finalize(self.P, self.p, worker.eid, worker.token, worker.fence, 'timed_out')
        self.assertEqual(self.exp(worker.eid)['state'], 'timed_out')
        self.assertEqual(self.exp(worker.eid)['report']['budget']['reserved_calls'], 0)
        self.assertEqual(self.exp(worker.eid)['report']['planned_slots'], 6)

    def test_unknown_intent_keeps_reservation_and_never_replays(self):
        worker = self.worker()
        material = self.next_material(worker)
        dispatch = worker.intent(material)
        XR._safety_finalize(self.P, self.p, worker.eid, worker.token, worker.fence, 'unknown')
        before = self.snapshot()
        with patch.object(R.IndependentRunner, 'run_command') as command:
            XR.work(self.P, self.p, worker.eid)
            XR.recover(self.P)
            command.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        slot = self.slots(worker.eid)[0]
        self.assertEqual((slot['state'], slot['dispatch_id'], slot['reserved_calls'], slot['settled_calls']), ('unknown', dispatch, 1, 0))
        self.assertEqual(self.exp(worker.eid)['report']['planned_slots'], 6)

    def test_old_owner_cannot_settle_or_cleanup_new_generation(self):
        worker = self.worker()
        material = self.next_material(worker)
        worker.intent(material)
        self.store.x('UPDATE learning_experiments SET owner=?,fence=fence+1 WHERE id=?', ('replacement', worker.eid))
        before = self.snapshot()
        with self.assertRaises(ApiError):
            worker.settle(material, {}, 'late-old-success', 'late-old-success')
        XR._safety_finalize(self.P, self.p, worker.eid, worker.token, worker.fence, 'cancelled')
        with patch('tmh.platform.crash_recovery.reconcile') as recover:
            XR._recover_registered(self.P, self.p, worker.eid, worker.token, worker.fence)
            recover.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_recovery_of_reserved_pre_intent_refunds_without_new_call(self):
        worker = self.worker()
        material = self.next_material(worker)
        with patch.object(R.IndependentRunner, 'run_command') as command:
            XR.work(self.P, self.p, worker.eid)
            command.assert_not_called()
        slot = self.slots(worker.eid)[0]
        self.assertEqual((slot['state'], slot['reserved_calls'], slot['settled_calls']), ('not_executed', 0, 0))
        self.assertEqual(self.store.run(material['slot']['run_id'])['status'], 'failed')
        self.assertEqual(self.exp(worker.eid)['report']['planned_slots'], 6)

    def test_restart_unprovable_clock_rolls_back_claim_and_safely_finalizes(self):
        worker = self.worker()
        material = self.next_material(worker)
        with patch.object(X, 'PROCESS_EPOCH', 'different-process'), patch.object(R.IndependentRunner, 'run_command') as command:
            XR.work(self.P, self.p, worker.eid)
            command.assert_not_called()
        exp = self.exp(worker.eid)
        self.assertEqual(exp['state'], 'unknown')
        self.assertEqual(exp['fence'], worker.fence)
        self.assertEqual(self.slots(worker.eid)[0]['state'], 'not_executed')
        self.assertEqual(exp['report']['budget']['reserved_calls'], 0)

    def test_t2_concurrency_one_cannot_register_two_runs(self):
        worker = self.worker()
        slots = self.slots(worker.eid)
        barrier = threading.Barrier(2)
        def register(slot):
            barrier.wait(5)
            try:
                return worker.register_step(slot['id'])
            except ApiError as exc:
                return exc
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(register, (slots[0], slots[0])))
        self.assertEqual(sum(isinstance(v, dict) for v in outcomes), 1)
        self.assertEqual(sum(isinstance(v, ApiError) for v in outcomes), 1)
        self.assertEqual(len(self.store.q('SELECT * FROM runs')), 1)
        self.assertEqual(sum(s['reserved_calls'] for s in self.slots(worker.eid)), 1)

    def test_settlement_fault_rolls_back_result_step_and_budget(self):
        worker = self.worker()
        material = self.next_material(worker)
        original = worker.settle
        captured = {}
        def save(*args):
            captured['args'] = args
            return False
        with patch.object(worker, 'settle', side_effect=save):
            worker.run_slot(material)
        before = self.snapshot()
        with self.fault('INSERT INTO learning_experiment_events'), self.assertRaises(OSError):
            original(*captured['args'])
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(original(*captured['args']))
        self.assertEqual(self.slots(worker.eid)[0]['settled_calls'], 1)
        before = self.snapshot()
        with self.assertRaises(ApiError):
            original(*captured['args'])
        self.assertEqual(self.snapshot(), before)

    def test_recovery_snapshot_never_executes_same_session_planned_work(self):
        value = self.running()
        ids = XR.recovery_candidates(self.P)
        self.assertEqual(ids, [value['experiment_id']])
        with patch.object(XR, 'work', side_effect=AssertionError('recovery cannot dispatch')), \
             patch.object(R.IndependentRunner, 'run_command') as command:
            self.assertEqual(XR.recover(self.P, ids), dict(processed=ids, failed=[], skipped=[], stopped=False))
            command.assert_not_called()
        exp = self.exp(ids[0])
        self.assertEqual(exp['state'], 'stale')
        self.assertEqual(exp['report']['planned_slots'], 6)
        self.assertEqual(self.store.q('SELECT * FROM runs'), [])
        self.assertEqual({s['state'] for s in self.slots(exp['id'])}, {'not_executed'})

    def test_recovery_does_not_scan_new_work_or_ignore_stop_event(self):
        snapshot = XR.recovery_candidates(self.P)
        value = self.running()
        before = self.snapshot()
        self.assertEqual(XR.recover(self.P, snapshot), dict(processed=[], failed=[], skipped=[], stopped=False))
        self.assertEqual(self.snapshot(), before)
        stop = threading.Event()
        stop.set()
        self.assertEqual(XR.recover(self.P, [value['experiment_id']], stop), dict(processed=[], failed=[], skipped=[], stopped=True))
        self.assertEqual(self.snapshot(), before)

    def test_recovery_skips_live_kernel_owner(self):
        from tmh.platform import filelock
        value = self.running()
        folder = XR._folder(self.P, value['experiment_id'])
        folder.mkdir(parents=True)
        with (folder / 'owner.lock').open('a+b') as stream:
            filelock.try_lock(stream)
            try:
                before = self.snapshot()
                with patch.object(XR, '_recover_registered') as recover:
                    self.assertEqual(XR.recover(self.P, [value['experiment_id']]), dict(processed=[], failed=[], skipped=[value['experiment_id']], stopped=False))
                    recover.assert_not_called()
                self.assertEqual(self.snapshot(), before)
            finally:
                filelock.unlock(stream)

    def test_recovery_intent_without_receipt_is_unknown_with_no_wait_or_refund(self):
        worker = self.worker()
        material = self.next_material(worker)
        worker.intent(material)
        with patch('tmh.platform.crash_recovery.reconcile', side_effect=ValueError('no owner proof')) as reconcile:
            self.assertEqual(XR.recover(self.P, [worker.eid]), dict(processed=[worker.eid], failed=[], skipped=[], stopped=False))
        self.assertEqual(reconcile.call_args.kwargs, {'wait_seconds': 0})
        exp = self.exp(worker.eid)
        self.assertEqual(exp['state'], 'unknown')
        self.assertEqual(exp['report']['budget']['reserved_calls'], 1)
        self.assertEqual(self.slots(worker.eid)[0]['state'], 'unknown')
        self.assertEqual(json.loads(self.slots(worker.eid)[0]['result'])['cleanup_status'], 'not_proven')
        self.assertEqual(exp['report']['planned_slots'], 6)


    def test_corrupt_first_record_does_not_strand_real_reserved_second_record(self):
        first = self.worker()
        first_material = self.next_material(first)
        first.intent(first_material)
        # A distinct real source gives the next experiment its own fixed plan.
        card = learn.add_lesson(self.data, {
            'project': 'APP', 'ticket': 'APP-2', 'status': 'candidate',
            'title': '第二个独立合成流程', 'symptom': '检查回执', 'fix': '保留原记录',
            'verify': '核对完整回执', 'applicability': '合成流程', 'non_applicability': '真实生产结论'})
        origin = L._origin(self.P, self.p, 'lesson:' + card['id'])
        self.revision = L.capture(self.P, self.p, origin['key'], origin['fingerprint'], 'owner')
        second = self.worker()
        material = self.next_material(second)
        self.store.x("UPDATE learning_experiments SET contract=? WHERE id=?", ('{private-invalid-contract', first.eid))
        first_before = self.store.one('SELECT * FROM learning_experiments WHERE id=?', (first.eid,))
        first_slots = self.slots(first.eid)
        first_run = self.store.run(first_material['slot']['run_id'])
        with patch.object(XR, 'work', side_effect=AssertionError('no recovery dispatch')), \
             patch.object(R.IndependentRunner, 'run_command') as command:
            report = XR.recover(self.P, [first.eid, second.eid])
            command.assert_not_called()
        self.assertEqual(report, dict(processed=[second.eid], failed=[{
            'experiment_id': first.eid, 'code': 'experiment_recovery_invalid'}], skipped=[], stopped=False))
        self.assertNotIn('private-invalid-contract', json.dumps(report))
        self.assertEqual(self.store.one('SELECT * FROM learning_experiments WHERE id=?', (first.eid,)), first_before)
        self.assertEqual(self.slots(first.eid), first_slots)
        self.assertEqual(self.store.run(first_material['slot']['run_id']), first_run)
        exp = self.exp(second.eid)
        self.assertEqual(exp['state'], 'stale')
        self.assertEqual(exp['report']['planned_slots'], 6)
        self.assertEqual(exp['report']['budget']['reserved_calls'], 0)
        self.assertEqual({slot['state'] for slot in self.slots(second.eid)}, {'not_executed'})
        self.assertEqual(self.store.run(material['slot']['run_id'])['status'], 'failed')
        step = self.store.one('SELECT * FROM learning_steps WHERE run_id=?', (material['slot']['run_id'],))
        self.assertEqual(step['status'], 'failed')

    def test_recovery_reports_only_safe_error_codes_and_honors_stop_after_failure(self):
        ids = ['a' * 32, 'b' * 32]
        cases = ((ApiError(409, 'private-task-content'), 'experiment_recovery_invalid'),
                 (ValueError('private-task-content'), 'experiment_recovery_invalid'),
                 (OSError('private-task-content'), 'experiment_recovery_io'),
                 (sqlite3.DatabaseError('private-task-content'), 'experiment_recovery_storage'))
        for error, code in cases:
            with self.subTest(code=code, kind=type(error).__name__), \
                 patch.object(XR, '_recover_one', side_effect=[error, 'skipped']):
                report = XR.recover(self.P, ids)
                self.assertEqual(report, dict(processed=[], failed=[{'experiment_id': ids[0], 'code': code}], skipped=[ids[1]], stopped=False))
                self.assertNotIn('private-task-content', json.dumps(report))
        report = XR.recover(self.P, ['private-invalid-id'])
        self.assertEqual(report['failed'], [{'experiment_id': None, 'code': 'experiment_recovery_invalid'}])
        self.assertNotIn('private-invalid-id', json.dumps(report))
        stop = threading.Event()
        def fail_and_stop(P, eid):
            stop.set()
            raise OSError('private-path')
        with patch.object(XR, '_recover_one', side_effect=fail_and_stop) as recover:
            report = XR.recover(self.P, ids, stop)
            self.assertEqual(recover.call_count, 1)
            self.assertTrue(report['stopped'])
            self.assertEqual(report['processed'], [])
        with patch.object(XR, '_recover_one', side_effect=AssertionError('implementation bug')):
            with self.assertRaisesRegex(AssertionError, 'implementation bug'):
                XR.recover(self.P, ids)


    def _last_slot_material_change(self, change, *, after_settle=False):
        value = self.running()
        eid = value['experiment_id']
        entered, released = threading.Event(), threading.Event()
        failures, observed, running = [], {}, []
        original = XR._Worker.settle
        run_command = R.IndependentRunner.run_command
        def observe(runner, rid, *args, **kwargs):
            running.append((runner, rid))
            return run_command(runner, rid, *args, **kwargs)
        def settle(worker, material, life, output, raw):
            if material['slot']['ordinal'] != 6:
                return original(worker, material, life, output, raw)
            observed.update(material=material, life=life, output=output, raw=raw)
            result = original(worker, material, life, output, raw) if after_settle else None
            entered.set()
            self.assertTrue(released.wait(5), 'last-slot material barrier was not released')
            return result if after_settle else original(worker, material, life, output, raw)
        def invoke():
            try:
                XR.work(self.P, self.p, eid)
            except BaseException as exc:
                failures.append(exc)
        with patch.object(XR._Worker, 'settle', settle), \
             patch.object(R.IndependentRunner, 'run_command', observe):
            thread = threading.Thread(target=invoke)
            thread.start()
            try:
                self.assertTrue(entered.wait(15), 'real final invocation did not reach its settlement barrier')
                slot = self.slots(eid)[-1]
                self.assertEqual(slot['state'], 'completed' if after_settle else 'intent')
                run = self.store.run(slot['run_id'])
                self.assertEqual((run['status'], run['exit_code']), ('done', 0))
                self.assertTrue(observed['life']['finished'])
                self.assertTrue(observed['life']['attempts'][0]['cleanup']['complete'])
                self.assertEqual(self.store.q("SELECT id FROM learning_experiment_slots WHERE experiment_id=? AND state='planned'", (eid,)), [])
                change(eid)
            finally:
                released.set()
                thread.join(15)
                finished = not thread.is_alive()
                if not finished:
                    for runner, rid in running:
                        runner._stopped(rid, 'cancelled')
                    thread.join(10)
        self.assertTrue(finished, 'last-slot verification did not finish; cleanup cannot turn this into a pass')
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        exp, slots = self.exp(eid), self.slots(eid)
        self.assertEqual(exp['state'], 'stale')
        self.assertFalse(exp['report']['mechanism_passed'])
        self.assertFalse(exp['report']['rsi_qualified'])
        self.assertEqual(exp['report']['planned_slots'], 6)
        self.assertEqual(exp['report']['budget'], dict(max_calls=6, reserved_calls=0, settled_calls=6, synthetic_units=6))
        self.assertEqual(len(self.store.q('SELECT * FROM runs')), 6)
        self.assertEqual([slot['state'] for slot in slots], ['completed'] * 5 + ['completed' if after_settle else 'failed'])
        result = json.loads(slots[-1]['result'])
        self.assertEqual(result['output'], observed['output'])
        self.assertEqual(result['raw_output'], observed['raw'])
        if not after_settle:
            self.assertFalse(result['passed'])
            self.assertEqual(result['cleanup_status'], 'confirmed')
        return eid

    def test_last_real_slot_rejects_source_edit_before_settlement(self):
        self._last_slot_material_change(lambda _: learn.edit_lesson(
            self.data, self.card['id'], {'fix': '最终子进程完成后发生的真实人工编辑'}, 'owner'))

    def test_last_real_slot_rejects_rehashed_asset_before_settlement(self):
        def change(eid):
            asset = self.store.one("SELECT * FROM learning_experiment_assets WHERE experiment_id=? AND kind='candidate'", (eid,))
            value = json.loads(asset['content'])
            value['content'] += '\r\nforged-after-final-intent'
            self.store.x('UPDATE learning_experiment_assets SET content=?,content_hash=? WHERE experiment_id=? AND id=?',
                         (X.encoded(value), X.digest(value), eid, asset['id']))
        self._last_slot_material_change(change)

    def test_source_edit_after_final_settlement_cannot_publish_mechanism_passed(self):
        self._last_slot_material_change(lambda _: learn.edit_lesson(
            self.data, self.card['id'], {'fix': '最后结算与最终报告之间的人工作业'}, 'owner'), after_settle=True)

    def _interrupted_generation_barrier(self, *, intent, revoke=False):
        worker = self.worker()
        material = self.next_material(worker)
        if intent:
            worker.intent(material)
        eid = worker.eid
        before = self.snapshot()
        entered, released = threading.Event(), threading.Event()
        failures, seen = [], []
        class InterruptedRecovery(BaseException):
            pass
        def stop_before_recovery(P, p, saved_eid, token, fence, *args, **kwargs):
            seen.append((saved_eid, token, fence))
            entered.set()
            self.assertTrue(released.wait(5))
            raise InterruptedRecovery('synthetic interruption before durable stop bookkeeping')
        def invoke():
            try:
                XR.work(self.P, self.p, eid)
            except BaseException as exc:
                failures.append(exc)
        with patch.object(XR, '_recover_registered', side_effect=stop_before_recovery), \
             patch.object(R.IndependentRunner, 'run_command') as command:
            thread = threading.Thread(target=invoke)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                exp = self.exp(eid)
                self.assertEqual((exp['owner'], exp['fence']), (worker.token, worker.fence))
                self.assertEqual(self.snapshot(), before, 'stop-only recovery must not commit a replacement generation')
                if revoke:
                    self.change('project_revoke', user='curator', project_id=self.p['id'])
            finally:
                released.set()
                thread.join(5)
            command.assert_not_called()
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], InterruptedRecovery)
        self.assertEqual(seen, [(eid, worker.token, worker.fence)])
        self.assertEqual(self.snapshot(), before)
        # A second stop-only attempt sees the same persisted generation; it
        # cannot depend on an in-memory previous_owner from the lost worker.
        with patch.object(XR, 'work', side_effect=AssertionError('no dispatch during recovery')), \
             patch.object(R.IndependentRunner, 'run_command') as command:
            report = XR.recover(self.P, [eid])
            command.assert_not_called()
        self.assertEqual(report, dict(processed=[eid], failed=[], skipped=[], stopped=False))
        exp, slots = self.exp(eid), self.slots(eid)
        self.assertEqual(exp['fence'], worker.fence)
        self.assertFalse(exp['report']['mechanism_passed'])
        self.assertEqual(exp['report']['planned_slots'], 6)
        self.assertEqual([slot['state'] for slot in slots][1:], ['not_executed'] * 5)
        self.assertEqual(exp['report']['budget']['reserved_calls'], 1 if intent else 0)
        self.assertEqual(exp['report']['budget']['settled_calls'], 0)
        self.assertEqual(slots[0]['state'], 'unknown' if intent else 'not_executed')
        self.assertEqual(json.loads(slots[0]['result'])['cleanup_status'], 'not_proven' if intent else 'not_started')
        self.assertEqual(len(self.store.q('SELECT * FROM runs')), 1)
        if not intent:
            self.assertEqual(self.store.run(material['slot']['run_id'])['status'], 'failed')
            self.assertEqual(self.store.one('SELECT status FROM learning_steps WHERE run_id=?', (material['slot']['run_id'],))['status'], 'failed')

    def test_interrupted_reserved_recovery_keeps_original_owner_across_second_failure(self):
        self._interrupted_generation_barrier(intent=False)

    def test_interrupted_intent_recovery_after_revocation_keeps_unknown_reservation(self):
        self._interrupted_generation_barrier(intent=True, revoke=True)


    def test_final_material_check_crossing_real_deadline_cannot_publish_success(self):
        value = self.running(timeout_seconds=30)
        eid = value['experiment_id']
        entered, released = threading.Event(), threading.Event()
        failures, observed = [], {}
        original = X.material_current
        def blocked(P, p, exp, *args, **kwargs):
            result = original(P, p, exp, *args, **kwargs)
            states = [row['state'] for row in P.store.db.execute(
                'SELECT state FROM learning_experiment_slots WHERE experiment_id=?', (eid,))]
            if exp['id'] == eid and states and set(states) == {'completed'}:
                observed.update(remaining=X.remaining_in_tx(P.store.db, exp), deadline=exp['deadline'])
                entered.set()
                self.assertTrue(released.wait(35))
            return result
        def invoke():
            try:
                XR.work(self.P, self.p, eid)
            except BaseException as exc:
                failures.append(exc)
        with patch.object(X, 'material_current', blocked):
            thread = threading.Thread(target=invoke)
            thread.start()
            try:
                self.assertTrue(entered.wait(20), 'all real slots must finish before the original final deadline barrier')
                self.assertGreater(observed['remaining'], 0)
                # Advance only real time. No clock replacement, DB deadline
                # change or expanded execution timeout is used by this test.
                threading.Event().wait(observed['remaining'] + .03)
            finally:
                released.set()
                thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        exp = self.exp(eid)
        self.assertEqual(exp['deadline'], observed['deadline'])
        self.assertEqual(exp['state'], 'timed_out')
        self.assertFalse(exp['report']['mechanism_passed'])
        self.assertEqual(exp['report']['planned_slots'], 6)
        self.assertEqual(exp['report']['budget'], dict(max_calls=6, reserved_calls=0, settled_calls=6, synthetic_units=6))
        self.assertEqual({slot['state'] for slot in self.slots(eid)}, {'completed'})
        for slot in self.slots(eid):
            self.assertTrue(R._sealed_run(self.P, slot['run_id'])['attempts'][0]['cleanup']['complete'])
