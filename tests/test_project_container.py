"""Project boundary regressions; no provider, Docker or production credentials."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tmh.platform import candidates, project_git
from tmh.platform.project_container import Engine, DockerError, specification
from tmh.platform.errors import ApiError
from tests import test_team_workspace as team_fixture
from tests import test_tenant_policy as policy_fixture


class ContainerBoundaryTest(unittest.TestCase):
    def test_model_job_never_inherits_host_environment_or_control_mounts(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'OPENAI_API_KEY':'fixture-host-secret'}):
            spec=specification('sha256:'+'a'*64,['codex','--version'],Path(folder).resolve(),10)
        serialized=json.dumps(spec)
        self.assertNotIn('fixture-host-secret',serialized)
        self.assertNotIn('docker.sock',serialized)
        self.assertTrue(spec['NetworkDisabled'])
        self.assertEqual(spec['HostConfig']['NetworkMode'],'none')
        self.assertEqual(spec['HostConfig']['CapDrop'],['ALL'])
        self.assertEqual(spec['Entrypoint'][:3],['python3','-u','-c'])
        self.assertIn('sys.stdin.buffer.read(1)',spec['Entrypoint'][3])
        self.assertTrue(spec['HostConfig']['ReadonlyRootfs'])
        self.assertTrue(spec['HostConfig']['Mounts'][0]['ReadOnly'])
        self.assertEqual(len(spec['HostConfig']['Mounts']),1)

    def test_mutable_image_unapproved_mount_and_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();link=root/'link';link.symlink_to(root,target_is_directory=True)
            for image,path,mounts in [('node:latest',root,()),('sha256:'+'a'*64,link,()),
                ('sha256:'+'a'*64,root,[(root,'/var/run/docker.sock')])]:
                with self.subTest(image=image,path=path,mounts=mounts),self.assertRaises(ValueError):
                    specification(image,['true'],path,10,mounts=mounts)

    def test_rootful_daemon_is_refused_before_allocating_container(self):
        engine=Engine();calls=[]
        def request(method,path,*args,**kwargs):
            calls.append((method,path));return {'SecurityOptions':['name=seccomp']}
        with patch.object(engine,'request',side_effect=request),self.assertRaises(DockerError):
            engine.run({},2)
        self.assertEqual(calls,[('GET','/info')])

    def test_metadata_allowlist_excludes_writes_shell_and_option_injection(self):
        for args in [('rev-parse','refs/webuddy/candidates/'+'b'*64),('rev-parse','--verify','--end-of-options','a'*40+'^{commit}'),
                ('rev-parse','main^{commit}'),('rev-parse','--verify','wb/JB-1^{commit}'),
                ('merge-base','--is-ancestor','a'*40,'refs/heads/main')]:
            self.assertTrue(project_git._allowed(args),args)
        for args in [('merge','--ff-only','a'*40),('update-ref','refs/heads/main','a'*40),
                ('rev-parse','--git-dir'),('rev-parse','--verify','--output=/tmp/x'),
                ('config','core.sshCommand','sh -c secret'),('diff','--ext-diff'),
                ('rev-parse','refs/webuddy/candidates/not-a-fingerprint'),('rev-parse','wb/../other'),
                ('rev-parse','refs/arbitrary/other')]:
            self.assertFalse(project_git._allowed(args),args)


class ManagedCandidateAuthorTest(unittest.TestCase):
    def test_read_projection_batches_but_verdict_checks_never_reuse_old_git_answer(self):
        fixture=policy_fixture.TenantPolicyTest('runTest');self.addCleanup(fixture.doCleanups);fixture.setUp()
        candidates.schema(fixture.store)
        (Path(fixture.projects['ALPHA']['root'])/'.git').mkdir()
        config=fixture.P.data_dir/'project-execution.json'
        config.write_text(json.dumps({'schema':1,'image':'sha256:'+'a'*64,'projects':['ALPHA']}));config.chmod(0o600)
        reference='refs/webuddy/candidates/'+'b'*64
        calls=[]
        class ChangingGit:
            def run(self,spec,seconds,output):
                command=json.loads(spec['Cmd'][1]);calls.append(command)
                sha=('%040x' % len(calls))+'\n'
                output((json.dumps({ref:[0,sha] for ref in json.loads(command[3])}) if command[:2]==['python3','-c'] else sha).encode())
                return {'reason':'exited','returncode':0,'cleanup':True}
        @project_git.scoped
        def dispatch_read(P,body,user):
            return [project_git.read(fixture.projects['ALPHA']['root'],('rev-parse',reference),text=True).stdout for _ in range(2)]
        @project_git.scoped
        def dispatch_action(P,body,user):
            return [project_git.read(fixture.projects['ALPHA']['root'],('rev-parse',reference),text=True).stdout for _ in range(2)]
        with patch('tmh.platform.project_git.Engine',ChangingGit):
            old=dispatch_read(fixture.P,{},'bob')
            self.assertEqual(len(calls),1)
            self.assertEqual(old[0],old[1])
            fresh=dispatch_action(fixture.P,{},'bob')
            self.assertEqual(len(calls),3)
            self.assertNotEqual(fresh[0],fresh[1])

    def test_non_git_project_keeps_materials_and_cannot_gain_candidate_permission(self):
        fixture=policy_fixture.TenantPolicyTest('runTest');self.addCleanup(fixture.doCleanups);fixture.setUp()
        team_fixture.team.schema(fixture.P)
        project=fixture.projects['ALPHA'];root=Path(project['root']);material=root/'materials.txt';material.write_text('original public material')
        config=fixture.P.data_dir/'project-execution.json'
        config.write_text(json.dumps({'schema':1,'image':'sha256:'+'a'*64,'projects':['ALPHA']}));config.chmod(0o600)
        self.assertFalse(project_git.available(fixture.P,project,'bob'))
        item=team_fixture.team.item(fixture.P,fixture.tickets['ALPHA'],'bob')
        self.assertFalse(item['repository_ready'])
        self.assertFalse(item['personal_decisions_available'])
        self.assertIn('代码仓库',item['repository_reason'])
        self.assertEqual(item['state'],'working')  # Materials/ordinary tasks remain usable.
        with self.assertRaises(ApiError):
            policy_fixture.policy.authorize(fixture.P,'POST','/api/team',{},
                {'action':'review','ticket':fixture.tickets['ALPHA']['key']},'bob')
        self.assertFalse((root/'.git').exists())
        self.assertEqual(material.read_text(),'original public material')

    def test_only_personal_verdicts_gain_project_metadata_permission(self):
        fixture=team_fixture.TeamWorkspaceTest('runTest');self.addCleanup(fixture.doCleanups);fixture.setUp()
        fixture.candidate()
        context=policy_fixture.Context(fixture.repo)
        context.people['bob']['project_grants']={'TEAM':'contributor'}
        context.people['reader']['project_grants']={'TEAM':'viewer'}
        fixture.P.tenant_context=context
        config=fixture.P.data_dir/'project-execution.json'
        config.write_text(json.dumps({'schema':1,'image':'sha256:'+'a'*64,'projects':['TEAM']}));config.chmod(0o600)
        policy=policy_fixture.policy
        for action in ('review','candidate_assess','business_accept'):
            body={'action':action,'ticket':fixture.ticket['key'],'candidate_id':fixture.cid}
            self.assertEqual(policy.authorize(fixture.P,'POST','/api/team',{},body,'bob')['allowed_project_keys'],['TEAM'])
            for user in ('reader','outsider'):
                with self.subTest(action=action,user=user),self.assertRaises(ApiError):
                    policy.authorize(fixture.P,'POST','/api/team',{},body,user)
        # 4e8b92c: isolated member verification and controlled merge use the personal project_git path.
        for action in ('candidate_verify','candidate_merge'):
            body={'action':action,'ticket':fixture.ticket['key'],'candidate_id':fixture.cid}
            self.assertEqual(policy.authorize(fixture.P,'POST','/api/team',{},body,'bob')['allowed_project_keys'],['TEAM'])
            for user in ('reader','outsider'):
                with self.subTest(action=action,user=user),self.assertRaises(ApiError):
                    policy.authorize(fixture.P,'POST','/api/team',{},body,user)
        for action in ('candidate_preview','candidate_submit'):
            with self.subTest(action=action),self.assertRaises(ApiError):
                policy.authorize(fixture.P,'POST','/api/team',{},
                    {'action':action,'ticket':fixture.ticket['key'],'candidate_id':fixture.cid},'bob')
        with self.assertRaises(ApiError):
            policy.authorize(fixture.P,'POST','/api/tickets/'+fixture.ticket['key']+'/accept',{}, {'result':'pass'},'bob')
        context.people['bob']['project_grants']={}
        with self.assertRaises(ApiError):
            policy.authorize(fixture.P,'POST','/api/team',{},
                {'action':'review','ticket':fixture.ticket['key'],'candidate_id':fixture.cid},'bob')

    def test_reassignment_never_allows_managed_initiator_to_sign_own_candidate(self):
        fixture=team_fixture.TeamWorkspaceTest('runTest');self.addCleanup(fixture.doCleanups);fixture.setUp()
        fixture.candidate();fixture.synthetic_checks()
        fixture.P.store.db.execute('UPDATE code_candidates SET agent=? WHERE id=?',('agent:member:alice',fixture.cid))
        fixture.P.store.db.commit()
        fixture.assign(owner='bob',reviewer='alice')
        current=candidates.view(fixture.P,fixture.cid)
        cases=[('candidate_assess',dict(verification_hash=current['verification_hash'],preview_hash=current['preview_hash'],
                    results=[{'id':'AC1','status':'pass','evidence':'synthetic only'}],note='fixture')),
               ('review',dict(evidence_hash=current['evidence_hash'],decision='reject',note='fixture')),
               ('business_accept',dict(evidence_hash=current['evidence_hash'],result='fail',note='fixture'))]
        for action,fields in cases:
            with self.subTest(action=action),self.assertRaisesRegex(ApiError,'实现|提交者'):
                fixture.action(action,'alice',candidate_id=fixture.cid,**fields)
        self.assertEqual(fixture.P.store.q('SELECT * FROM candidate_assessments'),[])
        self.assertEqual(fixture.P.store.q('SELECT * FROM candidate_decisions'),[])
        self.assertFalse(team_fixture.team.item(fixture.P,fixture.P.store.ticket(fixture.ticket['id']),'alice')['can_review'])
        self.assertFalse(candidates.implementation_author('agent:alice','alice'))


if __name__=='__main__': unittest.main()
