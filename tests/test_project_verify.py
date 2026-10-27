"""Bound, network-free verification of synthetic personal candidates."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from tmh.platform import candidates, fixloop, project_verify, project_merge, project_git, tenant_policy, team
from tmh.platform.errors import ApiError
from tmh.platform.recheck_operations import Operations
from tests import test_project_candidates as fixtures


class ProjectVerifyTest(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.ProjectCandidateRegistrationTest('runTest')
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fixture=fixture;self.P=fixture.P;self.store=fixture.store
        root=Path(fixture.project['root']);(root/'.tmh').mkdir()
        (root/'.tmh'/'config.json').write_text(json.dumps({'commands':{'build':'echo build','test':'echo test'}}))
        self.P.flow=SimpleNamespace(rechecks=Operations(self.store,self.P.data_dir))
        self.store.update_run(fixture.run['id'],status='done',diff='synthetic exact patch')
        candidates.schema(self.store)
        self.store.x('''INSERT INTO code_candidates(ticket_id,run_id,agent,base_commit,commit_sha,
            requirement_hash,configuration_hash,criteria,summary,fingerprint,ref,artifact_dir,created)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', (fixture.ticket['id'],fixture.run['id'],'alice','b'*40,'c'*40,
            'd'*64,'e'*64,'[]','fixture','f'*64,'refs/webuddy/candidates/'+'f'*64,str(fixture.folder),'fixture'))
        self.cid=self.store.one('SELECT id FROM code_candidates WHERE run_id=?',(fixture.run['id'],))['id']
        self.specs=[];self.allow=True;self.exit_codes=[0,0,0,0];self.cleanup=True;self.volume_cleanup=True;self.volumes=[];self.source_unchanged=True
        owner=self
        class Engine:
            def run(self,spec,seconds,**kwargs):
                owner.specs.append(spec)
                if spec['command'][0]=='python3':
                    return {'reason':'exited','returncode':0 if owner.source_unchanged else 1,'cleanup':owner.cleanup}
                kwargs['output'](b'raw\xff output\n')
                if not owner.allow: kwargs['cancel']()
                return {'reason':'exited','returncode':owner.exit_codes.pop(0),'cleanup':owner.cleanup}
        self.engine=Engine()
        class Volume:
            def __init__(self,engine,image,workspace,seconds,cancel):
                self.workspace=workspace;self.name='volume-'+str(len(owner.volumes)+1);owner.volumes.append(self)
            def __enter__(self):return self
            def __exit__(self,*args):
                if not owner.volume_cleanup:raise ValueError('项目临时工作区回收未确认')
            def alive(self):return True
            def spec(self,command,seconds):
                return {'command':command,'NetworkDisabled':True,'HostConfig':{'NetworkMode':'none',
                    'Mounts':[{'Type':'volume','Source':self.name,'Target':'/workspace','ReadOnly':False}]}}
        self.volume=Volume

    def run_synthetic(self, before=None):
        def snapshot(image,root,workspace,**kwargs):
            workspace.mkdir();(workspace/'fixture').write_text('candidate')
            commit='b'*40 if kwargs['ref']=='b'*40 else 'c'*40
            return {'commit':commit,'archive_sha256':'a'*64}
        with patch.object(project_verify,'Engine',return_value=self.engine), \
             patch.object(project_verify,'ProjectVolume',self.volume), \
             patch.object(project_verify.project_snapshot,'current',side_effect=lambda *a,**kw:self.allow), \
             patch.object(project_verify.project_snapshot,'create',side_effect=snapshot), \
             patch.object(project_verify.candidates,'view',return_value={'current':True,'blocked':[]}):
            if before:before()
            result=project_verify.start(self.P,'alice',self.cid)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                op=self.P.flow.rechecks.get(result['operation'])
                if op['status'] in ('done','failed','cancelled') and not op['running']:
                    break
                time.sleep(.02)
            self.assertFalse(op['running'],op)
            return op

    def test_success_seals_exact_version_and_separate_writable_no_network(self):
        op=self.run_synthetic()
        self.assertEqual(op['status'],'done',op)
        v=fixloop.verified(self.P.data_dir,self.fixture.run['id'])
        self.assertTrue(v['verification_current']);self.assertEqual(v['check'],'pass')
        self.assertEqual(v['checked_base'],'b'*40);self.assertEqual(v['checked_commit'],'c'*40)
        self.assertEqual(v['checked_diff'],'synthetic exact patch')
        self.assertEqual([x['kind'] for x in v['commands']],['build','test'])
        self.assertTrue(v['baseline_passed'])
        self.assertEqual(len(self.volumes),2)
        self.assertNotEqual(self.volumes[0].name,self.volumes[1].name)
        for spec in self.specs:
            self.assertTrue(spec['NetworkDisabled'])
            self.assertEqual(spec['HostConfig']['NetworkMode'],'none')
            self.assertEqual(spec['HostConfig']['Mounts'][0]['Type'],'volume')
            self.assertFalse(spec['HostConfig']['Mounts'][0]['ReadOnly'])
            if spec['command'][0]=='python3':
                self.assertEqual(spec['HostConfig']['Mounts'][1]['Target'],'/reference')
                self.assertTrue(spec['HostConfig']['Mounts'][1]['ReadOnly'])
            else:self.assertEqual(len(spec['HostConfig']['Mounts']),1)
        raw=Path(self.P.data_dir)/v['commands'][0]['raw_output']
        self.assertEqual(raw.read_bytes(),b'raw\xff output\n')
        self.assertEqual(self.store.q('SELECT * FROM candidate_decisions'),[])

    def test_failure_is_not_a_pass(self):
        self.exit_codes=[0,0,0,1]
        op=self.run_synthetic()
        self.assertEqual(op['status'],'failed')
        self.assertEqual(fixloop.verified(self.P.data_dir,self.fixture.run['id'])['check'],'fail')

    def test_unconfirmed_container_cleanup_cannot_publish_a_pass(self):
        self.cleanup=False
        op=self.run_synthetic()
        self.assertEqual(op['status'],'failed')
        self.assertIn('回收',op['result'])
        self.assertNotEqual(fixloop.verified(self.P.data_dir,self.fixture.run['id']).get('check'),'pass')

    def test_unconfirmed_volume_cleanup_cannot_publish_a_pass(self):
        self.volume_cleanup=False
        op=self.run_synthetic()
        self.assertEqual(op['status'],'failed')
        self.assertIn('回收',op['result'])
        self.assertNotEqual(fixloop.verified(self.P.data_dir,self.fixture.run['id']).get('check'),'pass')

    def test_failing_baseline_never_runs_or_passes_candidate(self):
        self.exit_codes=[1]
        op=self.run_synthetic()
        self.assertEqual(op['status'],'failed')
        self.assertIn('基线',op['result'])
        self.assertEqual(len(self.volumes),1)
        v=fixloop.verified(self.P.data_dir,self.fixture.run['id'])
        self.assertFalse(v['baseline_passed']);self.assertEqual(v['check'],'fail')

    def test_changed_source_cannot_pass(self):
        self.source_unchanged=False
        op=self.run_synthetic()
        self.assertEqual(op['status'],'failed')
        self.assertNotEqual(fixloop.verified(self.P.data_dir,self.fixture.run['id']).get('check'),'pass')

    def test_source_checker_allows_only_original_gitignored_products_and_rejects_source_changes(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);ref=root/'reference';work=root/'workspace'
            ref.mkdir();work.mkdir();(ref/'app.py').write_text('original');(work/'app.py').write_text('original')
            (ref/'.gitignore').write_text('target/\n');(work/'.gitignore').write_text('target/\n')
            checker=project_verify.CHECK_SOURCE.replace('/reference',str(ref)).replace('/workspace',str(work))
            def check():return subprocess.run(['python3','-I','-c',checker],capture_output=True).returncode
            (work/'target').mkdir();(work/'target'/'build.out').write_text('generated')
            self.assertEqual(check(),0)
            (work/'build').mkdir();(work/'build'/'new.py').write_text('unignored')
            self.assertNotEqual(check(),0)
            (work/'build'/'new.py').unlink();(work/'build').rmdir()
            (work/'new.py').write_text('unknown')
            self.assertNotEqual(check(),0)
            (work/'.gitignore').write_text('target/\nnew.py\n')
            self.assertNotEqual(check(),0)
            (work/'.gitignore').write_text('target/\n')
            (work/'new.py').unlink();(work/'app.py').write_text('changed')
            self.assertNotEqual(check(),0)

    def test_revocation_during_command_cannot_publish_verification(self):
        engine=self.engine
        real=engine.run
        def revoke(spec,seconds,**kwargs):
            result=real(spec,seconds,**kwargs)
            self.fixture.fixture.gateway.change('project_revoke',tenant=self.fixture.fixture.gateway.a,user='alice',project_id=1)
            return result
        engine.run=revoke
        op=self.run_synthetic()
        self.assertEqual(op['status'],'failed')
        self.assertNotEqual(fixloop.verified(self.P.data_dir,self.fixture.run['id']).get('check'),'pass')
        self.assertFalse((Path(self.P.data_dir)/'runs'/str(self.fixture.run['id'])/'verify.json').exists())

    def test_missing_explicit_test_and_unsupported_execution_mode_refuse(self):
        path=Path(self.fixture.project['root'])/'.tmh'/'config.json'
        path.write_text(json.dumps({'commands':{'build':'echo build','test':''}}))
        with self.assertRaisesRegex(ValueError,'test'):
            project_verify.commands(self.P,self.fixture.project)
        path.write_text(json.dumps({'commands':{'test':'echo test'}}))
        (self.P.data_dir/'autoflow.json').write_text(json.dumps({'check':'echo legacy'}))
        with self.assertRaisesRegex(ValueError,'暂不支持'):
            project_verify.commands(self.P,self.fixture.project)

    def test_member_action_is_project_scoped_and_routes_to_isolated_verifier(self):
        body={'action':'candidate_verify','ticket':self.fixture.ticket['key'],'candidate_id':self.cid}
        tenant_policy.authorize(self.P,'POST','/api/team',{},body,'alice')
        with patch.object(candidates,'view',return_value={'current':True,'blocked':[]}), \
             patch.object(project_verify,'start',return_value={'started':True,'operation':7}) as start:
            result=candidates.execute(self.P,'alice','candidate_verify',{'candidate_id':self.cid})
        self.assertEqual(result['operation'],7)
        start.assert_called_once_with(self.P,'alice',self.cid)
        self.fixture.fixture.gateway.change('project_revoke',tenant=self.fixture.fixture.gateway.a,user='alice',project_id=1)
        with self.assertRaises(ApiError):tenant_policy.authorize(self.P,'POST','/api/team',{},body,'alice')

    def test_member_cannot_cancel_another_persons_verification(self):
        with patch.object(candidates,'view',return_value={'current':True,'blocked':[]}), \
             patch.object(self.P.flow.rechecks,'status',return_value={'running':True,'author':'bob','id':12}), \
             self.assertRaises(ApiError):
            candidates.execute(self.P,'alice','candidate_cancel',{'candidate_id':self.cid})

    def test_personal_merge_requires_current_independent_review_and_records_exact_commit(self):
        gateway=self.fixture.fixture.gateway
        gateway.change('member_set',tenant=gateway.a,user='bob',role='member')
        gateway.change('project_grant',tenant=gateway.a,user='bob',project_id=1,role='contributor')
        team.schema(self.P)
        ticket=self.store.ticket(self.fixture.ticket['id'])
        team._assign(self.P,ticket,{'assignee':'alice','reviewer':'bob','revision':0,'previous_assignee':''},'owner')
        head=['b'*40];evidence={'evidence_hash':'evidence','human_accepted':False}
        def git(root,*args):
            if args==('rev-parse','HEAD'):return head[0]+'\n'
            if args==('rev-parse','refs/webuddy/candidates/'+'f'*64):return 'c'*40+'\n'
            raise AssertionError(args)
        def merge(*args,**kwargs):
            head[0]='c'*40
            raise ValueError('synthetic lost response after Git write')
        with patch.object(candidates,'view',side_effect=lambda *a,**k:dict(evidence)), \
             patch.object(candidates,'browser_review_current',return_value=True), \
             patch.object(candidates,'_git',side_effect=git), \
             patch('tmh.platform.release.main_branch',return_value='main'), \
             patch.object(project_merge,'fast_forward',side_effect=merge) as execute, \
             patch.object(project_merge,'verify_merged',return_value={}):
            with self.assertRaises(ApiError):
                project_merge.browser_merge(self.P,self.cid,'bob','evidence','merge-1',lambda:None)
            execute.assert_not_called()
            with self.assertRaises(ApiError):
                project_merge.browser_merge(self.P,self.cid,'alice','evidence','merge-2',lambda:None)
            evidence['human_accepted']=True
            with self.assertRaises(ApiError):
                project_merge.browser_merge(self.P,self.cid,'bob','evidence','merge-3',lambda:None)
            self.assertEqual(candidates.merge_receipt(self.P,self.cid)['state'],'prepared')
            result=project_merge.browser_merge(self.P,self.cid,'bob','evidence','merge-3',lambda:None)
            execute.assert_called_once()
        self.assertEqual(result['state'],'merged')
        self.assertTrue(result['replayed'])
        self.assertEqual(result['commit_sha'],'c'*40)
        self.assertFalse(result['pushed']);self.assertFalse(result['deployed'])
        self.assertEqual(self.store.q("SELECT author FROM events WHERE kind='candidate_merge'")[0]['author'],'bob')

    def test_real_personal_http_session_reaches_isolated_verification_entry(self):
        # Real gateway/session/worker; fixed metadata and execution are mocked.
        gateway=self.fixture.fixture.gateway
        site=gateway.data/'verify-site';site.mkdir()
        (site/'sitecustomize.py').write_text('''
from tmh.platform import candidates, project_verify, team
candidates.view=lambda *a,**kw:{"current":True,"blocked":[]}
project_verify.commands=lambda *a,**kw:([("test","echo fixture")],30)
project_verify.start=lambda P,actor,cid:{"started":True,"operation":7,"actor":actor,"candidate":cid}
team.item=lambda P,t,user:{"ticket":{"key":t["key"]}}
''')
        path=str(site)+os.pathsep+os.getcwd()+os.pathsep+os.environ.get('PYTHONPATH','')
        with patch.dict(os.environ,{'PYTHONPATH':path}):
            base='/t/'+gateway.a;token=gateway.token('alice',gateway.a)
            body={'action':'candidate_verify','ticket':self.fixture.ticket['key'],'candidate_id':self.cid,
                  'request_id':'verify-personal-http'}
            status,_,response=gateway.request('POST',base+'/api/team','alice',body,token=token,headers={'X-TMH':'1'})
            self.assertEqual(status,200,response)
            self.assertEqual(response['result'],{'started':True,'operation':7,'actor':'alice','candidate':self.cid})
            gateway.change('project_revoke',tenant=gateway.a,user='alice',project_id=1)
            fresh=gateway.token('alice',gateway.a)
            status,_,_=gateway.request('POST',base+'/api/team','alice',dict(body,request_id='after-revoke'),token=fresh,headers={'X-TMH':'1'})
            self.assertEqual(status,403)

    def test_personal_merge_uses_scoped_git_and_actual_disposable_repository(self):
        from tests.test_project_merge import LocalEngine
        gateway=self.fixture.fixture.gateway
        gateway.change('member_set',tenant=gateway.a,user='bob',role='member')
        gateway.change('project_grant',tenant=gateway.a,user='bob',project_id=1,role='contributor')
        root=Path(self.fixture.project['root']);(root/'.git').rmdir()
        def git(*args):return subprocess.run(['git','-C',str(root),*args],capture_output=True,check=True).stdout.decode().strip()
        git('init','-q','-b','main');(root/'code.py').write_text('old\n')
        git('add','code.py');git('-c','user.name=Fixture','-c','user.email=test@example.invalid','commit','-qm','base')
        base=git('rev-parse','HEAD');(root/'code.py').write_text('new\n');git('add','code.py')
        git('-c','user.name=Fixture','-c','user.email=test@example.invalid','commit','-qm','candidate')
        commit=git('rev-parse','HEAD');ref='refs/webuddy/candidates/'+'f'*64
        git('update-ref',ref,commit);git('reset','--hard',base)
        self.store.x('UPDATE code_candidates SET base_commit=?,commit_sha=?,ref=? WHERE id=?',(base,commit,ref,self.cid))
        team.schema(self.P);ticket=self.store.ticket(self.fixture.ticket['id'])
        team._assign(self.P,ticket,{'assignee':'alice','reviewer':'bob','revision':0,'previous_assignee':''},'owner')
        with project_git.personal_scope(self.P,'bob'), \
             patch.object(project_git,'Engine',LocalEngine),patch.object(project_merge,'Engine',LocalEngine), \
             patch.object(candidates,'view',return_value={'evidence_hash':'fixture','human_accepted':True}), \
             patch.object(candidates,'browser_review_current',return_value=True):
            result=project_merge.browser_merge(self.P,self.cid,'bob','fixture','fixture-merge',lambda:None)
        self.assertEqual(result['state'],'merged')
        self.assertEqual(git('rev-parse','HEAD'),commit)
        self.assertEqual((root/'code.py').read_text(),'new\n')
        self.assertTrue((root/'.tmh/config.json').exists())

if __name__=='__main__':unittest.main()
