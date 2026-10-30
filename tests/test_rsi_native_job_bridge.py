"""Actual native originals and synthetic personal decisions; no real adoption."""
import copy
import json
import os
import sqlite3
import threading
import unittest
from unittest.mock import patch

from tests import test_rsi_native_bc_report as F
from tests.sqlite_snapshot import dump_store
from scripts.rsi import trial_preparation as L, registered_trial as R, provider_adapter as A, native_bc_report as B, native_job_bridge as J
from tmh.platform import learn, learning, learning_runs, learning_decisions as D, native_learning as N
from tmh.platform.errors import ApiError


@unittest.skipUnless(os.name=='posix', 'private originals and actual supervised processes require POSIX')
class NativeJobBridgeTests(unittest.TestCase):
    def setUp(self):
        f = F.NativeReportTests('test_original_two_arm_assertions_execute_in_supervised_worker_and_replay_without_http')
        f.setUp(); self.addCleanup(f.doCleanups); self.f=f; self.c=f.c; self.context=f.f.context; self.project=f.f.project
        (self.c.root/'test-label.json').write_text(json.dumps({'test':self.id()}))
        c=self.c; c.base['limits']['calls']=getattr(self,'max_calls',20); c.base['schema']=L.FINITE_VERSION; c.base['root_family']='native-job-finite-root'
        c.base['budget']=dict(unit='observed_tokens',authorization_sha256=L.digest('new synthetic native job authorization'),prior_evidence_sha256=L.digest('original historical roots retained'))
        c.base['limits'].pop('billed_tokens');c.base['limits']['max_total_tokens']=None
        for k in ('input_cap_tokens','input_cap_reference_sha256','bound_evidence_ref'):c.profile.pop(k)
        c.profile.update(schema=A.FINITE_VERSION,max_request_bytes=1_000_000,billing_mode='observed-usage-v1',parameters_version='messages-text-finite-v1',protocol_sha256=L.digest(A.FINITE_PROTOCOLS['messages']),contract_sha256=L.digest(c.base))
        c.write_profile();c.key=c.adapter.register('fixture',c.base)
        self.broker=R.FiniteBroker(c.adapter,f.f.catalog,context=self.context,actor='owner')
        self.reports=B.Reports(self.broker,c.root/'job-bc-reports');self.jobs=J.Jobs(self.reports)
        spec=copy.deepcopy(f.spec);spec.update(root_pool=c.key,contract_sha256=L.digest(c.ledger.snapshot(c.key)['contract']),authorization_sha256=c.base['budget']['authorization_sha256'])
        p=c.registry_dir/'job-assertions.json';p.write_text(L.encoded(spec));p.chmod(0o600)
        self.reports.freeze(c.key,'job-assertions')
        self.send('proposal');c.adapter.bind_candidate(c.key,'proposal')
        for i in range(3):
            c.response['content'][0]['text']='missing expectation';self.send('B'+str(i),'baseline',i)
            c.response['content'][0]['text']=c.policy;self.send('C'+str(i),'candidate',i,c.policy)
        self.report=self.reports.evaluate(c.key)
        card=learn.add_lesson(c.root,dict(project='APP',ticket='TRAIN-1',status='candidate',flows=['fixture-flow'],title='transaction callback',symptom='transaction callback',fix=c.policy,verify='original fixed native assertions',applicability='synthetic same callback',non_applicability='synthetic different callback'))
        origin=learning._origin(self.context,self.project,'lesson:'+card['id'])
        self.revision=learning.capture(self.context,self.project,origin['key'],origin['fingerprint'],'owner')

    def send(self,name,phase='propose',index=3,policy='baseline'):
        c=self.c;plan=dict(schema=R.VERSION,kind=self.broker.KIND,input_id='input-'+str(index),input_sha256=self.f.f.input_hashes[index],root_pool=c.key,contract_sha256=L.digest(c.ledger.snapshot(c.key)['contract']),request_id=name,phase=phase,policy=policy,policy_sha256=R.sha(policy.encode()),broker_sha256=R.CODE_SHA256,source_family=c.base['holdout_cases'][index]['source_family'] if phase in {'baseline','candidate'} else c.base['training_family'])
        self.f.f.catalog.admit('plan',name,plan);return self.broker.dispatch(name,plan['input_id'])

    def reference(self,sha=None):
        return L.encoded(dict(schema='native-bc-decision-reference-v1',root_pool=self.c.key,native_report_sha256=sha or self.report['report_sha256'],reason='synthetic personal report reference only'))

    def test_publishes_actual_native_job_without_ordinary_evaluator_or_new_calls(self):
        job=self.jobs.publish(self.c.key,self.revision['id'])
        self.assertEqual(job['kind'],N.KIND);self.assertEqual(job['status'],'passed');self.assertEqual(job['calls'],7)
        self.assertTrue(job['result']['passed']);self.assertFalse(job['result']['rsi_qualified']);self.assertEqual(self.c.count,7)
        self.assertEqual(self.jobs.publish(self.c.key,self.revision['id']),job)
        self.assertEqual(N.verify(self.context,self.project,job)['revision'],self.revision)
        self.assertNotIn('expected',L.encoded(job));self.assertNotIn('supervised',L.encoded(job))
        self.assertEqual(self.c.store.q('SELECT id FROM learning_decisions'),[])
        decision=D.decide(self.context,self.project,'adopt',self.revision['id'],'owner','synthetic-native-personal',None,self.reference(),job['id'])
        self.assertEqual(decision['status'],'applied');self.assertTrue(D.adopted_current(self.context,self.project,self.revision))
        self.assertEqual(N.verify(self.context,self.project,job,reason=self.reference(),adopted=True)['native_report_sha256'],self.report['report_sha256'])
        self.assertEqual(self.c.count,7)

    def test_exact_report_reference_is_required_and_failure_writes_no_decision(self):
        job=self.jobs.publish(self.c.key,self.revision['id'])
        for reason in ('a person said passed',self.reference('0'*64)):
            before=dump_store(self.c.store)
            with self.assertRaises(ApiError):
                D.decide(self.context,self.project,'adopt',self.revision['id'],'owner','synthetic-wrong-reference',None,reason,job['id'])
            self.assertEqual(before,dump_store(self.c.store))
        self.assertIsNone(learn.active_revision(self.c.root,self.revision['origin_id']))

    def test_original_provider_tamper_invalidates_published_job_before_human_intent(self):
        job=self.jobs.publish(self.c.key,self.revision['id']);path=self.c.adapter._folder(self.c.key,'C0')/'transport/output.bin';path.write_bytes(path.read_bytes()+b'changed')
        before=dump_store(self.c.store)
        with self.assertRaises(ApiError):D.decide(self.context,self.project,'adopt',self.revision['id'],'owner','synthetic-tampered',None,self.reference(),job['id'])
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)

    def test_late_attempt_cannot_inherit_report(self):
        job=self.jobs.publish(self.c.key,self.revision['id']);self.c.ledger.reserve(self.c.key,'late','probe',1,1,material_sha256='1'*64)
        before=dump_store(self.c.store)
        with self.assertRaises(ApiError):D.decide(self.context,self.project,'adopt',self.revision['id'],'owner','synthetic-late',None,self.reference(),job['id'])
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)

    def adopt(self):
        job=self.jobs.publish(self.c.key,self.revision['id'])
        decision=D.decide(self.context,self.project,'adopt',self.revision['id'],'owner','synthetic-native-adopt',None,self.reference(),job['id'])
        return job,decision,self.jobs.link(self.c.key,decision['id'])

    def prepare_d(self, register=True):
        job,decision,link=self.adopt()
        ticket=self.c.store.create_ticket(self.project['id'],'transaction callback new D',body='new distinct callback case for synthetic D',type='bug',links={'flows':['fixture-flow']})
        cap=R.capture(self.c.store,self.project,ticket,tenant_id='default',history=[])
        input_hash=self.f.f.catalog.admit('input','input-D',cap)
        c=self.c
        plan=dict(schema=R.VERSION,kind=self.broker.KIND,input_id='input-D',input_sha256=input_hash,root_pool=c.key,contract_sha256=L.digest(c.ledger.snapshot(c.key)['contract']),
                  request_id='actual-D',phase='followup',policy=c.policy,policy_sha256=R.sha(c.policy.encode()),broker_sha256=R.CODE_SHA256,source_family=c.base['followup_family'],
                  adoption={k:link[k] for k in ('decision_id','revision_id','job_id','report_sha256')})
        self.f.f.catalog.admit('plan','actual-D',plan)
        spec=dict(schema='native-d-assertion-v1',root_pool=c.key,job_id=job['id'],input_sha256=input_hash,validator='exact',expected='独立D断言的完整答案 / independent-D-only',forbidden=[])
        p=c.registry_dir/'D-assertions.json';p.write_text(L.encoded(spec));p.chmod(0o600)
        if register: self.jobs.prepare_followup(c.key,'actual-D','D-assertions')
        c.response['content'][0]['text']=spec['expected']
        return job,decision,cap

    def test_actual_selected_new_D_uses_same_root_and_evaluates_original_only_once(self):
        job,decision,cap=self.prepare_d();result=self.broker.dispatch('actual-D','input-D')
        self.assertTrue(result['response_complete']);self.assertTrue(result['qualified_bc_report_verified'])
        self.assertEqual(self.c.count,8);self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['calls'],8)
        self.assertNotIn('independent-D-only',self.c.requests[-1].decode())
        self.assertTrue(self.jobs._selected(cap,self.revision))
        report=self.jobs.evaluate_followup(self.c.key)
        self.assertTrue(report['assertions']['passed']);self.assertFalse(report['rsi_qualified']);self.assertEqual(report['decision_id'],decision['id'])
        with patch.object(J.SP,'run_supervised',side_effect=AssertionError('no implicit D or evaluator rerun')):
            self.assertEqual(self.jobs.evaluate_followup(self.c.key),report)
            self.assertEqual(self.jobs.read_followup(self.c.key),report)
            self.assertFalse(self.broker.dispatch('actual-D','input-D')['new_dispatch'])
        with self.assertRaises(L.Conflict):self.reports.read(self.c.key)
        self.assertEqual(self.c.count,8)

    def test_unrelated_late_attempt_is_not_hidden_by_owned_D_exception(self):
        self.prepare_d();self.broker.dispatch('actual-D','input-D');self.jobs.evaluate_followup(self.c.key)
        self.c.ledger.reserve(self.c.key,'unrelated-late','probe',1,1,material_sha256='1'*64)
        with self.assertRaises((ApiError,L.Conflict)):self.jobs.read_followup(self.c.key)
        self.assertEqual(self.c.count,8)

    def test_actual_revoke_invalidates_D_and_never_replays_it(self):
        self.prepare_d();self.broker.dispatch('actual-D','input-D');self.jobs.evaluate_followup(self.c.key)
        D.decide(self.context,self.project,'revoke',self.revision['id'],'owner','synthetic-native-revoke',self.revision['id'],'synthetic personal withdrawal')
        with self.assertRaises((ApiError,L.Conflict)):self.jobs.read_followup(self.c.key)
        with self.assertRaises((ApiError,L.Conflict)):self.broker.dispatch('actual-D','input-D')
        self.assertEqual(self.c.count,8)

    def test_unknown_D_evaluator_keeps_original_intent_and_does_not_rerun(self):
        self.prepare_d();self.broker.dispatch('actual-D','input-D')
        with patch.object(J.SP,'run_supervised',side_effect=TimeoutError('synthetic worker could not finish')):
            with self.assertRaises(TimeoutError):self.jobs.evaluate_followup(self.c.key)
        self.assertIsNotNone(self.reports._one(self.c.key,'native_d_evaluation_intent'))
        self.assertIsNone(self.reports._one(self.c.key,'native_d_report'))
        with patch.object(J.SP,'run_supervised',side_effect=AssertionError('never rerun an unknown evaluator')):
            with self.assertRaises(L.Conflict):self.jobs.evaluate_followup(self.c.key)
        self.assertEqual(self.c.count,8)

    def test_ordinary_passed_job_with_exact_reason_is_not_native_provenance(self):
        from tests.test_learning_decisions import LearningDecisionsTests
        native=self.jobs.publish(self.c.key,self.revision['id'])
        fixture=LearningDecisionsTests('test_partial_lesson_proposal_remains_current_after_actual_adoption')
        fixture.P=self.context;fixture.store=self.c.store;fixture.p=self.project;fixture.r=self.revision;fixture.serial=0
        ordinary=fixture.passed(self.revision)
        self.assertEqual(ordinary['kind'],'evaluate');self.assertTrue(ordinary['result']['passed'])
        decision=D.decide(self.context,self.project,'adopt',self.revision['id'],'owner','synthetic-ordinary',None,self.reference(),ordinary['id'])
        with self.assertRaises(L.Conflict):self.jobs.link(self.c.key,decision['id'])
        self.assertNotEqual(ordinary['id'],native['id']);self.assertEqual(self.c.count,7)

    def test_publication_rollback_preserves_originals_and_retry_uses_no_new_worker(self):
        learning_runs.schema(self.c.store)
        self.c.store.db.execute("CREATE TEMP TRIGGER fail_native_publication BEFORE INSERT ON rsi_prepare_events WHEN NEW.kind='native_learning_job' BEGIN SELECT RAISE(ABORT,'synthetic publication failure'); END")
        self.c.store.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):self.jobs.publish(self.c.key,self.revision['id'])
        self.assertEqual(self.c.store.q('SELECT id FROM learning_jobs'),[])
        self.assertIsNone(self.reports._one(self.c.key,N.EVENT));self.assertEqual(self.c.count,7)
        self.c.store.db.execute('DROP TRIGGER fail_native_publication');self.c.store.db.commit()
        with patch.object(J.SP,'run_supervised',side_effect=AssertionError('publication cannot rerun originals')):
            job=self.jobs.publish(self.c.key,self.revision['id'])
        self.assertEqual(job['kind'],N.KIND);self.assertEqual(self.c.count,7)

    def test_agent_name_cannot_use_native_job_to_adopt(self):
        job=self.jobs.publish(self.c.key,self.revision['id']);before=dump_store(self.c.store)
        with self.assertRaises(ApiError):D.decide(self.context,self.project,'adopt',self.revision['id'],'agent:planner','synthetic-agent',None,self.reference(),job['id'])
        self.assertEqual(before,dump_store(self.c.store));self.assertIsNone(learn.active_revision(self.c.root,self.revision['origin_id']))

    def test_unknown_job_kind_cannot_bypass_native_evidence_validation(self):
        job=self.jobs.publish(self.c.key,self.revision['id'])
        self.c.store.db.execute("UPDATE learning_jobs SET kind='unknown_fake_kind' WHERE id=?",(job['id'],));self.c.store.db.commit()
        before=dump_store(self.c.store)
        with self.assertRaises(ApiError):D.decide(self.context,self.project,'adopt',self.revision['id'],'owner','synthetic-kind-forgery',None,self.reference(),job['id'])
        self.assertEqual(before,dump_store(self.c.store));self.assertIsNone(learn.active_revision(self.c.root,self.revision['origin_id']))

    def test_new_D_wrong_output_is_failed_assertion_not_execution_success(self):
        self.prepare_d();self.c.response['content'][0]['text']='wrong complete answer'
        self.assertTrue(self.broker.dispatch('actual-D','input-D')['response_complete'])
        report=self.jobs.evaluate_followup(self.c.key)
        self.assertFalse(report['assertions']['passed']);self.assertFalse(report['rsi_qualified']);self.assertEqual(self.c.count,8)

    def test_D_without_original_assertion_registration_is_refused_before_attempt(self):
        self.prepare_d(register=False);before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.broker.dispatch('actual-D','input-D')
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)

    def test_changed_D_oracle_is_refused_before_attempt_and_never_resealed(self):
        self.prepare_d();p=self.c.registry_dir/'D-assertions.json';v=json.loads(p.read_text());v['expected']='changed oracle';p.write_text(L.encoded(v))
        before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.broker.dispatch('actual-D','input-D')
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)

    def test_new_root_cannot_reseal_reserved_D_input_and_old_root_replay_is_unchanged(self):
        self.prepare_d();registered=self.reports._one(self.c.key,'native_d_registration')
        self.assertEqual(self.c.ledger.create(self.c.ledger.snapshot(self.c.key)['contract']),self.c.key)
        new=copy.deepcopy(self.c.base);new['root_family']='new-root-exposed-D';new['budget']['authorization_sha256']=L.digest('different synthetic new authorization')
        new['holdout_cases']=[dict(input_sha256=registered['input_sha256'],source_family='B'),dict(input_sha256=L.digest('new B'),source_family='C'),dict(input_sha256=L.digest('new C'),source_family='C')]
        before=dump_store(self.c.store)
        with self.assertRaisesRegex(L.Conflict,'already exposed'):self.c.ledger.create(new)
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)

    def test_recaptured_prior_D_task_cannot_become_next_roots_new_holdout(self):
        self.prepare_d();registration=self.reports._one(self.c.key,'native_d_registration')
        recaptured=R.capture(self.c.store,self.project,self.c.store.ticket(registration['task_id']),tenant_id='default',history=[dict(role='user',body='changed earlier context')])
        directory=self.c.root/'next-catalog';directory.mkdir(mode=0o700);catalog=R.Catalog(directory,trusted_uid=os.getuid());self.addCleanup(catalog.close)
        values=[recaptured]
        for i in range(3):
            ticket=self.c.store.create_ticket(self.project['id'],'transaction callback next '+str(i),body='new actual next task '+str(i),type='bug',links={'flows':['fixture-flow']})
            values.append(R.capture(self.c.store,self.project,ticket,tenant_id='default',history=[]))
        hashes=[catalog.admit('input','next-'+str(i),v) for i,v in enumerate(values)]
        self.assertNotEqual(hashes[0],registration['input_sha256'])
        new=copy.deepcopy(self.c.base);new['root_family']='next-root-recapture';new['budget']['authorization_sha256']=L.digest('synthetic separate next plan')
        new['holdout_cases']=[dict(input_sha256=hashes[i],source_family='B' if i==0 else 'C') for i in range(3)]
        profile=copy.deepcopy(self.c.profile);profile['contract_sha256']=L.digest(new)
        p=self.c.registry_dir/'next.json';p.write_text(L.encoded(profile));p.chmod(0o600)
        key=self.c.adapter.register('next',new);broker=R.FiniteBroker(self.c.adapter,catalog,context=self.context,actor='owner')
        plan=dict(schema=R.VERSION,kind=broker.KIND,input_id='next-3',input_sha256=hashes[3],root_pool=key,contract_sha256=L.digest(self.c.ledger.snapshot(key)['contract']),request_id='next-A',phase='propose',policy='baseline',policy_sha256=R.sha(b'baseline'),broker_sha256=R.CODE_SHA256,source_family=new['training_family'])
        catalog.admit('plan','next-A',plan)
        before=dump_store(self.c.store)
        with self.assertRaisesRegex(L.Conflict,'previously exposed'):broker.dispatch('next-A','next-3')
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)
        self.assertEqual(self.c.ledger.inspect(key)['totals']['calls'],0)

    def test_actual_inflight_D_cancel_preserves_eighth_call_and_unknown_fence(self):
        self.prepare_d();self.c.seen.clear();self.c.wait=True;cancel=threading.Event();results=[];errors=[]
        def run():
            try:results.append(self.broker.dispatch('actual-D','input-D',cancel_event=cancel))
            except BaseException as error:errors.append(error)
        thread=threading.Thread(target=run);thread.start()
        try:
            self.assertTrue(self.c.seen.wait(3));self.assertEqual(self.c.count,8);cancel.set();thread.join(6)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[]);self.assertEqual(results[0]['state'],'unknown')
            self.assertTrue(self.c.ledger.inspect(self.c.key)['blocked']);self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['calls'],8)
            with self.assertRaises((ApiError,L.Conflict)):self.jobs.evaluate_followup(self.c.key)
            self.assertIsNone(self.reports._one(self.c.key,'native_d_evaluation_intent'))
            with self.assertRaises((ApiError,L.Conflict)):self.broker.dispatch('actual-D','input-D')
            self.assertEqual(self.c.count,8)
        finally:
            cancel.set();self.c.release.set();thread.join(6)

    def test_original_deadline_refuses_D_before_reservation_without_refresh(self):
        self.prepare_d();contract=self.c.ledger.snapshot(self.c.key)['contract']
        self.c.ledger.wall=lambda:contract['limits']['deadline_us']
        with self.assertRaises((ApiError,L.Conflict)):self.broker.dispatch('actual-D','input-D')
        self.assertIsNone(self.c.store.one('SELECT * FROM rsi_prepare_attempts WHERE pool=? AND request_id=?',(self.c.key,'actual-D')))
        self.assertEqual(self.c.ledger.inspect(self.c.key)['totals']['calls'],7);self.assertEqual(self.c.count,7)
        self.assertEqual(self.c.ledger.snapshot(self.c.key)['contract'],contract)

    def test_removed_own_D_row_cannot_hide_its_original_reservation(self):
        job,_,_=self.prepare_d();self.broker.dispatch('actual-D','input-D')
        self.c.store.db.execute('DELETE FROM rsi_prepare_attempts WHERE pool=? AND request_id=?',(self.c.key,'actual-D'));self.c.store.db.commit()
        with self.assertRaises(ApiError):N.verify(self.context,self.project,job,adopted=True,followup_request='actual-D')
        self.assertEqual(self.c.count,8)

    def test_unresolved_registered_execution_blocks_native_human_intent(self):
        job=self.jobs.publish(self.c.key,self.revision['id'])
        self.c.ledger.begin_isolation(self.c.key,'proposal','2'*64)
        before=dump_store(self.c.store)
        with self.assertRaises(ApiError):D.decide(self.context,self.project,'adopt',self.revision['id'],'owner','synthetic-unresolved-execution',None,self.reference(),job['id'])
        self.assertEqual(before,dump_store(self.c.store));self.assertIsNone(learn.active_revision(self.c.root,self.revision['origin_id']))
        self.assertEqual(self.c.count,7)


@unittest.skipUnless(os.name=='posix','actual native fixture requires POSIX')
class EightCallNativeJobTests(unittest.TestCase):
    def test_D_eighth_call_exhausts_original_plan_without_new_root(self):
        f=NativeJobBridgeTests('test_actual_selected_new_D_uses_same_root_and_evaluates_original_only_once');f.max_calls=8
        f.setUp();self.addCleanup(f.doCleanups)
        (f.c.root/'outer-test-label.json').write_text(json.dumps({'test':self.id()}))
        f.prepare_d();pools=len(f.c.store.q('SELECT pool FROM rsi_prepare_pools'))
        self.assertTrue(f.broker.dispatch('actual-D','input-D')['response_complete'])
        self.assertTrue(f.jobs.evaluate_followup(f.c.key)['assertions']['passed'])
        self.assertEqual(f.c.count,8);self.assertEqual(f.c.ledger.inspect(f.c.key)['totals']['calls'],8)
        self.assertIn('call_limit_reached',f.c.ledger.inspect(f.c.key)['execution_plan']['block_reasons'])
        with self.assertRaises(L.Conflict):f.c.ledger.reserve(f.c.key,'ninth','probe',1,1,material_sha256='1'*64)
        self.assertEqual(len(f.c.store.q('SELECT pool FROM rsi_prepare_pools')),pools);self.assertEqual(f.c.count,8)


if __name__=='__main__':unittest.main()
