import hashlib,json,tarfile,shutil,tempfile
from pathlib import Path
archive=Path('/tmp/knowledge-delta.tar.gz')
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='d83e2afda7e3af15bf3a6f6820e83a56e60f157a7f2c78c036bd5c17b3992fb4'
dest=Path('/opt/webuddy/releases/e961515/app');dest.mkdir(parents=True,exist_ok=False)
with tempfile.TemporaryDirectory(prefix='webuddy-review-delta-') as tmp:
 with tarfile.open(archive) as t:t.extractall(tmp,filter='data')
 staging=Path(tmp);manifest=json.loads((staging/'MANIFEST.json').read_text())
 for name,digest in manifest.items():
  changed=staging/name;source=changed if changed.is_file() else Path('/opt/webuddy/app')/name
  assert hashlib.sha256(source.read_bytes()).hexdigest()==digest,name
  target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
 for name in ['MANIFEST.json','RELEASE.json']:shutil.copy2(staging/name,dest/name)
print('EXACT_MANIFEST_REBUILT',len(manifest))
