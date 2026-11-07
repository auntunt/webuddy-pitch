"""Official MCP SDK/stdio against the actual HTTP service and durable SQLite plans."""
import asyncio
import json
import os
import sys
from http.server import ThreadingHTTPServer
import threading
import unittest
import urllib.request
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
        self.atlas={'built':'fixed-knowledge','domains':[{'id':'sales','title':'Sales','tables':1,'flows':1}]}
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
            drafts=await self.call(session,'reforms_list',{'project':'EXT','status':'draft','limit':1})
            self.assertEqual([p['id'] for p in drafts['items']],[plan['id']])
            blocked_list=await self.call(session,'reforms_list',{'project':'EXT','status':'blocked'})
            self.assertEqual(blocked_list['items'],[])
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



    async def test_lost_outer_receipt_is_reconciled_only_by_original_write_replay(self):
        async with self.session('--allow-execution') as session:
            plan,args=await self.create(session)
            resource=dict(project='EXT',plan_id=plan['id'])
            original=dict(resource,expected_revision=plan['revision'],request_id='response-lost-start',action='start')
            accepted=await self.call(session,'reform_control',original)
            self.assertEqual(len(self.submitted),1)
            # Fault at the outer receipt boundary: inner plan/mapping/outbox receipt remains committed.
            self.P.store.x("UPDATE agent_requests SET state='uncertain',result='' WHERE request_id=?",(original['request_id'],))
            receipt=await self.call(session,'request_get',{'request_id':original['request_id']})
            self.assertEqual(receipt['state'],'uncertain')
            self.assertTrue(receipt['needs_reconcile'])
            self.assertEqual(self.P.store.one('SELECT state FROM agent_requests WHERE request_id=?',(original['request_id'],))['state'],'uncertain')
            recovered=await self.call(session,'reform_control',original)
            self.assertEqual(recovered,accepted)
            self.assertEqual(len(self.submitted),1)
            receipt=await self.call(session,'request_get',{'request_id':original['request_id']})
            self.assertEqual(receipt['state'],'complete')
            conflict=await self.call(session,'reform_control',dict(original,action='resume'),True)
            self.assertEqual(conflict['status'],409)

    async def test_two_stdio_clients_concurrently_start_one_batch_and_replay_one_receipt(self):
        async with self.session('--allow-execution') as first, self.session('--allow-execution') as second:
            plan,_=await self.create(first)
            resource=dict(project='EXT',plan_id=plan['id'])
            arguments=[dict(resource,expected_revision=plan['revision'],action='start',request_id='concurrent-'+str(i)) for i in range(2)]
            results=await asyncio.gather(*(session.call_tool('webuddy_reform_control',body) for session,body in zip((first,second),arguments)))
            self.assertEqual(sum(not result.isError for result in results),1)
            loser=next(result for result in results if result.isError)
            self.assertEqual(loser.structuredContent['status'],409)
            winner=next(i for i,result in enumerate(results) if not result.isError)
            replay=await first.call_tool('webuddy_reform_control',arguments[winner])
            self.assertFalse(replay.isError)
            self.assertEqual(replay.structuredContent,results[winner].structuredContent)
            self.assertEqual(len(self.submitted),1)
            self.assertEqual(len(self.P.store.q('SELECT * FROM reform_dispatch')),1)
        async with self.session('--allow-execution') as reconnected:
            current=await self.call(reconnected,'reform_get',resource)
            self.assertEqual(current['batch'],1)
            self.assertEqual(current['counts']['released'],1)
            receipt=await self.call(reconnected,'request_get',{'request_id':arguments[winner]['request_id']})
            self.assertEqual(receipt['state'],'complete')
            self.assertEqual(len(self.submitted),1)

    async def test_typed_preview_with_lead_matches_created_plan_without_start(self):
        async with self.session() as session:
            _,args=await self.create(session)
            lead={'title':'Shared foundation','body':'Full foundation scope\n'+'tail'*4000}
            preview=await self.call(session,'reform_preview',dict(project='EXT',scope_mode='selected',domains=['sales'],wave=2,lead=lead))
            saved=await self.call(session,'reform_create',dict(args,lead=lead,wave=2,knowledge_revision=preview['knowledge_revision'],request_id='lead-preview-create'))
            self.assertEqual(preview['items'],[{key:item[key] for key in expected} for expected,item in zip(preview['items'],saved['items'])])
            self.assertEqual(len(preview['items']),len(saved['items']))
            self.assertEqual(preview['batches'][0]['kind'],'lead')
            self.assertEqual(saved['counts']['released'],0)
            scope=await self.call(session,'reform_get',dict(project='EXT',plan_id=saved['id'],view='scope'))
            self.assertEqual(scope['scope']['lead'],lead)
            self.assertEqual(self.submitted,[])

    async def test_missing_initial_source_preview_and_control_agree(self):
        async with self.session('--allow-execution') as session:
            plan,_=await self.create(session)
            resource=dict(project='EXT',plan_id=plan['id'])
            changed=await self.call(session,'reform_update',dict(resource,expected_revision=plan['revision'],request_id='missing-initial-update',reason='Unfetched fixture source',changes={'source_version':'e'*40}))
            preview=await self.call(session,'reform_resume_preview',resource)
            self.assertIn('不可访问',preview['blocked'])
            self.assertNotIn('start',preview['allowed_actions'])
            failed=await self.call(session,'reform_control',dict(resource,expected_revision=changed['revision'],request_id='missing-initial-start',action='start'),True)
            self.assertEqual(failed['status'],409)
            self.assertEqual(self.submitted,[])

    def web(self,path,body=None):
        request=urllib.request.Request(self.endpoint+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'X-TMH-Token':'stdio-fixture-token','X-TMH':'1','Content-Type':'application/json'})
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    async def test_web_update_mcp_conflict_and_same_live_projection(self):
        async with self.session('--allow-execution') as session:
            plan,args=await self.create(session)
            resource=dict(project='EXT',plan_id=plan['id'])
            listed=self.web('/api/projects/EXT/reforms?view=list&status=draft&limit=1')
            self.assertEqual([p['id'] for p in listed['items']],[plan['id']])
            self.assertNotIn('goal',listed['items'][0])
            self.assertEqual(self.web('/api/projects/EXT/reforms?view=list&status=paused')['items'],[])
            current=self.web('/api/projects/EXT/reforms?plan_id='+plan['id'])
            self.assertEqual(current['revision'],plan['revision'])
            updated=self.web('/api/projects/EXT/reforms/'+plan['id'],dict(action='update',
                expected_revision=current['revision'],request_id='web-edit',reason='Fixture web change',changes={'keep':'Web confirmed constraints'}))
            stale=await self.call(session,'reform_control',dict(resource,expected_revision=plan['revision'],
                request_id='mcp-after-web-stale',action='start'),True)
            self.assertEqual(stale['status'],409)
            latest=await self.call(session,'reform_get',resource)
            scope=await self.call(session,'reform_get',dict(resource,view='scope'))
            self.assertEqual(latest['revision'],updated['revision'])
            self.assertEqual(scope['scope']['keep'],'Web confirmed constraints')
            self.assertEqual(scope['scope']['lead'],args['lead'])
            self.assertEqual(scope['scope']['wave'],args['wave'])
            self.assertEqual(scope['scope']['revisions'][0]['contract']['keep'],args['keep'])
            archive=await self.call(session,'reform_archive',dict(resource,expected_revision=latest['revision'],request_id='archive-draft'))
            self.assertTrue(archive['archived'])

    async def test_web_create_response_loss_replay_survives_knowledge_change(self):
        async with self.session() as session:
            _,args=await self.create(session)
        body=dict(args,request_id='web-response-lost-create')
        first=self.web('/api/projects/EXT/reforms',body)
        changed=dict(self.atlas,built='updated-after-response-loss')
        with patch.object(self.P.kb,'atlas',return_value=changed):
            recovered=self.web('/api/projects/EXT/reforms',body)
        self.assertEqual(recovered['id'],first['id'])
        self.assertEqual(len(reform.plans(self.P.data_dir,'EXT')),2)

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

    @unittest.skipUnless(os.name=='posix','real supervised recovery requires POSIX')
    async def test_sdk_recovers_web_origin_supervised_run_without_restarting_it(self):
        from tmh.platform.agents import Runner
        from tmh.platform.store import now
        t=self.fixture.ticket
        run=self.P.store.create_run(t['project_id'],t['id'],'fixture','analyze','web-fixture','original recovery contract')
        rid=run['id']
        self.P.runner._control(rid)
        self.P.store.update_run(rid,status='running',started=now())
        process,folder=self.P.runner.run_command(rid,[sys.executable,'-c',"print('retained supervised output')"],self.fixture.repo)
        self.assertEqual(process.returncode,0)
        raw=(folder/'output.bin').read_bytes()
        args={'project':'EXT','run_id':rid,'request_id':'sdk-web-run-recover'}
        async with self.session('--allow-execution') as session:
            denied=await self.call(session,'run_recover',dict(args,request_id='recover-live-owner'),True)
            self.assertEqual(denied['status'],409)
        self.assertEqual(self.P.store.run(rid)['status'],'running')
        self.P.runner._release(rid)
        self.P.runner=Runner(self.P.store,self.P.data_dir)
        async with self.session('--allow-execution') as session:
            recovered=await self.call(session,'run_recover',args)
            self.assertEqual(recovered['status'],'failed')
            self.assertEqual(recovered['exit_code'],125)
            self.assertFalse(self.P.store.one('SELECT * FROM agent_run_sources WHERE run_id=?',(rid,)))
        async with self.session('--allow-execution') as session:
            self.assertEqual(await self.call(session,'run_recover',args),recovered)
            receipt=await self.call(session,'request_get',{'request_id':args['request_id']})
            self.assertEqual(receipt['state'],'complete')
        self.assertEqual((folder/'output.bin').read_bytes(),raw)
        self.assertTrue(json.loads((self.P.data_dir/'runs'/str(rid)/'lifecycle.json').read_text())['finished'])
        self.assertEqual(len(self.P.store.runs(ticket_id=t['id'])),1)
        self.assertEqual(self.submitted,[])
