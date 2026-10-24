"""Versioned lesson content and obsolete execution retain legacy manual evidence."""
import copy
import json
import time
import unittest
import uuid
from unittest.mock import patch

from tests import test_learning_lesson_inputs as fixtures
from tmh.platform import learning as L, learning_eval as E, learning_runs as R, learn
from tmh.platform.errors import ApiError
from tmh.platform.store import now


def _legacy_revision(self):
    item=L._origin(self.P,self.p,'lesson:'+self.card['id'],lesson_schema=None)
    source=dict(self.r['source']);source.pop('lesson_content_schema')
    source['origin_fingerprint']=item['fingerprint']
    with L.transaction(self.store) as db:rid=L._save(db,self.p,item,source,'legacy')
    return L.revision(self.P,self.p,rid)


def _legacy_job(self,status='queued'):
    r=_legacy_revision(self)
    body={'max_calls':6,'timeout_seconds':60}
    frozen={'prompt_version':E.PROMPT_VERSION,'baseline':E._baseline(self.P,self.p,r),
            'candidate_revision_id':r['id'],'candidate_content':r['content'],'cases':[],'packs':{},'evidence':[],
            'min_holdout':3,'max_prompt_ratio':2.,'max_extra_input_chars_per_case':1024,'max_output_ratio':2.,'seed':1}
    opts=dict(body,evaluation=frozen)
    jid=uuid.uuid4().hex;request=uuid.uuid4().hex
    request_hash=R._hash(R._json({'kind':'evaluate','revision_id':r['id'],'options':body,'actor':'operator'}))
    self.store.x('INSERT INTO learning_jobs(id,project_id,kind,revision_id,current_revision_id,request_id,request_hash,actor,status,options,binding,created,deadline,result) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 (jid,self.p['id'],'evaluate',r['id'],r['id'],request,request_hash,'operator',status,R._json(opts),R._json(L.binding(self.P,self.p)),now(),time.time()+60,R._json({'passed':True})))
    return r,jid,request,body


class InputCompatibilityTests(unittest.TestCase):
    setUp = fixtures.LessonInputsTests.setUp
    capture = fixtures.LessonInputsTests.capture

    def test_legacy_source_literal_and_new_null_partial_proposals(self):
        legacy=_legacy_revision(self)
        self.assertTrue(L.revision_current(self.P,self.p,legacy))
        before=dict(self.store.one('SELECT * FROM learning_revisions WHERE id=?',(legacy['id'],)))
        proposal=L.propose(self.P,self.p,self.r['id'],L.encoded({'fix':'新的幂等处理'}),'writer')
        value=json.loads(proposal['content'])
        self.assertNotIn('anti',value);self.assertIsNone(value['cause'])
        self.assertEqual(self.store.one('SELECT * FROM learning_revisions WHERE id=?',(legacy['id'],)),before)
        self.assertTrue(L.revision_current(self.P,self.p,legacy))


    def test_legacy_terminal_manual_currentness_and_evidence_scope(self):
        r,jid,_,_=_legacy_job(self,'passed')
        before=self.store.one('SELECT * FROM learning_jobs WHERE id=?',(jid,))
        job=R.get(self.P,self.p,jid)
        self.assertTrue(E.current(self.P,self.p,job))
        self.assertFalse(job['input_contract']['executable'])
        self.assertEqual(job['evidence_scope']['input_scope'],'legacy-v1')
        self.assertFalse(job['evidence_scope']['rsi_qualified'])
        self.assertFalse(R._expire_input(self.P,self.p,jid))
        self.assertEqual(before,self.store.one('SELECT * FROM learning_jobs WHERE id=?',(jid,)))


    def test_obsolete_resume_and_idempotent_queued_replay_release_active_slot(self):
        for entry in ('resume','replay','recover'):
            r,jid,request,body=_legacy_job(self)
            before=self.store.one('SELECT * FROM learning_jobs WHERE id=?',(jid,))
            with patch.object(R.threading,'Thread',side_effect=AssertionError('obsolete thread started')):
                if entry=='resume':
                    with self.assertRaises(ApiError) as caught:R.resume(self.P,self.p,jid,'operator')
                    self.assertEqual(caught.exception.reason,'input_schema_expired')
                elif entry=='replay':R.start(self.P,self.p,'evaluate',r['id'],body,'operator',request,launch=True)
                else:R.recover(self.P)
            after=self.store.one('SELECT * FROM learning_jobs WHERE id=?',(jid,))
            self.assertEqual(after['status'],'stale');self.assertIn('input_schema_expired',after['error'])
            for key in ('options','binding','deadline','calls','result'):self.assertEqual(after[key],before[key])
            self.assertEqual(self.store.q('SELECT * FROM learning_steps WHERE job_id=?',(jid,)),[])


    def test_unknown_content_schema_is_not_treated_as_legacy(self):
        for value in ('future','lesson-content-v1'):
            with self.assertRaises(ApiError):L.lesson_content({'title':'x'},value)
        self.assertEqual(L.lesson_content({'title':'x'},None),L.lesson_content({'title':'x'},''))

    def test_old_job_cannot_be_expired_while_real_owner_kernel_lock_is_held(self):
        import subprocess
        import sys
        r,jid,_,_=_legacy_job(self)
        folder=R._folder(self.P,jid);folder.mkdir(parents=True)
        code="from tmh.platform import filelock;import sys;f=open(sys.argv[1],'a+b');filelock.try_lock(f);print('held',flush=True);sys.stdin.read(1)"
        proc=subprocess.Popen([sys.executable,'-c',code,str(folder/'owner.lock')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(),'held')
            self.assertFalse(R._expire_input(self.P,self.p,jid))
            self.assertEqual(R.get(self.P,self.p,jid)['status'],'queued')
        finally:
            proc.communicate('x',timeout=3)
        self.assertEqual(proc.returncode,0)
        self.assertTrue(R._expire_input(self.P,self.p,jid))
        self.assertEqual(R.get(self.P,self.p,jid)['status'],'stale')

    def test_unknown_and_malformed_contracts_never_claim_v2_or_raise_read_errors(self):
        for value in (None,[],42,{}, {'schema':'unknown'}):
            r,jid,_,_=_legacy_job(self,'passed')
            self.store.x('UPDATE learning_jobs SET options=? WHERE id=?',(R._json({'evaluation':value}),jid))
            before=self.store.one('SELECT * FROM learning_jobs WHERE id=?',(jid,))
            job=R.get(self.P,self.p,jid)
            self.assertFalse(E.current(self.P,self.p,job))
            self.assertFalse(job['input_contract']['executable'])
            self.assertEqual(job['evidence_scope']['input_scope'],'unknown')
            self.assertFalse(job['evidence_scope']['knowledge_block_same_renderer'])
            self.assertEqual(before,self.store.one('SELECT * FROM learning_jobs WHERE id=?',(jid,)))
