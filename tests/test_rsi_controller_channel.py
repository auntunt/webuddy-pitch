import json
import os
from pathlib import Path
import platform
import struct
import threading
import time
import unittest
from unittest.mock import patch

import test_rsi_registered_isolation as I
from scripts.rsi import controller_channel as C, registered_trial as R, registered_isolation as X, trial_preparation as L
from tmh.platform import supervised_process as SP


class ProjectionTests(unittest.TestCase):
    def test_projection_contains_only_allowed_state_not_private_fields_or_digests(self):
        value={'schema':X.VERSION,'isolated_execution':'evaluated','oracle_evaluation':'completed','verdict':False,
               'candidate_returncode':0,'evaluator_returncode':0,'production_equivalent':False,'rsi_qualified':False,
               'oracle':'PRIVATE','oracle_sha256':'a'*64,'binding_sha256':'b'*64,'execution_id':'c'*64,'error':'PRIVATE'}
        result=C.public_status(value)
        self.assertEqual(result,{'state':'evaluated','verdict':False,'cancel_requested':False,'stage':'idle'})
        for field in ('candidate_returncode','evaluator_returncode'):
            bad=dict(value);bad[field]=False
            self.assertEqual(C.public_status(bad)['state'],'unknown')
        self.assertNotIn('PRIVATE',L.encoded(result));self.assertNotIn('a'*64,L.encoded(result))

    def test_invalid_request_never_calls_privileged_work_or_returns_error_details(self):
        session=C.Session.__new__(C.Session);session.plan_id='plan-one';session.input_id='public-one';session.cache={}
        valid={'action':'run','plan_id':'plan-one','input_id':'public-one','request_id':'one'}
        bad=[None,[],dict(valid,command=['id']),dict(valid,uid=0),dict(valid,action='oracle'),dict(valid,input_id='private-oracle'),dict(valid,request_id='../private')]
        with patch.object(session,'_current',side_effect=AssertionError('must reject before privileged work')):
            for body in bad:
                with self.subTest(body=body):self.assertEqual(session._handle(body),{'error':'denied'})

    def test_unsupported_platform_or_uid_does_not_create_paths(self):
        with patch.object(X,'supported',return_value=False),patch.object(X,'private_directory',side_effect=AssertionError('must not touch')),self.assertRaises(L.Conflict):
            C.Session(None,None,Path('/not-admitted'))


@unittest.skipUnless(os.name=='posix','FIFO framing requires POSIX')
class FrameTests(unittest.TestCase):
    def setUp(self):
        self.read,self.write=os.pipe();os.set_blocking(self.read,False);os.set_blocking(self.write,False)
        self.addCleanup(os.close,self.read);self.addCleanup(os.close,self.write)

    def test_multichunk_unicode_and_null_public_input_roundtrip_losslessly(self):
        frames=C.Frames(self.read,self.write,deadline=time.monotonic()+2,stop=threading.Event(),limit=C.MAX_PUBLIC)
        value={'full':'全文\r\n 😀 '*9000,'null':None,'history':[{'role':'user','body':'完整尾部\r\n'}]};errors=[]
        def send():
            try:frames.send(value)
            except BaseException as error:errors.append(type(error).__name__)
        thread=threading.Thread(target=send);thread.start()
        try:self.assertEqual(frames.receive(),value)
        finally:thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])

    def test_oversized_length_rejects_before_body_read_or_allocation(self):
        os.write(self.write,struct.pack('!I',C.MAX_REQUEST+1))
        frames=C.Frames(self.read,self.write,deadline=time.monotonic()+1,stop=threading.Event(),limit=C.MAX_REQUEST)
        with self.assertRaises(ValueError):frames.receive()
        self.assertEqual(len(frames.buffer),4)

    def test_duplicate_json_fields_are_not_silently_normalized(self):
        raw=b'{"action":"input","action":"run"}';os.write(self.write,struct.pack('!I',len(raw))+raw)
        frames=C.Frames(self.read,self.write,deadline=time.monotonic()+1,stop=threading.Event(),limit=C.MAX_REQUEST)
        with self.assertRaises(ValueError):frames.receive()


@unittest.skipUnless(platform.system()=='Linux' and hasattr(os,'geteuid') and os.geteuid()==0 and os.environ.get('RSI_RUN_KERNEL_FIXTURE')=='1',
                     'explicit temporary root-owned Linux FIFO/UID fixture')
class ControllerKernelTests(unittest.TestCase):
    def setUp(self):
        self.base=I.RegisteredIsolationKernelTests('test_actual_two_identities_public_input_and_independent_oracle')
        self.base.setUp();self.addCleanup(self.base.doCleanups);self.c=self.base.c
        (self.c.root/'controller-test-identity.json').write_text(json.dumps({'test':self.id()}))
        path=self.c.root/'controller-catalog';path.mkdir(mode=0o700);self.catalog=R.Catalog(path);self.addCleanup(self.catalog.close)
        root=self.c.root/'controller-sessions';root.mkdir(mode=0o700)
        self.session=C.Session(self.base.launcher,self.catalog,root)

    def admit(self,operation='normal',worker_operation='deliver',**updates):
        self.base.admit(operation=worker_operation)
        self.contract={'schema':C.VERSION,'plan_id':'plan-one','input_id':'public-one','channel_sha256':C.LOADED,
             'execution_plan_sha256':self.base.executions.load('plan','plan-one')[1],'public_plan_sha256':self.base.public.load('plan','plan-one')[1],
             'input_sha256':self.base.public.load('input','public-one')[1],'root_pool':self.c.key,
             'root_contract_sha256':L.digest(self.c.ledger.snapshot(self.c.key)['contract']),'operation':operation,
             'controller_timeout_ms':C.LIMIT_MS,'max_requests':C.MAX_REQUESTS}
        self.contract.update(updates);self.catalog.admit('plan','plan-one',self.contract)

    def run_session(self):
        result=self.session.run('plan-one','public-one');(self.c.root/'controller-public-result.json').write_text(L.encoded(result))
        return result

    def controller_receipt(self):
        record=PJSON(self.session.last_folder/'result.json');path=self.session.last_folder/'controller-supervised'
        receipt=SP.read_receipt(path,{'token':record['nonce'],'run_id':'delivery-one','data_dir':str(self.session.root)})
        self.assertTrue(receipt['cleanup']['complete']);self.assertFalse(receipt['cleanup']['remaining_group']);self.assertTrue(receipt['cleanup']['reaped'])
        with self.assertRaises(ProcessLookupError):os.killpg(receipt['pgid'],0)
        raw=(path/'output.bin').read_bytes();channel=(self.session.last_folder/'channel.jsonl').read_bytes()
        private=[self.base.oracle['secret_canary'],self.base.execution['oracle_sha256'],self.contract['execution_plan_sha256'],record['binding_sha256']]
        for value in private:self.assertNotIn(value.encode(),raw+channel)
        return receipt,raw

    def assert_unknown_root(self):
        self.assertTrue(self.c.ledger.inspect(self.c.key)['blocked'])
        self.assertEqual(self.c.ledger.inspect(self.c.key)['totals'],{'calls':1,'billed_tokens':120,'cost_micro_cny':1400})
        self.assertEqual(self.c.count,1)

    def test_nonroot_controller_gets_full_public_input_and_only_public_verdict(self):
        self.admit();result=self.run_session();self.assertEqual(result['state'],'evaluated');self.assertIs(result['verdict'],True)
        self.assertEqual(result['controller_state'],'finished');self.assertFalse(result['cancel_requested'])
        receipt,raw=self.controller_receipt();client=json.loads(raw)
        self.assertEqual(client['checks']['uid'],508103);self.assertEqual(client['checks']['gid'],508103)
        self.assertTrue(all(value is True for key,value in client['checks'].items() if key not in ('uid','gid')))
        self.assertEqual(client['public_input'],self.base.cap)
        self.assertIn({'error':'request_conflict'},client['responses'])
        self.assertFalse(self.run_session()['new_controller']);self.assertEqual(self.c.count,1)
        self.assertEqual(len(self.c.store.q("SELECT * FROM rsi_prepare_events WHERE kind='controller_intent'")),1)

    def test_parameter_tampering_and_private_detail_requests_never_dispatch(self):
        self.admit(operation='tamper');result=self.run_session()
        self.assertEqual(result['state'],'not_started');self.assertEqual(self.c.count,0)
        self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['calls'],0)
        receipt,raw=self.controller_receipt();client=json.loads(raw)
        self.assertEqual(sum(value=={'error':'denied'} for value in client['responses']),7)

    def test_forged_controller_success_does_not_create_root_success(self):
        self.admit(operation='forge');result=self.run_session();self.assertEqual(result['state'],'not_started');self.assertIsNone(result['verdict'])
        self.assertEqual(self.c.count,0);receipt,raw=self.controller_receipt();self.assertEqual(json.loads(raw)['final']['state'],'evaluated')

    def test_private_error_content_and_hash_are_not_projected(self):
        self.admit(operation='error')
        message=self.base.oracle['secret_canary']+self.base.execution['oracle_sha256']
        with patch.object(self.base.launcher,'dispatch',side_effect=RuntimeError(message)):
            result=self.run_session()
        self.assertEqual(result['state'],'unknown');self.assertIsNone(result['verdict']);self.assertEqual(self.c.count,0)
        self.controller_receipt();self.assertFalse(self.run_session()['new_controller'])

    def test_controller_ready_cancel_keeps_unknown_and_original_max(self):
        self.admit(operation='cancel',worker_operation='hang');result=self.run_session()
        self.assertEqual(result['state'],'unknown');self.assertTrue(result['cancel_requested']);self.assertEqual(result['controller_state'],'finished')
        self.controller_receipt();self.assert_unknown_root()
        item=self.c.ledger.isolation_snapshot(self.c.key,'delivery-one');folder=self.base.launcher.root/item['anchor']['execution_id']
        candidate=SP.read_receipt(folder/'candidate-supervised');self.assertEqual(candidate['returncode'],130)
        self.assertFalse(self.run_session()['new_controller']);self.assertEqual(self.c.count,1)

    def test_controller_loss_after_ready_cancels_privileged_job_without_resend(self):
        self.admit(operation='exit',worker_operation='hang');result=self.run_session()
        self.assertEqual(result['state'],'unknown');self.assertEqual(result['controller_state'],'unknown')
        receipt,raw=self.controller_receipt();self.assertNotEqual(receipt['returncode'],0);self.assert_unknown_root()
        item=self.c.ledger.isolation_snapshot(self.c.key,'delivery-one');folder=self.base.launcher.root/item['anchor']['execution_id']
        self.assertEqual(SP.read_receipt(folder/'candidate-supervised')['returncode'],130)
        self.assertFalse(self.run_session()['new_controller']);self.assertEqual(self.c.count,1)

    def test_controller_watchdog_does_not_mask_original_candidate_timeout(self):
        self.admit(operation='hang',worker_operation='hang');result=self.run_session()
        self.assertEqual(result['state'],'unknown');receipt,raw=self.controller_receipt();self.assertEqual(receipt['returncode'],124)
        self.assert_unknown_root();item=self.c.ledger.isolation_snapshot(self.c.key,'delivery-one');folder=self.base.launcher.root/item['anchor']['execution_id']
        candidate=SP.read_receipt(folder/'candidate-supervised');self.assertEqual(candidate['returncode'],124)
        self.assertLess(candidate['elapsed_seconds'],receipt['elapsed_seconds'])
        self.assertFalse(self.run_session()['new_controller']);self.assertEqual(self.c.count,1)

    def test_completed_cache_revalidates_damaged_original_role_evidence(self):
        self.admit();result=self.run_session();self.assertEqual(result['state'],'evaluated')
        self.controller_receipt()
        item=self.c.ledger.isolation_snapshot(self.c.key,'delivery-one');folder=self.base.launcher.root/item['anchor']['execution_id']
        tables=('rsi_prepare_pools','rsi_prepare_attempts','rsi_prepare_holdouts','rsi_prepare_events')
        before={name:self.c.store.q('SELECT * FROM '+name+' ORDER BY rowid') for name in tables}
        changes=self.c.store.db.total_changes
        with patch.object(self.base.launcher,'dispatch',side_effect=AssertionError('replay cannot dispatch')),patch.object(SP,'run_supervised',side_effect=AssertionError('replay cannot spawn')):
            for role in ('candidate','evaluator'):
                path=folder/(role+'-supervised')/'output.bin';raw=path.read_bytes()
                for missing in (False,True):
                    with self.subTest(role=role,missing=missing):
                        try:
                            if missing:path.unlink()
                            else:path.write_bytes(raw+b'CORRUPTED ORIGINAL')
                            with self.assertRaises((OSError,ValueError)):self.run_session()
                        finally:path.write_bytes(raw)
                self.assertEqual(self.run_session()['state'],'evaluated')
        self.assertEqual({name:self.c.store.q('SELECT * FROM '+name+' ORDER BY rowid') for name in tables},before)
        self.assertEqual(self.c.store.db.total_changes,changes);self.assertEqual(self.c.count,1)

    def test_unregistered_or_changed_contract_refuses_before_controller_spawn(self):
        self.admit(command=['id'])
        with self.assertRaises(FileNotFoundError):self.session.run('missing','public-one')
        with self.assertRaises(ValueError):self.run_session()
        self.assertEqual(self.c.count,0);self.assertEqual(list(self.session.root.iterdir()),[])


def PJSON(path):return json.loads(path.read_bytes())
