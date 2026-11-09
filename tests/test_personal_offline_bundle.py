"""Synthetic-only checks. Never read the test runner's own AI credentials."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


builder=load('personal_builder','scripts/deploy/build-personal-offline.py')
launcher=load('personal_launcher','scripts/deploy/personal-offline/launcher.py')


class PersonalOfflineTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.runtime=self.root/'runtime.zip'
        with zipfile.ZipFile(self.runtime,'w') as z:z.writestr('Webuddy/release.json',json.dumps({'source_commit':'a'*40}))
        self.receipt=self.root/'bundle.json';self.receipt.write_text(json.dumps({'distribution':'customer','source_commit':'a'*40,'sha256':builder.digest(self.runtime),'bytes':self.runtime.stat().st_size}))
        self.codex=self.root/'codex';self.codex.mkdir()
        (self.codex/'auth.json').write_text(json.dumps({'tokens':{'access_token':'synthetic-login'}}))
        (self.codex/'config.toml').write_text('model="fixture"\nmodel_provider="fixture"\n[model_providers.fixture]\nbase_url="https://example.invalid"\nexperimental_bearer_token="synthetic-codex"\n[projects.private]\ntrust_level="trusted"\n')
        (self.codex/'history.jsonl').write_text('never copy this history')
        self.claude=self.root/'claude-settings.json';self.claude.write_text(json.dumps({'env':{'ANTHROPIC_AUTH_TOKEN':'synthetic-claude','ANTHROPIC_BASE_URL':'https://example.invalid','UNRELATED_SECRET':'never-copy'},'permissions':{'allow':['Bash(*)']},'model':'fixture'}))

    def build(self):
        return builder.build(self.runtime,self.receipt,self.root/'out',self.codex,self.claude)

    def test_personal_wrapper_preserves_runtime_and_excludes_unrelated_state(self):
        before=(self.codex/'auth.json').read_bytes();report=self.build()
        with zipfile.ZipFile(self.root/'out'/report['archive']) as z:
            names=z.namelist();manifest=json.loads(z.read('Webuddy-personal/PERSONAL.json'))
            self.assertEqual(z.read('Webuddy-personal/runtime.zip'),self.runtime.read_bytes())
            self.assertFalse(any('cursor' in n or 'history' in n for n in names))
            config=tomllib.loads(z.read('Webuddy-personal/profiles/codex/config.toml').decode())
            self.assertEqual(config['model_providers']['fixture']['experimental_bearer_token'],'synthetic-codex')
            self.assertNotIn('projects',config)
            settings=json.loads(z.read('Webuddy-personal/profiles/claude/settings.json'))
            self.assertEqual(settings['env']['ANTHROPIC_AUTH_TOKEN'],'synthetic-claude')
            self.assertNotIn('permissions',settings);self.assertNotIn('UNRELATED_SECRET',settings['env'])
            for name,digest in manifest['files'].items():self.assertEqual(hashlib.sha256(z.read('Webuddy-personal/'+name)).hexdigest(),digest)
        self.assertEqual((self.codex/'auth.json').read_bytes(),before)
        self.assertEqual(report['cursor'],'reuse_target_device_login')

    def test_bootstrap_is_idempotent_preserves_refresh_and_existing_cursor(self):
        report=self.build();extracted=self.root/'中文 space';extracted.mkdir()
        with zipfile.ZipFile(self.root/'out'/report['archive']) as z:z.extractall(extracted)
        root=extracted/'Webuddy-personal';local=self.root/'local';cursor=local/'Cursor/auth.json';cursor.parent.mkdir(parents=True);cursor.write_bytes(b'existing-target-login')
        config=launcher.prepare(root,local);data=json.loads(config.read_text());env=data['environment']
        self.assertFalse(any(k.startswith('CURSOR') or k in ('HOME','APPDATA') for k in env))
        auth=Path(env['CODEX_HOME'])/'auth.json';auth.write_text('refreshed synthetic credentials')
        self.assertEqual(launcher.prepare(root,local),config)
        self.assertEqual(auth.read_text(),'refreshed synthetic credentials')
        self.assertEqual(cursor.read_bytes(),b'existing-target-login')
        (root/'profiles/codex/auth.json').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'integrity'):launcher.prepare(root,local)

    def test_refuses_corrupt_runtime_and_missing_auth(self):
        self.runtime.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'receipt'):self.build()
        self.assertFalse((self.root/'out').exists())
