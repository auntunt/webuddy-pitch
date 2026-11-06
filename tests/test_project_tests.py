import base64
import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tmh.platform import project_tests as pt
from tmh.platform.errors import ApiError


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        (self.root/'.gitignore').write_text('report.json\nreports/\nevidence/\n')
        subprocess.run(['git','-C',str(self.root),'add','.gitignore'],check=True)
        subprocess.run(['git','-C',str(self.root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],check=True)

    def profile(self, command=None):
        return {'executor':'local', 'require_all_criteria':True, 'stages':[
            {'id':'unit','kind':'unit','required':True,'timeout':5,
             'command':command or '''node -e "require('fs').writeFileSync('report.json',JSON.stringify({cases:[{id:'sum',status:'pass'}]}))"''',
             'report':{'format':'json','path':'report.json'},'criteria':{'A1':['sum']}}]}

    def execute(self, profile):
        pt.validate(profile)
        plan = self.root / 'plan.json'
        plan.write_text(json.dumps({'stages':profile['stages'],'nonce':'fixture'}))
        runner = Path(pt.__file__).with_name('project_test_runner.cjs')
        run = subprocess.run(['node',str(runner),str(plan)],cwd=self.root,capture_output=True,timeout=20,check=True,start_new_session=os.name != 'nt')
        receipt = json.loads(base64.b64decode(run.stdout.decode().split('TMH_PROJECT_TESTS_fixture:')[1]))
        folder = self.root/'evidence'
        folder.mkdir(exist_ok=True)
        return pt.collect(profile,receipt,folder,[{'id':'A1','text':'sum works'}])

    def test_actual_command_and_raw_artifacts(self):
        report=self.execute(self.profile())
        self.assertEqual(report['status'],'pass')
        self.assertEqual((self.root/'report.json').read_bytes(),(self.root/'evidence/unit-0.json').read_bytes())
        self.assertEqual(report['criterion_evidence']['A1'][0]['status'],'pass')

    def test_source_mutation_blocks_later_stage_instead_of_mixing_versions(self):
        p = self.profile()
        p['stages'].insert(0, dict(id='mutate',kind='static',required=True,timeout=3,
            command="node -e \"require('fs').writeFileSync('business.js','changed')\""))
        result = self.execute(p)
        self.assertTrue(result['code_changed'])
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['stages'][1]['execution_status'], 'not_run')
        self.assertFalse((self.root/'report.json').exists())
        self.assertEqual(result['uncovered_criteria'], ['A1'])

    def test_zero_exit_failed_assertion_blocks(self):
        p=self.profile();p['stages'][0]['command']=p['stages'][0]['command'].replace("status:'pass'","status:'fail'")
        r=self.execute(p)
        self.assertEqual(r['status'],'fail');self.assertEqual(r['stages'][0]['exit_code'],0)
        self.assertEqual(r['uncovered_criteria'],['A1'])

    def test_missing_stale_zero_and_skipped_reports_block(self):
        for raw in (None, {'cases':[]}, {'cases':[{'id':'sum','status':'skip'}]}):
            with self.subTest(raw=raw):
                path=self.root/'report.json'
                if path.exists():path.unlink()
                command='node -e "process.exit(0)"' if raw is None else 'node -e "require(\'fs\').writeFileSync(\'report.json\',Buffer.from(\'%s\',\'base64\'))"'%base64.b64encode(json.dumps(raw).encode()).decode()
                self.assertEqual(self.execute(self.profile(command))['status'],'fail')
        self.execute(self.profile())
        result=self.execute(self.profile('node -e "process.exit(0)"'))
        self.assertIn('未更新',result['stages'][0]['error'])

    def test_timeout_dependencies_and_cleanup(self):
        p=self.profile('node -e "setTimeout(()=>{},10000)"');p['stages'][0]['timeout']=1
        p['stages'] += [dict(id='integration',kind='static',required=True,timeout=2,command='echo should-not-run',depends_on=['unit']),dict(id='cleanup',kind='cleanup',required=True,timeout=2,command='echo cleanup-ran',depends_on=['unit'])]
        r=self.execute(p)
        self.assertEqual(r['stages'][0]['exit_code'],124)
        self.assertEqual(r['stages'][0]['execution_status'],'blocked')
        self.assertEqual(r['stages'][0]['failure_kind'],'timeout')
        self.assertEqual(r['stages'][1]['execution_status'],'not_run')
        self.assertIn('未执行',r['stages'][1]['error'])
        self.assertIn('cleanup-ran',r['stages'][2]['output'])
        self.assertEqual(r['status'],'fail')

    @unittest.skipIf(os.name == 'nt', 'POSIX process group lifecycle')
    def test_background_service_survives_stages_and_is_reaped(self):
        import time
        service = self.root/'service.cjs'
        service.write_text("const fs=require('fs');fs.writeFileSync('reports/pid',String(process.pid));console.log('service-ready');setInterval(()=>{},1000)")
        p=self.profile()
        p['stages'].insert(0, dict(id='start',kind='setup',required=True,timeout=3,
            command='mkdir -p reports; node service.cjs &',depends_on=[]))
        p['stages'][1]['command'] = "node -e \"const fs=require('fs');setTimeout(()=>{process.kill(Number(fs.readFileSync('reports/pid')),0);fs.writeFileSync('report.json',JSON.stringify({cases:[{id:'sum',status:'pass'}]}))},300)\""
        result=self.execute(p)
        self.assertEqual(result['status'],'pass',result)
        self.assertIn('service-ready',result['stages'][0]['output'])
        pid=int((self.root/'reports/pid').read_text())
        for _ in range(30):
            state=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True).stdout.strip()
            if not state or state.startswith('Z'):break
            time.sleep(.05)
        self.assertTrue(not state or state.startswith('Z'),state)

    @unittest.skipIf(os.name == 'nt', 'POSIX cancellation')
    def test_cancellation_reaps_owned_processes_and_keeps_log(self):
        import time
        (self.root/'reports').mkdir()
        (self.root/'service.cjs').write_text("require('fs').writeFileSync('reports/pid',String(process.pid));console.log('started');setInterval(()=>{},1000)")
        plan=self.root/'plan.json'
        raw=self.root/'evidence/raw';raw.parent.mkdir()
        plan.write_text(json.dumps({'stages':self.profile('node service.cjs')['stages'],'nonce':'cancel','artifact_dir':str(raw)}))
        runner=Path(pt.__file__).with_name('project_test_runner.cjs')
        process=subprocess.Popen(['node',str(runner),str(plan)],cwd=self.root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        try:
            for _ in range(100):
                if (self.root/'reports/pid').exists():break
                time.sleep(.02)
            self.assertTrue((self.root/'reports/pid').exists())
            pid=int((self.root/'reports/pid').read_text())
            time.sleep(.05)
            process.terminate();out,err=process.communicate(timeout=5)
            self.assertEqual(process.returncode,130,err)
            self.assertNotIn(b'TMH_PROJECT_TESTS_',out)
            self.assertIn('started',(raw/'unit.log').read_text())
            for _ in range(30):
                state=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True).stdout.strip()
                if not state or state.startswith('Z'):break
                time.sleep(.05)
            self.assertTrue(not state or state.startswith('Z'),state)
        finally:
            if process.poll() is None:
                import signal
                os.killpg(process.pid,signal.SIGKILL);process.communicate()

    def test_profile_conflicts_and_validation(self):
        revision=pt.view(self.root,'P')['revision']
        pt.save(self.root,'P',{'revision':revision,'profile':self.profile()})
        with self.assertRaises(ApiError):pt.save(self.root,'P',{'revision':revision,'profile':self.profile()})
        for path in ('../secret','/tmp/file','C:/secret','a\\b'):
            p=self.profile();p['stages'][0]['report']['path']=path
            with self.assertRaises(ApiError):pt.validate(p)
        p=self.profile();p['stages'][0]['depends_on']=['unit']
        with self.assertRaises(ApiError):pt.validate(p)

    def test_concurrent_configuration_save_has_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        revision=pt.view(self.root,'P')['revision']
        def write(_):
            try:
                pt.save(self.root,'P',{'revision':revision,'profile':self.profile()})
                return 200
            except ApiError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(write,range(2))),[200,409])
        self.assertEqual(pt.view(self.root,'P')['profile'],self.profile())

    def test_junit_case_status_and_duplicates(self):
        r=pt.cases(b'<testsuite tests="3"><testcase classname="math" name="ok"/><testcase name="bad"><failure/></testcase><testcase name="later"><skipped/></testcase></testsuite>','junit')
        self.assertEqual([c['status'] for c in r],['pass','fail','skip'])
        self.assertEqual(r[0]['id'],'math::ok')
        with self.assertRaises(ValueError):pt.cases(b'<testsuite/>','junit')
        with self.assertRaises(ValueError):pt.cases(b'<testsuite><testcase name="x"/><testcase name="x"/></testsuite>','junit')

    def test_business_values_are_preserved_without_invention(self):
        raw=b'<testsuite><testcase name="refund"><properties><property name="webuddy.input" value="12.50"/><property name="webuddy.expected" value="-12.5"/><property name="webuddy.actual" value="-12.5"/></properties></testcase><testcase name="unrecorded"/></testsuite>'
        values=pt.cases(raw,'junit')
        self.assertEqual(values[0]['actual'],'-12.5')
        self.assertNotIn('actual',values[1])
        self.assertEqual(pt.cases(b'{"cases":[{"id":"refund","status":"pass","input":"12.50","expected":-12.5,"actual":-12.5}]}','json')[0]['actual'],-12.5)

    def test_unit_suite_does_not_invent_build_or_baseline_evidence(self):
        from tmh.platform import gates
        report=self.execute(self.profile())
        result={g['id']:g for g in gates.checks({'commands':[{'kind':'test','command':'project tests','exit_code':0,'project_tests':report}]})}
        self.assertEqual(result['baseline']['state'],gates.UNKNOWN)
        self.assertEqual(result['build']['state'],gates.UNKNOWN)
        self.assertEqual(result['test']['state'],gates.PASS)

    def test_misleading_junit_summary_rejected(self):
        for attr in ('tests="2"', 'failures="1"', 'errors="1"', 'skipped="1"'):
            with self.subTest(attr=attr), self.assertRaises(ValueError):
                pt.cases(('<testsuite '+attr+'><testcase name="ok"/></testsuite>').encode(), 'junit')

    def test_tests_changing_source_cannot_pass(self):
        p=self.profile()
        p['stages'][0]['command'] += ' && node -e "require(\'fs\').writeFileSync(\'business.js\',\'changed\')"'
        result=self.execute(p)
        self.assertEqual(result['status'],'fail')
        self.assertTrue(result['code_changed'])
        self.assertEqual(result['criterion_evidence']['A1'][0]['status'], 'unverified')
        self.assertEqual(result['uncovered_criteria'], ['A1'])

    def test_independent_criterion_fact_survives_other_failure(self):
        p=self.profile();p['stages'][0]['command']=p['stages'][0]['command'].replace("{id:'sum',status:'pass'}","{id:'sum',status:'pass'},{id:'other',status:'fail'}")
        r=self.execute(p)
        self.assertEqual(r['status'],'fail')
        self.assertEqual(r['criterion_evidence']['A1'][0]['status'],'pass')

    def test_symlink_report_outside_root_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            outside=Path(other)/'secret.json';outside.write_text('{"cases":[{"id":"sum","status":"pass"}]}')
            (self.root/'report.json').symlink_to(outside)
            r=self.execute(self.profile())
            self.assertEqual(r['status'],'fail')
            self.assertNotIn('report',r['stages'][0])
            self.assertEqual(outside.read_text(),'{"cases":[{"id":"sum","status":"pass"}]}')



class RecheckProjectTests(unittest.TestCase):
    def setUp(self):
        from tests.test_code_review import ManualReviewTest
        self.fixture=ManualReviewTest();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.data=self.fixture.data
        self.profile=ProjectTests.profile(self)
        self.profile['require_all_criteria']=False
        pt.save(self.data,'APP',{'revision':pt.view(self.data,'APP')['revision'],'profile':self.profile})
        # Use the fixture's actual project key.
        project=self.fixture.store.project(self.fixture.run['project_id'])
        (self.data/'project-tests.json').write_text(json.dumps({project['key']:self.profile}))
        self.key=project['key']
        exclude=subprocess.check_output(['git','-C',str(self.fixture.root),'rev-parse','--git-path','info/exclude'],text=True).strip()
        path=Path(exclude)
        if not path.is_absolute():path=self.fixture.root/path
        with path.open('a') as f:f.write('\nreport.json\n')

    def test_actual_recheck_sealed_evidence_and_configuration_change(self):
        from tmh.platform.fixloop import recheck,verified
        v=recheck(self.fixture.runner,self.fixture.rid)
        self.assertEqual(v['check'],'pass',v)
        report=v['commands'][0]['project_tests']
        self.assertEqual(report['stages'][0]['cases'][0]['id'],'sum')
        self.assertTrue(verified(self.data,self.fixture.rid)['verification_current'])
        self.profile['stages'][0]['timeout']=6
        pt.save(self.data,self.key,{'revision':pt.view(self.data,self.key)['revision'],'profile':self.profile})
        stale=verified(self.data,self.fixture.rid)
        self.assertFalse(stale['verification_current'])
        self.assertIn('配置已变化',stale['skip'])

    def test_project_baseline_failure_is_retained_and_candidate_still_runs(self):
        from tmh.platform.fixloop import recheck
        self.profile['stages'][0]['command'] = "node -e \"const f=require('fs');f.writeFileSync('report.json',JSON.stringify({cases:[{id:'sum',status:f.readFileSync('app.py','utf8').includes('VALUE = 1')?'pass':'fail'}]}))\""
        pt.save(self.data,self.key,{'revision':pt.view(self.data,self.key)['revision'],'profile':self.profile})
        result = recheck(self.fixture.runner,self.fixture.rid)
        self.assertEqual(result['baseline']['state'], 'fail')
        self.assertEqual(result['baseline']['commands'][0]['project_tests']['stages'][0]['cases'][0]['status'], 'fail')
        self.assertEqual(result['check'], 'pass')
        base = result['baseline']['commands'][0]['project_tests']
        candidate = result['commands'][0]['project_tests']
        self.assertEqual(base['base'], candidate['base'])
        self.assertNotEqual(base['diff_sha256'], candidate['diff_sha256'])
        self.assertNotEqual(base['evidence'], candidate['evidence'])
        self.assertEqual((self.fixture.wt/'app.py').read_text(), 'VALUE = 1\n')

    def test_test_failure_with_unexecuted_dependents_still_requests_repair(self):
        from tmh.platform.fixloop import recheck
        self.profile['stages'][0]['command'] = self.profile['stages'][0]['command'].replace("status:'pass'", "status:'fail'") + ' && node -e "process.exit(1)"'
        self.profile['stages'].append(dict(id='dependent',kind='build',required=True,timeout=2,command='echo should-not-run',depends_on=['unit']))
        pt.save(self.data,self.key,{'revision':pt.view(self.data,self.key)['revision'],'profile':self.profile})
        result = recheck(self.fixture.runner,self.fixture.rid)
        self.assertEqual(result['commands'][0]['project_tests']['stages'][1]['execution_status'], 'not_run')
        self.assertEqual(result['commands'][0]['verification_state'], 'failed')
        self.assertEqual(result['outcome'], 'repair_required')

    def test_original_artifact_tampering_invalidates(self):
        from tmh.platform.fixloop import recheck,verified
        v=recheck(self.fixture.runner,self.fixture.rid)
        report=v['commands'][0]['project_tests']
        (self.data/report['evidence']/'unit-0.json').write_text('{}')
        self.assertFalse(verified(self.data,self.fixture.rid)['verification_current'])

    def test_effective_plan_and_client_contract_changes_invalidate(self):
        from tmh.platform.fixloop import recheck, verified
        from tmh.platform import signoff
        st=self.fixture.store;run=self.fixture.run
        plan=st.create_run(run['project_id'],run['ticket_id'],'fixture','plan','tester','')
        def content(text):
            return '```tmh-plan\n'+json.dumps({'ac':[{'id':'A1','text':text,'check':'assert result'}]})+'\n```'
        st.update_run(plan['id'],status='done',exit_code=0,result=content('original'))
        result=recheck(self.fixture.runner,self.fixture.rid)
        self.assertEqual(result['commands'][0]['project_tests']['criteria_contract']['source'],'plan')
        st.update_run(plan['id'],result=content('changed'))
        self.assertFalse(verified(self.data,self.fixture.rid)['verification_current'])
        ticket=st.ticket(run['ticket_id'])
        signoff._add(signoff.epath(self.data,ticket['key']),'intake','tester',{'ac':[{'id':'A1','text':'confirmed','check':'assert'}]})
        result=recheck(self.fixture.runner,self.fixture.rid)
        self.assertEqual(result['commands'][0]['project_tests']['criteria_contract']['source'],'client')
        signoff._add(signoff.epath(self.data,ticket['key']),'intake','tester',{'ac':[]})
        self.assertFalse(verified(self.data,self.fixture.rid)['verification_current'])
        result=recheck(self.fixture.runner,self.fixture.rid)
        self.assertEqual(result['commands'][0]['project_tests']['criteria_contract']['source'],'plan')

    def test_report_download_is_bound_to_run_and_original_bytes(self):
        from tmh.platform.fixloop import recheck
        result=recheck(self.fixture.runner,self.fixture.rid)
        payload=pt.artifact(self.data,self.fixture.rid,'unit','unit-0.json')
        self.assertEqual(json.loads(base64.b64decode(payload['base64']))['cases'][0]['id'],'sum')
        for name in ('../platform.db','result.json','not-found'):
            with self.assertRaises(ApiError):pt.artifact(self.data,self.fixture.rid,'unit',name)
        report=result['commands'][0]['project_tests']
        (self.data/report['evidence']/'unit-0.json').write_text('{}')
        with self.assertRaises(ApiError) as err:pt.artifact(self.data,self.fixture.rid,'unit','unit-0.json')
        self.assertEqual(err.exception.code,409)

    def test_new_profile_does_not_inherit_legacy_pass(self):
        from tmh.platform.fixloop import verified
        result=verified(self.data,self.fixture.rid)
        self.assertFalse(result['verification_current'])
        self.assertIn('没有对应测试报告',result['skip'])


class ProjectTestPermissions(unittest.TestCase):
    def test_owner_commands_and_member_project_scope(self):
        from tests.test_tenant_policy import TenantPolicyTest
        fixture=TenantPolicyTest();fixture.setUp();self.addCleanup(fixture.doCleanups)
        from tmh.platform.server import api_project_tests
        from types import SimpleNamespace
        fixture.P.project=lambda key: fixture.projects[key]
        fixture.context.trusted_host=lambda: True
        for actor,expected in [('alice',False),('owner',True)]:
            request=SimpleNamespace(h=SimpleNamespace(_who=actor,headers={}))
            self.assertEqual(api_project_tests(fixture.P,request,'ALPHA')['can_edit'],expected)
        fixture.auth('/api/runs/%s/test-report' % fixture.runs['ALPHA']['id'])
        fixture.denied('/api/runs/%s/test-report' % fixture.runs['BETA']['id'],query={'project':'ALPHA'})
        fixture.auth('/api/projects/ALPHA/tests')
        fixture.denied('/api/projects/BETA/tests')
        fixture.denied('/api/projects/BETA/tests',query={'project':'ALPHA'})
        for actor in ('alice','bob','admin','reader'):
            fixture.denied('/api/projects/ALPHA/tests',method='POST',actor=actor,body={'revision':'x','profile':{}})


class MultiReportTests(unittest.TestCase):
    setUp = ProjectTests.setUp
    profile = ProjectTests.profile
    execute = ProjectTests.execute
    def test_multiple_junit_reports_preserve_all_cases(self):
        p=self.profile('node make.cjs')
        p['stages'][0].update(report={'format':'junit','path':'reports/TEST-*.xml'},criteria={'A1':['a::one','b::two']})
        (self.root/'make.cjs').write_text("const f=require('fs');f.mkdirSync('reports',{recursive:true});f.writeFileSync('reports/TEST-a.xml','<testsuite><testcase classname=\"a\" name=\"one\"/></testsuite>');f.writeFileSync('reports/TEST-b.xml','<testsuite><testcase classname=\"b\" name=\"two\"/></testsuite>');")
        r=self.execute(p)
        self.assertEqual(r['status'],'pass')
        self.assertEqual(len(r['stages'][0]['reports']),2)
        self.assertEqual(len(r['stages'][0]['cases']),2)

    def test_semantic_failure_blocks_dependent_stage_proof(self):
        p=self.profile();p['require_all_criteria']=False
        p['stages'][0]['command']=p['stages'][0]['command'].replace("status:'pass'","status:'fail'")
        p['stages'].append(dict(id='downstream',kind='build',command='echo success',required=True,timeout=2,depends_on=['unit']))
        r=self.execute(p)
        self.assertEqual(r['stages'][1]['status'],'fail')
        self.assertIn('依赖阶段未通过',r['stages'][1]['error'])

    def test_optional_dependency_with_mixed_report_cannot_prove_criterion(self):
        p=self.profile();p['stages'][0]['criteria']={}
        command=p['stages'][0]['command']
        for id,cases,deps,mapping in [('pre',"{id:'bad',status:'fail'}",[],{}),('dependent',"{id:'sum',status:'pass'},{id:'bad',status:'fail'}",['pre'],{'A1':['sum']})]:
            p['stages'].append(dict(id=id,kind='unit',required=False,timeout=3,command=command.replace("{id:'sum',status:'pass'}",cases).replace('report.json',id+'.json'),depends_on=deps,report={'format':'json','path':id+'.json'},criteria=mapping))
        with (self.root/'.gitignore').open('a') as f:f.write('pre.json\ndependent.json\n')
        result=self.execute(p)
        self.assertEqual(result['status'],'fail')
        self.assertEqual(result['criterion_evidence']['A1'][0]['status'],'unverified')
        self.assertFalse(result['stages'][2]['dependencies_valid'])
        self.assertTrue(result['stages'][2]['report_valid'])


if __name__ == '__main__':
    unittest.main()
