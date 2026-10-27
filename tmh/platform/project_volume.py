"""Hard-limited, temporary workspace volume for untrusted project tools."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import threading
import time
import uuid

from .project_container import specification
from .project_snapshot import MAX_ARCHIVE, unpack, validate_workspace


LOAD = r'''
import shutil
shutil.copytree('/source','/workspace',dirs_exist_ok=True,symlinks=False)
'''

SAVE = r'''
import io,json,os,stat,sys,tarfile
base='/workspace';commit=sys.argv[1]
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as tar:
    data=json.dumps({'commit':commit},separators=(',',':')).encode()
    info=tarfile.TarInfo('MANIFEST.json');info.size=len(data);tar.addfile(info,io.BytesIO(data))
    for root,dirs,files in os.walk(base,followlinks=False):
        dirs.sort();files.sort()
        for name in dirs+files:
            path=os.path.join(root,name);rel=os.path.relpath(path,base);st=os.lstat(path)
            if stat.S_ISLNK(st.st_mode):
                info=tarfile.TarInfo('tree/'+rel);info.type=tarfile.SYMTYPE;info.linkname=os.readlink(path);tar.addfile(info);continue
            if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                raise RuntimeError('unsupported output entry')
            info=tarfile.TarInfo('tree/'+rel)
            if stat.S_ISDIR(st.st_mode):
                info.type=tarfile.DIRTYPE;info.mode=0o700;tar.addfile(info);continue
            if st.st_nlink!=1 or st.st_size>268435456: raise RuntimeError('unsupported output file')
            info.size=st.st_size;info.mode=0o755 if st.st_mode & 0o111 else 0o644
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as source:
                current=os.fstat(source.fileno())
                if (current.st_ino,current.st_dev,current.st_size)!=(st.st_ino,st.st_dev,st.st_size):
                    raise RuntimeError('output changed during export')
                tar.addfile(info,source)
'''

# This fixed maintenance process has no project or provider mount. It can only
# remove its own random-labelled anchor and volume. It survives owner SIGKILL
# long enough to collect those exact resources, then Docker auto-removes it.
JANITOR = r'''
import http.client,json,socket,sys,time
anchor,volume,nonce,seconds=sys.argv[1:];deadline=time.monotonic()+float(seconds);grace=time.monotonic()+10;seen=False
class Conn(http.client.HTTPConnection):
 def connect(self):
  self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(3);self.sock.connect('/control/docker.sock')
def call(method,path):
 c=Conn('localhost',timeout=3)
 try:
  c.request(method,'/v1.45'+path);r=c.getresponse();body=r.read()
  return r.status,(json.loads(body) if body and r.status<300 else None)
 finally:c.close()
while time.monotonic()<deadline:
 try:
  ac,ar=call('GET','/containers/'+anchor+'/json');vc,vr=call('GET','/volumes/'+volume)
  if ac==200:
   if (ar.get('Config',{}).get('Labels') or {}).get('webuddy.owner')!=nonce:raise RuntimeError('anchor owner mismatch')
   seen=True
  if vc==200 and (vr.get('Labels') or {}).get('webuddy.owner')!=nonce:raise RuntimeError('volume owner mismatch')
  if (seen or time.monotonic()>=grace) and (ac==404 or ac==200 and not ar.get('State',{}).get('Running')):
   if ac==200:call('DELETE','/containers/'+anchor+'?force=1')
   if vc==200:call('DELETE','/volumes/'+volume)
   ac,_=call('GET','/containers/'+anchor+'/json');vc,_=call('GET','/volumes/'+volume)
   if ac==404 and vc==404:sys.exit(0)
 except (OSError,http.client.HTTPException):pass
 time.sleep(.2)
sys.exit(1)
'''


class ProjectVolume:
    SIZE = 512 * 1024 * 1024

    def __init__(self, engine, image, workspace, seconds, cancel):
        self.engine, self.image = engine, image
        self.workspace, self.seconds, self.cancel = Path(workspace), seconds, cancel
        self.name = 'webuddy-job-' + uuid.uuid4().hex
        self.nonce = uuid.uuid4().hex
        self.anchor_name = 'webuddy-project-' + self.nonce
        self.janitor_name = 'webuddy-janitor-' + uuid.uuid4().hex
        self.janitor_id = ''
        self.stop = threading.Event()
        self.created = threading.Event()
        self.receipt = {}
        self.cid = ''
        self.errors = []
        self.thread = None
        self._temp = None
        self.volume_created = False

    def _spec(self, command, seconds, *, source=False):
        spec = specification(self.image, command, self.empty, seconds,
                             mounts=[(self.workspace, '/source')] if source else ())
        spec['HostConfig']['Mounts'][0] = {'Type':'volume', 'Source':self.name,
                                           'Target':'/workspace', 'ReadOnly':False}
        return spec

    def _start_janitor(self):
        socket_path = Path(self.engine.path)
        info = socket_path.lstat()
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
                or any(p.is_symlink() for p in (socket_path, *socket_path.parents))):
            raise ValueError('项目清理通道不可用')
        spec = specification(self.image, ['python3','-c','pass'], self.empty, self.seconds + 30)
        spec.update(Entrypoint=['python3','-I','-u','-c',JANITOR],
                    Cmd=[self.anchor_name,self.name,self.nonce,str(self.seconds + 30)],
                    OpenStdin=False,AttachStdin=False,AttachStdout=False,AttachStderr=False,
                    Labels={'webuddy.janitor':self.nonce})
        spec['HostConfig']['Mounts'] = [{'Type':'bind','Source':str(socket_path),
                                         'Target':'/control/docker.sock','ReadOnly':True}]
        spec['HostConfig']['AutoRemove'] = True
        try:
            created = self.engine.request('POST','/containers/create?name='+self.janitor_name,spec)
            if not re.fullmatch('[0-9a-f]{64}',created.get('Id','')):
                raise ValueError('项目清理任务身份无效')
            self.janitor_id = created['Id']
            self.engine.request('POST','/containers/'+self.janitor_id+'/start')
        except BaseException:
            if self.janitor_id:
                self.engine.request('DELETE','/containers/'+self.janitor_id+'?force=1',missing=True)
            raise

    def __enter__(self):
        if not validate_workspace(self.workspace):
            raise ValueError('项目源码副本不可用')
        self._temp = tempfile.TemporaryDirectory(prefix='webuddy-volume-')
        self.empty = Path(self._temp.name).resolve() / 'empty'
        self.empty.mkdir(mode=0o700)
        try:
            info = self.engine.request('GET', '/info')
            if not any('rootless' in item for item in info.get('SecurityOptions', [])):
                raise ValueError('拒绝在非 rootless daemon 创建项目工作区')
            self._start_janitor()
            self.engine.request('POST', '/volumes/create', {'Name':self.name, 'Driver':'local',
                'Labels':{'webuddy.owner':self.nonce},
                'DriverOpts':{'type':'tmpfs', 'device':'tmpfs', 'o':'size=%d' % self.SIZE}})
            self.volume_created = True
            def anchor():
                try:
                    spec = self._spec(['python3','-c','import time;time.sleep(%s)' % self.seconds], self.seconds)
                    def created(cid):
                        self.cid = cid
                        self.created.set()
                    self.engine.run(spec, self.seconds, cancel=lambda: self.stop.is_set() or self.cancel(),
                                    receipt=self.receipt, on_created=created, owner_nonce=self.nonce)
                except BaseException as exc:
                    self.errors.append(type(exc).__name__)
                    self.created.set()
            self.thread = threading.Thread(target=anchor, daemon=True)
            self.thread.start()
            if not self.created.wait(min(10, self.seconds)) or self.errors:
                raise ValueError('项目工作区固定容器启动失败')
            # The volume exists only while at least one container keeps the
            # tmpfs mounted. The anchor remains alive for the entire run.
            deadline = time.monotonic() + min(10, self.seconds)
            while time.monotonic() < deadline:
                if self.errors or not self.thread.is_alive() or self.cancel():
                    raise ValueError('项目工作区固定容器不可用')
                state = self.engine.request('GET', '/containers/' + self.cid + '/json').get('State', {})
                if not state.get('Running'):
                    time.sleep(.05)
                    continue
                result = self.engine.run(self._spec(['python3','-I','-c',LOAD], 60, source=True),
                                         60, cancel=lambda: self.cancel() or not self.thread.is_alive())
                break
            else:
                raise ValueError('项目工作区准备超时')
            if result.get('reason') != 'exited' or result.get('returncode') != 0 or result.get('cleanup') is not True:
                raise ValueError('项目工作区复制失败或回收未确认')
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def spec(self, command, seconds):
        if not self.thread or not self.thread.is_alive() or self.errors:
            raise ValueError('项目工作区已失去所有权')
        return self._spec(command, seconds)

    def alive(self):
        return bool(self.thread and self.thread.is_alive() and not self.errors and not self.stop.is_set())

    def export(self, commit):
        if not self.alive() or self.cancel():
            raise ValueError('项目工作区已停止，不能读取结果')
        archive_path = self.workspace.parent / (self.workspace.name + '.result-' + uuid.uuid4().hex + '.tar')
        with archive_path.open('x+b') as archive:
            archive_path.chmod(0o600)
            size = 0
            def collect(chunk):
                nonlocal size
                size += len(chunk)
                if size > MAX_ARCHIVE + 128 * 1024 * 1024:
                    raise ValueError('项目结果超出大小限制')
                archive.write(chunk)
            result = self.engine.run(self._spec(['python3','-I','-c',SAVE,commit], 60),
                                     60, cancel=lambda:self.cancel() or not self.alive(), output=collect)
            if result.get('reason') != 'exited' or result.get('returncode') != 0 or result.get('cleanup') is not True:
                raise ValueError('项目结果导出失败或回收未确认；已保留导出现场：' + str(archive_path))
            archive.flush();archive.seek(0)
            candidate = self.workspace.parent / (self.workspace.name + '.result-' + uuid.uuid4().hex)
            try:
                info = unpack(archive, candidate)
            except Exception as exc:
                raise ValueError('项目结果不能安全导入；已保留完整导出现场：' + str(archive_path)) from exc
        backup = self.workspace.parent / (self.workspace.name + '.original-' + uuid.uuid4().hex)
        os.rename(self.workspace, backup)
        try:
            os.rename(candidate, self.workspace)
        except BaseException:
            os.rename(backup, self.workspace)
            raise
        archive_path.unlink()
        info.pop('commit')
        return dict(info, base_commit=commit, original_workspace=str(backup))

    def __exit__(self, typ, value, traceback):
        self.stop.set()
        if self.thread:
            self.thread.join(10)
        cleaned = not self.thread or (not self.thread.is_alive() and self.receipt.get('cleanup') is True)
        if self.volume_created:
            try:
                self.engine.request('DELETE', '/volumes/' + self.name, missing=True)
                cleaned = cleaned and self.engine.request('GET', '/volumes/' + self.name, missing=True) is None
            except Exception:
                cleaned = False
        if self.janitor_id:
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                if self.engine.request('GET','/containers/'+self.janitor_id+'/json',missing=True) is None:
                    break
                time.sleep(.1)
            else:
                cleaned=False
        if self._temp:
            self._temp.cleanup()
        if not cleaned:
            raise ValueError('项目临时工作区回收未确认') from value
