"""Real supervised assertion worker over loopback originals, never real quality."""
import copy
from contextlib import contextmanager
import os
import shutil
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_rsi_native_registered as N
from scripts.rsi import native_bc_report as B, trial_preparation as L
from scripts.rsi import native_bc_worker as W
from tests.sqlite_snapshot import dump_store


@unittest.skipUnless(os.name=='posix','native private registry and supervised worker require POSIX')
class NativeReportTests(unittest.TestCase):
    def setUp(self):
        self.f=N.NativeRegisteredTests('test_two_arms_use_same_complete_capture_original_root_and_derived_policy')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.authorize_context();self.c=self.f.c
        self.reports=B.Reports(self.f.broker,self.c.root/'bc-reports')
        self.spec={'schema':B.VERSION,'root_pool':self.c.key,'contract_sha256':L.digest(self.c.ledger.snapshot(self.c.key)['contract']),
                   'authorization_sha256':self.c.base['budget']['authorization_sha256'],
                   'cases':[dict(input_id='input-'+str(i),input_sha256=self.f.input_hashes[i],source_family=self.c.base['holdout_cases'][i]['source_family'],
                                 validator='exact',expected=self.c.policy,forbidden=[]) for i in range(3)],
                   'thresholds':dict(min_pairs=3,min_improvement=1,require_candidate_all=True,allow_regressions=False)}
        self.write_spec()

    def write_spec(self):
        p=self.c.registry_dir/'assertions.json';p.write_text(L.encoded(self.spec));p.chmod(0o600)

    def freeze(self):return self.reports.freeze(self.c.key,'assertions')

    def run_arms(self,improve=True):
        self.f.propose()
        for i in range(3):
            self.c.response['content'][0]['text']='baseline missing assertion' if improve else self.c.policy
            self.f.send('B'+str(i),phase='baseline',input_index=i)
            self.c.response['content'][0]['text']=self.c.policy
            self.f.send('C'+str(i),phase='candidate',input_index=i,policy=self.c.policy)

    def test_original_two_arm_assertions_execute_in_supervised_worker_and_replay_without_http(self):
        self.freeze();self.run_arms();before=self.c.ledger.inspect(self.c.key)['totals'];report=self.reports.evaluate(self.c.key)
        self.assertTrue(report['assertions']['passed']);self.assertEqual(report['assertions']['counts'],dict(baseline=0,candidate=3))
        self.assertEqual(len(report['origins']),6);self.assertEqual(len(report['frontier']),7)
        self.assertEqual(report['source_mode'],'fixture');self.assertFalse(report['rsi_qualified']);self.assertFalse(report['human_adoption'])
        self.assertEqual(before,self.c.ledger.inspect(self.c.key)['totals']);self.assertEqual(self.c.count,7)
        receipt=B.SP.read_receipt(self.reports.root/self.c.key)
        self.assertEqual(receipt['returncode'],0);self.assertTrue(receipt['cleanup']['complete']);self.assertFalse(receipt['cleanup']['remaining_group'])
        with patch.object(B.SP,'run_supervised',side_effect=AssertionError('do not repeat evaluation')):
            self.assertEqual(report,self.reports.evaluate(self.c.key));self.assertEqual(report,self.reports.read(self.c.key))
        self.assertEqual(self.c.count,7)

    def test_late_registration_cannot_backfill_after_proposal(self):
        # The response exists, but candidate binding has NOT happened yet.
        # This isolates the no-prior-attempt gate from the later binding gate.
        self.f.send('proposal');before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.freeze()
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,1)

    def test_no_registration_or_changed_thresholds_cannot_qualify(self):
        with self.assertRaises(L.Conflict):self.reports.evaluate(self.c.key)
        self.freeze();self.run_arms();self.spec['thresholds']['min_improvement']=2;self.write_spec();before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.reports.evaluate(self.c.key)
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)

    def test_complete_universe_and_nonweakened_explicit_thresholds(self):
        original=copy.deepcopy(self.spec)
        changes=[lambda s:s['cases'].pop(),lambda s:s['cases'].__setitem__(1,copy.deepcopy(s['cases'][0])),
                 lambda s:s['thresholds'].__setitem__('min_improvement',0),lambda s:s['thresholds'].__setitem__('allow_regressions',True),
                 lambda s:s['thresholds'].__setitem__('min_pairs',True),lambda s:s.__setitem__('authorization_sha256','0'*64)]
        for i,change in enumerate(changes):
            self.spec=copy.deepcopy(original);change(self.spec);self.write_spec();before=dump_store(self.c.store)
            with self.subTest(i=i),self.assertRaises(ValueError):self.freeze()
            self.assertEqual(before,dump_store(self.c.store))
        self.assertEqual(self.c.count,0)

    def test_all_pairs_passing_without_improvement_is_not_qualified(self):
        self.freeze();self.run_arms(improve=False);report=self.reports.evaluate(self.c.key)
        self.assertEqual(report['assertions']['counts'],dict(baseline=3,candidate=3));self.assertFalse(report['assertions']['passed'])
        self.assertFalse(report['rsi_qualified']);self.assertEqual(self.c.count,7)

    def test_fixed_worker_rejects_no_improvement_and_any_regression(self):
        value={'cases':[dict(input_sha256=str(i)*64,validator='exact',expected='pass',forbidden=[],baseline='pass',candidate='pass') for i in range(3)],
               'thresholds':self.spec['thresholds']}
        self.assertFalse(W.evaluate(value)['passed'])
        value['cases'][0]['candidate']='fail'
        result=W.evaluate(value);self.assertFalse(result['passed']);self.assertEqual(result['regressions'],['0'*64])

    def test_personal_reference_to_another_report_is_rejected_without_rewriting_the_decision(self):
        from tmh.platform import learning_decisions as D
        self.freeze();self.run_arms();self.reports.evaluate(self.c.key);decide=D.decide
        reference=L.encoded(dict(schema='native-bc-decision-reference-v1',root_pool=self.c.key,native_report_sha256='0'*64,reason='synthetic mismatched report'))
        def referenced(context,project,action,rid,actor,request,active,reason,job):
            return decide(context,project,action,rid,actor,request,active,reference,job)
        with patch.object(D,'decide',side_effect=referenced):adoption=self.f.adopted_fixture()
        before=dump_store(self.c.store)
        with self.assertRaises(L.Conflict):self.reports.decision_link(self.c.key,adoption['decision_id'])
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)

    def test_missing_arm_or_unknown_attempt_refuses_without_evaluator_launch(self):
        self.freeze();self.f.propose()
        with patch.object(B.SP,'run_supervised',side_effect=AssertionError('no incomplete evaluation')):
            with self.assertRaises(L.Conflict):self.reports.evaluate(self.c.key)
        self.c.response['usage']['output_tokens']=None
        self.f.send('B',phase='baseline',input_index=0)
        before=dump_store(self.c.store)
        with patch.object(B.SP,'run_supervised',side_effect=AssertionError('no unknown evaluation')):
            with self.assertRaises(L.Conflict):self.reports.evaluate(self.c.key)
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.ledger.inspect(self.c.key)['token_budget']['reserved_or_unknown'],120)

    def test_changed_original_provider_response_is_not_semantic_evidence(self):
        self.freeze();self.run_arms()
        output=self.c.adapter._folder(self.c.key,'C0')/'transport/output.bin';output.write_bytes(output.read_bytes()+b'changed')
        with self.assertRaises(ValueError):self.reports.evaluate(self.c.key)
        self.assertIsNone(self.reports._one(self.c.key,'native_bc_evaluation_intent'));self.assertEqual(self.c.count,7)

    def test_changed_original_evaluator_output_is_not_a_report(self):
        self.freeze();self.run_arms();self.reports.evaluate(self.c.key)
        output=self.reports.root/self.c.key/'output.bin';output.write_bytes(output.read_bytes()+b'changed')
        with self.assertRaises(ValueError):self.reports.read(self.c.key)
        self.assertEqual(self.c.count,7)

    def test_unknown_evaluator_does_not_rerun_or_create_a_passed_report(self):
        self.freeze();self.run_arms()
        with patch.object(B.SP,'run_supervised',side_effect=RuntimeError('synthetic controller loss')):
            with self.assertRaises(RuntimeError):self.reports.evaluate(self.c.key)
        with patch.object(B.SP,'run_supervised',side_effect=AssertionError('no unknown rerun')):
            with self.assertRaises(L.Conflict):self.reports.evaluate(self.c.key)
        self.assertIsNone(self.reports._one(self.c.key,'native_bc_report'));self.assertEqual(self.c.count,7)

    def test_personal_exact_report_reference_is_readonly_and_never_grants_live_d_from_an_ordinary_job(self):
        from tmh.platform import learning_decisions as D
        self.freeze();self.run_arms();report=self.reports.evaluate(self.c.key);decide=D.decide
        reference=L.encoded(dict(schema='native-bc-decision-reference-v1',root_pool=self.c.key,
                                 native_report_sha256=report['report_sha256'],reason='synthetic exact report reference'))
        def referenced(context,project,action,rid,actor,request,active,reason,job):
            return decide(context,project,action,rid,actor,request,active,reference,job)
        with patch.object(D,'decide',side_effect=referenced):adoption=self.f.adopted_fixture()
        before=dump_store(self.c.store);link=self.reports.decision_link(self.c.key,adoption['decision_id'])
        self.assertTrue(link['reference_verified']);self.assertEqual(link['native_report_sha256'],report['report_sha256'])
        self.assertFalse(link['job_native_provenance_verified']);self.assertFalse(link['live_d_eligible']);self.assertFalse(link['rsi_qualified'])
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)
        D.decide(self.f.context,self.f.project,'revoke',adoption['revision_id'],'owner','synthetic-report-revoke',adoption['revision_id'],'synthetic withdrawal')
        with self.assertRaises(L.Conflict):self.reports.decision_link(self.c.key,adoption['decision_id'])

    def test_an_ordinary_personal_passed_report_cannot_be_relabelled_as_this_native_report(self):
        self.freeze();self.run_arms();self.reports.evaluate(self.c.key);adoption=self.f.adopted_fixture();before=dump_store(self.c.store)
        with self.assertRaises(ValueError):self.reports.decision_link(self.c.key,adoption['decision_id'])
        self.assertEqual(before,dump_store(self.c.store));self.assertEqual(self.c.count,7)

    def test_attempt_arriving_at_final_commit_cannot_be_omitted_from_a_passed_report(self):
        self.freeze();self.run_arms();original=self.reports._guard
        @contextmanager
        def arriving(c):
            self.c.ledger.reserve(self.c.key,'late-probe','probe',100,20,material_sha256='1'*64)
            with original(c):yield
        with patch.object(self.reports,'_guard',side_effect=arriving),self.assertRaises(L.Conflict):self.reports.evaluate(self.c.key)
        self.assertIsNone(self.reports._one(self.c.key,'native_bc_report'))
        self.assertEqual(self.c.ledger.inspect(self.c.key)['token_budget']['reserved_or_unknown'],120);self.assertEqual(self.c.count,7)

    def test_report_event_failure_keeps_original_intent_and_never_reruns_worker(self):
        self.freeze();self.run_arms();original=self.c.ledger._event
        def fail(db,key,request,kind,value):
            if kind=='native_bc_report':raise RuntimeError('synthetic report commit loss')
            return original(db,key,request,kind,value)
        with patch.object(self.c.ledger,'_event',side_effect=fail),self.assertRaises(RuntimeError):self.reports.evaluate(self.c.key)
        self.assertIsNone(self.reports._one(self.c.key,'native_bc_report'))
        with patch.object(B.SP,'run_supervised',side_effect=AssertionError('no rerun after commit loss')):
            with self.assertRaises(L.Conflict):self.reports.evaluate(self.c.key)
        self.assertEqual(self.c.count,7)

    def test_evaluator_does_not_write_bytecode_in_a_fresh_import_tree(self):
        source=Path(B.__file__).resolve().parents[2];clone=self.c.root/'fresh-import-tree';clone.mkdir()
        for old in (source/'tmh').rglob('*.py'):
            target=clone/old.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old,target)
        for name in ('scripts/rsi/trial_preparation.py','scripts/rsi/native_bc_worker.py'):
            target=clone/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
        worker=clone/'scripts/rsi/native_bc_worker.py'
        self.assertEqual(worker.read_bytes(),B.WORKER.read_bytes());self.assertEqual(list(clone.rglob('*.pyc')),[])
        with patch.object(B,'WORKER',worker):
            self.freeze();self.run_arms();self.assertTrue(self.reports.evaluate(self.c.key)['assertions']['passed'])
        self.assertEqual(list(clone.rglob('*.pyc')),[])


if __name__=='__main__':unittest.main()
