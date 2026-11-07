"""Plan storage faults and concurrent outcomes must not duplicate business work."""
import concurrent.futures
import json
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tmh.platform import reform
from tmh.platform.store import Store


class ReformDurabilityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.store = Store(self.data/'platform.db')
        self.addCleanup(self.store.db.close)
        self.proj = self.store.add_project('RF', 'Fixture', str(self.data))
        self.submitted = []
        self.P = SimpleNamespace(data_dir=self.data, store=self.store,
            flow=SimpleNamespace(BY='flow', submit=lambda p,t: self.submitted.append(t['key'])))
        self.atlas = {'built': 'fixed', 'domains': [{'id':str(n), 'title':str(n), 'tables':0} for n in range(8)]}

    def create(self, **kw):
        return reform.create(self.data, 'RF', self.atlas,
            dict(title='Reform', goal='Full contract', wave=2, **kw), 'owner')

    def close(self, key):
        t = self.store.ticket(key)
        return self.store.update_ticket(t['id'], 'fixture', status='closed')

    def test_concurrent_duplicate_outcomes_release_one_wave(self):
        p = self.create()
        first = reform.release(self.P,self.proj,p['id'],None,'owner')
        tickets = [self.close(k) for k in first]
        # Force the old check-then-release race rather than hoping for timing.
        gate = threading.Barrier(2)
        original_release = reform.release
        def racing_release(*args,**kwargs):
            gate.wait(timeout=5)
            return original_release(*args,**kwargs)
        with patch.object(reform,'release',side_effect=racing_release):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda t: reform.outcome(self.P,self.proj,t,True,'fixture'), tickets*2))
        saved = reform.plan(self.data,'RF',p['id'])
        self.assertEqual(sum(bool(i.get('ticket')) for i in saved['items']),4)
        self.assertEqual(len(set(self.submitted)),4)

    def test_save_failure_after_ticket_insert_rolls_back_all_business_work(self):
        p = self.create()
        with patch.object(reform,'_save',side_effect=OSError('injected mapping failure')):
            with self.assertRaises(OSError):reform.release(self.P,self.proj,p['id'],None,'owner')
        self.assertEqual(self.store.tickets(),[])
        self.assertEqual(self.submitted,[])
        made = reform.release(self.P,self.proj,p['id'],None,'owner')
        self.assertEqual(len(made),2)
        self.assertEqual(len(self.store.tickets()),2)

    def test_full_contract_is_not_truncated_and_explicit_empty_scope_is_empty(self):
        goal, keep, body = '目标'*5000, '约束'*3000, '先导'*4000
        p = reform.create(self.data,'RF',self.atlas,dict(title='x',goal=goal,keep=keep,
            lead={'body':body},scope_mode='selected',domains=['0']),'owner')
        saved = reform.plan(self.data,'RF',p['id'])
        self.assertEqual((saved['goal'],saved['keep'],saved['items'][0]['body']),(goal,keep,body))
        self.assertEqual(reform.split(self.atlas,[],scope_mode='selected'),[])
        with self.assertRaises(ValueError):self.create(scope_mode='selected',domains=[])

    def test_pause_completed_wave_resume_advances_without_another_event(self):
        p = self.create()
        made = reform.release(self.P,self.proj,p['id'],None,'owner')
        reform.configure(self.data,'RF',p['id'],auto=False)
        for key in made:reform.outcome(self.P,self.proj,self.close(key),True,'fixture')
        reform.configure(self.data,'RF',p['id'],auto=True)
        result = reform.resume(self.P,self.proj,p['id'],'owner')
        self.assertEqual(len(result['opened']),2)
        self.assertEqual(reform.resume(self.P,self.proj,p['id'],'owner')['opened'],[])

    def test_active_archive_refused_and_old_identity_never_reused(self):
        p = self.create()
        made = reform.release(self.P,self.proj,p['id'],None,'owner')
        with self.assertRaises(ValueError):reform.remove(self.data,'RF',p['id'])
        for key in made:self.close(key)
        reform.configure(self.data,'RF',p['id'],auto=False)
        reform.remove(self.data,'RF',p['id'])
        new = self.create()
        self.assertNotEqual(new['id'],p['id'])
        self.assertTrue(reform.plan(self.data,'RF',p['id'])['archived'])
        reform.outcome(self.P,self.proj,self.store.ticket(made[0]),True,'old replay')
        self.assertFalse(any(i.get('ticket') for i in reform.plan(self.data,'RF',new['id'])['items']))

    def test_wrong_ticket_cannot_advance_a_plan(self):
        p = self.create()
        foreign = self.store.create_ticket(self.proj['id'],'foreign','fixture',links={'reform':{'plan':p['id'],'order':1}})
        reform.outcome(self.P,self.proj,foreign,False,'forged','no redo')
        self.assertNotIn('paused',reform.plan(self.data,'RF',p['id']))

    def test_pending_dispatch_survives_disconnect_and_resumes_same_tickets(self):
        p = self.create()
        with patch.object(reform,'_dispatch',side_effect=OSError('injected disconnect')):
            with self.assertRaises(OSError):reform.release(self.P,self.proj,p['id'],None,'owner')
        self.assertEqual(len(self.store.tickets()),2)
        self.assertEqual(self.submitted,[])
        resumed = reform.resume(self.P,self.proj,p['id'],'owner')
        self.assertEqual(len(resumed['opened']),2)
        self.assertEqual(len(self.store.tickets()),2)
        self.assertEqual(len(self.submitted),2)

    def test_claim_without_completion_is_unknown_and_is_never_replayed(self):
        p = self.create()
        self.P.flow.submit = lambda p,t: (_ for _ in ()).throw(OSError('lost external acknowledgement'))
        with self.assertRaises(OSError):reform.release(self.P,self.proj,p['id'],None,'owner')
        # A new Store represents another server process sharing only durable data.
        other = Store(self.data/'platform.db')
        self.addCleanup(other.db.close)
        P = SimpleNamespace(data_dir=self.data,store=other,flow=SimpleNamespace(BY='flow',submit=lambda p,t:self.submitted.append(t['key'])))
        reform.resume(P,self.proj,p['id'],'owner')
        view = reform.view(P,self.proj,reform.plan(self.data,'RF',p['id']))
        self.assertEqual(view['items'][0]['dispatch_state'],'claimed')
        self.assertEqual(self.submitted,[],'unknown claim also blocks the remaining pending steps')
        with self.assertRaises(ValueError):reform.release(P,self.proj,p['id'],None,'owner')
        self.assertEqual(len(self.store.tickets()),2)

    def test_legacy_import_preserves_original_file_history_and_identity(self):
        p = self.create()
        legacy = dict(p,id='r1')
        legacy.pop('uid')
        self.store.x('DELETE FROM reform_catalog')
        original = json.dumps([legacy],ensure_ascii=False).encode()
        f = self.data/'reforms'/'RF.json'
        f.parent.mkdir()
        f.write_bytes(original)
        imported = reform.plan(self.data,'RF','r1')
        self.assertTrue(imported['uid'])
        self.assertEqual(f.read_bytes(),original)
        self.assertEqual(reform.plan(self.data,'RF','r1')['uid'],imported['uid'])
        reform.remove(self.data,'RF','r1')
        self.assertNotEqual(self.create()['id'],'r1')
        self.assertTrue(reform.plan(self.data,'RF','r1')['archived'])
        self.assertEqual(f.read_bytes(),original)

    def test_preview_revision_conflict_keeps_the_full_original_contract(self):
        draft = dict(title='x',goal='whole goal',scope_mode='selected',domains=['0'])
        preview = reform.preview(self.atlas,draft)
        changed = dict(self.atlas,built='new-revision')
        with self.assertRaisesRegex(ValueError,'重新预览'):
            reform.create(self.data,'RF',changed,dict(draft,knowledge_revision=preview['knowledge_revision']),'owner')
        self.assertEqual(reform.plans(self.data,'RF'),[])
        self.assertEqual(draft['goal'],'whole goal')
