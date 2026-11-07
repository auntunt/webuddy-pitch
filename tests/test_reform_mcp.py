"""Official MCP SDK/stdio against the actual HTTP service and durable SQLite plans."""
import json
from http.server import ThreadingHTTPServer
import threading
import unittest
from unittest.mock import patch

from tests import test_workbench_mcp as mcp_fixtures
from tests import test_external_candidates as fixtures
from tmh.platform.server import make_handler
from tmh.platform import reform


@unittest.skipUnless(mcp_fixtures.SDK_AVAILABLE,'install .[mcp] for protocol verification')
class ReformMCPTest(unittest.IsolatedAsyncioTestCase):
    session = mcp_fixtures.WorkbenchMCPTest.session

    def setUp(self):
        self.fixture=fixtures.ExternalCandidateTest('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.P=self.fixture.P
        self.submitted=[]
        dispatch=patch.object(self.P.flow,'submit',side_effect=lambda p,t:self.submitted.append(t['key']))
        dispatch.start()
        self.addCleanup(dispatch.stop)
        self.atlas={'built':'fixed-knowledge','domains':[{'id':'sales','title':'Sales','tables':1}]}
        patched=patch.object(self.P.kb,'atlas',return_value=self.atlas)
        patched.start()
        self.addCleanup(patched.stop)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.P,token='stdio-fixture-token'))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.thread.join,2)
        self.addCleanup(self.http.shutdown)
        self.endpoint='http://127.0.0.1:'+str(self.http.server_port)

    async def call(self, session, name, body, error=False):
        result=await session.call_tool('webuddy_'+name,body)
        self.assertEqual(bool(result.isError),error,result)
        return result.structuredContent

    async def create(self, session):
        preview=await self.call(session,'reform_preview',{'project':'EXT','scope_mode':'selected','domains':['sales']})
        args=dict(project='EXT',kind='restructure',title='Sales reform',goal='Preserve full scope\n' * 400,
            keep='Preserve refund rules',scope_mode='selected',domains=['sales'],lead={'title':'','body':''},wave=1,
            source_version=self.fixture.sha,target_environment='isolated-fixture',criteria=['Refund rules preserved'],
            dependencies=[],target='',knowledge_revision=preview['knowledge_revision'],request_id='plan-stable-create')
        plan=await self.call(session,'reform_create',args)
        self.assertEqual(await self.call(session,'reform_create',args),plan)
        self.assertEqual(len(reform.plans(self.P.data_dir,'EXT')),1)
        self.assertEqual(plan['goal'],args['goal'])
        self.assertEqual(plan['counts']['released'],0)
        return plan,args

    async def test_create_reconnect_conflict_and_lookup_same_plan(self):
        async with self.session('--allow-execution') as session:
            names={t.name for t in (await session.list_tools()).tools}
            self.assertTrue({'webuddy_reform_create','webuddy_reform_get','webuddy_reform_control','webuddy_reform_events','webuddy_run_recover'}<=names)
            plan,args=await self.create(session)
            resource=dict(project='EXT',plan_id=plan['id'])
            state=await self.call(session,'reform_resume_preview',resource)
            self.assertEqual(state['evidence']['current_validity'],'not_checked')
            self.assertEqual(state['counts']['released'],0)
            updated=await self.call(session,'reform_update',dict(resource,expected_revision=plan['revision'],
                reason='Fixture confirmed correction',changes={'keep':'Preserve full refund and tax rules'},request_id='plan-update'))
            stale=await self.call(session,'reform_control',dict(resource,expected_revision=plan['revision'],action='pause',request_id='stale-control'),True)
            self.assertEqual(stale['status'],409)
        # Closing the MCP process does not delete or rebuild platform state.
        async with self.session('--allow-execution') as session:
            current=await self.call(session,'reform_get',resource)
            self.assertEqual(current['revision'],updated['revision'])
            self.assertEqual(current['deep_link'],plan['deep_link'])
            receipt=await self.call(session,'request_get',{'request_id':'plan-stable-create'})
            self.assertEqual(receipt['state'],'complete')
            paused=await self.call(session,'reform_control',dict(resource,expected_revision=current['revision'],action='pause',request_id='pause-current'))
            self.assertIn('当前运行继续',paused['paused'])
            # Explicit scheduling substitute: tickets/outbox/HTTP are real; no model is launched.
            resumed=await self.call(session,'reform_control',dict(resource,expected_revision=paused['revision'],action='resume',request_id='resume-current'))
            self.assertEqual(resumed['request_state'],'accepted')
            self.assertEqual(len(self.submitted),1)
            replay=await self.call(session,'reform_control',dict(resource,expected_revision=paused['revision'],action='resume',request_id='resume-current'))
            self.assertEqual(replay,resumed)
            self.assertEqual(len(self.submitted),1)
            latest=await self.call(session,'reform_get',resource)
            self.assertEqual(latest['counts']['released'],1)
            conflict=await self.call(session,'reform_create',dict(args,title='Different content'),True)
            self.assertEqual(conflict['status'],409)
            events=await self.call(session,'reform_events',dict(resource,limit=1))
            self.assertEqual(len(events['items']),1)
            self.assertTrue(events['has_more'])

    async def test_sdk_readonly_hides_and_rejects_writes_and_execution_flag_is_required(self):
        async with self.session('--read-only') as session:
            names={t.name for t in (await session.list_tools()).tools}
            self.assertIn('webuddy_reform_preview',names)
            self.assertNotIn('webuddy_reform_create',names)
            rejected=await session.call_tool('webuddy_reform_create',{})
            self.assertTrue(rejected.isError)
        async with self.session() as session:
            names={t.name for t in (await session.list_tools()).tools}
            self.assertIn('webuddy_reform_create',names)
            self.assertNotIn('webuddy_reform_control',names)
