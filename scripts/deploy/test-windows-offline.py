"""Actual Windows smoke test for an extracted offline bundle; uses only synthetic state."""
import argparse
import asyncio
from datetime import timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request


def cursor_e2e(root, evidence):
    """Real Cursor API run end-to-end through the bundle. Skipped without the key."""
    out = Path(evidence)
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'cursor-e2e.json'
    if not os.environ.get('CURSOR_API_KEY'):
        target.write_text(json.dumps({'cursor_e2e': 'not_run (no CURSOR_API_KEY secret)'}, ensure_ascii=False))
        return 0
    import urllib.request
    python = root / 'runtime/python/python.exe'
    launcher = root / 'launcher.py'
    check = subprocess.run([str(python), '-B', str(launcher), 'check'],
                           capture_output=True, text=True, encoding='utf-8', timeout=300)
    report = json.loads(check.stdout) if check.returncode == 0 else {}
    conn = report.get('cursor_connection') or {}
    if not conn.get('ok'):
        target.write_text(json.dumps({'cursor_e2e': 'failed', 'stage': 'cursor preflight',
                                      'error': str(conn.get('error') or conn.get('error_excerpt') or check.stdout[:400])}, ensure_ascii=False))
        return 1
    work = Path(tempfile.mkdtemp(prefix='e2e '))
    repo = work / 'fixture 项目'
    repo.mkdir(parents=True)
    subprocess.run(['git', 'init'], cwd=repo, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.email', 'e2e@local'], cwd=repo, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'e2e'], cwd=repo, check=True, capture_output=True)
    app = repo / 'app.py'
    app.write_text('print("hi")\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, capture_output=True, check=True)
    subprocess.run(['git', 'commit', '-m', 'init'], cwd=repo, capture_output=True, check=True)
    data = work / 'data'
    config = work / 'config.json'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config.write_text(json.dumps({'data_dir': str(data), 'host': '127.0.0.1', 'port': port}))
    server = subprocess.Popen([str(python), '-B', str(launcher), '--config', str(config), 'start'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def api(method, path, body=None):
        request = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), method=method,
                                         data=json.dumps(body).encode() if body is not None else None,
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise AssertionError('%s %s -> %s: %s' % (method, path, e.code, e.read()[:300]))
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/api/meta' % port, timeout=2)
                break
            except OSError:
                time.sleep(1)
        else:
            raise AssertionError('server did not start')
        api('POST', '/api/projects', {'key': 'e2e', 'name': 'e2e', 'root': str(repo)})
        run = api('POST', '/api/projects/e2e/runs', {'mode': 'fix', 'agent': 'cursor',
                  'target': '在 app.py 末尾加一行注释 # e2e-done，保存后用 shell 运行 git status 确认改动'})
        rid = run.get('run', {}).get('id') or run.get('id')
        status, detail = '', {}
        deadline = time.time() + 480
        while time.time() < deadline:
            detail = api('GET', '/api/runs/%d' % rid)
            status = detail.get('status', '')
            if status in ('done', 'failed', 'cancelled'):
                break
            time.sleep(5)
        changed = app.read_text(encoding='utf-8')
        rejected = (detail.get('output') or '').count('被拒绝的命令')
        record = {'cursor_e2e': 'passed' if (status == 'done' and rejected == 0 and '# e2e-done' in changed)
                  else 'failed', 'run': rid, 'status': status, 'rejected_calls': rejected,
                  'file_changed': '# e2e-done' in changed,
                  'result_excerpt': (detail.get('result') or '')[:300]}
        target.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        return 0 if record['cursor_e2e'] == 'passed' else 1
    except Exception as exc:
        target.write_text(json.dumps({'cursor_e2e': 'failed', 'error': str(exc)[:400]}, ensure_ascii=False))
        return 1
    finally:
        server.terminate()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle', type=Path)
    p.add_argument('--expect-network-blocked', action='store_true')
    p.add_argument('--cursor-e2e', metavar='EVIDENCE_DIR')
    args = p.parse_args()
    root = args.bundle.resolve()
    if args.cursor_e2e:
        raise SystemExit(cursor_e2e(root, args.cursor_e2e))
    launcher = root / 'launcher.py'
    spec = importlib.util.spec_from_file_location('launcher', launcher)
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    assert launch.inventory(root)['bundle_files_total'] > 1000
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    work = root.parent / 'synthetic smoke 数据'
    work.mkdir(exist_ok=False)
    python = root / 'runtime/python/python.exe'
    default_env = os.environ.copy()
    default_env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    records = {'manifest_sha256': hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()}
    def call(*argv, env=None, ok=True):
        result = subprocess.run([str(python), '-B', str(launcher), *map(str, argv)],
                                capture_output=True, encoding='utf-8', errors='replace',
                                env=env or default_env, timeout=90)
        if ok:
            assert result.returncode == 0, (argv, result.returncode, result.stdout, result.stderr)
        else:
            assert result.returncode != 0, (argv, result.stdout)
        return result
    records['local'] = json.loads(call('check').stdout)
    assert records['local']['model_access'] == 'not_checked'
    # Remove local tools from this process's PATH, without changing the machine PATH.
    env = default_env.copy()
    env['PATH'] = os.environ['SystemRoot'] + r'\System32'
    records['bundled'] = json.loads(call('check', env=env).stdout)
    assert all(records['bundled']['tools'][name]['source'] == 'bundled' for name in ('node', 'git', 'codex', 'claude'))
    assert records['bundled']['tools']['cursor']['available'] is False
    wrapped = subprocess.run([str(root / 'webuddy.cmd'), 'tool', 'codex', '--version'],
                             env=env, capture_output=True, text=True, timeout=90)
    assert wrapped.returncode == 0, (wrapped.stdout, wrapped.stderr)
    records['cmd_wrapper'] = wrapped.stdout.strip()
    if args.expect_network_blocked:
        try:
            socket.create_connection(('1.1.1.1', 443), timeout=3)
        except OSError:
            records['external_tcp'] = 'blocked'
        else:
            raise AssertionError('Outbound TCP was not blocked')
    # Verify binary Python dependencies and all native tool entry points.
    import sqlite3, ssl, cryptography, pypdf, mcp
    import cryptography.hazmat.bindings._rust
    import pydantic_core, rpds
    from tmh.platform import server, process_control
    records['python'] = sys.version
    records['sqlite'] = sqlite3.sqlite_version
    records['ssl'] = ssl.OPENSSL_VERSION
    node = records['bundled']['tools']['node']['path']
    runner = root / 'runtime/python/Lib/site-packages/tmh/platform/project_test_runner.cjs'
    subprocess.run([node, '--check', str(runner)], env=env, check=True)
    # Installed-only synthetic project: static knowledge and both instruction formats.
    project = work / 'sample 项目'
    project.mkdir()
    original_agents = b'# Customer instructions\nKeep these instructions.\n'
    (project / 'AGENTS.md').write_bytes(original_agents)
    (project / 'OrderController.java').write_text('package demo;\n@RestController\nclass OrderController {\n @GetMapping("/orders")\n public String orders() { return "ok"; }\n}\n', encoding='utf-8')
    def project_command(*args):
        result = subprocess.run([str(python), '-B', '-m', 'tmh', *args, '--repo', str(project)],
                                env=env, cwd=work, capture_output=True, text=True, encoding='utf-8', timeout=90)
        assert result.returncode == 0, (args, result.stdout, result.stderr)
        return result.stdout
    for _ in range(2):
        project_command('install')
    assert (project / 'AGENTS.md').read_bytes().startswith(original_agents)
    from tmh import resources
    resource_root = resources.root()
    for name in ('agent-commands.md', 'acceptance.md', 'operating-boundaries.md'):
        assert (project / '.tmh/docs' / name).stat().st_size > 100
    for name in ('independent-verifier.md', 'kb-writer.md'):
        assert (project / '.claude/agents' / name).read_bytes() == (resource_root / 'agents' / name).read_bytes()
    assert (project / '.codex/agents/independent-verifier.toml').is_file()
    records['knowledge_build'] = project_command('kb', 'build')
    records['knowledge_status'] = project_command('kb', 'status')
    records['knowledge_read'] = project_command('kb', 'read', 'index')
    assert records['knowledge_read'].strip()
    vendored = subprocess.run([str(python), '-B', str(project / '.tmh/tool/tmh.py'), '--version'],
                              env=env, cwd=work, capture_output=True, text=True, timeout=30)
    assert vendored.returncode == 0, vendored.stderr
    async def sdk_check(endpoint=None):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        if endpoint:
            arguments = ['-B', '-m', 'tmh.workbench', 'mcp', '--endpoint', endpoint, '--read-only']
        else:
            arguments = ['-B', '-m', 'tmh', 'mcp', '--repo', str(project)]
        sdk_env = dict(env, WEBUDDY_TOKEN='synthetic-offline-token')
        params = StdioServerParameters(command=str(python), args=arguments, env=sdk_env, cwd=str(work))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as client:
                init = await client.initialize()
                names = [t.name for t in (await client.list_tools()).tools]
                good = await client.call_tool('webuddy_projects_list' if endpoint else 'kb_read', {} if endpoint else {'ids': 'index'})
                assert not good.isError, good
                denied = await client.call_tool('webuddy_ticket_create' if endpoint else 'human_accept', {})
                assert denied.isError, denied
                return dict(server=init.serverInfo.name, tools=len(names), read='passed', unauthorized_write='denied')
    records['project_mcp'] = asyncio.run(sdk_check())
    data = work / 'state'
    data.mkdir()
    original = b'{"offline-fixture":{"title":"preserve this exact config","bin":"missing-fixture-tool"}}'
    (data / 'agents.json').write_bytes(original)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config = work / 'external config.json'
    config.write_text(json.dumps(dict(data_dir=str(data), port=port,
                                     environment={'TMH_TOKEN': 'synthetic-offline-token'})), encoding='utf-8')
    before = config.read_bytes()
    call('--config', config, 'check', env=env)
    assert {path.name for path in data.iterdir()} == {'agents.json'}
    base = 'http://127.0.0.1:%d' % port
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # Two starts with a supervised stop between them prove persistent readback.
    for attempt in range(2):
        cancel = threading.Event()
        outcomes = []
        def start():
            outcomes.append(process_control.run_process([str(python), '-B', str(launcher), '--config', str(config), 'start'],
                                                env=env, timeout=100, cancel_event=cancel))
        thread = threading.Thread(target=start)
        thread.start()
        try:
            deadline = time.monotonic() + 70
            while True:
                try:
                    with opener.open(base + '/login', timeout=1) as response:
                        assert response.status == 200
                    break
                except OSError:
                    if not thread.is_alive() or time.monotonic() > deadline:
                        raise AssertionError('server did not become healthy')
                    time.sleep(.2)
            try:
                opener.open(base + '/api/projects', timeout=3)
            except urllib.error.HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError('missing token was accepted')
            request = urllib.request.Request(base + '/api/projects', headers={'X-TMH-Token': 'synthetic-offline-token'})
            with opener.open(request, timeout=3) as response:
                records['projects_after_start_%d' % attempt] = json.load(response)
            with opener.open(base + '/next/?token=synthetic-offline-token', timeout=10) as response:
                page = response.read().decode('utf-8')
                assert response.status == 200 and '<div id="app"></div>' in page
            asset = re.search(r'assets/index-[^"]+\.js', page)
            assert asset, 'web bundle is missing its hashed entry asset'
            with opener.open(base + '/next/' + asset.group(0) + '?token=synthetic-offline-token', timeout=10) as response:
                assert response.status == 200
                assert 'immutable' in (response.headers.get('Cache-Control') or '')
            records['workbench_mcp_%d' % attempt] = asyncio.run(sdk_check(base))
            duplicate = call('--config', config, 'start', env=env, ok=False)
            assert 'lock timed out' in duplicate.stderr, duplicate.stderr
        finally:
            cancel.set()
            thread.join(15)
            if outcomes:
                (work / ('server-%d.log' % attempt)).write_bytes(outcomes[0].output_bytes)
        assert not thread.is_alive()
        assert outcomes[0].cleanup['complete'], outcomes[0]
        records['stop_%d' % attempt] = outcomes[0].cleanup
        for db in data.rglob('*.db'):
            with sqlite3.connect(db) as connection:
                assert connection.execute('pragma integrity_check').fetchall() == [('ok',)]
    assert config.read_bytes() == before
    assert (data / 'agents.json').read_bytes() == original
    # Existing but broken installation is refused without a silent fallback.
    broken = work / 'codex.cmd'
    broken.write_text('@exit /b 17\r\n')
    bad_config = work / 'broken.json'
    bad_config.write_text(json.dumps({'tools': {'codex': str(broken)}}))
    assert 'failed' in call('--config', bad_config, 'check', env=env, ok=False).stderr
    # Corruption is reported by check but never blocks start.
    asset = root / 'config.example.json'
    saved = asset.read_bytes()
    try:
        asset.write_bytes(saved + b' ')
        report = json.loads(call('check', env=env).stdout)
        assert 'config.example.json' in report['bundle_files_changed']
    finally:
        asset.write_bytes(saved)
    records['manifest_after_test'] = launch.inventory(root)['bundle_files_total']
    (work / 'receipt.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(ok=True, receipt=str(work / 'receipt.json')), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
