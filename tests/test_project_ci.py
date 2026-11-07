import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tmh.platform import project_ci
from tmh.platform.errors import ApiError


class ProjectCITest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.data=Path(temp.name)
        self.sha='a'*40
        project_ci.save(self.data,'ERP',{'revision':project_ci.configuration(self.data,'ERP')['revision'],
            'config':{'repository':'org/repo','required_checks':['tests']}})

    def run_check(self,runs,status=200):
        owner=self
        class Response:
            def __init__(self):self.status=status
            def read(self,limit):return json.dumps({'total_count':len(runs),'check_runs':runs}).encode()
        class Connection:
            def __init__(self,host,timeout):owner.assertEqual(host,'api.github.com')
            def request(self,method,path,headers):owner.assertTrue(path.startswith('/repos/org/repo/commits/'+owner.sha))
            def getresponse(self):return Response()
            def close(self):pass
        with patch.object(project_ci.http.client,'HTTPSConnection',Connection):
            return project_ci.check(self.data,'ERP',self.sha)

    def check_run(self,**kwargs):
        return dict({'name':'tests','head_sha':self.sha,'app':{'slug':'github-actions'},'status':'completed',
                     'conclusion':'success','id':1,'html_url':'https://github.com/org/repo/actions/runs/1'},**kwargs)

    def test_exact_success(self):self.assertEqual(self.run_check([self.check_run()])['state'],'pass')

    def test_missing_wrong_sha_or_wrong_app_cannot_pass(self):
        for runs in ([],[self.check_run(head_sha='b'*40)],[self.check_run(app={'slug':'untrusted'})]):
            with self.subTest(runs=runs):self.assertEqual(self.run_check(runs)['state'],'blocked')

    def test_fail_skip_cancel_pending_and_duplicate_failure_cannot_pass(self):
        for conclusion in ('failure','skipped','cancelled',None):
            with self.subTest(conclusion=conclusion):
                self.assertEqual(self.run_check([self.check_run(),self.check_run(id=2,conclusion=conclusion)])['state'],'blocked')
        self.assertEqual(self.run_check([self.check_run(status='in_progress')])['state'],'blocked')

    def test_redirect_is_not_followed(self):self.assertEqual(self.run_check([],status=302)['state'],'blocked')

    def test_malformed_report_cannot_pass(self):self.assertEqual(self.run_check([{'name':'tests'}])['state'],'blocked')

    def test_config_conflict_and_empty_required_checks(self):
        for revision,checks in [('stale',['tests']),(project_ci.configuration(self.data,'ERP')['revision'],[])]:
            with self.subTest(checks=checks),self.assertRaises(ApiError):
                project_ci.save(self.data,'ERP',{'revision':revision,'config':{'repository':'org/repo','required_checks':checks}})

    def test_short_sha_rejected(self):
        with self.assertRaises(ApiError):project_ci.check(self.data,'ERP','a'*7)

    def test_no_configuration_is_not_success(self):
        self.assertEqual(project_ci.check(self.data,'OTHER',self.sha)['state'],'not_configured')
