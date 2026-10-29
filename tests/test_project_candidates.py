import json
import unittest
from unittest.mock import patch

from tmh import evidence
from tmh.platform import candidates, project_candidates, signoff, team
from tmh.platform.agent_api import _requirement
from tmh.platform.project_authority import capture
from tmh.platform.project_mcp import BoundJob
from tests import test_project_authority as fixture_module


class ProjectCandidateRegistrationTest(unittest.TestCase):
    def setUp(self):
        fixture=fixture_module.ProjectAuthorityTest('runTest');fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fixture=fixture;self.P=fixture.P;self.store=self.P.store;self.project=fixture.project
        self.ticket=self.store.ticket('SAME-1')
        self.store.x('UPDATE tickets SET links=? WHERE id=?',(json.dumps({'hold':True}),self.ticket['id']))
        self.ticket=self.store.ticket(self.ticket['id'])
        self.authority=capture(self.P,'alice',self.project)
        self.job=BoundJob('alice','SAME',fixture.workspace,self.authority.image)
        self.run=self.store.create_run(self.project['id'],self.ticket['id'],'codex','fix','alice','synthetic prompt',expected_root=self.project['root'])
        self.store.update_run(self.run['id'],status='running')
        self.folder=fixture.workspace.parent/'candidate';self.folder.mkdir();(self.folder/'change.patch').write_text('synthetic patch')
        self.artifact={'artifact_dir':str(self.folder),'base_commit':'b'*40,'commit':'c'*40,
                       'bundle_sha256':'d'*64,'patch_sha256':'e'*64}
        self.proposal={'candidate':self.artifact}

    def bind(self):
        ticket=self.store.ticket(self.ticket['id'])
        return {'requirement_hash':_requirement(ticket,self.store),
                'configuration_hash':candidates.configuration(self.P,self.project),
                'assignment':{k:v for k,v in team.assignment(self.P,ticket).items() if k in ('assignee','reviewer','revision')}}

    def test_confirmed_full_criteria_registers_original_author_without_human_decision(self):
        text='full requirement '+('x'*400)
        evidence.append(signoff.epath(self.P.data_dir,self.ticket['key']),'intake','alice',
                        {'ac':[{'id':'A1','text':text,'check':'Verify exact result','open':False}]})
        binding=self.bind()
        with patch.object(project_candidates.project_artifact,'install',side_effect=lambda image,source,folder,artifact,fp,**kw:{'ref':'refs/webuddy/candidates/'+fp,'cleanup':True}) as install:
            cid=project_candidates.register(self.P,self.run['id'],self.authority,self.job,binding,self.proposal,'synthetic result',lambda commit:True)
        install.assert_called_once()
        row=self.store.one('SELECT * FROM code_candidates WHERE id=?',(cid,))
        self.assertEqual(row['agent'],'alice');self.assertEqual(row['run_id'],self.run['id'])
        self.assertEqual(json.loads(row['criteria'])[0]['text'],text)
        self.assertEqual(self.store.run(self.run['id'])['status'],'done')
        self.assertEqual(self.store.q('SELECT * FROM candidate_decisions'),[])
        self.assertEqual([x for x in self.store.events(self.ticket['id']) if x['kind']=='accept'],[])

    def test_missing_or_unconfirmed_criteria_never_installs_candidate(self):
        binding=self.bind()
        with patch.object(project_candidates.project_artifact,'install') as install:
            self.assertIsNone(project_candidates.register(self.P,self.run['id'],self.authority,self.job,binding,self.proposal,'proposal',lambda commit:True))
            install.assert_not_called()
        self.assertEqual(self.store.run(self.run['id'])['status'],'running')

    def test_revocation_before_install_refuses_without_mutation(self):
        evidence.append(signoff.epath(self.P.data_dir,self.ticket['key']),'intake','alice',
                        {'ac':[{'id':'A1','text':'full criterion','check':'verify','open':False}]})
        binding=self.bind()
        self.fixture.gateway.change('project_revoke',tenant=self.fixture.gateway.a,user='alice',project_id=1)
        with patch.object(project_candidates.project_artifact,'install') as install:
            with self.assertRaises(ValueError):
                project_candidates.register(self.P,self.run['id'],self.authority,self.job,binding,self.proposal,'proposal',lambda commit:True)
            install.assert_not_called()
        self.assertEqual(self.store.run(self.run['id'])['status'],'running')

    def test_broken_evidence_chain_never_supplies_criteria(self):
        path=signoff.epath(self.P.data_dir,self.ticket['key'])
        evidence.append(path,'intake','alice',{'ac':[{'id':'A1','text':'original','check':'verify','open':False}]})
        path.write_text(path.read_text().replace('original','tampered'))
        with patch.object(project_candidates.project_artifact,'install') as install:
            self.assertIsNone(project_candidates.register(self.P,self.run['id'],self.authority,self.job,self.bind(),self.proposal,'proposal',lambda commit:True))
            install.assert_not_called()

    def test_source_changes_after_git_install_preserves_uncertain_receipt_without_registration(self):
        evidence.append(signoff.epath(self.P.data_dir,self.ticket['key']),'intake','alice',
                        {'ac':[{'id':'A1','text':'criterion','check':'verify','open':False}]})
        binding=self.bind();checks=iter((True,False))
        with patch.object(project_candidates.project_artifact,'install',side_effect=lambda image,source,folder,artifact,fp,**kw:{'ref':'refs/webuddy/candidates/'+fp,'cleanup':True}):
            with self.assertRaises(ValueError):
                project_candidates.register(self.P,self.run['id'],self.authority,self.job,binding,self.proposal,'proposal',lambda commit:next(checks))
        self.assertEqual(json.loads((self.folder/'install.json').read_text())['state'],'prepared')
        self.assertEqual(self.store.q('SELECT * FROM code_candidates'),[])
        self.assertEqual(self.store.run(self.run['id'])['status'],'running')


if __name__=='__main__':unittest.main()
