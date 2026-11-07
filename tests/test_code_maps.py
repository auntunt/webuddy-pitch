import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tests import test_external_candidates as fixtures
from tmh import graph
from tmh.platform import code_maps
from tmh.platform.errors import ApiError

class SavedMapsTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ExternalCandidateTest('runTest');self.addCleanup(self.f.doCleanups);self.f.setUp()
        self.P=self.f.P;self.p=self.f.p
        (self.f.repo/'refund.py').write_text('def refund(amount):\n    return amount\n')
        graph.build(self.f.repo)
        self.args={'project':'EXT','question':'refund','request_id':'map-once','limit':30}
    def test_source_stays_fixed_and_project_boundary_is_not_map_id(self):
        saved=code_maps.create(self.P,self.p,'fixture',self.args)
        self.assertTrue(saved['nodes'])
        node=next(n for n in saved['nodes'] if n['name']=='refund')
        (self.f.repo/'refund.py').write_text('def renamed(amount):\n    return 0\n');graph.build(self.f.repo)
        result=code_maps.execute(self.P,self.p,'fixture','map_get',dict(map_id=saved['id'],node_id=node['id']))
        self.assertIn('return amount',result['text']);self.assertNotIn('return 0',result['text'])
        with self.assertRaises(ApiError):code_maps.load(self.P.store,dict(self.p,id=999),saved['id'])
        with self.assertRaises(ApiError):code_maps.create(self.P,self.p,'fixture',dict(self.args,request_id='expand',from_map=saved['id']))
        self.assertEqual(saved,code_maps.create(self.P,self.p,'fixture',self.args))
    def test_reads_do_not_write_or_invent_edges(self):
        saved=code_maps.create(self.P,self.p,'fixture',self.args)
        before=self.P.store.db.total_changes
        current=code_maps.execute(self.P,self.p,'fixture','map_get',{'map_id':saved['id']})
        self.assertEqual(current.pop('linked_plans'),[])
        self.assertEqual(current,saved)
        self.assertEqual(before,self.P.store.db.total_changes)
        self.assertTrue(all(e['kind'] in code_maps.RELATIONS for e in saved['relations']))

    def test_actual_prompt_and_run_receipt_match_selection_and_stale_omission(self):
        from tmh.platform import agents,tool_read
        saved=code_maps.create(self.P,self.p,'fixture',self.args)
        node=next(n for n in saved['nodes'] if n['name']=='refund')
        refs=[{'map_id':saved['id'],'revision':1,'nodes':[node['id']]}]
        self.P.store.update_ticket(self.f.ticket['id'],'fixture',links={'map_refs':refs})
        ticket=self.P.store.ticket(self.f.ticket['id'])
        agents._CTX_META.meta=[]
        prompt=agents.build_prompt(self.P.store,self.p,ticket,'analyze')
        receipt=next(m for m in agents.take_context_meta() if m['mode']=='code_maps')
        self.assertEqual(receipt['maps'][0]['injected'],[node['id']]);self.assertIn(saved['id'],prompt)
        run=self.P.store.create_run(self.p['id'],ticket['id'],'fixture-no-model','analyze','fixture',prompt)
        agents._record_context(self.P.store,self.P.data_dir,run['id'],[receipt])
        actual=tool_read.run_history(self.P,run)['context_receipt']['recorded'][0]
        self.assertEqual(actual,receipt)
        (self.f.repo/'refund.py').write_text('def refund(amount):\n    return 0\n')
        agents._CTX_META.meta=[]
        prompt=agents.build_prompt(self.P.store,self.p,ticket,'analyze')
        current=next(m for m in agents.take_context_meta() if m['mode']=='code_maps')
        self.assertEqual(current['maps'][0]['injected'],[])
        self.assertEqual(current['maps'][0]['applicability'],'stale')
        self.assertIn('未注入旧节点为当前事实',prompt)

    def test_local_mcp_reads_index_source_not_current_checkout(self):
        import json,subprocess,sys
        g=graph.Graph(self.f.repo)
        try:node=next(n for n in g.nodes('fn') if n['name']=='refund')
        finally:g.db.close()
        (self.f.repo/'refund.py').write_text('def renamed():\n    return 0\n')
        request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'source','arguments':{'node':node['id']}}}
        result=subprocess.run([sys.executable,'-B','-m','tmh','mcp','--repo',str(self.f.repo)],input=json.dumps(request)+'\n',capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        packet=json.loads(result.stdout)['result'];self.assertFalse(packet['isError'],packet)
        source=json.loads(packet['content'][0]['text'])
        self.assertIn('return amount',source['text']);self.assertEqual(source['provenance']['index_status'],'stale')

    def test_draft_handoff_survives_normalization_and_rejects_foreign_map(self):
        from tmh.platform import reform,reform_api
        from types import SimpleNamespace
        saved=code_maps.create(self.P,self.p,'fixture',self.args)
        refs=[{'map_id':saved['id'],'revision':1,'nodes':[saved['nodes'][0]['id']]}]
        atlas={'built':'fixture','domains':[{'id':'one','title':'One','tables':0}]}
        with patch.object(self.P.kb,'atlas',return_value=atlas):
            plan=reform.create(self.P.data_dir,'EXT',atlas,dict(title='Refund scenario',goal='Preserve refund'),'fixture')
            result=reform_api.execute(self.P,SimpleNamespace(user='fixture'),'fixture','reform_update',dict(project='EXT',plan_id=plan['id'],expected_revision=1,request_id='attach-map',reason='Scope reference',changes={'map_refs':refs}))
            self.assertEqual(result['map_refs'],refs)
            current=code_maps.execute(self.P,self.p,'fixture','map_get',{'map_id':saved['id']})
            self.assertEqual(current['linked_plans'][0]['plan_id'],plan['id'])
            with self.assertRaises(ApiError):code_maps.validate_refs(self.P.store,dict(self.p,id=999),refs)

    def test_registered_executor_actually_receives_selected_map(self):
        import json,sys,time
        from tmh.platform import agents
        self.f.git('add','refund.py');self.f.git('commit','-m','fixed refund source')
        graph.build(self.f.repo)
        saved=code_maps.create(self.P,self.p,'fixture',dict(self.args,request_id='actual-executor-map'))
        node=next(n for n in saved['nodes'] if n['name']=='refund')
        self.P.store.update_ticket(self.f.ticket['id'],'fixture',links={'map_refs':[{'map_id':saved['id'],'revision':1,'nodes':[node['id']]}]})
        script=self.P.data_dir/'read-map-prompt.py'
        script.write_text("from pathlib import Path\nimport sys\np=Path(sys.argv[1]).read_text()\nassert sys.argv[2] in p\nprint('fixture-executor-received-map:'+sys.argv[2])\n")
        (self.P.data_dir/'agents.json').write_text(json.dumps({'map-reader':{'timeout':15,'cmd':[sys.executable,str(script),'{prompt_file}',saved['id']]}}))
        run=self.P.runner.start(self.p,self.P.store.ticket(self.f.ticket['id']),'map-reader','analyze','fixture')
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            current=self.P.store.run(run['id'])
            if current['status'] not in ('queued','running'):break
            time.sleep(.1)
        self.assertEqual(current['status'],'done',current.get('output'))
        self.assertIn('fixture-executor-received-map:'+saved['id'],current['output'])
        receipt=json.loads((self.P.data_dir/'runs'/str(run['id'])/'context.json').read_text())
        item=next(m for m in receipt if m['mode']=='code_maps')
        self.assertEqual(item['maps'][0]['injected'],[node['id']])

    def test_scenario_originals_report_keeps_independent_failure_and_map_reference(self):
        import json,sys
        from tests import test_project_tests as checks
        from tmh.platform import reform,report_exports
        # Independent policy is fixed before either implementation runs.
        with (self.f.repo/'.gitignore').open('a') as out:out.write('report.json\nevidence/\nplan.json\n')
        (self.f.repo/'refund-check.py').write_text("import json,sys\nfrom refund import refund\nexpected=1250\nactual=refund(1250)\npassed=actual==expected\nopen('report.json','w').write(json.dumps({'cases':[{'id':'sum','status':'pass' if passed else 'fail','input':1250,'expected':expected,'actual':actual}]}))\nsys.exit(0 if passed else 1)\n")
        self.f.git('add','.');self.f.git('commit','-m','independent refund fixture')
        source=self.f.git('rev-parse','HEAD')
        graph.build(self.f.repo)
        saved=code_maps.create(self.P,self.p,'fixture',dict(self.args,request_id='scenario-map'))
        refs=[{'map_id':saved['id'],'revision':1,'nodes':[next(n['id'] for n in saved['nodes'] if n['name']=='refund')]}]
        atlas={'built':'fixture','domains':[{'id':'one','title':'One','tables':0}]}
        plan=reform.create(self.P.data_dir,'EXT',atlas,dict(title='Synthetic refund',goal='Refund exactly 1250 cents',source_version=source,target_environment='隔离Python进程与本地项目测试适配器',criteria=['输入1250分时原额退回；独立规则fixture://independent-refund-policy-v1'],map_refs=refs,scenario={'rules':['合成独立规则：退款保持1250分'],'expectation_sources':['fixture://independent-refund-policy-v1'],'sources':[{'id':'policy','kind':'policy','reference':'fixture://independent-refund-policy','version':'v1'}]}),'fixture')
        with reform._transaction(self.P.data_dir,self.P.store) as db:
            plans=reform._load(self.P.data_dir,'EXT',db);plans[0]['items'][0]['ticket']=self.f.ticket['key'];reform._save(self.P.data_dir,'EXT',plans,db)
        self.P.store.update_ticket(self.f.ticket['id'],'fixture',title='合成退款规则验证',body='输入1250分时必须原额退回；此预期在实现执行前固定。',links={'reform':{'plan':plan['id']},'map_refs':refs})
        helper=checks.ProjectTests('runTest');helper.root=self.f.repo
        for body,want in [('0','failed'),('amount','passed')]:
            (self.f.repo/'refund.py').write_text('def refund(amount):\n    return '+body+'\n')
            profile=helper.profile('"'+sys.executable+'" -B refund-check.py')
            result=helper.execute(profile,[{'id':'A1','text':'退款保持1250分','source':'fixture://independent-refund-policy-v1'}])
            self.assertEqual(result['verification_state'],want,result)
            run=self.P.store.create_run(self.p['id'],self.f.ticket['id'],'fixture-real-project-tests','verify','fixture','Independent 1250 cents; '+want)
            self.P.store.update_run(run['id'],status='failed' if want=='failed' else 'done',exit_code=1 if want=='failed' else 0)
            folder=self.P.data_dir/'runs'/str(run['id']);folder.mkdir(parents=True,exist_ok=True)
            (folder/'verify.json').write_text(json.dumps(result))
            import shutil
            shutil.copytree(self.f.repo/'evidence',folder/'project-tests'/'fixture',dirs_exist_ok=True)
        plan=reform.plan(self.P.data_dir,'EXT',plan['id'])
        manifest=report_exports.create(self.P,self.p,plan,'fixture',dict(project='EXT',plan_id=plan['id'],expected_revision=plan['revision'],request_id='scenario-export'))
        from tmh.report_download import download
        from types import SimpleNamespace
        client=SimpleNamespace(call=lambda op,a:report_exports.read(self.P,self.p,plan,a))
        result=download(client,'EXT',plan['id'],manifest['export_id'],self.P.data_dir/'delivery')
        reading=(Path(result['directory'])/'report.md').read_text()
        self.assertIn(saved['id'],reading);self.assertIn('失败',reading);self.assertIn('1250',reading)
        original=json.loads((Path(result['directory'])/(self.f.ticket['key']+'.json')).read_text())
        self.assertEqual(len(original['runs']),2)
        self.assertIsNone(original['ready_to_merge'])
        import os,shutil
        if os.environ.get('WEBUDDY_MAP_EVIDENCE_DIR'):
            target=Path(os.environ['WEBUDDY_MAP_EVIDENCE_DIR']);target.mkdir(parents=True,exist_ok=True)
            shutil.copytree(result['directory'],target/manifest['export_id'],dirs_exist_ok=True)
            (target/'saved-map.json').write_text(json.dumps(code_maps.load(self.P.store,self.p,saved['id']),ensure_ascii=False,indent=2))
            shutil.copytree(self.P.data_dir/'runs',target/'original-runs',dirs_exist_ok=True)


    def test_knowledge_is_frozen_material_not_automatic_adoption(self):
        from tmh import kb
        page=kb.page_path(self.f.repo,'index');page.parent.mkdir(parents=True,exist_ok=True)
        page.write_text('# Refund policy\n\n独立旧资料1250分\n')
        kb.save_registry(self.f.repo,{'index':{'title':'refund','status':'待确认'}})
        saved=code_maps.create(self.P,self.p,'fixture',dict(self.args,request_id='knowledge-map'))
        self.assertTrue(saved['knowledge_references'])
        page.write_text('# Refund policy\n\nchanged policy\n')
        source=code_maps.execute(self.P,self.p,'fixture','map_get',dict(map_id=saved['id'],knowledge_id='index'))
        self.assertIn('1250',source['text']);self.assertNotIn('changed policy',source['text'])
        self.assertIn('历史知识引用',source['node']['authority'])
        self.assertTrue(source['node']['source_version'].startswith('knowledge:'))

    def test_unknown_response_lookup_does_not_regenerate_map(self):
        saved=code_maps.create(self.P,self.p,'fixture',self.args)
        graph.graph_path(self.f.repo).unlink()
        result=code_maps.execute(self.P,self.p,'fixture','maps_list',dict(project='EXT',request_id=self.args['request_id']))
        self.assertEqual([m['id'] for m in result['items']],[saved['id']])
        self.assertEqual(code_maps.create(self.P,self.p,'fixture',self.args),saved)
        other=code_maps.execute(self.P,self.p,'other','maps_list',dict(project='EXT',request_id=self.args['request_id']))
        self.assertEqual(other['items'],[])
