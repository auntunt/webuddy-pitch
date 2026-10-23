"""Real tenant gateway and official stdio SDK preserve historical read semantics."""
from contextlib import asynccontextmanager
from datetime import timedelta
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from tests import test_tool_gateway as gateway


SDK_AVAILABLE = sys.version_info >= (3, 10) and importlib.util.find_spec('mcp') is not None
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix' and SDK_AVAILABLE, 'personal tenant stdio requires POSIX and optional MCP SDK')
class ToolReadMCPTest(unittest.IsolatedAsyncioTestCase):
    setUp = gateway.ToolGatewayTest.setUp
    change = gateway.ToolGatewayTest.change
    request = gateway.ToolGatewayTest.request
    token = gateway.ToolGatewayTest.token
    connections = gateway.ToolGatewayTest.connections
    grant = gateway.ToolGatewayTest.grant

    @asynccontextmanager
    async def session(self, credential):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from tmh.workbench_credentials import save
        with tempfile.TemporaryDirectory(prefix='tool-read-mcp-') as directory:
            path = Path(directory).resolve() / 'credential.json'
            save(path, {'schema': 1, 'endpoint': f'http://127.0.0.1:{self.port}/t/{self.a}',
                        'token': credential['token']})
            params = StdioServerParameters(command=sys.executable,
                args=[str(ROOT / 'tmh/workbench_entry.py'), 'mcp', '--credential-file', str(path),
                      '--agent', 'history-reader', '--read-only'],
                cwd=directory, env={'PYTHONPATH': '', 'NO_PROXY': '*', 'no_proxy': '*'})
            with tempfile.TemporaryFile(mode='w+') as errlog:
                async with stdio_client(params, errlog=errlog) as (reader, writer):
                    async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=10)) as client:
                        await client.initialize()
                        yield client

    def candidate(self, summary):
        from tmh.platform import candidates
        from tmh.platform.store import Store
        data = Path(self.reg.one('SELECT path FROM tenants WHERE id=?', (self.a,))['path'])
        st = Store(data / 'platform.db')
        try:
            candidates.schema(st)
            run = st.create_run(1, 1, 'fixture', 'fix', 'owner', 'stored prompt')
            st.x("UPDATE runs SET status='done',result=?,output=? WHERE id=?", (summary, summary, run['id']))
            st.x('INSERT INTO code_candidates(ticket_id,run_id,agent,base_commit,commit_sha,requirement_hash,configuration_hash,criteria,summary,fingerprint,ref,artifact_dir,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 (1, run['id'], 'agent:fixture', 'a' * 40, 'b' * 40, 'c' * 64, 'd' * 64,
                  json.dumps([{'id': 'A1', 'text': summary}]), summary, 'mcp-history-fixture',
                  'refs/webuddy/candidates/fixture', str(data / 'recorded-candidate'), 'synthetic'))
            return st.one('SELECT id FROM code_candidates WHERE run_id=?', (run['id'],))['id']
        finally:
            st.db.close()

    async def test_real_tenant_candidate_history_is_unknown_complete_and_revocable(self):
        summary = '  固定历史原文\r\n不得把未知判断为失败。\t\r\n' * 1000
        cid = self.candidate(summary)
        grant = self.grant(scope='read')
        async with self.session(grant) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            self.assertIn('webuddy_candidate_get', names)
            self.assertIn('webuddy_candidates_list', names)
            self.assertNotIn('webuddy_candidate_verify', names)
            self.assertNotIn('webuddy_candidate_decide', names)
            for operation, args in [('candidate_get', {'candidate_id': cid}),
                                    ('candidates_list', {'ticket': 'SAME-1'})]:
                with self.subTest(operation=operation):
                    result = await client.call_tool('webuddy_' + operation, args)
                    self.assertFalse(result.isError, result)
                    self.assertEqual(len(result.content), 1)
                    self.assertEqual(json.loads(result.content[0].text), result.structuredContent)
                    card = result.structuredContent if operation == 'candidate_get' else result.structuredContent['items'][0]
                    self.assertEqual(card['summary'], summary)
                    self.assertEqual(card['criteria'][0]['text'], summary)
                    self.assertIsNone(card['current'])
                    self.assertIsNone(card['human_accepted'])
                    self.assertEqual(card['state'], 'not_checked')
                    self.assertEqual(card['preview_url'], '')
            status, _, receipt = self.connections(body={'action': 'revoke', 'connection_id': grant['connection_id'],
                                                        'request_id': 'revoke-live-mcp-history'})
            self.assertEqual(status, 200, receipt)
            denied = await client.call_tool('webuddy_candidate_get', {'candidate_id': cid})
            self.assertTrue(denied.isError)
            self.assertEqual(denied.structuredContent['status'], 401)


if __name__ == '__main__':
    unittest.main()
