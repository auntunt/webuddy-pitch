"""Assert real browser effects from complete independently readable API snapshots."""
from pathlib import Path
import hashlib
import json
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def read(name):
    return json.loads((OUT/name).read_text())

before = read('preview-before-resume.json')
saved = read('preview-after-reconciled-save.json')
approved = read('preview-after-approval.json')
stale = read('preview-after-stale-approval.json')
assert approved == stale, 'Stale browser approval modified record or history'
by_id = lambda value: {r['id']: r for r in value['records']}
rows = [by_id(value) for value in [before, saved, approved]]
key = 'wbill-preview-1'
assert [value[key]['version'] for value in rows] == [1, 2, 3]
assert [len(value['history'][key]) for value in [before, saved, approved]] == [1, 2, 3]
assert rows[1][key]['stage'] == 'submitted' and rows[2][key]['stage'] == 'approved'
assert rows[1][key]['fields'] == rows[2][key]['fields']
fields = rows[2][key]['fields']
assert fields['总重'] == '10900' and fields['净重'] == '900'
assert fields['货名'] == '双人协作核对后的原料'
assert fields['备注'] == 'A 的完整草稿：保留货名修改与备注；重量需采用 B 已核对的新值。'
for untouched in ['wbill-preview-2', 'wbill-preview-3']:
    assert rows[0][untouched] == rows[1][untouched] == rows[2][untouched]
    assert before['history'][untouched] == saved['history'][untouched] == approved['history'][untouched]

original = read('bootv2-before.json')
current = read('bootv2-after.json')
assert all(original[k] == current[k] for k in ['commit', 'evidence_hash', 'human_accepted'])
data_dir = ROOT/'data/weighbill-pilot-20261019/preview-data'
marker = json.loads((data_dir/'webuddy-preview.json').read_text())
for image in marker['records']:
    raw = (data_dir/image['original_key']).read_bytes()
    assert len(raw) == image['bytes'] and hashlib.sha256(raw).hexdigest() == image['original_sha256']
with sqlite3.connect(f'file:{OUT}/preview-final-snapshot.db?mode=ro', uri=True) as db:
    assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
source = ROOT/'data/external-agents/weighbill-concurrency'
assert subprocess.check_output(['git','rev-parse','HEAD'], cwd=source).decode().strip() == approved['commit']
assert not subprocess.check_output(['git','status','--porcelain'], cwd=source).strip()
result = {'commit': approved['commit'], 'versions': [1, 2, 3], 'history_counts': [1, 2, 3],
          'approved_gross': '10900', 'approved_net': '900', 'full_goods_and_remarks_retained': True,
          'stale_approval_zero_state_and_history_change': True, 'two_other_records_unchanged': True,
          'original_image_bytes_unchanged': True, 'bootv2_acceptance_unchanged': True,
          'sqlite_backup_integrity': 'ok', 'business_source_unchanged': True}
(OUT/'business-checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(result, ensure_ascii=False, indent=2))
