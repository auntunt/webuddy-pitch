"""Original gateway and independent tenant workers; synthetic trial only."""
import copy
from datetime import timedelta, datetime, timezone
import os
from pathlib import Path
import unittest

from tests import test_tenant_gateway as G
from tmh.platform import pilots as PI
from tmh.platform.store import Store


@unittest.skipUnless(os.name=='posix','tenant workers require POSIX sockets')
class PilotsHTTPTest(unittest.TestCase):
    setUp=G.TenantGatewayTest.setUp
    change=G.TenantGatewayTest.change
    request=G.TenantGatewayTest.request
    token=G.TenantGatewayTest.token

    def call(self,path,body=None,user='owner',tenant=None,headers=None):
        tenant=tenant or self.a
        return self.request('POST' if body is not None else 'GET','/t/'+tenant+path,user,body,token=self.token(user,tenant),headers={'X-TMH':'1',**(headers or {})})

    def ok(self,path,body=None,**kw):
        status,_,value=self.call(path,body,**kw)
        self.assertEqual(status,200,value)
        return value

    def create(self, protocol=None):
        return self.ok('/api/projects/SAME/pilots',dict(action='create',protocol=protocol or {},version=0,revision=0,protocol_hash='',request_id='create-pilot',expected_actor='owner'))

    def view(self,r,**kw):
        return self.ok('/api/projects/SAME/pilots/'+r['id'],**kw)

    def action(self,v,action,user='owner',**kw):
        return self.ok('/api/projects/SAME/pilots/'+v['id'],dict(action=action,version=v['version'],revision=v['revision'],protocol_hash=v['protocol_hash'],request_id='http-'+str(v['version'])+'-'+action,expected_actor=user,**kw),user=user)

    def test_real_draft_personal_confirm_freeze_record_report_chain_without_execution(self):
        day=PI.today();fmt=lambda n:(day+timedelta(days=n)).isoformat()
        target=dict(metric='合成约束',direction='at_most',value='1',unit='次数')
        spec=dict(title='合成端到端',goal='完整原文\r\n'+'保留全部内容 '*200,application_reference='declared-only',baseline_reference='synthetic',comparison='before_after',inclusion_rule='现有任务全集',participants=[dict(user='owner',duties=['requirements','development']),dict(user='alice',duties=['testing','delivery','operations'])],periods=[dict(id='base',name='对照',kind='baseline',start_on=fmt(-7),end_on=fmt(-1)),dict(id='one',name='第一周期',kind='trial',start_on=fmt(1),end_on=fmt(2)),dict(id='two',name='第二周期',kind='trial',start_on=fmt(4),end_on=fmt(5))],tasks=[dict(ticket='SAME-1',period='one',complexity='完整复杂度原文')],targets={x:target for x in ('quality','improvement','cost_shift')},followup_on=fmt(20),exit_rule='退出不删',missing_rule='未知不为0',model_budget_cny='1.00')
        receipt=self.create(spec);v=self.view(receipt)
        self.assertEqual(v['protocol']['goal'],spec['goal'])
        self.action(v,'confirm');v=self.view(v)
        self.action(v,'confirm','alice');v=self.view(v)
        self.action(v,'freeze');v=self.view(v);self.assertEqual(v['state'],'frozen')
        self.action(v,'start');v=self.view(v)
        labor=dict(ticket='SAME-1',duty='testing',activity='testing',started_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),minutes=10,note='合成个人劳动原文',evidence_refs=['fixture://原始证据'],zero_reason='',outside_reason='合成阶段外操作，不伪装真实试点',supersedes=None)
        result=self.action(v,'labor','alice',labor=labor)
        v=self.view(v);self.assertEqual(v['report']['recorded_minutes'],10)
        self.assertEqual(v['report']['task_count'],1)
        self.assertEqual(v['report']['missing_labor_cells'],5)
        self.action(v,'end');v=self.view(v);self.assertEqual(v['state'],'ended')
        self.assertIsNone(v['report']['actual_model_cost']['amount'])
        root=Path(self.reg.one('SELECT path FROM tenants WHERE id=?',(self.a,))['path'])
        st=Store(root/'platform.db');self.addCleanup(st.db.close)
        self.assertEqual(st.q('SELECT * FROM runs'),[])
        self.assertEqual(st.q("SELECT * FROM events WHERE kind IN ('accept','close')"),[])
        self.assertEqual(st.ticket('SAME-1')['status'],'new')
        self.assertEqual(len(st.q("SELECT * FROM project_pilot_events WHERE kind='labor'")),1)

    def test_cross_tenant_project_session_agent_and_tool_boundaries(self):
        r=self.create();path='/api/projects/SAME/pilots/'+r['id'];v=self.view(r)
        self.assertEqual(self.call('/api/projects/PRIVATE/pilots/'+r['id'],user='alice')[0],403)
        self.assertEqual(self.call('/api/projects/PRIVATE/pilots/'+r['id'])[0],404)
        self.assertEqual(self.call(path,user='bob',tenant=self.b)[0],404)
        body=dict(action='confirm',version=v['version'],revision=v['revision'],protocol_hash=v['protocol_hash'],request_id='spoof',expected_actor='owner')
        self.assertEqual(self.call(path,body,headers={'X-Webuddy-Agent':'claude'})[0],403)
        self.assertEqual(self.call(path,dict(body,actor='owner'))[0],400)
        self.assertEqual(self.call(path,body,user='alice')[0],409)
        self.assertEqual(self.call('/api/projects/SAME/pilots',dict(action='create',protocol={},version=0,revision=0,protocol_hash='',request_id='member-create',expected_actor='alice'),user='alice')[0],403)
        grant=self.ok('/api/tool-connections',dict(action='create',label='synthetic',project_ids=[1],scope='read',expires_days=1,request_id='tool-read'),user='alice')
        status,_,_=self.request('GET','/t/'+self.a+path,headers={'Authorization':'Bearer '+grant['token'],'X-Webuddy-Agent':'claude'})
        self.assertIn(status,(401,403))

    def test_http_complete_list_and_duplicate_revision_parameters_fail_closed(self):
        r=self.create();v=self.view(r)
        listing=self.ok('/api/projects/SAME/pilots',user='alice')
        self.assertEqual(listing['actor'],'alice')
        self.assertFalse(listing['can_manage'])
        self.assertEqual(len(listing['tickets']),1)
        self.assertEqual(self.call('/api/projects/SAME/pilots?hidden=closed')[0],400)
        path='/api/projects/SAME/pilots/'+r['id']
        for suffix in ('?revision=1&revision=2','?revision=0','?revision=NaN','?unknown=1'):
            self.assertEqual(self.call(path+suffix)[0],400)
        self.assertEqual(self.ok(path+'?revision=1')['protocol_hash'],v['protocol_hash'])


if __name__=='__main__':unittest.main()
