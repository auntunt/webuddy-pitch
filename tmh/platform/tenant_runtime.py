"""Private, separately spawned tenant workers. No mutable current-tenant global.

The Unix socket and per-start key are local control-plane credentials. A worker
is not a sandbox: execution is denied unless the registry explicitly permits the
trusted legacy operator. Newly managed tenants never run host code.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, copy_context
import base64
import hashlib
import hmac
import http.client
import io
import json
import os
from pathlib import Path
import signal
import socket
import socketserver
import stat
import subprocess
import sys
import threading
import time

from .errors import ApiError
from . import filelock

ACTOR = ContextVar('tenant_actor', default='')
TOOL = ContextVar('tenant_tool_connection', default=None)


def error(code, message, reason='permission_denied'):
    exc = ApiError(code, message)
    exc.reason = reason
    return exc


class TenantContext:
    def __init__(self, registry, tenant_id):
        self.registry, self.tenant_id = registry, tenant_id
        self.root_data = registry.data_dir
        self.platform = None

    def current_actor(self, actor):
        value = self.registry.context(actor, self.tenant_id)
        if value['tenant']['status'] != 'active' or not value['role']:
            raise error(403, '当前租户未授权或已停用', 'membership_revoked')
        grants = value['project_grants']
        projects = self.platform.store.projects() if self.platform else []
        keys = {str(p['id']): p['key'] for p in projects}
        result = dict(value, project_grants={keys[g['project_id']]: g['role'] for g in grants if g['project_id'] in keys})
        tool = TOOL.get()
        if tool is not None:
            if tool['user'] != actor or tool['tenant'] != self.tenant_id:
                raise error(403, '工具连接与当前成员不匹配', 'tool_invalid')
            # A personal admin may issue a tool token, but never delegate their
            # admin, execution or human-signoff authority to that connection.
            role = 'contributor' if tool['scope'] == 'content' else 'viewer'
            result.update(role='member' if tool['scope'] == 'content' else 'viewer', platform_owner=False,
                          can_manage=False, project_grants={keys[str(pid)]: role for pid in tool['project_ids'] if str(pid) in keys},
                          tool_connection=tool,
                          capabilities={k: k == 'read' or k == 'write' and tool['scope'] == 'content'
                                        for k in value['capabilities']})
        return result

    def directory(self):
        return self.registry.directory(self.tenant_id)

    def runtime_allowed(self, actor):
        try:
            return bool(self.current_actor(actor)['capabilities']['execution'])
        except ApiError:
            return False

    def workspace_allowed(self, value):
        """Only server-approved roots; existing legacy project roots stay fixed."""
        raw = Path(value).expanduser()
        if not raw.is_absolute() or any(p.is_symlink() for p in (raw, *raw.parents)):
            return False
        path = raw.resolve()
        tenant = self.registry.one('SELECT * FROM tenants WHERE id=?', (self.tenant_id,))
        protected = [self.root_data / 'control'] + [Path(t['path']) for t in self.registry.q(
            "SELECT path FROM tenants WHERE id NOT IN (?, 'default')", (self.tenant_id,))]
        for other in protected:
            other = other.resolve()
            if path == other or other in path.parents or path in other.parents:
                return False
        roots = [Path(tenant['path']) / rel for rel in ('repositories', 'projects', 'project-library/workspaces')]
        if self.tenant_id == 'default' and self.platform:
            roots += [Path(p['root']).resolve() for p in self.platform.store.projects()]
        for root in roots:
            if path == root.resolve() or root.resolve() in path.parents:
                return True
        return False

    @contextmanager
    def acting(self, actor, tool=None):
        token = ACTOR.set(actor)
        tool_token = TOOL.set(tool)
        try:
            yield
        finally:
            TOOL.reset(tool_token)
            ACTOR.reset(token)


def sign_request(key, tenant, actor, method, path, body, context_token='', tool_connection=''):
    value = {'tenant': tenant, 'actor': actor, 'method': method, 'path': path,
             'body': hashlib.sha256(body).hexdigest(), 'time': time.time(), 'context': context_token}
    if tool_connection:
        value['tool_connection'] = tool_connection
    encoded = base64.urlsafe_b64encode(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).decode()
    return encoded + '.' + hmac.new(key, encoded.encode(), hashlib.sha256).hexdigest()


def verify_request(key, proof, tenant, method, path, body, context_token='', tool_connection=''):
    try:
        encoded, signature = proof.split('.')
        if not hmac.compare_digest(signature, hmac.new(key, encoded.encode(), hashlib.sha256).hexdigest()):
            raise ValueError()
        value = json.loads(base64.urlsafe_b64decode(encoded))
        if (value['tenant'] != tenant or value['method'] != method or value['path'] != path or
                value.get('context') != context_token or value.get('tool_connection', '') != tool_connection or
                value['body'] != hashlib.sha256(body).hexdigest() or abs(time.time() - value['time']) > 30 or
                not isinstance(value['actor'], str) or not value['actor']):
            raise ValueError()
        return value['actor']
    except (ValueError, KeyError, TypeError):
        raise error(401, '租户内部请求凭据无效', 'session_invalid') from None


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, address, timeout=300):
        super().__init__('localhost', timeout=timeout)
        self.address = str(address)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.address)


class Workers:
    """Only trusted registry records can allocate a worker; never user paths."""
    def __init__(self, registry):
        self.registry = registry
        self.lock = threading.RLock()
        self.live = {}
        self.instance_lock = (registry.path.parent / 'gateway.lock').open('a+b')
        try:
            if filelock.try_lock(self.instance_lock, blocking=False) is False:
                raise ValueError('此数据目录已经有一个租户入口在运行')
        except BaseException:
            self.instance_lock.close()
            raise
        try:
            label = hashlib.sha256(str(registry.path).encode()).hexdigest()[:20]
            self.socket_dir = Path('/tmp') / ('tmh-tenants-' + str(os.getuid()) + '-' + label)
            self.socket_dir.mkdir(mode=0o700, exist_ok=True)
            info = self.socket_dir.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError('租户 socket 目录权限不安全')
        except BaseException:
            filelock.unlock(self.instance_lock)
            self.instance_lock.close()
            raise

    def _start(self, tenant):
        row = self.registry.one('SELECT * FROM tenants WHERE id=?', (tenant,))
        if not row or row['status'] != 'active':
            raise error(403, '租户不存在或已停用', 'tenant_disabled')
        root = Path(row['path'])
        expected = self.registry.data_dir if tenant == 'default' else self.registry.data_dir / 'tenants' / tenant / 'data'
        if root != expected or any(p.is_symlink() for p in (root, *root.parents)) or (root / 'platform.db').is_symlink():
            raise error(403, '租户存储路径无效', 'storage_invalid')
        if tenant != 'default':
            for directory in (self.registry.data_dir / 'tenants', root.parent, root):
                directory.mkdir(mode=0o700, exist_ok=True)
        with self.lock:
            current = self.live.get(tenant)
            if current and current['proc'].poll() is None:
                return current
            if current:
                current['log'].close()
            name = hashlib.sha256(tenant.encode()).hexdigest()[:16]
            address = self.socket_dir / (name + '.sock')
            address.unlink(missing_ok=True)
            key = os.urandom(32)
            keyfile = self.socket_dir / (name + '.key')
            log = None
            try:
                fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                with os.fdopen(fd, 'wb') as out:
                    out.write(key)
                logs = self.registry.data_dir / 'control' / 'worker-logs'
                logs.mkdir(mode=0o700, exist_ok=True)
                log = (logs / (name + '.log')).open('ab')
                env = dict(os.environ)
                # The private socket is the only worker listener; no public service token.
                env.pop('TMH_TOKEN', None)
                proc = subprocess.Popen([sys.executable, '-m', 'tmh.platform.tenant_runtime', str(self.registry.data_dir),
                                         tenant, str(address), str(keyfile), str(os.getpid())], stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=log, env=env, start_new_session=True)
                current = {'proc': proc, 'key': key, 'socket': address, 'keyfile': keyfile, 'log': log}
                self.live[tenant] = current
                deadline = time.monotonic() + 30
                while not address.exists():
                    if proc.poll() is not None:
                        raise error(503, '租户服务启动失败，请管理员检查运行记录', 'worker_unavailable')
                    if time.monotonic() >= deadline:
                        raise error(503, '租户服务未在启动预算内就绪', 'worker_unavailable')
                    time.sleep(.03)
                return current
            except BaseException:
                self.stop(tenant)
                if log:
                    log.close()
                keyfile.unlink(missing_ok=True)
                address.unlink(missing_ok=True)
                raise

    def ensure(self, tenant):
        return self._start(tenant)

    def request(self, tenant, actor, method, path, body=b'', headers=None, *, require_live=False):
        if require_live:
            with self.lock:
                current = self.live.get(tenant)
                if not current or current['proc'].poll() is not None:
                    raise error(503, '租户服务已退出，请重新读取状态后再试', 'worker_unavailable')
        else:
            current = self._start(tenant)
        conn = UnixConnection(current['socket'])
        safe = {k: v for k, v in (headers or {}).items() if k.lower() in
                ('content-type', 'x-tmh', 'x-webuddy-context', 'x-webuddy-agent', 'x-webuddy-execution', 'x-webuddy-tool', 'referer')}
        context_token = next((v for k, v in safe.items() if k.lower() == 'x-webuddy-context'), '')
        tool_id = next((v for k, v in safe.items() if k.lower() == 'x-webuddy-tool'), '')
        safe['X-Webuddy-Worker-Proof'] = sign_request(current['key'], tenant, actor, method, path, body, context_token, tool_id)
        safe['Host'] = 'localhost'
        try:
            conn.request(method, path, body, safe)
            reply = conn.getresponse()
            content = reply.read()
            return reply.status, dict(reply.getheaders()), content
        finally:
            conn.close()

    def stop(self, tenant):
        with self.lock:
            value = self.live.pop(tenant, None)
            if not value:
                return
            proc = value['proc']
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
            value['log'].close()
            value['socket'].unlink(missing_ok=True)
            value['keyfile'].unlink(missing_ok=True)

    def close(self):
        for tenant in list(self.live):
            self.stop(tenant)
        try:
            self.socket_dir.rmdir()
        except OSError:
            pass
        if not self.instance_lock.closed:
            filelock.unlock(self.instance_lock)
            self.instance_lock.close()


def install_execution_gate(context):
    """Worker-only process launch backstop, including inherited background work."""
    original = threading.Thread.start
    def start(thread, *args, **kwargs):
        captured = copy_context()
        run = thread.run
        thread.run = lambda: captured.run(run)
        return original(thread, *args, **kwargs)
    threading.Thread.start = start
    def audit(event, args):
        if event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.fork', 'os.forkpty', 'os.exec'):
            if not context.runtime_allowed(ACTOR.get()):
                raise PermissionError('此租户没有可用的隔离执行环境，未启动宿主进程')
    sys.addaudithook(audit)


def worker(data, tenant, address, keyfile, parent_pid):
    from .tenancy import Registry
    from .server import Platform, make_handler
    from .tenant_policy import authorize
    registry = Registry(data)
    target = registry.one('SELECT * FROM tenants WHERE id=?', (tenant,))
    if not target or target['status'] != 'active':
        raise ValueError('租户未启用')
    keypath = Path(keyfile)
    if keypath.is_symlink() or stat.S_IMODE(keypath.stat().st_mode) != 0o600:
        raise ValueError('内部凭据权限不安全')
    key = keypath.read_bytes()
    context = TenantContext(registry, tenant)
    install_execution_gate(context)
    P = Platform(Path(target['path']), tenant_context=context)
    context.platform = P
    base = make_handler(P)

    class Handler(base):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def _send(self, *args, **kwargs):
            self._pending_response = (args, kwargs)

        def _authorized(self, q):
            self._who = getattr(self, '_tenant_actor', '')
            return bool(self._who)

        def _dispatch(self, method):
            self._pending_response = None
            from urllib.parse import urlsplit, parse_qs
            try:
                length = int(self.headers.get('Content-Length') or 0)
                if length < 0 or length > 5 * 1024 * 1024:
                    raise error(413, '请求大小不合适')
                raw = self.rfile.read(length) if length else b''
                tool_id = self.headers.get('X-Webuddy-Tool', '')
                actor = verify_request(key, self.headers.get('X-Webuddy-Worker-Proof', ''), tenant, method, self.path, raw, self.headers.get('X-Webuddy-Context', ''), tool_id)
                self._tenant_actor = actor
                self._who = actor
                self.rfile = io.BytesIO(raw)
                url = urlsplit(self.path)
                query = parse_qs(url.query)
                body = json.loads(raw) if method == 'POST' and raw else {}
                if not isinstance(body, dict):
                    raise error(400, '请求必须是 JSON 对象')
                with registry.authorization_guard():
                    tool = None
                    if tool_id:
                        from . import tool_access
                        tool = tool_access.validate_connection(registry, tenant, tool_id, actor)
                        operation = url.path.removeprefix('/api/agent/')
                        if method != 'POST' or not url.path.startswith('/api/agent/') or url.query or operation not in tool_access.allowed_operations(tool['scope']):
                            raise error(403, '此工具连接未获准执行该操作', 'tool_operation_denied')
                    identity = context.current_actor(actor)
                    expected_context = tool_access.context_token(tool) if tool else identity['context_token']
                    if self.headers.get('X-Webuddy-Context') != expected_context:
                        raise error(409, '成员身份或权限已变化，请重新读取', 'context_changed')
                    with context.acting(actor, tool):
                        if url.path not in ('/', '/index.html'):
                            self._tenant_scope = authorize(P, method, url.path, query, body, actor)
                        if url.path.startswith('/p/') and '/report/' in url.path:
                            raise error(403, '项目报告尚未接入独立安全来源，暂不可直接浏览')
                        return super()._dispatch(method)
            except ApiError as exc:
                return self._json(exc.code, {'error': str(exc), 'code': getattr(exc, 'reason', 'permission_denied')})
            except (ValueError, TypeError, json.JSONDecodeError):
                return self._json(400, {'error': '请求格式不正确', 'code': 'invalid_request'})
            except PermissionError:
                return self._json(403, {'error': '此操作需要独立执行环境', 'code': 'execution_disabled'})
            finally:
                if self._pending_response is not None:
                    args, kwargs = self._pending_response
                    super()._send(*args, **kwargs)

    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True
    server = Server(address, Handler)
    os.chmod(address, 0o600)
    stopping = threading.Event()
    def parent_watch():
        while not stopping.wait(.2):
            if os.getppid() != int(parent_pid):
                server.shutdown()
                return
    threading.Thread(target=parent_watch, daemon=True).start()
    def stop_worker(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop_worker)
    try:
        server.serve_forever()
    finally:
        stopping.set()
        server.server_close()
        P.store.db.close()
        registry.close()


if __name__ == '__main__':
    if len(sys.argv) != 6:
        raise SystemExit('private tenant worker requires five control-plane arguments')
    worker(*sys.argv[1:])
