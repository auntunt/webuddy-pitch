import importlib.util,sys,unittest,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tmh.platform.fixloop import FixLoop
original=FixLoop.diagnose
def delayed(self,*args,**kwargs):
 time.sleep(1.3)
 return original(self,*args,**kwargs)
FixLoop.diagnose=delayed
spec=importlib.util.spec_from_file_location('handwork_fixture',Path(sys.argv[1]))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
suite=unittest.TestSuite([m.HandworkLifecycleTest('test_review_shares_time_spent_on_baseline_and_candidate_checks')])
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
