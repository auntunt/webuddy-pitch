import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tmh.platform.task_preparation import baseline, environment


class PreparationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()

    def test_source_only_baseline_retains_local_credentials_and_build_output(self):
        (self.root / 'Main.java').write_text('class Main {}')
        (self.root / '.env').write_text('PASSWORD=actual-local-value')
        (self.root / 'config.json').write_text('{"API_KEY":"abcdefghijklmnopqrstuvwxyz0123456789"}')
        (self.root / 'target').mkdir()
        (self.root / 'target' / 'Main.class').write_bytes(b'compiled')
        original = {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        receipt = baseline(self.root)
        self.assertTrue(receipt['created'])
        self.assertEqual(self.git('ls-tree', '-r', '--name-only', 'HEAD'), 'Main.java')
        for name, data in original.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertIn('config.json', receipt['excluded'])
        subprocess.run(['git','-C',str(self.root),'worktree','add',str(self.root.parent / (self.root.name+'-work'))],check=True,capture_output=True)
        work = self.root.parent / (self.root.name+'-work')
        self.addCleanup(lambda: subprocess.run(['git','-C',str(self.root),'worktree','remove','--force',str(work)],capture_output=True))
        self.assertTrue((work / 'Main.java').is_file())

    def test_existing_history_and_uncommitted_changes_are_preserved(self):
        (self.root / 'a.txt').write_text('original')
        first = baseline(self.root)
        (self.root / 'a.txt').write_text('new work')
        again = baseline(self.root)
        self.assertFalse(again['created'])
        self.assertEqual(first['commit'], again['commit'])
        self.assertEqual((self.root / 'a.txt').read_text(), 'new work')
        self.assertIn('a.txt', self.git('status', '--porcelain'))

    def test_parent_repository_is_not_reinitialized_at_wrong_root(self):
        (self.root / 'a.txt').write_text('source')
        baseline(self.root)
        child = self.root / 'module';child.mkdir()
        with self.assertRaises(ValueError): baseline(child)
        self.assertFalse((child / '.git').exists())

    def test_environment_paths_are_per_run_and_do_not_change_process(self):
        folder = self.root / 'runs' / '1';folder.mkdir(parents=True)
        tools = self.root / 'portable' / 'bin';tools.mkdir(parents=True)
        (folder/'environment.json').write_text(json.dumps({'path':[str(tools)]}))
        original = os.environ.get('PATH')
        env = environment(self.root, 1)
        self.assertEqual(env['PATH'].split(os.pathsep)[0], str(tools))
        self.assertEqual(os.environ.get('PATH'), original)
        (folder/'environment.json').write_text(json.dumps({'path':['relative']}))
        with self.assertRaises(ValueError): environment(self.root, 1)

    def test_chinese_progress_round_trips_with_windows_default_encoding(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from tmh.platform.task_preparation import stage
        runner = SimpleNamespace(data_dir=self.root, store=Mock())
        read_text = Path.read_text
        def windows_read(path, encoding=None, **kwargs):
            return read_text(path, encoding=encoding or 'gbk', **kwargs)
        with patch.object(Path, 'read_text', windows_read):
            stage(runner, 1, '准备源码与 Git 基线')
            stage(runner, 1, '准备源码与 Git 基线', 'done', '已建立本地基线')
        progress = json.loads((self.root/'runs/1/preparation.json').read_text(encoding='utf-8'))
        self.assertEqual(progress['steps'][0]['state'], 'done')

    def test_registered_run_prepares_unversioned_source_and_executes_real_check(self):
        from unittest.mock import patch
        from tmh import config
        from tmh.platform.agents import Runner
        from tmh.platform.store import Store
        import sys
        source = self.root / 'source';source.mkdir()
        (source/'app.py').write_text('VALUE = 0\n')
        cfg=config.load(source)
        cfg['commands'].update(build='"'+sys.executable+'" -m py_compile app.py', test='"'+sys.executable+'" -c "import app; assert app.VALUE == 1"')
        config.save(source,cfg)
        data=self.root/'state';data.mkdir()
        store=Store(data/'platform.db');self.addCleanup(store.db.close)
        project=store.add_project('AUTO','自动准备',str(source))
        ticket=store.create_ticket(project['id'],'将VALUE改成1','alice',auto=False)
        runner=Runner(store,data)
        conf={'fixture':{'cmd':[sys.executable,'unused'], 'defaults':{}}}
        run=store.create_run(project['id'],ticket['id'],'fixture','fix','alice','change value')
        def invoke(rid,p,t,a,c,mode,prompt,workdir,*args,**kwargs):
            if mode in ('fix','edit'):
                (Path(workdir)/'app.py').write_text('VALUE = 1\n')
                return 0,'已修改VALUE'
            if mode=='diagnose':
                return 0,'```tmh-diag\n'+json.dumps({'verdict':'pass','blocking':[],'files':[],'ac':[]})+'\n```'
            return 0,'环境工具已可用'
        with patch.object(runner,'invoke',side_effect=invoke):
            runner._go(run['id'],project,ticket,'fixture','fix','将VALUE改成1',conf)
        result=store.run(run['id'])
        self.assertEqual(result['status'],'done',result['result'])
        self.assertEqual((source/'app.py').read_text(),'VALUE = 0\n')
        self.assertEqual((Path(result['workdir'])/'app.py').read_text(),'VALUE = 1\n')
        verify=json.loads((data/'runs'/str(run['id'])/'verify.json').read_text())
        self.assertEqual(verify['baseline']['state'],'fail',verify)
        self.assertEqual(verify['check'],'pass',verify)
        self.assertEqual(verify['commands'][0]['exit_code'],0)
        progress=json.loads((data/'runs'/str(run['id'])/'preparation.json').read_text())
        self.assertTrue(all(s['state']=='done' for s in progress['steps']),progress)
