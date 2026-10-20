"""Lossless local evidence snapshot. Does not alter either application database."""
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
DEST = ROOT/'docs/self-improvement/evidence/weighbill-pilot-2026-10-19'
CLONE = ROOT/'data/external-agents/weighbill-concurrency'
BASE = '60d6422ee898959557fc529a8e0335524b5ee2c0'
HEAD = 'ab9601e305bf9efdf908554174c56ca101194405'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=CLONE).decode().strip() == HEAD
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=CLONE).strip()
shutil.copytree(SOURCE, DEST, dirs_exist_ok=True, symlinks=True)

# SQLite online backup includes committed WAL changes in one consistent read.
source_db = sqlite3.connect(f'file:{SOURCE}/preview-data/ledger.db?mode=ro', uri=True)
with sqlite3.connect(DEST/'preview-consistent-snapshot.db') as target_db:
    source_db.backup(target_db)
    assert target_db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
source_db.close()

for oid in (2, 3, 4):
    shutil.copytree(ROOT/f'data/product-workbench/verification-operations/runs/{oid}', DEST/f'platform-verification/{oid}', dirs_exist_ok=True)
for filename in ('WBILL-65558a548e441391.json', 'WBILL-db7fd8e046d4dd7a.json'):
    shutil.copy2(ROOT/'data/product-workbench/verification-operations/checks'/filename, DEST/filename)
for log in (ROOT/'data/product-workbench/previews/logs/WBILL-1').glob('*.log'):
    (DEST/'preview-logs').mkdir(exist_ok=True)
    shutil.copy2(log, DEST/'preview-logs'/log.name)

subprocess.run(['git', 'bundle', 'create', str(DEST/'candidate.bundle'), 'HEAD', '^'+BASE], cwd=CLONE, check=True)
check = subprocess.run(['git', 'bundle', 'verify', str(DEST/'candidate.bundle')], cwd=CLONE, capture_output=True, check=True)
(DEST/'bundle-verify.log').write_bytes(check.stdout+check.stderr)
subprocess.run(['git', 'archive', '--format=tar', '--output='+str(DEST/'candidate-source.tar'), HEAD], cwd=CLONE, check=True)
(DEST/'candidate.diff').write_bytes(subprocess.check_output(['git', 'diff', '--binary', '--full-index', BASE, HEAD], cwd=CLONE))
(DEST/'candidate-history.txt').write_bytes(subprocess.check_output(['git','log','--format=fuller',BASE+'..'+HEAD], cwd=CLONE))
meta = {'saved_at': datetime.now(timezone.utc).isoformat(), 'platform_head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'business_base': BASE, 'business_head': HEAD, 'bundle_prerequisite': BASE,
        'source': str(SOURCE), 'image_treatment': 'Original screenshot/photo bytes copied; no resizing or re-encoding.',
        'database': 'preview-consistent-snapshot.db is the valid online backup; preview-data/ also retains original raw SQLite/WAL/SHM files as captured.',
        'script_location': 'Scripts originally ran under data/weighbill-pilot-20261019 and some resolve that directory; archived scripts are provenance, not directly runnable from this archive.'}
(DEST/'archive-metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'archive':str(DEST),'files':sum(p.is_file() for p in DEST.rglob('*'))},ensure_ascii=False))
