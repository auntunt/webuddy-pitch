"""Server-side required CI checks bound to the exact candidate commit."""
import json
import http.client
import time
from contextlib import contextmanager
import os
import re
import tempfile
from pathlib import Path
from . import filelock
from .errors import ApiError
from .development import digest


@contextmanager
def guard(data):
    with (Path(data)/'.project-ci.lock').open('a+b') as lock:
        filelock.try_lock(lock,blocking=True)
        yield


def configuration(data, key):
    path = Path(data)/'project-ci.json'
    values = json.loads(path.read_text()) if path.exists() else {}
    value = values.get(key)
    binding = value
    if value and value.get('connection'):
        path = Path(data)/'ci-connections.json'
        connections = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        binding = {'config': value, 'connection': connections.get(value['connection'])}
    return {'config':value, 'revision':digest(binding)}


def save(data, key, body):
    if set(body) != {'revision','config'}:
        raise ApiError(400,'需要CI配置和当前修订')
    value = body['config']
    if not isinstance(value,dict) or set(value) not in ({'repository','required_checks'}, {'repository','required_checks','provider','connection'}):
        raise ApiError(400,'需要仓库、必需检查及可选的已登记CI连接')
    if not isinstance(value['repository'],str) or len(value['repository']) > 200 or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)+',value['repository']):
        raise ApiError(400,'仓库格式为owner/repository')
    if 'provider' in value:
        from .private_ci import connection
        if value['provider'] not in ('gitlab', 'gitea', 'jenkins') or not isinstance(value['connection'], str):
            raise ApiError(400, '请选择已支持的私有CI连接')
        if value['provider'] == 'gitea' and value['repository'].count('/') != 1:
            raise ApiError(400, 'Gitea仓库格式为owner/repository')
        try:
            connection(data, key, value)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ApiError(400, 'CI连接未登记或未授权给当前项目和仓库') from exc
    elif value['repository'].count('/') != 1:
        raise ApiError(400, 'GitHub仓库格式为owner/repository')
    checks = value['required_checks']
    if not isinstance(checks,list) or not 1 <= len(checks) <= 50 or any(not isinstance(n,str) or not n.strip() for n in checks) or len(set(checks)) != len(checks):
        raise ApiError(400,'请配置不重复的必需CI检查名称，不能以空检查列表通过')
    path = Path(data)/'project-ci.json'
    with guard(data):
        values = json.loads(path.read_text()) if path.exists() else {}
        if configuration(data,key)['revision'] != body['revision']:
            raise ApiError(409,'CI配置已变化，请重新读取')
        values[key] = value
        fd,name = tempfile.mkstemp(prefix='.project-ci-',dir=data)
        try:
            with os.fdopen(fd,'w') as stream:
                json.dump(values,stream,ensure_ascii=False,indent=2)
                stream.flush();os.fsync(stream.fileno())
            os.replace(name,path)
        finally:
            Path(name).unlink(missing_ok=True)
    return configuration(data,key)


def check(data, key, commit):
    configured = configuration(data,key)
    config = configured['config']
    if not config:
        return dict(state='not_configured', commit=commit, checks=[], message='尚未配置该项目的必需CI检查', **configured)
    if not re.fullmatch(r'[0-9a-f]{40}',commit):
        raise ApiError(400,'CI必须绑定完整提交编号')
    if config.get('provider'):
        from .private_ci import check as private_check
        try:
            return dict(private_check(data,key,config,commit), **configured)
        except (OSError,http.client.HTTPException,ValueError,KeyError,TypeError,AttributeError):
            return dict(state='blocked',commit=commit,checks=[],message='无法核实私有CI；请检查连接授权、凭据和原始回执',**configured)
    headers = {'Accept':'application/vnd.github+json','User-Agent':'Webuddy-CI','X-GitHub-Api-Version':'2022-11-28'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    runs = []
    deadline = time.monotonic() + 20
    try:
        for page in range(1,11):
            remaining = deadline - time.monotonic()
            if remaining <= 0:raise TimeoutError('CI lookup deadline')
            path = '/repos/%s/commits/%s/check-runs?filter=latest&per_page=100&page=%d' % (config['repository'],commit,page)
            connection = http.client.HTTPSConnection('api.github.com',timeout=remaining)
            try:
                connection.request('GET',path,headers=headers)
                response = connection.getresponse()
                if response.status != 200:raise ValueError('GitHub response is not successful')
                raw = response.read(4*1024*1024+1)
                if len(raw)>4*1024*1024:raise ValueError('GitHub response is too large')
                payload = json.loads(raw)
            finally:
                connection.close()
            if not isinstance(payload,dict) or type(payload.get('total_count')) is not int or not isinstance(payload.get('check_runs'),list):
                raise ValueError('Invalid check runs response')
            batch = payload['check_runs']
            for run in batch:
                if (not isinstance(run,dict) or any(field not in run for field in ('name','head_sha','status','conclusion','id','html_url'))
                        or not isinstance(run.get('app'),dict)):
                    raise ValueError('Incomplete check run')
            runs.extend(batch)
            if len(runs) >= payload['total_count']:
                break
        else:
            return dict(state='blocked',commit=commit,checks=[],message='CI检查超过分页上限，不能以部分结果通过',**configured)
    except (OSError,http.client.HTTPException,ValueError) as exc:
        return dict(state='blocked',commit=commit,checks=[],message='无法核实GitHub CI（%s）'%type(exc).__name__,**configured)
    results = []
    for name in config['required_checks']:
        matches = [r for r in runs if r['name']==name and r['head_sha']==commit and r.get('app',{}).get('slug')=='github-actions']
        # Duplicate workflow names are ambiguous; an unrelated success cannot hide a failed run.
        state = 'missing' if not matches else 'pass' if all(r['status']=='completed' and r['conclusion']=='success' for r in matches) else 'pending' if any(r['status']!='completed' for r in matches) else 'fail'
        results.append({'name':name,'state':state,'runs':[{'id':r['id'],'status':r['status'],'conclusion':r['conclusion'],'url':r['html_url']} for r in matches]})
    return dict(state='pass' if all(r['state']=='pass' for r in results) else 'blocked',commit=commit,checks=results,**configured)
