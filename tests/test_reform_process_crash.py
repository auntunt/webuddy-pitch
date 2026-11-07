"""Actual SIGKILL at storage/claim boundaries; submit is a recorded executor substitute."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from tmh.platform import reform
from tmh.platform.store import Store

CHILD = r'''
import json,os,signal,sys
from pathlib import Path
from types import SimpleNamespace
from tmh.platform import reform
from tmh.platform.store import Store
root=Path(sys.argv[1]);pid=sys.argv[2];point=sys.argv[3]
st=Store(root/'platform.db');project=st.project('RF')
def crash(*a,**kw):os.kill(os.getpid(),signal.SIGKILL)
def submit(project,ticket):
    with (root/'executor-receipt').open('x') as f:
        f.write(json.dumps({'ticket':ticket['key']}));f.flush();os.fsync(f.fileno())
    crash()
P=SimpleNamespace(data_dir=root,store=st,flow=SimpleNamespace(BY='flow',submit=submit))
if point=='before_mapping_commit':reform._save=crash
elif point=='after_mapping_commit':reform._dispatch=crash
elif point=='after_claim':st.on_create.append(crash)
reform.release(P,project,pid,None,'owner')
raise AssertionError('fault boundary was not reached')
'''

@unittest.skipUnless(os.name=='posix','SIGKILL process boundary requires POSIX')
class ReformProcessCrashTest(unittest.TestCase):
    def test_restart_at_each_boundary_never_duplicates_or_hides_work(self):
        for point in ('before_mapping_commit','after_mapping_commit','after_claim','after_executor_receipt'):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);st=Store(root/'platform.db')
                try:
                    project=st.add_project('RF','Isolated crash fixture',str(root))
                    atlas={'built':'fixed','domains':[{'id':str(i),'title':str(i),'tables':0} for i in range(4)]}
                    subprocess.run(['git','init','-q',str(root)],check=True)
                    subprocess.run(['git','-C',str(root),'-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-q','--allow-empty','-m','fixed'],check=True)
                    sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
                    plan=reform.create(root,'RF',atlas,dict(title='Crash test',goal='Preserve state',wave=2,source_version=sha,target_environment='fixture',criteria=['Preserve state']),'owner')
                    killed=subprocess.run([sys.executable,'-B','-c',CHILD,str(root),plan['id'],point],capture_output=True,text=True,timeout=20)
                    self.assertEqual(killed.returncode,-signal.SIGKILL,killed.stderr)
                    submissions=[]
                    P=SimpleNamespace(data_dir=root,store=st,flow=SimpleNamespace(BY='flow',submit=lambda p,t:submissions.append(t['key'])))
                    saved=reform.plan(root,'RF',plan['id'],store=st)
                    if point=='before_mapping_commit':
                        self.assertEqual(st.tickets(),[])
                        self.assertEqual(st.q('SELECT * FROM reform_dispatch'),[])
                        self.assertFalse(any(i.get('ticket') for i in saved['items']))
                        reform.release(P,project,plan['id'],None,'owner')
                        self.assertEqual(len(st.tickets()),2) # fixed parent + one serial child
                        self.assertEqual(len(submissions),1)
                    else:
                        self.assertEqual(len(st.tickets()),2) # fixed parent + one serial child
                        self.assertEqual(sum(bool(i.get('ticket')) for i in saved['items']),1)
                        reform.reconcile(P)
                        current=reform.view(P,project,reform.plan(root,'RF',plan['id'],store=st))
                        if point=='after_mapping_commit':
                            self.assertEqual(len(submissions),1)
                        else:
                            self.assertEqual(submissions,[],'unknown claim must block every later pending launch')
                            self.assertIn('待核对',current['blocked'])
                            self.assertEqual(current['items'][0]['dispatch_state'],'claimed')
                        self.assertEqual(len(st.tickets()),2) # fixed parent + one serial child
                        receipt=root/'executor-receipt'
                        self.assertEqual(receipt.exists(),point=='after_executor_receipt')
                        if receipt.exists():
                            self.assertEqual(json.loads(receipt.read_text())['ticket'],saved['items'][0]['ticket'])
                finally:
                    st.db.close()
