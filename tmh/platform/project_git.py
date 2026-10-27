"""Only fixed Git metadata queries inside a project-only read-only container.

This scope does not authorize any host subprocess. Unknown commands are denied;
candidate verification, preview, merge and the legacy /accept path retain their
separate execution policy.
"""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
import json
import http.client
import os
from pathlib import Path
import re
import stat
from types import SimpleNamespace

from .errors import ApiError
from .project_container import Engine, DockerError, specification


SCOPE=ContextVar('project_metadata_scope',default=None)
BRANCH=re.compile(r'[A-Za-z0-9][A-Za-z0-9_./-]*\Z')


def valid_ref(value):
    if value.endswith('^{commit}'):
        value=value[:-9]
    if re.fullmatch('[0-9a-f]{40}',value) or value=='HEAD': return True
    if re.fullmatch('refs/webuddy/candidates/[0-9a-f]{64}',value): return True
    if value.startswith('refs/heads/'):
        value=value[len('refs/heads/'):]
    elif value.startswith('refs/'):
        return False
    return bool(BRANCH.fullmatch(value) and '..' not in value and '//' not in value and
                all(part and not part.endswith(('.','.lock')) and not part.startswith('.') for part in value.split('/')))


def settings(P):
    path=Path(P.data_dir)/'project-execution.json'
    try:
        info=path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
        raise ApiError(503,'项目隔离配置的所有者或权限不安全')
    value=json.loads(path.read_text())
    if (not isinstance(value,dict) or set(value)!={'schema','image','projects'} or value['schema']!=1 or
            not re.fullmatch(r'sha256:[0-9a-f]{64}',value.get('image','')) or
            not isinstance(value['projects'],list) or any(not isinstance(k,str) or not re.fullmatch('[A-Z][A-Z0-9]{0,9}',k) for k in value['projects'])):
        raise ApiError(503,'项目隔离配置无效')
    return value


def available(P, project, user):
    from .tenant_policy import require_member
    require_member(P,user,project,'contributor')
    value=settings(P)
    return bool(value and project['key'] in value['projects'] and repository(P,project,user)['ready'])


def repository(P, project, user=''):
    metadata=Path(project['root'])/'.git'
    managed=getattr(P,'tenant_context',None)
    if metadata.is_dir() and not metadata.is_symlink():
        return {'ready':True,'reason':''}
    if metadata.is_file() and (not managed or managed.runtime_allowed(user)):
        return {'ready':True,'reason':''}  # unchanged local/legacy Git worktrees
    reason=('当前代码工作树尚未接入独立的版本证据环境，请联系项目管理员。' if metadata.exists() else
            '当前工作区尚未接入代码仓库，暂不能进行固定版本代码复核；现有资料仍可使用。')
    return {'ready':False,'reason':reason}


def scoped(fn):
    @wraps(fn)
    def wrapped(P, *args, **kwargs):
        user=kwargs.get('user',kwargs.get('viewer',args[1] if len(args)>1 else ''))
        previous=SCOPE.get()
        if previous and previous['platform'] is P and previous['user']==user:
            return fn(P,*args,**kwargs)
        readonly=fn.__name__ in ('item','dispatch_read') or fn.__module__.endswith('.workspace') and fn.__name__=='read'
        token=SCOPE.set({'platform':P,'user':user,'readonly':readonly,'snapshots':{},'failed_roots':set()})
        try: return fn(P,*args,**kwargs)
        finally: SCOPE.reset(token)
    return wrapped


@contextmanager
def personal_scope(P,user):
    """Scoped read-only Git metadata for a personally authorized run."""
    previous=SCOPE.get()
    if previous and previous['platform'] is P and previous['user']==user:
        yield
        return
    token=SCOPE.set({'platform':P,'user':user,'readonly':False,'snapshots':{},'failed_roots':set()})
    try:yield
    finally:SCOPE.reset(token)


def _allowed(args):
    args=tuple(args)
    if args[:1]==('rev-parse',):
        options=args[1:-1]
        return all(x in ('--verify','--quiet','--end-of-options') for x in options) and valid_ref(args[-1])
    if args[:2]==('merge-base','--is-ancestor') and len(args)==4:
        return all(valid_ref(x) for x in args[2:])
    return args==('symbolic-ref','--quiet','--short','refs/remotes/origin/HEAD') or (
        args[:3]==('show-ref','--verify','--quiet') and len(args)==4 and args[-1].startswith('refs/heads/') and valid_ref(args[-1]))


# A read-only projection gets one actual metadata snapshot per project. Writes
# never use it: every validation inside a verdict transaction reads Git afresh.
BATCH = r'''
import json,subprocess,sys
result={}
for ref in json.loads(sys.argv[1]):
    p=subprocess.run(json.loads(sys.argv[2])+['rev-parse','--verify','--end-of-options',ref],capture_output=True)
    result[ref]=[p.returncode,p.stdout.decode('utf-8','strict')]
print(json.dumps(result))
'''


def _snapshot(P,project,image,root,first,base):
    refs={first}
    tickets={}
    for row in P.store.q('SELECT c.ref,c.ticket_id FROM code_candidates c JOIN tickets t ON t.id=c.ticket_id WHERE t.project_id=? AND c.id=(SELECT MAX(newer.id) FROM code_candidates newer WHERE newer.ticket_id=c.ticket_id)',(project['id'],)):
        refs.add(row['ref'])
        if row['ticket_id'] not in tickets:
            tickets[row['ticket_id']]=P.store.ticket(row['ticket_id'])
    for ticket in tickets.values():
        for name in ('base','code_at'):
            value=(ticket.get('links') or {}).get(name)
            if value: refs.add(str(value)+'^{commit}')
    refs=sorted(ref for ref in refs if valid_ref(ref))
    output=[]
    result=Engine().run(specification(image,['python3','-c',BATCH,json.dumps(refs),json.dumps(base)],root,10),10,output=output.append)
    if result['reason']!='exited' or result['returncode'] or not result['cleanup']:
        raise ApiError(503,'Git 元数据快照未正常结束或回收')
    return json.loads(b''.join(output))


def read(root, args, *, text=False):
    try:
        return _read(root,args,text=text)
    except DockerError as exc:
        _failed(root)
        raise ApiError(503,'项目 Git 隔离环境不可用：'+str(exc)) from None
    except (OSError,http.client.HTTPException,ValueError):
        _failed(root)
        raise ApiError(503,'无法连接或读取项目 Git 隔离证据，请由管理员检查执行环境') from None
    except ApiError as exc:
        if exc.code==503: _failed(root)
        raise


def _failed(root):
    active=SCOPE.get()
    if active: active['failed_roots'].add(str(root))


def unavailable(root):
    active=SCOPE.get()
    return bool(active and str(root) in active['failed_roots'])


def _read(root, args, *, text=False):
    active=SCOPE.get()
    if not active: return None
    P,user=active['platform'],active['user']
    managed=getattr(P,'tenant_context',None)
    if not managed or managed.runtime_allowed(user): return None
    from .tenant_policy import require_member
    project=next((p for p in P.store.projects() if Path(p['root'])==Path(root)),None)
    if not project: raise ApiError(403,'Git 证据目录不属于已授权项目')
    require_member(P,user,project,'viewer')
    value=settings(P)
    if not value or project['key'] not in value['projects'] or not managed.workspace_allowed(root):
        raise ApiError(403,'此项目没有可用的独立 Git 证据环境')
    status=repository(P,project,user)
    if not status['ready']: raise ApiError(409,status['reason'])
    if not _allowed(args): raise ApiError(403,'此通路只允许固定版本的 Git 证据读取')
    base=['git','--no-optional-locks','-c','safe.directory=/workspace','-c','core.hooksPath=/dev/null',
          '-c','core.fsmonitor=false','--no-replace-objects']
    if active['readonly'] and args[0]=='rev-parse':
        key=(project['id'],value['image'])
        if key not in active['snapshots']:
            try:
                active['snapshots'][key]=_snapshot(P,project,value['image'],root,args[-1],base)
            except (DockerError,OSError,http.client.HTTPException,ValueError,ApiError) as exc:
                active['snapshots'][key]=exc
                raise
        snapshot=active['snapshots'][key]
        if isinstance(snapshot,Exception): raise snapshot
        if args[-1] in snapshot:
            code,raw=snapshot[args[-1]]
            return SimpleNamespace(returncode=code,stdout=raw if text else raw.encode(),stderr='' if text else b'')
    command=[*base,*args]
    chunks=[]
    result=Engine().run(specification(value['image'],command,root,10),10,output=chunks.append)
    if result['reason']!='exited' or not result['cleanup']:
        raise ApiError(503,'Git 证据环境未正常结束或回收')
    raw=b''.join(chunks)
    return SimpleNamespace(returncode=result['returncode'],stdout=raw.decode('utf-8','strict') if text else raw,
                           stderr='' if text else b'')
