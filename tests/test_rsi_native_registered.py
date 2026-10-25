"""Original factory/lesson input and private token entry; synthetic HTTP only."""
import copy
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_rsi_token_adapter as F
from tests.sqlite_snapshot import dump_store
from scripts.rsi import registered_trial as R
from scripts.rsi import trial_preparation as L
from tmh.platform import learn, learning, lesson_input as I
from tmh.platform.errors import ApiError


@unittest.skipUnless(os.name=='posix','private registry and supervised native HTTP require POSIX')
class NativeRegisteredTests(unittest.TestCase):
    def setUp(self):
        self.c=F.TokenAdapterTests('test_messages_original_response_derives_exact_policy_and_same_root_terminal')
        self.c.setUp();self.addCleanup(self.c.doCleanups)
        root=self.c.root/'project';root.mkdir()
        learning.schema(self.c.store)
        self.project=self.c.store.add_project('APP','原输入工厂合成项目',str(root))
        self.lesson_text='完整事务原文\r\n'+('完整资料'*1600)+'末尾  😀'
        learn.add_lesson(self.c.root,dict(project='APP',ticket='OLD-1',status='active',flows=['fixture-flow'],
                         title='transaction callback',symptom='transaction callback',cause=None,fix=self.lesson_text,note='full original note'))
        self.history=[dict(role='user' if i%2==0 else 'assistant',body='history-%d\r\n尾部😀'%i) for i in range(9)]
        self.caps=[];self.input_hashes=[]
        directory=self.c.root/'catalog';directory.mkdir(mode=0o700)
        self.catalog=R.Catalog(directory,trusted_uid=os.getuid());self.addCleanup(self.catalog.close)
        for i in range(4):
            ticket=self.c.store.create_ticket(1,'transaction callback '+str(i),body='完整工单 transaction callback '+str(i),type='bug',links={'flows':['fixture-flow']})
            cap=R.capture(self.c.store,self.project,ticket,tenant_id='fixture-tenant',history=self.history)
            self.caps.append(cap);self.input_hashes.append(self.catalog.admit('input','input-'+str(i),cap))
        self.c.base['root_family']='registered-native-root'
        self.c.base['budget']['authorization_sha256']=F.h('distinct native registered fixture authorization')
        self.c.base['holdout_cases']=[dict(input_sha256=self.input_hashes[i],source_family='eval-B' if i==0 else 'eval-C') for i in range(3)]
        self.c.admit()
        self.broker=R.TokenBroker(self.c.adapter,self.catalog)

    def test_authorized_recapture_preserves_task_identity_across_update_order(self):
        original = [cap['source']['ticket']['id'] for cap in self.caps]
        # The UI's newest-first query can change order across a second boundary.
        # Input indexes belong to the original tasks, never to display ordering.
        for tid in original:
            self.c.store.x('UPDATE tickets SET updated=? WHERE id=?',
                           ('2026-10-26 01:00:%02d' % tid, tid))
        self.authorize_context()
        self.assertEqual([cap['source']['ticket']['id'] for cap in self.caps], original)
        block = next(m['block'] for m in self.caps[0]['source']['context']
                     if m.get('mode') == 'learning_lessons')
        self.assertTrue(block['bindings'])

    def plan(self,name,phase='propose',input_index=3,policy='baseline',family=None,request=None,adoption=None):
        family=family or (self.c.base['holdout_cases'][input_index]['source_family'] if phase in {'baseline','candidate'} else self.c.base['training_family'])
        plan=dict(schema=R.VERSION,kind=R.TokenBroker.KIND,input_id='input-'+str(input_index),input_sha256=self.input_hashes[input_index],
                  root_pool=self.c.key,contract_sha256=L.digest(self.c.ledger.snapshot(self.c.key)['contract']),
                  request_id=request or name,phase=phase,policy=policy,policy_sha256=R.sha(policy.encode()),broker_sha256=R.CODE_SHA256,source_family=family)
        if phase=='followup':plan['adoption']=adoption
        self.catalog.admit('plan',name,plan)
        return plan

    def send(self,name,**kwargs):
        plan=self.plan(name,**kwargs)
        return self.broker.dispatch(name,plan['input_id'])

    def propose(self):
        result=self.send('proposal')
        self.assertTrue(result['response_complete'])
        self.c.adapter.bind_candidate(self.c.key,'proposal')
        return result

    def authorize_context(self):
        from tmh.platform import login
        from tmh.platform.tenancy import Registry
        from tmh.platform.tenant_runtime import TenantContext
        login._save_users(self.c.root,{'owner':{'pw':login.hash_password('synthetic-native-owner-password')}})
        reg=Registry(self.c.root,bootstrap_owner='owner');self.addCleanup(reg.close)
        tenant=TenantContext(reg,'default')
        self.context=SimpleNamespace(store=self.c.store,data_dir=self.c.root,tenant_context=tenant);tenant.platform=self.context
        directory=self.c.root/'authorized-catalog';directory.mkdir(mode=0o700)
        self.catalog=R.Catalog(directory,trusted_uid=os.getuid());self.addCleanup(self.catalog.close)
        self.caps=[];self.input_hashes=[]
        for i,ticket in enumerate(sorted(self.c.store.tickets(project_id=1), key=lambda row: row['id'])):
            cap=R.capture(self.c.store,self.project,ticket,tenant_id='default',history=self.history)
            self.caps.append(cap);self.input_hashes.append(self.catalog.admit('input','input-'+str(i),cap))
        self.c.base.update(tenant_id='default',root_family='authorized-native-root')
        self.c.base['budget']['authorization_sha256']=F.h('distinct actual-registry synthetic authorization')
        self.c.base['holdout_cases']=[dict(input_sha256=self.input_hashes[i],source_family='eval-B' if i==0 else 'eval-C') for i in range(3)]
        self.c.admit();self.broker=R.TokenBroker(self.c.adapter,self.catalog,context=self.context,actor='owner')

    def reset_owner(self,request):
        reg=self.context.tenant_context.registry
        return reg.dispatch('owner',dict(action='password_reset',tenant='default',user='owner',password='synthetic-rotated-password',
                            revision=reg.context('owner')['revision'],request_id=request))

    def adopted_fixture(self):
        """Execute the existing synthetic evaluator and real decision/outbox.

        No real human or native-root report qualification is claimed. The live
        D gate remains closed until that report relation is implemented.
        """
        from tests.test_learning_decisions import LearningDecisionsTests
        from tmh.platform import learning_decisions as D
        card=learn.add_lesson(self.c.root,dict(project='APP',ticket='TRAIN-1',status='candidate',flows=['fixture-flow'],
            title='transaction callback',symptom='transaction callback',cause=None,fix=self.c.policy,verify='fixture exact check',
            applicability='同一事件重复回调',non_applicability='不同业务事件',anti='不跳过独立事件'))
        origin=learning._origin(self.context,self.project,'lesson:'+card['id'])
        revision=learning.capture(self.context,self.project,origin['key'],origin['fingerprint'],'owner')
        fixture=LearningDecisionsTests('test_partial_lesson_proposal_remains_current_after_actual_adoption')
        fixture.P=self.context;fixture.store=self.c.store;fixture.p=self.project;fixture.r=revision;fixture.serial=0
        job=fixture.passed(revision)
        decision=D.decide(self.context,self.project,'adopt',revision['id'],'owner','synthetic-adopt',None,'合成个人决定机制',job['id'])
        self.assertEqual(decision['status'],'applied')
        ticket=self.c.store.create_ticket(1,'new D transaction callback',body='new independent callback task',type='bug',links={'flows':['fixture-flow']})
        cap=R.capture(self.c.store,self.project,ticket,tenant_id='default',history=[])
        self.caps.append(cap);self.input_hashes.append(self.catalog.admit('input','input-4',cap))
        return dict(decision_id=decision['id'],revision_id=revision['id'],job_id=job['id'],report_sha256=L.digest(job['result']))

    def test_one_real_factory_snapshot_has_lossless_original_lesson_and_history(self):
        cap=self.caps[0]
        block=next(x['block'] for x in cap['source']['context'] if x['mode']=='learning_lessons')
        self.assertEqual(block['payloads'][0]['content']['fix'],self.lesson_text)
        self.assertIsNone(block['payloads'][0]['content']['cause'])
        self.assertIn(block['text'],cap['prompt']);self.assertEqual(block['renderer_version'],I.RENDERER_VERSION)
        self.assertEqual(cap['source']['history'],self.history);self.assertEqual(cap['source']['effective_history'],self.history[-6:])
        with patch.object(I,'select_lessons',side_effect=AssertionError('do not reselect per arm')),patch.object(I,'render_lessons',side_effect=AssertionError('do not rerender per arm')):
            pair=R.native_pair(cap,'baseline',self.c.policy,'messages')
        self.assertEqual(pair['baseline']['messages'],pair['candidate']['messages'])
        self.assertEqual(pair['candidate']['messages'],[{'role':'user','content':cap['prompt']}])
        self.assertFalse(pair['production_equivalent']);self.assertFalse(pair['rsi_qualified'])

    def test_two_arms_use_same_complete_capture_original_root_and_derived_policy(self):
        original=self.c.ledger.snapshot(self.c.key)['contract'];self.propose()
        b=self.send('baseline',phase='baseline',input_index=0)
        c=self.send('candidate',phase='candidate',input_index=0,policy=self.c.policy)
        self.assertEqual(b['input_sha256'],c['input_sha256']);self.assertEqual(b['common_sha256'],c['common_sha256'])
        sent_b,sent_c=[json.loads(x) for x in self.c.requests[1:]]
        self.assertEqual(sent_b['messages'],sent_c['messages'])
        self.assertEqual(sent_b['messages'][0]['content'],self.caps[0]['prompt'])
        self.assertEqual(sent_b['system'],'baseline');self.assertEqual(sent_c['system'],self.c.policy)
        self.assertEqual(self.c.ledger.snapshot(self.c.key)['contract'],original)
        self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['calls'],3)
        self.assertFalse(c['rsi_qualified']);self.assertEqual(c['oracle_evaluation'],'not_run')

    def test_responses_uses_the_same_original_factory_capture_without_legacy_session_claim(self):
        self.c.switch_responses();self.propose()
        b=self.send('baseline-r',phase='baseline',input_index=1)
        self.send('candidate-r',phase='candidate',input_index=1,policy=self.c.policy)
        baseline,candidate=[json.loads(x) for x in self.c.requests[1:]]
        self.assertEqual(baseline['input'],candidate['input']);self.assertEqual(baseline['input'][0]['content'],self.caps[1]['prompt'])
        pair=R.native_pair(self.caps[1],'baseline',self.c.policy,'responses')
        self.assertEqual(pair['baseline']['session'],'fresh-native-responses')
        self.assertEqual(b['state'],'settled');self.assertEqual(self.c.bearer_ok,[True,True,True])

    def test_unbound_candidate_refuses_before_claim_anchor_or_http(self):
        self.plan('B',phase='baseline',input_index=0);before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.broker.dispatch('B','input-0')
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,0)

    def test_exact_plan_replay_is_once_and_another_request_cannot_repeat_the_arm(self):
        self.propose();self.plan('B',phase='baseline',input_index=0)
        self.assertTrue(self.broker.dispatch('B','input-0')['new_dispatch'])
        self.assertFalse(self.broker.dispatch('B','input-0')['new_dispatch']);self.assertEqual(self.c.count,2)
        self.plan('B2',phase='baseline',input_index=0);before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.broker.dispatch('B2','input-0')
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,2)

    def test_unknown_plan_replay_keeps_original_hold_without_second_http(self):
        self.c.response['usage']['output_tokens']=None
        self.plan('unknown')
        self.assertEqual(self.broker.dispatch('unknown','input-3')['state'],'unknown')
        before=dump_store(self.c.store)
        replay=self.broker.dispatch('unknown','input-3')
        self.assertEqual(replay['state'],'unknown');self.assertFalse(replay['new_dispatch'])
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,1)
        self.assertEqual(self.c.ledger.inspect(self.c.key)['token_budget']['reserved_or_unknown'],120)

    def test_current_authority_is_rechecked_under_guard_before_any_reservation(self):
        self.authorize_context();self.plan('A');original=self.c.adapter.dispatch
        def rotate_then_dispatch(*args,**kwargs):
            self.reset_owner('synthetic-before-intent')
            return original(*args,**kwargs)
        with patch.object(self.c.adapter,'dispatch',side_effect=rotate_then_dispatch),self.assertRaises(L.Conflict):
            self.broker.dispatch('A','input-3')
        self.assertEqual(self.c.count,0)
        self.assertEqual(self.c.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=?',(self.c.key,)),[])

    def test_password_epoch_change_during_request_cancels_without_holding_auth_lock_across_http(self):
        self.authorize_context();self.plan('A');self.c.wait=True;results=[];errors=[]
        def work():
            try:results.append(self.broker.dispatch('A','input-3'))
            except BaseException as error:errors.append(error)
        t=threading.Thread(target=work);t.start()
        self.addCleanup(lambda:(self.c.release.set(),t.join(6)))
        self.assertTrue(self.c.seen.wait(3));self.reset_owner('synthetic-inflight');t.join(6)
        self.assertFalse(t.is_alive());self.assertEqual(errors,[]);self.assertEqual(results[0]['state'],'unknown')
        receipt=F.F.SP.read_receipt(Path(results[0]['evidence'])/'transport')
        self.assertEqual(receipt['reason'],'cancelled');self.assertTrue(receipt['cleanup']['complete'])
        self.assertEqual(self.c.count,1)
        self.assertEqual(self.c.ledger.inspect(self.c.key)['token_budget']['reserved_or_unknown'],120)

    def test_current_lesson_withdrawal_before_reservation_denies_without_http(self):
        self.propose();self.plan('B',phase='baseline',input_index=0);original=self.c.adapter.dispatch
        card=learn.lessons(self.c.root,'APP')[0]
        def retire_then_dispatch(*args,**kwargs):
            learn.set_status(self.c.root,card['id'],'retired','synthetic-owner','synthetic withdrawal')
            return original(*args,**kwargs)
        with patch.object(self.c.adapter,'dispatch',side_effect=retire_then_dispatch),self.assertRaises(L.Conflict):
            self.broker.dispatch('B','input-0')
        self.assertEqual(self.c.count,1)
        self.assertEqual(self.c.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=? AND request_id=?',(self.c.key,'B')),[])

    def test_external_knowledge_writer_cannot_publish_between_validation_and_intent(self):
        self.plan('A');reserve=self.c.ledger.reserve
        # A separate OS process tries the real ledger inode, without waiting or
        # replacing the selector/current check. Exit 73 means the write is fenced.
        program='import fcntl,sys\nf=open(sys.argv[1],"r+b")\ntry:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError:sys.exit(73)\nsys.exit(0)\n'
        def checked_reserve(*args,**kwargs):
            result=subprocess.run([sys.executable,'-I','-c',program,str(self.c.root/'lessons.lock')],capture_output=True,timeout=3)
            self.assertEqual(result.returncode,73,result.stderr)
            return reserve(*args,**kwargs)
        with patch.object(self.c.ledger,'reserve',side_effect=checked_reserve):
            result=self.broker.dispatch('A','input-3')
        self.assertEqual(result['state'],'settled');self.assertEqual(self.c.count,1)

    def test_inflight_lesson_withdrawal_cancels_and_holds_maximum_without_reexecution(self):
        self.propose();self.plan('B',phase='baseline',input_index=0);self.c.wait=True;self.c.seen.clear();results=[];errors=[]
        def work():
            try:results.append(self.broker.dispatch('B','input-0'))
            except BaseException as error:errors.append(error)
        t=threading.Thread(target=work);t.start()
        self.addCleanup(lambda:(self.c.release.set(),t.join(6)))
        self.assertTrue(self.c.seen.wait(3))
        card=learn.lessons(self.c.root,'APP')[0]
        learn.set_status(self.c.root,card['id'],'retired','synthetic-owner','synthetic withdrawal')
        t.join(6);self.assertFalse(t.is_alive());self.assertEqual(errors,[])
        self.assertEqual(results[0]['state'],'unknown')
        receipt=F.F.SP.read_receipt(Path(results[0]['evidence'])/'transport')
        self.assertEqual(receipt['reason'],'cancelled');self.assertTrue(receipt['cleanup']['complete'])
        self.assertFalse(receipt['cleanup']['remaining_group'])
        self.assertEqual(self.c.ledger.inspect(self.c.key)['token_budget']['reserved_or_unknown'],120)
        before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.broker.dispatch('B','input-0')
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,2)

    def test_two_connections_compete_for_one_input_arm_and_one_http(self):
        from tmh.platform.store import Store
        self.propose();self.plan('B1',phase='baseline',input_index=0);self.plan('B2',phase='baseline',input_index=0)
        store=Store(self.c.store.path);self.addCleanup(store.db.close)
        # Two connections in the SAME controller generation, not crash recovery.
        ledger=L.Ledger(store);ledger.generation=self.c.ledger.generation
        adapter=F.P.Adapter(ledger,self.c.registry,self.c.adapter.root)
        other=R.TokenBroker(adapter,self.catalog);barrier=threading.Barrier(2);results=[];errors=[]
        def work(broker,name):
            try:barrier.wait(3);results.append(broker.dispatch(name,'input-0'))
            except BaseException as error:errors.append(error)
        threads=[threading.Thread(target=work,args=(self.broker,'B1')),threading.Thread(target=work,args=(other,'B2'))]
        for t in threads:t.start()
        for t in threads:t.join(6)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(len(results),1);self.assertEqual(results[0]['state'],'settled')
        self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],L.Conflict)
        self.assertEqual(self.c.count,2)
        self.assertEqual(len(self.c.store.q("SELECT * FROM rsi_prepare_events WHERE pool=? AND kind='registered_token_arm'",(self.c.key,))),1)

    def test_failed_plan_anchor_rolls_back_input_and_arm_without_reservation(self):
        self.propose();self.plan('B',phase='baseline',input_index=0);before=dump_store(self.c.store)
        original=self.c.ledger._event
        def fail(db,key,request,kind,value):
            if kind=='registered_plan':raise RuntimeError('synthetic final registration write failure')
            return original(db,key,request,kind,value)
        with patch.object(self.c.ledger,'_event',side_effect=fail),self.assertRaises(RuntimeError):self.broker.dispatch('B','input-0')
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,1)

    def test_wrong_family_nonsealed_input_and_ambiguous_terminal_zero_new_http(self):
        self.propose()
        variants=[dict(phase='baseline',input_index=0,family='wrong-family'),dict(phase='baseline',input_index=3,family='eval-B'),dict(phase='terminal',family=self.c.base['training_family'])]
        for i,kwargs in enumerate(variants):
            plan=self.plan('bad-'+str(i),**kwargs);before=dump_store(self.c.store)
            with self.subTest(i=i),self.assertRaises(L.Conflict):self.broker.dispatch('bad-'+str(i),plan['input_id'])
            self.assertEqual(before,dump_store(self.c.store))
        self.assertEqual(self.c.count,1)

    def test_training_labels_cannot_expose_a_presealed_terminal_input(self):
        for phase in ('propose','judge','probe','retry'):
            plan=self.plan('leak-'+phase,phase=phase,input_index=0,family=self.c.base['training_family'])
            before=dump_store(self.c.store)
            with self.subTest(phase=phase),self.assertRaises(L.Conflict):self.broker.dispatch('leak-'+phase,plan['input_id'])
            self.assertEqual(before,dump_store(self.c.store))
        self.assertEqual(self.c.count,0)

    def test_current_task_change_before_reservation_denies_without_http(self):
        self.plan('A');original=self.c.adapter.dispatch;ticket=self.caps[3]['source']['ticket']
        def edit_then_dispatch(*args,**kwargs):
            self.c.store.x('UPDATE tickets SET body=? WHERE id=?',('changed original task',ticket['id']))
            return original(*args,**kwargs)
        with patch.object(self.c.adapter,'dispatch',side_effect=edit_then_dispatch),self.assertRaises(L.Conflict):self.broker.dispatch('A','input-3')
        self.assertEqual(self.c.count,0)
        self.assertEqual(self.c.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=?',(self.c.key,)),[])

    def test_new_d_does_not_treat_derived_policy_as_human_adoption(self):
        self.propose();plan=self.plan('D',phase='followup',family=self.c.base['followup_family']);before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.broker.dispatch('D',plan['input_id'])
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,1)

    def test_legacy_and_token_plan_kinds_are_not_interchangeable(self):
        plan=self.plan('typed');plan['kind']=R.Broker.KIND
        self.catalog.admit('plan','legacy-kind',plan)
        with self.assertRaises(L.Conflict):self.broker.dispatch('legacy-kind',plan['input_id'])
        with self.assertRaises(ValueError):R.Broker(self.c.adapter,self.catalog).dispatch('typed',plan['input_id'])
        self.assertEqual(self.c.count,0)

    def test_missing_server_tenant_context_or_execution_grant_is_not_inferred_from_a_name(self):
        self.plan('A');before=dump_store(self.c.store)
        broker=R.TokenBroker(self.c.adapter,self.catalog,context=SimpleNamespace(store=self.c.store),actor='manager')
        with self.assertRaises(ApiError):broker.dispatch('A','input-3')
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,0)
        with self.assertRaises(L.Conflict):self.broker._authority(self.c.ledger.snapshot(self.c.key)['contract'],dict(self.c.profile,mode='live'))

    def test_old_factory_or_renderer_code_cannot_relabel_a_capture(self):
        for field in ('factory_sha256','lesson_input_sha256','capture_code_sha256'):
            cap=copy.deepcopy(self.caps[0]);cap['source'][field]='0'*64
            cap['capture_sha256']=L.digest({k:v for k,v in cap.items() if k!='capture_sha256'})
            with self.subTest(field=field),self.assertRaises(L.Conflict):R.native_pair(cap,'baseline',self.c.policy,'messages')

    def test_existing_personal_adoption_is_read_only_selected_for_new_d_and_revoke_refuses_replay(self):
        from tmh.platform import learning_decisions as D
        self.authorize_context();self.propose()
        for i in range(3):
            self.send('B'+str(i),phase='baseline',input_index=i)
            self.send('C'+str(i),phase='candidate',input_index=i,policy=self.c.policy)
        adoption=self.adopted_fixture()
        original=self.c.store.q('SELECT * FROM learning_decisions ORDER BY rowid')
        bad=dict(adoption,report_sha256='0'*64)
        bad_plan=self.plan('wrong-report',phase='followup',input_index=4,family=self.c.base['followup_family'],policy=self.c.policy,adoption=bad)
        with self.assertRaises(L.Conflict):self.broker.dispatch('wrong-report',bad_plan['input_id'])
        self.assertEqual(self.c.count,7)
        plan=self.plan('D',phase='followup',input_index=4,family=self.c.base['followup_family'],policy=self.c.policy,adoption=adoption)
        result=self.broker.dispatch('D',plan['input_id'])
        self.assertEqual(result['state'],'settled');self.assertTrue(result['human_adoption']['selected'])
        self.assertFalse(result['qualified_bc_report_verified']);self.assertFalse(result['rsi_qualified'])
        self.assertEqual(original,self.c.store.q('SELECT * FROM learning_decisions ORDER BY rowid'))
        self.assertEqual(self.c.count,8)
        D.decide(self.context,self.project,'revoke',adoption['revision_id'],'owner','synthetic-revoke',adoption['revision_id'],'合成撤回')
        with self.assertRaises(L.Conflict):self.broker.dispatch('D',plan['input_id'])
        self.assertEqual(self.c.count,8)

    def test_d_cannot_skip_bc_and_live_d_does_not_launder_an_unlinked_manual_report(self):
        self.authorize_context();self.propose();adoption=self.adopted_fixture()
        plan=self.plan('early-D',phase='followup',input_index=4,family=self.c.base['followup_family'],policy=self.c.policy,adoption=adoption)
        with self.assertRaises(L.Conflict):self.broker.dispatch('early-D',plan['input_id'])
        self.assertEqual(self.c.count,1)
        with self.assertRaises(L.Conflict):self.broker._followup(plan,self.caps[4],self.c.ledger.snapshot(self.c.key)['contract'],self.input_hashes[4],dict(self.c.profile,mode='live'))
        self.assertEqual(self.c.count,1)

    def test_d_requires_actual_selection_even_when_the_personal_adoption_is_current(self):
        self.authorize_context();self.propose()
        for i in range(3):
            self.send('B'+str(i),phase='baseline',input_index=i)
            self.send('C'+str(i),phase='candidate',input_index=i,policy=self.c.policy)
        adoption=self.adopted_fixture()
        ticket=self.c.store.create_ticket(1,'unrelated inventory','unrelated inventory',type='bug')
        cap=R.capture(self.c.store,self.project,ticket,tenant_id='default',history=[])
        self.caps.append(cap);self.input_hashes.append(self.catalog.admit('input','input-5',cap))
        plan=self.plan('unselected-D',phase='followup',input_index=5,family=self.c.base['followup_family'],policy=self.c.policy,adoption=adoption)
        with self.assertRaises(L.Conflict):self.broker.dispatch('unselected-D',plan['input_id'])
        self.assertEqual(self.c.count,7)

    def test_d_cannot_change_adopted_policy_or_use_duplicate_arm_history(self):
        self.authorize_context();self.propose()
        for i in range(3):
            self.send('B'+str(i),phase='baseline',input_index=i)
            self.send('C'+str(i),phase='candidate',input_index=i,policy=self.c.policy)
        adoption=self.adopted_fixture()
        plan=self.plan('wrong-policy-D',phase='followup',input_index=4,family=self.c.base['followup_family'],policy='unadopted override',adoption=adoption)
        before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.broker.dispatch('wrong-policy-D',plan['input_id'])
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)
        with learning.transaction(self.c.store) as db:
            self.c.ledger._event(db,self.c.key,'','registered_token_arm',dict(input_sha256=self.input_hashes[0],phase='baseline',request_id='B0'))
        plan=self.plan('duplicate-D',phase='followup',input_index=4,family=self.c.base['followup_family'],policy=self.c.policy,adoption=adoption)
        before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.broker.dispatch('duplicate-D',plan['input_id'])
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)


if __name__=='__main__':unittest.main()
