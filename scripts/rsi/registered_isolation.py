"""Linux-only fixed text delivery and separate oracle evaluator, fixture admission.

Trusted Python controller construction only. No root RPC, command API, production
service or arbitrary model-code execution. Public entry arguments are two IDs.
"""
from __future__ import annotations
try:
    import fcntl, pwd
except ImportError:
    fcntl = pwd = None
import hashlib
import os
from pathlib import Path
import platform

from scripts.rsi import registered_trial as R, provider_adapter as P, trial_preparation as L
from tmh.platform import supervised_process as SP

VERSION = 'registered-isolation-fixture-v1'
CANDIDATE_UID, EVALUATOR_UID = 508101, 508102
CODE = Path(__file__).resolve()
LOADED = hashlib.sha256(CODE.read_bytes()).hexdigest()
CORE = {'supervised_process.py':'51f60191cd8380517c0398f061fec299446abd772812e4827c327794690d3b12',
        'process_control.py':'44b692746a94b0a3540d021ce72898e56f774fee8dd1df0ac54dc99394830be3'}

WORKER = r'''
import os,json,socket,sys,time,hashlib
from pathlib import Path
role=sys.argv[1]
try:
 if role=='candidate':
  value=json.loads(Path('/input/public.json').read_text())
  status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
  checks={}
  checks['uid']=os.getuid();checks['gid']=os.getgid()
  checks['no_new_privileges']=status.get('NoNewPrivs','').strip()=='1'
  checks['no_capabilities']=all(int(status[k].strip(),16)==0 for k in ('CapEff','CapPrm','CapBnd','CapAmb'))
  checks['host_unmapped']=all(not Path(p).exists() for p in ('/home','/root','/opt/webuddy','/sealed'))
  checks['separate_network']=os.readlink('/proc/self/ns/net')!=value['host_netns']
  try:Path('/proc/1/environ').read_bytes();checks['parent_environment_denied']=False
  except PermissionError:checks['parent_environment_denied']=True
  for name,link in [('parent_root_denied','/proc/1/root'),('parent_cwd_denied','/proc/1/cwd')]:
   try:os.readlink(link);checks[name]=False
   except PermissionError:checks[name]=True
  try:list(Path('/proc/1/fd').iterdir());checks['parent_fds_denied']=False
  except PermissionError:checks['parent_fds_denied']=True
  try:Path('/input/oracle.json').read_bytes();checks['oracle_unmapped']=False
  except FileNotFoundError:checks['oracle_unmapped']=True
  try:os.setuid(0);checks['cannot_regain_root']=False
  except PermissionError:checks['cannot_regain_root']=True
  checks['sanitized_environment']=set(os.environ)<={'PATH','LANG','LC_CTYPE'}
  targets=[]
  for name in os.listdir('/proc/self/fd'):
   try:targets.append(os.readlink('/proc/self/fd/'+name))
   except FileNotFoundError:pass
  checks['no_inherited_host_fds']=all(not p.startswith('/') or p=='/dev/null' for p in targets)
  checks['cwd_is_root']=os.getcwd()=='/'
  mounts={line.split()[4]:set(line.split()[5].split(',')) for line in Path('/proc/self/mountinfo').read_text().splitlines()}
  checks['readonly_system']=all('ro' in mounts.get(p,set()) for p in ('/usr','/lib','/lib64','/proc'))
  if value['operation']=='hang':
   print('CANDIDATE_READY',flush=True)
   while True:time.sleep(1)
  print(json.dumps({'schema':'candidate-text-v1','checks':checks,'blocks':value['native_response']['content']},ensure_ascii=False),flush=True)
 elif role=='evaluator':
  candidate_raw=Path('/input/candidate.json').read_bytes();candidate=json.loads(candidate_raw)
  oracle=json.loads(Path('/input/oracle.json').read_text())
  # Canonical parsed JSON preserves every field and bool/number distinctions.
  # Object order is ignored; array order and int/float representations remain.
  def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
  print(json.dumps({'schema':'oracle-exact-blocks-v2','uid':os.getuid(),'verdict':canonical(candidate['blocks'])==canonical(oracle['expected_blocks']),
                    'candidate_sha256':hashlib.sha256(candidate_raw).hexdigest()},sort_keys=True),flush=True)
 else:raise ValueError()
except BaseException:
 print('{"schema":"fixed-worker-error-v1"}',flush=True)
 raise SystemExit(1)
'''

# Only the trusted controller supplies these internal paths/roles. They are
# freshly constructed beneath its private root, never accepted from a plan.
SETUP = r'''
import os,sys,subprocess
from pathlib import Path
root=Path(sys.argv[1]);role=sys.argv[2];worker=sys.argv[3]
uid={'candidate':508101,'evaluator':508102}[role]
def call(a):subprocess.run(a,check=True,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
for source,name in [('/usr','usr'),('/lib','lib'),('/lib64','lib64')]:
 target=root/name
 call(['/usr/bin/mount','--bind',source,str(target)])
 call(['/usr/bin/mount','-o','remount,bind,ro,nosuid,nodev',str(target)])
call(['/usr/bin/mount','-t','proc','-o','ro,nosuid,nodev,noexec','proc',str(root/'proc')])
command=['/usr/sbin/chroot',str(root),'/usr/bin/env','-i','PATH=/usr/bin:/bin','LANG=C.UTF-8','/usr/bin/setpriv',
 '--reuid='+str(uid),'--regid='+str(uid),'--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
 '/usr/bin/python3','-I','-c',worker,role]
p=subprocess.Popen(command,stdin=subprocess.DEVNULL,close_fds=True)
raise SystemExit(p.wait())
'''


def bundle():
    paths = dict(P.SOURCES, broker=R.CODE_PATH, executor=CODE,
                 supervisor=Path(SP.__file__), process_control=Path(SP.__file__).with_name('process_control.py'))
    return {name:P.file_hash(path) for name,path in paths.items()}


def supported():
    return platform.system()=='Linux' and os.geteuid()==0


def private_directory(path):
    path=Path(path)
    if path.resolve()!=path:raise L.Conflict('private controller path must not contain symlinks')
    P._private(path.lstat(),0,directory=True)
    return path


def seal(folder,name,raw,*,uid=0,mode=0o400):
    fd=os.open(folder/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.fchown(stream.fileno(),uid,uid);os.fchmod(stream.fileno(),mode)


class Launcher:
    def __init__(self,broker,execution_catalog,oracles,work_root):
        if not supported():raise L.Conflict('explicit Linux root fixture controller required')
        self.broker=broker;self.ledger=broker.adapter.ledger
        self.catalog=execution_catalog;self.oracles=oracles
        self.root=private_directory(work_root)
        self.source_bundle=bundle()

    def _code_current(self):
        if P.file_hash(CODE)!=LOADED or bundle()!=self.source_bundle:raise L.Conflict('executor bundle changed after import')
        for path in [CODE,R.CODE_PATH,*P.SOURCES.values(),Path(SP.__file__),Path(SP.__file__).with_name('process_control.py')]:
            st=path.lstat()
            if st.st_uid!=0 or st.st_mode&0o022 or path.is_symlink():raise L.Conflict('root-owned immutable fixture source required')
        for name,digest in CORE.items():
            if P.file_hash(Path(SP.__file__).with_name(name))!=digest:raise L.Conflict('reviewed supervisor changed')
        R.code_current()

    def _lease(self):
        fd=os.open('/tmp/webuddy-registered-isolation-uid-lease.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            P._private(os.fstat(fd),0)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            for uid in (CANDIDATE_UID,EVALUATOR_UID):
                try:pwd.getpwuid(uid)
                except KeyError:pass
                else:raise L.Conflict('fixture numerical identity already assigned')
                for status in Path('/proc').glob('[0-9]*/status'):
                    try:lines=status.read_text().splitlines()
                    except (FileNotFoundError,ProcessLookupError):continue
                    if any(line.startswith('Uid:') and str(uid) in line.split()[1:] for line in lines):
                        raise L.Conflict('fixture identity already active')
            return fd
        except BaseException:os.close(fd);raise

    def _sandbox(self,folder,role,payload,oracle=None):
        root=folder/(role+'-root');root.mkdir(mode=0o700)
        # mkdir's mode is masked by the controller's deliberately strict umask.
        # Only these fresh sandbox-internal directories become traversable.
        root.chmod(0o755)
        for name in ('usr','lib','lib64','proc','input'):
            child=root/name;child.mkdir(mode=0o700);child.chmod(0o755)
        uid=CANDIDATE_UID if role=='candidate' else EVALUATOR_UID
        seal(root/'input','public.json' if role=='candidate' else 'candidate.json',payload,mode=0o444)
        if oracle is not None:seal(root/'input','oracle.json',oracle,uid=uid,mode=0o400)
        return root

    def _run(self,folder,role,root,timeout,owner,cancel):
        command=['/usr/bin/unshare','--mount','--pid','--fork','--net','--propagation','private','--',
                 '/usr/bin/python3','-I','-c',SETUP,str(root),role,WORKER]
        return SP.run_supervised(command,folder=folder/(role+'-supervised'),owner=owner,cwd=folder,
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},timeout=timeout,cancel_event=cancel)

    def _admission(self,plan_id,input_id):
        self._code_current();P.opaque(plan_id);P.opaque(input_id)
        execution,execution_hash,ei=self.catalog.load('plan',plan_id)
        L.fields(execution,{'schema','plan_id','input_id','plan_sha256','input_sha256','root_pool','contract_sha256','bundle_sha256','oracle_sha256','operation','timeout_ms'})
        if execution['schema']!=VERSION or execution['plan_id']!=plan_id or execution['input_id']!=input_id or execution['operation'] not in {'deliver','hang'} or type(execution['timeout_ms']) is not int or execution['timeout_ms']!=3000:
            raise L.Conflict('unsupported fixed execution contract')
        plan,ph,pi=self.broker.catalog.load('plan',plan_id)
        public,ih,ii=self.broker.catalog.load('input',input_id)
        R.validate_capture(public)
        oracle,oh,oi=self.oracles.load('input',plan_id)
        L.fields(oracle,{'expected_blocks','secret_canary'})
        if not isinstance(oracle['expected_blocks'],list) or not isinstance(oracle['secret_canary'],str) or len(oracle['secret_canary'])<64:
            raise L.Conflict('registered typed oracle required')
        snap=self.ledger.snapshot(plan['root_pool'])
        if (execution['plan_sha256']!=ph or execution['input_sha256']!=ih or execution['root_pool']!=plan['root_pool'] or execution['contract_sha256']!=L.digest(snap['contract']) or execution['bundle_sha256']!=L.digest(bundle()) or execution['oracle_sha256']!=oh):
            raise L.Conflict('registered execution sources differ')
        binding={'execution_sha256':execution_hash,'plan_sha256':ph,'input_sha256':ih,
                 'oracle_sha256':oh,'root_contract':L.digest(snap['contract'])}
        return execution,plan,public,oracle,(ei,pi,ii,oi),binding

    def _read_replay(self,plan,prior,binding):
        """Verify original completed evidence only; never dispatch or mutate it."""
        if prior is None:return None
        # begin_isolation adds transient dispatch metadata to the same stored
        # anchor/result. Compare only that persisted state on the final read.
        prior={'anchor':prior['anchor'],'result':prior['result']}
        old=self.ledger.snapshot(plan['root_pool'],plan['request_id'])['attempt']
        if old is None:raise L.Conflict('original provider attempt missing')
        binding=dict(binding,provider_intent=old['intent'],provider_receipt_sha256=old['receipt_hash'])
        binding_hash=L.digest(binding)
        if prior['anchor']['binding_sha256']!=binding_hash:raise L.Conflict('existing execution provenance differs')
        if prior['result'] is None:return {'isolated_execution':'pending','oracle_evaluation':'not_run','new_execution':False}
        folder=self.root/prior['anchor']['execution_id']
        binding_raw=(folder/'binding.json').read_bytes()
        if P.strict_json(binding_raw)!=binding:raise L.Conflict('original execution binding changed')
        raw=(folder/'execution-result.json').read_bytes();receipt=P.strict_json(raw)
        if L.digest(receipt)!=prior['result']['receipt_sha256']:raise L.Conflict('original execution result changed')
        L.fields(receipt,{'schema','binding_sha256','execution_id','isolated_execution','oracle_evaluation','verdict',
            'candidate_uid','evaluator_uid','candidate_returncode','evaluator_returncode','candidate_receipt_sha256',
            'evaluator_receipt_sha256','production_equivalent','rsi_qualified','production_entry'})
        evaluated=prior['result']['status']=='evaluated'
        if (receipt['schema']!=VERSION or receipt['binding_sha256']!=binding_hash or receipt['execution_id']!=prior['anchor']['execution_id']
                or receipt['isolated_execution']!=prior['result']['status']
                or receipt['oracle_evaluation']!=('completed' if evaluated else 'unknown')
                or (type(receipt['verdict']) is not bool if evaluated else receipt['verdict'] is not None)
                or type(receipt['candidate_uid']) is not int or receipt['candidate_uid']!=CANDIDATE_UID
                or type(receipt['evaluator_uid']) is not int or receipt['evaluator_uid']!=EVALUATOR_UID
                or any(receipt[k] is not False for k in ('production_equivalent','rsi_qualified','production_entry'))):
            raise L.Conflict('original execution result binding invalid')
        owner={'token':prior['anchor']['execution_id'],'run_id':plan['request_id'],'data_dir':str(self.root)}
        for role in ('candidate','evaluator'):
            digest=receipt[role+'_receipt_sha256'];code=receipt[role+'_returncode']
            if digest is None:
                if evaluated or code is not None:raise L.Conflict('original role evidence missing')
                continue
            L.sha(digest);path=folder/(role+'-supervised');original=SP.read_receipt(path,owner)
            if (original is None or P.file_hash(path/'supervisor-result.json')!=digest
                    or type(code) is not int or original['returncode']!=code
                    or evaluated and (code!=0 or original['cleanup']['complete'] is not True)):
                raise L.Conflict('original role receipt changed')
        if ((folder/'binding.json').read_bytes()!=binding_raw or (folder/'execution-result.json').read_bytes()!=raw
                or self.ledger.isolation_snapshot(plan['root_pool'],plan['request_id'])!=prior):
            raise L.Conflict('original execution evidence changed during verification')
        return dict(receipt,new_execution=False)

    def replay(self,plan_id,input_id,*,provider_intent):
        """Read-only replay API: absence/pending is not a verified success."""
        execution,plan,public,oracle,identities,binding=self._admission(plan_id,input_id)
        # A controller may finish unknown before the provider ever had an
        # intent. snapshot(request) deliberately rejects absence, so first
        # distinguish that valid no-attempt case without creating anything.
        exists=self.ledger.store.one('SELECT intent FROM rsi_prepare_attempts WHERE pool=? AND request_id=?',
                                     (plan['root_pool'],plan['request_id']))
        attempt=self.ledger.snapshot(plan['root_pool'],plan['request_id'])['attempt'] if exists else None
        if (attempt['intent'] if attempt else None)!=provider_intent:raise L.Conflict('original provider intent differs')
        prior=self.ledger.isolation_snapshot(plan['root_pool'],plan['request_id'])
        return self._read_replay(plan,prior,binding)

    def dispatch(self,plan_id,input_id,*,cancel_event=None):
        """Exactly two registered IDs; no request command, UID, mount or env."""
        execution,plan,public,oracle,identities,binding_base=self._admission(plan_id,input_id)
        ei,pi,ii,oi=identities
        def binding_for(attempt):
            return dict(binding_base,provider_intent=attempt['intent'],provider_receipt_sha256=attempt['receipt_hash'])
        prior=self.ledger.isolation_snapshot(plan['root_pool'],plan['request_id'])
        if prior:return self._read_replay(plan,prior,binding_base)
        # All private admission checks precede the original provider dispatch.
        lease=self._lease()
        try:
            result=self.broker.dispatch(plan_id,input_id,cancel_event=cancel_event)
            if result.get('state')!='settled' or not result.get('response_complete'):
                return dict(result,isolated_execution='not_run',oracle_evaluation='not_run')
            snap=self.ledger.snapshot(plan['root_pool'],plan['request_id']);attempt=snap['attempt']
            provider_folder=self.broker.adapter._folder(plan['root_pool'],plan['request_id'])
            transport=SP.read_receipt(provider_folder/'transport',self.broker.adapter._owner(plan['root_pool'],plan['request_id'],attempt['intent']))
            raw=(provider_folder/'transport/output.bin').read_bytes().partition(b'\n')[2]
            if R.sha(raw)!=result['response_sha256'] or transport is None or transport['returncode']!=0:raise L.Conflict('original native output changed')
            native=P.strict_json(raw)
            binding=binding_for(attempt)
            binding_hash=L.digest(binding)
            item=self.ledger.begin_isolation(plan['root_pool'],plan['request_id'],binding_hash)
            folder=self.root/item['anchor']['execution_id']
            if not item['new_execution']:
                return self._read_replay(plan,item,binding_base)
            folder.mkdir(mode=0o700)
            seal(folder,'binding.json',L.encoded(binding).encode())
            owner={'token':item['anchor']['execution_id'],'run_id':plan['request_id'],'data_dir':str(self.root)}
            outer=self
            class Cancel:
                def is_set(self):
                    if cancel_event is not None and cancel_event.is_set():return True
                    try:
                        outer._code_current()
                        return (outer.catalog.identity('plan',plan_id),outer.broker.catalog.identity('plan',plan_id),outer.broker.catalog.identity('input',input_id),outer.oracles.identity('input',plan_id))!=(ei,pi,ii,oi)
                    except (OSError,ValueError,KeyError,TypeError):return True
            cancel=Cancel();candidate=None;evaluated=None;verified=False;verdict=None
            try:
                def remaining():
                    limit=min(3.,(snap['contract']['limits']['deadline_us']-self.ledger._time())/1000000)
                    if limit<=0:raise L.Conflict('original root deadline expired')
                    return limit
                payload=L.encoded({'capture':public,'native_response':native,'operation':execution['operation'],
                                   'host_netns':os.readlink('/proc/self/ns/net')}).encode()
                root=self._sandbox(folder,'candidate',payload)
                candidate=self._run(folder,'candidate',root,remaining(),owner,cancel)
                if candidate.returncode!=0 or not candidate.cleanup.get('complete') or cancel.is_set():raise L.Conflict('candidate outcome unknown')
                data=P.strict_json(candidate.output_bytes);L.fields(data,{'schema','checks','blocks'})
                checks=data['checks'];expected={'uid','gid','no_new_privileges','no_capabilities','host_unmapped','separate_network','parent_environment_denied','parent_root_denied','parent_cwd_denied','parent_fds_denied','oracle_unmapped','cannot_regain_root','sanitized_environment','no_inherited_host_fds','cwd_is_root','readonly_system'}
                if data['schema']!='candidate-text-v1' or set(checks)!=expected or checks['uid']!=CANDIDATE_UID or checks['gid']!=CANDIDATE_UID or any(checks[k] is not True for k in expected-{'uid','gid'}):raise L.Conflict('candidate isolation observations failed')
                root=self._sandbox(folder,'evaluator',candidate.output_bytes,L.encoded(oracle).encode())
                evaluated=self._run(folder,'evaluator',root,remaining(),owner,cancel)
                if evaluated.returncode!=0 or not evaluated.cleanup.get('complete') or cancel.is_set():raise L.Conflict('oracle outcome unknown')
                value=P.strict_json(evaluated.output_bytes);L.fields(value,{'schema','uid','verdict','candidate_sha256'})
                if value['schema']!='oracle-exact-blocks-v2' or value['uid']!=EVALUATOR_UID or type(value['verdict']) is not bool or value['candidate_sha256']!=R.sha(candidate.output_bytes):raise L.Conflict('independent evaluation binding failed')
                if oracle['secret_canary'].encode() in candidate.output_bytes+evaluated.output_bytes:raise L.Conflict('private oracle canary exposed')
                verdict=value['verdict'];verified=True
                if self.ledger._time()>=snap['contract']['limits']['deadline_us']:verified=False
            except Exception:
                # Never expose oracle values or arbitrary worker error details.
                verified=False
            receipt={'schema':VERSION,'binding_sha256':binding_hash,'execution_id':item['anchor']['execution_id'],
                'isolated_execution':'evaluated' if verified else 'unknown','oracle_evaluation':'completed' if verified else 'unknown',
                'verdict':verdict if verified else None,'candidate_uid':CANDIDATE_UID,'evaluator_uid':EVALUATOR_UID,
                'candidate_returncode':candidate.returncode if candidate else None,'evaluator_returncode':evaluated.returncode if evaluated else None,
                'candidate_receipt_sha256':R.sha((folder/'candidate-supervised/supervisor-result.json').read_bytes()) if candidate else None,
                'evaluator_receipt_sha256':R.sha((folder/'evaluator-supervised/supervisor-result.json').read_bytes()) if evaluated else None,
                'production_equivalent':False,'rsi_qualified':False,'production_entry':False}
            seal(folder,'execution-result.json',L.encoded(receipt).encode())
            self.ledger.finish_isolation(plan['root_pool'],plan['request_id'],binding_hash,verified=verified,receipt_sha256=L.digest(receipt))
            return dict(receipt,new_execution=True)
        finally:
            # No recursive chown, traversal, deletion or ownership recovery of
            # either sandbox. Kernel-private mounts disappear with namespaces.
            os.close(lease)
