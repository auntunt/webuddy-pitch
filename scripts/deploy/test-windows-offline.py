"""Actual Windows smoke test for an extracted offline bundle; uses only synthetic state."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle', type=Path)
    p.add_argument('--expect-network-blocked', action='store_true')
    args = p.parse_args()
    root = args.bundle.resolve()
    launcher = root / 'launcher.py'
    spec = importlib.util.spec_from_file_location('launcher', launcher)
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    assert launch.verify(root) > 1000
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
    assert all(row['source'] == 'bundled' for row in records['bundled']['tools'].values())
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
    # Corruption is caught before any new state directory is created.
    asset = root / 'config.example.json'
    saved = asset.read_bytes()
    try:
        asset.write_bytes(saved + b' ')
        assert 'checksum mismatch' in call('check', env=env, ok=False).stderr
    finally:
        asset.write_bytes(saved)
    records['manifest_after_test'] = launch.verify(root)
    (work / 'receipt.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(ok=True, receipt=str(work / 'receipt.json')), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
