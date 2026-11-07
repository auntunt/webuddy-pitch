"""Jenkins API contract fixtures; live demonstration is recorded separately."""
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tmh.platform import project_ci, private_ci


class JenkinsCITest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.data=Path(tmp.name)
        self.sha='a'*40;self.remote='ssh://git@git.example.test/team/erp.git'
        self.connection={'provider':'jenkins','url':'https://jenkins.example.test/jenkins',
            'user_env':'DEMO_JENKINS_USER','token_env':'DEMO_JENKINS_TOKEN',
            'projects':{'ERP':['team/erp']},
            'repositories':{'team/erp':{'remote_urls':[self.remote],'jobs':{'business':['ERP folder','main']}}}}
        (self.data/'ci-connections.json').write_text(json.dumps({'demo':self.connection}))
        project_ci.save(self.data,'ERP',{'revision':project_ci.configuration(self.data,'ERP')['revision'],
            'config':{'provider':'jenkins','connection':'demo','repository':'team/erp','required_checks':['business']}})

    def build(self,number=1,sha=None,remote=None,**changes):
        return dict({'number':number,'building':False,'result':'SUCCESS','actions':[
            {'_class':'hudson.plugins.git.util.BuildData','remoteUrls':[remote or self.remote],
             'lastBuiltRevision':{'SHA1':sha or self.sha}}]},**changes)

    def query(self,builds,status=200,payload=None):
        owner=self;calls=[]
        class Connection:
            def __init__(self,host,timeout):owner.assertEqual(host,'jenkins.example.test')
            def request(self,method,path,headers):
                owner.assertEqual(method,'GET');calls.append(path)
                owner.assertEqual(headers['Authorization'],'Basic '+base64.b64encode(b'fixture:fixture-token').decode())
            def getresponse(self):return self
            def read(self,limit):return json.dumps(payload if payload is not None else {
                'lastBuild':{'number':builds[0]['number']} if builds else None,'builds':builds}).encode()
            def close(self):pass
        Connection.status=status
        with patch.dict(os.environ,DEMO_JENKINS_USER='fixture',DEMO_JENKINS_TOKEN='fixture-token'),\
             patch.object(private_ci.http.client,'HTTPSConnection',Connection):
            value=project_ci.check(self.data,'ERP',self.sha)
        self.assertNotIn('fixture-token',json.dumps(value))
        return value,calls

    def test_exact_repository_sha_and_job_path(self):
        value,calls=self.query([self.build()])
        self.assertEqual(value['state'],'pass')
        self.assertEqual(self.query([],payload={'lastBuild':{'number':1,'_class':'hudson.model.FreeStyleBuild'},'builds':[self.build()]})[0]['state'],'pass')
        self.assertTrue(calls[0].startswith('/jenkins/job/ERP%20folder/job/main/api/json?tree='))
        self.assertEqual(value['checks'][0]['runs'][0]['commit'],self.sha)

    def test_no_build_wrong_repository_sha_and_untrusted_parameters_block(self):
        for builds in ([],[self.build(sha='b'*40)],[self.build(remote='ssh://other/erp.git')],
                       [self.build(actions=[{'parameters':[{'name':'GIT_COMMIT','value':self.sha}]}])]):
            with self.subTest(builds=builds):self.assertEqual(self.query(builds)[0]['state'],'blocked')

    def test_failure_cancel_unstable_notbuilt_and_running_block(self):
        for result in ('FAILURE','ABORTED','UNSTABLE','NOT_BUILT',None):
            self.assertEqual(self.query([self.build(result=result)])[0]['state'],'blocked')
        self.assertEqual(self.query([self.build(building=True)])[0]['state'],'blocked')

    def test_newest_matching_run_wins_and_successful_rerun_is_usable(self):
        self.assertEqual(self.query([self.build(2,result='FAILURE'),self.build()])[0]['state'],'blocked')
        self.assertEqual(self.query([self.build(2),self.build(result='FAILURE')])[0]['state'],'pass')
        self.assertEqual(self.query([self.build(2,sha='b'*40),self.build()])[0]['state'],'pass')

    def test_newer_unknown_checkout_cannot_be_hidden_by_old_success(self):
        self.assertEqual(self.query([self.build(2,actions=[]),self.build()])[0]['state'],'blocked')

    def test_malformed_missing_latest_duplicate_and_redirect_block(self):
        for payload in ({'builds':[self.build()]}, {'lastBuild':{'number':2},'builds':[self.build()]},
                        {'lastBuild':{'number':1},'builds':[self.build(),self.build()]},
                        {'lastBuild':None,'builds':[{'number':1}]},[]):
            self.assertEqual(self.query([],payload=payload)[0]['state'],'blocked')
        self.assertEqual(self.query([],status=302)[0]['state'],'blocked')

    def test_multi_checkout_same_repository_different_revision_blocks(self):
        build=self.build();build['actions'].extend(self.build(sha='b'*40)['actions'])
        self.assertEqual(self.query([build])[0]['state'],'blocked')

    def test_missing_credential_does_not_query(self):
        with patch.dict(os.environ,{},clear=True),patch.object(private_ci.http.client,'HTTPSConnection',side_effect=AssertionError):
            self.assertEqual(project_ci.check(self.data,'ERP',self.sha)['state'],'blocked')

    def test_malformed_revision_blocks_without_escaping_query(self):
        for revision in (None, [], 'bad', 42):
            build=self.build();build['actions'][0]['lastBuiltRevision']=revision
            self.assertEqual(self.query([build])[0]['state'],'blocked')
