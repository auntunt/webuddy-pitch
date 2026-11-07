"""Run every test module in a separate process; retain failures and interruptions."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--shard', type=int, default=0)
    parser.add_argument('--shards', type=int, default=1)
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not 0 <= args.shard < args.shards or args.timeout <= 0:
        parser.error('invalid shard or timeout')
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    modules = sorted(root.joinpath('tests').rglob('test_*.py'))
    units = [p.relative_to(root).as_posix() for p in modules]
    # This integration module exceeds the module budget on Windows. Keep its
    # existing cases intact, but give each case an independent process/receipt.
    platform_module = 'tests/test_platform.py'
    collection = subprocess.run([sys.executable, '-m', 'pytest', platform_module,
                                 '--collect-only', '-q', '-p', 'no:cacheprovider'],
                                cwd=root, capture_output=True, timeout=60)
    (output / 'platform-collection.log').write_bytes(collection.stdout + collection.stderr)
    cases = [line.strip() for line in collection.stdout.decode('utf-8').splitlines()
             if line.startswith(platform_module + '::')]
    if collection.returncode or not cases:
        raise RuntimeError('platform test collection failed; see platform-collection.log')
    units[units.index(platform_module):units.index(platform_module) + 1] = cases
    selected = units[args.shard::args.shards]
    result = dict(commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                  python=sys.version, platform=sys.platform,
                  started=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  shard=args.shard, shards=args.shards,
                  discovered=units, results=[])
    for name in selected:
        stem = name.replace('/', '__').replace('::', '__').removesuffix('.py')
        command = [sys.executable, '-m', 'pytest', name, '-vv', '-rs', '--full-trace',
                   '-p', 'no:cacheprovider', '--junitxml=' + str(output / (stem + '.xml'))]
        started = time.monotonic()
        # A separate console prevents tests' Windows console events from
        # interrupting this controller and losing the remaining module receipts.
        with (output / (stem + '.log')).open('wb') as log:
            process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.DETACHED_PROCESS if os.name == 'nt' else 0)
            timed_out = False
            try:
                code = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=log, stderr=subprocess.STDOUT)
                else:
                    process.kill()
                process.wait()
                code = process.returncode
        row = dict(module=name, command=command, exit_code=code, timed_out=timed_out,
                   seconds=round(time.monotonic() - started, 3),
                   junit_exists=(output / (stem + '.xml')).is_file())
        result['results'].append(row)
        (output / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(row), flush=True)
    return int(any(r['exit_code'] != 0 or r['timed_out'] or not r['junit_exists'] for r in result['results']))


if __name__ == '__main__':
    sys.exit(main())
