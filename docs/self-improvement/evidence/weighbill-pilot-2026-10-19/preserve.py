from pathlib import Path
import hashlib
import json
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = Path('/Users/auntlee/workspace/weighbill-system')
def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()
def git(*args):
    return subprocess.check_output(['git', *args], cwd=SOURCE).decode().strip()
def snapshot():
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=SOURCE).decode().split('\0')
    tracked = {n: digest(SOURCE/n) for n in names if n and (SOURCE/n).is_file()}
    local = {}
    for p in [SOURCE/'config.json', SOURCE/'.DS_Store', SOURCE/'docs/开发任务清单.xlsx', *(SOURCE/'data').rglob('*')]:
        if p.is_file():
            local[str(p.relative_to(SOURCE))] = {'bytes':p.stat().st_size,'sha256':digest(p)}
    db = sqlite3.connect(f'file:{ROOT}/data/product-workbench/platform.db?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    tables = ['projects','tickets','events','runs','code_candidates','candidate_decisions']
    rows = {}
    for table in tables:
        exists = db.execute('select 1 from sqlite_master where type=\'table\' and name=?',(table,)).fetchone()
        if not exists:
            continue
        records = [dict(row) for row in db.execute('select * from '+table)]
        rows[table] = {str(r['id']):hashlib.sha256(json.dumps(r, sort_keys=True, ensure_ascii=False).encode()).hexdigest() for r in records}
    db.close()
    return {'head':git('rev-parse','HEAD'), 'status':git('status','--short','--untracked-files=all'), 'tracked':tracked, 'local':local, 'platform_existing_rows':rows}

phase = sys.argv[1]
value = snapshot()
(OUT/f'preservation-{phase}.json').write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
if phase == 'after':
    before = json.loads((OUT/'preservation-before.json').read_text())
    report = {k: value[k] == before[k] for k in ('head','status','tracked','local')}
    report['platform_existing_rows'] = {table:all(value['platform_existing_rows'][table].get(key)==h for key,h in rows.items()) for table,rows in before['platform_existing_rows'].items()}
    (OUT/'preservation-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report))
else:
    print(json.dumps({'tracked_files':len(value['tracked']), 'local_files':len(value['local']), 'platform_rows':{t:len(r) for t,r in value['platform_existing_rows'].items()}}))
