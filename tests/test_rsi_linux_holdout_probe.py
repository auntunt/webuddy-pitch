import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/rsi/linux_holdout_probe.py'
spec=importlib.util.spec_from_file_location('linux_holdout_probe',SCRIPT)
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


def declared_report():
    # Only structural data. Actual kernel checks are executed separately on Linux.
    return {'probe_passed':True,'returncode':0,'reason':'exited','fixture_root':'/tmp/fixture','owner_uid':1000,'test_uid':65534,
            'checks':dict.fromkeys(M.CHECKS,True),'oracle_in_output':False,'production_qualified':False,'dedicated_trial_identity':False,'provider_calls':0,
            'cleanup':{'complete':True,'reaped':True,'output_complete':True,'remaining_group':False,'errors':[]}}


class LinuxProbeContractTests(unittest.TestCase):
    def test_unsupported_platform_never_calls_sudo_or_creates_fixture(self):
        with patch.object(M.platform,'system',return_value='Darwin'),patch.object(M.subprocess,'run',side_effect=AssertionError('must not execute')),patch.object(M.tempfile,'mkdtemp',side_effect=AssertionError('must not write')):
            result=M.run(Path('/does-not-exist'))
        self.assertEqual(result['status'],'unsupported')
        self.assertIs(result['production_qualified'],False)
        self.assertEqual(result['provider_calls'],0)

    def test_complete_declaration_is_only_a_probe(self):
        result=M.classify(declared_report(),Path('/tmp/fixture'),1000)
        self.assertEqual(result['status'],'passed')
        self.assertIs(result['production_qualified'],False)
        self.assertIs(result['dedicated_trial_identity'],False)

    def test_missing_or_failing_negative_control_cannot_pass(self):
        for key in M.CHECKS:
            for mode in ['missing','false','integer']:
                v=declared_report()
                if mode=='missing':v['checks'].pop(key)
                else:v['checks'][key]=False if mode=='false' else 1
                with self.subTest(key=key,mode=mode),self.assertRaises(ValueError):M.classify(v,Path('/tmp/fixture'),1000)

    def test_wrong_identity_or_claimed_production_qualification_rejected(self):
        for key,value in [('owner_uid',0),('test_uid',1000),('fixture_root','/etc'),('production_qualified',True),('dedicated_trial_identity',True),('provider_calls',1),('provider_calls',False),('oracle_in_output',True),('returncode',True)]:
            v=declared_report();v[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):M.classify(v,Path('/tmp/fixture'),1000)

    def test_cleanup_is_required_and_failure_remains_failure(self):
        for key,value in [('complete',False),('reaped',False),('output_complete',False),('remaining_group',True),('errors',['failure'])]:
            v=declared_report();v['cleanup'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):M.classify(v,Path('/tmp/fixture'),1000)
        v=declared_report();v.update(probe_passed=False,returncode=1,checks={})
        self.assertEqual(M.classify(v,Path('/tmp/fixture'),1000)['status'],'failed')
