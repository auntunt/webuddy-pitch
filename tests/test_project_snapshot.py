import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from tmh.platform.project_snapshot import EXPORT, unpack, validate_workspace
from tmh.platform.project_artifact import BUILD


def archive(entries, commit='a' * 40):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as out:
        content = json.dumps({'commit': commit}).encode()
        info = tarfile.TarInfo('MANIFEST.json')
        info.size = len(content)
        out.addfile(info, io.BytesIO(content))
        for name, content, kind in entries:
            info = tarfile.TarInfo('tree/' + name)
            if kind == 'symlink':
                info.type = tarfile.SYMTYPE
                info.linkname = '../../outside'
                out.addfile(info)
            else:
                info.size = len(content)
                out.addfile(info, io.BytesIO(content))
    stream.seek(0)
    return stream


class ProjectSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def test_exports_exact_regular_files_and_version(self):
        target = self.root / 'job'
        result = unpack(archive([('src/app.py', b'hello\x00world', 'file')]), target)
        self.assertEqual(result, {'commit': 'a' * 40, 'files': 1, 'bytes': 11, 'lfs':{}})
        self.assertEqual((target / 'src/app.py').read_bytes(), b'hello\x00world')
        self.assertFalse((target / '.git').exists())

    def test_sensitive_special_duplicate_and_traversal_fail_without_partial_export(self):
        for invalid in ('src/private-key.pem', '.git/config', '../outside', 'src/link'):
            with self.subTest(invalid=invalid):
                target = self.root / 'job'
                kind = 'symlink' if invalid == 'src/link' else 'file'
                with self.assertRaises(ValueError):
                    unpack(archive([('src/ok.py', b'unchanged', 'file'), (invalid, b'x', kind)]), target)
                self.assertFalse(target.exists())
                self.assertFalse((self.root / 'outside').exists())
        with self.assertRaises(ValueError):
            unpack(archive([('a', b'1', 'file'), ('a', b'2', 'file')]), self.root / 'job')
        self.assertFalse((self.root / 'job').exists())

    def test_existing_workspace_is_never_overwritten(self):
        target = self.root / 'job'
        target.mkdir()
        (target / 'existing').write_text('keep')
        with self.assertRaises(ValueError):
            unpack(archive([('a', b'1', 'file')]), target)
        self.assertEqual((target / 'existing').read_text(), 'keep')

    def test_business_data_and_example_names_are_not_mistaken_for_secrets(self):
        target = self.root / 'job'
        values = [('data/history.txt', b'business', 'file'),
                  ('.env.example', b'API_KEY=placeholder', 'file'),
                  ('src/token_service.py', b'print(1)', 'file')]
        unpack(archive(values), target)
        self.assertEqual((target / 'data/history.txt').read_bytes(), b'business')
        self.assertEqual((target / '.env.example').read_bytes(), b'API_KEY=placeholder')
        self.assertTrue(validate_workspace(target))

    def test_real_git_export_uses_committed_bytes_and_rejects_sensitive_tree(self):
        repo = self.root / 'repo'
        repo.mkdir()
        def git(*args):
            return subprocess.run(['git', '-C', str(repo), *args], check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git('init', '-q')
        (repo / 'app.py').write_text('committed\n')
        git('add', 'app.py')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
        commit = git('rev-parse', 'HEAD').stdout.decode().strip()
        (repo / 'app.py').write_text('uncommitted\n')
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0')
        command = ['python3', '-I', '-c', EXPORT.replace('/source', str(repo)), 'HEAD']
        dirty = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.assertNotEqual(dirty.returncode, 0)
        self.assertIn(b'app.py', dirty.stderr)
        git('checkout', '--', 'app.py')
        (repo / '.tmh').mkdir()
        (repo / '.tmh' / 'platform-note').write_text('not project source')
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=True)
        target = self.root / 'exported'
        snapshot = unpack(io.BytesIO(result.stdout), target)
        self.assertEqual(snapshot['commit'], commit)
        self.assertEqual((target / 'app.py').read_text(), 'committed\n')
        self.assertFalse((target / '.tmh').exists())
        self.assertEqual((repo / '.tmh' / 'platform-note').read_text(), 'not project source')
        self.assertTrue(validate_workspace(target))
        (target / 'private-key.pem').write_text('synthetic')
        self.assertFalse(validate_workspace(target))
        (target / 'private-key.pem').unlink()
        (repo / '.env').write_text('ACCESS_TOKEN=synthetic\n')
        git('add', '.env')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'sensitive')
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b'synthetic', result.stdout)
        self.assertIn(b'WEBUDDY_BLOCK:', result.stderr)
        self.assertIn(b'.env', result.stderr)

    def test_exporter_rejects_secret_content_even_in_example_without_echoing_it(self):
        repo = self.root / 'repo'
        repo.mkdir()
        def git(*args):
            return subprocess.run(['git', '-C', str(repo), *args], check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git('init', '-q')
        synthetic = 'fake-' + 'a' * 24
        (repo / '.env.example').write_text('API_KEY=' + synthetic + '\n')
        git('add', '.env.example')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
        result = subprocess.run(['python3', '-I', '-c', EXPORT.replace('/source', str(repo)), 'HEAD'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'.env.example', result.stderr)
        self.assertNotIn(synthetic.encode(), result.stdout + result.stderr)

    def test_prefixed_environment_and_json_credentials_are_blocked_without_echo(self):
        value='synthetic-'+'q'*24
        cases=[('settings.env','OPENAI_API_KEY='+value+'\n'),
               ('settings.json',json.dumps({'api_key':value}))]
        for index,(name,content) in enumerate(cases):
            with self.subTest(name=name):
                repo=self.root/('repo'+str(index));repo.mkdir()
                def git(*args):
                    return subprocess.run(['git','-C',str(repo),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                git('init','-q');(repo/name).write_text(content);git('add',name)
                git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
                result=subprocess.run(['python3','-I','-c',EXPORT.replace('/source',str(repo)),'HEAD'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(name.encode(),result.stderr)
                self.assertNotIn(value.encode(),result.stdout+result.stderr)

    def test_code_expression_does_not_hide_quoted_or_template_credentials(self):
        secret='synthetic'+'z'*24
        cases=[
            ('component.vue', '<script>\nconst label = `welcome`;\nchangePassword = invokePasswordChangeDialog()\n</script>\n', True),
            ('component.ts', 'changePassword = invokePasswordChangeDialog()\n', True),
            ('component.js', 'password = "'+secret+'"\n', False),
            ('component.js', "password = '"+secret+"'\n", False),
            ('component.js', 'const text = `\npassword = '+secret+'()\n`;\n', False),
            ('settings.env', 'PASSWORD='+secret+'\n', False),
            ('component.js', 'password = '+secret+'\n', False),
            ('component.vue', '<script>\nchangePassword = "/api/account/changePassword"\n</script>\n', True),
            ('component.ts', 'updatePassword = "/api/account/updatePassword"\n', True),
            ('component.js', 'password = "/api/account/changePassword"\n', False),
            ('component.js', 'updatePassword = "/api/account/getUserProfile"\n', False),
            ('component.js', 'updatePassword = "/api/account/'+secret+'"\n', False),
            ('component.js', 'updatePassword = "/api/account/updatePassword?token='+secret+'"\n', False),
            ('component.js', 'updatePassword = "//remoteexamplelonghostname/account/changePassword"\n', False),
            ('component.js', 'const text = `\nupdatePassword = "/api/account/updatePassword"\n`;\n', False),
        ]
        for index,(name,content,allowed) in enumerate(cases):
            with self.subTest(index=index):
                repo=self.root/('expression'+str(index));repo.mkdir()
                def git(*args):
                    return subprocess.run(['git','-C',str(repo),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                git('init','-q');(repo/name).write_text(content);git('add',name)
                git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
                result=subprocess.run(['python3','-I','-c',EXPORT.replace('/source',str(repo)),'HEAD'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                self.assertEqual(result.returncode==0,allowed,result.stderr.decode(errors='replace'))
                if not allowed:
                    self.assertNotIn(secret.encode(),result.stdout+result.stderr)

    def test_lfs_original_is_verified_preserved_and_never_runs_project_filter(self):
        repo=self.root/'lfs-repo';repo.mkdir();workspace=self.root/'lfs-workspace'
        env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0')
        def git(*args):
            return subprocess.run(['git','-C',str(repo),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        git('init','-q');original=bytes(range(256))*4;oid=hashlib.sha256(original).hexdigest()
        pointer=('version https://git-lfs.github.com/spec/v1\noid sha256:'+oid+'\nsize '+str(len(original))+'\n').encode()
        (repo/'.gitattributes').write_text('*.bin filter=lfs -text\n');(repo/'image.bin').write_bytes(pointer)
        (repo/'app.py').write_text('old\n');git('add','.gitattributes','image.bin','app.py')
        git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
        commit=git('rev-parse','HEAD').stdout.decode().strip()
        object_path=repo/'.git/lfs/objects'/oid[:2]/oid[2:4]/oid;object_path.parent.mkdir(parents=True);object_path.write_bytes(original)
        sentinel=self.root/'filter-ran';git('config','filter.lfs.clean','touch '+str(sentinel))
        cmd=['python3','-I','-c',EXPORT.replace('/source',str(repo)),'HEAD']
        exported=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        self.assertEqual(exported.returncode,0,exported.stderr.decode(errors='replace'))
        self.assertFalse(sentinel.exists())
        result=unpack(io.BytesIO(exported.stdout),workspace)
        self.assertEqual((workspace/'image.bin').read_bytes(),original)
        self.assertEqual(result['lfs']['image.bin']['oid'],oid)
        (workspace/'app.py').write_text('new\n')
        metadata=self.root/'lfs.json';metadata.write_text(json.dumps(result['lfs']))
        script=BUILD.replace('/source/.git/objects',str(repo/'.git/objects')).replace('/workspace',str(workspace)).replace('/tmp/job-index',str(self.root/'index')).replace('/tmp/job.git',str(self.root/'scratch.git')).replace('/tmp/candidate.bundle',str(self.root/'output.bundle'))
        built=subprocess.run(['python3','-I','-c',script,commit,str(metadata)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        self.assertEqual(built.returncode,0,built.stderr.decode(errors='replace'))
        self.assertFalse(sentinel.exists())
        (workspace/'image.bin').write_bytes(original+b'changed')
        script2=script.replace(str(self.root/'index'),str(self.root/'index2')).replace(str(self.root/'scratch.git'),str(self.root/'scratch2.git')).replace(str(self.root/'output.bundle'),str(self.root/'output2.bundle'))
        changed=subprocess.run(['python3','-I','-c',script2,commit,str(metadata)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        self.assertNotEqual(changed.returncode,0)
        object_path.unlink()
        missing=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        self.assertNotEqual(missing.returncode,0)
        self.assertIn(b'image.bin',missing.stderr)
        self.assertNotIn(original,missing.stdout)


if __name__ == '__main__':
    unittest.main()
