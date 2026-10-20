import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tests import test_recheck_crash_independent as checks
hold=r'''
import time
from tmh.platform.agents import Runner
_original_lifecycle=Runner._save_lifecycle
def delayed_lifecycle(self,rid):
    if self.data_dir.name=='verification-operations' and self.controls.get(rid,{}).get('finished'):
        time.sleep(.5)
    return _original_lifecycle(self,rid)
Runner._save_lifecycle=delayed_lifecycle
'''
with patch.object(checks,'SERVICE',checks.SERVICE.replace('httpd=ThreadingHTTPServer',hold+'\nhttpd=ThreadingHTTPServer')):
    suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_recheck_crash_independent.RecheckCrashIndependentTest.test_multicommand_recheck_holds_lease_between_real_commands_across_instances')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
