"""Finite one-shot plans without a total token cap; all HTTP is synthetic loopback."""
import copy
import hashlib
import json
import os
import time
import threading
from pathlib import Path
import unittest
from tests import test_rsi_provider_adapter as F, test_rsi_token_budget as T, test_rsi_token_adapter as A
from tests.sqlite_snapshot import dump_store
from scripts.rsi import registered_trial as R

L, P = F.L, F.P
h = lambda v: hashlib.sha256(v.encode()).hexdigest()


def contract():
    c = T.contract()
    c['schema'] = 'trial-finite-proposal-v6'
    c['root_family'] = 'prospective-finite-execution'
    c['budget'] = dict(unit='observed_tokens', authorization_sha256=h('synthetic prospective cap waiver'),
                       prior_evidence_sha256=h('prior evidence is retained; no historical accounting completeness claim'))
    c['limits'] = dict(calls=8, max_total_tokens=None, starts_us=time.time_ns()//1000-1_000_000,
                       deadline_us=time.time_ns()//1000+60_000_000)
    return c


@unittest.skipUnless(os.name == 'posix', 'private registry and real supervision require POSIX')
class FiniteExecutionTests(unittest.TestCase):
    def setUp(self):
        self.f = F.ProviderAdapterTests('test_success_full_raw_cache_accounting_and_no_credential_artifact')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.old_key = self.f.key
        self.old = self.f.ledger.snapshot(self.old_key)['contract']
        self.c = contract()
        p = self.f.profile
        for key in ('price', 'input_cap_tokens', 'input_cap_reference_sha256'): p.pop(key)
        p.update(schema='server-fixed-text-finite-adapter-v3', protocol='messages', max_request_bytes=100000,
                 billing_mode='observed-usage-v1', parameters_version='messages-text-finite-v1',
                 protocol_sha256=L.digest(P.FINITE_PROTOCOLS['messages']), contract_sha256=L.digest(self.c),
                 valid_until_us=self.c['limits']['deadline_us'])
        self.f.system = 'baseline'; self.f.response['content'][0]['text'] = ' exact candidate\r\n '
        self.admit()

    def admit(self):
        self.f.profile['contract_sha256'] = L.digest(self.c)
        self.f.write_profile(); self.f.key = self.f.adapter.register('fixture', self.c)

    def test_null_cap_is_explicit_and_old_contract_is_unchanged(self):
        self.assertIsNone(L.validate_contract(self.c)['limits']['max_total_tokens'])
        for cap in (L.MAX, 100000000, 0, False):
            c = copy.deepcopy(self.c); c['limits']['max_total_tokens'] = cap
            with self.subTest(cap=cap), self.assertRaises(ValueError): L.validate_contract(c)
        c = copy.deepcopy(self.c); del c['limits']['max_total_tokens']
        with self.assertRaises(ValueError): L.validate_contract(c)
        self.assertEqual(self.f.ledger.snapshot(self.old_key)['contract'], self.old)
        self.assertNotIn('price', self.c); self.assertNotIn('cost_micro_cny', self.c['limits'])

    def test_complete_messages_with_missing_usage_needs_no_bound_and_can_bind(self):
        self.assertFalse((self.f.registry_dir/'bounds').exists())
        self.f.response.pop('usage'); r = self.f.dispatch()
        self.assertEqual(r['state'], 'settled'); self.assertTrue(r['response_complete'])
        self.assertEqual(r['usage_status'], 'unknown'); self.assertIsNone(r['input_tokens'])
        bound = self.f.adapter.bind_candidate(self.f.key, 'one')
        self.assertTrue(bound['candidate_derivation_verified'])
        self.assertEqual(self.f.ledger.snapshot(self.f.key)['candidate_binding']['candidate_text'], ' exact candidate\r\n ')
        v = self.f.ledger.inspect(self.f.key)
        self.assertIsNone(v['totals']['billed_tokens']); self.assertEqual(v['totals']['reported_tokens'], 0)
        self.assertEqual(v['totals']['response_usage_status'], 'unknown')
        self.assertIsNone(v['execution_plan']['max_total_tokens']); self.assertNotIn('token_budget', v)
        self.assertFalse(self.f.dispatch()['new_dispatch']); self.assertEqual(self.f.count, 1)
        self.assertEqual(self.f.ledger.snapshot(self.old_key)['contract'], self.old)

    def test_reported_usage_above_old_100m_does_not_become_a_new_cap(self):
        self.f.response['usage'].update(input_tokens=100_000_001)
        r = self.f.dispatch(); self.assertEqual(r['state'], 'settled')
        self.assertEqual(r['input_tokens'], 100_000_006)
        v = self.f.ledger.inspect(self.f.key)
        self.assertEqual(v['totals']['reported_tokens'], 100_000_008)
        self.assertIsNone(v['totals']['billed_tokens']); self.assertIsNone(v['totals']['cost_micro_cny'])
        self.assertEqual(v['totals']['hidden_attempts'], 'unknown')
        self.assertNotIn('token_limit_reached', v['execution_plan']['block_reasons'])

    def test_responses_partial_usage_preserved_unknown_not_a_dispatch_blocker(self):
        self.c['root_family'] = 'prospective-responses'
        self.c['budget']['authorization_sha256'] = h('second synthetic prospective authorization')
        self.f.profile.update(protocol='responses', endpoint=f'http://127.0.0.1:{self.f.server.server_port}/v1/responses',
                              parameters_version='responses-text-finite-v1', protocol_sha256=L.digest(P.FINITE_PROTOCOLS['responses']))
        self.f.response = A.responses(); self.f.response['usage'] = {'input_tokens': 9}
        self.admit(); r = self.f.dispatch()
        self.assertTrue(r['response_complete']); self.assertEqual(r['usage_status'], 'unknown')
        receipt = json.loads(self.f.ledger.snapshot(self.f.key, 'one')['attempt']['receipt'])
        self.assertEqual(receipt['usage_raw'], {'input_tokens': 9})
        self.assertIsNone(receipt['output_tokens']); self.assertEqual(self.f.bearer_ok, [True])
        self.f.adapter.bind_candidate(self.f.key, 'one')
        self.assertFalse(self.f.dispatch()['new_dispatch']); self.assertEqual(self.f.count, 1)

    def test_finite_call_plan_remains_cumulative_even_for_missing_usage(self):
        self.f.response.pop('usage'); self.f.dispatch(); self.f.adapter.bind_candidate(self.f.key, 'one')
        for i in range(7): self.assertEqual(self.f.dispatch(str(i), 'probe')['state'], 'settled')
        before = dump_store(self.f.store)
        with self.assertRaises(L.Conflict): self.f.dispatch('ninth', 'probe')
        self.assertEqual(dump_store(self.f.store), before); self.assertEqual(self.f.count, 8)
        self.assertIn('call_limit_reached', self.f.ledger.inspect(self.f.key)['execution_plan']['block_reasons'])

    def test_request_byte_limit_refuses_before_reserve_without_truncation(self):
        self.f.messages[0]['content'] = '汉字'*100000
        before = dump_store(self.f.store)
        with self.assertRaises(L.Conflict): self.f.dispatch()
        self.assertEqual(dump_store(self.f.store), before); self.assertEqual(self.f.count, 0)

    def test_unknown_transport_cannot_repeat_or_continue(self):
        self.f.raw_override = b'{not-json'
        self.assertEqual(self.f.dispatch()['state'], 'unknown'); self.assertEqual(self.f.count, 1)
        self.assertFalse(self.f.dispatch()['new_dispatch']); self.assertEqual(self.f.count, 1)
        with self.assertRaises(L.Conflict): self.f.dispatch('different', 'propose')
        self.assertTrue(self.f.ledger.inspect(self.f.key)['blocked'])

    def test_original_time_generation_and_preintent_cancel_do_not_refresh_plan(self):
        row = self.f.ledger.reserve(self.f.key, 'cancelled', 'propose', 100000, 20, material_sha256=h('whole request'))
        self.assertIsNone(row['body']['reserved_micro_cny'])
        self.assertEqual(self.f.ledger.cancel(self.f.key, 'cancelled'), 'cancelled')
        self.assertEqual(self.f.ledger.inspect(self.f.key)['totals']['calls'], 1)
        newer = L.Ledger(self.f.store)
        with self.assertRaises(L.Conflict): newer.reserve(self.f.key, 'new-generation', 'propose', 1, 1, material_sha256=h('new'))
        self.f.ledger.wall = lambda: self.c['limits']['deadline_us']
        before = dump_store(self.f.store)
        with self.assertRaises(L.Conflict): self.f.dispatch()
        self.assertEqual(dump_store(self.f.store), before); self.assertEqual(self.f.count, 0)

    def test_explicit_broker_entry_does_not_relax_old_token_entry(self):
        c = self.f.ledger.snapshot(self.f.key)['contract']
        broker = R.FiniteBroker(self.f.adapter, None)
        self.assertEqual(broker._profile(c)['schema'], P.FINITE_VERSION)
        with self.assertRaises(L.Conflict): R.TokenBroker(self.f.adapter, None)._profile(c)
        with self.assertRaises(L.Conflict): broker._profile(self.old)
        duplicate = copy.deepcopy(self.c); duplicate['root_family'] = 'same-waiver-second-root'
        with self.assertRaises(L.Conflict): self.f.ledger.create(duplicate)
        self.assertEqual(self.f.count, 0)

    def test_same_request_concurrency_returns_one_actual_transport(self):
        self.f.wait = True; result = []
        thread = threading.Thread(target=lambda: result.append(self.f.dispatch()))
        thread.start()
        try:
            self.assertTrue(self.f.seen.wait(3))
            replay = self.f.dispatch()
            self.assertFalse(replay['new_dispatch']); self.assertEqual(replay['state'], 'intent')
        finally:
            self.f.release.set(); thread.join(6)
        self.assertFalse(thread.is_alive()); self.assertEqual(result[0]['state'], 'settled')
        self.assertEqual(self.f.count, 1)

    def test_actual_cancel_reaps_original_and_never_reissues(self):
        self.f.wait = True; cancel = threading.Event(); result = []
        thread = threading.Thread(target=lambda: result.append(self.f.dispatch(cancel_event=cancel)))
        thread.start()
        try:
            self.assertTrue(self.f.seen.wait(3)); cancel.set(); thread.join(6)
            self.assertFalse(thread.is_alive()); self.assertEqual(result[0]['state'], 'unknown')
            owner = self.f.adapter._owner(self.f.key, 'one', self.f.ledger.snapshot(self.f.key, 'one')['attempt']['intent'])
            receipt = F.SP.read_receipt(Path(result[0]['evidence'])/'transport', owner)
            self.assertEqual(receipt['reason'], 'cancelled'); self.assertTrue(receipt['cleanup']['complete'])
            self.assertFalse(receipt['cleanup']['remaining_group'])
            self.assertFalse(self.f.dispatch()['new_dispatch']); self.assertEqual(self.f.count, 1)
        finally:
            cancel.set(); self.f.release.set(); thread.join(6)

    def test_actual_timeout_retains_unknown_and_never_reissues(self):
        self.f.wait = True
        try:
            start = time.monotonic(); result = self.f.dispatch()
            self.assertEqual(result['state'], 'unknown'); self.assertGreaterEqual(time.monotonic()-start, 4.9)
            owner = self.f.adapter._owner(self.f.key, 'one', self.f.ledger.snapshot(self.f.key, 'one')['attempt']['intent'])
            receipt = F.SP.read_receipt(Path(result['evidence'])/'transport', owner)
            self.assertEqual(receipt['reason'], 'timeout'); self.assertTrue(receipt['cleanup']['complete'])
            self.assertFalse(receipt['cleanup']['remaining_group'])
            self.assertFalse(self.f.dispatch()['new_dispatch']); self.assertEqual(self.f.count, 1)
        finally: self.f.release.set()


if __name__ == '__main__': unittest.main()
