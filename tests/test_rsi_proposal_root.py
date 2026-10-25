"""One pre-proposal root, declared candidate and presealed cases; no paid execution."""
import concurrent.futures
import copy
import hashlib
import sqlite3
import tempfile
from pathlib import Path
import unittest

from tests import test_rsi_trial_preparation as F
from tests.sqlite_snapshot import dump_store
from tmh.platform.store import Store

M = F.M
h = lambda v: hashlib.sha256(v.encode()).hexdigest()


class ProposalRootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tmh-proposal-')
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'root.db')
        self.addCleanup(self.store.db.close)
        self.clock = [1000]
        self.ledger = M.Ledger(self.store, wall_us=lambda: self.clock[0])
        self.c = F.contract()
        self.c.update(schema=M.PROPOSAL_VERSION, candidate_sha256=None)
        self.c['limits']['cost_micro_cny'] = 20_000_000
        self.key = self.ledger.create(self.c)
        self.policy = '  完整候选策略\r\n第二行与尾部  '

    def reserve(self, request='A', phase='propose', a=10, b=10, ledger=None, key=None):
        return (ledger or self.ledger).reserve(key or self.key, request, phase, a, b, material_sha256=h('complete-'+request))

    def proposal(self, request='A', ledger=None, key=None, **usage):
        ledger = ledger or self.ledger;key = key or self.key
        self.reserve(request, ledger=ledger, key=key)
        intent = ledger.intent(key, request)['intent']
        self.assertEqual(ledger.settle(key, request, intent, F.receipt(**usage)), 'settled')
        return intent

    def bind(self, request='A', policy=None, ledger=None, key=None, raw=None):
        return (ledger or self.ledger).bind_candidate(key or self.key, request, self.policy if policy is None else policy, raw or h('fixture-response'))

    def rejected(self, fn, error=M.Conflict):
        before = dump_store(self.store)
        with self.assertRaises(error):fn()
        self.assertEqual(before, dump_store(self.store))

    def test_root_freezes_before_candidate_and_never_rewrites_contract(self):
        original = self.store.one('SELECT * FROM rsi_prepare_pools WHERE pool=?', (self.key,))
        self.assertIsNone(self.ledger.snapshot(self.key)['contract']['candidate_sha256'])
        self.assertFalse(self.ledger.inspect(self.key)['candidate_bound'])
        self.proposal();bound = self.bind()
        current = self.store.one('SELECT * FROM rsi_prepare_pools WHERE pool=?', (self.key,))
        for name in ('contract', 'contract_hash', 'created_us', 'generation'):
            self.assertEqual(current[name], original[name])
        self.assertEqual(self.ledger.snapshot(self.key)['contract'], self.c)
        self.assertEqual(self.ledger.inspect(self.key)['contract_hash'], M.digest(self.c))
        self.assertEqual(bound['candidate_sha256'], h(self.policy))
        self.assertEqual(self.ledger.snapshot(self.key)['candidate_binding']['candidate_text'], self.policy)
        self.assertFalse(self.ledger.snapshot(self.key)['candidate_derivation_verified'])
        self.assertFalse(self.ledger.inspect(self.key)['execution_authorized'])

    def test_legacy_requires_candidate_and_proposal_never_embeds_generated_candidate(self):
        old = F.contract();old['candidate_sha256'] = None
        self.rejected(lambda: self.ledger.create(old), ValueError)
        c = copy.deepcopy(self.c);c['candidate_sha256'] = h(self.policy)
        self.rejected(lambda: self.ledger.create(c), ValueError)

    def test_missing_material_and_all_nonproposal_phases_refuse_before_binding(self):
        self.rejected(lambda: self.ledger.reserve(self.key, 'bad', 'propose', 10, 10), ValueError)
        for phase in sorted(M.PHASES - {'propose'}):
            with self.subTest(phase=phase):self.rejected(lambda phase=phase: self.reserve('bad-'+phase, phase))
        self.rejected(lambda: self.ledger.consume_holdout(self.key))

    def test_binding_requires_original_settled_proposal_and_exact_response_reference(self):
        self.rejected(lambda: self.bind())
        self.reserve();self.rejected(lambda: self.bind())
        intent = self.ledger.intent(self.key, 'A')['intent'];self.rejected(lambda: self.bind())
        self.ledger.settle(self.key, 'A', intent, F.receipt())
        self.rejected(lambda: self.bind(raw=h('other-response')))
        self.rejected(lambda: self.bind(policy='baseline'))
        self.assertTrue(self.bind()['new_binding'])

    def test_binding_once_consumes_all_presealed_cases_and_replay_is_read_only(self):
        self.proposal();first = self.bind();before = dump_store(self.store)
        self.assertTrue(first['new_binding'])
        self.assertEqual(len(self.store.q('SELECT * FROM rsi_prepare_holdouts')), 3)
        self.assertFalse(self.bind()['new_binding'])
        self.assertEqual(before, dump_store(self.store))
        self.assertFalse(self.ledger.consume_holdout(self.key))
        self.rejected(lambda: self.bind(policy='another policy'))
        self.rejected(lambda: self.bind(request='another-proposal'))
        self.rejected(lambda: self.reserve('new-A'))
        row = self.reserve('B', 'baseline')
        self.assertEqual(row['body']['candidate_binding_sha256'], first['binding_sha256'])
        self.assertEqual(row['body']['contract_hash'], M.digest(self.c))

    def test_root_budget_counts_proposal_and_terminal_together(self):
        c = copy.deepcopy(self.c);c['root_family'] = 'twenty-yuan-root'
        c['price'].update(input_micro_cny_per_token=1_000_000, cached_micro_cny_per_token=1_000_000, output_micro_cny_per_token=1_000_000)
        key = self.ledger.create(c)
        self.reserve('A20', a=8, b=8, key=key)
        intent = self.ledger.intent(key, 'A20')['intent']
        self.ledger.settle(key, 'A20', intent, F.receipt(input_tokens=8, cached_input_tokens=0, output_tokens=8))
        self.bind('A20', key=key)
        self.assertEqual(self.ledger.inspect(key)['totals']['cost_micro_cny'], 16_000_000)
        self.rejected(lambda: self.reserve('B-too-large', 'baseline', 3, 3, key=key))
        self.reserve('B-fit', 'baseline', 2, 2, key=key)
        totals = self.ledger.inspect(key)['totals']
        self.assertEqual(totals, dict(calls=2, billed_tokens=20, cost_micro_cny=20_000_000))
        changed = copy.deepcopy(c);changed['limits']['cost_micro_cny'] += 1
        self.rejected(lambda: self.ledger.create(changed))

    def test_pending_or_unknown_attempts_never_bind_or_release_budget(self):
        self.proposal();self.reserve('pending')
        self.rejected(lambda: self.bind())
        intent = self.ledger.intent(self.key, 'pending')['intent']
        self.ledger.unknown(self.key, 'pending', intent, 'fixture-disconnect')
        before = self.ledger.inspect(self.key)['totals']
        self.rejected(lambda: self.bind())
        self.assertEqual(before, self.ledger.inspect(self.key)['totals'])
        self.assertTrue(self.ledger.inspect(self.key)['blocked'])

    def test_late_known_receipt_never_reopens_unknown_proposal_root(self):
        self.reserve();intent = self.ledger.intent(self.key, 'A')['intent']
        self.ledger.unknown(self.key, 'A', intent, 'unknown')
        self.assertEqual(self.ledger.settle(self.key, 'A', intent, F.receipt()), 'settled')
        self.rejected(lambda: self.bind())
        self.rejected(lambda: self.reserve('retry-A'))

    def test_cancel_before_intent_keeps_call_count_but_allows_existing_proposal_binding(self):
        self.proposal();self.reserve('not-sent')
        self.assertEqual(self.ledger.cancel(self.key, 'not-sent'), 'cancelled')
        self.assertTrue(self.bind()['new_binding'])
        self.assertEqual(self.ledger.inspect(self.key)['totals']['calls'], 2)

    def test_generation_and_original_deadline_still_fence_new_binding(self):
        self.proposal()
        other = M.Ledger(self.store, wall_us=lambda: self.clock[0])
        self.rejected(lambda: self.bind(ledger=other))
        self.clock[0] = self.c['limits']['deadline_us']
        self.rejected(lambda: self.bind())
        self.assertFalse(self.ledger.inspect(self.key)['candidate_bound'])

    def test_completed_binding_replay_after_restart_is_only_history(self):
        self.proposal();first = self.bind();other = M.Ledger(self.store, wall_us=lambda: self.clock[0])
        before = dump_store(self.store)
        self.assertFalse(self.bind(ledger=other)['new_binding'])
        self.assertEqual(before, dump_store(self.store))
        self.rejected(lambda: self.reserve('B-after-restart', 'baseline', ledger=other))
        self.assertEqual(self.ledger.snapshot(self.key)['contract'], self.c)

    def test_same_project_cannot_reuse_cases_with_another_candidate_root(self):
        self.proposal();self.bind()
        c = copy.deepcopy(self.c);c['root_family'] = 'new-root-same-cases';key = self.ledger.create(c)
        self.proposal('A2', key=key)
        self.rejected(lambda: self.bind('A2', policy='other-candidate', key=key))
        self.assertEqual(len(self.store.q('SELECT * FROM rsi_prepare_holdouts')), 3)
        self.assertFalse(self.ledger.inspect(key)['candidate_bound'])

    def test_different_project_remains_independent(self):
        self.proposal();self.bind()
        c = copy.deepcopy(self.c);c['project_id'] = 2;key = self.ledger.create(c)
        self.proposal('A2', key=key)
        self.assertTrue(self.bind('A2', key=key)['new_binding'])
        self.assertEqual(len(self.store.q('SELECT * FROM rsi_prepare_holdouts')), 6)

    def test_binding_and_claims_rollback_together_on_database_fault(self):
        self.proposal()
        self.store.db.executescript("CREATE TRIGGER stop_claim BEFORE INSERT ON rsi_prepare_holdouts WHEN NEW.input_hash='" + self.c['holdout_cases'][1]['input_sha256'] + "' BEGIN SELECT RAISE(ABORT,'fixture'); END;")
        self.rejected(lambda: self.bind(), sqlite3.IntegrityError)
        self.assertEqual(self.store.q("SELECT * FROM rsi_prepare_events WHERE kind IN ('bind_candidate','consume_holdout')"), [])
        self.assertEqual(self.store.q('SELECT * FROM rsi_prepare_holdouts'), [])
        self.store.db.execute('DROP TRIGGER stop_claim');self.store.db.commit()
        self.assertTrue(self.bind()['new_binding'])

    def test_concurrent_same_binding_has_one_anchor_and_three_claims(self):
        self.proposal()
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.bind(),range(2)))
        self.assertEqual(sorted(x['new_binding'] for x in results), [False, True])
        self.assertEqual(len(self.store.q("SELECT * FROM rsi_prepare_events WHERE kind='bind_candidate'")), 1)
        self.assertEqual(len(self.store.q('SELECT * FROM rsi_prepare_holdouts')), 3)

    def test_failure_after_binding_event_rolls_back_all_claims_and_both_events(self):
        self.proposal()
        self.store.db.executescript("CREATE TRIGGER stop_consumption BEFORE INSERT ON rsi_prepare_events WHEN NEW.kind='consume_holdout' BEGIN SELECT RAISE(ABORT,'fixture'); END;")
        self.rejected(lambda: self.bind(), sqlite3.IntegrityError)
        self.assertFalse(self.ledger.inspect(self.key)['candidate_bound'])
        self.assertEqual(self.store.q('SELECT * FROM rsi_prepare_holdouts'), [])
        self.assertEqual(self.store.q("SELECT * FROM rsi_prepare_events WHERE kind IN ('bind_candidate','consume_holdout')"), [])

    def test_two_connections_competing_roots_cannot_both_consume_the_same_cases(self):
        self.proposal()
        other_store = Store(self.store.path)
        self.addCleanup(other_store.db.close)
        other = M.Ledger(other_store, wall_us=lambda: self.clock[0])
        c = copy.deepcopy(self.c)
        c['root_family'] = 'competing-root'
        other_key = other.create(c)
        self.proposal('A2', ledger=other, key=other_key)
        def call(args):
            ledger, key, request = args
            try:
                return self.bind(request, ledger=ledger, key=key)
            except M.Conflict:
                return 'refused'
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(call, [(self.ledger, self.key, 'A'), (other, other_key, 'A2')]))
        self.assertEqual(sum(isinstance(r, dict) and r['new_binding'] for r in results), 1)
        self.assertEqual(results.count('refused'), 1)
        self.assertEqual(len(self.store.q('SELECT * FROM rsi_prepare_holdouts')), 3)
        self.assertEqual(len(self.store.q("SELECT * FROM rsi_prepare_events WHERE kind='bind_candidate'")), 1)
        self.assertEqual(len(self.store.q("SELECT * FROM rsi_prepare_events WHERE kind='consume_holdout'")), 1)
        snapshots = [self.ledger.snapshot(self.key), other.snapshot(other_key)]
        self.assertEqual(sum(s['candidate_binding'] is not None for s in snapshots), 1)

    def test_two_connections_cannot_replace_the_first_candidate(self):
        self.proposal();other_store=Store(self.store.path);self.addCleanup(other_store.db.close)
        other=M.Ledger(other_store,wall_us=lambda:self.clock[0])
        def call(args):
            ledger,policy=args
            try:return self.bind(ledger=ledger,policy=policy)
            except M.Conflict:return 'refused'
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(call,[(self.ledger,self.policy),(other,'other candidate')]))
        self.assertEqual(sum(isinstance(r,dict) and r['new_binding'] for r in results),1)
        self.assertEqual(self.ledger.snapshot(self.key)['candidate_binding']['candidate_text'],self.policy)

    def test_deleted_binding_or_consumption_or_claims_fail_closed_without_repair(self):
        self.proposal();self.bind()
        self.store.db.execute("DELETE FROM rsi_prepare_events WHERE kind='consume_holdout'");self.store.db.commit()
        self.rejected(lambda:self.ledger.snapshot(self.key))
        self.rejected(lambda:self.reserve('B','baseline'))

    def test_missing_claim_is_not_reconsumed(self):
        self.proposal();self.bind()
        self.store.db.execute('DELETE FROM rsi_prepare_holdouts WHERE input_hash=?',(self.c['holdout_cases'][0]['input_sha256'],));self.store.db.commit()
        self.rejected(lambda:self.bind())
        self.rejected(lambda:self.ledger.consume_holdout(self.key))

    def test_deleted_candidate_anchor_does_not_leave_claims_reusable(self):
        self.proposal();self.bind()
        self.store.db.execute("DELETE FROM rsi_prepare_events WHERE kind='bind_candidate'");self.store.db.commit()
        self.rejected(lambda:self.ledger.snapshot(self.key))
        self.rejected(lambda:self.ledger.create(self.c))

    def test_reanchored_attempt_cannot_switch_candidate_binding(self):
        self.proposal();self.bind();row=self.reserve('B','baseline')
        body=copy.deepcopy(row['body']);body['candidate_binding_sha256']=h('other-binding')
        self.store.db.execute('UPDATE rsi_prepare_attempts SET body=?,body_hash=? WHERE pool=? AND request_id=?',(M.encoded(body),M.digest(body),self.key,'B'))
        self.store.db.execute("UPDATE rsi_prepare_events SET payload=?,payload_hash=? WHERE pool=? AND request_id=? AND kind='reserve'",(M.encoded(body),M.digest(body),self.key,'B'));self.store.db.commit()
        self.rejected(lambda:self.ledger.snapshot(self.key,'B'))
        self.rejected(lambda:self.ledger.intent(self.key,'B'))

    def test_missing_consumption_and_claims_cannot_erase_binding_history(self):
        self.proposal();self.bind()
        self.store.db.execute('DELETE FROM rsi_prepare_holdouts');self.store.db.execute("DELETE FROM rsi_prepare_events WHERE kind='consume_holdout'");self.store.db.commit()
        self.rejected(lambda:self.ledger.inspect(self.key))

    def test_rehashed_candidate_change_still_conflicts_with_consumption(self):
        self.proposal();self.bind()
        event=self.store.one("SELECT * FROM rsi_prepare_events WHERE kind='bind_candidate'")
        import json
        payload=json.loads(event['payload']) if isinstance(event['payload'],str) else copy.deepcopy(event['payload'])
        payload.update(candidate_text='changed',candidate_sha256=h('changed'))
        self.store.db.execute('UPDATE rsi_prepare_events SET payload=?,payload_hash=? WHERE id=?',(M.encoded(payload),M.digest(payload),event['id']));self.store.db.commit()
        self.rejected(lambda:self.ledger.snapshot(self.key))

    def test_late_unknown_keeps_binding_history_and_maximum_reservation(self):
        self.proposal();self.bind();row=self.ledger.snapshot(self.key,'A')['attempt']
        self.rejected(lambda:self.ledger.unknown(self.key,'A',row['intent'],'not an active intent'))
        self.assertEqual(self.ledger.invalidate_framing(self.key,'A',row['intent']),'unknown')
        state=self.ledger.inspect(self.key)
        self.assertTrue(state['candidate_bound']);self.assertTrue(state['blocked'])
        self.assertEqual(state['totals']['cost_micro_cny'],300)
        self.rejected(lambda:self.reserve('B','baseline'))
        self.rejected(lambda:self.ledger.settle(self.key,'A',row['intent'],F.receipt()))

    def test_existing_provider_adapter_does_not_silently_accept_pending_schema(self):
        from scripts.rsi import provider_adapter
        with self.assertRaises(ValueError):provider_adapter._base(self.c)


if __name__=='__main__':unittest.main()
