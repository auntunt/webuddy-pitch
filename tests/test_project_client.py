import json
from pathlib import Path
import socket
import tempfile
import unittest

from tmh.platform.project_client import run, provider_binding
from tmh.platform.project_mcp import BoundJob
from tmh.platform.project_container import specification


class FakeVolume:
    def __init__(self, engine, image, workspace, seconds, cancel):
        self.image=image;self.workspace=workspace;self.name='webuddy-job-synthetic'
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def alive(self): return True
    def spec(self, command, seconds):
        spec=specification(self.image,command,self.workspace,seconds)
        spec['HostConfig']['Mounts']=[{'Type':'volume','Source':self.name,'Target':'/workspace','ReadOnly':False}]
        return spec
    def export(self, commit): return {'commit':commit,'files':1}


class ClientEngine:
    def __init__(self):
        self.initial_config = ''
        self.erased_config = None
        self.project_spec = None
        self.options = None
        self.profile_after = None

    def run(self, spec, seconds, *, cancel, output, receipt=None):
        if spec['NetworkDisabled']:
            self.project_spec = spec
            output(b'project done\n')
            if receipt is not None:
                receipt['cleanup'] = True
            return {'reason':'exited', 'returncode':0, 'cleanup':True}
        mounts = {x['Target']:x['Source'] for x in spec['HostConfig']['Mounts']}
        config = Path(mounts['/home/worker/.codex/config.toml'])
        self.initial_config = config.read_text()
        self.options=json.loads((Path(mounts['/fixture'])/'options.json').read_text())
        profile_target='/home/worker/.codex/'+self.options['profile']+'.config.toml'
        profile_path=Path(mounts[profile_target]) if self.options['profile'] else None
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(Path(mounts['/mcp-channel']) / 'mcp.sock'))
            with connection.makefile('r', encoding='utf-8') as reader:
                def call(value):
                    connection.sendall((json.dumps(value) + '\n').encode())
                    return json.loads(reader.readline())
                init = call({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})
                assert 'result' in init
                self.erased_config = config.read_text()
                self.profile_after = profile_path.read_text() if profile_path else None
                tools = call({'jsonrpc':'2.0','id':2,'method':'tools/list'})
                assert tools['result']['tools'][0]['name'] == 'project_exec'
                result = call({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{
                    'name':'project_exec','arguments':{'project':'JB','argv':['true']}}})
                assert not result['result']['isError']
        output(b'{"type":"item.completed","item":{"type":"agent_message","text":"done"}}\n')
        output(b'{"type":"turn.completed"}\n')
        return {'reason':'exited', 'returncode':0, 'cleanup':True}


class ProjectClientTest(unittest.TestCase):
    def test_initialize_erases_file_before_tools_and_runs_project_separately(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            workspace = root / 'project'
            workspace.mkdir()
            (workspace / 'app.py').write_text('safe\n')
            config = root / 'provider.toml'
            config.write_text('model_provider="fixture"\n[model_providers.fixture]\nname="fixture"\n[model_providers.fixture.http_headers]\nx-test="synthetic-canary"\n')
            config.chmod(0o600)
            engine = ClientEngine()
            output = []
            job = BoundJob('LYB', 'JB', workspace, 'sha256:'+'a'*64)
            result = run(job, config, 'synthetic task', 5, base_commit='b'*40, authorize=lambda j: j == job,
                         output=output.append, engine=engine, volume_factory=FakeVolume)
            self.assertEqual(result['returncode'], 0)
            self.assertIn('synthetic-canary', engine.initial_config)
            self.assertEqual(engine.erased_config, '')
            self.assertIn('synthetic-canary', config.read_text())
            self.assertEqual(engine.project_spec['HostConfig']['NetworkMode'], 'none')
            self.assertEqual([m['Target'] for m in engine.project_spec['HostConfig']['Mounts']], ['/workspace'])
            self.assertEqual(engine.project_spec['HostConfig']['Mounts'][0]['Type'], 'volume')
            self.assertTrue(result['volume_cleanup'])
            self.assertEqual(len(output), 2)
            self.assertTrue(result['client_completion']['completed'])
            self.assertTrue(result['client_completion']['answer'])

    def test_profile_and_model_are_bound_and_temporary_profile_is_erased(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve();workspace=root/'project';workspace.mkdir();(workspace/'a').write_text('safe')
            config=root/'config.toml';config.write_text('model_provider="fixture"\n[model_providers.fixture]\nname="fixture"\n');config.chmod(0o600)
            profile=root/'team.config.toml';profile.write_text('model="profile-model"\nmodel_provider="fixture"\napproval_policy="never"\n');profile.chmod(0o600)
            _,_,binding=provider_binding(config,'team','selected-model');engine=ClientEngine()
            job=BoundJob('LYB','JB',workspace,'sha256:'+'a'*64)
            result=run(job,config,'task',5,base_commit='b'*40,authorize=lambda j:True,engine=engine,
                       volume_factory=FakeVolume,profile='team',model='selected-model',expected_binding=binding)
            self.assertEqual(result['returncode'],0)
            self.assertEqual(engine.options,{'profile':'team','model':'selected-model'})
            self.assertEqual(engine.profile_after,'')
            self.assertIn('profile-model',profile.read_text())
            profile.write_text('model="other"\nmodel_provider="fixture"\n')
            with self.assertRaisesRegex(ValueError,'变化'):
                run(job,config,'task',5,base_commit='b'*40,authorize=lambda j:True,engine=ClientEngine(),
                    volume_factory=FakeVolume,profile='team',model='selected-model',expected_binding=binding)


if __name__ == '__main__':
    unittest.main()
