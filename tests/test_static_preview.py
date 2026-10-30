"""Private static previews use real HTTP, scoped grants and immutable bytes."""
import hashlib
import json
import time
from pathlib import Path
import unittest
from unittest.mock import patch

from tmh.platform import static_preview, candidates, project_verify, fixloop, tenant_policy
from tmh.platform.store import Store
from tests import test_tenant_gateway as gateway_fixture
from tests import test_project_verify as verify_fixture


class StaticPreviewGatewayTest(unittest.TestCase):
    def setUp(self):
        f=gateway_fixture.TenantGatewayTest('runTest');f.setUp();self.addCleanup(f.doCleanups)
        self.f=f;self.reg=f.reg;self.tenant=f.a
        self.data=Path(self.reg.one('SELECT path FROM tenants WHERE id=?',(self.tenant,))['path'])
        profile=self.data/'static-preview.json'
        profile.write_text(json.dumps({'schema':1,'projects':{'SAME':{'image':'sha256:'+'a'*64,'output':'frontend/dist','auto':True}}}));profile.chmod(0o600)
        st=Store(self.data/'platform.db');self.addCleanup(st.db.close);self.store=st
        run=st.create_run(1,1,'codex','fix','alice','synthetic fixed source')
        st.update_run(run['id'],status='done',diff='fixed patch');candidates.schema(st)
        st.x('''INSERT INTO code_candidates(ticket_id,run_id,agent,base_commit,commit_sha,
            requirement_hash,configuration_hash,criteria,summary,fingerprint,ref,artifact_dir,created)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(1,run['id'],'alice','b'*40,'c'*40,'d'*64,'e'*64,'[]','synthetic','f'*64,'refs/webuddy/candidates/'+'f'*64,'fixture','now'))
        row=st.one('SELECT * FROM code_candidates WHERE run_id=?',(run['id'],));self.row=row
        folder=self.data/'verification-operations'/'runs'/'fixture';folder.mkdir(parents=True)
        self.site=folder/'static-site';(self.site/'assets').mkdir(parents=True)
        self.files={'index.html':b'<html><script type="module" src="./assets/app.js"></script><h1>Candidate</h1></html>',
                    'assets/app.js':b'document.body.dataset.ready="true";'}
        manifest={}
        for name,raw in self.files.items():
            (self.site/name).write_bytes(raw);manifest[name]={'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        digest=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        artifact={'commit':row['commit_sha'],'digest':digest,'files':manifest}
        verification={'check':'pass','verification_current':True,'checked_commit':row['commit_sha'],'checked_base':row['base_commit'],
                      'static_preview':static_preview.publish(self.data,folder,row,artifact)}
        self.verify=self.data/'runs'/str(run['id'])/'verify.json';self.verify.parent.mkdir(parents=True,exist_ok=True);self.verify.write_text(json.dumps(verification))
        self.enter='/t/'+self.tenant+'/static-preview/'+str(row['id'])+'/enter'

    def grant(self,user='alice'):
        code,headers,body=self.f.request('GET',self.enter,user)
        self.assertEqual(code,303,body);return headers['Location']

    def test_private_entry_and_cookie_free_modules_are_sandboxed(self):
        self.assertEqual(self.f.request('GET',self.enter)[0],401)
        self.assertEqual(self.f.request('GET',self.enter,'outsider')[0],403)
        url=self.grant()
        code,headers,body=self.f.request('GET',url,headers={'Origin':'null'})
        self.assertEqual(code,200,body);self.assertIn('Candidate',body)
        self.assertIn('sandbox allow-scripts',headers['Content-Security-Policy'])
        self.assertNotIn('allow-same-origin',headers['Content-Security-Policy'])
        self.assertIn("connect-src 'none'",headers['Content-Security-Policy'])
        self.assertNotIn('Set-Cookie',headers);self.assertEqual(headers['Referrer-Policy'],'no-referrer')
        code,headers,body=self.f.request('GET',url+'assets/app.js',headers={'Origin':'null'})
        self.assertEqual(code,200,body);self.assertEqual(headers['Access-Control-Allow-Origin'],'*')
        self.assertNotIn('Access-Control-Allow-Credentials',headers)
        self.assertEqual(self.f.request('GET','/t/'+self.tenant+'/api/projects',headers={'Origin':'null'})[0],401)
        self.assertEqual(self.f.request('POST','/t/'+self.tenant+'/api/projects','alice',body={},headers={'Origin':'null','X-TMH':'1'})[0],403)

    def test_grants_are_tenant_candidate_personal_and_revocable(self):
        url=self.grant()
        self.assertEqual(self.f.request('GET',url.replace('/t/'+self.tenant+'/', '/t/'+self.f.b+'/'))[0],403)
        self.f.change('project_revoke',tenant=self.tenant,user='alice',project_id=1)
        self.assertEqual(self.f.request('GET',url)[0],403)
        self.f.change('project_grant',tenant=self.tenant,user='alice',project_id=1,role='contributor')
        self.assertEqual(self.f.request('GET',url)[0],403)
        self.assertEqual(self.f.request('GET',self.grant())[0],200)

    def test_expired_tampered_and_path_escape_grants_fail(self):
        url=self.grant();part=url.split('/static-preview/')[1].split('/',1)[1].rstrip('/')
        self.assertEqual(self.f.request('GET',url.replace(part,part[:-1]+('a' if part[-1]!='a' else 'b')))[0],403)
        with patch.object(static_preview.time,'time',return_value=time.time()+7200):
            self.assertEqual(self.f.request('GET',url)[0],403)
        self.assertEqual(self.f.request('GET',url+'%2e%2e/session.key')[0],400)
        self.assertEqual(self.f.request('GET',url+'missing.js')[0],404)
        self.assertEqual(self.f.request('GET',url+'assets/app.js')[0],200)

    def test_edited_artifact_or_new_verification_cannot_reuse_preview(self):
        url=self.grant();(self.site/'assets/app.js').write_text('changed')
        self.assertEqual(self.f.request('GET',url+'assets/app.js')[0],409)
        v=json.loads(self.verify.read_text());v['verification_current']=False;self.verify.write_text(json.dumps(v))
        self.assertEqual(self.f.request('GET',url)[0],409)

    def test_links_and_disabled_profile_are_denied(self):
        url=self.grant();p=self.site/'assets/app.js';p.unlink();p.symlink_to(self.site/'index.html')
        self.assertEqual(self.f.request('GET',url+'assets/app.js')[0],409)
        (self.data/'static-preview.json').unlink()
        self.assertEqual(self.f.request('GET',url)[0],403)


class StaticPreviewVerificationTest(unittest.TestCase):
    def setUp(self):
        f=verify_fixture.ProjectVerifyTest('runTest');f.setUp();self.addCleanup(f.doCleanups);self.f=f
        path=f.P.data_dir/'static-preview.json'
        path.write_text(json.dumps({'schema':1,'projects':{'SAME':{'image':'sha256:'+'9'*64,'output':'frontend/dist','auto':True}}}));path.chmod(0o600)

    def test_explicit_static_profile_uses_test_then_final_build_and_separate_image(self):
        images=[];original=self.f.volume
        class Volume(original):
            def __init__(self,engine,image,*args):images.append(image);super().__init__(engine,image,*args)
        self.f.volume=Volume
        artifact={'digest':'d'*64,'commit':'c'*40,'files':{}}
        with patch.object(static_preview,'export',return_value=artifact) as export:
            operation=self.f.run_synthetic()
        self.assertEqual(operation['status'],'done',operation)
        self.assertEqual(images,['sha256:'+'9'*64]*2)
        commands,_=project_verify.commands(self.f.P,self.f.fixture.project)
        self.assertEqual([x[0] for x in commands],['test','build'])
        execute=[s for s in self.f.specs if s['command'][0]!="python3"]
        self.assertTrue(all(s['HostConfig']['NetworkMode']=='none' and s['NetworkDisabled'] is False and not s['HostConfig'].get('PortBindings') for s in execute))
        export.assert_called_once()
        v=fixloop.verified(self.f.P.data_dir,self.f.fixture.run['id'])
        self.assertEqual(v['static_preview']['digest'],'d'*64)
        self.assertEqual(self.f.store.q('SELECT * FROM candidate_assessments'),[])
        self.assertEqual(self.f.store.q('SELECT * FROM candidate_decisions'),[])

    def test_failed_build_never_publishes_preview(self):
        self.f.exit_codes=[0,0,0,1]
        with patch.object(static_preview,'export') as export:
            op=self.f.run_synthetic()
        self.assertEqual(op['status'],'failed');export.assert_not_called()
        self.assertNotIn('static_preview',fixloop.verified(self.f.P.data_dir,self.f.fixture.run['id']))

    def test_automatic_verification_requires_explicit_project_opt_in(self):
        with patch.object(project_verify,'start',return_value={'operation':7}) as start:
            self.assertEqual(static_preview.auto_verify(self.f.P,'alice',self.f.cid),{'operation':7})
            start.assert_called_once_with(self.f.P,'alice',self.f.cid)
            path=self.f.P.data_dir/'static-preview.json'
            conf=json.loads(path.read_text());conf['projects']['SAME']['auto']=False;path.write_text(json.dumps(conf))
            self.assertIsNone(static_preview.auto_verify(self.f.P,'alice',self.f.cid))
            path.unlink()
            self.assertIsNone(static_preview.auto_verify(self.f.P,'alice',self.f.cid))
            self.assertEqual(start.call_count,1)
        self.assertEqual(self.f.store.q('SELECT * FROM candidate_assessments'),[])
        self.assertEqual(self.f.store.q('SELECT * FROM candidate_decisions'),[])

    def test_personal_preview_action_only_opens_configured_project(self):
        from tmh.platform.errors import ApiError
        body={'action':'candidate_preview','candidate_id':self.f.cid,'ticket':self.f.fixture.ticket['key']}
        tenant_policy.authorize(self.f.P,'POST','/api/team',{},body,'alice')
        with self.assertRaises(ApiError):
            tenant_policy.authorize(self.f.P,'POST','/api/team',{},body,'outsider')
        (self.f.P.data_dir/'static-preview.json').unlink()
        with self.assertRaisesRegex(ApiError,'尚未接入'):
            tenant_policy.authorize(self.f.P,'POST','/api/team',{},body,'alice')

    def test_unsafe_operator_config_is_refused(self):
        path=self.f.P.data_dir/'static-preview.json';path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'权限'):project_verify.commands(self.f.P,self.f.fixture.project)


if __name__=='__main__':unittest.main()
