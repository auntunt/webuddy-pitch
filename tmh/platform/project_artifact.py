"""Create a fixed Git candidate from a screened workspace without editing the source repository.

This produces an immutable bundle and complete binary patch. Registration,
verification and human decisions are separate operations and are not implied.
"""
from __future__ import annotations

import hashlib
import json
import re
import tarfile
from pathlib import Path

from .project_container import Engine, specification
from .project_snapshot import MAX_ARCHIVE, validate_workspace

BUILD = r'''
import hashlib,io,json,os,stat,subprocess,sys,tarfile
base=sys.argv[1];lfs=json.load(open(sys.argv[2])) if len(sys.argv)>2 else {};env=dict(os.environ,GIT_INDEX_FILE='/tmp/job-index',
 GIT_ALTERNATE_OBJECT_DIRECTORIES='/source/.git/objects',GIT_AUTHOR_NAME='Webuddy',
 GIT_AUTHOR_EMAIL='webuddy@invalid',GIT_COMMITTER_NAME='Webuddy',GIT_COMMITTER_EMAIL='webuddy@invalid')
subprocess.run(['git','init','--bare','-q','/tmp/job.git'],env=env,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
cmd=['git','--git-dir=/tmp/job.git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-c','commit.gpgsign=false']
def git(args,data=None):
 p=subprocess.run(cmd+args,input=data,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if p.returncode:raise RuntimeError('Git candidate preparation failed')
 return p.stdout
assert git(['rev-parse','--verify',base+'^{commit}']).decode().strip()==base
git(['read-tree','--empty']);items=[];paths=[];count=total=0
for root,dirs,files in os.walk('/workspace',followlinks=False):
 dirs.sort();files.sort()
 for name in dirs+files:
  path=os.path.join(root,name);st=os.lstat(path);rel=os.path.relpath(path,'/workspace')
  if stat.S_ISLNK(st.st_mode) or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):raise RuntimeError('Unsupported project output entry')
  if stat.S_ISDIR(st.st_mode):continue
  if st.st_nlink!=1 or st.st_size>268435456:raise RuntimeError('Unsupported project output file')
  count+=1;total+=st.st_size
  if count>100000 or total>536870912:raise RuntimeError('Project output exceeds limit')
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
  with os.fdopen(fd,'rb') as f:
   fresh=os.fstat(f.fileno())
   if (fresh.st_ino,fresh.st_dev,fresh.st_size)!=(st.st_ino,st.st_dev,st.st_size):raise RuntimeError('Project output changed')
   data=f.read()
  if rel in lfs:
   item=lfs[rel]
   if len(data)!=item['size'] or hashlib.sha256(data).hexdigest()!=item['oid']:raise RuntimeError('Modified LFS file requires explicit LFS publication')
   entry=git(['ls-tree','-z',base,'--',rel]).split(b'\t',1)
   if len(entry)!=2 or entry[0].split()[-1].decode('ascii')!=item['pointer_blob']:raise RuntimeError('LFS baseline mismatch')
   pointer=git(['cat-file','blob',item['pointer_blob']])
   if (b'oid sha256:'+item['oid'].encode('ascii')) not in pointer:raise RuntimeError('LFS pointer mismatch')
   sha=item['pointer_blob'].encode('ascii')
  else:sha=git(['hash-object','-w','--stdin'],data).strip()
  mode=b'100755' if st.st_mode&0o111 else b'100644'
  items.append(mode+b' '+sha+b'\t'+rel.encode('utf-8')+b'\0')
  paths.append(rel)
git(['update-index','-z','--index-info'],b''.join(items))
attrs=git(['check-attr','--cached','-z','--stdin','filter'],b''.join(p.encode('utf-8')+b'\0' for p in paths)).split(b'\0')
for i in range(0,len(attrs)-1,3):
 name=attrs[i].decode('utf-8','strict');value=attrs[i+2]
 if (value==b'lfs') != (name in lfs):raise RuntimeError('LFS attribute change requires explicit LFS publication')
tree=git(['write-tree']).decode().strip()
patch=git(['diff','--cached','--binary','--no-ext-diff','--no-textconv',base,'--'])
if not patch:raise RuntimeError('Project output has no changes')
changes=git(['diff','--cached','--name-status','-z','--no-renames',base,'--']).split(b'\0')
deleted=[]
for i in range(0,len(changes)-1,2):
 if changes[i]==b'D':deleted.append(changes[i+1].decode('utf-8','strict'))
commit=git(['commit-tree',tree,'-p',base],b'Webuddy isolated project candidate\n').decode().strip()
git(['update-ref','refs/heads/candidate',commit])
git(['bundle','create','/tmp/candidate.bundle','refs/heads/candidate','^'+base])
with open('/tmp/candidate.bundle','rb') as f:bundle=f.read()
manifest={'base_commit':base,'commit':commit,'tree':tree,'files':count,'bytes':total,'deleted_files':deleted,
 'patch_sha256':hashlib.sha256(patch).hexdigest(),'bundle_sha256':hashlib.sha256(bundle).hexdigest()}
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as out:
 for name,data in [('manifest.json',json.dumps(manifest,separators=(',',':')).encode()),('change.patch',patch),('candidate.bundle',bundle)]:
  info=tarfile.TarInfo(name);info.mode=0o600;info.size=len(data);out.addfile(info,io.BytesIO(data))
'''

INSTALL = r'''
import hashlib,json,os,subprocess,sys
base,commit,ref,expected_bundle,expected_patch=sys.argv[1:]
if hashlib.sha256(open('/workspace/candidate.bundle','rb').read()).hexdigest()!=expected_bundle:raise RuntimeError('bundle digest mismatch')
env=dict(os.environ,GIT_ALLOW_PROTOCOL='file')
cmd=['git','--git-dir=/source/.git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
 '-c','gc.auto=0','-c','maintenance.auto=false','-c','protocol.file.allow=always']
def git(args,check=True):
 p=subprocess.run(cmd+args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if check and p.returncode:raise RuntimeError('candidate Git operation failed')
 return p
heads=git(['bundle','list-heads','/workspace/candidate.bundle']).stdout.decode('ascii').strip().splitlines()
if heads!=[commit+' refs/heads/candidate']:raise RuntimeError('bundle target mismatch')
git(['fetch','--no-tags','--no-write-fetch-head','/workspace/candidate.bundle','refs/heads/candidate'])
if git(['rev-list','--parents','-n','1',commit]).stdout.decode('ascii').strip()!=commit+' '+base:raise RuntimeError('candidate parent mismatch')
diff=git(['diff','--binary','--no-ext-diff','--no-textconv',base,commit,'--']).stdout
if hashlib.sha256(diff).hexdigest()!=expected_patch:raise RuntimeError('candidate patch mismatch')
old=git(['rev-parse','--verify','--quiet',ref],check=False)
if old.returncode==0:
 if old.stdout.decode('ascii').strip()!=commit:raise RuntimeError('candidate reference mismatch')
else:git(['update-ref',ref,commit,'0'*40])
print(json.dumps({'commit':commit,'base_commit':base,'ref':ref},separators=(',',':')))
'''


def create(image, source, workspace, base_commit, folder, *, lfs=None, cancel=lambda:False, engine=None):
    if not re.fullmatch('[0-9a-f]{40}', base_commit) or not validate_workspace(workspace):
        raise ValueError('项目候选的基线或工作区无效')
    source, folder = Path(source), Path(folder)
    if not (source / '.git').is_dir() or (source / '.git').is_symlink() or folder.exists():
        raise ValueError('项目仓库或候选保存位置不可用')
    folder.mkdir(parents=True, mode=0o700)
    lfs=lfs or {}
    if not isinstance(lfs,dict):raise ValueError('Git LFS 来源记录无效')
    (folder/'lfs-input.json').write_text(json.dumps(lfs,ensure_ascii=False),encoding='utf-8')
    output = folder / 'candidate.tar'
    try:
        size = 0
        diagnostics = bytearray()
        with output.open('x+b') as stream:
            def collect(chunk):
                nonlocal size
                size += len(chunk)
                if size > MAX_ARCHIVE + 128 * 1024 * 1024:
                    raise ValueError('项目候选超过大小上限')
                stream.write(chunk)
            def diagnostic(chunk):
                if len(diagnostics) + len(chunk) <= 65536:
                    diagnostics.extend(chunk)
            spec=specification(image,['python3','-I','-c',BUILD,base_commit,'/meta/lfs-input.json'],workspace,120,
                               mounts=[(source,'/source')])
            spec['HostConfig']['Mounts'].append({'Type':'bind','Source':str(folder.resolve()),'Target':'/meta','ReadOnly':True})
            receipt = (engine or Engine()).run(spec,120,cancel=cancel,output=collect,diagnostic=diagnostic)
            if receipt.get('reason')!='exited' or receipt.get('returncode')!=0 or receipt.get('cleanup') is not True:
                raise ValueError('固定版本候选生成失败或隔离容器未回收；原结果已保留')
            stream.flush();stream.seek(0)
            with tarfile.open(fileobj=stream,mode='r:*') as tar:
                members=tar.getmembers()
                if [x.name for x in members] != ['manifest.json','change.patch','candidate.bundle'] or any(not x.isfile() for x in members):
                    raise ValueError('项目候选产物格式不正确')
                if members[0].size>4096 or any(x.size>MAX_ARCHIVE for x in members):
                    raise ValueError('项目候选产物超过上限')
                manifest=json.load(tar.extractfile(members[0]))
                if manifest.get('base_commit')!=base_commit or any(not re.fullmatch('[0-9a-f]{40}',manifest.get(k,'')) for k in ('commit','tree')):
                    raise ValueError('项目候选的固定版本不正确')
                deleted=manifest.get('deleted_files')
                if (not isinstance(deleted,list) or any(not isinstance(name,str) or not name for name in deleted)
                        or len(set(deleted))!=len(deleted)):
                    raise ValueError('项目候选的删除文件清单不完整')
                for member,key in ((members[1],'patch_sha256'),(members[2],'bundle_sha256')):
                    digest=hashlib.sha256()
                    with tar.extractfile(member) as src, (folder/member.name).open('xb') as dst:
                        while True:
                            chunk=src.read(1024*1024)
                            if not chunk:break
                            digest.update(chunk);dst.write(chunk)
                    if digest.hexdigest()!=manifest.get(key):
                        raise ValueError('项目候选产物摘要不一致')
        return dict(manifest,artifact_dir=str(folder),cleanup=True)
    except BaseException:
        # Retain partial files for diagnosis; never describe them as candidates.
        raise


def install(image, source, folder, manifest, fingerprint, *, cancel=lambda:False, engine=None):
    """Install only the verified commit under its generated candidate ref.

    Caller must hold the personal authorization guard and reconcile failures:
    a transport error can leave the atomic ref update's result unknown.
    """
    source,folder=Path(source),Path(folder)
    if (not isinstance(fingerprint,str) or not re.fullmatch('[0-9a-f]{64}',fingerprint) or
            not (source/'.git').is_dir() or (source/'.git').is_symlink()):
        raise ValueError('候选引用或项目仓库无效')
    for key,length in (('base_commit',40),('commit',40),('bundle_sha256',64),('patch_sha256',64)):
        if not isinstance(manifest.get(key),str) or not re.fullmatch('[0-9a-f]{%d}' % length,manifest[key]):
            raise ValueError('候选固定版本或摘要无效')
    bundle=folder/'candidate.bundle'
    if bundle.is_symlink() or not bundle.is_file():
        raise ValueError('候选 bundle 不可用')
    with bundle.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=manifest['bundle_sha256']:
            raise ValueError('候选 bundle 已变化')
    ref='refs/webuddy/candidates/'+fingerprint
    spec=specification(image,['python3','-I','-c',INSTALL,manifest['base_commit'],manifest['commit'],ref,
                              manifest['bundle_sha256'],manifest['patch_sha256']],folder,60,mounts=[(source,'/source')])
    spec['HostConfig']['Mounts'][1]['ReadOnly']=False  # Only this fixed trusted Git installer writes repository objects/refs.
    output=[]
    result=(engine or Engine()).run(spec,60,cancel=cancel,output=output.append)
    if result.get('reason')!='exited' or result.get('returncode')!=0 or result.get('cleanup') is not True:
        raise ValueError('候选引用结果未知，请核对原操作后再重试')
    try:value=json.loads(b''.join(output))
    except (ValueError,UnicodeDecodeError):raise ValueError('候选引用回执无法核对') from None
    if value!={'base_commit':manifest['base_commit'],'commit':manifest['commit'],'ref':ref}:
        raise ValueError('候选引用回执与固定版本不一致')
    return dict(value,cleanup=True)
