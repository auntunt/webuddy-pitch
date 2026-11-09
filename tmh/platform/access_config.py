"""访问方式 settings for the Windows offline bundle.

Active only when the launcher exported WEBUDDY_BUNDLE_CONFIG (the resolved
config path: --config / WEBUDDY_CONFIG / %LOCALAPPDATA%\\Webuddy\\config.json).
The card writes that file atomically, preserving data_dir, tools and other
environment keys; it never writes anywhere else."""
import ipaddress
import json
import os
import re
import secrets
import socket
import tempfile
from pathlib import Path

from .errors import ApiError

ALLOWED_TOP = {'data_dir', 'host', 'port', 'environment', 'tools'}
PUBLIC_RE = re.compile(r"^https?://[A-Za-z0-9.:\[\]\-]{1,120}$")


def path() -> Path | None:
    value = os.environ.get('WEBUDDY_BUNDLE_CONFIG', '')
    return Path(value) if value else None


def local_ipv4s() -> list:
    try:
        addrs = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        addrs = []
    out = []
    for a in addrs:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError:
            continue
        if ip.version == 4 and not ip.is_loopback and a not in out:
            out.append(a)
    return out


def _read(path):
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding='utf-8-sig'))
    except ValueError as exc:
        raise ApiError(409, '访问方式配置文件不是有效 JSON：%s' % path.name) from exc
    if not isinstance(config, dict):
        raise ApiError(409, '访问方式配置文件必须是 JSON 对象')
    return config


def view() -> dict:
    target = path()
    if target is None:
        return {'available': False}
    config = _read(target)
    env = config.get('environment') or {}
    host = config.get('host', '127.0.0.1')
    return {'available': True, 'path': str(target),
            'mode': 'lan' if host in ('0.0.0.0', '::') else 'local',
            'port': int(config.get('port', 8790)),
            'public_url': env.get('TMH_PUBLIC_URL', ''),
            'token_set': bool(env.get('TMH_TOKEN')),
            'addresses': local_ipv4s()}


def save(body: dict) -> dict:
    target = path()
    if target is None:
        raise ApiError(404, '这个安装不支持访问方式配置')
    mode = body.get('mode')
    if mode not in ('local', 'lan'):
        raise ApiError(400, '访问方式只能是 local 或 lan')
    try:
        port = int(body.get('port'))
    except (TypeError, ValueError):
        raise ApiError(400, '端口必须是 1-65535 的整数')
    if not 1 <= port <= 65535:
        raise ApiError(400, '端口必须是 1-65535 的整数')
    public_url = str(body.get('public_url') or '').strip().rstrip('/')
    token = ''
    config = _read(target)
    config['host'] = '0.0.0.0' if mode == 'lan' else '127.0.0.1'
    config['port'] = port
    env = dict(config.get('environment') or {})
    if mode == 'lan':
        if not public_url:
            addresses = local_ipv4s()
            if not addresses:
                raise ApiError(400, '没有检测到可用的局域网地址，请手动填写')
            public_url = 'http://%s:%d' % (addresses[0], port)
        if not PUBLIC_RE.match(public_url):
            raise ApiError(400, '对外地址必须是 http://IP:端口 形式')
        env['TMH_PUBLIC_URL'] = public_url
        if body.get('regenerate') or not env.get('TMH_TOKEN'):
            env['TMH_TOKEN'] = secrets.token_urlsafe(24)
            token = env['TMH_TOKEN']
    else:
        env.pop('TMH_TOKEN', None)
        env.pop('TMH_PUBLIC_URL', None)
    config['environment'] = env
    unknown = set(config) - ALLOWED_TOP
    for key in unknown:
        config.pop(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.config-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    result = view()
    if token:
        result['access_url'] = '%s/?token=%s' % (public_url, token)
    result['restart_required'] = True
    return result
