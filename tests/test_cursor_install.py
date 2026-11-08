"""Cursor project setup and actual stdio transport, not Cursor host approval."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tmh import install


class CursorInstallTests(unittest.TestCase):
    def test_native_launch_preserves_other_servers_and_refreshes(self):
        with tempfile.TemporaryDirectory(prefix='cursor 项目 ') as folder:
            root=Path(folder)/'repo with spaces'
            (root/'.cursor').mkdir(parents=True)
            custom={'mcpServers':{'customer':{'command':'customer-tool'}},'other':'preserved'}
            config=root/'.cursor/mcp.json'
            config.write_text(json.dumps(custom))
            original=b'# Project instructions\r\nKeep this.  \r\n'
            (root/'AGENTS.md').write_bytes(original)
            for _ in range(2): install.install(root,['cursor'])
            result=json.loads(config.read_text())
            self.assertEqual(result['mcpServers']['customer'],custom['mcpServers']['customer'])
            self.assertEqual(result['other'],'preserved')
            self.assertTrue((root/'AGENTS.md').read_bytes().startswith(original))
            self.assertFalse((root/'.cursor/cli.json').exists())
            self.assertFalse((root/'.cursor/hooks.json').exists())
            for name in ('legacy-feature','migrate-to-java','xinchuang-migrate'):
                self.assertTrue((root/'.cursor/skills'/name/'SKILL.md').is_file())
            entry=result['mcpServers']['tmh']
            messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}}},
                      {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}]
            run=subprocess.run([entry['command'],*entry['args']],cwd=Path(folder),input=''.join(json.dumps(m)+'\n' for m in messages),text=True,capture_output=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stderr)
            replies=[json.loads(line) for line in run.stdout.splitlines()]
            self.assertTrue(replies[0]['result']['serverInfo'])
            names={t['name'] for t in replies[1]['result']['tools']}
            self.assertTrue({'context','flows','impact','trace'}<=names,names)

    def test_unknown_engine_does_not_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'untouched'
            with self.assertRaises(ValueError):install.install(root,['curser'])
            self.assertFalse(root.exists())
