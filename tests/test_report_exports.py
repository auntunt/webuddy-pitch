"""Frozen exports: full original bytes, resumed retrieval, no implicit writes."""
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tests import test_external_candidates as fixtures
from tmh.platform import reform, report_exports
from tmh.platform.errors import ApiError
from tmh.report_download import download

class ReportExportsTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ExternalCandidateTest('runTest');self.addCleanup(self.f.doCleanups);self.f.setUp()
        self.P,self.project=self.f.P,self.f.p
        self.plan=reform.create(self.P.data_dir,'EXT',{'built':'x','domains':[{'id':'one','title':'One','tables':0}]},dict(title='Refund',goal='Keep independent refund rule'),'fixture')
        self.args=dict(project='EXT',plan_id=self.plan['id'],expected_revision=1,request_id='frozen-export')
    def create(self):return report_exports.create(self.P,self.project,self.plan,'fixture',self.args)
    def read(self,args):return report_exports.read(self.P,self.project,self.plan,args)
    def test_real_report_saved_once_reads_are_readonly_and_project_bound(self):
        manifest=self.create();self.assertEqual(self.create(),manifest)
        before=self.P.store.db.total_changes
        for entry in manifest['files']:
            raw=b'';offset=0
            while offset is not None:
                chunk=self.read(dict(export_id=manifest['export_id'],file=entry['name'],offset=offset))
                raw+=base64.b64decode(chunk['data_base64']);offset=chunk['next_offset']
            self.assertEqual(hashlib.sha256(raw).hexdigest(),entry['sha256'])
        self.assertEqual(before,self.P.store.db.total_changes)
        with self.assertRaises(ApiError):report_exports.read(self.P,dict(self.project,id=9999),self.plan,dict(export_id=manifest['export_id']))
        with self.assertRaises(ApiError):report_exports.create(self.P,self.project,self.plan,'fixture',dict(self.args,expected_revision=2))
    def test_large_report_resume_new_version_and_corruption(self):
        # 36 MB of original evidence, not an aggregate test count or customer POC.
        original=('0123456789abcdef'*2250000)
        record={'ticket':{'key':'TEST','title':'Refund','body':'independent rule'},'generated_at':'fixture',
                'scenario':None,'consumption':[],'next_step':'human decision pending','child_evidence':[], 'original':original}
        with patch('tmh.platform.reform_api.report',return_value=record):manifest=self.create()
        calls=[]; fail=[True]
        def call(operation,args):
            calls.append(args)
            if args.get('offset',0)>=report_exports.CHUNK*2 and fail[0]:raise ConnectionError('injected disconnect')
            return self.read(args)
        client=SimpleNamespace(call=call)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ConnectionError):download(client,'EXT',self.plan['id'],manifest['export_id'],directory)
            self.args['request_id']='new-version'
            second=self.create();self.assertNotEqual(second['export_id'],manifest['export_id'])
            fail[0]=False;calls.clear()
            result=download(client,'EXT',self.plan['id'],manifest['export_id'],directory)
            self.assertEqual(result['integrity'],'verified')
            saved=json.loads((Path(result['directory'])/'plan.json').read_text())
            self.assertEqual(saved['original'],original)
            offsets=[a['offset'] for a in calls if a.get('file')=='plan.json']
            self.assertEqual(min(offsets),report_exports.CHUNK*2)
        self.P.store.x('UPDATE report_export_files SET body=? WHERE export_id=? AND name=?',(b'corrupt',manifest['export_id'],'plan.json'))
        with self.assertRaises(ApiError):self.read(dict(export_id=manifest['export_id'],file='plan.json'))
    def test_revocation_during_download_never_publishes_complete_file(self):
        manifest=self.create();n=[0]
        def call(op,args):
            n[0]+=1
            if n[0]>2:raise ApiError(403,'revoked')
            return self.read(args)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ApiError):download(SimpleNamespace(call=call),'EXT',self.plan['id'],manifest['export_id'],directory)
            self.assertFalse((Path(directory)/manifest['export_id']/'plan.json').exists())

class ColdImportTest(unittest.TestCase):
    def test_fresh_process_actual_read_audit_without_cache_prewarming(self):
        # The interpreter starts without -B and with an empty cache destination.
        with tempfile.TemporaryDirectory() as tmp:
            code="import sys; sys.pycache_prefix="+repr(tmp)+"; from tests.test_tool_read import ToolReadTests; import unittest; r=unittest.TextTestRunner().run(unittest.TestSuite([ToolReadTests('test_all_allowed_read_branches_have_no_live_effects_or_writes')])); assert r.wasSuccessful(); from pathlib import Path; assert sys.dont_write_bytecode; cached=list(Path(sys.pycache_prefix).rglob('tmh/**/*.pyc')); assert all(p.parent.name=='tmh' and p.name.startswith('__init__.') for p in cached), cached"
            result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
