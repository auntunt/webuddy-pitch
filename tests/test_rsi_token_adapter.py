"""Actual one-shot loopback protocols; trusted bounds here are synthetic only."""
import copy
import hashlib
import json
import os
import threading
import time
import unittest
from pathlib import Path

from tests import test_rsi_provider_adapter as F
from tests import test_rsi_token_budget as T
from tests.sqlite_snapshot import dump_store

P,L=F.P,F.L
h=lambda s:hashlib.sha256(s.encode()).hexdigest()


def responses():
    return dict(id='resp_fixture',object='response',model='fixture-response-v1',status='completed',error=None,incomplete_details=None,
                output=[dict(type='reasoning',id='rs_fixture',summary=[]),dict(type='message',id='msg_fixture',role='assistant',status='completed',
                        content=[dict(type='output_text',text='  exact policy\r\n尾部  ',annotations=[])])],
                usage=dict(input_tokens=9,input_tokens_details=dict(cached_tokens=2),output_tokens=7,output_tokens_details=dict(reasoning_tokens=5),total_tokens=16))


@unittest.skipUnless(os.name=='posix','private registry/real supervised loopback require POSIX')
class TokenAdapterTests(unittest.TestCase):
    shutdown=F.ProviderAdapterTests.shutdown
    write_profile=F.ProviderAdapterTests.write_profile
    dispatch=F.ProviderAdapterTests.dispatch

    def setUp(self):
        F.ProviderAdapterTests.setUp(self)
        self.base=T.contract()
        self.base['root_family']='token-native-root'
        self.base['limits'].update(starts_us=time.time_ns()//1000-1_000_000,deadline_us=time.time_ns()//1000+60_000_000)
        self.profile.pop('price')
        self.profile.update(schema=P.TOKEN_VERSION,billing_mode='tokens-inclusive-v1',protocol='messages',bound_evidence_ref='bound',
                            parameters_version='messages-text-token-v1',contract_sha256=L.digest(self.base),
                            protocol_sha256=L.digest(P.TOKEN_PROTOCOLS['messages']),valid_until_us=self.base['limits']['deadline_us'])
        self.bounds=self.registry_dir/'bounds';self.bounds.mkdir(mode=0o700)
        self.system='baseline'
        self.policy='  exact policy\r\n尾部  '
        self.response['content'][0]['text']=self.policy
        self.admit()

    def admit(self):
        self.profile['contract_sha256']=L.digest(self.base)
        bound=dict(schema='trusted-total-token-bound-v1',kind='provider_enforced_total_limit',mode='fixture',model=self.profile['model'],
                   protocol=self.profile['protocol'],input_cap_tokens=self.profile['input_cap_tokens'],output_cap_tokens=self.profile['output_cap_tokens'],
                   all_input_included=True,all_output_included=True,no_hidden_retries=True,all_tokens_in_usage=True,
                   verified=True,source_sha256=h('synthetic bound; not provider evidence'),valid_until_us=self.profile['valid_until_us'])
        raw=L.encoded(bound).encode();(self.bounds/'bound').write_bytes(raw);(self.bounds/'bound').chmod(0o600)
        self.profile['input_cap_reference_sha256']=hashlib.sha256(raw).hexdigest()
        self.write_profile();self.key=self.adapter.register('fixture',self.base)

    def switch_responses(self):
        self.base['root_family']='explicit-responses-root'
        self.base['budget']['authorization_sha256']=h('distinct synthetic Responses authorization')
        self.profile.update(protocol='responses',parameters_version='responses-text-token-v1',protocol_sha256=L.digest(P.TOKEN_PROTOCOLS['responses']),
                            endpoint=f'http://127.0.0.1:{self.server.server_port}/v1/responses')
        self.response=responses();self.admit()

    def proposal_bind(self):
        r=self.dispatch();self.assertTrue(r['response_complete'])
        b=self.adapter.bind_candidate(self.key,'one');self.assertTrue(b['candidate_derivation_verified'])
        self.assertEqual(self.ledger.snapshot(self.key)['candidate_binding']['candidate_text'],self.policy)
        return r,b

    def test_messages_original_response_derives_exact_policy_and_same_root_terminal(self):
        original=self.ledger.snapshot(self.key)['contract'];r,b=self.proposal_bind()
        self.assertEqual(r['response_text'],self.policy);self.assertEqual(self.auth_ok,[True])
        self.assertEqual(self.paths,['/v1/messages']);self.assertFalse(self.adapter.bind_candidate(self.key,'one')['new_binding'])
        self.assertEqual(self.dispatch('B','baseline')['state'],'settled')
        self.system=self.policy;self.assertEqual(self.dispatch('C','candidate')['state'],'settled')
        self.assertEqual(self.ledger.inspect(self.key)['totals']['billed_tokens'],33)
        self.assertEqual(self.ledger.snapshot(self.key)['contract'],original)
        self.assertFalse(self.ledger.snapshot(self.key)['candidate_derivation_verified'])
        self.assertFalse(r['rsi_qualified']);self.assertFalse(self.ledger.inspect(self.key)['execution_authorized'])
        self.assertEqual(len(self.store.q('SELECT * FROM rsi_prepare_holdouts')),3)
        sent=json.loads(self.requests[0]);self.assertEqual(sent['tools'],[]);self.assertEqual(sent['thinking'],{'type':'disabled'})
        self.assertEqual(sent['messages'],self.messages)

    def test_responses_wire_full_text_inclusive_cache_reasoning_and_replay(self):
        self.switch_responses();r,b=self.proposal_bind()
        self.assertEqual((r['input_tokens'],r['output_tokens']),(9,7))
        self.assertEqual(self.ledger.inspect(self.key)['totals']['billed_tokens'],16)
        self.assertEqual(self.paths,['/v1/responses']);self.assertEqual(self.bearer_ok,[True]);self.assertEqual(self.auth_ok,[False])
        sent=json.loads(self.requests[0]);self.assertEqual(sent['instructions'],self.system);self.assertEqual(sent['input'],self.messages)
        for flag in ('stream','store','background','parallel_tool_calls'):self.assertIs(sent[flag],False)
        self.assertEqual(sent['truncation'],'disabled');self.assertEqual(sent['tools'],[]);self.assertEqual(sent['tool_choice'],'none')
        self.assertEqual(sent['max_output_tokens'],20);self.assertNotIn('previous_response_id',sent)
        self.assertFalse(self.dispatch()['new_dispatch']);self.assertEqual(self.count,1)
        folder=Path(r['evidence']);metadata,raw=(folder/'transport/output.bin').read_bytes().split(b'\n',1)
        self.assertEqual(raw,json.dumps(self.response,ensure_ascii=False).encode())
        self.assertEqual(json.loads(metadata)['protocol'],'responses')
        for f in (self.root/'evidence').rglob('*'):
            if f.is_file():self.assertNotIn(self.secret.encode(),f.read_bytes())

    def test_pending_root_or_wrong_frozen_arm_policy_refuses_before_http(self):
        with self.assertRaises(L.Conflict):self.dispatch('B','baseline')
        self.assertEqual(self.count,0);self.proposal_bind();before=dump_store(self.store)
        self.system='wrong policy'
        for phase in ('baseline','candidate'):
            with self.assertRaises(L.Conflict):self.dispatch('bad-'+phase,phase)
        self.assertEqual(dump_store(self.store),before);self.assertEqual(self.count,1)

    def test_caller_declared_wrong_candidate_never_passes_original_derivation_check(self):
        r=self.dispatch();self.ledger.bind_candidate(self.key,'one','caller invented policy',r['response_sha256'])
        before=dump_store(self.store)
        with self.assertRaises(L.Conflict):self.adapter.bind_candidate(self.key,'one')
        with self.assertRaises(L.Conflict):self.dispatch('B','baseline')
        self.assertEqual(dump_store(self.store),before);self.assertEqual(self.count,1)

    def test_missing_or_unverified_bound_refuses_without_attempt_or_http(self):
        before=dump_store(self.store);(self.bounds/'bound').unlink()
        with self.assertRaises(OSError):self.dispatch()
        self.assertEqual(before,dump_store(self.store));self.assertEqual(self.count,0)

    def test_legacy_fixture_broker_does_not_silently_inherit_token_protocol(self):
        from scripts.rsi.registered_trial import Broker
        before=dump_store(self.store)
        with self.assertRaises(L.Conflict):Broker(self.adapter,None)._profile(self.ledger.snapshot(self.key)['contract'])
        self.assertEqual(before,dump_store(self.store));self.assertEqual(self.count,0)

    def test_uncertain_proxy_retries_or_incomplete_usage_cannot_approve_a_token_bound(self):
        original=json.loads((self.bounds/'bound').read_bytes())
        for name in ('no_hidden_retries','all_tokens_in_usage','all_input_included','all_output_included'):
            bound=copy.deepcopy(original);bound[name]=False;raw=L.encoded(bound).encode()
            (self.bounds/'bound').write_bytes(raw);self.profile['input_cap_reference_sha256']=hashlib.sha256(raw).hexdigest();self.write_profile()
            with self.subTest(name=name):
                with self.assertRaises(ValueError):P.validate_token_bound(self.profile,raw)
                with self.assertRaises(ValueError):self.adapter.register('fixture',self.base)
        self.assertEqual(self.count,0)

    def test_bound_original_replacement_cancels_the_inflight_request(self):
        self.switch_responses();self.wait=True;results=[]
        t=threading.Thread(target=lambda:results.append(self.dispatch()));t.start()
        self.assertTrue(self.seen.wait(3))
        p=self.bounds/'bound';raw=p.read_bytes();replacement=self.bounds/'new-bound'
        replacement.write_bytes(raw);replacement.chmod(0o600);replacement.replace(p)
        t.join(6);self.assertFalse(t.is_alive());self.assertEqual(results[0]['state'],'unknown')
        receipt=F.SP.read_receipt(Path(results[0]['evidence'])/'transport')
        self.assertEqual(receipt['reason'],'cancelled');self.assertEqual(receipt['returncode'],130)
        self.assertTrue(receipt['cleanup']['complete']);self.assertFalse(receipt['cleanup']['remaining_group'])
        self.assertEqual(self.ledger.inspect(self.key)['token_budget']['reserved_or_unknown'],120)
        self.assertEqual(self.count,1);self.release.set()

    def test_unapproved_total_bound_and_fixture_live_substitution_refuse(self):
        raw=(self.bounds/'bound').read_text();bound=json.loads(raw);bound['verified']=False
        raw=L.encoded(bound).encode();(self.bounds/'bound').write_bytes(raw);self.profile['input_cap_reference_sha256']=hashlib.sha256(raw).hexdigest();self.write_profile()
        with self.assertRaises(ValueError):self.adapter.register('fixture',self.base)
        bound['verified']=True;bound['mode']='live';raw=L.encoded(bound).encode();(self.bounds/'bound').write_bytes(raw);self.profile['input_cap_reference_sha256']=hashlib.sha256(raw).hexdigest();self.write_profile()
        with self.assertRaises(ValueError):self.adapter.register('fixture',self.base)
        self.assertEqual(self.count,0)

    def test_root_budget_refuses_reservation_before_http_even_with_valid_profile(self):
        self.base['root_family']='small-root';self.base['budget']['authorization_sha256']=h('distinct synthetic small authorization')
        self.base['limits']['billed_tokens']=119;self.admit()
        before=dump_store(self.store)
        with self.assertRaises(L.Conflict):self.dispatch()
        self.assertEqual(dump_store(self.store),before);self.assertEqual(self.count,0)

    def test_ambiguous_or_incomplete_policy_still_counts_usage_but_cannot_bind(self):
        self.response['content'].append(dict(type='text',text='second block'))
        r=self.dispatch();self.assertEqual(r['state'],'settled');self.assertFalse(r['response_complete'])
        with self.assertRaises(L.Conflict):self.adapter.bind_candidate(self.key,'one')
        self.assertEqual(self.ledger.inspect(self.key)['totals']['billed_tokens'],11)
        self.assertEqual(self.store.q('SELECT * FROM rsi_prepare_holdouts'),[])

    def test_responses_missing_contradictory_or_boolean_usage_holds_maximum_and_no_retry(self):
        self.switch_responses();self.response['usage']['output_tokens_details']['reasoning_tokens']=8
        r=self.dispatch();self.assertEqual(r['state'],'unknown')
        view=self.ledger.inspect(self.key);self.assertTrue(view['blocked']);self.assertEqual(view['token_budget']['reserved_or_unknown'],120)
        self.assertFalse(self.dispatch()['new_dispatch']);self.assertEqual(self.count,1)
        with self.assertRaises(L.Conflict):self.dispatch('retry','retry')

    def test_pure_protocol_usage_rejects_each_unknown_missing_or_inconsistent_dimension(self):
        cases=[]
        for field in ('input_tokens','output_tokens','total_tokens'):
            for val in (None,True,-1):
                value=responses();value['usage'][field]=val;cases.append(value)
        value=responses();value['usage']['total_tokens']=17;cases.append(value)
        value=responses();value['usage']['input_tokens_details']['cached_tokens']=10;cases.append(value)
        value=responses();del value['usage']['output_tokens_details'];cases.append(value)
        value=responses();value['usage']['server_tool_use']=1;cases.append(value)
        value=responses();value['usage']['input_tokens_details']['cache_write_tokens']=10;cases.append(value)
        for value in cases:
            with self.subTest(usage=value['usage']):
                with self.assertRaises((ValueError,KeyError)):P.normalize_token_response('responses',value,L.encoded(value).encode())

    def test_responses_cache_writes_are_a_parent_subset_and_not_added_twice(self):
        self.switch_responses();self.response['usage']['input_tokens_details']['cache_write_tokens']=3
        r=self.dispatch();self.assertEqual(r['state'],'settled')
        self.assertEqual(self.ledger.inspect(self.key)['totals']['billed_tokens'],16)

    def test_messages_missing_cache_parent_dimensions_do_not_become_zero(self):
        del self.response['usage']['cache_creation_input_tokens']
        r=self.dispatch();self.assertEqual(r['state'],'unknown')
        self.assertEqual(self.ledger.inspect(self.key)['token_budget']['reserved_or_unknown'],120)
        self.assertEqual(self.count,1)

    def test_two_threads_same_request_get_one_real_transport(self):
        self.switch_responses();self.wait=True;results=[]
        t=threading.Thread(target=lambda:results.append(self.dispatch()));t.start()
        self.assertTrue(self.seen.wait(3))
        replay=self.dispatch();self.assertFalse(replay['new_dispatch']);self.assertEqual(replay['state'],'intent')
        self.release.set();t.join(6);self.assertFalse(t.is_alive())
        self.assertEqual(results[0]['state'],'settled');self.assertEqual(self.count,1)
        self.assertEqual(self.ledger.inspect(self.key)['totals']['billed_tokens'],16)

    def test_real_responses_timeout_preserves_hold_and_reaps_original_transport(self):
        self.switch_responses();self.wait=True
        started=time.monotonic();r=self.dispatch()
        self.assertEqual(r['state'],'unknown');self.assertEqual(self.count,1)
        receipt=F.SP.read_receipt(Path(r['evidence'])/'transport',self.adapter._owner(self.key,'one',self.ledger.snapshot(self.key,'one')['attempt']['intent']))
        self.assertEqual(receipt['reason'],'timeout');self.assertEqual(receipt['returncode'],124)
        self.assertTrue(receipt['cleanup']['complete']);self.assertGreaterEqual(time.monotonic()-started,4.9)
        self.assertEqual(self.ledger.inspect(self.key)['token_budget']['reserved_or_unknown'],120)
        self.release.set();self.assertFalse(self.dispatch()['new_dispatch']);self.assertEqual(self.count,1)

    def test_response_tool_output_is_never_an_executable_or_candidate_policy(self):
        self.switch_responses();self.response['output'].append(dict(type='function_call',name='shell',arguments='{}'))
        r=self.dispatch();self.assertEqual(r['state'],'settled');self.assertFalse(r['response_complete'])
        with self.assertRaises(L.Conflict):self.adapter.bind_candidate(self.key,'one')
        self.assertEqual(self.count,1)

    def test_changed_original_response_is_not_accepted_as_cached_or_derived(self):
        r=self.dispatch();folder=Path(r['evidence']);p=folder/'transport/output.bin';p.write_bytes(p.read_bytes()+b'changed')
        with self.assertRaises(L.Conflict):self.adapter.bind_candidate(self.key,'one')
        self.assertEqual(self.count,1);self.assertEqual(self.store.q('SELECT * FROM rsi_prepare_holdouts'),[])

    def test_real_cancellation_after_request_keeps_hold_and_never_reissues(self):
        self.switch_responses();self.wait=True;cancel=threading.Event();results=[]
        t=threading.Thread(target=lambda:results.append(self.dispatch(cancel_event=cancel)));t.start()
        self.assertTrue(self.seen.wait(3));cancel.set();t.join(6)
        self.assertFalse(t.is_alive());self.assertEqual(results[0]['state'],'unknown')
        self.assertTrue(self.ledger.inspect(self.key)['blocked'])
        self.assertEqual(self.ledger.inspect(self.key)['token_budget']['reserved_or_unknown'],120)
        self.assertFalse(self.dispatch()['new_dispatch']);self.assertEqual(self.count,1)
        self.release.set()


if __name__=='__main__':unittest.main()
