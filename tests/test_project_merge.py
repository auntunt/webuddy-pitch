"""Fixed merge operation against disposable local repositories only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tmh.platform.project_merge import fast_forward, verify_merged


class LocalEngine:
    def run(self, spec, seconds, *, cancel=lambda:False, output, diagnostic=lambda data:None):
        if cancel(): return {'reason':'cancelled','returncode':125,'cleanup':True}
        root=spec['HostConfig']['Mounts'][0]['Source']
        command=json.loads(spec['Cmd'][1])
        env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0')
        process=subprocess.run(command,cwd=root,env=env,capture_output=True)
        output(process.stdout)
        diagnostic(process.stderr)
        return {'reason':'exited','returncode':process.returncode,'cleanup':True}


class PersonalMergeTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.git('init','-q','-b','main')
        (self.root/'example.py').write_text('old\n')
        self.git('add','example.py');self.commit('base')
        self.base=self.git('rev-parse','HEAD')
        (self.root/'example.py').write_text('new\n')
        (self.root/'new.txt').write_text('candidate file\n')
        self.git('add','example.py','new.txt');self.commit('candidate')
        self.candidate=self.git('rev-parse','HEAD')
        self.ref='refs/webuddy/candidates/'+'a'*64
        self.git('update-ref',self.ref,self.candidate)
        self.git('reset','--hard',self.base)

    def git(self,*args):
        return subprocess.run(['git','-C',str(self.root),*args],capture_output=True,check=True).stdout.decode().strip()

    def commit(self,message):
        self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm',message)

    def merge(self):
        return fast_forward('sha256:'+'a'*64,self.root,self.base,self.candidate,self.ref,'main',engine=LocalEngine())

    def test_exact_candidate_fast_forwards_without_hooks_or_other_files(self):
        hook=self.root/'.git/hooks/post-merge';hook.write_text('#!/bin/sh\ntouch hook-ran\n');hook.chmod(0o755)
        (self.root/'.tmh').mkdir();(self.root/'.tmh/data').write_text('preserved')
        result=self.merge()
        self.assertEqual(result['commit'],self.candidate)
        self.assertEqual(self.git('rev-parse','HEAD'),self.candidate)
        self.assertEqual((self.root/'example.py').read_text(),'new\n')
        self.assertEqual((self.root/'.tmh/data').read_text(),'preserved')
        self.assertFalse((self.root/'hook-ran').exists())
        self.assertEqual(verify_merged('sha256:'+'a'*64,self.root,self.base,self.candidate,self.ref,'main',engine=LocalEngine())['commit'],self.candidate)
        (self.root/'example.py').write_text('new uncommitted change')
        with self.assertRaises(ValueError):
            verify_merged('sha256:'+'a'*64,self.root,self.base,self.candidate,self.ref,'main',engine=LocalEngine())

    def test_dirty_or_moved_source_fails_without_overwriting(self):
        (self.root/'example.py').write_text('user changes\n')
        with self.assertRaises(ValueError):self.merge()
        self.assertEqual((self.root/'example.py').read_text(),'user changes\n')
        self.assertEqual(self.git('rev-parse','HEAD'),self.base)
        (self.root/'example.py').write_text('old\n')
        (self.root/'untracked').write_text('keep')
        with self.assertRaises(ValueError):self.merge()
        self.assertEqual((self.root/'untracked').read_text(),'keep')

    def test_wrong_ref_or_branch_never_mutates(self):
        self.git('update-ref',self.ref,self.base)
        with self.assertRaises(ValueError):self.merge()
        self.assertEqual(self.git('rev-parse','HEAD'),self.base)

    def test_ignored_cache_is_preserved_and_ignored_collision_is_never_overwritten(self):
        (self.root/'.git/info/exclude').write_text('cache/\nnew.txt\n')
        (self.root/'cache').mkdir();(self.root/'cache/keep').write_text('cache')
        (self.root/'new.txt').write_text('user data')
        with self.assertRaises(ValueError):self.merge()
        self.assertEqual((self.root/'new.txt').read_text(),'user data')
        self.assertEqual(self.git('rev-parse','HEAD'),self.base)
        (self.root/'new.txt').unlink()
        self.merge()
        self.assertEqual((self.root/'cache/keep').read_text(),'cache')
        self.assertEqual((self.root/'new.txt').read_text(),'candidate file\n')

    def test_options_cannot_be_injected(self):
        with self.assertRaises(ValueError):
            fast_forward('sha256:'+'a'*64,self.root,self.base,self.candidate,self.ref,'--help',engine=LocalEngine())

    def test_lfs_filter_is_refused_with_clear_reason(self):
        (self.root/'.git/info/attributes').write_text('example.py filter=lfs\n')
        with self.assertRaisesRegex(ValueError,'LFS'):self.merge()
        self.assertEqual(self.git('rev-parse','HEAD'),self.base)
        self.assertEqual((self.root/'example.py').read_text(),'old\n')


if __name__=='__main__':unittest.main()
