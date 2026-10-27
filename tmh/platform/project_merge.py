"""Bounded fast-forward of an already reviewed candidate, never a grant.

The caller must hold the project/authorization and candidate evidence locks,
and must journal intent before invoking this helper.  A failure after starting
the container is uncertain; callers must reconcile it rather than retrying an
unobserved mutation.  This helper does not push, deploy or accept work.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
import re

from .project_container import Engine, specification


MERGE = r'''
import json,os,subprocess,sys
base,candidate,ref,branch=sys.argv[1:]
root=os.getcwd()
env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0',
         GIT_NO_REPLACE_OBJECTS='1',GIT_NO_LAZY_FETCH='1',GIT_ALLOW_PROTOCOL='')
cmd=['git','--no-optional-locks','--git-dir='+root+'/.git','--work-tree='+root,
     '-c','safe.directory='+root,'-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
     '-c','gc.auto=0','-c','maintenance.auto=false','-c','merge.autoStash=false']
def git(args, data=None, check=True):
    p=subprocess.run(cmd+args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
    if check and p.returncode: raise RuntimeError('Git 安全核验失败')
    return p.stdout
def val(args): return git(args).decode('utf-8','strict').strip()
if not os.path.isdir('.git') or os.path.islink('.git'): raise RuntimeError('项目不是独立 Git 仓库')
if val(['symbolic-ref','--quiet','--short','HEAD'])!=branch: raise RuntimeError('项目不在指定主干')
if val(['rev-parse','--verify','HEAD'])!=base: raise RuntimeError('主干已变化')
if val(['rev-parse','--verify',ref])!=candidate: raise RuntimeError('候选引用已变化')
parents=val(['rev-list','--parents','-n','1',candidate]).split()
if parents!=[candidate,base]: raise RuntimeError('候选父版本不匹配')
for name in ('MERGE_HEAD','CHERRY_PICK_HEAD','REVERT_HEAD','rebase-merge','rebase-apply','sequencer','index.lock'):
    if os.path.lexists('.git/'+name): raise RuntimeError('仓库存在未完成操作')
# .tmh is platform metadata and is masked by the container. Tracked edits and
# untracked files block; unrelated ignored caches may remain. Git's explicit
# --no-overwrite-ignore below prevents replacing ignored user files.
if git(['status','--porcelain=v1','-z','--untracked-files=all','--','.',':(exclude).tmh',':(exclude).tmh/**']):
    raise RuntimeError('项目工作区包含未提交或未跟踪的文件')
paths=git(['diff','--name-only','--no-renames','-z',base,candidate,'--']).split(b'\0')
paths=[p for p in paths if p]
if not paths: raise RuntimeError('候选没有修改')
if any(p.split(b'/')[-1]==b'.gitattributes' for p in paths):
    sys.stderr.write('WEBUDDY_REFUSE:git-attributes\n');sys.exit(3)
attrs=git(['check-attr','--cached','-z','--stdin','filter'],b''.join(p+b'\0' for p in paths)).split(b'\0')
if len(attrs)!=len(paths)*3+1 or any(attrs[i] not in (b'unspecified',b'unset') for i in range(2,len(attrs)-1,3)):
    sys.stderr.write('WEBUDDY_REFUSE:git-filter\n');sys.exit(3)
git(['merge','--ff-only','--no-edit','--no-overwrite-ignore',candidate])
if val(['rev-parse','--verify','HEAD'])!=candidate: raise RuntimeError('合并结果版本不匹配')
print(json.dumps({'base_commit':base,'commit':candidate,'branch':branch},separators=(',',':')))
'''

CHECK_MERGED = r'''
import json,os,subprocess,sys
base,candidate,ref,branch=sys.argv[1:];root=os.getcwd()
cmd=['git','--no-optional-locks','--git-dir='+root+'/.git','--work-tree='+root,
     '-c','safe.directory='+root,'-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false']
def git(args):
 p=subprocess.run(cmd+args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if p.returncode:raise RuntimeError('Git reconciliation failed')
 return p.stdout
if git(['symbolic-ref','--quiet','--short','HEAD']).decode().strip()!=branch:raise RuntimeError('branch mismatch')
if git(['rev-parse','--verify','HEAD']).decode().strip()!=candidate:raise RuntimeError('commit mismatch')
if git(['rev-parse','--verify',ref]).decode().strip()!=candidate:raise RuntimeError('reference mismatch')
if git(['rev-list','--parents','-n','1',candidate]).decode().split()!=[candidate,base]:raise RuntimeError('parent mismatch')
if git(['status','--porcelain=v1','-z','--untracked-files=all','--','.',':(exclude).tmh',':(exclude).tmh/**']):raise RuntimeError('workspace changed')
print(json.dumps({'base_commit':base,'commit':candidate,'branch':branch},separators=(',',':')))
'''


def fast_forward(image, root, base, commit, ref, branch, *, cancel=lambda: False, engine=None):
    """Run the fixed merger; unknown results are deliberately not replayed."""
    root = Path(root)
    if any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{40}',v) for v in (base,commit)):
        raise ValueError('合并需要完整固定提交')
    if not isinstance(ref,str) or not re.fullmatch('refs/webuddy/candidates/[0-9a-f]{64}',ref):
        raise ValueError('候选引用无效')
    if (not isinstance(branch,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_./-]*',branch)
            or '..' in branch or '//' in branch or any(not p or p.startswith('.') or p.endswith(('.', '.lock')) for p in branch.split('/'))):
        raise ValueError('项目主干名称无效')
    if not (root/'.git').is_dir() or (root/'.git').is_symlink():
        raise ValueError('当前项目没有独立 Git 仓库')
    chunks=[];diagnostics=[]
    spec=specification(image,['python3','-I','-c',MERGE,base,commit,ref,branch],root,60,writable=True)
    receipt=(engine or Engine()).run(spec,60,cancel=cancel,output=chunks.append,diagnostic=diagnostics.append)
    if receipt.get('reason')!='exited' or receipt.get('returncode')!=0 or receipt.get('cleanup') is not True:
        errors=b''.join(diagnostics)
        if receipt.get('reason')=='exited' and receipt.get('returncode')==3 and receipt.get('cleanup') is True:
            if errors==b'WEBUDDY_REFUSE:git-filter\n':
                raise ValueError('候选涉及 Git 过滤器或 LFS，当前不支持自动合并，请人工处理')
            if errors==b'WEBUDDY_REFUSE:git-attributes\n':
                raise ValueError('候选修改了 Git 属性，当前不支持自动合并，请人工处理')
        raise ValueError('合并未确认，请先核对项目与操作回执，不能自动重试')
    try: result=json.loads(b''.join(chunks))
    except (ValueError,UnicodeDecodeError): raise ValueError('合并回执不可核对，请先核对项目') from None
    if result!={'base_commit':base,'commit':commit,'branch':branch}:
        raise ValueError('合并回执不匹配，请先核对项目')
    return dict(result,cleanup=True)


def verify_merged(image, root, base, commit, ref, branch, *, engine=None):
    """Read-only check before reconciling a merge with an uncertain receipt."""
    chunks=[]
    spec=specification(image,['python3','-I','-c',CHECK_MERGED,base,commit,ref,branch],root,30)
    receipt=(engine or Engine()).run(spec,30,output=chunks.append)
    if receipt.get('reason')!='exited' or receipt.get('returncode')!=0 or receipt.get('cleanup') is not True:
        raise ValueError('合并回执或工作区尚不能核对，请由管理员检查')
    try:result=json.loads(b''.join(chunks))
    except (ValueError,UnicodeDecodeError):raise ValueError('合并检查回执不完整') from None
    if result!={'base_commit':base,'commit':commit,'branch':branch}:
        raise ValueError('合并检查回执与固定版本不符')
    return result


@contextmanager
def _repository_guard(root):
    from . import filelock
    from .errors import ApiError
    folder=Path(root)/'.git'
    if not folder.is_dir() or folder.is_symlink():
        raise ApiError(409,'项目需要独立 Git 仓库')
    flags=os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0)
    try: fd=os.open(folder/'webuddy-candidate-merge.lock',flags,0o600)
    except OSError: raise ApiError(409,'无法安全锁定项目仓库') from None
    with os.fdopen(fd,'a+b') as stream:
        try:filelock.try_lock(stream)
        except BlockingIOError:raise ApiError(409,'项目仓库正在合并，请稍后核对') from None
        try:yield
        finally:filelock.unlock(stream)


def browser_merge(P, cid, user, evidence_hash, request_id, mutation):
    """Merge only after current independent human review, with durable intent."""
    from . import candidates, release, team
    from .errors import ApiError
    from .project_authority import capture
    from .project_library import require_development
    from .project_mcp import BoundJob
    from .recheck_operations import source_guard
    from .store import now
    row=candidates._row(P,cid)
    ticket=team.require_reviewer(P,row['ticket_id'],user)
    project=P.store.project(ticket['project_id'])
    try:require_development(P.store,project)
    except ValueError as exc:raise ApiError(409,str(exc)) from exc
    authority=capture(P,user,project)
    job=BoundJob(user,project['key'],Path(P.data_dir)/'runs'/str(row['run_id']),authority.image)
    root=Path(project['root']);st=P.store
    with P.tenant_context.registry.authorization_guard(), candidates.guard(P,ticket['id']), \
            source_guard(P.data_dir,row['run_id']), _repository_guard(root), st.lock:
        try:
            st.db.execute('BEGIN IMMEDIATE')
            team.require_reviewer(P,ticket['id'],user)
            view=candidates.view(P,cid)
            if (not authority.current(job) or not isinstance(evidence_hash,str) or
                    evidence_hash!=view['evidence_hash'] or not view['human_accepted'] or
                    not candidates.browser_review_current(P,cid)):
                raise ApiError(409,'授权、证据或指定复核人已变化，尚不能合并')
            main=release.main_branch(root,P.data_dir,project['key'])
            if not main:raise ApiError(409,'请管理员先配置项目主干')
            head=candidates._git(root,'rev-parse','HEAD').strip()
            previous=candidates.merge_receipt(P,cid)
            if previous and (previous['state'] not in ('prepared','merged') or
                    previous['commit_sha']!=row['commit_sha'] or previous['before_commit']!=row['base_commit']):
                raise ApiError(409,'原合并回执与固定候选不一致，请先由管理员核对')
            if previous and previous['state']=='merged':
                candidates._git(root,'merge-base','--is-ancestor',row['commit_sha'],head)
                st.db.commit()
                return dict(previous,pushed=False,deployed=False,replayed=True)
            recover=(previous and previous['state']=='prepared' and head==row['commit_sha'] and
                     previous['evidence_hash']==evidence_hash and previous['before_commit']==row['base_commit'] and
                     previous['main']==main)
            if head!=row['base_commit'] and not recover:
                raise ApiError(409,'主干已偏离固定基线，请重新提交、验证和复核')
            if candidates._git(root,'rev-parse',row['ref']).strip()!=row['commit_sha']:
                raise ApiError(409,'候选固定引用已变化')
            stamp=now()
            if not previous:
                st.db.execute("INSERT INTO candidate_merges VALUES(?,?,?,?,?,?,?,'prepared',?,?)",
                    (cid,user,request_id,evidence_hash,main,head,row['commit_sha'],stamp,stamp))
            elif not recover and (previous['evidence_hash']!=evidence_hash or previous['main']!=main):
                st.db.execute("UPDATE candidate_merges SET author=?,request_id=?,evidence_hash=?,main=?,before_commit=?,updated=? WHERE candidate_id=?",
                    (user,request_id,evidence_hash,main,head,stamp,cid))
            st.db.commit()
            st.db.execute('BEGIN IMMEDIATE')
            team.require_reviewer(P,ticket['id'],user)
            view=candidates.view(P,cid)
            if (not authority.current(job) or view['evidence_hash']!=evidence_hash or
                    not view['human_accepted'] or not candidates.browser_review_current(P,cid) or
                    candidates._git(root,'rev-parse','HEAD').strip()!=head):
                raise ApiError(409,'准备合并期间授权、证据或主干已变化')
            mutation()
            if not recover:
                try:fast_forward(authority.image,root,row['base_commit'],row['commit_sha'],row['ref'],main)
                except ValueError as exc:raise ApiError(409,str(exc)) from exc
            try:verify_merged(authority.image,root,row['base_commit'],row['commit_sha'],row['ref'],main)
            except ValueError as exc:raise ApiError(409,str(exc)) from exc
            if candidates._git(root,'rev-parse','HEAD').strip()!=row['commit_sha']:
                raise ApiError(409,'合并后的版本不一致，请核对项目')
            st.db.execute("UPDATE candidate_merges SET state='merged',updated=? WHERE candidate_id=?",(now(),cid))
            st.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,'candidate_merge',?,?)",
                (ticket['id'],now(),user,'已合并固定候选到本地主干；尚未推送或部署',
                 candidates._json({'candidate':cid,'commit':row['commit_sha'],'main':main,'evidence_hash':evidence_hash})))
            st.db.commit()
            return dict(candidates.merge_receipt(P,cid),pushed=False,deployed=False,replayed=bool(recover))
        except BaseException:
            st.db.rollback()
            raise
