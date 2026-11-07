"""Customer artifact checks. Findings contain paths and categories, never matched contents."""
import io
import re
from pathlib import PurePosixPath
import zipfile

PRIVATE_KEY = re.compile(rb'(?m)^-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----')
TOKEN = re.compile(rb'\b(?:sk-proj-|sk-ant-|ghp_|github_pat_)[A-Za-z0-9_-]{32,}')
FORBIDDEN_PARTS = {'.git', '.claude', '.codex', '__pycache__', 'self-improvement', 'progress-archive', 'audit', 'evidence', '.tmh', 'snapshots'}
STATE_SUFFIXES = ('.db', '.sqlite', '.sqlite3', '.log', '.jsonl', '.pyc')
TEXT_SUFFIXES = ('.py', '.md', '.txt', '.json', '.toml', '.yaml', '.yml', '.html', '.ini', '.cfg', '.pem', '.key')


def inspect_zip(package, *, resource_files=None, prefix='', official_stdlib=False):
    findings = []
    seen = set()
    nested_files = 0
    resources = set(resource_files) if resource_files is not None else None
    for info in package.infolist():
        if info.is_dir():
            continue
        name = info.filename
        path = prefix + name
        parts = PurePosixPath(name).parts
        lower = tuple(p.lower() for p in parts)
        if name in seen or '..' in parts or name.startswith(('/', '\\')):
            findings.append(dict(path=path, category='unsafe_or_duplicate_path'))
        seen.add(name)
        # npm ships cache implementation modules; these are source, not cached state.
        npm_cache_module = (name.startswith('Webuddy/tools/node/') and name.endswith('.js') and
                            any(segment in name for segment in ('/node_modules/make-fetch-happen/lib/cache/',
                                                               '/node_modules/undici/lib/web/cache/')))
        if any(p in FORBIDDEN_PARTS for p in lower) or 'worker-logs' in lower or ('cache' in lower and not npm_cache_module):
            findings.append(dict(path=path, category='internal_or_generated_directory'))
        if name.lower().endswith(STATE_SUFFIXES) and not (official_stdlib and name.endswith('.pyc')):
            findings.append(dict(path=path, category='state_or_build_cache'))
        if any(p in {'auth.json', 'credential.json', 'credentials.json', '.env', '.ds_store'} for p in lower):
            findings.append(dict(path=path, category='personal_configuration'))
        marker = 'tmh/_resources/'
        if marker in name and resources is not None:
            relative = name.split(marker, 1)[1]
            if relative not in resources:
                findings.append(dict(path=path, category='resource_not_allowlisted'))
        if name.endswith(('.zip', '.whl')):
            # The embedded standard library is an official compiled runtime, not a build-machine cache.
            with zipfile.ZipFile(io.BytesIO(package.read(info))) as nested:
                result = inspect_zip(nested, resource_files=resource_files, prefix=path + '!/',
                                     official_stdlib=name.endswith('runtime/python/python314.zip'))
            findings.extend(result['findings'])
            nested_files += result['files']
        elif name.lower().endswith(TEXT_SUFFIXES):
            data = package.read(info)
            if PRIVATE_KEY.search(data):
                findings.append(dict(path=path, category='private_key_material'))
            if TOKEN.search(data):
                findings.append(dict(path=path, category='credential_like_value'))
            if '/_resources/' in name or name.startswith(('docs/', 'templates/', 'skills/', 'agents/', 'kb/')):
                if any(mark in data for mark in (b'docs/self-improvement/', b'43.153.76.85', b'/Users/auntlee', b'ralph-port-progress', b'JeecgBoot', b'JB-6', '那轮评审'.encode())):
                    findings.append(dict(path=path, category='internal_resource_content'))
    return dict(ok=not findings, files=len(seen) + nested_files, findings=findings,
                check='paths_nested_archives_resources_and_high_confidence_credentials')


def require_clean(path, resource_files):
    with zipfile.ZipFile(path) as package:
        result = inspect_zip(package, resource_files=resource_files)
        package_names = package.namelist()
    present = {n.split('tmh/_resources/', 1)[1] for n in package_names if 'tmh/_resources/' in n}
    for missing in sorted(set(resource_files) - present):
        result['findings'].append(dict(path='tmh/_resources/' + missing, category='required_resource_missing'))
    result['ok'] = not result['findings']
    if not result['ok']:
        import json
        raise ValueError(json.dumps(result['findings'], ensure_ascii=True))
    return result
