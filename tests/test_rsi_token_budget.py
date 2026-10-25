"""Explicit token root; unknown money never becomes a zero-price quote."""
import concurrent.futures
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from tests import test_rsi_trial_preparation as F
from tests.sqlite_snapshot import dump_store
from tmh.platform.store import Store

L = F.M
h = lambda v: hashlib.sha256(v.encode()).hexdigest()


def contract():
    c = F.contract()
    c.update(schema=L.TOKEN_VERSION, candidate_sha256=None)
    del c['price']
    c['budget'] = dict(unit='tokens', authorization_sha256=h('100M replaces CNY20'),
                       prior_confirmed_tokens=0, prior_held_tokens=0,
                       prior_evidence_sha256=h('no in-scope calls before this synthetic root'))
    c['limits'] = dict(calls=20, billed_tokens=100_000_000, starts_us=900, deadline_us=100_000_000)
    return c


class TokenBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tmh-token-root-')
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name)/'root.db')
        self.addCleanup(self.store.db.close)
        self.clock = [1000]
        self.ledger = L.Ledger(self.store, wall_us=lambda:self.clock[0])
        self.c = contract()
        self.key = self.ledger.create(self.c)

    def reject(self, fn, error=L.Conflict):
        before = dump_store(self.store)
        with self.assertRaises(error): fn()
        self.assertEqual(before, dump_store(self.store))

    def reserve(self, request='A', phase='propose', a=10, b=10):
        return self.ledger.reserve(self.key,request,phase,a,b,material_sha256=h('full-'+request))

    def settle(self, request='A', a=4, b=2, cached=2, charge=None):
        intent=self.ledger.intent(self.key,request)['intent']
        return self.ledger.settle(self.key,request,intent,F.receipt(input_tokens=a,output_tokens=b,cached_input_tokens=cached,provider_charge_micro_cny=charge))

    def bind(self):
        return self.ledger.bind_candidate(self.key,'A','  exact policy\r\n ',h('fixture-response'))

    def test_explicit_no_price_or_money_limit_no_fake_zero_and_old_root_preserved(self):
        self.assertNotIn('price',self.c);self.assertNotIn('cost_micro_cny',self.c['limits'])
        for key in ('price','cost_micro_cny'):
            bad=copy.deepcopy(self.c)
            if key=='price':bad['price']=F.contract()['price']
            else:bad['limits'][key]=L.MAX
            self.reject(lambda:self.ledger.create(bad),ValueError)
        old=F.contract();old['root_family']='old-money-root';key=self.ledger.create(old)
        self.assertEqual(self.ledger.snapshot(key)['contract'],old)
        self.reserve();self.assertIsNone(self.ledger.snapshot(self.key,'A')['attempt']['body']['reserved_micro_cny'])
        self.assertEqual(self.settle(),'settled')
        row=self.ledger.snapshot(self.key,'A')['attempt']
        import json
        receipt=json.loads(row['receipt'])
        self.assertIsNone(receipt['accounted_micro_cny']);self.assertEqual(receipt['cost_source'],'unknown')
        self.assertIsNone(self.ledger.inspect(self.key)['totals']['cost_micro_cny'])

    def test_exact_100m_counts_a_and_terminal_then_one_token_over_refuses_before_intent(self):
        self.reserve(a=50_000_000,b=30_000_000)
        self.assertEqual(self.settle(a=50_000_000,b=30_000_000,cached=20_000_000),'settled');self.bind()
        self.reserve('B','baseline',10_000_000,10_000_000)
        self.assertEqual(self.ledger.inspect(self.key)['token_budget']['remaining'],0)
        self.assertEqual(self.settle('B',10_000_000,10_000_000,cached=1),'settled')
        self.reject(lambda:self.reserve('C','candidate',1,1))
        self.assertIsNone(self.store.one('SELECT * FROM rsi_prepare_attempts WHERE request_id=?',('C',)))
        budget=self.ledger.inspect(self.key)['token_budget']
        self.assertEqual(budget['confirmed_used'],100_000_000)
        self.assertEqual(budget['reserved_or_unknown'],0)
        self.assertIn('token_limit_reached',budget['block_reasons'])

    def test_all_remaining_phases_share_the_original_root_and_complete_text_binding(self):
        original=self.ledger.snapshot(self.key)['contract']
        self.reserve();self.settle();self.bind()
        for i,phase in enumerate(sorted(L.PHASES-{'propose'})):
            self.reserve(str(i),phase);self.settle(str(i))
        view=self.ledger.inspect(self.key)
        self.assertEqual(view['totals']['calls'],8)
        self.assertEqual(view['token_budget']['confirmed_used'],48)
        self.assertEqual(self.ledger.snapshot(self.key)['contract'],original)
        self.assertEqual(len(self.store.q('SELECT * FROM rsi_prepare_holdouts')),3)
        self.assertFalse(self.bind()['new_binding'])

    def test_usage_without_money_still_counts_all_cached_input_and_output(self):
        self.reserve(a=100,b=20);self.settle(a=90,b=20,cached=80)
        self.assertEqual(self.ledger.inspect(self.key)['totals']['billed_tokens'],110)
        self.assertEqual(self.ledger.inspect(self.key)['token_budget']['confirmed_used'],110)

    def test_provider_money_is_preserved_without_becoming_a_permission_gate(self):
        self.reserve();self.assertEqual(self.settle(charge=L.MAX),'settled')
        import json
        receipt=json.loads(self.ledger.snapshot(self.key,'A')['attempt']['receipt'])
        self.assertEqual(receipt['accounted_micro_cny'],L.MAX)
        self.assertIsNone(self.ledger.inspect(self.key)['token_budget']['actual_cost_micro_cny'])

    def test_unknown_max_hold_and_late_settlement_never_reopen_dispatch(self):
        self.reserve(a=100,b=20);intent=self.ledger.intent(self.key,'A')['intent']
        self.ledger.unknown(self.key,'A',intent,'synthetic disconnect')
        b=self.ledger.inspect(self.key)['token_budget'];self.assertEqual((b['confirmed_used'],b['reserved_or_unknown']),(0,120))
        self.assertEqual(self.ledger.settle(self.key,'A',intent,F.receipt()),'settled')
        self.assertTrue(self.ledger.inspect(self.key)['blocked'])
        self.reject(lambda:self.bind());self.reject(lambda:self.reserve('again'))

    def test_cancel_before_intent_releases_hold_but_not_attempt_count(self):
        self.reserve();self.ledger.cancel(self.key,'A')
        v=self.ledger.inspect(self.key)
        self.assertEqual(v['totals']['calls'],1);self.assertEqual(v['token_budget']['reserved_or_unknown'],0)
        self.assertEqual(v['token_budget']['remaining'],100_000_000)

    def test_cancel_after_intent_preserves_max_hold_and_blocks(self):
        self.reserve();self.ledger.intent(self.key,'A');self.ledger.cancel(self.key,'A')
        v=self.ledger.inspect(self.key)
        self.assertTrue(v['blocked']);self.assertEqual(v['token_budget']['reserved_or_unknown'],20)
        self.reject(lambda:self.reserve('again'))

    def test_invalid_and_over_cap_usage_never_refunds_max_hold(self):
        self.reserve();intent=self.ledger.intent(self.key,'A')['intent']
        self.assertEqual(self.ledger.settle(self.key,'A',intent,F.receipt(input_tokens=11)),'unknown')
        v=self.ledger.inspect(self.key)
        self.assertTrue(v['blocked']);self.assertEqual(v['token_budget']['reserved_or_unknown'],20)

    def test_boolean_or_missing_usage_is_not_a_zero(self):
        self.reserve();intent=self.ledger.intent(self.key,'A')['intent']
        for field in ('input_tokens','output_tokens','cached_input_tokens'):
            for value in (True,None,-1):
                with self.subTest(field=field,value=value):
                    receipt=F.receipt();receipt[field]=value
                    self.reject(lambda:self.ledger.settle(self.key,'A',intent,receipt),ValueError)
        self.assertEqual(self.ledger.inspect(self.key)['token_budget']['reserved_or_unknown'],20)

    def test_original_window_and_generation_cannot_restart(self):
        future=contract();future['root_family']='future-window';future['limits']['starts_us']=1_000_000
        future['budget']['authorization_sha256']=h('distinct future authorization')
        key=self.ledger.create(future)
        self.reject(lambda:self.ledger.reserve(key,'A','propose',10,10,material_sha256=h('future')))
        self.reserve();self.clock[0]=self.c['limits']['deadline_us']
        self.reject(lambda:self.ledger.intent(self.key,'A'))
        other=L.Ledger(self.store,wall_us=lambda:1000)
        self.reject(lambda:other.intent(self.key,'A'))
        self.assertIn('generation_changed',other.inspect(self.key)['token_budget']['block_reasons'])

    def test_prior_confirmed_is_cumulative_and_prior_unknown_blocks_new_dispatch(self):
        c=contract();c['root_family']='prior-known';c['budget']['prior_confirmed_tokens']=99_999_999
        c['budget']['authorization_sha256']=h('distinct prior authorization')
        key=self.ledger.create(c)
        self.reject(lambda:self.ledger.reserve(key,'A','propose',1,1,material_sha256=h('x')))
        self.assertEqual(self.ledger.inspect(key)['token_budget']['remaining'],1)
        c['root_family']='prior-unknown';c['budget']['prior_held_tokens']=1
        c['budget']['authorization_sha256']=h('distinct unknown prior authorization');key=self.ledger.create(c)
        self.assertIn('prior_unknown',self.ledger.inspect(key)['token_budget']['block_reasons'])
        self.reject(lambda:self.ledger.reserve(key,'A','propose',1,1,material_sha256=h('x')))

    def test_scope_budget_auth_and_window_cannot_change_on_same_root(self):
        for change in ('budget','window','authorization','prior'):
            c=copy.deepcopy(self.c)
            if change=='budget':c['limits']['billed_tokens']+=1
            elif change=='window':c['limits']['deadline_us']+=1
            elif change=='prior':c['budget']['prior_confirmed_tokens']=1
            else:c['budget']['authorization_sha256']=h('other')
            self.reject(lambda:self.ledger.create(c))

    def test_same_authorization_cannot_start_another_root_project_or_model(self):
        for field,value in [('root_family','another-root'),('project_id',2),('tenant_id','other-tenant'),('model',dict(provider='other',requested_model='other',response_model='other'))]:
            c=copy.deepcopy(self.c);c[field]=value
            if field=='model':c['root_family']='other-model-root'
            self.reject(lambda:self.ledger.create(c))
        self.store.db.execute('DELETE FROM rsi_prepare_pools WHERE pool=?',(self.key,));self.store.db.commit()
        c=copy.deepcopy(self.c);c['root_family']='try-orphan-history'
        self.reject(lambda:self.ledger.create(c))

    def test_two_connections_competing_roots_share_one_authorization(self):
        one=contract();one['root_family']='auth-race-one';one['budget']['authorization_sha256']=h('race authorization')
        two=copy.deepcopy(one);two['root_family']='auth-race-two'
        other_store=Store(self.store.path);self.addCleanup(other_store.db.close)
        other=L.Ledger(other_store,wall_us=lambda:1000)
        def create(args):
            ledger,c=args
            try:return ledger.create(c)
            except L.Conflict:return 'refused'
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(create,[(self.ledger,one),(other,two)]))
        self.assertEqual(results.count('refused'),1)
        self.assertEqual(len(self.store.q('SELECT * FROM rsi_prepare_pools')),2)

    def test_concurrent_requests_cannot_both_reserve_or_overspend(self):
        def call(request):
            try:return self.reserve(request,a=40_000_000,b=20_000_000)
            except L.Conflict:return 'refused'
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(call,['A','A2']))
        self.assertEqual(results.count('refused'),1)
        self.assertEqual(self.ledger.inspect(self.key)['token_budget']['reserved_or_unknown'],60_000_000)
        self.assertEqual(len(self.store.q('SELECT * FROM rsi_prepare_attempts')),1)

    def test_token_limit_and_prior_shape_are_explicit_and_bounded(self):
        for bad in (True,0,-1,None,L.MAX+1):
            c=contract();c['limits']['billed_tokens']=bad
            self.reject(lambda:self.ledger.create(c),ValueError)
        c=contract();c['budget']['prior_held_tokens']=100_000_001
        self.reject(lambda:self.ledger.create(c),ValueError)
        c=contract();c['budget']['unit']='CNY'
        self.reject(lambda:self.ledger.create(c),ValueError)

    def test_cancelled_eight_calls_exhaust_attempt_limit_with_explicit_reason(self):
        c=contract();c['root_family']='eight-calls';c['limits']['calls']=8
        c['budget']['authorization_sha256']=h('distinct eight-call authorization')
        key=self.ledger.create(c)
        for i in range(8):
            request='cancelled-'+str(i)
            self.ledger.reserve(key,request,'propose',10,10,material_sha256=h(request))
            self.assertEqual(self.ledger.cancel(key,request),'cancelled')
        before=dump_store(self.store)
        with self.assertRaises(L.Conflict):self.ledger.reserve(key,'ninth','propose',1,1,material_sha256=h('ninth'))
        self.assertEqual(dump_store(self.store),before)
        self.assertEqual(len(self.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=?',(key,))),8)
        self.assertIsNone(self.store.one('SELECT * FROM rsi_prepare_attempts WHERE pool=? AND request_id=?',(key,'ninth')))
        view=self.ledger.inspect(key)
        self.assertEqual(view['totals']['calls'],8)
        self.assertEqual(view['token_budget']['remaining'],100_000_000)
        self.assertEqual(view['token_budget']['reserved_or_unknown'],0)
        self.assertIn('call_limit_reached',view['token_budget']['block_reasons'])


if __name__=='__main__':unittest.main()
