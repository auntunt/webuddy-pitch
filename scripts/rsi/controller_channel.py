"""Temporary, registered-ID FIFO broker for a non-root fixture controller.

Root is trusted provisioning, never the optimizable controller. No daemon or RPC
installation. Existing provider/ledger/launcher own all paid and worker intents.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import select
import stat
import struct
import threading
import time
import uuid
try:
    import fcntl, pwd, grp
except ImportError:
    fcntl = pwd = grp = None

from scripts.rsi import registered_isolation as X, registered_trial as R, provider_adapter as P, trial_preparation as L
from tmh.platform import learning, supervised_process as SP

VERSION='controller-channel-fixture-v1'
UID=508103
MAX_REQUEST=4096
MAX_PUBLIC=8*1024*1024
MAX_REQUESTS=128
LIMIT_MS=8000
ACTIONS={'input','run','status','cancel'}
OPERATIONS={'normal','tamper','cancel','exit','hang','forge','error'}
CODE=Path(__file__).resolve()
LOADED=P.file_hash(CODE)


def public_status(result,*,running=False,cancelled=False,stage='idle'):
    """A deliberate declassification: state and one frozen verdict, no hashes."""
    state='running' if running else 'not_started'
    verdict=None
    if result is not None:
        state='unknown'
        if (isinstance(result,dict) and result.get('schema')==X.VERSION and result.get('isolated_execution')=='evaluated'
                and result.get('oracle_evaluation')=='completed' and type(result.get('verdict')) is bool
                and type(result.get('candidate_returncode')) is int and result['candidate_returncode']==0
                and type(result.get('evaluator_returncode')) is int and result['evaluator_returncode']==0
                and result.get('production_equivalent') is False and result.get('rsi_qualified') is False):
            state='evaluated';verdict=result['verdict']
    return {'state':state,'verdict':verdict,'cancel_requested':bool(cancelled),'stage':stage}


class Frames:
    """Bounded, lossless frames; reject oversized records, never truncate them."""
    def __init__(self,read_fd,write_fd,*,deadline,stop,limit):
        self.read_fd,self.write_fd=read_fd,write_fd
        self.deadline,self.stop,self.limit=deadline,stop,limit
        self.buffer=bytearray()

    def check(self):
        if self.stop.is_set() or time.monotonic()>=self.deadline:raise TimeoutError('channel ended')

    def receive(self):
        while True:
            self.check()
            if len(self.buffer)>=4:
                length=struct.unpack('!I',self.buffer[:4])[0]
                if length==0 or length>self.limit:raise ValueError('unsupported frame size')
                if len(self.buffer)>=length+4:
                    raw=bytes(self.buffer[4:length+4]);del self.buffer[:length+4]
                    return P.strict_json(raw)
            if select.select([self.read_fd],[],[],.03)[0]:
                raw=os.read(self.read_fd,4096)
                if not raw:raise EOFError('channel closed')
                self.buffer.extend(raw)

    def send(self,value):
        raw=L.encoded(value).encode()
        if not raw or len(raw)>MAX_PUBLIC:raise ValueError('unsupported public frame size')
        data=memoryview(struct.pack('!I',len(raw))+raw)
        while data:
            self.check()
            if select.select([],[self.write_fd],[],.03)[1]:
                try:written=os.write(self.write_fd,data)
                except BlockingIOError:continue
                if not written:raise EOFError('channel closed')
                data=data[written:]


WORKER=r'''
import os,sys,json,time,struct,select,signal
from pathlib import Path
config=json.loads(sys.stdin.buffer.read())
checks={'uid':os.getuid(),'gid':os.getgid()}
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
checks['no_caps']=all(int(status[k].strip(),16)==0 for k in ('CapEff','CapPrm','CapBnd','CapAmb'))
checks['no_new_privileges']=status.get('NoNewPrivs','').strip()=='1'
checks['environment_clean']=set(os.environ)<={'PATH','LANG','LC_CTYPE'}
checks['host_unmapped']=all(not Path(p).exists() for p in ('/home','/root','/opt/webuddy','/tmp'))
for name,path,method in [('oracle_unmapped','/input/oracle.json','file'),('parent_environment_denied','/proc/1/environ','file'),
 ('parent_root_denied','/proc/1/root','link'),('parent_cwd_denied','/proc/1/cwd','link'),('parent_fds_denied','/proc/1/fd','dir'),
 ('private_file_denied','/deny/private-canary','file')]:
 try:
  if method=='link':os.readlink(path)
  elif method=='dir':list(Path(path).iterdir())
  else:Path(path).read_bytes()
  checks[name]=False
 except PermissionError:checks[name]=True
 except FileNotFoundError:checks[name]=name=='oracle_unmapped'
for name,path,flags in [('request_read_denied','/ipc/request',os.O_RDONLY|os.O_NONBLOCK),('response_write_denied','/ipc/response',os.O_WRONLY|os.O_NONBLOCK)]:
 try:fd=os.open(path,flags);os.close(fd);checks[name]=False
 except PermissionError:checks[name]=True
try:os.chmod('/ipc/request',0o666);checks['cannot_change_channel_rights']=False
except PermissionError:checks['cannot_change_channel_rights']=True
try:os.setuid(0);checks['cannot_regain_root']=False
except PermissionError:checks['cannot_regain_root']=True
targets=[]
for name in os.listdir('/proc/self/fd'):
 try:targets.append(os.readlink('/proc/self/fd/'+name))
 except FileNotFoundError:pass
checks['no_inherited_host_fds']=all(not p.startswith('/') or p=='/dev/null' for p in targets)
if checks['uid']!=508103 or checks['gid']!=508103 or any(v is not True for k,v in checks.items() if k not in ('uid','gid')):
 print(json.dumps({'schema':'controller-observation-failed','checks':checks}),flush=True);raise SystemExit(1)
if config['operation']=='forge':
 print(json.dumps({'schema':'controller-client-v1','checks':checks,'final':{'state':'evaluated','verdict':True}}),flush=True);raise SystemExit(0)
read_fd=os.open('/ipc/response',os.O_RDONLY|os.O_NONBLOCK);write_fd=os.open('/ipc/request',os.O_WRONLY|os.O_NONBLOCK)
received=bytearray();responses=[];counter=0

def exchange(body):
 global counter
 counter+=1;message={'action':body.pop('action'),'plan_id':config['plan_id'],'input_id':config['input_id'],'request_id':'control-'+str(counter)};message.update(body)
 raw=json.dumps(message,ensure_ascii=False,separators=(',',':')).encode();data=memoryview(struct.pack('!I',len(raw))+raw);deadline=time.monotonic()+2
 while data:
  if time.monotonic()>deadline:raise TimeoutError()
  if select.select([],[write_fd],[],.02)[1]:
   try:n=os.write(write_fd,data);data=data[n:]
   except BlockingIOError:pass
 while True:
  if len(received)>=4:
   n=struct.unpack('!I',received[:4])[0]
   if n>8*1024*1024:raise ValueError()
   if len(received)>=n+4:
    value=json.loads(received[4:n+4]);del received[:n+4];responses.append(value);return value
  if time.monotonic()>deadline:raise TimeoutError()
  if select.select([read_fd],[],[],.02)[0]:received.extend(os.read(read_fd,4096))

try:
 public=exchange({'action':'input'})
 if config['operation']=='tamper':
  for body in [{'action':'details'},{'action':'run','command':['id']},{'action':'run','uid':0},{'action':'run','mount':'/root'},
               {'action':'run','env':{'SECRET':'not-authorized'}},{'action':'run','input_id':'unregistered'},{'action':'run','oracle':True}]:exchange(body)
  final=exchange({'action':'status'})
 else:
  exchange({'action':'run','request_id':'one-immutable-run'})
  exchange({'action':'run','request_id':'one-immutable-run'})
  exchange({'action':'status','request_id':'one-immutable-run'})
  while True:
   final=exchange({'action':'status'})
   if config['operation'] in ('cancel','exit','hang') and final.get('stage')=='candidate_ready':
    if config['operation']=='cancel':exchange({'action':'cancel'});config['operation']='normal'
    elif config['operation']=='exit':os.kill(os.getpid(),signal.SIGKILL)
    else:
     while True:time.sleep(1)
   if final.get('state') in ('evaluated','unknown'):break
   time.sleep(.05)
 print(json.dumps({'schema':'controller-client-v1','checks':checks,'public_input':public,'responses':responses,'final':final},ensure_ascii=False),flush=True)
except BaseException:
 print('{"schema":"controller-client-error-v1"}',flush=True);raise SystemExit(1)
'''

SETUP=r'''
import os,sys,subprocess
from pathlib import Path
root=Path(sys.argv[1]);ipc=Path(sys.argv[2]);worker=sys.argv[3]
def call(a):subprocess.run(a,check=True,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
for source,name in [('/usr','usr'),('/lib','lib'),('/lib64','lib64')]:
 call(['/usr/bin/mount','--bind',source,str(root/name)])
 call(['/usr/bin/mount','-o','remount,bind,ro,nosuid,nodev',str(root/name)])
call(['/usr/bin/mount','-t','proc','-o','ro,nosuid,nodev,noexec','proc',str(root/'proc')])
for name in ('request','response'):call(['/usr/bin/mount','--bind',str(ipc/name),str(root/'ipc'/name)])
command=['/usr/sbin/chroot',str(root),'/usr/bin/env','-i','PATH=/usr/bin:/bin','LANG=C.UTF-8','/usr/bin/setpriv','--reuid=508103','--regid=508103',
 '--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','/usr/bin/python3','-I','-c',worker]
p=subprocess.Popen(command,close_fds=True)
raise SystemExit(p.wait())
'''

CHECKS={'uid','gid','no_caps','no_new_privileges','environment_clean','host_unmapped','oracle_unmapped',
        'parent_environment_denied','parent_root_denied','parent_cwd_denied','parent_fds_denied','private_file_denied',
        'request_read_denied','response_write_denied','cannot_change_channel_rights','cannot_regain_root','no_inherited_host_fds'}


class Session:
    """Trusted temporary provisioning/broker. The child controller is UID508103."""
    def __init__(self,launcher,catalog,work_root):
        if not X.supported():raise L.Conflict('explicit Linux root fixture provisioning required')
        self.launcher,self.catalog=launcher,catalog
        self.ledger=launcher.ledger
        self.root=X.private_directory(work_root)
        self.last_folder=None

    def _current(self):
        if P.file_hash(CODE)!=LOADED:raise L.Conflict('channel code changed')
        st=CODE.lstat()
        if st.st_uid!=0 or st.st_mode&0o022 or CODE.is_symlink():raise L.Conflict('trusted root-owned channel source required')
        self.launcher._code_current()
        if hasattr(self,'identities'):
            if (self.catalog.identity('plan',self.plan_id),self.launcher.catalog.identity('plan',self.plan_id),
                self.launcher.broker.catalog.identity('plan',self.plan_id),self.launcher.broker.catalog.identity('input',self.input_id))!=self.identities:
                raise L.Conflict('admitted channel material changed')

    def _lease(self):
        fd=os.open('/tmp/webuddy-controller-uid-lease.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            P._private(os.fstat(fd),0);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            for lookup in (pwd.getpwuid,grp.getgrgid):
                try:lookup(UID)
                except KeyError:pass
                else:raise L.Conflict('controller fixture identity already assigned')
            for path in Path('/proc').glob('[0-9]*/status'):
                try:lines=path.read_text().splitlines()
                except (FileNotFoundError,ProcessLookupError):continue
                if any(line.split(':',1)[0] in {'Uid','Gid','Groups'} and str(UID) in line.split()[1:] for line in lines):
                    raise L.Conflict('controller fixture identity active')
            return fd
        except BaseException:os.close(fd);raise

    def _history(self,db,key,request):
        intents=[];finished=[]
        for event in db.execute("SELECT request_id,kind,payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind IN ('controller_intent','controller_finished') ORDER BY id",(key,)):
            value=P.strict_json(event['payload'])
            if event['request_id'] or L.digest(value)!=event['payload_hash']:raise L.Conflict('controller anchor corrupt')
            if value.get('request_id')==request:
                if event['kind']=='controller_intent':
                    L.fields(value,{'request_id','binding_sha256','nonce'});L.sha(value['binding_sha256'])
                else:
                    L.fields(value,{'request_id','nonce','receipt_sha256'});L.sha(value['receipt_sha256'])
                P.opaque(value['nonce'])
                (intents if event['kind']=='controller_intent' else finished).append(value)
        if len(intents)>1 or len(finished)>1 or finished and (not intents or finished[0]['nonce']!=intents[0]['nonce']):raise L.Conflict('controller history not unique')
        return (intents[0] if intents else None),(finished[0] if finished else None)

    def _stage(self):
        with self.lock:
            if self.job_result is not None:return 'reported'
            started=self.job_started
        if not started:return 'idle'
        try:
            item=self.ledger.isolation_snapshot(self.pool,self.request)
            if item:
                folder=self.launcher.root/item['anchor']['execution_id']
                path=folder/'candidate-supervised/output.bin'
                if path.exists() and path.read_bytes()==b'CANDIDATE_READY\n':return 'candidate_ready'
        except (OSError,ValueError,KeyError,TypeError):pass
        return 'working'

    def _status(self):
        with self.lock:result=self.job_result;running=self.job_started and result is None
        return public_status(result,running=running,cancelled=self.user_cancel,stage=self._stage())

    def _job(self):
        outer=self
        class Cancel:
            def is_set(self):
                if outer.cancel_job.is_set() or outer.external is not None and outer.external.is_set():return True
                try:outer._current();return False
                except (OSError,ValueError,KeyError,TypeError):return True
        try:result=self.launcher.dispatch(self.plan_id,self.input_id,cancel_event=Cancel())
        except BaseException as error:
            # Neither the controller channel nor its error receipt gets str(error).
            self.job_error=type(error).__name__;result={}
        with self.lock:self.job_result=result

    def _handle(self,body):
        try:
            L.fields(body,{'action','plan_id','input_id','request_id'})
            if not isinstance(body['action'],str) or body['action'] not in ACTIONS:raise ValueError()
            for name in ('plan_id','input_id','request_id'):P.opaque(body[name])
            if (body['plan_id'],body['input_id'])!=(self.plan_id,self.input_id):raise ValueError()
            fingerprint=L.digest(body);prior=self.cache.get(body['request_id'])
            if prior:
                return R.detached(prior[1]) if prior[0]==fingerprint else {'error':'request_conflict'}
            self._current()
            if body['action']=='input':
                if len(L.encoded(self.public).encode())>MAX_PUBLIC:reply={'error':'public_input_unavailable'}
                else:reply=R.detached(self.public)
            elif body['action']=='run':
                with self.lock:
                    if not self.job_started:
                        self.job_started=True
                        self.job_thread=threading.Thread(target=self._job,name='fixed-root-job')
                        self.job_thread.start()
                reply={'accepted':True}
            elif body['action']=='cancel':self.user_cancel=True;self.cancel_job.set();reply={'cancel_requested':True}
            else:reply=self._status()
            self.cache[body['request_id']]=(fingerprint,R.detached(reply));return reply
        except (OSError,ValueError,KeyError,TypeError):return {'error':'denied'}

    def _serve(self,frames):
        try:
            with (self.last_folder/'channel.jsonl').open('x',encoding='utf-8') as log:
                for unused in range(MAX_REQUESTS):
                    body=frames.receive();reply=self._handle(body)
                    log.write(L.encoded({'request':body,'response':reply})+'\n');log.flush()
                    frames.send(reply)
                self.channel_error='request_limit'
        except (TimeoutError,EOFError):pass
        except BaseException:self.channel_error='protocol_error'
        finally:self.cancel_job.set()

    def _sandbox(self,folder):
        root=folder/'controller-root';root.mkdir(mode=0o700);root.chmod(0o755)
        for name in ('usr','lib','lib64','proc','ipc','deny'):
            path=root/name;path.mkdir(mode=0o700);path.chmod(0o755)
        X.seal(root/'deny','private-canary',uuid.uuid4().hex.encode(),mode=0o400)
        ipc=folder/'private-ipc';ipc.mkdir(mode=0o700)
        for name,mode in (('request',0o620),('response',0o640)):
            os.mkfifo(ipc/name,mode=0o600)
            fd=os.open(ipc/name,os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW)
            try:os.fchown(fd,0,UID);os.fchmod(fd,mode)
            finally:os.close(fd)
            os.mkfifo(root/'ipc'/name,mode=0o600)
        (root/'ipc').chmod(0o555)
        return root,ipc

    def run(self,plan_id,input_id,*,cancel_event=None):
        self._current();P.opaque(plan_id);P.opaque(input_id)
        control,ch,ci=self.catalog.load('plan',plan_id)
        L.fields(control,{'schema','plan_id','input_id','channel_sha256','execution_plan_sha256','public_plan_sha256','input_sha256','root_pool','root_contract_sha256','operation','controller_timeout_ms','max_requests'})
        if (control['schema']!=VERSION or (control['plan_id'],control['input_id'])!=(plan_id,input_id)
                or control['channel_sha256']!=LOADED or control['operation'] not in OPERATIONS
                or type(control['controller_timeout_ms']) is not int or control['controller_timeout_ms']!=LIMIT_MS
                or type(control['max_requests']) is not int or control['max_requests']!=MAX_REQUESTS):raise L.Conflict('unsupported controller contract')
        execution,eh,ei=self.launcher.catalog.load('plan',plan_id)
        plan,ph,pi=self.launcher.broker.catalog.load('plan',plan_id)
        public,ih,ii=self.launcher.broker.catalog.load('input',input_id);R.validate_capture(public)
        if len(L.encoded(public).encode())>MAX_PUBLIC:raise L.Conflict('complete public input exceeds this fixed channel')
        snap=self.ledger.snapshot(plan['root_pool'])
        if (control['execution_plan_sha256']!=eh or control['public_plan_sha256']!=ph or control['input_sha256']!=ih
                or control['root_pool']!=plan['root_pool'] or control['root_contract_sha256']!=L.digest(snap['contract'])):raise L.Conflict('controller admission binding differs')
        self.plan_id,self.input_id,self.pool,self.request=plan_id,input_id,plan['root_pool'],plan['request_id']
        self.public,self.identities=public,(ci,ei,pi,ii)
        binding=L.digest([ch,eh,ph,ih,L.digest(snap['contract']),LOADED])
        cached=None
        with learning.transaction(self.ledger.store) as db:
            self.ledger._pool(db,self.pool)
            prior,finished=self._history(db,self.pool,self.request)
            if prior:
                if prior['binding_sha256']!=binding:raise L.Conflict('controller cannot rebind original request')
                self.last_folder=self.root/prior['nonce']
                if not finished:return {'state':'unknown','verdict':None,'controller_state':'unknown','new_controller':False}
                raw=(self.last_folder/'result.json').read_bytes()
                if R.sha(raw)!=finished['receipt_sha256']:raise L.Conflict('original controller result changed')
                record=P.strict_json(raw)
                receipt=SP.read_receipt(self.last_folder/'controller-supervised',{'token':prior['nonce'],'run_id':self.request,'data_dir':str(self.root)})
                if receipt is None or P.file_hash(self.last_folder/'controller-supervised/supervisor-result.json')!=record['controller_receipt_sha256']:raise L.Conflict('original controller receipt differs')
                cached=record
        if cached is not None:
            # Leave the controller transaction before the launcher's read-only
            # ledger snapshots; learning transactions deliberately cannot nest.
            original=self.launcher.replay(plan_id,input_id,provider_intent=cached['provider_intent'])
            if cached['public']['state']=='evaluated':
                current=public_status(original)
                if current['state']!='evaluated' or current['verdict'] is not cached['public']['verdict']:
                    raise L.Conflict('cached controller verdict lacks original execution evidence')
            self._current()
            return dict(cached['public'],new_controller=False)
        lease=self._lease();self.held_lease=lease
        self.stop,self.cancel_job,self.lock=threading.Event(),threading.Event(),threading.Lock()
        self.cache={};self.job_started=False;self.job_result=None;self.job_thread=None;self.job_error='';self.channel_error='';self.user_cancel=False
        self.external=cancel_event;server=None;read_fd=write_fd=None;process=None;spawn_attempted=False
        try:
            with learning.transaction(self.ledger.store) as db:
                self.ledger._pool(db,self.pool,dispatch=True)
                again,finished=self._history(db,self.pool,self.request)
                if again:raise L.Conflict('controller concurrently claimed')
                prior={'request_id':self.request,'binding_sha256':binding,'nonce':uuid.uuid4().hex}
                self.ledger._event(db,self.pool,'','controller_intent',prior)
            folder=self.root/prior['nonce'];folder.mkdir(mode=0o700);self.last_folder=folder
            root,ipc=self._sandbox(folder)
            read_fd=os.open(ipc/'request',os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW)
            write_fd=os.open(ipc/'response',os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW)
            remaining=min(LIMIT_MS/1000,(snap['contract']['limits']['deadline_us']-self.ledger._time())/1000000)
            if remaining<=0:raise L.Conflict('original deadline expired')
            deadline=time.monotonic()+remaining
            frames=Frames(read_fd,write_fd,deadline=deadline,stop=self.stop,limit=MAX_REQUEST)
            server=threading.Thread(target=self._serve,args=(frames,),name='fixed-fifo-broker');server.start()
            outer=self
            class Cancel:
                def is_set(self):
                    if outer.external is not None and outer.external.is_set():return True
                    try:outer._current();return False
                    except (OSError,ValueError,KeyError,TypeError):return True
            command=['/usr/bin/unshare','--mount','--pid','--fork','--net','--ipc','--propagation','private','--',
                     '/usr/bin/python3','-I','-c',SETUP,str(root),str(ipc),WORKER]
            spawn_attempted=True
            process=SP.run_supervised(command,folder=folder/'controller-supervised',owner={'token':prior['nonce'],'run_id':self.request,'data_dir':str(self.root)},cwd=folder,
                env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},timeout=remaining,cancel_event=Cancel(),
                stdin=L.encoded({'plan_id':plan_id,'input_id':input_id,'operation':control['operation']}))
        finally:
            self.stop.set();self.cancel_job.set()
            if server:server.join(2)
            if self.job_thread:self.job_thread.join(8)
            if (server and server.is_alive() or self.job_thread and self.job_thread.is_alive()
                    or spawn_attempted and (process is None or process.cleanup.get('complete') is not True)):
                # Keep ownership/lease and unresolved anchor; do not claim cleanup.
                raise L.Conflict('privileged broker cleanup unconfirmed')
            for fd in (read_fd,write_fd):
                if fd is not None:os.close(fd)
            os.close(lease);self.held_lease=None
        public_result=self._status();controller_verified=False
        if process is not None and process.returncode==0 and process.cleanup.get('complete'):
            try:
                value=P.strict_json(process.output_bytes);checks=value['checks']
                controller_verified=(value['schema']=='controller-client-v1' and set(checks)==CHECKS and checks['uid']==UID and checks['gid']==UID
                    and all(checks[k] is True for k in CHECKS-{'uid','gid'}))
            except (ValueError,KeyError,TypeError):pass
        public_result['controller_state']='finished' if controller_verified else 'unknown'
        attempt=self.ledger.store.one('SELECT intent FROM rsi_prepare_attempts WHERE pool=? AND request_id=?',(self.pool,self.request))
        record={'schema':VERSION,'binding_sha256':binding,'nonce':prior['nonce'],'provider_intent':attempt['intent'] if attempt else None,
                'controller_receipt_sha256':P.file_hash(folder/'controller-supervised/supervisor-result.json') if process else None,
                'public':public_result,'job_error_class':self.job_error,'channel_error_code':self.channel_error}
        raw=L.encoded(record).encode();X.seal(folder,'result.json',raw)
        with learning.transaction(self.ledger.store) as db:
            self.ledger._pool(db,self.pool);again,finished=self._history(db,self.pool,self.request)
            if again!=prior or finished:raise L.Conflict('controller intent changed')
            self.ledger._event(db,self.pool,'','controller_finished',{'request_id':self.request,'nonce':prior['nonce'],'receipt_sha256':R.sha(raw)})
        return dict(public_result,new_controller=True)
