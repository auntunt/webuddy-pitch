import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from tmh.platform.project_artifact import BUILD, INSTALL


class ProjectArtifactTest(unittest.TestCase):
    def test_real_git_bundle_preserves_base_and_exact_binary_change(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve();repo=root/'repo';repo.mkdir();workspace=root/'workspace';workspace.mkdir()
            def git(path,*args):
                return subprocess.run(['git','-C',str(path),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
            git(repo,'init','-q')
            (repo/'app.py').write_text('old\n');(repo/'binary.bin').write_bytes(b'\x00old\xff');(repo/'removed.txt').write_text('keep in source')
            git(repo,'add','app.py','binary.bin','removed.txt')
            git(repo,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','base')
            base=git(repo,'rev-parse','HEAD').decode().strip()
            (workspace/'app.py').write_text('new\n');(workspace/'binary.bin').write_bytes(b'\x00new\xff')
            script=BUILD.replace('/source/.git/objects',str(repo/'.git/objects')).replace('/workspace',str(workspace)).replace('/tmp/job-index',str(root/'index')).replace('/tmp/job.git',str(root/'scratch.git')).replace('/tmp/candidate.bundle',str(root/'output.bundle'))
            env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0')
            result=subprocess.run(['python3','-I','-c',script,base],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
                manifest=json.load(tar.extractfile('manifest.json'));bundle=tar.extractfile('candidate.bundle').read();patch=tar.extractfile('change.patch').read()
            self.assertEqual(manifest['base_commit'],base)
            self.assertEqual(manifest['deleted_files'],['removed.txt'])
            self.assertIn(b'GIT binary patch',patch)
            self.assertEqual(git(repo,'rev-parse','HEAD').decode().strip(),base)
            self.assertEqual((repo/'app.py').read_text(),'old\n')
            bundle_path=root/'candidate.bundle';bundle_path.write_bytes(bundle)
            clone=root/'clone';subprocess.run(['git','clone','-q',str(repo),str(clone)],check=True)
            git(clone,'fetch','-q',str(bundle_path),'refs/heads/candidate')
            commit=git(clone,'rev-parse','FETCH_HEAD').decode().strip()
            self.assertEqual(commit,manifest['commit'])
            self.assertEqual(git(clone,'rev-parse',commit+'^').decode().strip(),base)
            self.assertEqual(git(clone,'show',commit+':binary.bin'),b'\x00new\xff')
            self.assertEqual(git(clone,'show',commit+':app.py'),b'new\n')
            artifact_dir=root/'installer';artifact_dir.mkdir();(artifact_dir/'candidate.bundle').write_bytes(bundle)
            install=INSTALL.replace('/source/.git',str(repo/'.git')).replace('/workspace',str(artifact_dir))
            ref='refs/webuddy/candidates/'+'d'*64
            command=['python3','-I','-c',install,base,commit,ref,manifest['bundle_sha256'],manifest['patch_sha256']]
            for _ in range(2):
                installed=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
                self.assertEqual(installed.returncode,0,installed.stderr.decode(errors='replace'))
            self.assertEqual(git(repo,'rev-parse',ref).decode().strip(),commit)
            self.assertEqual(git(repo,'rev-parse','HEAD').decode().strip(),base)
            self.assertEqual((repo/'app.py').read_text(),'old\n')
            before=git(repo,'rev-parse',ref)
            bad=subprocess.run(command[:-1]+['0'*64],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
            self.assertNotEqual(bad.returncode,0)
            self.assertEqual(git(repo,'rev-parse',ref),before)


if __name__=='__main__':unittest.main()
