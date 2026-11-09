import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from tmh.platform.store import Store
from tmh.platform import review_feedback as F
from tmh.platform.errors import ApiError

class ReviewFeedbackTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.data=Path(temp.name);self.store=Store(self.data/'platform.db');self.addCleanup(self.store.db.close)
        self.P=SimpleNamespace(store=self.store,data_dir=self.data)
        p=self.store.add_project('R','Review',str(self.data));self.pid=p['id']
        r=self.store.create_run(p['id'],None,'codex','fix','alice','')
        self.store.update_run(r['id'],status='done',exit_code=0)
        self.run=self.store.run(r['id']);self.folder=self.data/'runs'/str(r['id']);self.folder.mkdir(parents=True)
        self.verification={'diagnosis':{'review':{'base':'a'*40,'diff_sha256':'b'*64,'created':'2026-11-06'},'blocking':[{'scenario':'金额符号错误'}],'advisory':['重复代码']}}
        self.write()
    def write(self):
        (self.folder/'verify.json').write_text(json.dumps(self.verification))
    def body(self):
        return {'request_id':'request-1','binding':F.snapshot(self.verification)['binding'],'minutes':12,
                'findings':[{'id':'blocking:0','verdict':'valid','reason':'实际保存负数失败'},
                            {'id':'advisory:0','verdict':'false_positive','reason':'两处遵守不同接口契约'}],
                'missed':['人工发现分摊金额不一致仍可保存'],'note':'人工检查金额保存、回读；合成测试记录'}
    def test_records_are_idempotent_and_do_not_accept_work(self):
        before=self.store.run(self.run['id']);body=self.body()
        a=F.save(self.P,self.run,'alice',body);b=F.save(self.P,self.run,'alice',body)
        self.assertEqual(a,b);self.assertEqual(self.store.run(self.run['id']),before)
        result=F.summary(self.P,self.pid)
        self.assertEqual((result['valid'],result['false_positive'],result['missed'],result['minutes']),(1,1,1,12))
        self.assertIsNone(result['saved_minutes'])
        body['minutes']=20
        with self.assertRaises(ApiError):F.save(self.P,self.run,'alice',body)
    def test_latest_per_reviewer_without_double_counting_history(self):
        body=self.body();F.save(self.P,self.run,'alice',body)
        body.update(request_id='request-2',minutes=18);F.save(self.P,self.run,'alice',body)
        result=F.summary(self.P,self.pid)
        self.assertEqual((result['observations'],result['minutes']),(1,18))
        self.assertEqual(len(F.view(self.P,self.run,self.verification)['records']),2)
    def test_changed_review_rejects_old_save_and_removes_current_totals(self):
        body=self.body();F.save(self.P,self.run,'alice',body)
        self.verification['diagnosis']['blocking'][0]['scenario']='不同问题';self.write()
        body['request_id']='new'
        with self.assertRaises(ApiError) as e:F.save(self.P,self.run,'alice',body)
        self.assertEqual(e.exception.code,409)
        self.assertEqual(F.summary(self.P,self.pid)['observations'],0)
        self.assertFalse(F.view(self.P,self.run,self.verification)['records'][0]['current'])
    def test_invalidation_unassessed_and_empty_are_not_success(self):
        self.assertIsNone(F.summary(self.P,self.pid)['minutes'])
        self.assertIsNone(F.snapshot(dict(self.verification,diagnosis_invalidated='code changed')))
        body=self.body()
        for f in body['findings']:f.update(verdict='unassessed',reason='')
        F.save(self.P,self.run,'alice',body)
        result=F.summary(self.P,self.pid)
        self.assertEqual(result['unassessed'],2);self.assertIsNone(result['valid_rate'])
    def test_rejects_agent_missing_finding_or_unexplained_verdict(self):
        with self.assertRaises(ApiError):F.save(self.P,self.run,'agent:codex',self.body())
        for mutation in ('missing','reason','minutes','duplicate','invalid_id'):
            body=self.body()
            if mutation=='missing':body['findings'].pop()
            if mutation=='reason':body['findings'][0]['reason']=''
            if mutation=='minutes':body['minutes']=True
            if mutation=='duplicate':body['findings'].append(copy.deepcopy(body['findings'][0]))
            if mutation=='invalid_id':body['findings'][0]['id']=[]
            with self.assertRaises(ApiError):F.save(self.P,self.run,'alice',body)
    def test_project_summary_does_not_include_another_project(self):
        F.save(self.P,self.run,'alice',self.body())
        p=self.store.add_project('OTHER','Other',str(self.data))
        self.assertEqual(F.summary(self.P,p['id'])['observations'],0)
