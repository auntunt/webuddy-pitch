"""Actual SQLite/file-lock ordering and lease across finite admission commit."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import unittest

from tests import test_rsi_finite_execution as F
from tmh.platform import learn


@unittest.skipUnless(os.name=='posix','real independent flock process requires POSIX')
class NativeAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=F.FiniteExecutionTests('test_null_cap_is_explicit_and_old_contract_is_unchanged')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.f=self.fixture.f
        with learn.ledger_lock(self.f.root): pass

    def test_actual_commit_keeps_lesson_lease_and_check_runs_inside_transaction(self):
        raw=self.f.store.db;observed=[];armed=[False];case=self
        code='import fcntl,sys\nf=open(sys.argv[1],"r+b")\ntry:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError:sys.exit(73)\nsys.exit(0)\n'
        class Proxy:
            def __getattr__(self,name):return getattr(raw,name)
            def commit(self):
                if armed[0] and raw.in_transaction:
                    process=subprocess.run([sys.executable,'-I','-B','-c',code,str(case.f.root/'lessons.lock')],capture_output=True,timeout=3)
                    observed.append(process.returncode);case.assertEqual(process.returncode,73,process.stderr)
                return raw.commit()
        def check():
            case.assertTrue(raw.in_transaction);armed[0]=True
        @contextmanager
        def admission():
            try:yield check
            finally:armed[0]=False
        self.f.store.db=Proxy()
        try:result=self.f.dispatch(dispatch_guard=admission())
        finally:self.f.store.db=raw
        self.assertEqual(result['state'],'settled');self.assertEqual(observed,[73]);self.assertEqual(self.f.count,1)

    def test_sqlite_owner_can_acquire_lesson_while_competing_admission_waits(self):
        code='''import fcntl,json,sqlite3,sys
conn=sqlite3.connect(sys.argv[1]);conn.execute('BEGIN IMMEDIATE')
print('sqlite-owned',flush=True);sys.stdin.readline()
f=open(sys.argv[2],'r+b');acquired=False
try:
 fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);acquired=True
except BlockingIOError:pass
finally:
 if acquired:fcntl.flock(f,fcntl.LOCK_UN)
 f.close();conn.rollback();conn.close()
print(json.dumps({'lesson_acquired':acquired}),flush=True)
'''
        child=subprocess.Popen([sys.executable,'-I','-B','-c',code,str(self.f.store.path),str(self.f.root/'lessons.lock')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        raw=self.f.store.db;began=threading.Event();result=[];errors=[]
        class Proxy:
            def __getattr__(self,name):return getattr(raw,name)
            def execute(self,sql,*args):
                if sql=='BEGIN IMMEDIATE':began.set()
                return raw.execute(sql,*args)
        def admit():
            try:result.append(self.f.ledger.admit(self.f.key,'lock-order','propose',1000,20,material_sha256='1'*64,check=lambda:None))
            except BaseException as error:errors.append(error)
        thread=threading.Thread(target=admit)
        try:
            ready,_,_=select.select([child.stdout],[],[],3);self.assertTrue(ready)
            self.assertEqual(child.stdout.readline().strip(),'sqlite-owned')
            self.f.store.db=Proxy();thread.start();self.assertTrue(began.wait(3))
            stdout,stderr=child.communicate('go\n',timeout=3);thread.join(4)
            self.assertEqual(child.returncode,0,stderr);self.assertTrue(json.loads(stdout)['lesson_acquired'])
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[]);self.assertTrue(result[0]['new_intent'])
            self.assertEqual(self.f.count,0)
        finally:
            if child.poll() is None:child.kill();child.communicate(timeout=3)
            if thread.ident is not None:thread.join(6)
            self.f.store.db=raw
