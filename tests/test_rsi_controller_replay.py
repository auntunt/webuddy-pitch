"""Completed replay using real ordinary SP/SQLite, not a privileged Session.

Root ownership admission alone is stubbed. Real Catalog/capture/receipt/event
bindings execute; roles are ordinary local processes, not UID isolation proof.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.rsi import controller_channel as C, registered_isolation as X, registered_trial as R, trial_preparation as L
from tmh.platform import learning, supervised_process as SP
from tmh.platform.store import Store


@unittest.skipUnless(os.name=='posix','original process supervision requires POSIX')
class CompletedReplayTests(unittest.TestCase):
    def setUp(self):
        retained=os.environ.get('RSI_REPLAY_EVIDENCE_DIR')
        if retained:self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=retained))
        else:
            temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.store=Store(self.root/'fixture.sqlite');self.addCleanup(self.store.db.close)
        self.ledger=L.Ledger(self.store);learning.schema(self.store)
        contract={'schema':L.VERSION,'tenant_id':'ordinary-replay','project_id':1,'root_family':'one-root','application_commit':'a'*40,
          'candidate_sha256':'b'*64,'baseline_sha256':'c'*64,'training_family':'A','followup_family':'D',
          'holdout_cases':[{'input_sha256':R.sha(str(i).encode()),'source_family':f} for i,f in enumerate(['B','B','C'])],
          'model':{'provider':'synthetic','requested_model':'synthetic','response_model':'synthetic-response'},
          'price':{'reference_sha256':'d'*64,'input_micro_cny_per_token':7,'cached_micro_cny_per_token':7,'output_micro_cny_per_token':11},
          'limits':{'calls':8,'billed_tokens':1000,'cost_micro_cny':5000,'deadline_us':time.time_ns()//1000+120000000}}
        self.key=self.ledger.create(contract);self.request='original-one'
        (self.root/'project').mkdir();project=self.store.add_project('APP','合成重放',str(self.root/'project'))
        ticket=self.store.create_ticket(project['id'],'complete replay',body='全文\r\n😀')
        cap=R.capture(self.store,project,ticket,tenant_id=contract['tenant_id'],history=[{'role':'user','body':'完整历史'}])
        cats=[]
        for name in ('public','execution','oracle','controller'):
            root=self.root/name;root.mkdir(mode=0o700);cat=R.Catalog(root,trusted_uid=os.getuid());cats.append(cat);self.addCleanup(cat.close)
        public,execution,oracle,controller=cats;ih=public.admit('input','input-one',cap)
        self.plan={'schema':R.VERSION,'kind':'fixture-provider-only','input_id':'input-one','input_sha256':ih,'root_pool':self.key,
                   'contract_sha256':L.digest(contract),'request_id':self.request,'phase':'propose','broker_sha256':R.CODE_SHA256,'policy':'fixed','policy_sha256':R.sha(b'fixed')}
        ph=public.admit('plan','plan-one',self.plan);oh=oracle.admit('input','plan-one',{'expected_blocks':[],'secret_canary':'e'*64})
        eh=execution.admit('plan','plan-one',{'schema':X.VERSION,'plan_id':'plan-one','input_id':'input-one','plan_sha256':ph,'input_sha256':ih,
              'root_pool':self.key,'contract_sha256':L.digest(contract),'bundle_sha256':L.digest(X.bundle()),'oracle_sha256':oh,'operation':'deliver','timeout_ms':3000})
        self.ledger.reserve(self.key,self.request,'propose',10,5);self.intent=self.ledger.intent(self.key,self.request)['intent']
        self.ledger.settle(self.key,self.request,self.intent,{'provider_request_id':'synthetic','response_model':'synthetic-response','input_tokens':4,
            'cached_input_tokens':0,'output_tokens':2,'provider_charge_micro_cny':None,'raw_response_sha256':R.sha(b'not a real provider')})
        attempt=self.ledger.snapshot(self.key,self.request)['attempt']
        self.binding={'execution_sha256':eh,'plan_sha256':ph,'input_sha256':ih,'oracle_sha256':oh,'provider_intent':self.intent,
                      'provider_receipt_sha256':attempt['receipt_hash'],'root_contract':L.digest(contract)}
        self.launcher=X.Launcher.__new__(X.Launcher);self.launcher.catalog=execution;self.launcher.oracles=oracle;self.launcher.ledger=self.ledger
        self.launcher.broker=SimpleNamespace(catalog=public,dispatch=Mock(side_effect=AssertionError('no provider dispatch')))
        self.launcher._code_current=Mock();self.launcher._lease=Mock(side_effect=AssertionError('no role lease'))
        self.launcher.root=self.root/'isolated';self.launcher.root.mkdir()
        item=self.ledger.begin_isolation(self.key,self.request,L.digest(self.binding));eid=item['anchor']['execution_id']
        self.folder=self.launcher.root/eid;self.folder.mkdir();(self.folder/'binding.json').write_text(L.encoded(self.binding))
        owner={'token':eid,'run_id':self.request,'data_dir':str(self.launcher.root)}
        digests={role:self.ordinary(self.folder/(role+'-supervised'),owner,role+' full output\r\n😀') for role in ('candidate','evaluator')}
        self.iso={'schema':X.VERSION,'binding_sha256':L.digest(self.binding),'execution_id':eid,'isolated_execution':'evaluated','oracle_evaluation':'completed',
            'verdict':True,'candidate_uid':X.CANDIDATE_UID,'evaluator_uid':X.EVALUATOR_UID,'candidate_returncode':0,'evaluator_returncode':0,
            'candidate_receipt_sha256':digests['candidate'],'evaluator_receipt_sha256':digests['evaluator'],'production_equivalent':False,'rsi_qualified':False,'production_entry':False}
        (self.folder/'execution-result.json').write_text(L.encoded(self.iso));self.ledger.finish_isolation(self.key,self.request,L.digest(self.binding),verified=True,receipt_sha256=L.digest(self.iso))
        self.control={'schema':C.VERSION,'plan_id':'plan-one','input_id':'input-one','channel_sha256':C.LOADED,'execution_plan_sha256':eh,'public_plan_sha256':ph,
            'input_sha256':ih,'root_pool':self.key,'root_contract_sha256':L.digest(contract),'operation':'normal','controller_timeout_ms':8000,'max_requests':128}
        ch=controller.admit('plan','plan-one',self.control);binding=L.digest([ch,eh,ph,ih,L.digest(contract),C.LOADED]);nonce='one-controller'
        self.session=C.Session.__new__(C.Session);self.session.launcher=self.launcher;self.session.catalog=controller;self.session.ledger=self.ledger
        self.session.root=self.root/'sessions';self.session.root.mkdir();self.session._current=Mock();self.session._lease=Mock(side_effect=AssertionError('no controller lease'))
        folder=self.session.root/nonce;folder.mkdir();self.controller_folder=folder
        receipt=self.ordinary(folder/'controller-supervised',{'token':nonce,'run_id':self.request,'data_dir':str(self.session.root)},'ordinary complete controller')
        self.record={'schema':C.VERSION,'binding_sha256':binding,'nonce':nonce,'provider_intent':self.intent,'controller_receipt_sha256':receipt,
              'public':dict(C.public_status(self.iso,stage='reported'),controller_state='finished'),'job_error_class':'','channel_error_code':''}
        self.record_path=folder/'result.json';self.record_path.write_text(L.encoded(self.record))
        with learning.transaction(self.store) as db:
            self.ledger._event(db,self.key,'','controller_intent',{'request_id':self.request,'binding_sha256':binding,'nonce':nonce})
            self.ledger._event(db,self.key,'','controller_finished',{'request_id':self.request,'nonce':nonce,'receipt_sha256':R.sha(self.record_path.read_bytes())})
        self.before=self.rows();self.changes=self.store.db.total_changes
        self.addCleanup(self.assert_read_only)
        self.launcher.dispatch=Mock(side_effect=AssertionError('replay cannot call dispatch'))
        no_spawn=patch.object(SP,'run_supervised',side_effect=AssertionError('replay cannot spawn'));no_spawn.start();self.addCleanup(no_spawn.stop)

    def ordinary(self,folder,owner,text):
        result=SP.run_supervised([sys.executable,'-B','-c','print('+repr(text)+')'],folder=folder,owner=owner,cwd=self.root,
                                env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},timeout=3)
        self.assertEqual(result.returncode,0);receipt=SP.read_receipt(folder,owner)
        self.assertTrue(receipt['cleanup']['complete'])
        with self.assertRaises(ProcessLookupError):os.killpg(receipt['pgid'],0)
        return R.sha((folder/'supervisor-result.json').read_bytes())

    def rows(self):return {name:self.store.q('SELECT * FROM '+name+' ORDER BY rowid') for name in ('rsi_prepare_pools','rsi_prepare_attempts','rsi_prepare_holdouts','rsi_prepare_events')}

    def assert_read_only(self):
        self.assertEqual(self.rows(),self.before);self.assertEqual(self.store.db.total_changes,self.changes)
        self.launcher.broker.dispatch.assert_not_called();self.launcher.dispatch.assert_not_called();self.launcher._lease.assert_not_called();self.session._lease.assert_not_called()

    def replay(self):
        return self.session.run('plan-one','input-one')

    def test_intact_completed_cache_replays_and_parallel_reads_never_dispatch(self):
        self.assertEqual(self.replay(),dict(self.record['public'],new_controller=False))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda unused:self.replay(),range(8)))
        self.assertTrue(all(r==dict(self.record['public'],new_controller=False) for r in results))

    def test_each_role_original_output_plan_and_result_damage_or_loss_rejected(self):
        for role in ('candidate','evaluator'):
            for name in ('output.bin','supervisor.json','supervisor-result.json'):
                path=self.folder/(role+'-supervised')/name;raw=path.read_bytes()
                for damage in ('append','missing'):
                    with self.subTest(role=role,file=name,damage=damage):
                        try:
                            if damage=='append':path.write_bytes(raw+b'BROKEN')
                            else:path.unlink()
                            with self.assertRaises((OSError,ValueError)):self.replay()
                        finally:path.write_bytes(raw)

    def test_execution_binding_and_result_original_damage_or_loss_rejected(self):
        for name in ('binding.json','execution-result.json'):
            path=self.folder/name;raw=path.read_bytes()
            for damage in ('append','missing','different_binding'):
                with self.subTest(file=name,damage=damage):
                    try:
                        if damage=='append':path.write_bytes(raw+b'BROKEN')
                        elif damage=='missing':path.unlink()
                        else:
                            value=json.loads(raw);value['binding_sha256' if name=='execution-result.json' else 'provider_intent']='0'*64;path.write_text(L.encoded(value))
                        with self.assertRaises((OSError,ValueError)):self.replay()
                    finally:path.write_bytes(raw)

    def test_parallel_completed_cache_reads_after_damage_all_reject(self):
        path=self.folder/'evaluator-supervised/output.bin';path.write_bytes(path.read_bytes()+b'BROKEN')
        def read(unused):
            try:self.replay()
            except (OSError,ValueError):return 'rejected'
            return 'accepted'
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:self.assertEqual(list(pool.map(read,range(8))),['rejected']*8)

    def test_inner_dispatch_completed_branch_reuses_read_only_validation(self):
        self.assertEqual(X.Launcher.dispatch(self.launcher,'plan-one','input-one'),dict(self.iso,new_execution=False))
        path=self.folder/'evaluator-supervised/output.bin';path.unlink()
        with self.assertRaises((OSError,ValueError)):X.Launcher.dispatch(self.launcher,'plan-one','input-one')

    def seed_cache(self,change):
        # Construct an internally hashed but misbound trusted cache, then check
        # readback itself changes no history. This is not a controller write.
        change(self.record);self.record_path.write_text(L.encoded(self.record))
        event=self.store.one("SELECT id,payload FROM rsi_prepare_events WHERE kind='controller_finished'")
        payload=json.loads(event['payload']);payload['receipt_sha256']=R.sha(self.record_path.read_bytes())
        self.store.x('UPDATE rsi_prepare_events SET payload=?,payload_hash=? WHERE id=?',(L.encoded(payload),L.digest(payload),event['id']))
        self.before=self.rows();self.changes=self.store.db.total_changes

    def test_cached_provider_intent_mismatch_cannot_reuse_original(self):
        self.seed_cache(lambda record:record.update(provider_intent='another-original-intent'))
        with self.assertRaises(ValueError):self.replay()

    def test_cached_verdict_must_match_original_independent_result(self):
        self.seed_cache(lambda record:record['public'].update(verdict=False))
        with self.assertRaises(ValueError):self.replay()

    def test_cached_success_without_original_isolation_anchor_rejected(self):
        # Seed missing original history before readback; never repair it.
        self.store.x("DELETE FROM rsi_prepare_events WHERE kind IN ('isolation_intent','isolation_finished')")
        self.before=self.rows();self.changes=self.store.db.total_changes
        with self.assertRaises(ValueError):self.replay()

    def test_unknown_before_provider_intent_replays_without_inventing_attempt(self):
        self.store.x("DELETE FROM rsi_prepare_events WHERE kind IN ('isolation_intent','isolation_finished') OR request_id=?",(self.request,))
        self.store.x('DELETE FROM rsi_prepare_attempts WHERE request_id=?',(self.request,))
        def unknown(record):
            record['provider_intent']=None;record['public'].update(state='unknown',verdict=None)
        self.seed_cache(unknown)
        self.assertEqual(self.replay(),dict(self.record['public'],new_controller=False))
        self.assertIsNone(self.store.one('SELECT * FROM rsi_prepare_attempts'))
