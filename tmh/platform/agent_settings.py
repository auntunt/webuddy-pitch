"""Editable, non-secret agent fields; execution commands remain operator-owned."""
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

from . import agents, agent_routes
from .errors import ApiError

_LOCK = threading.Lock()
MODES = ('analyze', 'plan', 'fix', 'edit', 'diagnose', 'ask', 'kb', 'chart', 'understand')


def _read(data_dir):
    path = Path(data_dir) / 'agents.json'
    raw = path.read_bytes() if path.exists() else b'{}'
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise ApiError(400, '智能体配置不是有效 JSON，请先修复原文件') from exc
    if not isinstance(value, dict) or any(not isinstance(v, dict) for v in value.values()):
        raise ApiError(400, '智能体配置必须是名称到配置的对象')
    return value, hashlib.sha256(raw).hexdigest()


def view(data_dir):
    raw, revision = _read(data_dir)
    configs = {k: dict(v) for k, v in agents.BUILTIN.items()}
    for name, value in raw.items():
        configs.setdefault(name, {}).update(value)
    items = []
    for item in agents.available(data_dir):
        c = configs[item['name']]
        items.append(dict(item, timeout=c.get('run_timeout') or c.get('timeout') or 1800))
    return {'agents': items, 'revision': revision, 'route': agent_routes.route(data_dir), 'modes': list(MODES)}


def save(data_dir, body):
    if set(body) != {'action', 'name', 'revision', 'config'}:
        raise ApiError(400, '需要创建或更新操作、智能体名称、配置和当前版本')
    if body['action'] not in ('create', 'update'):
        raise ApiError(400, '操作必须是 create 或 update')
    name, value = body['name'], body['config']
    if not isinstance(name, str) or not agent_routes.AGENT.fullmatch(name):
        raise ApiError(400, '智能体代号只能使用字母、数字、短横线和下划线')
    if not isinstance(value, dict) or set(value) - {'title', 'models', 'defaults', 'timeout', 'profile', 'engine'}:
        raise ApiError(400, '仅支持名称、模型、步骤默认模型、超时、执行引擎和 Codex 配置档')
    title, models, defaults, timeout = (value.get(k) for k in ('title', 'models', 'defaults', 'timeout'))
    if not isinstance(title, str) or not title.strip() or len(title) > 100:
        raise ApiError(400, '填写不超过 100 字的显示名称')
    if not isinstance(models, list) or any(not isinstance(m, list) or len(m) != 2 or
            not isinstance(m[0], str) or not agents.MODEL_ID.fullmatch(m[0]) or
            not isinstance(m[1], str) or not m[1].strip() or len(m[1]) > 100 for m in models):
        raise ApiError(400, '模型列表需要合法模型 ID 和显示名称')
    ids = [m[0] for m in models]
    if len(set(ids)) != len(ids):
        raise ApiError(400, '模型 ID 不能重复')
    if not isinstance(defaults, dict) or set(defaults) - set(MODES) or any(not isinstance(v, str) or v and v not in ids for v in defaults.values()):
        raise ApiError(400, '步骤默认模型必须来自模型列表，或留空沿用执行器配置')
    if type(timeout) is not int or not 1 <= timeout <= 86400:
        raise ApiError(400, '超时必须是 1 至 86400 秒的整数')
    with _LOCK:
        raw, revision = _read(data_dir)
        if body['revision'] != revision:
            raise ApiError(409, '配置已被更新，请重新打开后编辑')
        existing = name in raw or name in agents.BUILTIN
        if body['action'] == 'create' and existing:
            raise ApiError(409, '此代号已存在，请打开已有智能体配置编辑')
        if body['action'] == 'update' and not existing:
            raise ApiError(404, '智能体不存在，请重新读取配置')
        c = dict(agents.BUILTIN.get(name, {}), **raw.get(name, {}))
        engine = value.get('engine', 'codex' if not existing else agents.engine_name(name, c))
        if 'engine' in value and (engine not in ('codex', 'cursor') or existing and engine != agents.engine_name(name, c)):
            raise ApiError(400, '已有执行器不能更换引擎；新执行器支持 codex/cursor')
        if not existing:
            c.update(engine=engine, resume=False, retry_busy=False)
            if engine == 'codex':
                c['prompt_transport'] = 'stdin'
            else:
                c['bin'] = 'agent'
        if 'profile' in value:
            profile = value['profile']
            if not isinstance(profile, str) or profile and not agents.PROFILE_ID.fullmatch(profile):
                raise ApiError(400, 'Codex 配置档名称不合法')
            if profile:
                c['profile'] = profile
            else:
                c.pop('profile', None)
        c.update(title=title.strip(), models=models, defaults=defaults, run_timeout=timeout)
        try:
            agents.engine_name(name, c)
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        raw[name] = c
        path = Path(data_dir) / 'agents.json'
        fd, temporary = tempfile.mkstemp(prefix='.agents-', dir=data_dir)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
                f.write('\n')
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return view(data_dir)
