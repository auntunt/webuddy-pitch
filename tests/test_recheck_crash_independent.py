"""Real HTTP recheck, real owner SIGKILL, original run and current evidence safety.

Only isolated temporary Git/Store/Platform data and test-owned processes are used.
The previous passing build is executed for real; no model or human review is faked.
"""
import base64
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tmh import config
from tmh.platform import fixloop, signoff
from tmh.platform.agents import make_worktree, worktree_diff
from tmh.platform.server import ApiError, Platform
from tmh.platform.store import now


REPO = Path(__file__).resolve().parents[1]
RAW = b"recheck-candidate-started\x00\xff\n"
WORKER = r'''
import json,os,pathlib,signal,subprocess,sys,time
action=sys.argv[1]; control=pathlib.Path(sys.argv[2]); cwd=pathlib.Path.cwd()
if action=='child':
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    (control/'child.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'cwd':str(cwd)}))
    while True:time.sleep(.03)
text=(cwd/'app.py').read_text()
assert text in ('VALUE = 0\n','VALUE = 1\n'),repr(text)
value=1 if '1' in text else 0
with (control/'commands.jsonl').open('a') as f:
    f.write(json.dumps({'action':action,'value':value,'cwd':str(cwd),'pid':os.getpid()})+'\n')
if action=='test' and value==1 and (control/'hold').exists():
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    (control/'leader.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'cwd':str(cwd)}))
    subprocess.Popen([sys.executable,__file__,'child',str(control)])
    os.write(1,b'recheck-candidate-started\x00\xff\n')
    while True:time.sleep(.03)
if action=='test' and value==1 and (control/'fail-check').exists():
    print('REAL_CHECK_FAILURE candidate VALUE=1 rejected by fixture acceptance',flush=True)
    raise SystemExit(7)
print('REAL_CHECK '+json.dumps({'action':action,'value':value,'cwd':str(cwd)}),flush=True)
'''
SERVICE = r'''
import json,pathlib,sys
from http.server import ThreadingHTTPServer
from tmh.platform.server import Platform,make_handler
data=pathlib.Path(sys.argv[1]);p=Platform(data,user='independent-test-operator')
httpd=ThreadingHTTPServer(('127.0.0.1',0),make_handler(p))
(data/'service.json').write_text(json.dumps({'port':httpd.server_port}))
httpd.serve_forever()
'''


@unittest.skipUnless(os.name == 'posix', 'requires POSIX owned process failure')
class RecheckCrashIndependentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tmh-recheck-independent-')
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name).resolve()
        (self.data/'autoflow.json').write_text(json.dumps({'on':False,'check_timeout':30,'rounds':0}))
        self.worker = self.data/'owned-check.py'; self.worker.write_text(WORKER)
        self.service_script = self.data/'owned-service.py'; self.service_script.write_text(SERVICE)
        self.root = self.data/'project'; self.root.mkdir()
        (self.root/'app.py').write_text('VALUE = 0\n')
        (self.root/'.gitignore').write_text('__pycache__/\n')
        cfg=config.load(self.root)
        cfg['commands'].update({kind:shlex.join([sys.executable,str(self.worker),kind,str(self.data)]) for kind in ('build','test')})
        config.save(self.root,cfg)
        self.git('init','-q'); self.git('config','user.name','independent-fixture'); self.git('config','user.email','fixture@localhost')
        self.git('add','.'); self.git('commit','-qm','actual local baseline')
        self.P=Platform(self.data,user='independent-fixture')
        self.addCleanup(self.P.store.db.close)
        self.p=self.P.store.add_project('RECHK','隔离真实重验',str(self.root))
        self.t=self.P.store.create_ticket(self.p['id'],'验证当前候选值','independent-fixture',auto=False)
        self.r=self.P.store.create_run(self.p['id'],self.t['id'],'local-fixture','fix','independent-fixture','保留完整原始任务')
        self.rid=self.r['id']; self.folder=self.data/'runs'/str(self.rid)
        self.wt,_=make_worktree(self.data,self.p,self.t,self.rid)
        (self.wt/'app.py').write_text('VALUE = 1\n')
        self.diff=worktree_diff(self.wt)
        self.P.runner._control(self.rid,{'local-fixture':{'timeout':30}},'local-fixture')
        self.P.store.update_run(self.rid,status='running',started=now(),workdir=str(self.wt),diff=self.diff)
        checked=fixloop.recheck(self.P.runner,self.rid,allow_running=True)
        self.assertEqual(checked['check'],'pass')
        self.assertEqual(len(checked['commands']),2)
        self.P.runner.finish_invocation(self.rid,0,'original completed run; real local checks, no model verdict')
        self.original=self.P.store.run(self.rid)
        self.original_verify=(self.folder/'verify.json').read_bytes()
        self.original_lifecycle=(self.folder/'lifecycle.json').read_bytes()
        self.pack=signoff.pack(self.P,self.t,'independent-fixture','隔离测试中的真实构建快照，不代表人工验收')
        self.original_records=signoff.records(self.data,self.t['key'])
        self.assertEqual(signoff.state(self.data,self.t['key'])['snapshot']['check']['result'],'pass')
        self.service=None; self.extra_platforms=[]
        self.observations={'test':self.id(),'temporary_directory':str(self.data),
            'original_run':self.original,'original_verify_base64':base64.b64encode(self.original_verify).decode(),
            'original_lifecycle_base64':base64.b64encode(self.original_lifecycle).decode(),'original_package_records':self.original_records}
        self.addCleanup(self.cleanup_owned)

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],text=True,stderr=subprocess.PIPE).strip()

    def json(self,path):
        try:return json.loads(path.read_text())
        except (OSError,ValueError):return None

    def wait_for(self,predicate,seconds=8):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            result=predicate()
            if result:return result
            time.sleep(.025)
        return None

    def process(self,pid):
        result=subprocess.run(['ps','-ww','-p',str(pid),'-o','pid=,ppid=,pgid=,stat=,lstart=,command='],capture_output=True,text=True)
        raw=result.stdout.strip(); fields=raw.split(None,4)
        return {'pid':pid,'alive':bool(len(fields)>=4 and not fields[3].startswith('Z')),'ps':raw}

    def workers(self):
        return [x for x in (self.json(self.data/(name+'.json')) for name in ('leader','child')) if x]

    def snapshot(self,P=None):
        P=P or self.P
        files={str(p.relative_to(self.folder)):base64.b64encode(p.read_bytes()).decode()
               for p in self.folder.rglob('*') if p.is_file()}
        operation_root=self.data/'verification-operations'
        operation_files={str(p.relative_to(operation_root)):base64.b64encode(p.read_bytes()).decode()
                         for p in operation_root.rglob('*') if p.is_file()} if operation_root.exists() else {}
        return {'run':P.store.run(self.rid),'verified':fixloop.verified(self.data,self.rid),
                'package':signoff.state(self.data,self.t['key']),'snapshot':signoff.snapshot(P,P.store.ticket(self.t['id'])),
                'workers':[self.process(w['pid']) for w in self.workers()], 'run_files':files,'operation_files':operation_files}

    def http(self,method,path,body=None):
        port=self.json(self.data/'service.json')['port']
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request('http://127.0.0.1:%d%s'%(port,path),data=data,method=method,
            headers={'Content-Type':'application/json','X-TMH':'1','X-TMH-User':'independent-test-operator'})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req,timeout=5) as response:return response.status,json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:return error.code,json.loads(error.read())

    def launch_service(self):
        (self.data/'service.json').unlink(missing_ok=True)
        env=dict(os.environ,PYTHONPATH=str(REPO)+os.pathsep+os.environ.get('PYTHONPATH',''),TMH_UNDERSTAND='rules')
        output=(self.data/'service-output.bin').open('ab'); self.addCleanup(output.close)
        self.service=subprocess.Popen([sys.executable,str(self.service_script),str(self.data)],cwd=REPO,env=env,
                                     stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        self.assertTrue(self.wait_for(lambda:self.json(self.data/'service.json')),'temporary service did not start')

    def start_recheck(self):
        (self.data/'hold').write_text('block candidate test after build; fixture-owned')
        self.launch_service()
        code,body=self.http('POST','/api/runs/%d/recheck'%self.rid,{})
        self.observations['start_http']={'status':code,'body':body}
        self.assertEqual(code,200,body)
        self.assertTrue(self.wait_for(lambda:len(self.workers())==2),
            'actual candidate check never blocked: '+(self.data/'service-output.bin').read_text(errors='replace'))
        for row in self.workers():self.assertIn(str(self.worker),self.process(row['pid'])['ps'])
        self.assertNotEqual(self.workers()[0]['pgid'],os.getpgrp())
        self.assertNotEqual(self.workers()[0]['pgid'],self.service.pid)

    def cleanup_owned(self):
        try:
            self.observations['before_fixture_cleanup']=self.snapshot()
            if self.service and self.service.poll() is None:
                self.service.kill(); self.service.wait(timeout=3)
            self.wait_for(lambda:all(not self.process(w['pid'])['alive'] for w in self.workers()),3)
            signals=[]
            for w in reversed(self.workers()):
                proc=self.process(w['pid'])
                if proc['alive'] and str(self.worker) in proc['ps']:
                    try:os.kill(w['pid'],signal.SIGKILL); signals.append(proc)
                    except ProcessLookupError:pass
            self.observations['fixture_cleanup_signals']=signals
            self.wait_for(lambda:all(not self.process(w['pid'])['alive'] for w in self.workers()),3)
            self.observations['after_fixture_cleanup_workers']=[self.process(w['pid']) for w in self.workers()]
            target=os.environ.get('TMH_RECHECK_EVIDENCE')
            if target:
                folder=Path(target); folder.mkdir(parents=True,exist_ok=True)
                (folder/(self._testMethodName+'.json')).write_text(json.dumps(self.observations,ensure_ascii=False,indent=2)+'\n')
        finally:
            for P in self.extra_platforms:P.store.db.close()

    def test_crashed_recheck_invalidates_old_proof_without_rewriting_original_run(self):
        self.start_recheck()
        before=self.snapshot(); self.observations['during_recheck']=before
        self.observations['during_http']=self.http('GET','/api/runs/%d/recheck'%self.rid)
        self.service.kill(); self.assertEqual(self.service.wait(timeout=3),-signal.SIGKILL)
        restarted=Platform(self.data,user='independent-recovery-operator'); self.extra_platforms.append(restarted)
        self.wait_for(lambda:all(not self.process(w['pid'])['alive'] for w in self.workers()),5)
        after=self.snapshot(restarted); self.observations['after_restart']=after
        failures=[]
        if before['verified'].get('check')=='pass':failures.append('active recheck still exposes previous verification as current pass')
        if before['snapshot']['check']['result']=='pass':failures.append('live signoff snapshot still claims old build passed during recheck')
        if not before['package'].get('stale'):failures.append('old ordinary package remains current while recheck is active')
        if after['verified'].get('check')=='pass':failures.append('interrupted recheck leaves previous verification current pass after restart')
        if not after['package'].get('stale'):failures.append('old ordinary package remains current after interrupted recheck')
        if after['run']['status']!='done':failures.append('recheck recovery rewrites original completed run status')
        for key in ('diff','result','exit_code','decision','prompt'):
            if after['run'][key]!=self.original[key]:failures.append('recheck recovery overwrites original run '+key)
        if any(w['alive'] for w in after['workers']):failures.append('recheck descendants remain alive after service crash')
        if signoff.records(self.data,self.t['key'])[:len(self.original_records)]!=self.original_records:
            failures.append('original evidence-package history was overwritten')
        raw=[base64.b64decode(value) for name,value in after['operation_files'].items() if name.endswith('output.bin')]
        if not any(RAW in value for value in raw):failures.append('interrupted check raw output was not preserved')
        if (self.folder/'lifecycle.json').read_bytes()!=self.original_lifecycle:
            failures.append('recheck modified original completed lifecycle bytes')
        if after['run']['output']!=self.original['output']:
            failures.append('recheck appended its own logs to the original completed run')
        for label,record in (('active',before),('interrupted',after)):
            current_gates={gate['id']:gate['state'] for gate in record['package']['gates']}
            for gate in ('parse','baseline','build','test','match'):
                if current_gates.get(gate)!='unknown':
                    failures.append(label+' package still presents old '+gate+' gate as current')
            historical={gate['id']:gate['state'] for gate in record['package']['snapshot']['gates']}
            if historical.get('build')!='pass' or historical.get('test')!='pass':
                failures.append(label+' package lost historical passing build/test gates')
        self.observations['contract_failures']=failures
        self.assertEqual(failures,[],'\n'.join(failures))

        self.launch_service()
        count=len((self.data/'commands.jsonl').read_text().splitlines())
        code,state=self.http('GET','/api/runs/%d/recheck'%self.rid)
        self.assertEqual(code,200,state)
        old_operation=state['operation']['id']
        self.assertFalse(state['running'])
        self.assertNotEqual(state['verify']['check'],'pass')
        self.assertEqual(len((self.data/'commands.jsonl').read_text().splitlines()),count,'GET must not silently rerun commands')
        code,collected=self.http('POST','/api/runs/%d/recheck/recover'%self.rid,{})
        self.assertEqual(code,200,collected)
        self.assertEqual(len((self.data/'commands.jsonl').read_text().splitlines()),count,'collecting receipts must not rerun commands')
        (self.data/'hold').unlink()
        code,result=self.http('POST','/api/runs/%d/recheck'%self.rid,{'wait':True})
        self.assertEqual(code,200,result)
        code,done=self.http('GET','/api/runs/%d/recheck'%self.rid)
        self.observations.update(after_explicit_recovery=collected,after_explicit_recheck=done)
        self.assertEqual(code,200,done)
        self.assertGreater(done['operation']['id'],old_operation)
        self.assertEqual(done['operation']['status'],'done')
        self.assertEqual(done['verify']['check'],'pass')
        self.assertTrue(done['verify']['verification_current'])
        self.assertEqual(len(done['verify']['commands']),2)
        self.assertTrue(all('REAL_CHECK' in command['output'] for command in done['verify']['commands']))
        old_package=signoff.state(self.data,self.t['key'])
        self.assertTrue(old_package['stale'],'new green proof cannot resurrect an old package')
        self.assertTrue(all(gate['state']=='unknown' for gate in old_package['gates']
                            if gate['id'] in ('parse','baseline','build','test','match')))
        signoff.pack(restarted,restarted.store.ticket(self.t['id']),'independent-fixture','按新完成的真实验证重新生成包')
        current=signoff.state(self.data,self.t['key']); self.observations['repacked_state']=current
        self.assertFalse(current['stale'])
        self.assertEqual(current['snapshot']['check']['result'],'pass')
        self.assertEqual({g['id']:g['state'] for g in current['gates']}['build'],'pass')
        self.assertEqual({g['id']:g['state'] for g in current['gates']}['test'],'pass')
        self.assertNotEqual(current['pack_hash'],self.pack['hash'])
        original=restarted.store.run(self.rid)
        for key in ('status','result','exit_code','diff','decision','prompt','output'):
            self.assertEqual(original[key],self.original[key],'completed source run changed: '+key)
        self.assertEqual((self.folder/'lifecycle.json').read_bytes(),self.original_lifecycle)
        raw_before=[base64.b64decode(value) for name,value in self.snapshot()['operation_files'].items()
                    if name.endswith('verification.before.json')]
        self.assertIn(self.original_verify,raw_before,'previous complete verification must remain byte-for-byte available')

    def test_active_recheck_rejects_adoption_without_removing_its_worktree(self):
        self.start_recheck()
        before=self.P.store.run(self.rid)
        rejected=''
        try:
            self.P.runner.decide(self.rid,'accept','isolated-rejected-request')
        except (ValueError,RuntimeError) as error:
            rejected=str(error)
        after=self.P.store.run(self.rid)
        self.observations.update(adoption_rejected=rejected,run_before_adoption=before,
                                 run_after_adoption=after,worktree_exists_after_adoption=self.wt.is_dir())
        self.assertTrue(rejected,'a second caller adopted code while its actual recheck command was still executing')
        self.assertEqual(after['decision'],before['decision'])
        self.assertTrue(self.wt.is_dir(),'rechecking worktree must remain available to its active commands')

    def test_missing_interrupted_receipt_blocks_retry_until_explicit_collection(self):
        self.start_recheck()
        code,state=self.http('GET','/api/runs/%d/recheck'%self.rid)
        self.assertEqual(code,200,state)
        opid=state['operation']['id']
        self.service.kill(); self.assertEqual(self.service.wait(timeout=3),-signal.SIGKILL)
        operation=self.data/'verification-operations'/'runs'/str(opid)
        attempts=operation/'attempts'
        self.assertTrue(self.wait_for(lambda:all((folder/'supervisor-result.json').exists()
            for folder in attempts.iterdir() if folder.is_dir()) and
            all(not self.process(w['pid'])['alive'] for w in self.workers())))
        results=[f for f in attempts.glob('*/supervisor-result.json') if self.json(f).get('reason')=='owner_lost']
        self.assertEqual(len(results),1,'only the actual blocked command should carry owner loss')
        final=results[0]; original=final.read_bytes(); held=final.with_name('supervisor-result.withheld-original')
        final.rename(held)  # keep every byte, but withhold the expected proof path
        self.launch_service()
        code,blocked=self.http('GET','/api/runs/%d/recheck'%self.rid)
        self.assertEqual(code,200,blocked)
        self.observations['missing_receipt_state']=blocked
        self.assertFalse(blocked['operation']['can_retry'])
        self.assertNotEqual(blocked['verify']['check'],'pass')
        count=len((self.data/'commands.jsonl').read_text().splitlines())
        code,rejected=self.http('POST','/api/runs/%d/recheck'%self.rid,{})
        self.observations['missing_receipt_start']={'status':code,'body':rejected}
        self.assertIn(code,(400,409),rejected)
        self.assertEqual(len((self.data/'commands.jsonl').read_text().splitlines()),count)
        self.assertEqual(held.read_bytes(),original)
        held.rename(final)
        code,collected=self.http('POST','/api/runs/%d/recheck/recover'%self.rid,{})
        self.assertEqual(code,200,collected)
        code,ready=self.http('GET','/api/runs/%d/recheck'%self.rid)
        self.observations['collected_restored_receipt']=ready
        self.assertEqual(code,200,ready)
        self.assertEqual(ready['operation']['id'],opid)
        self.assertTrue(ready['operation']['can_retry'])
        self.assertNotEqual(ready['verify']['check'],'pass','receipt collection proves cleanup, not completed verification')
        self.assertEqual(len((self.data/'commands.jsonl').read_text().splitlines()),count)
        self.assertEqual((self.folder/'lifecycle.json').read_bytes(),self.original_lifecycle)

    def test_real_failed_recheck_is_current_failure_and_never_overwrites_source_success(self):
        (self.data/'fail-check').write_text('actual local test command must fail with 7')
        self.launch_service()
        code,result=self.http('POST','/api/runs/%d/recheck'%self.rid,{'wait':True})
        self.assertEqual(code,200,result)
        code,state=self.http('GET','/api/runs/%d/recheck'%self.rid)
        self.observations['real_failed_check']=state
        self.assertEqual(code,200,state)
        self.assertEqual(state['operation']['status'],'failed')
        self.assertTrue(state['operation']['can_retry'],'complete failed checks may be explicitly retried')
        self.assertTrue(state['verify']['verification_current'])
        self.assertEqual(state['verify']['check'],'fail')
        self.assertEqual(state['verify']['commands'][-1]['exit_code'],7)
        self.assertIn('REAL_CHECK_FAILURE',state['verify']['commands'][-1]['output'])
        with self.assertRaises((ValueError,RuntimeError)):
            self.P.runner.decide(self.rid,'accept','isolated-rejected-request')
        self.assertTrue(signoff.state(self.data,self.t['key'])['stale'])
        for key in ('status','exit_code','result','output','diff'):
            self.assertEqual(self.P.store.run(self.rid)[key],self.original[key])

    def test_synthetic_signer_cannot_accept_freshly_repacked_real_failed_checks(self):
        # Synthetic sign-flow request over actual failing local checks. This
        # fixture never represents human approval or a real customer signature.
        (self.data/'fail-check').write_text('actual test exits 7')
        self.launch_service()
        code,result=self.http('POST','/api/runs/%d/recheck'%self.rid,{'wait':True})
        self.assertEqual(code,200,result)
        self.assertEqual(fixloop.verified(self.data,self.rid)['check'],'fail')
        self.P.store.update_ticket(self.t['id'],'SYNTHETIC-test-fixture',status='verify')
        ticket=self.P.store.ticket(self.t['id'])
        signoff.pack(self.P,ticket,'SYNTHETIC-test-fixture','explicitly package current real failure')
        state=signoff.state(self.data,self.t['key'])
        self.observations['fresh_failed_package']=state
        self.assertEqual({gate['id']:gate['state'] for gate in state['gates']}['test'],'fail',
                         'known failed command must remain fail, not become an unknown historical result')
        blocked='';signature=None
        try:
            link=signoff.issue(self.P,ticket,'SYNTHETIC-test-fixture','SYNTHETIC signer',
                               note='SYNTHETIC regression reason must not waive a known failed command')
            signature=signoff.decide(self.P,link['token'],'sign','SYNTHETIC signer',{},'SYNTHETIC request only')
        except ApiError as error:
            blocked=str(error)
            self.assertEqual(error.code,409)
        self.observations.update(failed_check_sign_blocked=blocked,failed_check_signature=signature,
                                 failed_check_ticket=self.P.store.ticket(self.t['id']))
        self.assertTrue(blocked,'fresh actual failed checks were signed after a note bypassed missing evidence')
        self.assertIsNone(signature)
        self.assertEqual(self.P.store.ticket(self.t['id'])['status'],'verify')

    def test_damaged_sealed_evidence_is_unknown_read_only_and_cannot_be_adopted(self):
        self.launch_service()
        code,result=self.http('POST','/api/runs/%d/recheck'%self.rid,{'wait':True})
        self.assertEqual(code,200,result)
        code,state=self.http('GET','/api/runs/%d/recheck'%self.rid)
        self.assertEqual(state['verify']['check'],'pass')
        opid=state['operation']['id'];folder=self.data/'verification-operations'/'runs'/str(opid)
        observations=[]
        count=len((self.data/'commands.jsonl').read_text().splitlines())
        for name in ('lifecycle.json','verification.json','source.json'):
            with self.subTest(name=name):
                path=folder/name;held=folder/(name+'.held-original');original=path.read_bytes();path.rename(held)
                try:
                    code,bad=self.http('GET','/api/runs/%d/recheck'%self.rid)
                    observations.append({'missing':name,'status':code,'body':bad})
                    self.assertEqual(code,200,bad)
                    self.assertFalse(bad['verify']['verification_current'])
                    self.assertNotEqual(bad['verify']['check'],'pass')
                    with self.assertRaises((ValueError,RuntimeError)):
                        self.P.runner.decide(self.rid,'accept','isolated-rejected-request')
                    self.assertFalse(path.exists(),'GET cannot fabricate missing proof')
                    self.assertEqual(held.read_bytes(),original)
                    self.assertEqual(len((self.data/'commands.jsonl').read_text().splitlines()),count)
                finally:
                    held.rename(path)
        self.observations['damaged_evidence_reads']=observations
        # Matching copies alone do not prove identity: corrupt both public and
        # operation artifacts while keeping their original bytes on disk.
        paths=[self.folder/'verify.json',folder/'verification.json']
        held_paths=[]
        for path in paths:
            held=path.with_name(path.name+'.identity-original');path.rename(held);held_paths.append(held)
        try:
            for field in ('commit','source_run'):
                altered=json.loads(held_paths[0].read_text())
                if field=='commit':altered['checked_commit']='a'*40
                else:altered['recheck_operation']['source_run']=self.rid+100
                for path in paths:path.write_text(json.dumps(altered))
                code,bad=self.http('GET','/api/runs/%d/recheck'%self.rid)
                observations.append({'matching_corrupt_artifacts':field,'status':code,'body':bad})
                self.assertEqual(code,200,bad)
                self.assertFalse(bad['verify']['verification_current'])
                self.assertNotEqual(bad['verify']['check'],'pass')
        finally:
            for path,held in zip(paths,held_paths):held.replace(path)
        self.assertEqual((self.folder/'lifecycle.json').read_bytes(),self.original_lifecycle)

    def test_synthetic_signoff_serializes_current_proof_check_and_commit_against_recheck(self):
        # Deliberately synthetic signer/token in temporary data: this is a race
        # regression, never a real user's acceptance or customer authorization.
        self.P.store.update_ticket(self.t['id'],'SYNTHETIC-test-fixture',status='verify')
        ticket=self.P.store.ticket(self.t['id'])
        link=signoff.issue(self.P,ticket,'SYNTHETIC-test-fixture','SYNTHETIC signer',
                           note='isolated regression fixture explicitly permits incomplete package for race test')
        original_check=signoff._require_current_binding
        raced=[]
        def try_recheck_after_current_proof_checked(state):
            original_check(state)
            try:
                operation=fixloop.start_recheck(self.P.runner,self.rid,'SYNTHETIC racing operator')
                raced.append({'started':True,'operation':operation})
            except (ValueError,RuntimeError) as error:
                raced.append({'started':False,'error':str(error)})
        try:
            with mock.patch.object(signoff,'_require_current_binding',side_effect=try_recheck_after_current_proof_checked):
                result=signoff.decide(self.P,link['token'],'sign','SYNTHETIC signer',{},'SYNTHETIC race test only')
            self.observations.update(synthetic_sign_result=result,race_attempts=raced,
                synthetic_post_sign_ticket=self.P.store.ticket(self.t['id']))
            self.assertTrue(raced,'race barrier must execute after reading current proof')
            self.assertFalse(any(x['started'] for x in raced),
                             'a new recheck started between signature proof validation and signature commit')
            self.assertEqual(self.P.store.ticket(self.t['id'])['status'],'closed')
        finally:
            for attempt in raced:
                if attempt['started']:
                    self.P.flow.rechecks.finish(attempt['operation']['id'],1,'SYNTHETIC fixture ends before any command')
        operation=fixloop.start_recheck(self.P.runner,self.rid,'SYNTHETIC operator after sign completes')
        try:
            after=signoff.state(self.data,self.t['key']);self.observations['synthetic_sign_after_new_recheck']=after
            self.assertTrue(after['stale'])
            self.assertIsNone(after['decision'],'later recheck invalidates prior signature as current, while retaining history')
            self.assertEqual(after['previous_decision']['signer'],'SYNTHETIC signer')
        finally:
            self.P.flow.rechecks.finish(operation['id'],1,'SYNTHETIC fixture ends before any command')

    def test_multicommand_recheck_holds_lease_between_real_commands_across_instances(self):
        barrier=r'''
import time
from tmh.platform.agents import Runner
original_run_command=Runner.run_command
def pause_after_real_candidate_build(self,rid,cmd,workdir,**kwargs):
    result=original_run_command(self,rid,cmd,workdir,**kwargs)
    if kwargs.get('kind')=='check:build' and (pathlib.Path(workdir)/'app.py').read_text()=='VALUE = 1\n':
        (data/'command-gap.json').write_text(json.dumps({'operation':rid,'code':result[0].returncode}))
        while not (data/'release-command-gap').exists():time.sleep(.025)
    return result
Runner.run_command=pause_after_real_candidate_build
'''
        self.service_script.write_text(SERVICE.replace("httpd=ThreadingHTTPServer",barrier+"\nhttpd=ThreadingHTTPServer"))
        self.launch_service()
        code,result=self.http('POST','/api/runs/%d/recheck'%self.rid,{})
        self.assertEqual(code,200,result)
        self.assertTrue(self.wait_for(lambda:self.json(self.data/'command-gap.json')))
        self.assertEqual(self.json(self.data/'command-gap.json')['code'],0,'barrier follows a real successful command')
        code,before=self.http('GET','/api/runs/%d/recheck'%self.rid)
        second=Platform(self.data,user='independent-second-instance');self.extra_platforms.append(second)
        self.assertTrue(before['operation']['owner_active'])
        self.assertTrue(before['running'])
        self.assertNotEqual(before['verify']['check'],'pass')
        count=len((self.data/'commands.jsonl').read_text().splitlines())
        with self.assertRaises((ValueError,RuntimeError)):
            second.flow.recheck(self.rid,'independent-second-instance',wait=False)
        self.assertEqual(len((self.data/'commands.jsonl').read_text().splitlines()),count)
        self.observations['between_commands']=before
        self.assertEqual(second.store.run(self.rid),self.original)
        (self.data/'release-command-gap').write_text('allow existing operation to continue')
        done=self.wait_for(lambda:(state if (state:=self.http('GET','/api/runs/%d/recheck'%self.rid)[1])
                                   .get('operation',{}).get('status')=='done' and not state.get('running') else None))
        self.assertTrue(done)
        # The row reaches done before lifecycle sealing releases ownership.
        # Read the verification after observing that completion boundary; the
        # earlier response may have sampled verification while still active.
        code,done=self.http('GET','/api/runs/%d/recheck'%self.rid)
        self.assertEqual(code,200,done)
        self.assertFalse(done['running'],done)
        self.observations['after_command_gap']=done
        self.assertTrue(done)
        self.assertEqual(done['verify']['check'],'pass')
        self.assertEqual(len(done['verify']['commands']),2)


if __name__=='__main__':unittest.main()
