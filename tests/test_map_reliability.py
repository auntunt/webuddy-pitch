"""Scope diffs and flow associations must not invent execution facts."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tests import test_external_candidates as fixtures
from tmh.platform import reform, reform_api
from tmh.platform.errors import ApiError
from tmh.platform.knowledge import Knowledge

class SuccessorContractTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ExternalCandidateTest('runTest');self.addCleanup(self.f.doCleanups);self.f.setUp()
        self.P=self.f.P;self.atlas={'built':'x','domains':[{'id':'a','title':'A','tables':0}]}
        p=patch.object(self.P.kb,'atlas',return_value=self.atlas);p.start();self.addCleanup(p.stop)
        self.original=reform.create(self.P.data_dir,'EXT',self.atlas,dict(title='Original',goal='Preserve',target='old',dependencies=['old condition']),'fixture')
    def test_each_contract_change_and_missing_history_is_explicit(self):
        for field,value in [('target','new'),('dependencies',['new condition']),('criteria',['Independent result']),('target_environment','isolated')]:
            body=dict(reform.contract(self.original),supersedes={'plan_id':self.original['id'],'revision':1,'reason':'new rule'})
            body[field]=value
            successor=reform.create(self.P.data_dir,'EXT',self.atlas,body,'fixture')
            changes={row['field']:row for row in reform.contract_changes(successor)}
            self.assertIn(field,changes);self.assertEqual(changes[field]['after'],value)
            self.assertEqual(reform.plan(self.P.data_dir,'EXT',self.original['id']),self.original)
        successor['predecessor_contract'].pop('target')
        self.assertEqual(next(c for c in reform.contract_changes(successor) if c['field']=='target')['before_status'],'旧版本未记录')
    def test_successor_fill_conditions_and_replay_does_not_touch_original(self):
        child=reform.create(self.P.data_dir,'EXT',self.atlas,dict(reform.contract(self.original),supersedes={'plan_id':self.original['id'],'revision':1,'reason':'fill gaps'}),'fixture')
        req=SimpleNamespace(user='fixture')
        args=dict(project='EXT',plan_id=child['id'],expected_revision=1,request_id='fill-once',reason='prepare',changes=dict(source_version=self.f.sha,target_environment='isolated',criteria=['Independent result']))
        result=reform_api.execute(self.P,req,'fixture','reform_update',args)
        self.assertEqual(result['source_version'],self.f.sha);self.assertEqual(result['effective_wave'],1)
        self.assertEqual(result,reform_api.execute(self.P,req,'fixture','reform_update',args))
        self.assertEqual(reform.plan(self.P.data_dir,'EXT',self.original['id']),self.original)
        with self.assertRaises(ApiError):reform_api.execute(self.P,req,'fixture','reform_update',dict(args,request_id='stale'))
        with self.assertRaises(ValueError):reform.create(self.P.data_dir,'EXT',self.atlas,dict(reform.contract(self.original),supersedes={'plan_id':self.original['id'],'revision':99,'reason':'stale'}),'fixture')

class AtlasFlowPagingTest(unittest.TestCase):
    def test_pages_keep_flow_io_separate_from_method_io(self):
        from tmh import graph
        import sqlite3, json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'refund.py').write_text('def refund():\n    return 1250\n')
            graph.build(root)
            with sqlite3.connect(graph.graph_path(root)) as db:
                db.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)',('flow:refund','flow','退款','退款','refund.py',1,2,'','','',json.dumps({'crud':{'budget':'U'}})))
                for i in range(65):
                    nid='fn:step%02d'%i
                    db.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)',(nid,'fn',nid,nid,'refund.py',1,2,'','','','{}'))
                    db.execute('INSERT INTO edges VALUES(?,?,?,?,?,?)',('flow:refund',nid,'step','','refund.py',1))
                db.execute('INSERT INTO edges VALUES(?,?,?,?,?,?)',('fn:step00','fn:step02','calls','','refund.py',1))
            k=Knowledge(None,None)
            with patch.object(k,'root',return_value=root),patch.object(k,'_open_tickets_by_flow',return_value={}):
                first=k.atlas_flow({},'refund');last=k.atlas_flow({},'refund',first['next_offset'])
                self.assertEqual((len(first['steps']),len(last['steps']),first['steps_total']),(60,5,65))
                self.assertIsNone(last['next_offset'])
                self.assertEqual(len({s['id'] for s in first['steps']+last['steps']}),65)
                self.assertEqual(first['steps'][0]['calls'],['fn:step02'])
                self.assertTrue(all(not s['io'] for s in first['steps']+last['steps']))
                self.assertEqual(first['crud'],{'budget':'U'})
                self.assertEqual(first['provenance']['index_revision'],last['provenance']['index_revision'])
                with self.assertRaises(ApiError):k.atlas_flow({},'refund',-1)
