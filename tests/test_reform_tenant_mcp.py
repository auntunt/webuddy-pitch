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

    async def test_legacy_accepted_lead_does_not_crash_read_only_worker_startup(self):
        from tmh.platform import reform
        from tmh.platform.store import Store
        f=self.fixture
        data=Path(f.reg.one('SELECT path FROM tenants WHERE id=?',(f.a,))['path'])
        store=Store(data/'platform.db')
        try:
            plan=reform.create(data,'SAME',{'built':'fixed','domains':[{'id':'sales','title':'Sales','tables':0}]},
                {'title':'Legacy reform','goal':'Keep old evidence','wave':1},'owner')
            plan['id']='r1'
            plan.pop('uid')
            plan['items'][0].update(ticket='SAME-1',lead=True)
            store.update_ticket(1,'fixture',status='closed',links={'reform':{'plan':'r1','order':plan['items'][0]['order']}})
            store.event(1,'fixture','adopt','synthetic historical adoption',{'branch':'historic','commit':'a'*40})
            store.event(1,'fixture','accept','验收通过：synthetic old verdict')
            folder=data/'reforms';folder.mkdir(exist_ok=True)
            original=json.dumps([plan],ensure_ascii=False).encode()
            (folder/'SAME.json').write_bytes(original)
            store.x('DELETE FROM reform_catalog WHERE project_key=?',('SAME',))
        finally:
            store.db.close()
        for restart in (False,True):
            if restart:
                f.workers.stop(f.a)
            async with self.session(self.grant) as session:
                state=await self.call(session,'status',{})
                projects=await self.call(session,'projects_list',{})
                self.assertEqual([p['key'] for p in projects['items']],['SAME'])
                current=await self.call(session,'reform_get',{'project':'SAME','plan_id':'r1'})
                self.assertIn('旧计划缺少固定源版本',current['blocked'])
                self.assertEqual(current['evidence']['integrated_delivery'],'pending')
        self.assertEqual((folder/'SAME.json').read_bytes(),original)

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
            export_args=dict(resource,expected_revision=plan['revision'],request_id='frozen-report')
            manifest=await self.call(session,'reform_report_create',export_args)
            self.assertEqual(await self.call(session,'reform_report_create',export_args),manifest)
            exported=dict(resource,export_id=manifest['export_id'])
            chunk=await self.call(session,'reform_report_get',dict(exported,file='plan.json',offset=0))
            import base64,hashlib
            self.assertEqual(hashlib.sha256(base64.b64decode(chunk['data_base64'])).hexdigest(),chunk['sha256'])
            denied=await self.call(session,'reform_report_get',dict(exported,project='PRIVATE'),True)
            self.assertIn(denied['status'],(403,404))
            reader=f.grant(scope='read',rid='report-reader')
            async with self.session(reader) as readonly:
                self.assertEqual(await self.call(readonly,'reform_report_get',exported),manifest)
                result=await readonly.call_tool('webuddy_reform_report_create',dict(export_args,request_id='read-denied'))
                self.assertTrue(result.isError)

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
            self.assertEqual(await self.call(session,'reform_report_get',exported),manifest)
            f.change('project_revoke',tenant=f.a,user='alice',project_id=1)
            denied=await self.call(session,'reform_report_get',dict(exported,file='plan.json',offset=0),True)
            self.assertIn(denied['status'],(401,403))
            denied=await self.call(session,'reform_get',resource,True)
            self.assertIn(denied['status'],(401,403))
            denied=await self.call(session,'request_get',{'request_id':'tenant-plan-create'},True)
            self.assertIn(denied['status'],(401,403))

        # A newly issued content connection may archive only after the current
        # member actually receives project management authority.
        f.change('project_grant',tenant=f.a,user='alice',project_id=1,role='manager')
        manager=f.grant(rid='new-manager-connection')
        async with self.session(manager) as session:
            current=await self.call(session,'reform_get',resource)
            archived=await self.call(session,'reform_archive',dict(resource,expected_revision=current['revision'],request_id='manager-archive'))
            self.assertTrue(archived['archived'])
