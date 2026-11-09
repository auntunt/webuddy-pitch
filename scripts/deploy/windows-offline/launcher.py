"""Portable Windows launcher. No downloads, system installation or account copying."""
import argparse
import datetime
import hashlib
import ipaddress
import json
import os
import secrets
import socket
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent


def inventory(root):
    """Report-only manifest comparison: mismatches are listed, never fatal."""
    report = {'bundle_files_total': 0, 'bundle_files_changed': [], 'bundle_files_missing': []}
    manifest_path = root / 'MANIFEST.json'
    if not manifest_path.is_file():
        report['error'] = 'MANIFEST.json missing'
        return report
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    report['bundle_files_total'] = len(manifest)
    for name, digest in manifest.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            report['bundle_files_missing'].append(name)
            continue
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                report['bundle_files_changed'].append(name)
    report['bundle_files_changed_count'] = len(report['bundle_files_changed'])
    report['bundle_files_missing_count'] = len(report['bundle_files_missing'])
    report['bundle_files_changed'] = report['bundle_files_changed'][:50]
    report['bundle_files_missing'] = report['bundle_files_missing'][:50]
    return report


def config_path(root, env):
    """--config / WEBUDDY_CONFIG > %LOCALAPPDATA%\\Webuddy\\config.json > defaults.

    The returned path is also what the server edits via the 访问方式 card, so it
    points at LOCALAPPDATA even when no file exists yet (survives re-unpacking)."""
    env_value = env.get('WEBUDDY_CONFIG', '')
    if env_value:
        return Path(env_value)
    local = Path(env.get('LOCALAPPDATA', str(Path.home()))) / 'Webuddy' / 'config.json'
    return local


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
    host = config.get('host', env.get('TMH_HOST', '0.0.0.0'))
    port = int(config.get('port', env.get('TMH_PORT', '8790')))
    if not isinstance(host, str) or not 1 <= port <= 65535:
        raise ValueError('Invalid host or port')
    tools = config.get('tools', {})
    if set(tools) - {'codex', 'claude', 'git', 'node', 'cursor'}:
        raise ValueError('Unknown tool override')
    return config, env, data, host, port


VIRTUAL_NAMES = re.compile(r'vEthernet|WSL|Hyper-V|VMware|VirtualBox|TAP|TUN|Meta|Clash|Wintun|Loopback|Bluetooth', re.I)
VPN_TUNNEL = ipaddress.ip_network('198.18.0.0/15')


def lan_addresses(rows):
    """Usable LAN IPv4 addresses from Get-NetIPConfiguration rows (dicts with alias, description, ipv4, gateway, up).
    Adapters must be up with a default gateway; virtual, tunnel and benchmark ranges are excluded. RFC 1918 first."""
    found = []
    for row in rows:
        address = str(row.get('ipv4') or '')
        if not row.get('up') or not row.get('gateway'):
            continue
        if VIRTUAL_NAMES.search('%s %s' % (row.get('alias') or '', row.get('description') or '')):
            continue
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.version != 4 or ip.is_loopback or ip.is_link_local or ip in VPN_TUNNEL:
            continue
        if address not in found:
            found.append(address)
    private = [a for a in found if ipaddress.ip_address(a).is_private]
    return private + [a for a in found if a not in private]


def windows_adapter_rows():
    # Adapter names are localised (e.g. 以太网); force UTF-8 so decoding never depends on the console code page.
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-NetIPConfiguration | ForEach-Object { [pscustomobject]@{ alias=$_.InterfaceAlias; "
              "description=$_.InterfaceDescription; ipv4=($_.IPv4Address | Select-Object -First 1).IPAddress; "
              "gateway=($_.IPv4DefaultGateway | Select-Object -First 1).NextHop; "
              "up=($_.NetAdapter.Status -eq 'Up') } } | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, encoding='utf-8', errors='replace', timeout=20).stdout
        data = json.loads(out or '[]')
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return [data] if isinstance(data, dict) else data


def primary_ipv4():
    """First usable LAN address; see lan_addresses for the filter."""
    if os.name == 'nt':
        found = lan_addresses(windows_adapter_rows())
        return found[0] if found else ''
    return _default_route_ipv4()


def _default_route_ipv4():
    """IPv4 of the interface with the default route; link-local/loopback skipped."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(('192.0.2.1', 9))  # route selection only; no packet is sent
            addr = probe.getsockname()[0]
        finally:
            probe.close()
        ip = ipaddress.ip_address(addr)
        if ip.version == 4 and not ip.is_loopback and not ip.is_link_local:
            return addr
    except OSError:
        pass
    try:
        for addr in socket.gethostbyname_ex(socket.gethostname())[2]:
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if ip.version == 4 and not ip.is_loopback and not ip.is_link_local:
                return addr
    except OSError:
        pass
    return ''


def lan_bootstrap(filename, config, env, host, port, persist=True):
    """LAN default: persist a generated token + public URL into the resolved config.

    An explicit --config/WEBUDDY_CONFIG file stays read-only (persist=False): the
    token still applies to this session, it is just not written into a user file."""
    if host not in ('0.0.0.0', '::'):
        return None
    changed = False
    if 'TMH_TOKEN' not in env:
        env['TMH_TOKEN'] = secrets.token_urlsafe(24)
        changed = True
    if 'TMH_PUBLIC_URL' not in env:
        address = primary_ipv4()
        if address:
            env['TMH_PUBLIC_URL'] = 'http://%s:%d' % (address, port)
            changed = True
    if changed and persist:
        target = Path(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        written = dict(config)
        stored = dict(written.get('environment') or {})
        for key in ('TMH_TOKEN', 'TMH_PUBLIC_URL'):
            if key in env:
                stored.setdefault(key, env[key])
        written['environment'] = stored
        fd, tmp = tempfile.mkstemp(prefix='.config-', dir=target.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(written, f, ensure_ascii=False, indent=2)
                f.write('\n')
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return env.get('TMH_PUBLIC_URL', '')


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
    env['WEBUDDY_CODEX_BIN'] = selected['codex']['path']
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
                                capture_output=True, encoding='utf-8', errors='replace', timeout=120)
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
            from tmh.platform.executor_setup import cursor_failure
            known = cursor_failure(result.stdout + result.stderr)
            if known:
                report['error'] = '%s（%s）' % (known[0], known[1])
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
    filename = args.config or (str(config_path(ROOT, os.environ)) if config_path(ROOT, os.environ).is_file() else '')
    config, env, data, host, port = configuration(ROOT, filename)
    env['WEBUDDY_BUNDLE_CONFIG'] = str(args.config or config_path(ROOT, env))
    selected, env = resolve_tools(ROOT, config.get('tools', {}), env, disabled_executors(data))
    if args.action == 'tool':
        if not args.arguments or args.arguments[0] not in selected or not selected[args.arguments[0]].get('path'):
            raise ValueError('tool requires an installed codex, claude, git, node or cursor, followed by its arguments')
        return subprocess.call([selected[args.arguments[0]]['path'], *args.arguments[1:]], env=env)
    from tmh.deployment import check_config, load_secrets
    report = dict(tools=selected, data_dir=str(data),
                  url='http://%s:%s/' % (host, port), configuration=check_config(data),
                  model_access='not_checked', authentication='not_checked')
    if args.action == 'check':
        report.update(inventory(ROOT))
    try:
        from tmh.platform.executor_setup import scan as executor_scan
        report['executor_scan'] = executor_scan()
    except Exception as exc:  # noqa: BLE001 - a scanner hiccup must not mask the bundle report
        report['executor_scan'] = {'error': str(exc)}
    if args.action == 'check' and selected['cursor'].get('path'):
        # Reported, never blocking: one real no-tools Cursor request proves the
        # model connection; a version number or saved login does not. Start skips
        # it (it can take a minute); the 智能体 page runs the same test on demand.
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
    public = lan_bootstrap(filename or config_path(ROOT, env), config, env, host, port,
                           persist=not args.config)  # explicit --config/WEBUDDY_CONFIG stays read-only
    os.environ.update(env)
    if host in ('0.0.0.0', '::'):
        # A token-protected server answers 401 to the bare loopback address too.
        print('本机地址：http://127.0.0.1:%d/?token=%s' % (port, env['TMH_TOKEN']))
        for address in (lan_addresses(windows_adapter_rows()) if os.name == 'nt' else []) or ([public] if public else []):
            print('局域网地址：http://%s:%d/?token=%s' % (address, port, env['TMH_TOKEN']))
        print('如果其他电脑无法连接：请以管理员身份运行 configure-firewall.ps1（或在 Windows 防火墙提示时允许 Python）')
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
