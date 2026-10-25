"""Finite-mode original capture, heldout isolation and actual assertion worker."""
import copy
import os
import unittest
from tests import test_rsi_native_bc_report as N
from scripts.rsi import trial_preparation as L, provider_adapter as P, registered_trial as R, native_bc_report as B
from tmh.platform import learn


@unittest.skipUnless(os.name == 'posix', 'private registry and real supervision require POSIX')
class FiniteNativeTests(unittest.TestCase):
    def test_complete_original_pairs_and_holdout_recapture_fence_without_fake_metering(self):
        f = N.NativeReportTests('test_original_two_arm_assertions_execute_in_supervised_worker_and_replay_without_http')
        f.setUp(); self.addCleanup(f.doCleanups); c = f.c
        c.base['schema'] = L.FINITE_VERSION; c.base['root_family'] = 'new-finite-native-root'
        c.base['budget'] = dict(unit='observed_tokens', authorization_sha256=L.digest('synthetic new finite native authorization'),
                                prior_evidence_sha256=L.digest('historical roots remain; observed accounting only'))
        c.base['limits'] = {k:v for k,v in c.base['limits'].items() if k != 'billed_tokens'}
        c.base['limits']['max_total_tokens'] = None
        for name in ('input_cap_tokens','input_cap_reference_sha256','bound_evidence_ref'): c.profile.pop(name)
        c.profile.update(schema=P.FINITE_VERSION, max_request_bytes=1_000_000, billing_mode='observed-usage-v1',
                         parameters_version='messages-text-finite-v1',protocol_sha256=L.digest(P.FINITE_PROTOCOLS['messages']),
                         contract_sha256=L.digest(c.base))
        c.write_profile(); c.key = c.adapter.register('fixture', c.base)
        broker = R.FiniteBroker(c.adapter, f.f.catalog, context=f.f.context, actor='owner')
        reports = B.Reports(broker, c.root/'finite-bc-reports')
        spec = copy.deepcopy(f.spec); spec.update(root_pool=c.key,contract_sha256=L.digest(c.ledger.snapshot(c.key)['contract']),
                                                 authorization_sha256=c.base['budget']['authorization_sha256'])
        path = c.registry_dir/'finite-assertions.json'; path.write_text(L.encoded(spec)); path.chmod(0o600)
        reports.freeze(c.key, 'finite-assertions')
        def send(name, phase='propose', index=3, policy='baseline', input_id=None, input_sha=None):
            plan = dict(schema=R.VERSION,kind=R.FiniteBroker.KIND,input_id=input_id or 'input-'+str(index),input_sha256=input_sha or f.f.input_hashes[index],
                        root_pool=c.key,contract_sha256=L.digest(c.ledger.snapshot(c.key)['contract']),request_id=name,phase=phase,policy=policy,
                        policy_sha256=R.sha(policy.encode()),broker_sha256=R.CODE_SHA256,
                        source_family=c.base['holdout_cases'][index]['source_family'] if phase in {'baseline','candidate'} else c.base['training_family'])
            f.f.catalog.admit('plan',name,plan); return broker.dispatch(name,plan['input_id'])
        history = copy.deepcopy(f.f.history); history[0]['body'] += 'outside last-six model history'
        cap = R.capture(c.store,f.f.project,c.store.ticket(f.f.caps[0]['source']['ticket']['id']),tenant_id='default',history=history)
        digest = f.f.catalog.admit('input','recaptured',cap)
        self.assertNotEqual(digest, f.f.input_hashes[0])
        with self.assertRaises(L.Conflict): send('denied-recapture',input_id='recaptured',input_sha=digest)
        self.assertEqual(c.count,0); self.assertEqual(c.ledger.inspect(c.key)['totals']['calls'],0)
        c.response.pop('usage'); self.assertTrue(send('proposal')['response_complete']); c.adapter.bind_candidate(c.key,'proposal')
        for i in range(3):
            c.response['content'][0]['text'] = 'missing assertion'; self.assertTrue(send('B'+str(i),'baseline',i)['response_complete'])
            c.response['content'][0]['text'] = c.policy; self.assertTrue(send('C'+str(i),'candidate',i,c.policy)['response_complete'])
        report = reports.evaluate(c.key)
        self.assertTrue(report['assertions']['passed']); self.assertFalse(report['rsi_qualified'])
        self.assertEqual(report['assertions']['counts'], {'baseline':0,'candidate':3}); self.assertEqual(c.count,7)
        self.assertIsNone(c.ledger.inspect(c.key)['totals']['billed_tokens'])
        self.assertEqual(reports.read(c.key), report)
        block = next(m['block'] for m in f.f.caps[0]['source']['context'] if m.get('mode')=='learning_lessons')
        learn.set_status(c.root,block['bindings'][0]['id'],'retired','synthetic-owner','withdraw finite-mode knowledge')
        with self.assertRaises(L.Conflict): reports.read(c.key)
        self.assertEqual(c.count,7)


if __name__ == '__main__': unittest.main()
