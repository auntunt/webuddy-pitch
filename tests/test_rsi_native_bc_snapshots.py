"""Executed ordinary retirement/reservation interleavings; no human-race claims."""
from contextlib import contextmanager
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from tests import test_rsi_native_bc_report as T
from tmh.platform import learn, learning_decisions as D
from scripts.rsi import trial_preparation as L


@unittest.skipUnless(os.name=='posix','native private registry and real file locks require POSIX')
class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.f=T.NativeReportTests('test_original_two_arm_assertions_execute_in_supervised_worker_and_replay_without_http')
        self.f.setUp();self.addCleanup(self.f.doCleanups);self.f.freeze();self.f.run_arms();self.c=self.f.c

    def adopted(self,report):
        decide=D.decide
        reference=L.encoded(dict(schema='native-bc-decision-reference-v1',root_pool=self.c.key,native_report_sha256=report['report_sha256'],reason='synthetic exact report reference'))
        def referenced(context,project,action,rid,actor,request,active,reason,job):return decide(context,project,action,rid,actor,request,active,reference,job)
        with patch.object(D,'decide',side_effect=referenced):return self.f.f.adopted_fixture()

    def test_retirement_after_final_observations_cannot_commit_a_passed_report(self):
        reports=self.f.reports;guard=reports._guard
        block=next(m['block'] for m in self.f.f.caps[0]['source']['context'] if m.get('mode')=='learning_lessons');selected=block['bindings'][0]['id']
        @contextmanager
        def retire(c):
            learn.set_status(self.c.root,selected,'retired','synthetic-owner','actual selected lesson retired after observations')
            with guard(c):yield
        try:
            with patch.object(reports,'_guard',side_effect=retire),self.assertRaises(L.Conflict):reports.evaluate(self.c.key)
            self.assertIsNone(reports._one(self.c.key,'native_bc_report'))
            self.assertIsNotNone(reports._one(self.c.key,'native_bc_evaluation_intent'))
            with patch.object(T.B.SP,'run_supervised',side_effect=AssertionError('never repeat the evaluator')):
                with self.assertRaises(L.Conflict):reports.evaluate(self.c.key)
            self.assertEqual(self.c.count,7)
        finally:
            (self.c.root/'retirement-proof.json').write_text(json.dumps(dict(report=reports._one(self.c.key,'native_bc_report'),intent=reports._one(self.c.key,'native_bc_evaluation_intent'),selected=learn.lesson(self.c.root,selected),http_calls=self.c.count),ensure_ascii=False,indent=2))

    def test_reservation_after_report_read_before_personal_snapshot_refuses_reference(self):
        reports=self.f.reports;report=reports.evaluate(self.c.key);adoption=self.adopted(report);snapshot=reports._decision_snapshot
        @contextmanager
        def arriving(c,context):
            self.c.ledger.reserve(self.c.key,'late-reference-probe','probe',100,20,material_sha256='1'*64)
            with snapshot(c,context):yield
        try:
            with patch.object(reports,'_decision_snapshot',side_effect=arriving),self.assertRaises(L.Conflict):reports.decision_link(self.c.key,adoption['decision_id'])
            self.assertEqual(self.c.count,7)
            self.assertEqual(self.c.ledger.inspect(self.c.key)['token_budget']['reserved_or_unknown'],120)
        finally:
            (self.c.root/'decision-frontier-proof.json').write_text(json.dumps(dict(report=report,adoption=adoption,attempts=self.c.store.q('SELECT * FROM rsi_prepare_attempts WHERE pool=? ORDER BY request_id',(self.c.key,)),http_calls=self.c.count),ensure_ascii=False,indent=2))

    def test_knowledge_lock_is_held_through_the_actual_report_commit(self):
        reports=self.f.reports;raw=self.c.store.db;guard=reports._guard;armed=[False];observed=[];case=self
        code='import fcntl,sys\nf=open(sys.argv[1],"r+b")\ntry:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError:sys.exit(73)\nsys.exit(0)\n'
        class Proxy:
            def __getattr__(self,name):return getattr(raw,name)
            def commit(self):
                if armed[0] and raw.in_transaction:
                    p=subprocess.run([sys.executable,'-I','-B','-c',code,str(case.c.root/'lessons.lock')],capture_output=True,timeout=3)
                    observed.append(p.returncode);case.assertEqual(p.returncode,73,p.stderr)
                return raw.commit()
        @contextmanager
        def final_guard(c):
            armed[0]=True
            try:
                with guard(c):yield
            finally:armed[0]=False
        self.c.store.db=Proxy()
        try:
            with patch.object(reports,'_guard',side_effect=final_guard):result=reports.evaluate(self.c.key)
            self.assertTrue(result['assertions']['passed']);self.assertEqual(observed,[73]);self.assertEqual(self.c.count,7)
        finally:self.c.store.db=raw


if __name__=='__main__':unittest.main()
