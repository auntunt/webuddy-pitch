from pathlib import Path
import hashlib
import json
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'docs/self-improvement/evidence/preview-health-2026-10-19'
manifest = json.loads((DEST / 'manifest.json').read_text())
for name, metadata in manifest.items():
    value = (DEST / name).read_bytes()
    assert len(value) == metadata['bytes'], name
    assert hashlib.sha256(value).hexdigest() == metadata['sha256'], name
assert not (DEST / 'fixture/operator-approval.key').exists()
assert not (DEST / 'fixture/previews/secret').exists()
databases = {}
for path in sorted(DEST.rglob('*.db')):
    with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        check = [row[0] for row in db.execute('PRAGMA integrity_check')]
        assert check == ['ok'], (path, check)
        databases[str(path.relative_to(DEST))] = check
    db.close()
bundle = subprocess.run(['git', 'bundle', 'verify', str(DEST / 'fixture-candidate.bundle')], cwd=ROOT,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
assert bundle.returncode == 0, bundle.stdout
report = {
    'manifest_entries_verified': len(manifest),
    'original_bytes_verified': True,
    'private_credential_files_excluded': True,
    'sqlite_integrity': databases,
    'bundle_exit_code': bundle.returncode,
    'bundle_verification': bundle.stdout,
}
(DEST / 'readback-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
