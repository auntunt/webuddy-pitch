from pathlib import Path
import dataclasses
import datetime
import hashlib
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tmh.platform.process_control import run_process

OUT = Path(__file__).resolve().parent
CLONE = ROOT / 'data/external-agents/weighbill-concurrency'
env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'TMPDIR', 'TERM', 'CODEX_HOME')}
env.update(WB_TEST_STACK='', PYTEST_ADDOPTS='', PYTHONDONTWRITEBYTECODE='1')
cmd = ['/Users/auntlee/.nvm/versions/node/v24.16.0/bin/codex', 'exec', '--sandbox', 'workspace-write', '--json', '--color', 'never', '-C', str(CLONE), '-o', str(OUT/'last-message.txt'), '-']
start = datetime.datetime.now(datetime.timezone.utc).isoformat()
with (OUT/'events.jsonl').open('wb') as stream:
    def record(raw):
        stream.write(raw)
        stream.flush()
    result = run_process(cmd, cwd=str(CLONE), env=env, timeout=900, stdin=(OUT/'request.md').read_text(), on_bytes=record)
report = {k: v for k, v in dataclasses.asdict(result).items() if k not in ('output', 'output_bytes')}
report.update(command=cmd, started_at=start, finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), timeout_seconds=900,
              output_sha256=hashlib.sha256(result.output_bytes).hexdigest(), output_bytes=len(result.output_bytes))
(OUT/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
sys.exit(result.returncode)
