import json,os,tempfile,threading,time,unittest
from pathlib import Path
from tmh.platform.project_container import specification
from tmh.platform.project_mcp import BoundJob, ProjectMCP

class Client:
    def __init__(self,server):
        inr,self.inw=os.pipe();self.outr,outw=os.pipe()
        self.input=os.fdopen(inr,'r');self.output=os.fdopen(outw,'w')
        self.thread=threading.Thread(target=server.serve,args=(self.input,self.output));self.thread.start()
        self.writer=os.fdopen(self.inw,'w');self.reader=os.fdopen(self.outr,'r')
    def send(self,method,ident=None,params=None):
        d={'jsonrpc':'2.0','method':method}
        if ident is not None:d['id']=ident
        if params is not None:d['params']=params
        self.writer.write(json.dumps(d)+'\n');self.writer.flush()
    def recv(self):return json.loads(self.reader.readline())
    def close(self):
        self.writer.close();self.thread.join(8)
        if self.thread.is_alive():raise AssertionError('MCP server failed to stop')
        self.input.close();self.output.close();self.reader.close()

class FakeEngine:
    def __init__(self):self.specs=[];self.started=threading.Event();self.mode='ok';self.cleaned=threading.Event()
    def run(self,spec,seconds,*,cancel,output,receipt):
        self.specs.append(spec);self.started.set()
        try:
            if self.mode=='wait':
                deadline=time.monotonic()+seconds
                while not cancel() and time.monotonic()<deadline:time.sleep(0.01)
                return {'reason':'cancelled' if cancel() else 'timeout','returncode':125 if cancel() else 124,'cleanup':True}
            output(b'\xff\x00' if self.mode=='binary' else b'PROJECT_OK\n')
            return {'reason':'exited','returncode':0,'cleanup':True}
        finally:receipt['cleanup']=True;self.cleaned.set()

class PrototypeTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name).resolve();self.engine=FakeEngine();self.allowed=True;self.seen=[]
        self.job=BoundJob('LYB','JB',root,'sha256:'+'a'*64)
        self.server=ProjectMCP(self.job,lambda j:self.seen.append((j.principal,j.project)) or self.allowed,lambda j:j.workspace==root,lambda:self.engine,specification)
        self.client=Client(self.server);self.addCleanup(self.client.close)
        self.client.send('initialize',1,{'protocolVersion':'2024-11-05'});self.assertEqual(self.client.recv()['result']['serverInfo']['name'],'project-executor')
    def call(self,project='JB',argv=None,timeout=1,ident=7):
        self.client.send('tools/call',ident,{'name':'project_exec','arguments':{'project':project,'argv':argv or ['printf','hello'],'timeout_seconds':timeout}})
        return self.client.recv()
    def test_stdio_and_scoped_execution(self):
        self.client.send('tools/list',2);self.assertEqual(self.client.recv()['result']['tools'][0]['name'],'project_exec')
        result=self.call();self.assertFalse(result['result']['isError'])
        self.assertEqual(json.loads(result['result']['content'][0]['text'])['output'],'PROJECT_OK\n')
        self.assertTrue(self.seen);self.assertEqual(set(self.seen),{('LYB','JB')})
        spec=self.engine.specs[0];self.assertEqual(spec['HostConfig']['NetworkMode'],'none')
        self.assertEqual(spec['HostConfig']['Mounts'],[{'Type':'bind','Source':str(self.job.workspace),'Target':'/workspace','ReadOnly':False}])
        self.assertNotIn('docker.sock',json.dumps(spec));self.assertNotIn('OPENAI_API_KEY',json.dumps(spec))
    def test_binary_output_preserves_original_bytes(self):
        import base64
        self.engine.mode='binary';data=json.loads(self.call()['result']['content'][0]['text'])
        self.assertEqual(data['output_encoding'],'base64');self.assertEqual(base64.b64decode(data['output']),b'\xff\x00')
    def test_cross_project_and_untrusted_env_are_denied(self):
        result=self.call(project='RW');self.assertTrue(result['result']['isError']);self.assertEqual(len(self.engine.specs),0)
        self.client.send('tools/call',8,{'name':'project_exec','arguments':{'project':'JB','argv':['true'],'env':{'KEY':'x'}}})
        self.assertEqual(self.client.recv()['error']['code'],-32602);self.assertEqual(len(self.engine.specs),0)
    def test_timeout_fails_and_cleanup_confirmed(self):
        self.engine.mode='wait';result=self.call(timeout=.12)
        data=json.loads(result['result']['content'][0]['text'])
        self.assertEqual(data['status'],'timeout');self.assertTrue(data['cleanup']);self.assertTrue(self.engine.cleaned.is_set())
    def test_live_revocation_cancels_and_hides_output(self):
        self.engine.mode='wait';self.client.send('tools/call',10,{'name':'project_exec','arguments':{'project':'JB','argv':['true'],'timeout_seconds':2}})
        self.assertTrue(self.engine.started.wait(2));self.allowed=False
        result=self.client.recv();data=json.loads(result['result']['content'][0]['text'])
        self.assertEqual(data['status'],'denied');self.assertTrue(data['cleanup']);self.assertTrue(self.engine.cleaned.is_set())
    def test_client_disconnect_cancels_and_cleans(self):
        self.engine.mode='wait';self.client.send('tools/call',12,{'name':'project_exec','arguments':{'project':'JB','argv':['true'],'timeout_seconds':2}})
        self.assertTrue(self.engine.started.wait(2));self.client.writer.close()
        self.client.thread.join(5);self.assertFalse(self.client.thread.is_alive());self.assertTrue(self.engine.cleaned.is_set())

    def test_mcp_cancel_cleans_job(self):
        self.engine.mode='wait';self.client.send('tools/call',11,{'name':'project_exec','arguments':{'project':'JB','argv':['true'],'timeout_seconds':2}})
        self.assertTrue(self.engine.started.wait(2));self.client.send('notifications/cancelled',params={'requestId':11})
        data=json.loads(self.client.recv()['result']['content'][0]['text'])
        self.assertEqual(data['status'],'cancelled');self.assertTrue(data['cleanup'])

if __name__=='__main__':unittest.main(verbosity=2)
