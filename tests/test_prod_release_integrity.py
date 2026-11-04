"""申请身份与真实部署结果：只用临时目录和本地合成脚本。"""
import json
import sys
import tempfile
import shutil
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from tests.test_prod_release import FakeP
from tmh.platform import prod_release as prod
from tmh.platform.errors import ApiError


class ReleaseIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.p = FakeP(self.root.name)
        self.addCleanup(shutil.rmtree, self.p.data_dir)
        with (self.p.data_dir / 'releases.jsonl').open('a') as f:
            f.write(json.dumps({'project': 'BID', 'version': 'v2', 'commit': self.p.commit[:7], 'tickets': []})+'\n')

    def request(self, version='v1.0.3'):
        return prod.request(self.p, 'BID', version, 'fde', checked='合成验证通过')

    def approve(self, r):
        # Avoid starting a background worker so every test joins its real work.
        with patch.object(prod.threading, 'Thread'):
            prod.decide(self.p, r['id'], True, 'lead')

    def script(self, body):
        script = Path(self.root.name) / 'deploy.py'
        script.write_text('import json, os\nfrom pathlib import Path\n' + body)
        config = {'cmd': f'"{sys.executable}" "{script}"', 'target': 'synthetic:production'}
        (self.p.data_dir / 'autoflow.json').write_text(json.dumps({'prod_deploy': {'BID': config}}))

    def run_deploy(self):
        r = self.request()
        self.approve(r)
        prod._deploy(self.p, r['id'], 'lead')
        return prod.get(self.p.data_dir, r['id'])

    def test_same_second_versions_and_reapplication_are_distinct(self):
        with patch.object(prod, '_now', return_value='2026-11-05 01:00:00'):
            a, b = self.request(), self.request('v2')
            self.assertNotEqual(a['id'], b['id'])
            prod.decide(self.p, a['id'], False, 'lead', '重新申请')
            c = self.request()
        self.assertEqual(len({a['id'], b['id'], c['id']}), 3)
        self.assertEqual(prod.requests(self.p.data_dir)[0]['id'], c['id'])
        self.assertEqual(prod.get(self.p.data_dir, b['id'])['state'], 'requested')
        self.assertEqual(prod.get(self.p.data_dir, a['id'])['state'], 'rejected')

    def test_history_collision_preserves_events_and_blocks_mutation(self):
        a = self.request()
        original = a['steps'][0]
        prod._append(self.p.data_dir, dict(original, version='v2', commit='def5678'))
        prod._append(self.p.data_dir, {'id': a['id'], 'project': 'BID', 'step': 'decide', 'state': 'approved'})
        path = prod._file(self.p.data_dir)
        before = path.read_bytes()
        rows = prod.requests(self.p.data_dir, 'BID')
        self.assertEqual({r['version'] for r in rows}, {'v1.0.3', 'v2'})
        self.assertTrue(all(r['ambiguous'] and len(r['steps']) == 3 for r in rows))
        for op in [lambda: prod.get(self.p.data_dir, a['id']), lambda: prod.decide(self.p, a['id'], True, 'lead'),
                   lambda: prod.deployed(self.p, a['id'], 'lead'), lambda: self.request('v2')]:
            with self.assertRaises(ApiError) as e:
                op()
            self.assertEqual(e.exception.code, 409)
        self.assertEqual(path.read_bytes(), before)

    def test_concurrent_approval_has_one_winner(self):
        r = self.request()
        def approve(_):
            try:
                return prod.decide(self.p, r['id'], True, 'lead')['state']
            except ApiError as e:
                return e.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(approve, range(2)))
        self.assertCountEqual(results, ['approved', 409])
        self.assertEqual(len(prod.get(self.p.data_dir, r['id'])['steps']), 2)

    def test_exit_zero_without_receipt_is_not_verified(self):
        self.script("print('deploy done')\n")
        r = self.run_deploy()
        self.assertEqual((r['state'], r['execution'], r['verification']), ('deployed', 'completed', 'unverified'))
        self.assertEqual(r['state_text'], '命令完成，部署未验证')
        self.assertNotEqual(self.p.store.events[-1][2], 'prod_deployed')

    def receipt_script(self, mutate=''):
        self.script("r=json.loads(os.environ['WEBUDDY_DEPLOY_CONTEXT'])\n"
                    "r['observed_commit']=r['commit']\n"
                    "r['checks']={k:{'result':'pass','evidence':'synthetic check '+k} for k in ['health','version','smoke']}\n"
                    + mutate + "\nPath(os.environ['WEBUDDY_DEPLOY_RECEIPT']).write_text(json.dumps(r))\n")

    def test_bound_receipt_pass_and_full_output(self):
        self.receipt_script("print('x'*5000)")
        r = self.run_deploy()
        self.assertEqual(r['verification'], 'pass')
        self.assertEqual(r['receipt']['request_id'], r['id'])
        self.assertEqual(r['receipt']['target'], 'synthetic:production')
        self.assertGreater(len(r['steps'][-1]['output']), 5000)
        self.assertEqual(r['state_text'], '部署验证通过')

    def test_failed_health_and_wrong_runtime_commit_are_not_success(self):
        for mutate in ["r['checks']['health']['result']='fail'", "r['observed_commit']='old'", "r['checks']['smoke']['result']='fail'"]:
            with self.subTest(mutate=mutate):
                self.receipt_script(mutate)
                r = self.request()
                self.approve(r)
                prod._deploy(self.p, r['id'], 'lead')
                self.assertEqual(prod.get(self.p.data_dir, r['id'])['verification'], 'fail')
                prod._file(self.p.data_dir).unlink()

    def test_wrong_binding_missing_evidence_and_stdout_claim_are_unverified(self):
        for mutate in ["r['nonce']='old'", "r['request_id']='other'", "r['target']='other'", "r['commit']='old'",
                       "r['command_sha256']='other'", "r['checks']['health']['evidence']=''", "del r['checks']['smoke']"]:
            with self.subTest(mutate=mutate):
                self.receipt_script(mutate)
                r = self.run_deploy()
                self.assertEqual(r['verification'], 'unverified')
                prod._file(self.p.data_dir).unlink()

    def test_historical_and_manual_records_are_not_automatically_verified(self):
        r = self.request()
        self.approve(r)
        r = prod.deployed(self.p, r['id'], 'ops', '人工核对')
        self.assertEqual((r['source'], r['verification']), ('manual', 'unverified'))
        self.assertIn('人工登记', r['state_text'])
        prod._append(self.p.data_dir, {'id':r['id'], 'project':'BID', 'step':'deployed', 'state':'deployed', 'by':'old', 'ts':prod._now()})
        self.assertNotEqual(prod.get(self.p.data_dir, r['id'])['verification'], 'pass')

    @unittest.skipUnless(shutil.which('node'), 'node is needed for the actual UI function')
    def test_version_ui_does_not_color_unverified_deployments_green(self):
        from tmh.platform.ui_work import WORK_JS as JS
        # Run the real rendering function with API-shaped records.
        source = JS[JS.index('function prodBox('):JS.index('function versionWire(')]
        js = "const h=x=>String(x);\n" + source + "\n" + """
for (const verification of ['pass','fail','unverified']) {
 const html=prodBox({version:'v1',prod:{id:'r',state:'deployed',verification,state_text:verification,steps:[]}},{});
 const expected=verification==='pass'?'ok':verification==='fail'?'bad':'warn';
 if(!html.includes('ev-tag '+expected)) throw Error(html);
}
"""
        result = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_changed_deploy_configuration_cannot_execute_after_approval(self):
        self.script("raise AssertionError('must not run')")
        r = self.request()
        self.approve(r)
        self.script("raise AssertionError('different command must not run')")
        # The contract freezes configuration, not arbitrary script file contents.
        config_path = self.p.data_dir / 'autoflow.json'
        config = json.loads(config_path.read_text())
        config['prod_deploy']['BID']['target'] = 'different:production'
        config_path.write_text(json.dumps(config))
        prod._deploy(self.p, r['id'], 'lead')
        r = prod.get(self.p.data_dir, r['id'])
        self.assertEqual(r['execution'], 'not_started')
        self.assertIn('批准时不同', r['verification_note'])

    def test_interrupted_deployment_does_not_rerun(self):
        self.script("raise AssertionError('must not run')")
        r = self.request()
        self.approve(r)
        prod._append(self.p.data_dir, {'id':r['id'], 'project':'BID', 'step':'deploy', 'state':'deploying',
                                     'source':'command', 'execution':'running', 'ts':prod._now()})
        prod._deploy(self.p, r['id'], 'lead')
        r = prod.get(self.p.data_dir, r['id'])
        self.assertIn('结果未知', r['state_text'])
        self.assertEqual(len(r['steps']), 3)
        with self.assertRaises(ApiError):
            self.request()


    def test_real_observed_git_sha_matches_historical_short_request(self):
        self.script("import subprocess\nr=json.loads(os.environ['WEBUDDY_DEPLOY_CONTEXT'])\n"
                    "r['observed_commit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()\n"
                    "r['checks']={k:{'result':'pass','evidence':'local fixture check'} for k in ['health','version','smoke']}\n"
                    "Path(os.environ['WEBUDDY_DEPLOY_RECEIPT']).write_text(json.dumps(r))\n")
        r=self.run_deploy()
        self.assertEqual(r['verification'],'pass')
        self.assertEqual(r['commit'],self.p.commit)
        path=Path(self.root.name)/'receipt.json'
        receipt={'commit':self.p.commit[:7],'observed_commit':self.p.commit,'checks':{k:{'result':'pass','evidence':'fixture'} for k in ('health','version','smoke')}}
        path.write_text(json.dumps(receipt))
        self.assertEqual(prod._receipt(path,{'commit':self.p.commit[:7]},self.root.name)[0],'pass')
        for observed in ('','HEAD','f'*40):
            receipt['observed_commit']=observed;path.write_text(json.dumps(receipt))
            self.assertEqual(prod._receipt(path,{'commit':self.p.commit[:7]},self.root.name)[0],'fail')


if __name__ == '__main__':
    unittest.main()
