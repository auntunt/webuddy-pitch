"""Real local Git fixtures; no customer repository or model execution."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from tmh.workspace_preflight import inspect, repository_identity
from tmh.workbench_client import ClientError


class WorkspacePreflightTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.git('init','-b','main');self.git('config','user.name','Fixture');self.git('config','user.email','fixture@localhost')
        (self.root/'app.txt').write_text('initial')
        self.git('add','.');self.git('commit','-m','baseline')
        self.git('remote','add','origin','https://github.com/team/project.git')
        self.sha=self.git('rev-parse','HEAD')
        self.state={'state':'confirmed','digest':'d'*64,'execution':{'current':True,'mode':'local','project':'PROJ','repository':'git@github.com:team/project.git','base_commit':self.sha}}
        self.library={'revisions':[{'id':'K1','commit':self.sha,'status':'ready'}],'references':[]}
        self.calls=[]
    def git(self,*args):
        return subprocess.run(['git','-C',str(self.root),*args],capture_output=True,check=True,text=True).stdout.strip()
    def call(self,op,body):
        self.calls.append((op,body))
        return copy.deepcopy(self.state if op=='development_get' else self.library)
    def check(self):return inspect(self,'PROJ-1',str(self.root))
    def test_clean_bound_repository(self):
        value=self.check();self.assertTrue(value['ready']);self.assertEqual(value['head'],self.sha)
        self.assertEqual(value['matching_remotes'],['origin']);self.assertEqual(value['branch'],'main')
    def test_foreign_repository_rejected(self):
        self.git('remote','set-url','origin','https://github.com/other/project.git')
        self.assertEqual(self.check()['checks']['repository'],'mismatch')
    def test_dirty_and_untracked_preserved(self):
        (self.root/'app.txt').write_text('keep my changes');(self.root/'new.txt').write_text('preserve')
        value=self.check();self.assertFalse(value['ready']);self.assertEqual(len(value['changes']),2)
        self.assertEqual((self.root/'app.txt').read_text(),'keep my changes')
        self.assertTrue((self.root/'new.txt').exists())
    def test_head_mismatch_and_knowledge_mismatch(self):
        self.git('commit','--allow-empty','-m','next')
        value=self.check();self.assertFalse(value['ready']);self.assertEqual(value['checks']['baseline'],'mismatch')
        self.assertEqual(value['checks']['knowledge'],'not_matched')
    def test_unselected_does_not_probe_git_or_library(self):
        self.state['execution']['current']=False
        value=inspect(self,'PROJ-1',str(self.root/'does-not-exist'))
        self.assertFalse(value['ready']);self.assertEqual(len(self.calls),1)
    def test_changed_confirmation_during_check(self):
        original=self.call
        def call(op,body):
            value=original(op,body)
            if len(self.calls)>2:value['digest']='e'*64
            return value
        self.call=call
        self.assertFalse(self.check()['checks']['stable'])
    def test_worktree_directory_is_actual_root(self):
        target=self.root/'nested-worktree'
        self.git('worktree','add','--detach',str(target),self.sha)
        value=inspect(self,'PROJ-1',str(target))
        self.assertTrue(value['ready']);self.assertEqual(Path(value['git_root']).resolve(),target.resolve())
        self.assertEqual(value['branch'],'HEAD')
    def test_missing_repo_and_knowledge_are_explicit(self):
        self.state['execution']['repository']='';self.library['revisions']=[]
        value=self.check();self.assertFalse(value['ready']);self.assertEqual(value['checks']['repository'],'unknown')
    def test_relative_directory_rejected(self):
        with self.assertRaises(ClientError):inspect(self,'PROJ-1','.')
    def test_credentials_not_normalized_into_identity(self):
        self.assertIsNone(repository_identity('https://secret:token@github.com/team/project.git'))
