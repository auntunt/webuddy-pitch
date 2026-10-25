"""Real production prompt + registered IDs + controlled native HTTP, no sandbox claim."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import test_rsi_provider_adapter as F
from scripts.rsi import registered_trial as R
from scripts.rsi import trial_preparation as L
from tmh.platform import agents, learn, learning, store as S, supervised_process as SP


class ProductionCaptureTests(unittest.TestCase):
    def setUp(self):
        missing=object();old=getattr(agents._CTX_META,'meta',missing)
        def restore():
            if old is missing:agents._CTX_META.__dict__.pop('meta',None)
            else:agents._CTX_META.meta=old
        self.addCleanup(restore)
        retained=os.environ.get('RSI_CAPTURE_EVIDENCE_DIR')
        if retained:self.root=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=retained))
        else:
            self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.root.chmod(0o700);(self.root/'project').mkdir()
        self.store=S.Store(self.root/'fixture.db');self.addCleanup(self.store.db.close)
        learning.schema(self.store)
        self.project=self.store.add_project('APP','实际提示词合成项目',str(self.root/'project'))
        self.ticket=self.store.create_ticket(self.project['id'],'transaction callback',body='完整工单正文 transaction callback',type='bug')
        self.history=[{'role':'user' if i%2==0 else 'assistant','body':'history-%d\r\n  尾部😀'%i} for i in range(9)]

    def capture(self,**kwargs):
        value=R.capture(self.store,self.project,self.ticket,tenant_id='fixture-tenant',history=self.history,**kwargs)
        (self.root/'captured-input.json').write_text(L.encoded(value))
        return value

    def test_real_factory_and_original_window_with_full_source_history(self):
        old=[{'mode':'prior-thread-sentinel'}];agents._CTX_META.meta=old
        result=self.capture()
        self.assertIs(agents._CTX_META.meta,old)
        self.assertEqual(result['source']['history'],self.history)
        self.assertEqual(result['source']['effective_history'],self.history[-6:])
        self.assertNotIn('history-0',result['prompt']);self.assertIn('history-8',result['prompt'])
        self.assertIn('完整工单正文',result['prompt']);self.assertIn('transaction callback',result['prompt'])
        self.assertTrue(result['production_factory_used']);self.assertFalse(result['production_equivalent'])
        self.assertTrue(result['equivalence_gaps']);self.assertTrue(result['source']['context'])

    def test_pair_permits_only_policy_with_lossless_unicode(self):
        cap=self.capture(question='末尾\r\n😀')
        a=R.effective(cap,'base policy');b=R.effective(cap,'candidate policy\r\n  ')
        self.assertTrue(R.assert_pair(a,b));self.assertEqual(a['messages'][0]['content'],cap['prompt'])
        for field,value in [('messages',[{'role':'user','content':'truncated'}]),('common_sha256','0'*64),('tools',['Read']),('production_equivalent',True)]:
            bad=copy.deepcopy(b);bad[field]=value
            with self.subTest(field=field),self.assertRaises(L.Conflict):R.assert_pair(a,bad)
        b['equivalence_gaps'].clear();self.assertTrue(R.effective(cap,'new')['equivalence_gaps'])

    def test_real_selector_and_renderer_preserve_selected_long_lesson(self):
        from tmh.platform import lesson_input as I
        text='事务完整尾部\r\n  😀'+('完整资料'*3000)
        self.ticket=self.store.update_ticket(self.ticket['id'],links={'flows':['fixture-flow']})
        learn.add_lesson(self.root,{'project':'APP','ticket':'OLD-1','status':'active','flows':['fixture-flow'],
            'title':'transaction callback','symptom':'transaction callback','fix':text,'cause':None,'note':'original full note'})
        with patch.object(I,'select_lessons',wraps=I.select_lessons) as selected,patch.object(I,'render_lessons',wraps=I.render_lessons) as rendered:
            result=self.capture()
        self.assertTrue(selected.called);self.assertTrue(rendered.called)
        block=next(x['block'] for x in result['source']['context'] if x['mode']=='learning_lessons')
        self.assertEqual(block['payloads'][0]['content']['fix'],text)
        self.assertIsNone(block['payloads'][0]['content']['cause'])
        self.assertIn(block['text'],result['prompt'])
        self.assertEqual(block['renderer_version'],I.RENDERER_VERSION)
        self.assertEqual(result['source']['pool_before']['local'][0]['fix'],text)
        self.assertEqual(result['source']['pool_after']['local'][0]['fix'],text)

    def test_changed_scope_or_corrupt_capture_rejected(self):
        other=dict(self.ticket,project_id=999)
        with self.assertRaises(L.Conflict):R.capture(self.store,self.project,other,tenant_id='fixture-tenant')
        cap=self.capture();cap['prompt']+='forged'
        with self.assertRaises(L.Conflict):R.effective(cap,'policy')

    def test_wrong_history_type_rejects_before_factory_without_coercion(self):
        for history in [{},'', [None], [{'role':'user','body':None}]]:
            with self.subTest(history=history),patch.object(agents,'build_prompt',side_effect=AssertionError('must not call')) as factory:
                with self.assertRaises(ValueError):R.capture(self.store,self.project,self.ticket,tenant_id='fixture-tenant',history=history)
                factory.assert_not_called()

    def test_exception_restores_existing_metadata(self):
        old=[{'mode':'sentinel'}];agents._CTX_META.meta=old
        with patch.object(agents,'build_prompt',side_effect=RuntimeError('synthetic factory failure')),self.assertRaises(RuntimeError):self.capture()
        self.assertIs(agents._CTX_META.meta,old)


@unittest.skipUnless(os.name=='posix','original metered supervisor requires POSIX')
class RegisteredBrokerTests(unittest.TestCase):
    def setUp(self):
        self.c=F.ProviderAdapterTests('test_success_full_raw_cache_accounting_and_no_credential_artifact')
        self.c.setUp();self.addCleanup(self.c.doCleanups)
        (self.c.root/'test-identity.json').write_text(json.dumps({'test':self.id()}))
        (self.c.root/'project').mkdir()
        learning.schema(self.c.store)
        self.project=self.c.store.add_project('APP','合成生产工厂',str(self.c.root/'project'))
        self.assertEqual(self.project['id'],1)
        self.ticket=self.c.store.create_ticket(1,'transaction callback',body='完整来源输入',type='bug')
        self.cap=R.capture(self.c.store,self.project,self.ticket,tenant_id='fixture-tenant',history=[{'role':'user','body':'source history'}])
        catalog=self.c.root/'catalog';catalog.mkdir(mode=0o700)
        self.catalog=R.Catalog(catalog,trusted_uid=os.getuid());self.addCleanup(self.catalog.close)
        self.broker=R.Broker(self.c.adapter,self.catalog)
        self.input_hash=self.catalog.admit('input','input-one',self.cap)
        self.plan=self.makeplan()
        self.catalog.admit('plan','plan-one',self.plan)

    def makeplan(self,**updates):
        return dict({'schema':R.VERSION,'kind':'fixture-provider-only','input_id':'input-one','input_sha256':self.input_hash,
                     'root_pool':self.c.key,'contract_sha256':L.digest(self.c.ledger.snapshot(self.c.key)['contract']),
                     'request_id':'registered-one','phase':'propose','broker_sha256':R.CODE_SHA256,'policy':'policy-one','policy_sha256':R.sha(b'policy-one')},**updates)

    def test_registered_ids_dispatch_complete_input_and_original_receipt_once(self):
        result=self.broker.dispatch('plan-one','input-one')
        (self.c.root/'registered-result.json').write_text(L.encoded(result))
        self.assertEqual(result['state'],'settled');self.assertTrue(result['response_complete'])
        sent=json.loads(self.c.requests[0]);self.assertEqual(sent['system'],'policy-one')
        self.assertEqual(sent['messages'],[{'role':'user','content':self.cap['prompt']}])
        self.assertEqual(result['root_pool'],self.c.key);self.assertEqual(result['input_sha256'],self.input_hash)
        self.assertEqual(result['isolated_execution'],'not_run');self.assertEqual(result['oracle_evaluation'],'not_run')
        self.assertFalse(result['production_equivalent']);self.assertFalse(result['rsi_qualified'])
        self.assertFalse(self.broker.dispatch('plan-one','input-one')['new_dispatch']);self.assertEqual(self.c.count,1)

    def test_missing_wrong_scope_and_arbitrary_command_plan_zero_dispatch(self):
        with self.assertRaises(FileNotFoundError):self.broker.dispatch('missing','input-one')
        with self.assertRaises(L.Conflict):self.broker.dispatch('plan-one','wrong-input')
        variants=[dict(self.plan,command=['false']),self.makeplan(kind='root-shell'),self.makeplan(contract_sha256='0'*64)]
        for i,plan in enumerate(variants):
            name='bad-'+str(i);self.catalog.admit('plan',name,plan)
            with self.subTest(i=i),self.assertRaises(ValueError):self.broker.dispatch(name,'input-one')
        self.assertEqual(self.c.count,0)
        self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['calls'],0)

    def test_changed_provenance_cannot_relabel_same_http_bytes(self):
        self.broker.dispatch('plan-one','input-one')
        altered=copy.deepcopy(self.cap);altered['source']['history'].append({'role':'user','body':'another capture source'})
        altered['capture_sha256']=L.digest({k:v for k,v in altered.items() if k!='capture_sha256'})
        h=self.catalog.admit('input','input-two',altered)
        self.catalog.admit('plan','plan-two',self.makeplan(input_id='input-two',input_sha256=h))
        with self.assertRaises(L.Conflict):self.broker.dispatch('plan-two','input-two')
        self.assertEqual(self.c.count,1)

    def test_catalog_never_replaces_an_existing_id(self):
        with self.assertRaises(OSError):self.catalog.admit('plan','plan-one',self.makeplan(policy='replacement'))
        loaded,_,_=self.catalog.load('plan','plan-one');self.assertEqual(loaded,self.plan)

    def test_admission_is_visible_only_after_atomic_publication(self):
        reached=threading.Event();release=threading.Event();errors=[];original=R.os.rename
        def rename(*args,**kwargs):
            reached.set()
            if not release.wait(3):raise RuntimeError('publication barrier expired')
            return original(*args,**kwargs)
        def write():
            try:self.catalog.admit('input','atomic-input',self.cap)
            except BaseException as e:errors.append(type(e).__name__)
        with patch.object(R.os,'rename',side_effect=rename):
            thread=threading.Thread(target=write);thread.start()
            try:
                self.assertTrue(reached.wait(3))
                with self.assertRaises(FileNotFoundError):self.catalog.load('input','atomic-input')
                release.set();thread.join(3);self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
            finally:release.set();thread.join(3)
        self.assertEqual(self.catalog.load('input','atomic-input')[0],self.cap)

    def test_two_registered_callers_use_one_original_intent(self):
        self.c.wait=True;results=[];errors=[]
        def call():
            try:results.append(self.broker.dispatch('plan-one','input-one'))
            except BaseException as e:errors.append(type(e).__name__)
        a=threading.Thread(target=call);a.start()
        try:
            self.assertTrue(self.c.seen.wait(4));b=threading.Thread(target=call);b.start();b.join(3)
            self.assertFalse(b.is_alive());self.c.release.set();a.join(6)
            self.assertFalse(a.is_alive());self.assertEqual(errors,[])
            self.assertEqual(sorted(r['state'] for r in results),['intent','settled'])
            self.assertEqual(self.c.count,1)
            anchors=self.c.store.q("SELECT * FROM rsi_prepare_events WHERE kind='registered_plan'")
            self.assertEqual(len(anchors),1)
        finally:self.c.release.set();a.join(6)

    def test_changed_broker_code_cancels_and_preserves_original_worst_hold(self):
        original=R.CODE_PATH;copyfile=self.c.root/'broker-copy.py';copyfile.write_bytes(original.read_bytes());R.CODE_PATH=copyfile
        self.c.wait=True;result=[];errors=[]
        def call():
            try:result.append(self.broker.dispatch('plan-one','input-one'))
            except BaseException as e:errors.append(type(e).__name__)
        thread=threading.Thread(target=call);thread.start()
        try:
            self.assertTrue(self.c.seen.wait(4));copyfile.write_bytes(copyfile.read_bytes()+b'\n# changed\n')
            thread.join(6);self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
            self.assertEqual(result[0]['state'],'unknown')
            receipt=SP.read_receipt(Path(result[0]['evidence'])/'transport')
            self.assertEqual(receipt['returncode'],130);self.assertEqual(receipt['reason'],'cancelled')
            self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['cost_micro_cny'],1400)
            self.assertTrue(self.c.ledger.inspect(self.c.key)['blocked'])
        finally:self.c.release.set();thread.join(6);R.CODE_PATH=original

    def test_registered_input_change_cancels_and_unknown_never_resends(self):
        self.c.wait=True;results=[];errors=[]
        def call():
            try:results.append(self.broker.dispatch('plan-one','input-one'))
            except BaseException as e:errors.append(type(e).__name__)
        thread=threading.Thread(target=call);thread.start()
        try:
            self.assertTrue(self.c.seen.wait(4))
            record=self.c.root/'catalog/input-input-one/record.json'
            # Same valid JSON value; its original file identity still changed.
            with record.open('ab') as stream:stream.write(b'\n');stream.flush();os.fsync(stream.fileno())
            thread.join(6);self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
            self.assertEqual(results[0]['state'],'unknown')
            receipt=SP.read_receipt(Path(results[0]['evidence'])/'transport')
            self.assertEqual(receipt['returncode'],130);self.assertEqual(receipt['reason'],'cancelled')
            # An altered admitted record cannot reclaim the old request ID.
            with self.assertRaises(L.Conflict):self.broker.dispatch('plan-one','input-one')
            self.assertEqual(self.c.count,1)
            self.assertEqual(self.c.ledger.inspect(self.c.key)['totals'],{'calls':1,'billed_tokens':120,'cost_micro_cny':1400})
            self.assertTrue(self.c.ledger.inspect(self.c.key)['blocked'])
        finally:self.c.release.set();thread.join(6)

    def test_external_cancellation_replay_preserves_unknown_without_second_http(self):
        cancel=threading.Event();self.c.wait=True;results=[];errors=[]
        def call():
            try:results.append(self.broker.dispatch('plan-one','input-one',cancel_event=cancel))
            except BaseException as e:errors.append(type(e).__name__)
        thread=threading.Thread(target=call);thread.start()
        try:
            self.assertTrue(self.c.seen.wait(4));cancel.set();thread.join(6)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
            self.assertEqual(results[0]['state'],'unknown')
            receipt=SP.read_receipt(Path(results[0]['evidence'])/'transport')
            self.assertEqual(receipt['returncode'],130);self.assertEqual(receipt['reason'],'cancelled')
            replay=self.broker.dispatch('plan-one','input-one')
            self.assertEqual(replay['state'],'unknown');self.assertFalse(replay['new_dispatch'])
            self.catalog.admit('plan','retry-plan',self.makeplan(request_id='another-request',phase='retry'))
            with self.assertRaises(L.Conflict):self.broker.dispatch('retry-plan','input-one')
            self.assertEqual(self.c.count,1)
            self.assertEqual(self.c.ledger.inspect(self.c.key)['totals'],{'calls':1,'billed_tokens':120,'cost_micro_cny':1400})
        finally:self.c.release.set();thread.join(6)

    def test_live_mode_is_denied_before_reservation_or_admission_anchor(self):
        original=self.c.registry.load
        def declared_live(profile_id):
            value=original(profile_id);value['profile']=dict(value['profile'],mode='live');return value
        with patch.object(self.c.registry,'load',side_effect=declared_live),self.assertRaises(L.Conflict):
            self.broker.dispatch('plan-one','input-one')
        self.assertEqual(self.c.count,0)
        self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['calls'],0)
        self.assertEqual(self.c.store.q("SELECT * FROM rsi_prepare_events WHERE kind='registered_plan'"),[])

    def test_historical_attempt_never_backfilled_with_plan(self):
        packet=R.effective(self.cap,'policy-one')
        self.c.adapter.dispatch(self.c.key,'registered-one','propose',system=packet['system'],messages=packet['messages'])
        with self.assertRaises(L.Conflict):self.broker.dispatch('plan-one','input-one')
        self.assertEqual(self.c.count,1)

    def test_budget_and_terminal_consumption_stay_on_original_root(self):
        for i,phase in enumerate(['propose','judge','probe','retry','terminal','baseline','candidate','followup']):
            if phase=='terminal':self.c.ledger.consume_holdout(self.c.key)
            plan=self.makeplan(request_id='phase-'+str(i),phase=phase)
            self.catalog.admit('plan','phase-plan-'+str(i),plan)
            self.assertEqual(self.broker.dispatch('phase-plan-'+str(i),'input-one')['state'],'settled')
        self.catalog.admit('plan','overflow',self.makeplan(request_id='ninth'))
        with self.assertRaises(L.Conflict):self.broker.dispatch('overflow','input-one')
        self.assertEqual(self.c.count,8);self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['calls'],8)
