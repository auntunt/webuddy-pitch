import sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tmh.platform.agents import Runner
from tests.test_platform import PlatformApiTest
original_decide=Runner._decide
original_call=PlatformApiTest.call

def delayed(self,rid,decision,author):
    result=original_decide(self,rid,decision,author)
    if author=='自动流转':
        time.sleep(.5)  # expose verify status while source guard is still held
    return result

def reported(self,method,path,body=None,**kwargs):
    result=original_call(self,method,path,body,**kwargs)
    if path.endswith('/accept') and body and body.get('note')=='还是不对':
        print('SECOND_REJECTION_RESPONSE',repr(result),flush=True)
    return result

with patch.object(Runner,'_decide',delayed),patch.object(PlatformApiTest,'call',reported):
    suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_platform.PlatformApiTest.test_acceptance_teaches_and_grows_the_eval_set')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
