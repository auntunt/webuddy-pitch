import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import project_vue_diagnostic as diagnostic


class VueDiagnosticTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.project={'id':1,'key':'JB','root':str(self.root)}
        self.row={'id':7,'ticket_id':3,'base_commit':'a'*40,'commit_sha':'b'*40,'ref':'refs/webuddy/candidates/7'}
        self.store=SimpleNamespace(ticket=lambda _: {'project_id':1},project=lambda _:self.project)
        self.P=SimpleNamespace(store=self.store,data_dir=str(self.root))
        self.authority=SimpleNamespace(image='sha256:'+'f'*64,current=lambda job:True)

    def test_result_is_partial_and_executes_readonly_offline(self):
        outputs={'vue_files':2,'templates_checked':1,'skipped':[],'bad':['example.vue [模板]']}
        class Engine:
            def run(self,spec,seconds,cancel,output):
                self_spec.append(spec)
                output(json.dumps(outputs).encode())
                return {'reason':'exited','returncode':0,'cleanup':True}
        self_spec=[]
        def create(image,source,destination,**kwargs):
            destination.mkdir()
            return {'commit':'b'*40}
        with patch.object(diagnostic,'capture',return_value=self.authority), patch.object(diagnostic,'Engine',Engine), \
             patch.object(diagnostic.candidates,'view',return_value={'current':True}), \
             patch.object(diagnostic,'personal_scope') as scope, \
             patch.object(diagnostic.project_snapshot,'current',return_value=True), \
             patch.object(diagnostic.project_snapshot,'create',side_effect=create):
            scope.return_value.__enter__.return_value=None
            result=diagnostic.run(self.P,self.row,'LYB')
        self.assertEqual(result['kind'],'partial_vue_diagnostic')
        self.assertEqual(result['bad'],['example.vue [模板]'])
        self.assertIn('不代表',result['scope'])
        self.assertEqual(result['commit'],'b'*40)
        spec=self_spec[0]
        self.assertTrue(spec['NetworkDisabled'])
        self.assertTrue(spec['HostConfig']['ReadonlyRootfs'])
        self.assertTrue(spec['HostConfig']['Mounts'][0]['ReadOnly'])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_other_project_and_revoked_access_fail(self):
        self.project['key']='RW'
        with self.assertRaisesRegex(ValueError,'仅支持'):
            diagnostic.run(self.P,self.row,'LYB')
        self.project['key']='JB'
        self.authority.current=lambda job:False
        with patch.object(diagnostic,'capture',return_value=self.authority), patch.object(diagnostic,'Engine'):
            with self.assertRaisesRegex(ValueError,'权限'):
                diagnostic.run(self.P,self.row,'LYB')

    def test_concurrent_diagnostic_is_rejected_without_starting_a_second_job(self):
        diagnostic._lock.acquire()
        try:
            with patch.object(diagnostic,'capture') as captured:
                with self.assertRaisesRegex(ValueError,'正在运行'):
                    diagnostic.run(self.P,self.row,'LYB')
                captured.assert_not_called()
        finally:
            diagnostic._lock.release()

    def test_revocation_before_result_prevents_reporting(self):
        class Engine:
            def run(engine,spec,seconds,cancel,output):
                output(json.dumps({'vue_files':1,'templates_checked':1,'skipped':[],'bad':[]}).encode())
                self.authority.current=lambda job:False
                return {'reason':'exited','returncode':0,'cleanup':True}
        def create(image,source,destination,**kwargs):
            destination.mkdir()
            return {'commit':'b'*40}
        with patch.object(diagnostic,'capture',return_value=self.authority), patch.object(diagnostic,'Engine',Engine), \
             patch.object(diagnostic.candidates,'view',return_value={'current':True}), \
             patch.object(diagnostic,'personal_scope') as scope, \
             patch.object(diagnostic.project_snapshot,'current',return_value=True), \
             patch.object(diagnostic.project_snapshot,'create',side_effect=create):
            scope.return_value.__enter__.return_value=None
            with self.assertRaisesRegex(ValueError,'权限'):
                diagnostic.run(self.P,self.row,'LYB')
        self.assertEqual(list(self.root.iterdir()),[])


if __name__=='__main__':unittest.main()
