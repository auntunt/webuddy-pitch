from pathlib import Path
import datetime
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def snapshot():
    paths = [ROOT / 'pyproject.toml', *ROOT.glob('tmh/**/*.py'), *ROOT.glob('tests/**/*.py')]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
(OUT / 'test-fix-commit.txt').write_text(head + '\n')
(OUT / 'test-fix.patch').write_bytes(subprocess.check_output(['git', 'show', '--format=fuller', '--binary', head], cwd=ROOT))
before = snapshot()
save('source-before-final.json', before)
command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v']
env = dict(os.environ, NO_PROXY='127.0.0.1,localhost', no_proxy='127.0.0.1,localhost')
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
clock = time.monotonic()
with (OUT / 'full-platform-final.log').open('xb') as log:
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
elapsed = time.monotonic() - clock
after = snapshot()
save('source-after-final.json', after)
raw = (OUT / 'full-platform-final.log').read_text(errors='replace')
match = re.search(r'^Ran (\d+) tests in ([\d.]+)s$', raw, re.MULTILINE)
report = {
    'commit': head,
    'product_commit': 'd21e4f4da680b6649e06abd0517ca7200c714359',
    'started_utc': started,
    'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'command': command,
    'python': sys.version,
    'mcp_sdk': importlib.metadata.version('mcp'),
    'exit_code': result.returncode,
    'tests': int(match[1]) if match else None,
    'test_runtime_seconds': float(match[2]) if match else None,
    'wall_runtime_seconds': elapsed,
    'ok_line': bool(re.search(r'^OK(?: \([^\n]*\))?$', raw, re.MULTILINE)),
    'source_files': len(before),
    'source_unchanged': before == after,
    'source_differences': [name for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)],
    'resource_warning_lines': sum('ResourceWarning:' in line for line in raw.splitlines()),
    'log_sha256': hashlib.sha256((OUT / 'full-platform-final.log').read_bytes()).hexdigest(),
}
save('final-verification.json', report)
print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
sys.exit(result.returncode or (0 if before == after else 2))
