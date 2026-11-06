"""Protocol fixtures, not customer CI integration tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tmh.platform import project_ci, private_ci
from tmh.platform.errors import ApiError


class PrivateCITest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name); self.sha = 'a'*40
        self.config = {'provider':'gitlab','connection':'internal','repository':'team/sub/repo','required_checks':['tests']}
        self.connections = {'internal': {'provider':'gitlab','url':'https://ci.example.test',
                                        'projects': {'APP':['team/sub/repo']}}}
        self.write_connections()
        self.save()

    def write_connections(self):
        (self.data/'ci-connections.json').write_text(json.dumps(self.connections))

    def save(self):
        return project_ci.save(self.data,'APP', {'revision':project_ci.configuration(self.data,'APP')['revision'], 'config':self.config})

    def query(self, payloads, status=200):
        calls=[]; owner=self
        class Connection:
            def __init__(self,host,timeout): owner.assertEqual(host,'ci.example.test')
            def request(self,method,path,headers): calls.append(path)
            def getresponse(self): return self
            def read(self,limit): return json.dumps(payloads.pop(0)).encode()
            def close(self): pass
        Connection.status=status
        with patch.object(private_ci.http.client,'HTTPSConnection',Connection):
            result=project_ci.check(self.data,'APP',self.sha)
        return result,calls

    def job(self,**changes):
        return dict({'id':2,'name':'tests','status':'success','web_url':'https://ci.example.test/job/2',
                     'commit':{'id':self.sha},'pipeline':{'id':1}},**changes)

    def test_gitlab_exact_sha_encoded_repository_and_jobs(self):
        result,calls=self.query([[{'id':1,'sha':self.sha,'status':'success'}],[self.job()]])
        self.assertEqual(result['state'],'pass')
        self.assertIn('/projects/team%2Fsub%2Frepo/pipelines?sha='+self.sha,calls[0])
        self.assertIn('include_retried=false',calls[1])

    def test_no_pipeline_missing_job_failure_skip_cancel_pending(self):
        for jobs in ([],[self.job(status='failed')],[self.job(status='skipped')],
                     [self.job(status='canceled')],[self.job(status='running')],
                     [self.job(),self.job(id=3,status='failed')]):
            with self.subTest(jobs=jobs):
                self.assertEqual(self.query([[{'id':1,'sha':self.sha,'status':'success'}],jobs])[0]['state'],'blocked')
        self.assertEqual(self.query([[]])[0]['state'],'blocked')

    def test_wrong_pipeline_and_job_binding_never_pass(self):
        for payload in ([[{'id':1,'sha':'b'*40,'status':'success'}]],
                        [[{'id':1,'sha':self.sha,'status':'success'}],[self.job(commit={'id':'b'*40})]],
                        [[{'id':1,'sha':self.sha,'status':'success'}],[self.job(pipeline={'id':2})]],
                        [[{'id':1,'sha':self.sha,'status':'success'}],[{'name':'tests'}]]):
            with self.subTest(payload=payload):self.assertEqual(self.query(payload)[0]['state'],'blocked')

    def test_redirect_credentials_revocation_and_project_grant(self):
        self.assertEqual(self.query([],status=302)[0]['state'],'blocked')
        self.connections['internal']['token_env']='WEBUDDY_TEST_MISSING_CI_TOKEN'
        self.write_connections()
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(self.query([])[0]['state'],'blocked')
        self.connections['internal']['projects']={}
        self.write_connections()
        with self.assertRaises(ApiError):self.save()
        self.assertEqual(self.query([])[0]['state'],'blocked')

    def test_invalid_destination_rejected_at_configuration(self):
        for url in ('http://ci.example.test','https://user:secret@ci.example.test','https://ci.example.test?token=x'):
            self.connections['internal']['url']=url;self.write_connections()
            with self.subTest(url=url),self.assertRaises(ApiError):self.save()

    def test_gitea_commit_and_all_required_statuses(self):
        self.config.update(provider='gitea',repository='team/repo')
        self.connections['internal'].update(provider='gitea',projects={'APP':['team/repo']})
        self.write_connections();self.save()
        success={'context':'tests','status':'success','id':1,'target_url':'https://ci.example.test/job/1'}
        result,calls=self.query([{'sha':self.sha,'total_count':1,'statuses':[success]}])
        self.assertEqual(result['state'],'pass')
        self.assertIn('/api/v1/repos/team/repo/commits/'+self.sha,calls[0])
        for result in ({'sha':'b'*40,'total_count':1,'statuses':[success]},
                       {'sha':self.sha,'total_count':0,'statuses':[]},
                       {'sha':self.sha,'total_count':1,'statuses':[dict(success,status='pending')]}):
            self.assertEqual(self.query([result])[0]['state'],'blocked')

    def test_pagination_does_not_accept_partial_results(self):
        pipelines=[{'id':i,'sha':self.sha,'status':'success'} for i in range(100)]
        result,calls=self.query([pipelines]*10)
        self.assertEqual(result['state'],'blocked')
        self.assertEqual(len(calls),10)

    def test_latest_pipeline_must_finish_and_rerun_can_replace_failure(self):
        for status in ('failed','canceled','skipped','running'):
            result,_=self.query([[{'id':2,'sha':self.sha,'status':status}]])
            self.assertEqual(result['state'],'blocked')
        result,calls=self.query([[{'id':1,'sha':self.sha,'status':'failed'},
                                  {'id':2,'sha':self.sha,'status':'success'}],
                                 [self.job(pipeline={'id':2})]])
        self.assertEqual(result['state'],'pass')
        self.assertIn('/pipelines/2/jobs',calls[-1])

    def test_connection_change_invalidates_configuration_revision(self):
        old=project_ci.configuration(self.data,'APP')['revision']
        self.connections['internal']['url']='https://changed.example.test'
        self.write_connections()
        self.assertNotEqual(old,project_ci.configuration(self.data,'APP')['revision'])
        with self.assertRaises(ApiError):
            project_ci.save(self.data,'APP',{'revision':old,'config':self.config})
