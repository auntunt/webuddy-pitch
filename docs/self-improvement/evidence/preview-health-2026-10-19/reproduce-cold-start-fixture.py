import importlib.util,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
p=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("process_fixture",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original=m.ProcessControlTest.run_python
def cold(self,code,**kw):
 return original(self,"import time;time.sleep(.4)\n"+code,**kw)
m.ProcessControlTest.run_python=cold
suite=unittest.TestSuite([m.ProcessControlTest("test_blocked_stdin_and_no_newline_output_do_not_block_deadline")])
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
