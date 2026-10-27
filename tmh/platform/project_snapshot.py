"""Export a fixed, screened Git tree for a project-only execution container.

The Git repository is only mounted into a separate, network-disabled exporter.
The execution container receives regular files, never the repository metadata.
An unsupported or sensitive entry aborts the entire export; it is not omitted.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile

from .project_container import Engine, specification
from .project_git import valid_ref

MAX_ARCHIVE = 512 * 1024 * 1024
MAX_FILE = 256 * 1024 * 1024
MAX_FILES = 100000
KEY_EXTENSIONS = ('.pem', '.key', '.p12', '.pfx', '.jks', '.keystore', '.crt', '.cer')

# Executed only in the fixed image with the source mounted read-only. No
# worktree, hooks, filters or repository-provided scripts are executed.
EXPORT = r'''
import hashlib,io,json,os,re,subprocess,sys,tarfile
ref=sys.argv[1]
base=['git','--no-optional-locks','-c','safe.directory=/source','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-C','/source']
def git(*args):
    p=subprocess.run(base+list(args),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise RuntimeError('git source read failed')
    return p.stdout
def blocked(name,reason):
    sys.stderr.write('WEBUDDY_BLOCK:'+json.dumps({'path':name,'reason':reason},ensure_ascii=True)+'\n')
    raise SystemExit(2)
def path_check(name):
    for part in name.split('/'):
        low=part.casefold()
        if (not part or part in ('.','..') or low in ('.git','.tmh','.ssh','.aws','.kube','.gnupg','.netrc','.npmrc','.pypirc')
            or low.endswith(('.pem','.key','.p12','.pfx','.jks','.keystore','.crt','.cer'))):
            blocked(name,'凭据、密钥或不安全路径不能交给执行器')
def pointer(data):
    return re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\r?\noid sha256:([0-9a-f]{64})\r?\nsize ([0-9]+)\r?\n?',data)
def clean_workspace():
    committed={}
    for item in git('ls-tree','-rz','--full-tree','-r','HEAD').split(b'\0'):
        if not item:continue
        header,name=item.split(b'\t',1);mode,kind,sha=header.split();committed[name]=(mode,sha,kind)
    index={}
    for item in git('ls-files','--stage','-z').split(b'\0'):
        if not item:continue
        header,name=item.split(b'\t',1);mode,sha,stage=header.split()
        if stage!=b'0' or name in index:blocked(name.decode('utf-8','strict'),'工作区存在未解决的索引冲突')
        index[name]=(mode,sha,b'blob' if mode in (b'100644',b'100755',b'120000') else b'commit')
    if index!=committed:
        changed=next(iter(set(index)^set(committed)),None) or next(n for n in index if index[n]!=committed[n])
        blocked(changed.decode('utf-8','strict'),'工作区有已暂存的未提交源码')
    for raw,(mode,sha,kind) in index.items():
        name=raw.decode('utf-8','strict');path_check(name)
        if kind!=b'blob' or mode not in (b'100644',b'100755'):blocked(name,'不支持符号链接、子模块或特殊文件')
        path='/source/'+name
        try:
            st=os.lstat(path)
            if not os.path.isfile(path) or os.path.islink(path) or st.st_size>268435456:blocked(name,'工作区文件不可用或超过大小限制')
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as f:data=f.read(268435457)
        except OSError:blocked(name,'工作区文件不可读取')
        actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest().encode()
        if actual!=sha:
            blob=git('cat-file','blob',sha.decode('ascii'));match=pointer(blob)
            if not match or len(data)!=int(match.group(2)) or hashlib.sha256(data).hexdigest().encode()!=match.group(1):
                blocked(name,'工作区有未提交源码或依赖不支持的 Git 过滤规则')
        if bool(st.st_mode&0o111)!=(mode==b'100755'):blocked(name,'工作区文件权限已变化')
    for args in (('ls-files','--others','--exclude-standard','--directory','-z'),
                 ('ls-files','--others','--ignored','--exclude-standard','--directory','-z')):
        for raw in git(*args).split(b'\0'):
            if not raw:continue
            name=raw.decode('utf-8','strict')
            if name=='.tmh' or name.startswith('.tmh/'):continue
            blocked(name,'工作区包含未提交或被忽略的文件，不能静默省略')
clean_workspace()
commit=git('rev-parse','--verify','--end-of-options',ref+'^{commit}').decode('ascii').strip()
entries=git('ls-tree','-rz','--full-tree','-r',commit).split(b'\0')
if len(entries)>100001: raise RuntimeError('too many files')
lfs={}
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as out:
    data=json.dumps({'commit':commit},separators=(',',':')).encode()
    info=tarfile.TarInfo('MANIFEST.json');info.size=len(data);out.addfile(info,io.BytesIO(data))
    for entry in entries:
        if not entry: continue
        header,name=entry.split(b'\t',1);mode,kind,sha=header.split()
        name=name.decode('utf-8','strict')
        if kind!=b'blob' or mode not in (b'100644',b'100755'): blocked(name,'不支持符号链接、子模块或特殊文件')
        path_check(name)
        data=git('cat-file','blob',sha.decode('ascii'))
        if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
            match=pointer(data)
            if not match:blocked(name,'Git LFS 指针格式不受支持')
            oid=match.group(1).decode('ascii');size=int(match.group(2))
            if size>268435456:blocked(name,'Git LFS 原文件超过隔离工作区大小限制')
            obj='/source/.git/lfs/objects/'+oid[:2]+'/'+oid[2:4]+'/'+oid
            parts=['/source/.git/lfs','/source/.git/lfs/objects','/source/.git/lfs/objects/'+oid[:2],
                   '/source/.git/lfs/objects/'+oid[:2]+'/'+oid[2:4],obj]
            if any(os.path.islink(part) for part in parts):blocked(name,'Git LFS 对象路径包含符号链接')
            try:
                fd=os.open(obj,os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,'rb') as f:data=f.read(size+1)
            except OSError:blocked(name,'固定版本的 Git LFS 原文件不可用')
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=oid:blocked(name,'Git LFS 原文件大小或摘要不匹配')
            lfs[name]={'oid':oid,'size':size,'pointer_blob':sha.decode('ascii')}
        if len(data)>268435456: blocked(name,'文件超过隔离工作区大小限制')
        # Detect high-confidence secrets without printing their contents.
        if (re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',data)
            or re.search(rb'AKIA[0-9A-Z]{16}',data)
            or re.search(rb'(?im)^\s*(?:export\s+)?[A-Za-z0-9_]*(?:API_KEY|ACCESS_TOKEN|SECRET_KEY|PASSWORD)\s*[=:]\s*["\']?[A-Za-z0-9_+/=-]{20,}',data)
            or re.search(rb'(?i)"[A-Za-z0-9_]*(?:API_?KEY|ACCESS_?TOKEN|SECRET_?KEY|PASSWORD)"\s*:\s*"[A-Za-z0-9_+/=-]{20,}"',data)):
            blocked(name,'内容疑似包含凭据，需要人工检查')
        if name.rsplit('/',1)[-1].lower().startswith('.env'):
            for line in data.splitlines():
                m=re.match(rb'\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$',line)
                if not m or not re.search(rb'(?:SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE.?KEY|ACCESS.?KEY|API.?KEY|AUTH)',m.group(1),re.I):
                    continue
                value=m.group(2).strip(b' \t\"\'')
                if value and not re.fullmatch(rb'(?:\$\{[^}]+\}|<[^>]+>|your[_-].*|changeme|placeholder|example)',value,re.I):
                    blocked(name,'环境配置的敏感字段非空，需要人工检查')
        info=tarfile.TarInfo('tree/'+name);info.size=len(data);info.mode=0o755 if mode==b'100755' else 0o644
        out.addfile(info,io.BytesIO(data))
    metadata=json.dumps(lfs,ensure_ascii=True,separators=(',',':')).encode()
    info=tarfile.TarInfo('LFS.json');info.size=len(metadata);out.addfile(info,io.BytesIO(metadata))
clean_workspace()
'''

CHECK = EXPORT.split("clean_workspace()\ncommit=", 1)[0] + r'''
clean_workspace()
commit=git('rev-parse','--verify','--end-of-options',ref+'^{commit}').decode('ascii').strip()
if commit!=sys.argv[2]:raise RuntimeError('source revision changed')
print('current')
'''
RESOLVE = EXPORT.split("clean_workspace()\ncommit=", 1)[0] + r'''
clean_workspace()
commit=git('rev-parse','--verify','--end-of-options',ref+'^{commit}').decode('ascii').strip()
print(commit)
'''


def _safe_name(name):
    path = PurePosixPath(name)
    parts = path.parts
    if (not parts or path.is_absolute() or any(p in ('', '.', '..') for p in parts)
            or '\\' in name or '\x00' in name or any(ord(c) < 32 for c in name)):
        raise ValueError('代码路径不安全')
    for part in parts:
        low = part.casefold()
        if (low in ('.git', '.tmh', '.ssh', '.aws', '.kube', '.gnupg', '.netrc', '.npmrc', '.pypirc')
                or low.endswith(KEY_EXTENSIONS)):
            raise ValueError('固定版本包含凭据或密钥相关路径，不能交给项目执行器：' + name)
    return path


def unpack(stream, destination):
    """Validate every entry before copying; leave no partial tree on failure."""
    destination = Path(destination)
    if destination.exists() or not destination.is_absolute():
        raise ValueError('隔离工作区必须是新的绝对路径')
    destination.mkdir(mode=0o700)
    try:
        with tarfile.open(fileobj=stream, mode='r:*') as archive:
            entries = archive.getmembers()
            if not entries or entries[0].name != 'MANIFEST.json' or not entries[0].isfile():
                raise ValueError('源码快照缺少版本记录')
            if entries[0].size > 4096 or len(entries) > MAX_FILES + 2:
                raise ValueError('源码快照超出限制')
            manifest = json.loads(archive.extractfile(entries[0]).read())
            if set(manifest) != {'commit'} or not re.fullmatch('[0-9a-f]{40}', manifest['commit']):
                raise ValueError('源码快照版本无效')
            seen = set();files=set();lfs={}
            total = 0
            for index,entry in enumerate(entries[1:],start=1):
                if entry.name=='LFS.json' and index==len(entries)-1 and entry.isfile() and entry.size<=16*1024*1024:
                    lfs=json.load(archive.extractfile(entry))
                    if not isinstance(lfs,dict):raise ValueError('Git LFS 来源记录无效')
                    continue
                if not (entry.isfile() or entry.isdir()) or not entry.name.startswith('tree/'):
                    raise ValueError('源码快照含有不支持的条目')
                path = _safe_name(entry.name[5:])
                if str(path) in seen or entry.size > MAX_FILE:
                    raise ValueError('源码快照路径重复或文件过大')
                seen.add(str(path))
                target = destination.joinpath(*path.parts)
                if entry.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                total += entry.size
                if total > MAX_ARCHIVE:
                    raise ValueError('源码快照超出限制')
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(entry) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                files.add(str(path))
                target.chmod(0o700 if entry.mode & 0o111 else 0o600)
            for name,record in lfs.items():
                if (name not in files or not isinstance(record,dict) or set(record)!={'oid','size','pointer_blob'} or
                        not re.fullmatch('[0-9a-f]{64}',str(record['oid'])) or
                        not re.fullmatch('[0-9a-f]{40}',str(record['pointer_blob'])) or
                        type(record['size']) is not int or not 0<=record['size']<=MAX_FILE):
                    raise ValueError('Git LFS 来源记录无效')
                with destination.joinpath(*PurePosixPath(name).parts).open('rb') as source:
                    if hashlib.file_digest(source,'sha256').hexdigest()!=record['oid']:
                        raise ValueError('Git LFS 导出内容摘要不匹配')
                if destination.joinpath(*PurePosixPath(name).parts).stat().st_size!=record['size']:
                    raise ValueError('Git LFS 导出内容大小不匹配')
        return {'commit': manifest['commit'], 'files': len(files), 'bytes': total, 'lfs':lfs}
    except BaseException:
        shutil.rmtree(destination)
        raise


def validate_workspace(destination):
    """Reject links, special files and sensitive paths on every tool request."""
    destination = Path(destination)
    try:
        if not destination.is_absolute() or any(p.is_symlink() for p in (destination, *destination.parents)):
            return False
        count = total = 0
        for root, dirs, files in os.walk(destination, followlinks=False):
            for name in dirs + files:
                path = Path(root) / name
                _safe_name(path.relative_to(destination).as_posix())
                info = path.lstat()
                if path.is_symlink() or not (path.is_dir() or path.is_file()):
                    return False
                if path.is_file():
                    count += 1
                    total += info.st_size
                    if info.st_nlink != 1 or info.st_size > MAX_FILE:
                        return False
                if count > MAX_FILES or total > MAX_ARCHIVE:
                    return False
        return destination.is_dir()
    except (OSError, ValueError):
        return False


def create(image, source, destination, ref='HEAD', *, cancel=lambda: False, engine=None):
    if not valid_ref(ref) or ref.endswith('^{commit}'):
        raise ValueError('指定的源码版本无效')
    source = Path(source)
    if not (source / '.git').is_dir() or (source / '.git').is_symlink():
        raise ValueError('项目尚未接入受支持的 Git 仓库')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='project-export-', dir=destination.parent) as temp:
        temp = Path(temp)
        empty = temp / 'empty'
        empty.mkdir(mode=0o700)
        archive_path = temp / 'snapshot.tar'
        with archive_path.open('w+b') as archive:
            size = 0
            diagnostics = bytearray()
            def collect(chunk):
                nonlocal size
                size += len(chunk)
                if size > MAX_ARCHIVE:
                    raise ValueError('源码快照超出限制')
                archive.write(chunk)
            def diagnostic(chunk):
                if len(diagnostics) + len(chunk) <= 65536:
                    diagnostics.extend(chunk)
            result = (engine or Engine()).run(
                specification(image, ['python3', '-I', '-c', EXPORT, ref], empty, 120,
                              mounts=[(source, '/source')]), 120, cancel=cancel, output=collect, diagnostic=diagnostic)
            if result.get('reason') != 'exited' or result.get('returncode') != 0 or result.get('cleanup') is not True:
                for line in diagnostics.decode('utf-8', 'replace').splitlines():
                    if line.startswith('WEBUDDY_BLOCK:'):
                        try:
                            detail = json.loads(line[len('WEBUDDY_BLOCK:'):])
                            name = detail['path']
                            reason = detail['reason']
                            if isinstance(name, str) and isinstance(reason, str) and len(name) <= 500 and len(reason) <= 100:
                                raise ValueError('源码导出受阻：%s（%s）' % (name, reason))
                        except (KeyError, TypeError, json.JSONDecodeError):
                            pass
                raise ValueError('固定版本源码导出失败或容器回收未确认')
            archive.flush()
            archive.seek(0)
            digest = hashlib.file_digest(archive, 'sha256').hexdigest()
            archive.seek(0)
            snapshot = unpack(archive, destination)
    return dict(snapshot, archive_sha256=digest, cleanup=True)


def current(image, source, ref, commit, *, cancel=lambda: False, engine=None):
    """Recheck the chosen source and dirty state without reading it into Python."""
    if not valid_ref(ref) or ref.endswith('^{commit}') or not re.fullmatch('[0-9a-f]{40}',commit):
        return False
    with tempfile.TemporaryDirectory(prefix='project-source-check-') as raw:
        empty=Path(raw).resolve()/'empty'
        empty.mkdir(mode=0o700)
        result=(engine or Engine()).run(
            specification(image,['python3','-I','-c',CHECK,ref,commit],empty,30,
                          mounts=[(Path(source),'/source')]),30,cancel=cancel,output=lambda chunk:None)
        return result.get('reason')=='exited' and result.get('returncode')==0 and result.get('cleanup') is True


def resolve(image, source, ref='HEAD', *, cancel=lambda: False, engine=None):
    if not valid_ref(ref) or ref.endswith('^{commit}'):
        raise ValueError('指定的项目源码版本无效')
    with tempfile.TemporaryDirectory(prefix='project-source-resolve-') as raw:
        empty=Path(raw).resolve()/'empty';empty.mkdir(mode=0o700)
        output=[];diagnostic=[]
        result=(engine or Engine()).run(
            specification(image,['python3','-I','-c',RESOLVE,ref],empty,30,
                          mounts=[(Path(source),'/source')]),30,cancel=cancel,
            output=output.append,diagnostic=diagnostic.append)
        commit=b''.join(output).decode('ascii','strict').strip()
        if (result.get('reason')!='exited' or result.get('returncode')!=0 or result.get('cleanup') is not True
                or not re.fullmatch('[0-9a-f]{40}',commit)):
            for line in b''.join(diagnostic).decode('utf-8','replace').splitlines():
                if line.startswith('WEBUDDY_BLOCK:'):
                    try:
                        detail=json.loads(line[len('WEBUDDY_BLOCK:'):])
                        name,reason=detail['path'],detail['reason']
                        if isinstance(name,str) and isinstance(reason,str) and len(name)<=500 and len(reason)<=100:
                            raise ValueError('项目源码暂不可执行：%s（%s）' % (name,reason))
                    except (KeyError,TypeError,json.JSONDecodeError):
                        pass
            raise ValueError('项目固定源码版本不可用或隔离容器未回收')
        return commit
