"""Portable Windows launcher. No downloads, system installation or account copying."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def verify(root):
    manifest = json.loads((root / 'MANIFEST.json').read_text(encoding='utf-8'))
    for name, digest in manifest.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('Missing or unsafe bundle file: ' + name)
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != digest:
            raise ValueError('Bundle checksum mismatch: ' + name)
    return len(manifest)


def configuration(root, filename):
    config = json.loads(Path(filename).read_text(encoding='utf-8-sig')) if filename else {}
    unknown = set(config) - {'data_dir', 'host', 'port', 'environment', 'tools'}
    if unknown:
        raise ValueError('Unknown config fields: ' + ', '.join(sorted(unknown)))
    env = os.environ.copy()
    for key, value in config.get('environment', {}).items():
        if not isinstance(value, str):
            raise ValueError('Environment values must be strings: ' + key)
        env[key] = value
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONUTF8'] = '1'
    local = Path(env.get('LOCALAPPDATA', str(Path.home()))) / 'Webuddy' / 'data'
    data = Path(config.get('data_dir') or env.get('TMH_DATA_DIR') or local).expanduser().resolve()
    host = config.get('host', env.get('TMH_HOST', '127.0.0.1'))
    port = int(config.get('port', env.get('TMH_PORT', '8790')))
    if not isinstance(host, str) or not 1 <= port <= 65535:
        raise ValueError('Invalid host or port')
    tools = config.get('tools', {})
    if set(tools) - {'codex', 'claude', 'git', 'node'}:
        raise ValueError('Unknown tool override')
    return config, env, data, host, port


def resolve_tools(root, overrides, environment):
    release = json.loads((root / 'release.json').read_text(encoding='utf-8'))
    env = environment.copy()
    selected = {}
    # Resolve every local executable BEFORE adding any private fallback to PATH.
    for name in ('node', 'git', 'codex', 'claude'):
        explicit = overrides.get(name)
        if explicit and not Path(explicit).is_absolute():
            raise ValueError('Tool override must be an absolute path: ' + name)
        local = explicit or shutil.which(name, path=env.get('PATH', ''))
        path = Path(local) if local else root / release['tools'][name]
        if not path.is_file():
            raise ValueError('Tool not found: ' + name)
        selected[name] = dict(path=str(path), source='configured' if explicit else 'local' if local else 'bundled')
    # Explicit selection must win over PATH. This only affects this process tree.
    dirs = [str(Path(row['path']).parent) for row in selected.values()]
    dirs += [str(root / 'tools/codex/package/vendor/x86_64-pc-windows-msvc/codex-path')]
    env['PATH'] = os.pathsep.join(dirs + [env.get('PATH', '')])
    if not env.get('CLAUDE_CODE_GIT_BASH_PATH'):
        git_root = Path(selected['git']['path']).parent.parent
        bash = git_root / 'bin/bash.exe'
        if not bash.is_file():
            bash = root / 'tools/git/bin/bash.exe'
        env['CLAUDE_CODE_GIT_BASH_PATH'] = str(bash)
    for name, row in selected.items():
        result = subprocess.run([row['path'], '--version'], env=env, capture_output=True,
                                encoding='utf-8', errors='replace', timeout=30)
        if result.returncode:
            # Do not silently replace a broken local installation or print its potentially private stderr.
            raise ValueError(name + ' --version failed; repair it or set an explicit tools path in your config')
        row['version'] = result.stdout.strip()
    return selected, env


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=os.environ.get('WEBUDDY_CONFIG'), help='External UTF-8 JSON; never overwritten')
    parser.add_argument('action', choices=('check', 'start', 'tool'))
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if os.name != 'nt':
        raise ValueError('This bundle supports Windows x86_64 only')
    count = verify(ROOT)
    config, env, data, host, port = configuration(ROOT, args.config)
    selected, env = resolve_tools(ROOT, config.get('tools', {}), env)
    if args.action == 'tool':
        if not args.arguments or args.arguments[0] not in selected:
            raise ValueError('tool requires codex, claude, git or node, followed by its arguments')
        return subprocess.call([selected[args.arguments[0]]['path'], *args.arguments[1:]], env=env)
    from tmh.deployment import check_config, load_secrets
    report = dict(bundle_files_verified=count, tools=selected, data_dir=str(data),
                  url='http://%s:%s/' % (host, port), configuration=check_config(data),
                  model_access='not_checked', authentication='not_checked')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if not report['configuration']['ok']:
        return 1
    # Check is read-only: it never loads secrets, creates data or starts the platform.
    if args.action == 'check':
        return 0
    if args.arguments:
        raise ValueError('start takes no additional arguments')
    load_secrets(env)
    os.environ.update(env)
    from tmh.cli import main as cli
    from tmh.platform.windows_process import receipt_lock
    with receipt_lock(data / '.offline-server'):
        return cli(['serve', '--data', str(data), '--host', host, '--port', str(port)])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
