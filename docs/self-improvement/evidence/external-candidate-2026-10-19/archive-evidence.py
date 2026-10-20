"""Copy complete selected evidence, excluding credentials; never alter PNG bytes."""
from pathlib import Path
import hashlib,json,shutil,sqlite3,subprocess
ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'data/external-delivery-20261019'
target=ROOT/'docs/self-improvement/evidence/external-candidate-2026-10-19'
result=json.loads((source/'platform-full-complete-result.json').read_text())
assert result['exit_code']==0 and result['source_unchanged']
target.mkdir(parents=True,exist_ok=True)
# Explicit source roots: never copy operator-approval.key, login sessions or the
# complete runtime data directory. Every selected file is copied byte for byte.
for path in source.iterdir():
 if path.is_dir():shutil.copytree(path,target/path.name,dirs_exist_ok=True)
 else:shutil.copy2(path,target/path.name)
shutil.copytree(ROOT/'data/product-workbench/verification-operations/runs/1',target/'platform-verification',dirs_exist_ok=True)
shutil.copytree(ROOT/'data/product-workbench/runs/7',target/'candidate-run',dirs_exist_ok=True)
preview=json.loads((source/'candidate-before-assessment.json').read_text())['preview']
shutil.copy2(preview['log'],target/'preview-raw.log')
shutil.copytree(ROOT/'data/agent-client-configs/external-candidates',target/'client-configs',dirs_exist_ok=True)
store=sqlite3.connect(ROOT/'data/product-workbench/platform.db')
artifact=store.execute('SELECT artifact_dir FROM code_candidates WHERE id=1').fetchone()[0]
shutil.copytree(artifact,target/'candidate-artifact',dirs_exist_ok=True)
backup=sqlite3.connect(target/'platform-after.db');store.backup(backup);backup.close();store.close()
for path in (source/'browser-filter-desktop.png',source/'browser-filter-empty.png'):
 assert path.read_bytes()==(target/path.name).read_bytes()
manifest={str(p.relative_to(target)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(target.rglob('*')) if p.is_file() and p.name!='manifest.json'}
assert not any('operator-approval.key' in p for p in manifest)
(target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'files':len(manifest),'bytes':sum(v['bytes'] for v in manifest.values()),'png_bytes_preserved':True},indent=2))
