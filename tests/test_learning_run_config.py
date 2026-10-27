"""Project-scoped frozen configuration plumbing, with real synthetic CLI processes.

Only the capability handshake is stubbed in process tests. This cannot admit
real Codex: the production capability function still refuses its model path.
"""
import copy
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh.platform import learning, learning_runs as lr
from tmh.platform.store import Store
from tests.test_learning_runs import PAGE


SYNTHETIC = r'''
import json,os,sys,time
from pathlib import Path
root=Path(__file__).parent
args=sys.argv[1:]
assert args[-1]=='-'
prompt=sys.stdin.read()
with (root/'calls.jsonl').open('a') as out:
    out.write(json.dumps({'args':args,'prompt':prompt,'pid':os.getpid()})+'\n')
    out.flush();os.fsync(out.fileno())
ready=root/'ready.pending';ready.write_text(str(os.getpid()));ready.replace(root/'ready')
while (root/'pause').exists():time.sleep(.02)
d=json.loads(prompt.split('待审数据 JSON：\n',1)[1]);e=d['source']['evidence'][0]
answer={'claims':[{'id':c['id'],'verdict':'supported','kind':'code','reason':'Synthetic supplied input',
                  'evidence':[{'path':e['path'],'sha256':e['sha256'],'start':1,'end':1,'quote':e['content'].splitlines()[0]}]}
                 for c in d['claims']],'summary':'Synthetic configuration test only'}
print(json.dumps({'type':'thread.started','thread_id':'synthetic-config-thread'}),flush=True)
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps(answer)}}),flush=True)
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':3,'output_tokens':2}}),flush=True)
'''


class LearningRunConfigTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='tmh-config-review-')
        self.addCleanup(temp.cleanup)
        self.home=Path(temp.name).resolve();self.data=self.home/'data';self.root=self.home/'project';self.root.mkdir()
        (self.root/'app.py').write_text('STATUS = "OPEN"\n# 完整公开证据\n')
        page=self.root/'.tmh/knowledge/index.md';page.parent.mkdir(parents=True);page.write_text(PAGE)
        self.exe=self.home/'synthetic-cli';self.exe.write_text('#!'+sys.executable+'\n'+SYNTHETIC);self.exe.chmod(0o700)
        self.store=Store(self.data/'platform.db');self.addCleanup(self.store.db.close)
        learning.schema(self.store);lr.schema(self.store)
        self.p=self.store.add_project('CFG','配置回归',str(self.root));self.P=SimpleNamespace(store=self.store,data_dir=self.data)
        self.config={'engine':'codex','bin':str(self.exe),'args':[],'profile':'fixed-public-profile','prompt_transport':'stdin',
                     'resume':False,'retry_busy':False,'timeout':2,'defaults':{'ask':'synthetic-model'},'private_note':'SYNTHETIC_NOT_FOR_RECEIPT'}
        self.save_config()
        self.route={'schema':1,'projects':{'CFG':{'agent':'team-codex','allowed_agents':['team-codex'],'direct_api':False}}};self.save_route()
        self.revision=learning.capture(self.P,self.p,'fact:index',learning.digest(PAGE),'author')
        self.cap=mock.patch.object(lr,'_capabilities',return_value=['synthetic-isolation-handshake-only']);self.cap.start();self.addCleanup(self.cap.stop)
        # Optional evidence retention belongs only to these public synthetic tests.
        self.addCleanup(self.retain)

    def retain(self):
        target=os.environ.get('TMH_CONFIG_TEST_SCENES')
        if not target:return
        dest=Path(target)/self._testMethodName
        shutil.copytree(self.home,dest,ignore=shutil.ignore_patterns('platform.db','platform.db-wal','platform.db-shm'))
        saved=sqlite3.connect(dest/'data/platform.db')
        try:self.store.db.backup(saved)
        finally:saved.close()

    def save_config(self):
        (self.data/'agents.json').write_text(json.dumps({'team-codex':self.config,'claude':{'bin':sys.executable,'args':[]}}))

    def save_route(self):
        (self.data/'agent-routes.json').write_text(json.dumps(self.route))

    def start(self,**options):
        return lr.start(self.P,self.p,'review',self.revision['id'],dict(timeout_seconds=15,**options),'operator','single-config-request',launch=False)

    def work(self,job):
        lr._work(self.P,self.p,job['id']);return lr.get(self.P,self.p,job['id'])

    def calls(self):
        path=self.home/'calls.jsonl';return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_route_selects_and_freezes_effective_settings_without_unknown_fields(self):
        job=self.start();opts=job['options'];f=opts['configuration']
        self.assertEqual(opts['agent'],'team-codex');self.assertEqual(opts['model'],'synthetic-model')
        for key in ('engine','profile','prompt_transport','resume','retry_busy','timeout'):self.assertEqual(f[key],self.config[key])
        self.assertEqual(f['sha256'],hashlib.sha256(self.exe.read_bytes()).hexdigest())
        self.assertNotIn('SYNTHETIC_NOT_FOR_RECEIPT',json.dumps(opts))
        conf=lr._execution_config(job);conf['team-codex']['args'].append('not-frozen')
        self.assertEqual(opts['configuration']['args'],[])
        self.assertLessEqual(conf['team-codex']['run_timeout'],2)
        other=self.store.add_project('OTHER','其他项目',str(self.root))
        self.assertEqual(lr._configuration(self.P,{},other)['agent'],'claude')
        with self.assertRaises(ValueError):self.start(agent='claude')
        self.assertEqual(self.calls(),[])

    def test_real_capability_guard_still_refuses_codex_before_registration_or_help(self):
        self.cap.stop()
        with mock.patch.object(lr.subprocess,'run',side_effect=AssertionError('No metadata/help/model allowed')):
            with self.assertRaisesRegex(ValueError,'外部上下文'):self.start()
        self.assertEqual(self.store.q('SELECT * FROM learning_jobs'),[])
        self.assertEqual(self.calls(),[])

    def test_real_synthetic_cli_gets_full_stdin_profile_and_strict_terminal_receipt(self):
        job=self.start();deadline=job['deadline'];done=self.work(job)
        self.assertEqual(done['status'],'passed',done['error']);self.assertEqual(done['deadline'],deadline)
        self.assertEqual(done['calls'],1);call=self.calls()[0];step=done['steps'][0]
        self.assertEqual(call['prompt'],step['prompt']);self.assertNotIn(step['prompt'],call['args'])
        self.assertEqual(call['args'][-1],'-');self.assertIn('--json',call['args'])
        self.assertEqual(call['args'][call['args'].index('--profile')+1],'fixed-public-profile')
        self.assertEqual(call['args'][call['args'].index('-m')+1],'synthetic-model')
        self.assertNotIn('--tools',call['args']);self.assertNotIn('resume',call['args'])
        life=lr._sealed_run(self.P,step['run_id']);self.assertEqual(len(life['attempts']),1);self.assertTrue(life['attempts'][0]['cleanup']['complete'])
        raw=(self.data/'runs'/str(step['run_id'])/'attempts/0001/output.bin').read_bytes()
        self.assertEqual(step['raw_output'],raw.decode());self.assertIn(b'turn.completed',raw)
        self.assertEqual(done['result']['human_confirmation'],'pending');self.assertEqual(self.store.q('SELECT * FROM learning_decisions'),[])

    def test_profile_change_before_dispatch_stales_without_start_or_new_budget(self):
        job=self.start();self.config['profile']='other-public-profile';self.save_config();done=self.work(job)
        self.assertEqual(done['status'],'stale',done['error']);self.assertEqual(done['calls'],0);self.assertEqual(done['deadline'],job['deadline']);self.assertEqual(self.calls(),[])

    def test_route_revocation_before_dispatch_stales_without_fallback(self):
        job=self.start();self.route['projects']['CFG']={'agent':'claude','allowed_agents':['claude']};self.save_route();done=self.work(job)
        self.assertEqual(done['status'],'stale',done['error']);self.assertEqual(done['calls'],0);self.assertEqual(self.calls(),[])

    def test_original_job_cancel_stops_real_synthetic_process_and_keeps_one_attempt(self):
        (self.home/'pause').write_text('public synthetic pause');job=self.start()
        thread=threading.Thread(target=lr._work,args=(self.P,self.p,job['id']));thread.start()
        try:
            until=time.monotonic()+4
            while not (self.home/'ready').exists() and thread.is_alive() and time.monotonic()<until:time.sleep(.01)
            self.assertTrue((self.home/'ready').exists(),'synthetic process never published atomic ready')
            lr.cancel(self.P,self.p,job['id'],'operator');thread.join(6);self.assertFalse(thread.is_alive())
        finally:
            lr.cancel(self.P,self.p,job['id'],'test-cleanup');thread.join(6)
        done=lr.get(self.P,self.p,job['id']);self.assertEqual(done['status'],'cancelled');self.assertEqual(done['deadline'],job['deadline']);self.assertEqual(done['calls'],1);self.assertEqual(len(self.calls()),1)
        life=lr._sealed_run(self.P,done['steps'][0]['run_id']);self.assertEqual(len(life['attempts']),1);self.assertTrue(life['attempts'][0]['cleanup']['complete'])

    def test_frozen_executor_timeout_caps_real_process_without_extending_job(self):
        (self.home/'pause').write_text('public synthetic pause');job=self.start();done=self.work(job)
        self.assertEqual(done['status'],'timed_out',done['error']);self.assertEqual(done['deadline'],job['deadline']);self.assertEqual(done['calls'],1);self.assertEqual(len(self.calls()),1)
        life=lr._sealed_run(self.P,done['steps'][0]['run_id']);self.assertEqual(len(life['attempts']),1);self.assertTrue(life['attempts'][0]['cleanup']['complete'])
        self.assertEqual(life['stopped_reason'],'timeout')
        self.assertEqual(life['attempts'][0]['reason'],'timeout')
        self.assertEqual(life['attempts'][0]['returncode'],124)
        self.assertEqual(life['timeout_seconds'],2)
        self.assertLessEqual(life['attempts'][0]['timeout_seconds'],2)


if __name__=='__main__':unittest.main()
