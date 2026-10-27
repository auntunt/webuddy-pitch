"""Project-only rootless containers, without granting host process execution.

The trusted worker talks to its rootless daemon directly. Neither the daemon
socket nor host environment is passed to a job. The attach connection is the
job's ownership lease; EOF kills PID 1, including detached descendants. A second
deadline inside the container bounds jobs after a daemon/transport failure.

Currently used only for trusted fixed Git metadata queries. A project can itself
contain credentials or Unix sockets: this mount contract alone is not approval
to run untrusted project tools or expose a provider-authenticated proxy.
"""
from __future__ import annotations

import http.client
import json
import math
import os
from pathlib import Path
import re
import socket
import struct
import threading
import time
import uuid
from urllib.parse import quote


WATCH = r'''
import json,os,signal,subprocess,sys,threading,time
limit=max(0,float(sys.argv[1])-time.monotonic()); command=json.loads(sys.argv[2])
if limit<=0: os._exit(124)
def owner():
    if not sys.stdin.buffer.read(1): os._exit(125)
threading.Thread(target=owner,daemon=True).start()
p=subprocess.Popen(command,stdin=subprocess.DEVNULL,start_new_session=True)
try: code=p.wait(timeout=limit)
except subprocess.TimeoutExpired:
    os.killpg(p.pid,signal.SIGTERM)
    try: p.wait(timeout=2)
    except subprocess.TimeoutExpired: pass
    os._exit(124)
for name in os.listdir('/proc'):
    if name.isdigit() and int(name) not in (1,os.getpid()):
        try:
            state=open('/proc/'+name+'/stat').read().rsplit(')',1)[1].split()[0]
            if state!='Z': os._exit(125)
        except FileNotFoundError: pass
os._exit(code if 0<=code<=255 else 125)
'''


class DockerError(RuntimeError):
    pass


class Connection(http.client.HTTPConnection):
    def __init__(self, path, timeout=10):
        super().__init__('localhost', timeout=timeout)
        self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def _path(path):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('隔离挂载路径必须是无符号链接的绝对路径')
    if ',' in str(path) or ':' in str(path) or '\n' in str(path):
        raise ValueError('隔离挂载路径包含不支持的字符')
    return str(path)


def specification(image, command, workspace, seconds, *, writable=False, mounts=()):
    """No raw Docker options, host env, network, devices or arbitrary targets."""
    if not isinstance(image, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise ValueError('项目执行镜像必须固定到完整 image ID')
    if not isinstance(command, list) or not command or any(not isinstance(x, str) or '\0' in x for x in command):
        raise ValueError('隔离命令必须是字符串列表')
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('隔离任务需要正数总时限')
    bindings = [{'Type':'bind', 'Source':_path(workspace), 'Target':'/workspace', 'ReadOnly':not writable}]
    for source, target in mounts:
        if target != '/source':
            raise ValueError('不支持的隔离挂载目标')
        bindings.append({'Type':'bind', 'Source':_path(source), 'Target':target, 'ReadOnly':True})
    temporary={'/tmp':'rw,nosuid,nodev,size=128m','/home/worker':'rw,nosuid,nodev,size=128m'}
    for binding in bindings:
        metadata=Path(binding['Source'])/'.tmh'
        if metadata.is_symlink() or metadata.exists() and not metadata.is_dir():
            raise ValueError('项目元数据目录不能是符号链接或普通文件')
        if metadata.is_dir():
            temporary[binding['Target']+'/.tmh']='rw,nosuid,nodev,noexec,size=1m'
    return {'Image':image, 'Entrypoint':['python3','-u','-c',WATCH],
        'Cmd':[str(time.monotonic()+seconds),json.dumps(command)],
        'User':'0:0', 'WorkingDir':'/workspace', 'NetworkDisabled':True,
        'OpenStdin':True, 'StdinOnce':True, 'AttachStdin':True, 'AttachStdout':True, 'AttachStderr':True,
        'Env':['PATH=/usr/local/bin:/usr/bin:/bin','HOME=/home/worker','LANG=C.UTF-8','PYTHONDONTWRITEBYTECODE=1','GIT_CONFIG_NOSYSTEM=1',
               'GIT_CONFIG_GLOBAL=/dev/null','GIT_TERMINAL_PROMPT=0','GIT_NO_REPLACE_OBJECTS=1',
               'GIT_NO_LAZY_FETCH=1','GIT_ALLOW_PROTOCOL='],
        'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'CapDrop':['ALL'],
            'SecurityOpt':['no-new-privileges:true'], 'PidsLimit':128, 'Memory':1024**3,
            'NanoCpus':10**9, 'Mounts':bindings,
            'Tmpfs':temporary}}


class Engine:
    def __init__(self, path=None):
        self.path = Path(path or '/run/user/%d/docker.sock' % os.getuid())

    def request(self, method, path, value=None, *, timeout=10, missing=False):
        conn = Connection(self.path, timeout)
        try:
            body = json.dumps(value).encode() if value is not None else None
            conn.request(method, '/v1.45'+path, body, {'Content-Type':'application/json'})
            response = conn.getresponse(); raw = response.read()
            if missing and response.status == 404:
                return None
            if response.status >= 300:
                # Do not expose daemon error bodies containing job paths/prompts.
                error=DockerError('隔离执行请求失败（HTTP %d）' % response.status)
                error.status=response.status
                error.details=raw  # Private diagnostics only, never the public error text.
                raise error
            return json.loads(raw) if raw else {}
        finally:
            conn.close()

    def _attach(self, cid, timeout=10):
        connection = Connection(self.path, timeout)
        connection.connect()
        stream = connection.sock.makefile('rwb', buffering=0)
        stream.write(('POST /v1.45/containers/%s/attach?stream=1&stdin=1&stdout=1&stderr=1 HTTP/1.1\r\n'
            'Host: localhost\r\nConnection: Upgrade\r\nUpgrade: tcp\r\nContent-Length: 0\r\n\r\n' % cid).encode())
        status = stream.readline(8192)
        if not status.startswith(b'HTTP/1.1 101 '):
            stream.close(); connection.close()
            raise DockerError('无法建立隔离任务所有权连接')
        for _ in range(100):
            line=stream.readline(8192)
            if line==b'\r\n': break
            if not line: raise DockerError('隔离任务所有权连接被截断')
        else:
            raise DockerError('隔离任务所有权响应头过长')
        connection.sock.settimeout(None)
        return connection, stream

    def run(self, spec, seconds, *, cancel=lambda:False, output=lambda data:None, receipt=None, diagnostic=None,
            on_created=lambda cid:None, owner_nonce=None):
        started = time.monotonic(); cid = None; attached = stream = None
        deadline=started+seconds
        nonce=owner_nonce or uuid.uuid4().hex
        if not re.fullmatch('[0-9a-f]{32}',nonce):
            raise ValueError('隔离任务所有权标识不正确')
        name='webuddy-project-'+nonce
        attempted=finished_create=False
        result = {'reason':'error','cleanup':True,'returncode':125,'container_name':name}
        errors = []
        def request(method,path,value=None):
            remaining=deadline-time.monotonic()
            if remaining<=0: raise TimeoutError('隔离任务总时限已到')
            return self.request(method,path,value,timeout=min(10,remaining))
        try:
            if cancel():
                result.update(reason='cancelled',returncode=125);return result
            info = request('GET','/info')
            if not any('rootless' in item for item in info.get('SecurityOptions', [])):
                raise DockerError('拒绝在非 rootless daemon 上执行项目')
            if cancel():
                result.update(reason='cancelled',returncode=125);return result
            attempted=True;result['cleanup']=False
            try:
                created=request('POST','/containers/create?name='+name,dict(spec,Labels={'webuddy.owner':nonce}))
                finished_create=True
            except DockerError:
                finished_create=True
                raise
            if not re.fullmatch('[0-9a-f]{64}',created['Id']):
                raise DockerError('隔离任务身份不正确')
            cid=created['Id']
            result['container_id'] = cid
            on_created(cid)
            if cancel():
                result.update(reason='cancelled',returncode=125);return result
            remaining=deadline-time.monotonic()
            if remaining<=0: raise TimeoutError('隔离任务总时限已到')
            attached, stream = self._attach(cid,min(10,remaining))
            def consume():
                def read(size):
                    chunks = bytearray()
                    while len(chunks)<size:
                        part=stream.read(size-len(chunks))
                        if not part: break
                        chunks.extend(part)
                    return bytes(chunks)
                try:
                    while True:
                        header=read(8)
                        if not header: break
                        if len(header)!=8 or header[0] not in (1,2) or header[1:4]!=b'\0\0\0':
                            raise DockerError('隔离输出帧不完整')
                        length=struct.unpack('>I',header[4:])[0]
                        if length>16*1024*1024: raise DockerError('隔离输出帧超过上限')
                        data=read(length)
                        if len(data)!=length: raise DockerError('隔离输出帧被截断')
                        if header[0] == 2 and diagnostic is not None:
                            diagnostic(data)
                        else:
                            output(data)
                except BaseException as exc:
                    errors.append(exc)
            consumer=threading.Thread(target=consume,daemon=True);consumer.start()
            request('POST','/containers/'+cid+'/start')
            while True:
                if cancel():
                    result.update(reason='cancelled',returncode=125);break
                if time.monotonic()-started>=seconds:
                    result.update(reason='timeout',returncode=124);break
                if errors: raise DockerError('隔离输出读取失败') from errors[0]
                state=request('GET','/containers/'+cid+'/json')['State']
                if not state['Running']:
                    result.update(reason='exited',returncode=state['ExitCode']);break
                time.sleep(min(.1,max(0,seconds-(time.monotonic()-started))))
            if result['reason']=='exited':
                consumer.join(3)
                if consumer.is_alive() or errors:
                    raise DockerError('隔离输出或所有权连接未正常结束')
        except TimeoutError:
            result.update(reason='timeout' if time.monotonic()>=deadline else 'error',
                          returncode=124 if time.monotonic()>=deadline else 125)
        finally:
            try:
                if attempted and not cid:
                    recovered=self.request('GET','/containers/'+name+'/json',timeout=3,missing=True)
                    if recovered is None:
                        # A transport timeout can finish creating later. Never
                        # call that unknown state confirmed complete cleanup.
                        result['cleanup']=finished_create
                    elif recovered.get('Config',{}).get('Labels',{}).get('webuddy.owner')==nonce and re.fullmatch('[0-9a-f]{64}',recovered.get('Id','')):
                        cid=recovered['Id'];result['container_id']=cid
                if cid:
                    self.request('DELETE','/containers/'+quote(cid,safe='')+'?force=1',timeout=3,missing=True)
                    result['cleanup']=self.request('GET','/containers/'+cid+'/json',timeout=3,missing=True) is None
            finally:
                if stream:
                    stream.close()
                if attached:
                    attached.close()
                result['elapsed_seconds']=round(time.monotonic()-started,3)
                if receipt is not None:
                    receipt.update(result)
        return result
