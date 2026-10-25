import copy
import json
import os
from pathlib import Path
import platform
import threading
import tempfile
import stat
import unittest
import uuid
from unittest.mock import patch

import test_rsi_provider_adapter as F
from scripts.rsi import registered_isolation as X, registered_trial as R, trial_preparation as L
from tmh.platform import learning, supervised_process as SP


@unittest.skipUnless(os.name=='posix','original metered provider needs POSIX')
class IsolationLedgerTests(unittest.TestCase):
    def setUp(self):
        self.c=F.ProviderAdapterTests('test_success_full_raw_cache_accounting_and_no_credential_artifact')
        self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.c.dispatch();self.ledger=self.c.ledger;self.key=self.c.key
        self.before=self.ledger.snapshot(self.key,'one')['attempt']
        self.binding='a'*64

    def test_pending_execution_holds_original_max_and_blocks_other_calls(self):
        first=self.ledger.begin_isolation(self.key,'one',self.binding)
        self.assertTrue(first['new_execution'])
        self.assertFalse(self.ledger.begin_isolation(self.key,'one',self.binding)['new_execution'])
        self.assertEqual(self.ledger.inspect(self.key)['totals'],{'calls':1,'billed_tokens':120,'cost_micro_cny':1400})
        with self.assertRaises(L.Conflict):self.c.dispatch('another')
        with self.assertRaises(L.Conflict):self.ledger.begin_isolation(self.key,'one','b'*64)
        self.assertEqual(self.c.count,1)

    def test_verified_result_releases_only_pending_hold_and_keeps_budget(self):
        self.ledger.begin_isolation(self.key,'one',self.binding)
        result=self.ledger.finish_isolation(self.key,'one',self.binding,verified=True,receipt_sha256='c'*64)
        self.assertEqual(result['status'],'evaluated')
        self.assertEqual(self.ledger.inspect(self.key)['totals'],{'calls':1,'billed_tokens':11,'cost_micro_cny':130})
        self.c.dispatch('another');self.assertEqual(self.c.count,2)
        self.assertEqual(self.ledger.finish_isolation(self.key,'one',self.binding,verified=True,receipt_sha256='c'*64),result)
        with self.assertRaises(L.Conflict):self.ledger.finish_isolation(self.key,'one',self.binding,verified=False,receipt_sha256='d'*64)

    def test_unknown_preserves_usage_and_blocks_late_settlement(self):
        self.ledger.begin_isolation(self.key,'one',self.binding)
        self.ledger.finish_isolation(self.key,'one',self.binding,verified=False,receipt_sha256='c'*64)
        now=self.ledger.snapshot(self.key,'one')['attempt']
        self.assertEqual(now['state'],'unknown');self.assertEqual(now['receipt'],self.before['receipt'])
        self.assertEqual(now['receipt_hash'],self.before['receipt_hash'])
        self.assertEqual(self.ledger.inspect(self.key)['totals'],{'calls':1,'billed_tokens':120,'cost_micro_cny':1400})
        with self.assertRaises(L.Conflict):self.c.adapter.reconcile(self.key,'one')
        with self.assertRaises(L.Conflict):self.c.dispatch('another')
        self.assertEqual(self.c.count,1)

    def test_result_write_failure_rolls_back_unknown_and_preserves_pending(self):
        self.ledger.begin_isolation(self.key,'one',self.binding)
        original=self.ledger._event
        def fail(db,key,request,kind,value):
            if kind=='isolation_finished':raise RuntimeError('synthetic final write fault')
            return original(db,key,request,kind,value)
        with patch.object(self.ledger,'_event',side_effect=fail),self.assertRaises(RuntimeError):
            self.ledger.finish_isolation(self.key,'one',self.binding,verified=False,receipt_sha256='c'*64)
        self.assertEqual(self.ledger.snapshot(self.key,'one')['attempt']['state'],'settled')
        self.assertIsNone(self.ledger.isolation_snapshot(self.key,'one')['result'])
        self.assertEqual(self.ledger.inspect(self.key)['totals']['cost_micro_cny'],1400)
        self.ledger.finish_isolation(self.key,'one',self.binding,verified=False,receipt_sha256='c'*64)

    def test_competing_execution_intents_have_one_original_anchor(self):
        barrier=threading.Barrier(2);results=[];errors=[]
        def call():
            try:barrier.wait();results.append(self.ledger.begin_isolation(self.key,'one',self.binding)['new_execution'])
            except BaseException as e:errors.append(type(e).__name__)
        a=threading.Thread(target=call);b=threading.Thread(target=call);a.start();b.start();a.join(4);b.join(4)
        self.assertFalse(a.is_alive());self.assertFalse(b.is_alive());self.assertEqual(errors,[])
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(len(self.c.store.q("SELECT * FROM rsi_prepare_events WHERE kind='isolation_intent'")),1)


class PlatformAdmissionTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='posix','sandbox directory mode contract is POSIX only')
    def test_fresh_internal_sandbox_permissions_are_explicit_under_private_umask(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);folder.chmod(0o700)
            launcher=X.Launcher.__new__(X.Launcher)
            previous=os.umask(0o077)
            try:
                with patch.object(X,'seal'):
                    root=launcher._sandbox(folder,'candidate',b'{}')
            finally:os.umask(previous)
            self.assertEqual(stat.S_IMODE(folder.stat().st_mode),0o700)
            for p in [root,*root.iterdir()]:self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o755)

    def test_nonroot_or_nonlinux_rejects_before_any_filesystem_write(self):
        with patch.object(X,'supported',return_value=False),patch.object(X,'private_directory',side_effect=AssertionError('must not touch')),self.assertRaises(L.Conflict):
            X.Launcher(None,None,None,Path('/not-an-admitted-path'))


@unittest.skipUnless(platform.system()=='Linux' and hasattr(os,'geteuid') and os.geteuid()==0 and os.environ.get('RSI_RUN_KERNEL_FIXTURE')=='1',
                     'explicit root-owned temporary Linux kernel fixture only')
class RegisteredIsolationKernelTests(unittest.TestCase):
    def setUp(self):
        self.c=F.ProviderAdapterTests('test_success_full_raw_cache_accounting_and_no_credential_artifact')
        self.c.setUp();self.addCleanup(self.c.doCleanups)
        (self.c.root/'isolation-test-identity.json').write_text(json.dumps({'test':self.id()}))
        learning.schema(self.c.store);(self.c.root/'project').mkdir()
        project=self.c.store.add_project('APP','固定文本交付合成项目',str(self.c.root/'project'))
        ticket=self.c.store.create_ticket(project['id'],'complete native text',body='原始完整任务\r\n😀')
        self.cap=R.capture(self.c.store,project,ticket,tenant_id='fixture-tenant',history=[{'role':'user','body':'全部历史\r\n😀'}])
        catalogs=[]
        for name in ('catalog','execution-catalog','oracle-catalog'):
            p=self.c.root/name;p.mkdir(mode=0o700);catalog=R.Catalog(p);self.addCleanup(catalog.close);catalogs.append(catalog)
        self.public,self.executions,self.oracles=catalogs
        ih=self.public.admit('input','public-one',self.cap)
        self.plan={'schema':R.VERSION,'kind':'fixture-provider-only','input_id':'public-one','input_sha256':ih,
            'root_pool':self.c.key,'contract_sha256':L.digest(self.c.ledger.snapshot(self.c.key)['contract']),
            'request_id':'delivery-one','phase':'propose','broker_sha256':R.CODE_SHA256,'policy':'exact public delivery','policy_sha256':R.sha(b'exact public delivery')}
        ph=self.public.admit('plan','plan-one',self.plan)
        self.oracle={'expected_blocks':copy.deepcopy(self.c.response['content']),'secret_canary':uuid.uuid4().hex+uuid.uuid4().hex}
        oh=self.oracles.admit('input','plan-one',self.oracle)
        self.execution={'schema':X.VERSION,'plan_id':'plan-one','input_id':'public-one','plan_sha256':ph,'input_sha256':ih,
            'root_pool':self.c.key,'contract_sha256':self.plan['contract_sha256'],'bundle_sha256':L.digest(X.bundle()),
            'oracle_sha256':oh,'operation':'deliver','timeout_ms':3000}
        root=self.c.root/'isolated-executions';root.mkdir(mode=0o700)
        self.launcher=X.Launcher(R.Broker(self.c.adapter,self.public),self.executions,self.oracles,root)

    def admit(self,**updates):
        self.execution.update(updates);self.executions.admit('plan','plan-one',self.execution)

    def dispatch(self,**kwargs):return self.launcher.dispatch('plan-one','public-one',**kwargs)

    def original_receipts(self,result):
        folder=self.launcher.root/result['execution_id'];out={}
        for role in ('candidate','evaluator'):
            path=folder/(role+'-supervised')
            if not path.exists():continue
            receipt=SP.read_receipt(path,{'token':result['execution_id'],'run_id':'delivery-one','data_dir':str(self.launcher.root)})
            self.assertTrue(receipt['cleanup']['complete']);self.assertTrue(receipt['cleanup']['reaped']);self.assertFalse(receipt['cleanup']['remaining_group'])
            with self.assertRaises(ProcessLookupError):os.killpg(receipt['pgid'],0)
            raw=(path/'output.bin').read_bytes();self.assertNotIn(self.oracle['secret_canary'].encode(),raw);out[role]=receipt
        return out

    def test_actual_two_identities_public_input_and_independent_oracle(self):
        self.admit();result=self.dispatch();(self.c.root/'isolation-result.json').write_text(L.encoded(result))
        self.assertEqual(result['isolated_execution'],'evaluated');self.assertIs(result['verdict'],True)
        self.assertNotEqual(result['candidate_uid'],result['evaluator_uid']);self.assertNotEqual(result['candidate_uid'],os.getuid())
        self.assertFalse(result['production_equivalent']);self.assertFalse(result['rsi_qualified'])
        receipts=self.original_receipts(result);self.assertEqual(set(receipts),{'candidate','evaluator'})
        folder=self.launcher.root/result['execution_id'];sent=json.loads((folder/'candidate-root/input/public.json').read_text())
        self.assertEqual(sent['capture'],self.cap);self.assertEqual(sent['native_response'],self.c.response)
        self.assertNotIn('oracle',sent);self.assertNotIn(self.oracle['secret_canary'],L.encoded(sent))
        self.assertFalse(self.dispatch()['new_execution']);self.assertEqual(self.c.count,1)

    def test_wrong_oracle_is_real_failed_verdict_not_execution_success(self):
        p=self.c.root/'oracle-catalog/input-plan-one/record.json';oracle=dict(self.oracle,expected_blocks=[{'type':'text','text':'deliberately different'}])
        p.write_text(L.encoded(oracle));p.chmod(0o600);self.admit(oracle_sha256=R.sha(p.read_bytes()))
        result=self.dispatch();self.assertEqual(result['oracle_evaluation'],'completed');self.assertIs(result['verdict'],False)
        self.original_receipts(result);self.assertEqual(self.c.count,1)

    def test_missing_changed_and_arbitrary_command_admission_zero_http(self):
        self.admit(command=['/bin/true'])
        with self.assertRaises(FileNotFoundError):self.launcher.dispatch('missing','public-one')
        with self.assertRaises(ValueError):self.dispatch()
        self.assertEqual(self.c.count,0);self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['calls'],0)

    def test_changed_input_id_or_source_is_denied_before_http(self):
        self.admit()
        with self.assertRaises(L.Conflict):self.launcher.dispatch('plan-one','unregistered-input')
        record=self.c.root/'catalog/input-public-one/record.json'
        with record.open('ab') as stream:stream.write(b'\n')
        with self.assertRaises(L.Conflict):self.dispatch()
        self.assertEqual(self.c.count,0)

    def test_real_candidate_timeout_preserves_max_hold_and_never_reruns(self):
        self.admit(operation='hang');result=self.dispatch()
        self.assertEqual(result['isolated_execution'],'unknown');self.assertEqual(result['candidate_returncode'],124)
        self.assertIsNone(result['evaluator_returncode']);self.original_receipts(result)
        self.assertEqual(self.c.ledger.inspect(self.c.key)['totals'],{'calls':1,'billed_tokens':120,'cost_micro_cny':1400})
        self.assertTrue(self.c.ledger.inspect(self.c.key)['blocked']);self.assertFalse(self.dispatch()['new_execution']);self.assertEqual(self.c.count,1)

    def test_ready_barrier_cancellation_preserves_unknown_and_reaps(self):
        self.admit(operation='hang');root=self.launcher.root
        class CancelAtReady:
            def is_set(self):
                for p in root.glob('*/candidate-supervised/output.bin'):
                    if b'CANDIDATE_READY' in p.read_bytes():return True
                return False
        result=self.dispatch(cancel_event=CancelAtReady())
        self.assertEqual(result['isolated_execution'],'unknown');self.assertEqual(result['candidate_returncode'],130)
        self.original_receipts(result);self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['cost_micro_cny'],1400)
        self.assertFalse(self.dispatch()['new_execution']);self.assertEqual(self.c.count,1)
