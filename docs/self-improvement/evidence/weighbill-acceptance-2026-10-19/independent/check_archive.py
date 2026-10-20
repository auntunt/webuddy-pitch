"""Read-only checks of the saved acceptance database and browser artifacts."""
from pathlib import Path
import hashlib
import json
import sqlite3

OUT=Path(__file__).resolve().parent
HERE=OUT.parent
path=HERE/'preview-final-snapshot.db'
db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row
try:
    db.execute('PRAGMA query_only=ON')
    integrity=[r[0] for r in db.execute('PRAGMA integrity_check')]
    rows={name:[dict(r) for r in db.execute(sql)] for name,sql in {
        'records':'SELECT * FROM records ORDER BY id',
        'history':'SELECT * FROM history ORDER BY seq'}.items()}
finally:db.close()
live=json.loads((OUT/'live-SQLite-rows.json').read_text())
before=json.loads((HERE/'bootv2-before.json').read_text())
after=json.loads((HERE/'bootv2-after.json').read_text())
result={'backup_integrity':integrity,'backup_rows_equal_independent_live_rows':rows==live,
        'bootv2_recorded_commit_evidence_human_state_equal':all(before[k]==after[k] for k in ['commit','evidence_hash','human_accepted']),
        'artifact_hashes':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [path,HERE/'browser-approved.jpg',HERE/'browser-original.jpg',HERE/'business-checks.json',HERE/'business-checks.log',HERE/'verify-resumed-behavior.py']}}
(OUT/'archive-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(OUT/'saved-database-rows.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
assert integrity==['ok']
assert result['backup_rows_equal_independent_live_rows']
assert result['bootv2_recorded_commit_evidence_human_state_equal']
