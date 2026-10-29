"""Real Registry/SQLite, synthetic people and tasks; no model or business signoff."""
import concurrent.futures
import copy
from datetime import timedelta, datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import pilots as PI, login
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tmh.platform.tenancy import Registry
from tmh.platform.tenant_runtime import TenantContext
from tests.sqlite_snapshot import dump_store


class PilotFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tmh-pilot-')
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        login._save_users(self.data, {n: {'pw': login.hash_password('synthetic-password')} for n in ('owner', 'alice', 'bob', 'viewer')})
        self.reg = Registry(self.data, bootstrap_owner='owner')
        self.addCleanup(self.reg.close)
        self.st = Store(self.data / 'platform.db')
        self.addCleanup(self.st.db.close)
        root = self.data / 'repo'; root.mkdir()
        self.p = self.st.add_project('APP', '合成组织试点', str(root))
        self.other = self.st.add_project('OTHER', '其他项目', str(root))
        self.seq = 0
        self.change('project_grant', user='alice', project_id=self.p['id'], role='manager')
        self.change('project_grant', user='bob', project_id=self.p['id'], role='contributor')
        self.change('project_grant', user='viewer', project_id=self.p['id'], role='viewer')
        self.ctx = TenantContext(self.reg, 'default')
        self.P = SimpleNamespace(store=self.st, data_dir=self.data, tenant_context=self.ctx)
        self.ctx.platform = self.P
        self.tickets = [self.st.create_ticket(self.p['id'], '合成任务 '+str(n), 'owner', body='完整原文\r\n' + '来源不可丢失 ' * 100) for n in range(3)]

    def rid(self):
        self.seq += 1
        return 'pilot-' + str(self.seq)

    def change(self, action, **fields):
        return self.reg.dispatch('owner', dict(action=action, tenant='default', revision=self.reg.context('owner')['revision'], request_id=self.rid(), **fields))

    def spec(self):
        day = PI.today()
        fmt = lambda n: (day + timedelta(days=n)).isoformat()
        return dict(title='合成试点', goal='不把劳动转嫁给测试与运维\r\n完整原文', application_reference='declared-fixture-version',
                    baseline_reference='仅合成基线', comparison='before_after', inclusion_rule='事前确定三条合成任务，保留全部结局',
                    participants=[{'user':'alice','duties':['requirements','development']},{'user':'bob','duties':['testing','delivery','operations']}],
                    periods=[dict(id='base',name='对照',kind='baseline',start_on=fmt(-7),end_on=fmt(-1)),dict(id='t1',name='第一周期',kind='trial',start_on=fmt(1),end_on=fmt(2)),dict(id='t2',name='第二周期',kind='trial',start_on=fmt(4),end_on=fmt(5))],
                    tasks=[dict(ticket=t['key'],period=('base','t1','t2')[n],complexity='保留复杂度声明 '+str(n)) for n,t in enumerate(self.tickets)],
                    targets={key:dict(metric='合成指标 '+key,direction='at_most',value='5.25',unit='分钟') for key in ('quality','improvement','cost_shift')},
                    followup_on=fmt(20),exit_rule='保留退出原因',missing_rule='未知不按0',model_budget_cny='1.00')

    def body(self, view, action, actor='alice', **kw):
        return dict(action=action, expected_actor=actor, request_id=self.rid(), version=view['version'], revision=view['revision'], protocol_hash=view['protocol_hash'], **kw)

    def read(self, pid, actor='alice', **kw):
        return PI.read(self.P,'APP',pid,actor,**kw)

    def create(self, spec=None):
        v=dict(version=0,revision=0,protocol_hash='')
        r=PI.act(self.P,'APP',self.body(v,'create',protocol=self.spec() if spec is None else spec),'alice')
        return self.read(r['id'])

    def act(self,v,action,actor='alice',**kw):
        PI.act(self.P,'APP',self.body(v,action,actor,**kw),actor,v['id'])
        return self.read(v['id'])

    def active(self):
        v=self.create()
        for user in ('alice','bob'):
            v=self.act(v,'confirm',user)
        v=self.act(v,'freeze')
        return self.act(v,'start')

    def labor(self, **changes):
        return dict(ticket=self.tickets[1]['key'],duty='development',activity='implementation',
                    started_at=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat(),minutes=30,note='完整实际劳动说明\r\n第二行',
                    evidence_refs=['fixture://完整引用'],zero_reason='',outside_reason='明确阶段外合成记录',supersedes=None,**changes)

    def denied(self,code,fn):
        before=dump_store(self.st)
        with self.assertRaises(ApiError) as cm:
            fn()
        self.assertEqual(cm.exception.code,code,str(cm.exception))
        self.assertEqual(before,dump_store(self.st))


class PilotsTest(PilotFixture, unittest.TestCase):
    def test_missing_complexity_draft_remains_readable_and_incomplete(self):
        spec=self.spec()
        del spec['tasks'][0]['complexity']
        v=self.create(spec)
        self.assertEqual(v['state'],'draft')
        self.assertEqual(v['protocol']['tasks'][0]['complexity'],'')
        self.assertTrue(any('复杂度' in x for x in v['missing']))
        self.denied(409,lambda:self.act(v,'freeze'))

    def test_legacy_missing_complexity_read_preserves_protocol_hash_and_rows(self):
        v=self.create()
        spec=copy.deepcopy(v['protocol']);del spec['tasks'][0]['complexity']
        ph=PI.digest(dict(schema=PI.PROTOCOL,protocol=spec,sources=v['sources']))
        self.st.db.execute('UPDATE project_pilot_revisions SET protocol=?,protocol_hash=? WHERE pilot_id=?',
                           (PI.encoded(spec),ph,v['id']))
        self.st.db.commit()
        before=dump_store(self.st)
        read=self.read(v['id'])
        self.assertNotIn('complexity',read['protocol']['tasks'][0])
        self.assertEqual(read['protocol_hash'],ph)
        self.assertTrue(any('复杂度' in x for x in read['missing']))
        self.assertEqual(before,dump_store(self.st))

    def test_reacceptance_does_not_erase_first_acceptance_rework(self):
        v=self.create();tid=self.tickets[0]['id']
        for kind,ts in [('accept','2026-10-02 10:00:00'),('reject','2026-10-03 10:00:00'),('accept','2026-10-05 10:00:00')]:
            eid=self.st.event(tid,'owner',kind,'synthetic historical event')
            self.st.db.execute('UPDATE events SET ts=? WHERE id=?',(ts,eid))
        self.st.db.commit()
        with patch.object(PI,'stamp',return_value='2026-10-25T10:00:00+00:00'):
            report=self.read(v['id'])['report']
        acceptance=report['tasks'][0]['acceptance']
        self.assertEqual(acceptance['recorded_at'],'2026-10-02 10:00:00')
        self.assertEqual(acceptance['latest_recorded_at'],'2026-10-05 10:00:00')
        self.assertTrue(acceptance['reopened'])
        self.assertEqual(acceptance['status'],'matured')
        with patch.object(PI.metrics.time,'strftime',return_value='2026-10-25 10:00:00'):
            original=PI.metrics.compute(self.st,self.p,[])['pilot']['reopen']
        self.assertEqual(original['matured'],1)
        self.assertEqual(original['reopened'],1)

    def test_frozen_ticket_id_does_not_rebind_reused_key(self):
        v=self.create();old=self.tickets[-1]
        self.st.db.execute('UPDATE tickets SET project_id=? WHERE id=?',(self.other['id'],old['id']))
        self.st.db.commit()
        replacement=self.st.create_ticket(self.p['id'],'synthetic replacement','owner')
        self.assertEqual(replacement['key'],old['key'])
        self.st.event(replacement['id'],'owner','accept','replacement only')
        read=self.read(v['id']);report=read['report']['tasks'][-1]
        self.assertFalse(read['source_current'])
        self.assertEqual(report['frozen_source']['ticket']['id'],old['id'])
        self.assertFalse(report['current_available'])
        self.assertIsNone(report['current_ticket'])
        self.assertEqual(report['events'],[])
        self.assertEqual(report['runs'],[])
        self.assertEqual(report['acceptance']['status'],'unknown')

    def test_empty_draft_is_usable_and_no_automatic_start_or_signoff(self):
        v=self.create({})
        self.assertEqual(v['state'],'draft')
        self.assertGreater(len(v['missing']),10)
        self.assertIsNone(v['protocol']['model_budget_cny'])
        self.assertEqual(v['report']['task_count'],0)
        self.assertEqual(self.st.q('SELECT * FROM runs'),[])
        self.assertEqual(self.st.q("SELECT * FROM events WHERE kind IN ('accept','close')"),[])
        self.denied(409,lambda: self.act(v,'freeze'))

    def test_full_sources_and_revisions_are_immutable_and_confirmation_is_per_person(self):
        v=self.create()
        original=copy.deepcopy(v['sources'])
        self.assertEqual(original['tickets'][0]['ticket']['body'],self.tickets[0]['body'])
        v=self.act(v,'confirm')
        self.assertTrue(v['confirmations'][0]['confirmed'])
        self.assertFalse(v['confirmations'][1]['confirmed'])
        self.denied(409,lambda: self.act(v,'freeze'))
        v=self.act(v,'confirm','bob')
        v=self.act(v,'freeze')
        self.assertEqual(v['state'],'frozen')
        spec=copy.deepcopy(v['protocol']);spec['goal']+=' 新目标'
        newer=self.act(v,'revise',protocol=spec)
        self.assertEqual(newer['state'],'draft')
        self.assertTrue(all(not x['confirmed'] for x in newer['confirmations']))
        old=self.read(v['id'],revision=1)
        self.assertEqual(old['sources'],original)
        self.assertEqual(old['protocol'],v['protocol'])
        self.assertEqual(old['state'],'frozen')

    def test_authorship_payload_agent_and_legacy_are_not_personal_authority(self):
        v=self.create()
        for field in ('actor','tenant','by','user'):
            body=self.body(v,'confirm');body[field]='bob'
            self.denied(400,lambda: PI.act(self.P,'APP',body,'alice',v['id']))
        self.denied(409,lambda: PI.act(self.P,'APP',self.body(v,'confirm','bob'),'alice',v['id']))
        self.denied(403,lambda: self.act(v,'confirm','viewer'))
        self.denied(403,lambda: self.act(v,'confirm','agent:spoof'))
        legacy=SimpleNamespace(store=self.st,data_dir=self.data)
        self.denied(403,lambda: PI.read(legacy,'APP',v['id'],'alice'))

    def test_revoke_regrant_epoch_and_unrelated_grant_confirmation_semantics(self):
        v=self.act(self.create(),'confirm','bob')
        self.change('project_grant',user='bob',project_id=self.other['id'],role='viewer')
        self.assertTrue(self.read(v['id'])['confirmations'][1]['confirmed'])
        self.change('project_revoke',user='bob',project_id=self.p['id'])
        self.change('project_grant',user='bob',project_id=self.p['id'],role='contributor')
        v=self.read(v['id']);self.assertTrue(v['confirmations'][1]['stale'])
        v=self.act(v,'confirm','bob')
        self.change('password_reset',user='bob',password='new-synthetic-password')
        self.assertTrue(self.read(v['id'])['confirmations'][1]['stale'])

    def test_exact_idempotency_conflict_and_reauthorization_before_replay(self):
        v=self.create();body=self.body(v,'confirm')
        first=PI.act(self.P,'APP',body,'alice',v['id'])
        before=dump_store(self.st)
        self.assertTrue(PI.act(self.P,'APP',body,'alice',v['id'])['receipt']['replayed'])
        self.assertEqual(dump_store(self.st),before)
        changed=dict(body,action='freeze')
        self.denied(409,lambda: PI.act(self.P,'APP',changed,'alice',v['id']))
        self.change('project_revoke',user='alice',project_id=self.p['id'])
        self.denied(403,lambda: PI.act(self.P,'APP',body,'alice',v['id']))
        self.denied(403,lambda: self.read(v['id']))

    def test_requirement_change_prevents_confirm_and_freeze_and_keeps_old_source(self):
        v=self.create();old=v['sources']
        v=self.act(v,'confirm');v=self.act(v,'confirm','bob')
        self.st.event(self.tickets[0]['id'],'owner','comment','新增完整需求')
        self.assertFalse(self.read(v['id'])['source_current'])
        self.denied(409,lambda: self.act(v,'freeze'))
        self.denied(409,lambda: self.act(v,'confirm'))
        self.assertEqual(self.read(v['id'])['sources'],old)

    def test_start_rechecks_authority_and_source_and_freeze_is_prospective(self):
        v=self.create();v=self.act(v,'confirm');v=self.act(v,'confirm','bob');v=self.act(v,'freeze')
        self.change('project_revoke',user='bob',project_id=self.p['id'])
        self.change('project_grant',user='bob',project_id=self.p['id'],role='contributor')
        self.denied(409,lambda: self.act(v,'start'))
        spec=self.spec();spec['periods'][1]['start_on']=PI.today().isoformat()
        w=self.create(spec);w=self.act(w,'confirm');w=self.act(w,'confirm','bob')
        self.denied(409,lambda: self.act(w,'freeze'))

    def test_only_manager_changes_lifecycle_and_sources_are_scoped(self):
        v=self.create()
        for action in ('freeze','start','end','revise','exit'):
            self.denied(403,lambda action=action: self.act(v,action,'bob'))
        self.denied(403,lambda: PI.read(self.P,'OTHER',v['id'],'alice'))
        self.denied(404,lambda: PI.read(self.P,'OTHER',v['id'],'owner'))
        foreign=self.st.create_ticket(self.other['id'],'其他任务','owner')
        spec=self.spec();spec['tasks'][0]['ticket']=foreign['key']
        self.denied(400,lambda: self.create(spec))

    def test_labor_is_own_append_only_and_overlap_including_other_pilots_rejected(self):
        v=self.active();entry=self.labor();v=self.act(v,'labor',labor=entry)
        original=v['report']['labor'][0]
        self.assertEqual(v['report']['recorded_minutes'],30)
        self.assertEqual(original['payload']['note'],entry['note'])
        self.denied(409,lambda: self.act(v,'labor',labor=entry))
        bad=dict(entry,duty='testing',supersedes=original['id'])
        self.denied(409,lambda: self.act(v,'labor','bob',labor=bad))
        corrected=dict(entry,minutes=20,supersedes=original['id'])
        v=self.act(v,'labor',labor=corrected)
        self.assertEqual(v['report']['recorded_minutes'],20)
        self.assertEqual(len([e for e in v['events'] if e['kind']=='labor']),2)
        self.denied(409,lambda: self.act(v,'labor',labor=corrected))
        other=self.active()
        self.denied(409,lambda: self.act(other,'labor',labor=entry))

    def test_zero_unknown_future_timezone_and_outside_period_are_not_conflated(self):
        v=self.active()
        for change in (dict(minutes=True),dict(minutes=-1),dict(started_at='2026-10-25T09:00:00'),dict(minutes=0),dict(outside_reason=''),dict(started_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())):
            self.denied(400,lambda change=change: self.act(v,'labor',labor=dict(self.labor(),**change)))
        v=self.act(v,'labor',labor=dict(self.labor(),minutes=0,zero_reason='本职责未投入，有明确确认'))
        coverage=v['report']['tasks'][1]['coverage']
        self.assertEqual(next(x for x in coverage if x['user']=='alice' and x['duty']=='development')['minutes'],0)
        self.assertIsNone(next(x for x in coverage if x['user']=='bob')['minutes'])
        self.assertTrue(v['report']['labor'][0]['payload']['outside_period'])
        self.assertEqual(v['report']['missing_labor_cells'],15)
        self.assertIsNone(next(x for x in coverage if x['user']=='alice' and x['duty']=='development')['in_period_minutes'])

    def test_report_preserves_failed_exited_unfinished_and_immature_denominator(self):
        v=self.active()
        tid=self.tickets[0]['id']
        self.st.event(tid,'owner','accept','仅合成历史事件，不是真实业务验收')
        self.st.db.execute("INSERT INTO runs(project_id,ticket_id,agent,mode,status,created) VALUES(?,?,?,?,?,?)",(self.p['id'],tid,'synthetic','analyze','failed',PI.stamp()));self.st.db.commit()
        v=self.read(v['id']);v=self.act(v,'exit',ticket=self.tickets[1]['key'],reason='合成退出原因，仍保留原任务')
        v=self.act(v,'end')
        report=v['report']
        self.assertEqual(report['task_count'],3)
        self.assertEqual(len(report['tasks'][1]['exits']),1)
        self.assertEqual(report['tasks'][0]['runs'][0]['status'],'failed')
        self.assertEqual(report['tasks'][0]['acceptance']['status'],'pending')
        self.assertEqual(report['tasks'][2]['acceptance']['status'],'not_accepted')
        self.assertIsNone(report['improvement_percent'])
        self.assertIsNone(report['actual_model_cost']['amount'])
        self.assertEqual(report['missing_labor_cells'],15)
        self.assertTrue(all(t['waiting']['seconds'] is None for t in report['tasks']))
        self.assertIn(self.tickets[0]['body'],json.loads(PI.markdown(v).split('```json\n')[1].rsplit('\n```',1)[0])['sources']['tickets'][0]['ticket']['body'])

    def test_waiting_preserves_open_and_received_block_is_not_wait(self):
        observed=datetime(2026,10,25,12,tzinfo=timezone.utc)
        events=[dict(handoff_id=1,ts='2026-10-25T09:00:00+00:00',status='waiting'),dict(handoff_id=1,ts='2026-10-25T10:00:00+00:00',status='received'),dict(handoff_id=1,ts='2026-10-25T10:30:00+00:00',status='blocked')]
        self.assertEqual(PI._waiting(events,observed)['seconds'],3600)
        events.pop();events[1]['status']='blocked'
        self.assertEqual(PI._waiting(events,observed),dict(seconds=10800,status='observed_open'))
        self.assertIsNone(PI._waiting([dict(handoff_id=1,ts='broken',status='waiting')],observed)['seconds'])

    def test_cross_connection_cas_and_identical_request_have_one_event(self):
        v=self.create();second=Store(self.st.path);self.addCleanup(second.db.close)
        P2=SimpleNamespace(store=second,data_dir=self.data,tenant_context=self.ctx)
        body=self.body(v,'confirm');barrier=threading.Barrier(2)
        def call(P,b):
            barrier.wait()
            try:return PI.act(P,'APP',b,'alice',v['id'])
            except ApiError as e:return e.code
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda x:call(*x),[(self.P,body),(P2,body)]))
        self.assertTrue(all(isinstance(x,dict) for x in results),results)
        self.assertEqual(len([x for x in self.read(v['id'])['events'] if x['kind']=='confirm']),1)
        v=self.read(v['id']);barrier=threading.Barrier(2)
        bodies=[self.body(v,'confirm') for _ in range(2)]
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda x:call(*x),[(self.P,bodies[0]),(P2,bodies[1])]))
        self.assertEqual(sum(x==409 for x in results),1,results)

    def test_atomic_event_failure_rolls_back_head_revision_and_payload(self):
        v=self.create();before=dump_store(self.st);db=self.st.db
        class Fail:
            def __getattr__(self,name):return getattr(db,name)
            def execute(self,sql,args=()):
                if 'INSERT INTO project_pilot_events' in sql:raise OSError('synthetic event insertion failure')
                return db.execute(sql,args)
        self.st.db=Fail()
        try:
            with self.assertRaises(OSError):self.act(v,'revise',protocol=self.spec())
        finally:self.st.db=db
        self.assertEqual(dump_store(self.st),before)

    def test_validation_rejects_invalid_types_duplicate_tasks_and_no_silent_trim(self):
        for change in (dict(model_budget_cny=1),dict(model_budget_cny='NaN'),dict(tasks=[self.spec()['tasks'][0]]*2),dict(participants=[dict(user='alice',duties=[{}])])):
            self.denied(400,lambda change=change:self.create(dict(self.spec(),**change)))
        spec=self.spec();spec['goal']='  原文\r\n完整保留\u2028尾部  '
        self.assertEqual(self.create(spec)['protocol']['goal'],spec['goal'])

    def test_schema_atomic_partial_refusal_and_read_is_no_business_mutation(self):
        v=self.create();before=dump_store(self.st)
        self.read(v['id']);PI.listing(self.P,'APP','alice')
        self.assertEqual(dump_store(self.st),before)
        self.st.db.execute('DROP TABLE project_pilot_events');self.st.db.commit()
        with self.assertRaises(ApiError):PI.schema(self.st)
        self.assertIsNone(self.st.one("SELECT name FROM sqlite_master WHERE name='project_pilot_events'"))

    def test_damaged_original_hash_cannot_confirm_or_replay(self):
        v=self.create();body=self.body(v,'confirm')
        PI.act(self.P,'APP',body,'alice',v['id'])
        self.st.db.execute("UPDATE project_pilot_revisions SET protocol=? WHERE pilot_id=?",(PI.encoded(dict(v['protocol'],goal='tampered')),v['id']));self.st.db.commit()
        self.denied(409,lambda: PI.act(self.P,'APP',body,'alice',v['id']))
        with self.assertRaises(ApiError):self.read(v['id'])

    def test_moved_task_keeps_frozen_denominator_without_other_project_details(self):
        v=self.active();tid=self.tickets[0]['id']
        self.st.db.execute("UPDATE tickets SET project_id=?,num=99,body='other project private content' WHERE id=?",(self.other['id'],tid));self.st.db.commit()
        report=self.read(v['id'])['report']
        self.assertEqual(report['task_count'],3)
        t=report['tasks'][0]
        self.assertFalse(t['current_available'])
        self.assertIsNone(t['current_ticket'])
        self.assertEqual(t['frozen_source']['ticket']['body'],self.tickets[0]['body'])
        self.assertNotIn('other project private content',PI.encoded(report))

    def test_end_retains_history_and_retroactive_correction_is_explicit(self):
        v=self.active();v=self.act(v,'end')
        entry=self.labor();v=self.act(v,'labor',labor=entry)
        self.assertTrue(v['report']['labor'][0]['payload']['retrospective'])
        self.denied(409,lambda:self.act(v,'start'))

    def test_before_after_or_parallel_dates_cannot_fake_comparable_periods(self):
        for comparison in ('before_after','parallel'):
            spec=self.spec();spec['comparison']=comparison
            if comparison=='before_after':spec['periods'][0]['end_on']=spec['periods'][1]['end_on']
            v=self.create(spec);v=self.act(v,'confirm');v=self.act(v,'confirm','bob')
            self.denied(409,lambda:self.act(v,'freeze'))

    def test_new_draft_does_not_strand_original_active_trial(self):
        v=self.active();original=v['protocol_hash']
        newer=self.act(v,'revise',protocol=self.spec())
        old=self.read(v['id'],revision=1)
        receipt=PI.act(self.P,'APP',self.body(old,'labor',labor=self.labor()),'alice',v['id'])
        self.assertEqual(receipt['revision'],1)
        self.assertEqual(receipt['protocol_hash'],original)
        old=self.read(v['id'],revision=1)
        PI.act(self.P,'APP',self.body(old,'end'),'alice',v['id'])
        self.assertEqual(self.read(v['id'],revision=1)['state'],'ended')
        self.assertEqual(self.read(v['id'])['state'],'draft')
        self.assertEqual(self.read(v['id'])['report']['recorded_minutes'],0)

    def test_partial_fill_never_claims_completeness_and_export_keeps_original_cutoff(self):
        spec=self.spec();spec['periods'][0]['end_on']=PI.today().isoformat()
        v=self.create(spec);v=self.act(v,'confirm');v=self.act(v,'confirm','bob');v=self.act(v,'freeze');v=self.act(v,'start')
        entry=dict(self.labor(),ticket=self.tickets[0]['key'])
        v=self.act(v,'labor',labor=entry)
        original=json.loads(json.dumps(v,ensure_ascii=False))
        self.assertEqual(v['report']['tasks'][0]['coverage'][1]['in_period_minutes'],30)
        self.assertEqual(v['report']['completeness']['status'],'unknown')
        self.assertIsNone(v['report']['improvement_percent'])
        r=v['report'];self.assertEqual(r['snapshot_sha256'],PI.digest({k:x for k,x in r.items() if k!='snapshot_sha256'}))
        oldid=r['labor'][0]['id'];v=self.act(v,'labor',labor=dict(entry,supersedes=oldid,minutes=20))
        self.assertEqual(original['report']['recorded_minutes'],30)
        self.assertEqual(v['report']['recorded_minutes'],20)
        self.assertNotEqual(original['report']['event_range'],v['report']['event_range'])
        self.assertNotEqual(original['report']['snapshot_sha256'],v['report']['snapshot_sha256'])

    def test_cross_period_work_remains_whole_and_unallocated_until_person_splits(self):
        spec=self.spec();yesterday=(PI.today()-timedelta(days=1)).isoformat()
        spec['periods'][0]['start_on']=yesterday;spec['periods'][0]['end_on']=yesterday
        v=self.create(spec);v=self.act(v,'confirm');v=self.act(v,'confirm','bob');v=self.act(v,'freeze');v=self.act(v,'start')
        entry=dict(self.labor(),ticket=self.tickets[0]['key'],started_at=yesterday+'T23:50:00+08:00')
        v=self.act(v,'labor',labor=entry)
        r=v['report'];self.assertEqual(r['recorded_minutes'],30)
        self.assertEqual(r['outside_period_minutes'],30)
        self.assertEqual(r['missing_labor_cells'],15)
        self.assertEqual(r['labor'][0]['payload']['allocation'],'unallocated_outside_period')

    def test_correction_cannot_move_original_cost_to_other_pilot_or_revision(self):
        v=self.active();entry=self.labor();v=self.act(v,'labor',labor=entry);oldid=v['report']['labor'][0]['id']
        other=self.active()
        self.denied(409,lambda:self.act(other,'labor',labor=dict(entry,supersedes=oldid)))
        newer=self.act(v,'revise',protocol=self.spec());newer=self.act(newer,'confirm');newer=self.act(newer,'confirm','bob');newer=self.act(newer,'freeze');newer=self.act(newer,'start')
        self.denied(409,lambda:self.act(newer,'labor',labor=dict(entry,supersedes=oldid)))
        self.assertEqual(self.read(v['id'],revision=1)['report']['recorded_minutes'],30)

    def test_competing_corrections_keep_one_effect_and_original_overlap_protection(self):
        v=self.active();entry=self.labor();v=self.act(v,'labor',labor=entry);oldid=v['report']['labor'][0]['id']
        st2=Store(self.st.path);self.addCleanup(st2.db.close);P2=SimpleNamespace(store=st2,data_dir=self.data,tenant_context=self.ctx)
        bodies=[self.body(v,'labor',labor=dict(entry,supersedes=oldid,minutes=x)) for x in (20,25)];barrier=threading.Barrier(2)
        def call(P,b):
            barrier.wait()
            try:return PI.act(P,'APP',b,'alice',v['id'])
            except ApiError as e:return e.code
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda x:call(*x),[(self.P,bodies[0]),(P2,bodies[1])]))
        self.assertEqual(sum(x==409 for x in results),1)
        current=self.read(v['id']);self.assertEqual(len(current['report']['labor']),1)
        self.assertEqual(len([e for e in current['events'] if e['kind']=='labor']),2)
        self.denied(409,lambda:self.act(current,'labor',labor=entry))

    def test_protected_experiment_run_cannot_leak_through_new_report(self):
        v=self.active()
        self.st.db.execute("INSERT INTO runs(project_id,ticket_id,agent,mode,status,created,batch,output) VALUES(?,?,?,?,?,?,?,?)",(self.p['id'],self.tickets[0]['id'],'synthetic','review','failed',PI.stamp(),'experiment:orphan-private','private-synthetic-sentinel'))
        self.st.db.commit()
        self.denied(409,lambda:self.read(v['id']))


if __name__=='__main__':
    unittest.main()
