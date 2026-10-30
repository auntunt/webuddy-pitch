"""Run the official client separately from its credential-free project tools.

This module is a building block, not an authorization grant. Its caller binds
the current principal and project, checks authorization continuously, and owns
the screened workspace and all resulting evidence.
"""
from __future__ import annotations

import os
import json
import hashlib
import hmac
from pathlib import Path
import re
import socket
import stat
import tempfile
import threading
import time
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11: only project execution needs TOML parsing
    tomllib = None

from .project_container import Engine, specification
from .project_mcp import BoundJob, ProjectMCP
from .project_snapshot import validate_workspace
from .project_volume import ProjectVolume

RELAY = r'''
import os,select,socket,sys
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.connect('/mcp-channel/mcp.sock')
try:
    while True:
        ready,_,_=select.select([0,s],[],[],1)
        for source in ready:
            data=os.read(0,65536) if source==0 else s.recv(65536)
            if not data: raise EOFError()
            if source==0: s.sendall(data)
            else: os.write(1,data)
except (EOFError,BrokenPipeError): pass
finally: s.close()
'''

DRIVER = r'''
import json,pathlib,subprocess,sys
disabled=['shell_tool','unified_exec','multi_agent','multi_agent_v2','view_image','image_generation',
 'browser_use','browser_use_external','browser_use_full_cdp_access','in_app_browser','computer_use',
 'plugins','remote_plugin','apps','hooks','skill_search','skill_mcp_dependency_install',
 'workspace_dependencies','worktrees','goals','tool_suggest','enable_request_compression',
 'api_key_model_discovery','daemon_auto_start']
cmd=['codex']
for feature in disabled: cmd+=['--disable',feature]
cmd+=['--enable','code_mode_only','--enable','code_mode_only_strict_3p_tools','exec','--json',
 '--color','never','--ephemeral','--skip-git-repo-check','--sandbox','danger-full-access',
 '-C','/workspace']
opts=json.loads(pathlib.Path('/fixture/options.json').read_text())
if opts['profile']:cmd+=['--profile',opts['profile']]
if opts['model']:cmd+=['-m',opts['model']]
cmd+=['-']
with pathlib.Path('/fixture/prompt').open('rb') as prompt:
    raise SystemExit(subprocess.call(cmd,stdin=prompt))
'''

MCP_CONFIG = '''
[mcp_servers.project]
command="/usr/bin/python3"
args=["-I","-S","-B","/mcp-channel/client.py"]
startup_timeout_sec=10
tool_timeout_sec=35
required=true
'''


def _secure_config(path):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077 or path.is_symlink()):
        raise ValueError('官方客户端配置的所有者或权限不安全')
    return path.read_text(encoding='utf-8')


def provider_binding(path, profile='', model=''):
    if profile and not re.fullmatch('[A-Za-z0-9_-]{1,64}',profile):
        raise ValueError('项目 Codex profile 名称不正确')
    if model and not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}',model):
        raise ValueError('项目模型名称不正确')
    if tomllib is None:
        raise RuntimeError('项目 Codex 执行配置需要 Python 3.11 以上（tomllib）')
    path=Path(path);text=_secure_config(path);config=tomllib.loads(text)
    if any(key in config for key in ('mcp_servers', 'features', 'profiles', 'hooks')):
        raise ValueError('官方客户端配置含有不支持的工具或配置覆盖')
    profile_text=''
    overrides={}
    if profile:
        profile_text=_secure_config(path.parent/(profile+'.config.toml'))
        overrides=tomllib.loads(profile_text)
        if (not isinstance(overrides,dict) or set(overrides)-{'model','model_provider','approval_policy','model_reasoning_effort','service_tier'}
                or any(not isinstance(v,str) for v in overrides.values())):
            raise ValueError('项目 Codex profile 含不支持的配置')
    provider = overrides.get('model_provider',config.get('model_provider'))
    if not isinstance(provider, str) or provider not in config.get('model_providers', {}):
        raise ValueError('官方客户端供应商配置不可用')
    definition=config['model_providers'][provider]
    if (not isinstance(definition,dict) or definition.get('requires_openai_auth') is True or
            any(k in definition for k in ('env_key','env_http_headers'))):
        raise ValueError('项目供应商认证方式尚不支持隔离执行')
    digest=hashlib.sha256((text+'\0'+profile_text+'\0'+profile+'\0'+model).encode()).hexdigest()
    return text,profile_text,digest


def run(job: BoundJob, provider_config, prompt, seconds, *, base_commit, authorize, profile='', model='',
        expected_binding=None, cancel=lambda: False,
        output=lambda chunk: None, tool_output=lambda chunk: None, engine=None, volume_factory=ProjectVolume):
    if not isinstance(prompt, str) or not prompt.strip() or seconds <= 0:
        raise ValueError('项目执行需要完整任务和正数时限')
    if authorize(job) is not True or not validate_workspace(job.workspace):
        raise ValueError('项目授权或隔离工作区不可用')
    if not isinstance(base_commit, str) or not re.fullmatch('[0-9a-f]{40}', base_commit):
        raise ValueError('项目执行需要固定基线提交')
    engine = engine or Engine()
    deadline = time.monotonic() + seconds
    pending = bytearray()
    state = {'completed':False, 'failed':False, 'answer':False}
    def observe(chunk):
        output(chunk)
        pending.extend(chunk)
        while b'\n' in pending:
            line, _, rest = pending.partition(b'\n')
            pending[:] = rest
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(event, dict):
                kind = event.get('type')
                state['completed'] |= kind == 'turn.completed'
                state['failed'] |= kind == 'turn.failed'
                item = event.get('item') or {}
                if kind == 'item.completed' and isinstance(item, dict):
                    state['answer'] |= item.get('type') == 'agent_message' and bool(str(item.get('text') or '').strip())
        if len(pending) > 4 * 1024 * 1024:
            raise ValueError('客户端输出单行超出限制')
    def stopped():
        return cancel() or time.monotonic() >= deadline
    with volume_factory(engine, job.image_id, job.workspace, seconds, stopped) as volume:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('准备项目工作区时已超过总时限')
        receipt = _run(job, provider_config, prompt, remaining, authorize=authorize, cancel=stopped,
                       output=observe, tool_output=tool_output, engine=engine, volume=volume,
                       profile=profile,model=model,expected_binding=expected_binding)
        receipt['client_completion'] = dict(state)
        if receipt.get('returncode') == 0 and (not state['completed'] or state['failed'] or not state['answer']):
            receipt.update(returncode=1, reason='incomplete_client_result')
        if (receipt.get('reason') == 'exited' and receipt.get('returncode') == 0
                and receipt.get('cleanup') is True and not stopped() and authorize(job) is True
                and all(item.get('cleanup') is True for item in receipt.get('project_tools', []))):
            receipt['workspace'] = volume.export(base_commit)
    receipt['volume_cleanup'] = True
    return receipt


def _run(job, provider_config, prompt, seconds, *, authorize, cancel, output, tool_output, engine, volume,
         profile, model, expected_binding):
    stop = threading.Event()
    connections = []
    errors = []
    tool_receipts = []
    erased = threading.Event()
    with tempfile.TemporaryDirectory(prefix='webuddy-client-') as raw:
        root = Path(raw).resolve()
        for name in ('empty', 'client', 'channel', 'credentials'):
            (root / name).mkdir(mode=0o700)
        (root / 'client/driver.py').write_text(DRIVER, encoding='utf-8')
        (root / 'client/prompt').write_text(prompt, encoding='utf-8')
        (root / 'client/options.json').write_text(json.dumps({'profile':profile,'model':model}),encoding='utf-8')
        (root / 'channel/client.py').write_text(RELAY, encoding='utf-8')
        config = root / 'credentials/config.toml'
        base_text,profile_text,binding=provider_binding(provider_config,profile,model)
        if expected_binding is not None and not hmac.compare_digest(binding,expected_binding):
            raise ValueError('项目 Codex 供应商或 profile 在登记后已变化')
        config.write_text(base_text+'\n'+MCP_CONFIG, encoding='utf-8')
        config.chmod(0o400)
        profile_copy=None
        if profile:
            profile_copy=root/'credentials/profile.toml'
            profile_copy.write_text(profile_text,encoding='utf-8');profile_copy.chmod(0o400)

        def erase():
            # In-place truncation is necessary: an atomic replacement leaves
            # the original inode visible through the container bind mount.
            for path in (config,profile_copy):
                if path is None:continue
                path.chmod(0o600)
                with path.open('w', encoding='utf-8') as stream:
                    stream.flush()
                    os.fsync(stream.fileno())
                path.chmod(0o400)
            erased.set()
            return True

        def cancelled():
            return stop.is_set() or cancel()

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(root / 'channel/mcp.sock'))
        listener.listen(1)
        listener.settimeout(.2)
        service = ProjectMCP(job, authorize, lambda current: validate_workspace(current.workspace),
                             engine_factory=lambda: engine, initialize=erase, cancelled=cancelled,
                             output_log=tool_output, record=tool_receipts.append, volume=volume)

        def serve():
            conn = None
            try:
                while not cancelled():
                    try:
                        conn, _ = listener.accept()
                        break
                    except socket.timeout:
                        pass
                if conn is None:
                    return
                connections.append(conn)
                with conn.makefile('r', encoding='utf-8') as source, conn.makefile('w', encoding='utf-8') as sink:
                    service.serve(source, sink)
            except (OSError, ValueError) as exc:
                if not cancelled():
                    errors.append(type(exc).__name__)
            finally:
                if conn:
                    conn.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        spec = specification(job.image_id, ['python3', '-I', '-u', '/fixture/driver.py'], root / 'empty', seconds)
        spec['NetworkDisabled'] = False
        spec['HostConfig']['NetworkMode'] = 'bridge'
        spec['HostConfig']['Mounts'] += [
            {'Type':'bind', 'Source':str(root / 'client'), 'Target':'/fixture', 'ReadOnly':True},
            {'Type':'bind', 'Source':str(root / 'channel'), 'Target':'/mcp-channel', 'ReadOnly':True},
            {'Type':'bind', 'Source':str(config), 'Target':'/home/worker/.codex/config.toml', 'ReadOnly':True},
        ]
        if profile_copy:
            spec['HostConfig']['Mounts'].append({'Type':'bind','Source':str(profile_copy),
                'Target':'/home/worker/.codex/'+profile+'.config.toml','ReadOnly':True})
        try:
            receipt = engine.run(spec, seconds, cancel=lambda: cancelled() or not service._authorized(), output=output)
        finally:
            stop.set()
            listener.close()
            for conn in connections:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            thread.join(40)
            if not erased.is_set():
                erase()
        if thread.is_alive() or errors or not erased.is_set():
            raise ValueError('项目工具通道未能安全结束')
        return dict(receipt, project_tools=tool_receipts, credential_erased=True)
