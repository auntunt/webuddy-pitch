"""Fixed static build artifacts, served with no application-origin authority.

Only explicitly configured projects use this path. Candidate JS runs in an
opaque CSP sandbox. Read-only resource grants are signed, personal, expiring,
and checked against current tenant/project authority on every request.
"""
from __future__ import annotations

import base64
from contextlib import closing
import hashlib
import hmac
import io
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import time
from urllib.parse import quote, unquote

from .errors import ApiError
from .supervised_process import _atomic_json

MAX_ARTIFACT = 128 * 1024 * 1024


def profile(data_dir, key):
    path = Path(data_dir) / 'static-preview.json'
    if not path.exists():
        return None
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
            stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError('静态预览配置所有者或权限不安全')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) != {'schema', 'projects'} or value['schema'] != 1 or not isinstance(value['projects'], dict):
        raise ValueError('静态预览配置无效')
    for code, item in value['projects'].items():
        if (not re.fullmatch('[A-Z][A-Z0-9]{0,9}', code) or not isinstance(item, dict) or
                set(item) != {'image', 'output', 'auto'} or type(item['auto']) is not bool or
                not isinstance(item['image'], str) or not re.fullmatch('sha256:[0-9a-f]{64}', item['image']) or
                not isinstance(item['output'], str)):
            raise ValueError('静态预览项目配置无效')
        relative(item['output'])
    return value['projects'].get(key)


def relative(name):
    if (not isinstance(name, str) or not name or '\\' in name or '\0' in name or
            name.startswith('/') or any(p in ('', '.', '..') for p in name.split('/'))):
        raise ValueError('静态预览路径不安全')
    return PurePosixPath(name)


EXPORT = r'''
import io,json,os,stat,sys,tarfile
base='/workspace/'+sys.argv[1];commit=sys.argv[2]
if not os.path.isdir(base) or os.path.islink(base):raise RuntimeError('static output missing')
for part in sys.argv[1].split('/'):
 if part in ('','.','..'):raise RuntimeError('invalid static output')
p='/workspace'
for part in sys.argv[1].split('/'):
 p+='/'+part
 if os.path.islink(p):raise RuntimeError('linked static output')
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as tar:
 data=json.dumps({'commit':commit}).encode();info=tarfile.TarInfo('MANIFEST.json');info.size=len(data);tar.addfile(info,io.BytesIO(data))
 total=0;count=0
 for root,dirs,files in os.walk(base,followlinks=False):
  dirs.sort();files.sort()
  for name in dirs+files:
   p=os.path.join(root,name);s=os.lstat(p)
   if not(stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)) or s.st_nlink!=1 and stat.S_ISREG(s.st_mode):raise RuntimeError('unsupported static output')
  for name in files:
   p=os.path.join(root,name);s=os.lstat(p);total+=s.st_size;count+=1
   if total>134217728 or count>10000:raise RuntimeError('static output exceeds limit')
   info=tarfile.TarInfo('tree/'+os.path.relpath(p,base));info.size=s.st_size;info.mode=0o644
   with open(p,'rb') as f:tar.addfile(info,f)
'''


def export(engine, volume, output, destination, commit, seconds, stopped):
    from .project_snapshot import unpack
    relative(output)
    stream = io.BytesIO()
    def collect(data):
        if stream.tell() + len(data) > MAX_ARTIFACT + 4 * 1024 * 1024:
            raise ValueError('静态预览产物超过上限')
        stream.write(data)
    result = engine.run(volume.spec(['python3', '-I', '-c', EXPORT, output, commit], seconds), seconds,
                        cancel=stopped, output=collect)
    if result.get('reason') != 'exited' or result.get('returncode') != 0 or result.get('cleanup') is not True:
        raise ValueError('静态预览产物导出或回收失败')
    stream.seek(0)
    result = unpack(stream, destination)
    if result['commit'] != commit or not (destination / 'index.html').is_file():
        raise ValueError('静态预览缺少固定版本首页')
    files = {}
    for file in sorted(destination.rglob('*')):
        if file.is_file():
            raw = file.read_bytes()
            files[file.relative_to(destination).as_posix()] = {'size':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'digest':digest, 'commit':commit, 'files':files}


def publish(data_dir, folder, row, artifact):
    receipt = dict(artifact, candidate_id=row['id'], run_id=row['run_id'], ticket_id=row['ticket_id'])
    path = folder / 'static-manifest.json'
    _atomic_json(path, receipt)
    return {'digest':artifact['digest'], 'commit':row['commit_sha'], 'manifest':path.relative_to(data_dir).as_posix()}


def _receipt(data_dir, row, verification):
    item = verification.get('static_preview')
    if (not isinstance(item, dict) or verification.get('check') != 'pass' or
            verification.get('verification_current') is not True or
            verification.get('checked_commit') != row['commit_sha'] or
            verification.get('checked_base') != row['base_commit']):
        return None
    name = relative(item.get('manifest'))
    base = Path(data_dir)
    path = base.joinpath(*name.parts)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('预览产物路径已变化')
    receipt = json.loads(path.read_text())
    if (receipt.get('candidate_id') != row['id'] or receipt.get('run_id') != row['run_id'] or
            receipt.get('ticket_id') != row['ticket_id'] or receipt.get('commit') != row['commit_sha'] or
            item.get('commit') != row['commit_sha'] or receipt.get('digest') != item.get('digest') or
            not isinstance(receipt.get('files'), dict)):
        raise ValueError('预览产物与候选不一致')
    digest = hashlib.sha256(json.dumps(receipt['files'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if digest != receipt['digest']:
        raise ValueError('预览文件清单已变化')
    return receipt, path.parent / 'static-site'


def view(P, row, verification):
    try:
        result = _receipt(P.data_dir, row, verification)
        if not result:
            return {}
        receipt, root = result
        if 'index.html' not in receipt['files']:raise ValueError('预览首页缺失')
        for name, info in receipt['files'].items():
            relative(name)
            file = root.joinpath(*PurePosixPath(name).parts)
            if any(p.is_symlink() for p in (file, *file.parents)):
                raise ValueError('预览产物路径已变化')
            raw = file.read_bytes()
            if len(raw) != info['size'] or hashlib.sha256(raw).hexdigest() != info['sha256']:
                raise ValueError('预览产物已变化')
        tenant = P.tenant_context.tenant_id
        return {'state':'up', 'kind':'static', 'commit_full':row['commit_sha'],
                'digest':receipt['digest'], 'entry':'/t/'+tenant+'/static-preview/'+str(row['id'])+'/enter',
                'why':'固定版本静态预览；业务验收由指定复核人操作'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'state':'failed', 'kind':'static', 'why':'静态预览产物缺失或与候选不一致'}


def _secret(reg):
    # Existing owner-only session signing material; domain-separated purpose.
    key = bytes.fromhex((reg.data_dir/'session.key').read_text().strip())
    if len(key) != 32:raise ValueError('预览签名配置不可用')
    return key


def _sign(reg, payload):
    raw = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).decode().rstrip('=')
    sig = hmac.new(_secret(reg), ('webuddy-static-preview-v1:'+raw).encode(), hashlib.sha256).hexdigest()
    return raw + '.' + sig


def _unsign(reg, token):
    if not isinstance(token, str) or len(token) > 3000:
        raise ApiError(403, '预览授权无效')
    try:
        raw, signature = token.split('.')
        expected = hmac.new(_secret(reg), ('webuddy-static-preview-v1:'+raw).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError('signature')
        payload = json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
        if not isinstance(payload, dict) or payload.get('expires', 0) < time.time():
            raise ValueError('expired')
        return payload
    except (ValueError, TypeError, KeyError):
        raise ApiError(403, '预览授权已失效，请从工单重新打开') from None


def response(reg, tenant, cid, part, user, origin):
    """Gateway-only read path. No project process or upstream is ever invoked."""
    from .fixloop import verified
    entering = part == 'enter'
    token, _, name = part.partition('/')
    payload = None if entering else _unsign(reg, token)
    if not entering:
        if payload.get('tenant') != tenant or payload.get('candidate') != cid:
            raise ApiError(403, '预览授权不属于此版本')
        user = payload.get('user')
    if not user:
        raise ApiError(401, '请登录后从工单打开预览')
    with reg.authorization_guard():
        context = reg.context(user, tenant)
        if context['tenant']['status'] != 'active' or not context['role']:
            raise ApiError(403, '预览成员权限已失效')
        if payload and payload.get('context') != context['context_token']:
            raise ApiError(403, '预览权限已变化，请从工单重新打开')
        data = Path(context['tenant']['path'])
        expected = reg.data_dir if tenant == 'default' else reg.data_dir/'tenants'/tenant/'data'
        if data != expected or any(p.is_symlink() for p in (data, *data.parents)):
            raise ApiError(403, '预览租户路径不可用')
        with closing(sqlite3.connect('file:'+str(data/'platform.db')+'?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            record = db.execute('''SELECT c.*,t.project_id,p.key project_key FROM code_candidates c
                JOIN tickets t ON t.id=c.ticket_id JOIN projects p ON p.id=t.project_id WHERE c.id=?''',(cid,)).fetchone()
            if not record:
                raise ApiError(404, '预览候选不存在')
            row = dict(record)
            latest = db.execute('SELECT MAX(id) FROM code_candidates WHERE ticket_id=?',(row['ticket_id'],)).fetchone()[0]
            if latest != cid:
                raise ApiError(409, '已有更新候选，请从工单重新打开预览')
        grants = {g['project_id']:g['role'] for g in context['project_grants']}
        if context['role'] != 'admin' and str(row['project_id']) not in grants:
            raise ApiError(403, '没有此项目的预览权限')
        if not profile(data, row['project_key']):
            raise ApiError(403, '此项目静态预览已停用')
        result = _receipt(data, row, verified(data, row['run_id']))
        if not result:
            raise ApiError(409, '当前候选尚无通过验证的静态预览')
        receipt, root = result
        if entering:
            grant = _sign(reg, {'tenant':tenant, 'candidate':cid, 'user':user, 'digest':receipt['digest'],
                                'context':context['context_token'], 'expires':int(time.time()+3600)})
            return 303, b'', 'text/plain', {'Location':'/t/'+tenant+'/static-preview/'+str(cid)+'/'+grant+'/'}
        if payload.get('digest') != receipt['digest']:
            raise ApiError(409, '预览构建已更新，请从工单重新打开')
        name = unquote(name) or 'index.html'
        relative(name)
        info = receipt['files'].get(name)
        if not info:
            raise ApiError(404, '预览文件不存在')
        file = root.joinpath(*PurePosixPath(name).parts)
        if any(p.is_symlink() for p in (file, *file.parents)):
            raise ApiError(409, '预览文件路径已变化')
        raw = file.read_bytes()
        if len(raw) != info['size'] or hashlib.sha256(raw).hexdigest() != info['sha256']:
            raise ApiError(409, '预览文件已变化，请重新构建')
    csp = ("sandbox allow-scripts; default-src 'none'; script-src "+origin+" 'unsafe-inline'; "
           "style-src "+origin+" 'unsafe-inline'; img-src "+origin+" data: blob:; font-src "+origin+" data:; "
           "connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    return 200, raw, mimetypes.guess_type(name)[0] or 'application/octet-stream', {
        'Content-Security-Policy':csp, 'Access-Control-Allow-Origin':'*', 'Referrer-Policy':'no-referrer',
        'Cache-Control':'no-store', 'Cross-Origin-Resource-Policy':'cross-origin'}


def auto_verify(P, actor, cid):
    """Explicit project opt-in only. No automatic human verdict or merge."""
    from . import candidates, project_verify
    row = candidates._row(P, cid)
    project = P.store.project(P.store.ticket(row['ticket_id'])['project_id'])
    setting = profile(P.data_dir, project['key'])
    if not setting or not setting['auto']:
        return None
    try:
        with candidates.guard(P, row['ticket_id']):
            result = project_verify.start(P, actor, cid)
        P.store.event(row['ticket_id'], actor, 'verification', '代码候选已提交，自动构建与预览准备已启动', {'candidate':cid})
        return result
    except (ValueError, ApiError, OSError) as exc:
        P.store.event(row['ticket_id'], actor, 'verification', '自动构建未启动：'+str(exc), {'candidate':cid})
        return None
