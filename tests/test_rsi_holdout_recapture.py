"""Ordinary recapture aliases must not reveal presealed BC tasks to training."""
import copy
import json
import os
from pathlib import Path
import unittest
from tests import test_rsi_native_registered as N
from tests.sqlite_snapshot import dump_store
from scripts.rsi import registered_trial as R, trial_preparation as L


@unittest.skipUnless(os.name=='posix','private catalog and supervised loopback require POSIX')
class RecaptureTests(unittest.TestCase):
    def setUp(self):
        self.f=N.NativeRegisteredTests('test_two_arms_use_same_complete_capture_original_root_and_derived_policy')
        self.f.setUp();self.addCleanup(self.f.doCleanups);self.f.authorize_context();self.c=self.f.c

    def alias(self,index=0,*,effective=False):
        old=self.f.caps[index];history=copy.deepcopy(old['source']['history'])
        history[-1 if effective else 0]['body']+=' recaptured ordinary history'
        new=R.capture(self.c.store,self.f.project,old['source']['ticket'],tenant_id='default',history=history)
        i=len(self.f.caps);self.f.caps.append(new);self.f.input_hashes.append(self.f.catalog.admit('input','input-'+str(i),new))
        return old,new,i

    def test_unused_history_recapture_cannot_expose_presealed_task_to_A(self):
        old,new,i=self.alias();self.assertNotEqual(old['source']['history'],new['source']['history'])
        self.assertEqual(old['source']['effective_history'],new['source']['effective_history'])
        self.assertEqual(old['prompt'],new['prompt']);self.assertNotEqual(self.f.input_hashes[0],self.f.input_hashes[i])
        original=copy.deepcopy(self.c.ledger.snapshot(self.c.key)['contract'])
        self.f.plan('recaptured-A',input_index=i,family=self.c.base['training_family']);before=dump_store(self.c.store)
        try:
            with self.assertRaises(L.Conflict):self.f.broker.dispatch('recaptured-A','input-'+str(i))
            self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,0)
            self.assertEqual(self.c.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=?',(self.c.key,)),[])
        finally:
            (self.c.root/'recapture-inputs.json').write_text(json.dumps(dict(original=old,recaptured=new),ensure_ascii=False,indent=2))
            (self.c.root/'recapture-proof.json').write_text(json.dumps(dict(original_contract=original,current_contract=self.c.ledger.snapshot(self.c.key)['contract'],
                original_input_sha256=self.f.input_hashes[0],recaptured_input_sha256=self.f.input_hashes[i],
                effective_messages_equal=R.effective(old,'')['messages']==R.effective(new,'')['messages'],http_calls=self.c.count,
                attempts=self.c.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=?',(self.c.key,))),ensure_ascii=False,indent=2))

    def test_recaptured_holdout_is_refused_for_judge_probe_and_retry_without_new_attempts(self):
        self.f.propose();original=self.c.ledger.snapshot(self.c.key)['contract']
        consumed=self.c.store.q('SELECT * FROM rsi_prepare_holdouts ORDER BY input_hash')
        _,_,i=self.alias()
        for phase in ('judge','probe','retry'):
            self.f.plan('alias-'+phase,phase=phase,input_index=i,family=self.c.base['training_family'])
            before=dump_store(self.c.store)
            with self.subTest(phase=phase),self.assertRaises(L.Conflict):self.f.broker.dispatch('alias-'+phase,'input-'+str(i))
            self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,1)
        self.assertEqual(original,self.c.ledger.snapshot(self.c.key)['contract'])
        self.assertEqual(consumed,self.c.store.q('SELECT * FROM rsi_prepare_holdouts ORDER BY input_hash'))

    def test_same_sealed_task_with_changed_effective_history_is_still_not_training(self):
        old,new,i=self.alias(effective=True)
        self.assertNotEqual(old['prompt'],new['prompt'])
        self.f.plan('changed-question',input_index=i,family=self.c.base['training_family']);before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.f.broker.dispatch('changed-question','input-'+str(i))
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,0)

    def test_distinct_training_task_with_more_history_is_allowed_and_root_cases_do_not_change(self):
        old,new,i=self.alias(index=3,effective=True)
        self.assertNotEqual(old['prompt'],new['prompt']);original=copy.deepcopy(self.c.ledger.snapshot(self.c.key)['contract'])
        self.f.plan('legitimate-A',input_index=i,family=self.c.base['training_family'])
        result=self.f.broker.dispatch('legitimate-A','input-'+str(i))
        self.assertEqual(result['state'],'settled');self.assertEqual(self.c.count,1)
        self.c.adapter.bind_candidate(self.c.key,'legitimate-A')
        _,_,next_index=self.alias(index=3)
        self.f.plan('legitimate-probe',phase='probe',input_index=next_index,family=self.c.base['training_family'])
        self.assertEqual(self.f.broker.dispatch('legitimate-probe','input-'+str(next_index))['state'],'settled')
        self.assertEqual(self.c.count,2);self.assertEqual(original,self.c.ledger.snapshot(self.c.key)['contract'])
        rows=self.c.store.q("SELECT payload FROM rsi_prepare_events WHERE pool=? AND kind='registered_sealed_inputs'",(self.c.key,))
        self.assertEqual(len(rows),1)
        self.assertEqual([v['input_sha256'] for v in json.loads(rows[0]['payload'])['inputs']],[v['input_sha256'] for v in original['holdout_cases']])

    def test_attempted_root_missing_stable_anchor_cannot_backfill_or_replace_exposed_cases(self):
        self.f.propose();original=copy.deepcopy(self.c.ledger.snapshot(self.c.key)['contract'])
        # Defensive simulation of an old/damaged root, not a public mutation.
        self.c.store.x("DELETE FROM rsi_prepare_events WHERE pool=? AND kind='registered_sealed_inputs'",(self.c.key,))
        self.f.plan('old-root-probe',phase='probe');before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.f.broker.dispatch('old-root-probe','input-3')
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(original,self.c.ledger.snapshot(self.c.key)['contract']);self.assertEqual(self.c.count,1)

    def test_distinct_ticketless_training_material_remains_supported(self):
        value=R.capture(self.c.store,self.f.project,None,tenant_id='default',mode='ask',question='independent training material',history=[])
        i=len(self.f.caps);self.f.caps.append(value);self.f.input_hashes.append(self.f.catalog.admit('input','input-'+str(i),value))
        self.f.plan('ticketless-training',input_index=i,family=self.c.base['training_family'])
        result=self.f.broker.dispatch('ticketless-training','input-'+str(i))
        self.assertEqual(result['state'],'settled');self.assertEqual(self.c.count,1)

    def test_missing_original_sealed_capture_denies_instead_of_using_a_recaptured_replacement(self):
        _,_,i=self.alias()
        path=self.f.catalog.files.path/'input-input-0'/'record.json';raw=path.read_bytes();path.unlink()
        self.f.plan('missing-original',input_index=3);before=dump_store(self.c.store)
        with self.assertRaises(OSError):self.f.broker.dispatch('missing-original','input-3')
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,0)
        path.write_bytes(raw);path.chmod(0o600)
        # Restoring the exact original is not replacing it with the alias.
        self.f.plan('restored-original',input_index=3)
        self.assertEqual(self.f.broker.dispatch('restored-original','input-3')['state'],'settled');self.assertEqual(self.c.count,1)


if __name__=='__main__':unittest.main()
