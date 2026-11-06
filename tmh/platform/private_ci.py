"""Operator-owned CI endpoints. Project members cannot supply destinations or secrets."""
import http.client
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, urlsplit


def connection(data, key, config):
    path = Path(data) / 'ci-connections.json'
    values = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    value = values.get(config.get('connection'))
    if not isinstance(value, dict) or value.get('provider') != config.get('provider'):
        raise ValueError('CI connection is not registered')
    # Explicit project AND repository binding prevents a project manager from
    # borrowing an operator credential to query another customer's repository.
    if config['repository'] not in value.get('projects', {}).get(key, []):
        raise ValueError('CI connection is not granted to this project/repository')
    url = urlsplit(value['url'])
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or any(c in value['url'] for c in '\r\n')):
        raise ValueError('CI endpoint must be an HTTPS origin/base path')
    token_env = value.get('token_env', '')
    if token_env and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', token_env):
        raise ValueError('Invalid credential environment name')
    return value


def check(data, key, config, commit):
    value = connection(data, key, config)
    endpoint = urlsplit(value['url'])
    token = os.environ.get(value.get('token_env', ''), '')
    if value.get('token_env') and not token:
        raise ValueError('Configured CI credential is unavailable')
    provider = config['provider']
    headers = {'Accept': 'application/json', 'User-Agent': 'Webuddy-CI'}
    if token:
        headers.update({'PRIVATE-TOKEN': token} if provider == 'gitlab' else {'Authorization': 'token ' + token})
    deadline = time.monotonic() + 20
    requests = 0

    def get(path):
        nonlocal requests
        requests += 1
        remaining = deadline - time.monotonic()
        if remaining <= 0 or requests > 30:
            raise TimeoutError('CI query budget exceeded')
        client = http.client.HTTPSConnection(endpoint.netloc, timeout=remaining)
        try:
            client.request('GET', endpoint.path.rstrip('/') + path, headers=headers)
            response = client.getresponse()
            if response.status != 200:
                raise ValueError('CI response is not successful')
            raw = response.read(4*1024*1024+1)
            if len(raw) > 4*1024*1024:
                raise ValueError('CI response too large')
            return json.loads(raw)
        finally:
            client.close()

    def pages(path):
        result = []
        for page in range(1, 11):
            batch = get(path + ('&' if '?' in path else '?') + 'per_page=100&page=' + str(page))
            if not isinstance(batch, list):
                raise ValueError('Invalid CI list')
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise ValueError('CI pagination incomplete')

    checks = []
    if provider == 'gitlab':
        root = '/api/v4/projects/' + quote(config['repository'], safe='')
        pipelines = pages(root + '/pipelines?sha=' + commit)
        for pipeline in pipelines:
            if not isinstance(pipeline, dict) or pipeline.get('sha') != commit or type(pipeline.get('id')) is not int or 'status' not in pipeline:
                raise ValueError('Pipeline commit mismatch')
        # A rerun creates a newer pipeline. Older failures remain in the CI
        # system; they cannot mask the latest pipeline, nor prove this one.
        for pipeline in sorted(pipelines, key=lambda p: p['id'], reverse=True)[:1]:
            if pipeline['status'] != 'success':
                return {'state':'blocked','commit':commit,'checks':[],
                        'message':'当前提交最新流水线尚未成功','pipeline_id':pipeline['id'],
                        'pipeline_status':pipeline['status']}
            jobs = pages(root + '/pipelines/' + str(pipeline['id']) + '/jobs?include_retried=false')
            for job in jobs:
                if (not isinstance(job, dict) or job.get('commit', {}).get('id') != commit
                        or job.get('pipeline', {}).get('id') != pipeline['id']
                        or any(field not in job for field in ('name', 'status', 'id', 'web_url'))):
                    raise ValueError('Job binding mismatch')
                checks.append({'name': job['name'], 'status': job['status'], 'id': job['id'], 'url': job['web_url']})
    elif provider == 'gitea':
        root = '/api/v1/repos/' + config['repository'] + '/commits/' + commit + '/status'
        for page in range(1, 11):
            result = get(root + '?limit=100&page=' + str(page))
            if (not isinstance(result, dict) or result.get('sha') != commit
                    or type(result.get('total_count')) is not int or not isinstance(result.get('statuses'), list)):
                raise ValueError('Commit status binding mismatch')
            for status in result['statuses']:
                if not isinstance(status, dict) or any(f not in status for f in ('context', 'status', 'id', 'target_url')):
                    raise ValueError('Incomplete commit status')
                checks.append({'name': status['context'], 'status': status['status'], 'id': status['id'], 'url': status['target_url']})
            if len(checks) >= result['total_count']:
                break
        else:
            raise ValueError('CI pagination incomplete')
    else:
        raise ValueError('Unsupported CI provider')
    results = []
    for name in config['required_checks']:
        matches = [c for c in checks if c['name'] == name]
        state = 'missing' if not matches else 'pass' if all(c['status'] == 'success' for c in matches) else 'blocked'
        results.append({'name': name, 'state': state, 'runs': matches})
    return {'state': 'pass' if all(c['state'] == 'pass' for c in results) else 'blocked',
            'commit': commit, 'checks': results}
