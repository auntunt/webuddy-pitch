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
    def test_virtualenv_supervisor_keeps_the_real_owner(self):
        import venv
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            venv.EnvBuilder(with_pip=False).create(root / 'env')
            script = (
                'import sys; from pathlib import Path; '
                'sys.path.insert(0, ' + repr(str(Path(__file__).resolve().parents[1])) + '); '
                'from tmh.platform.supervised_process import run_supervised; '
                'r=run_supervised([sys.executable,"-c","print(123)"], '
                'folder=Path(sys.argv[1]),owner={"token":"venv-fixture","run_id":1,"data_dir":sys.argv[1]},timeout=15); '
                'assert (r.returncode,r.reason,r.output_bytes,r.cleanup["complete"]) '
                '== (0,"exited",b"123\\r\\n",True), (r.returncode,r.reason,r.output_bytes,r.cleanup)'
            )
            result = subprocess.run([str(root / 'env' / 'Scripts' / 'python.exe'), '-c', script,
                                     str(root / 'receipt')], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))

    def test_preview_liveness_never_signals_a_live_process(self):
        from tmh.platform.preview import _alive
        from unittest.mock import patch
        with patch('os.kill', side_effect=AssertionError('liveness must not signal')):
            self.assertTrue(_alive(os.getpid()))
            self.assertFalse(_alive(0))
            child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'],
                                     stdin=subprocess.PIPE)
            try:
                self.assertTrue(_alive(child.pid))
                child.communicate(timeout=5)
                self.assertFalse(_alive(child.pid))
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()

    def test_receipt_reader_does_not_block_atomic_publication(self):
        from concurrent.futures import ThreadPoolExecutor
        from tmh.platform.supervised_process import _atomic_json, _json
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'supervisor.json'
            _atomic_json(path,{'revision':0,'body':'完整原文'*10000})
            stop=threading.Event();ready=threading.Event()
            def reading():
                count=0
                while not stop.is_set():
                    value=_json(path)
                    self.assertEqual(value['body'],'完整原文'*10000)
                    self.assertIn(value['revision'],range(51))
                    count+=1;ready.set()
                return count
            with ThreadPoolExecutor(max_workers=1) as pool:
                reader=pool.submit(reading)
                try:
                    self.assertTrue(ready.wait(5))
                    for revision in range(1,51):
                        _atomic_json(path,{'revision':revision,'body':'完整原文'*10000})
                finally:stop.set()
                self.assertGreater(reader.result(timeout=5),0)
            self.assertEqual(_json(path)['revision'],50)

    def run_command(self,script,**kwargs):
        from tmh.platform.process_control import run_process
        return run_process([sys.executable,'-c',script],**kwargs)

    def test_input_output_and_nonzero(self):
        r=self.run_command('import sys;sys.stdout.buffer.write(sys.stdin.buffer.read());sys.exit(7)',stdin=b'x'*200000,timeout=15)
        self.assertEqual(r.returncode,7);self.assertEqual(r.output_bytes,b'x'*200000)
        self.assertTrue(r.cleanup['complete'])

    def test_short_process_exit_is_not_mistaken_for_an_orphan(self):
        for _ in range(12):
            result=self.run_command('pass',timeout=15)
            self.assertEqual((result.reason,result.returncode),('exited',0),result.cleanup)
            self.assertTrue(result.cleanup['complete'])

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
        from tmh.platform.supervised_process import run_supervised,read_receipt,_json
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
                    if (folder/'supervisor.json').exists() and _json(folder/'supervisor.json').get('phase')=='running':break
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
