"""Real stdio MCP -> signed tenant gateway -> independent worker -> SQLite."""
from contextlib import asynccontextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import unittest

from tests import test_tool_gateway as tool_fixtures
from tests import test_workbench_mcp as mcp_fixtures
from tmh import graph


@unittest.skipUnless(os.name=='posix' and mcp_fixtures.SDK_AVAILABLE,'POSIX private worker and .[mcp] required')
class ReformTenantMCPTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture=tool_fixtures.ToolGatewayTest('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        f=self.fixture
        data=Path(f.reg.one('SELECT path FROM tenants WHERE id=?',(f.a,))['path'])
        root=data/'repositories'/'same'
        node={'id':'dom:sales','kind':'dom','name':'sales','label':'Sales','file':'','line':0,'end':0,
              'domain':'sales','module':'','hash':'fixture','data':{'key':'sales'}}
        graph._write_db(root,{node['id']:node},[],{'built_at':'fixed-fixture'})
        self.grant=f.grant()
        self.endpoint='http://127.0.0.1:%d/t/%s'%(f.port,f.a)

    @asynccontextmanager
    async def session(self, grant):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params=StdioServerParameters(command=sys.executable,
            args=['-m','tmh.workbench','mcp','--endpoint',self.endpoint,'--agent','reform-fixture'],
            env={'PYTHONPATH':str(mcp_fixtures.ROOT),'WEBUDDY_TOOL_TOKEN':grant['token']},cwd=str(mcp_fixtures.ROOT))
        # The bridge intentionally accepts credentials through its documented file path.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            credential=Path(tmp).resolve()/'synthetic.json'
            credential.write_text(json.dumps({'schema':1,'endpoint':self.endpoint,'token':grant['token']}))
            credential.chmod(0o600)
            params.env['WEBUDDY_CREDENTIAL_FILE']=str(credential)
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=15)) as session:
                    await session.initialize()
                    yield session

    async def call(self, session, operation, args, error=False):
        r=await session.call_tool('webuddy_'+operation,args)
        self.assertEqual(bool(r.isError),error,r)
        return r.structuredContent

    async def test_tenant_reconnect_worker_restart_project_scope_and_revocation(self):
        f=self.fixture
        async with self.session(self.grant) as session:
            tools={t.name for t in (await session.list_tools()).tools}
            self.assertIn('webuddy_reform_create',tools)
            self.assertNotIn('webuddy_reform_control',tools)
            preview=await self.call(session,'reform_preview',{'project':'SAME','scope_mode':'selected','domains':['dom:sales']})
            plan=await self.call(session,'reform_create',dict(project='SAME',kind='restructure',title='Tenant reform',
                goal='Full tenant contract',keep='Keep behavior',scope_mode='selected',domains=['dom:sales'],
                lead={'title':'','body':''},wave=1,source_version='a'*40,target_environment='isolated fixture',
                criteria=['Keep behavior'],dependencies=[],target='',knowledge_revision=preview['knowledge_revision'],request_id='tenant-plan-create'))
            resource={'project':'SAME','plan_id':plan['id']}
            denied=await self.call(session,'reform_get',dict(resource,project='PRIVATE'),True)
            self.assertIn(denied['status'],(403,404))
            denied=await self.call(session,'reform_archive',dict(resource,expected_revision=plan['revision'],request_id='not-manager'),True)
            self.assertEqual(denied['status'],403)
        f.workers.stop(f.a)
        async with self.session(self.grant) as session:
            current=await self.call(session,'reform_get',resource)
            self.assertEqual(current['id'],plan['id'])
            receipt=await self.call(session,'request_get',{'request_id':'tenant-plan-create'})
            self.assertEqual(receipt['state'],'complete')
            f.change('project_revoke',tenant=f.a,user='alice',project_id=1)
            denied=await self.call(session,'reform_get',resource,True)
            self.assertIn(denied['status'],(401,403))
            denied=await self.call(session,'request_get',{'request_id':'tenant-plan-create'},True)
            self.assertIn(denied['status'],(401,403))
