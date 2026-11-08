"""Portable Windows launcher. No downloads, system installation or account copying."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


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
    if set(tools) - {'codex', 'claude', 'git', 'node', 'cursor'}:
        raise ValueError('Unknown tool override')
    return config, env, data, host, port


def disabled_executors(data):
    """Executors switched off per install (<data>/agents.json enabled:false)."""
    try:
        raw = json.loads((Path(data) / 'agents.json').read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return ()
    return tuple(name for name, c in raw.items() if isinstance(c, dict) and c.get('enabled') is False)


def resolve_tools(root, overrides, environment, disabled=()):
    release = json.loads((root / 'release.json').read_text(encoding='utf-8'))
    env = environment.copy()
    selected = {}
    # Resolve every local executable BEFORE adding any private fallback to PATH.
    for name in (n for n in ('node', 'git', 'codex', 'claude') if n not in disabled):
        explicit = overrides.get(name)
        if explicit and not Path(explicit).is_absolute():
            raise ValueError('Tool override must be an absolute path: ' + name)
        local = explicit or shutil.which(name, path=env.get('PATH', ''))
        path = Path(local) if local else root / release['tools'][name]
        if not path.is_file():
            raise ValueError('Tool not found: ' + name)
        selected[name] = dict(path=str(path), source='configured' if explicit else 'local' if local else 'bundled')
    explicit = overrides.get('cursor')
    if explicit and not Path(explicit).is_absolute():
        raise ValueError('Tool override must be an absolute path: cursor')
    local = explicit or shutil.which('agent', path=env.get('PATH', '')) or shutil.which('cursor-agent', path=env.get('PATH', ''))
    if local:
        if not Path(local).is_file():
            raise ValueError('Tool not found: cursor')
        selected['cursor'] = dict(path=str(local), source='configured' if explicit else 'local', available=True)
        env['WEBUDDY_CURSOR_BIN'] = str(local)
    else:
        selected['cursor'] = dict(source='not_installed', available=False)
    # Explicit selection must win over PATH. This only affects this process tree.
    dirs = [str(Path(row['path']).parent) for row in selected.values() if row.get('path')]
    dirs += [str(root / 'tools/codex/package/vendor/x86_64-pc-windows-msvc/codex-path')]
    env['PATH'] = os.pathsep.join(dirs + [env.get('PATH', '')])
    if not env.get('CLAUDE_CODE_GIT_BASH_PATH'):
        git_root = Path(selected['git']['path']).parent.parent
        bash = git_root / 'bin/bash.exe'
        if not bash.is_file():
            bash = root / 'tools/git/bin/bash.exe'
        env['CLAUDE_CODE_GIT_BASH_PATH'] = str(bash)
    for name, row in selected.items():
        if not row.get('path'):
            continue
        result = subprocess.run([row['path'], '--version'], env=env, capture_output=True,
                                encoding='utf-8', errors='replace', timeout=30)
        if result.returncode:
            # Do not silently replace a broken local installation or print its potentially private stderr.
            raise ValueError(name + ' --version failed; repair it or set an explicit tools path in your config')
        row['version'] = result.stdout.strip()
    return selected, env


def _preflight_excerpt(output):
    lines = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            if re.search(r'error|fail|trust|auth|login|permission|denied|timed? out|connect|workspace', line, re.I):
                lines.append(line)
            continue
        if isinstance(event, str):
            lines.append(event)
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'result' or event.get('is_error') or event.get('type') == 'error':
            value = event.get('result') or event.get('error') or event.get('message') or event.get('subtype')
            if value:
                lines.append(str(value))
    text = '\n'.join(lines[-6:])[-2000:]
    text = re.sub(r'(?i)(Bearer\s+)\S+', r'\1[REDACTED]', text)
    text = re.sub(r'\b(?:sk-|cur_)[A-Za-z0-9_-]+', '[REDACTED]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|access_token|refresh_token|authorization)[\s\"\x27:=]+)[^\s,\"\x27]+', r'\1[REDACTED]', text)
    return text


def cursor_preflight(cursor_bin, env, workdir):
    """One no-tools request in a fresh empty directory; PASS only on CURSOR_OK.

    --trust is scoped to this newly created diagnostic workspace only; project
    trust, global Cursor settings and tool permissions are unchanged."""
    workdir = Path(workdir)
    if workdir.is_symlink() or any(workdir.iterdir()):
        raise RuntimeError('Diagnostic workspace is not a fresh empty directory')
    prompt = 'Reply with exactly CURSOR_OK. Do not use tools, read files, or modify files.'
    cmd = [cursor_bin, '--trust', '--print', '--output-format', 'stream-json',
           '--sandbox', 'disabled', '--mode', 'ask']
    report = {'checked_at': datetime.datetime.now().isoformat(timespec='seconds'),
              'ok': False, 'command': cmd}
    try:
        result = subprocess.run(cmd, input=prompt, cwd=str(workdir), env=env,
                                capture_output=True, encoding='utf-8', errors='replace', timeout=45)
        replies = []
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') == 'result' and not event.get('is_error'):
                replies.append(str(event.get('result', '')))
        report.update(returncode=result.returncode,
                      ok=result.returncode == 0 and any('CURSOR_OK' in value for value in replies))
        if not report['ok']:
            report['error_excerpt'] = _preflight_excerpt(result.stdout + result.stderr)
            text = (result.stdout + result.stderr).lower()
            if 'uv_os_get_passwd' in text:
                report['error'] = 'Cursor could not read Windows user information (uv_os_get_passwd).'
            elif 'not logged in' in text or 'unauthenticated' in text:
                report['error'] = 'Cursor authentication failed; use Cursor login or a supported Cursor API key.'
            elif 'sandbox mode is enabled but not available' in text:
                report['error'] = 'Unsupported sandbox mode.'
            else:
                report['error'] = 'No successful CURSOR_OK result; inspect the evidence directory.'
    except (OSError, subprocess.SubprocessError) as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
    return report


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
    selected, env = resolve_tools(ROOT, config.get('tools', {}), env, disabled_executors(data))
    if args.action == 'tool':
        if not args.arguments or args.arguments[0] not in selected or not selected[args.arguments[0]].get('path'):
            raise ValueError('tool requires an installed codex, claude, git, node or cursor, followed by its arguments')
        return subprocess.call([selected[args.arguments[0]]['path'], *args.arguments[1:]], env=env)
    from tmh.deployment import check_config, load_secrets
    report = dict(bundle_files_verified=count, tools=selected, data_dir=str(data),
                  url='http://%s:%s/' % (host, port), configuration=check_config(data),
                  model_access='not_checked', authentication='not_checked')
    try:
        from tmh.platform.executor_setup import scan as executor_scan
        report['executor_scan'] = executor_scan()
    except Exception as exc:  # noqa: BLE001 - a scanner hiccup must not mask the bundle report
        report['executor_scan'] = {'error': str(exc)}
    if selected['cursor'].get('path'):
        # Reported, never blocking: one real no-tools Cursor request proves the
        # model connection; a version number or saved login does not.
        workdir = Path(tempfile.mkdtemp(prefix='cursor-connection-'))
        report['cursor_connection'] = cursor_preflight(selected['cursor']['path'], env, workdir)
        report['cursor_connection']['evidence_dir'] = str(workdir)
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
