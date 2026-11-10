import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tmh.platform.agents import worktree_diff
from tmh.platform.comment_execution import push
from tmh.platform.store import Store
from tmh.platform.task_preparation import baseline


class CommentPushTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.data=Path(self.temp.name);self.root=self.data/'source';self.root.mkdir()
        (self.root/'a.txt').write_text('before\n');baseline(self.root)
        self.remote=self.data/'remote.git'
        subprocess.run(['git','init','--bare',str(self.remote)],check=True,capture_output=True)
        self.git('remote','add','origin',str(self.remote))
        self.wt=self.data/'work'
        self.git('worktree','add','-b','task',str(self.wt))
        (self.wt/'a.txt').write_text('after\n')
        self.store=Store(self.data/'platform.db');self.addCleanup(self.store.db.close)
        self.project=self.store.add_project('PUSH','Push',str(self.root))
        self.ticket=self.store.create_ticket(self.project['id'],'tested change','alice',auto=False)
        self.source=self.store.create_run(self.project['id'],self.ticket['id'],'cursor','fix','alice','')
        diff=worktree_diff(self.wt)
        self.store.update_run(self.source['id'],status='done',exit_code=0,workdir=str(self.wt),diff=diff)
        folder=self.data/'runs'/str(self.source['id']);folder.mkdir(parents=True)
        (folder/'verify.json').write_text(json.dumps({'check':'pass','verdict':'pass','checked_diff':diff,'checked_base':self.git('rev-parse','HEAD')}))
        self.run=self.store.create_run(self.project['id'],self.ticket['id'],'cursor','continue','alice','')
        self.runner=SimpleNamespace(data_dir=self.data,store=self.store,run_command=self.command)
        self.commands=[]

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.DEVNULL,text=True).strip()

    def command(self,rid,argv,cwd,**kw):
        self.commands.append(argv)
        value=subprocess.run(argv,cwd=cwd,env=kw.get('env'),capture_output=True,text=True)
        return SimpleNamespace(returncode=value.returncode,output=value.stdout+value.stderr),None

    def test_explicit_comment_pushes_verified_snapshot_without_adopting_or_merging(self):
        before=self.git('rev-parse','HEAD')
        reply=push(self.runner,self.run['id'],self.project,self.ticket,'请推送 origin feature/review','origin','feature/review')
        self.assertIn('已推送',reply)
        content=subprocess.check_output(['git','--git-dir',str(self.remote),'show','feature/review:a.txt'],text=True)
        self.assertEqual(content,'after\n')
        self.assertEqual(self.git('rev-parse','HEAD'),before)
        self.assertEqual(self.store.run(self.source['id'])['decision'],'')
        self.assertNotEqual(self.store.ticket(self.ticket['id'])['status'],'closed')
        self.assertEqual((self.wt/'a.txt').read_text(),'after\n')
        push_args=[a for a in self.commands if a[1:2]==['push']][0]
        self.assertNotIn('--force',push_args)

    def test_changed_code_cannot_reuse_successful_verification(self):
        (self.wt/'a.txt').write_text('changed after review\n')
        with self.assertRaises(ValueError):
            push(self.runner,self.run['id'],self.project,self.ticket,'推送 origin feature/review','origin','feature/review')
        self.assertFalse(any(a[1:2]==['push'] for a in self.commands))
