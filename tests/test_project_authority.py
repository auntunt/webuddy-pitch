import json
import os
from pathlib import Path
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import patch

from tmh.platform.project_authority import capture
from tmh.platform.project_mcp import BoundJob
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tmh.platform.tenant_runtime import TenantContext
from tmh.platform.agents import Runner, member_codex_binding, member_route_binding, pick_model
from tests import test_tenant_gateway as gateway_fixture


class ProjectAuthorityTest(unittest.TestCase):
    def setUp(self):
        gateway=gateway_fixture.TenantGatewayTest('runTest')
        gateway.setUp();self.addCleanup(gateway.doCleanups);self.gateway=gateway
        data=Path(gateway.reg.one('SELECT path FROM tenants WHERE id=?',(gateway.a,))['path']).resolve()
        store=Store(data/'platform.db');self.addCleanup(store.db.close)
        project=store.project('SAME');root=Path(project['root']).resolve();(root/'.git').mkdir()
        store.x('UPDATE projects SET root=? WHERE id=?',(str(root),project['id']))
        self.project=store.project(project['id'])
        context=TenantContext(gateway.reg,gateway.a)
        self.P=SimpleNamespace(store=store,data_dir=data,tenant_context=context);context.platform=self.P
        config=data/'project-execution.json';config.write_text(json.dumps({'schema':1,'image':'sha256:'+'a'*64,'projects':['SAME']}));config.chmod(0o600)
        self.workspace=data/'synthetic-job';self.workspace.mkdir()

    def test_unrelated_project_changes_do_not_invalidate_but_revoke_and_regrant_do(self):
        authority=capture(self.P,'alice',self.project)
        job=BoundJob('alice','SAME',self.workspace,'sha256:'+'a'*64)
        self.assertTrue(authority.current(job))
        self.gateway.change('project_grant',tenant=self.gateway.a,user='alice',project_id=2,role='viewer')
        self.gateway.change('project_revoke',tenant=self.gateway.a,user='alice',project_id=2)
        self.gateway.change('project_grant',tenant=self.gateway.a,user='alice',project_id=1,role='contributor')
        self.assertTrue(authority.current(job))
        self.gateway.change('project_revoke',tenant=self.gateway.a,user='alice',project_id=1)
        self.assertFalse(authority.current(job))
        self.gateway.change('project_grant',tenant=self.gateway.a,user='alice',project_id=1,role='contributor')
        self.assertFalse(authority.current(job))
        self.assertTrue(capture(self.P,'alice',self.project).current(job))

    def test_viewer_and_cross_project_job_cannot_execute(self):
        authority=capture(self.P,'alice',self.project)
        self.assertFalse(authority.current(BoundJob('alice','PRIVATE',self.workspace,'sha256:'+'a'*64)))
        self.assertFalse(authority.current(BoundJob('bob','SAME',self.workspace,'sha256:'+'a'*64)))
        self.gateway.change('project_grant',tenant=self.gateway.a,user='alice',project_id=1,role='viewer')
        with self.assertRaises(ApiError):capture(self.P,'alice',self.project)

    def test_runner_uses_personal_grant_and_preserves_unpublished_marker(self):
        ticket=self.P.store.ticket('SAME-1')
        self.P.store.x('UPDATE tickets SET links=? WHERE id=?',(json.dumps({'hold':True}),ticket['id']))
        ticket=self.P.store.ticket(ticket['id'])
        runner=Runner(self.P.store,self.P.data_dir);runner.tenant_context=self.P.tenant_context;self.P.runner=runner
        finished=threading.Event();seen=[]
        def execute(runner,rid,project,ticket,prompt,authority,image,binding):
            seen.append((rid,authority.principal,project['key'],authority.current(
                BoundJob('alice','SAME',self.workspace,image))))
            runner.store.update_run(rid,status='done',result='synthetic proposal')
            finished.set()
        with patch('tmh.platform.agents.build_prompt',return_value='synthetic prompt'), patch('tmh.platform.project_snapshot.resolve',return_value='b'*40), patch('tmh.platform.agents.member_codex_binding',return_value=('', 'd'*64)), patch('tmh.platform.project_member.execute',side_effect=execute):
            run=runner.start(self.project,ticket,'codex','fix','alice')
            self.assertTrue(finished.wait(4))
        stored=runner.store.run(run['id'])
        self.assertEqual(seen,[(run['id'],'alice','SAME',True)])
        self.assertTrue(stored['batch'].startswith('member:'))
        marker=json.loads((self.P.data_dir/'runs'/str(run['id'])/'member-execution.json').read_text())
        self.assertEqual(marker['batch'],stored['batch'])
        self.assertEqual(marker['provider_binding'], 'd'*64)
        self.assertEqual(len(marker['route_binding']), 64)
        self.assertFalse(runner.retry_state(run['id'])['can_retry'])

    def test_nonmember_cannot_enter_runner_path(self):
        ticket=self.P.store.ticket('SAME-1')
        self.P.store.x('UPDATE tickets SET links=? WHERE id=?',(json.dumps({'hold':True}),ticket['id']))
        runner=Runner(self.P.store,self.P.data_dir);runner.tenant_context=self.P.tenant_context;self.P.runner=runner
        with self.assertRaises(ApiError):
            runner.start(self.project,self.P.store.ticket(ticket['id']),'codex','fix','outsider')

    def test_authenticated_http_member_fix_reaches_runner_and_other_modes_remain_closed(self):
        base='/t/'+self.gateway.a
        token=self.gateway.token('alice',self.gateway.a)
        status,_,meta=self.gateway.request('GET',base+'/api/meta','alice')
        self.assertEqual(status,200,meta)
        self.assertEqual(meta['member_execution']['projects'],['SAME'])
        path=base+'/api/tickets/SAME-1/runs'
        def post(mode):
            return self.gateway.request('POST',path,'alice',{'agent':'codex','mode':mode},token=token,headers={'X-TMH':'1'})
        status,_,reply=post('fix')
        self.assertNotEqual(status,403,reply)
        self.assertIn('认领',str(reply))
        self.assertEqual(post('analyze')[0],403)
        self.gateway.change('project_revoke',tenant=self.gateway.a,user='alice',project_id=1)
        self.assertIn(post('fix')[0],(403,409))  # stale signed tenant context is rejected too
        token=self.gateway.token('alice',self.gateway.a)
        self.assertEqual(post('fix')[0],403)

    def test_codex_profile_and_selected_or_default_model_are_preserved(self):
        config={'engine':'codex','profile':'webuddy-cloudwave','args':['--ephemeral','--color','never'],
                'defaults':{'fix':'route-model'}}
        with patch('tmh.platform.project_client.provider_binding',return_value=('','', 'd'*64)) as provider:
            self.assertEqual(member_codex_binding(config,pick_model(config,'fix',None)),('webuddy-cloudwave','d'*64))
            self.assertEqual(provider.call_args.args[1:],('webuddy-cloudwave','route-model'))
            member_codex_binding(config,pick_model(config,'fix',''))
            self.assertEqual(provider.call_args.args[1:],('webuddy-cloudwave',''))
            member_codex_binding(config,pick_model(config,'fix','chosen-model'))
            self.assertEqual(provider.call_args.args[1:],('webuddy-cloudwave','chosen-model'))
        with self.assertRaisesRegex(ValueError,'不支持'):
            member_codex_binding(dict(config,args=['--unknown']), 'route-model')

    def test_route_configuration_is_bound(self):
        before=member_route_binding(self.P.data_dir,self.project,'codex')
        (self.P.data_dir/'agent-routes.json').write_text(json.dumps({'schema':1,'projects':{'SAME':{'agent':'codex'}}}))
        self.assertNotEqual(before,member_route_binding(self.P.data_dir,self.project,'codex'))

    def test_authenticated_http_runner_records_synthetic_result(self):
        # Start a real local gateway worker with a stubbed source and model job.
        # No real project, provider, Docker container or human is involved.
        site=self.gateway.data/'site';site.mkdir()
        (site/'sitecustomize.py').write_text('''
from tmh.platform import agents, project_snapshot, project_client, project_member
project_snapshot.resolve=lambda *a, **kw: "b"*40
project_client.provider_binding=lambda *a, **kw: ("", "", "d"*64)
agents.build_prompt=lambda *a, **kw: "synthetic prompt"
def execute(runner,rid,project,ticket,prompt,authority,image,binding):
    runner.store.update_run(rid,status="done",result="synthetic proposal")
project_member.execute=execute
''')
        path=str(site)+os.pathsep+os.getcwd()+os.pathsep+os.environ.get('PYTHONPATH','')
        with patch.dict(os.environ,{'PYTHONPATH':path}):
            base='/t/'+self.gateway.a
            token=self.gateway.token('alice',self.gateway.a)
            status,_,meta=self.gateway.request('GET',base+'/api/meta','alice')
            self.assertEqual(status,200,meta)
            status,_,claimed=self.gateway.request('POST',base+'/api/tickets/SAME-1/claim','alice',
                {'on':True},token=token,headers={'X-TMH':'1'})
            self.assertEqual(status,200,claimed)
            status,_,run=self.gateway.request('POST',base+'/api/tickets/SAME-1/runs','alice',
                {'agent':'codex','mode':'fix'},token=token,headers={'X-TMH':'1'})
            self.assertEqual(status,200,run)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                status,_,state=self.gateway.request('GET',base+'/api/runs/'+str(run['id']),'alice',token=token)
                self.assertEqual(status,200,state)
                if state.get('run',state).get('status')=='done':break
                time.sleep(.05)
            self.assertEqual(state.get('run',state)['status'],'done')
            self.assertEqual(state.get('run',state)['result'],'synthetic proposal')
            status,_,_=self.gateway.request('POST',base+'/api/tickets/SAME-1/claim','alice',
                {'on':False},token=token,headers={'X-TMH':'1'})
            self.assertEqual(status,403)


if __name__=='__main__':unittest.main()
