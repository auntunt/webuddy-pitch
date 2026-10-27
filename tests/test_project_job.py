import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tmh.platform import project_job


class ProjectJobTest(unittest.TestCase):
    def test_fixed_source_binds_candidate_and_preserves_raw_outputs(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve();folder=root/'job';calls=[];base='a'*40
            def snapshot(image,source,workspace,**kwargs):
                calls.append(('snapshot',kwargs['ref']));workspace.mkdir();(workspace/'a').write_text('old')
                return {'commit':base,'archive_sha256':'b'*64}
            def client(job,config,prompt,seconds,**kwargs):
                calls.append(('client',kwargs['base_commit']));kwargs['output'](b'client\n');kwargs['tool_output'](b'raw\xff')
                (job.workspace/'a').write_text('new')
                return {'reason':'exited','returncode':0,'cleanup':True,'volume_cleanup':True,'workspace':{'base_commit':base}}
            def artifact(image,source,workspace,commit,folder,**kwargs):
                calls.append(('artifact',commit));self.assertEqual((workspace/'a').read_text(),'new')
                return {'base_commit':commit,'commit':'c'*40,'cleanup':True}
            with patch.object(project_job.project_snapshot,'create',side_effect=snapshot), patch.object(project_job.project_client,'run',side_effect=client), patch.object(project_job.project_artifact,'create',side_effect=artifact):
                result=project_job.run(principal='LYB',project='JB',source=root,image='sha256:'+'d'*64,
                    provider_config=root/'config',prompt='complete task',folder=folder,seconds=10,
                    authorize=lambda job:job.principal=='LYB' and job.project=='JB',source_current=lambda commit:commit==base,ref='main')
            self.assertEqual(calls,[('snapshot','main'),('client',base),('artifact',base)])
            self.assertEqual(result['status'],'proposal')
            self.assertEqual(json.loads((folder/'receipt.json').read_text())['candidate']['base_commit'],base)
            self.assertEqual((folder/'tool-output.bin').read_bytes(),b'raw\xff')
            self.assertEqual((folder/'client-output.bin').read_bytes(),b'client\n')

    def test_revocation_after_model_prevents_candidate_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve();folder=root/'job';allowed=[True]
            def snapshot(image,source,workspace,**kwargs):
                workspace.mkdir();return {'commit':'a'*40,'archive_sha256':'b'*64}
            def client(job,config,prompt,seconds,**kwargs):
                kwargs['output'](b'partial');allowed[0]=False
                return {'reason':'exited','returncode':0,'cleanup':True,'volume_cleanup':True,'workspace':{'base_commit':'a'*40}}
            with patch.object(project_job.project_snapshot,'create',side_effect=snapshot), patch.object(project_job.project_client,'run',side_effect=client), patch.object(project_job.project_artifact,'create') as artifact:
                with self.assertRaises(ValueError):
                    project_job.run(principal='LYB',project='JB',source=root,image='sha256:'+'d'*64,
                        provider_config=root/'config',prompt='task',folder=folder,seconds=10,
                        authorize=lambda job:allowed[0],source_current=lambda commit:True)
            artifact.assert_not_called()
            self.assertEqual(json.loads((folder/'receipt.json').read_text())['status'],'failed')
            self.assertEqual((folder/'client-output.bin').read_bytes(),b'partial')


if __name__=='__main__':unittest.main()
