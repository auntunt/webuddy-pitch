"""Actual Windows job ownership; portable knowledge newline contracts."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from tmh import kb
from tmh.platform.learning_facts import _status

class NewlineContracts(unittest.TestCase):
    def test_agent_fences_accept_lf_and_crlf_without_changing_payload(self):
        from tmh.platform.fixloop import fenced
        for label in ('tmh-intake','tmh-diag','tmh-plan'):
            for newline in ('\n','\r\n'):
                self.assertEqual(fenced(label,'```'+label+newline+'{"text":"keep\\r\\nexact"}'+newline+'```'),
                                 {'text':'keep\r\nexact'})
                self.assertIsNone(fenced(label,'```'+label+newline+'invalid JSON'+newline+'```'))

    def test_supervisor_preserves_mixed_newline_output_bytes(self):
        from tmh.platform.supervised_process import run_supervised
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/'output'
            raw=b'first\r\nsecond\nthird\r\n'
            result=run_supervised([sys.executable,'-c','import sys;sys.stdout.buffer.write('+repr(raw)+')'],
                                 folder=folder,owner={'token':'newline','run_id':1,'data_dir':td},timeout=15)
            self.assertEqual(result.returncode,0)
            self.assertEqual(result.output_bytes,raw)
            self.assertEqual((folder/'output.txt').read_bytes(),raw)
            self.assertEqual((folder/'output.bin').read_bytes(),raw)

    def test_managed_human_confirmation_preserves_crlf_body(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);page=kb.page_path(root,'index');page.parent.mkdir(parents=True)
            (root/'.tmh'/'cache').mkdir()
            original='---\r\nid: index\r\nstatus: 待确认\r\n---\r\n# 标题\r\n完整正文\r\n'
            page.write_bytes(original.encode('utf-8'))
            kb.save_registry(root,{'index':{'status':kb.STATUS_DRAFT,'learning':{}}})
            kb.confirm(root,'index','synthetic-human')
            self.assertEqual(page.read_bytes(),original.replace('待确认','已确认').encode('utf-8'))

    def test_crlf_page_identity_and_status_preserve_original_body(self):
        text='---\r\nid: index\r\nstatus: 待确认\r\n---\r\n# 标题\r\n原始正文\r\n'
        self.assertEqual(kb.parse_page(text)['meta']['id'],'index')
        changed=_status(text,'已确认')
        self.assertEqual(changed,text.replace('待确认','已确认'))

@unittest.skipUnless(os.name=='nt','Windows Job Object API')
class WindowsOwnership(unittest.TestCase):
    def run_command(self,script,**kwargs):
        from tmh.platform.process_control import run_process
        return run_process([sys.executable,'-c',script],**kwargs)

    def test_input_output_and_nonzero(self):
        r=self.run_command('import sys;sys.stdout.buffer.write(sys.stdin.buffer.read());sys.exit(7)',stdin=b'x'*200000,timeout=15)
        self.assertEqual(r.returncode,7);self.assertEqual(r.output_bytes,b'x'*200000)
        self.assertTrue(r.cleanup['complete'])

    def test_timeout_cancel_and_orphan_kill_descendant(self):
        with tempfile.TemporaryDirectory() as td:
            for kind in ('timeout','cancel','orphan'):
                marker=Path(td)/kind
                child='import time;from pathlib import Path;time.sleep(4);Path('+repr(str(marker))+').write_text("escaped")'
                script='import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'+repr(child)+']);'+('time.sleep(30)' if kind!='orphan' else '')
                event=threading.Event();timer=threading.Timer(1,event.set)
                if kind=='cancel':timer.start()
                try:r=self.run_command(script,timeout=1 if kind=='timeout' else 10,cancel_event=event)
                finally:
                    if kind=='cancel':timer.join()
                self.assertEqual(r.reason,{'cancel':'cancelled','orphan':'orphaned','timeout':'timeout'}[kind])
                self.assertTrue(r.cleanup['complete'],r.cleanup)
            time.sleep(4.2)
            self.assertEqual(list(Path(td).iterdir()),[])

    def test_supervisor_seals_receipt_and_owner_loss(self):
        from tmh.platform.supervised_process import run_supervised,read_receipt
        with tempfile.TemporaryDirectory() as td:
            owner={'token':'test-owner','run_id':1,'data_dir':td}
            folder=Path(td)/'normal'
            result=run_supervised([sys.executable,'-c','print("real windows")'],folder=folder,owner=owner,timeout=15)
            self.assertEqual(result.returncode,0)
            self.assertEqual((folder/'output.txt').read_bytes(),result.output.encode('utf-8'))
            self.assertEqual((folder/'output.bin').read_bytes(),result.output_bytes)
            self.assertTrue(read_receipt(folder,owner)['cleanup']['complete'])
            folder=Path(td)/'lost'
            script='from tmh.platform.supervised_process import run_supervised;import sys;run_supervised([sys.executable,"-c","import time;time.sleep(60)"],folder='+repr(str(folder))+',owner='+repr(owner)+',timeout=60)'
            parent=subprocess.Popen([sys.executable,'-c',script])
            try:
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    if (folder/'supervisor.json').exists() and '"running"' in (folder/'supervisor.json').read_text():break
                    time.sleep(.05)
                else:self.fail('target did not start')
                parent.kill();parent.wait()
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    result=read_receipt(folder,owner)
                    if result:break
                    time.sleep(.05)
                self.assertEqual(result['reason'],'owner_lost')
                self.assertTrue(result['cleanup']['complete'])
            finally:
                if parent.poll() is None:parent.kill();parent.wait()
