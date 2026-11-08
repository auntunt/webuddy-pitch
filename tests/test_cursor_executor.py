"""Targeted Cursor adapter checks; the supervised CLI fixture makes no model calls."""
import json
import os
from unittest.mock import patch
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

from tmh.platform import agents, agent_settings
from tmh.platform.store import Store
from tmh.platform.errors import ApiError


class CursorExecutorTest(unittest.TestCase):
    def test_commands_and_permission_boundary(self):
        conf = {'cursor': dict(agents.BUILTIN['cursor'], bin='fixture-cursor')}
        for mode in ('ask', 'analyze'):
            cmd = agents.command(conf, 'cursor', mode, 'prompt', Path('prompt'), Path('.'), Path('last'), model='sonnet')
            self.assertEqual(cmd[:6], ['fixture-cursor', '--print', '--output-format', 'stream-json', '--sandbox', 'enabled'])
            self.assertIn('--mode', cmd)
            self.assertNotIn('--force', cmd)
            self.assertNotIn('--approve-mcps', cmd)
            self.assertNotIn('prompt', cmd)
        for mode in ('fix', 'edit', 'kb', 'chart'):
            cmd = agents.command(conf, 'cursor', mode, 'prompt', Path('prompt'), Path('.'), Path('last'))
            self.assertIn('--force', cmd)
            self.assertNotIn('--mode', cmd)
            self.assertEqual(cmd[cmd.index('--sandbox')+1], 'enabled')
        for changes in ({'args':['--force']}, {'profile':'team'}, {'prompt_transport':'stdin'}):
            with self.assertRaises(ValueError):
                agents.engine_name('team-cursor', dict(engine='cursor', **changes))
        with self.assertRaises(ValueError):
            agents.member_codex_binding({'engine':'cursor'}, '')

    def test_agent_command_and_legacy_name_share_discovery(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(agents.shutil, 'which', side_effect=lambda name: '/fixture/agent' if name == 'agent' else None):
            self.assertEqual(agents.executable('cursor', {}), '/fixture/agent')
            self.assertEqual(agents.executable('cursor', {'bin':'cursor-agent'}), '/fixture/agent')
            self.assertEqual(agents.executable('cursor', {'bin':'/explicit/missing'}), '/explicit/missing')
        with patch.dict(os.environ, {'WEBUDDY_CURSOR_BIN':'/configured/agent'}):
            self.assertEqual(agents.executable('cursor', {'bin':'cursor-agent'}), '/configured/agent')

    def test_settings_alias_and_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = {'action':'create','name':'team-cursor','revision':agent_settings.view(root)['revision'],
                    'config':{'engine':'cursor','title':'Cursor','models':[], 'defaults':{},'timeout':60}}
            saved = agent_settings.save(root, body)
            self.assertEqual(agents.load_config(root)['team-cursor']['bin'], 'agent')
            with self.assertRaises(ApiError) as caught:
                agent_settings.save(root, body)
            self.assertEqual(caught.exception.code, 409)
            body.update(action='update', revision=saved['revision'])
            body['config']['engine'] = 'codex'
            with self.assertRaises(ApiError):
                agent_settings.save(root, body)

    def test_supervised_success_incomplete_and_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / 'fixture.py'
            script.write_text('''import json, sys, time
prompt = sys.stdin.read()
print(json.dumps({'type':'system','subtype':'init','session_id':'fixture-session','model':'fixture'}), flush=True)
if '--force' in sys.argv:
    from pathlib import Path
    Path('synthetic-change.txt').write_text('authorized fixture change')
if prompt == 'wait':
    time.sleep(30)
elif prompt.startswith('complete'):
    print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':'fixture answer'}), flush=True)
''')
            exe = root / ('cursor-fixture.cmd' if os.name == 'nt' else 'cursor-fixture')
            exe.write_text('@echo off\n"%s" "%s" %%*\n' % (sys.executable, script) if os.name == 'nt' else '#!%s\n%s' % (sys.executable, script.read_text()))
            exe.chmod(0o700)
            store = Store(root / 'platform.db')
            runner = agents.Runner(store, root)
            project = store.add_project('CURSOR', 'Synthetic', str(root))
            conf = {'cursor': {'engine':'cursor', 'bin':str(exe), 'resume':False, 'retry_busy':False}}
            try:
                for prompt, expected in [('complete' + 'x'*40000, 0), ('incomplete', 1)]:
                    run = store.create_run(project['id'], None, 'cursor', 'ask', 'tester', prompt)
                    store.update_run(run['id'], status='running')
                    code, result = runner.invoke(run['id'], project, None, 'cursor', conf, 'ask', prompt, root)
                    self.assertEqual(code, expected, result)
                    self.assertEqual((root / 'runs' / str(run['id']) / 'session.txt').read_text(), 'fixture-session')
                    self.assertTrue(list((root / 'runs' / str(run['id'])).rglob('process.json')))
                    runner.finish_invocation(run['id'], code, result)
                run = store.create_run(project['id'], None, 'cursor', 'fix', 'tester', 'complete')
                store.update_run(run['id'], status='running')
                code, result = runner.invoke(run['id'], project, None, 'cursor', conf, 'fix', 'complete', root)
                self.assertEqual(code, 0, result)
                self.assertEqual((root/'synthetic-change.txt').read_text(), 'authorized fixture change')
                runner.finish_invocation(run['id'], code, result)
                run = store.create_run(project['id'], None, 'cursor', 'ask', 'tester', 'wait')
                store.update_run(run['id'], status='running')
                output = []
                def invoke():
                    output.append(runner.invoke(run['id'], project, None, 'cursor', conf, 'ask', 'wait', root))
                thread = threading.Thread(target=invoke)
                thread.start()
                deadline = time.monotonic() + 5
                while not runner.procs and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(runner.procs)
                runner.cancel(run['id'], 'tester')
                thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertNotEqual(output[0][0], 0)
                self.assertFalse(runner.procs)
            finally:
                self.assertTrue(runner.wait_for_idle(10))
                store.db.close()
