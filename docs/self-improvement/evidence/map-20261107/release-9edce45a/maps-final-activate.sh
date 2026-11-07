#!/bin/bash
set -euo pipefail
exec 9>/opt/webuddy/.release.lock
flock -n 9
release=/opt/webuddy/releases/maps-9edce45a/app
fallback=/opt/webuddy/releases/package-3261e871/app
switched=0
old=$(readlink /opt/webuddy/app)
[ "$old" = "$fallback" ]
python3 - <<'GATE'
import json
from pathlib import Path
r=json.loads(Path('/tmp/maps-final-ci-gates.json').read_text())
for role,sha in [('target','9edce45a5364d7f20a373929815bbbfec40a3c7f'),('fallback','3261e871d33bc243493abfd1dc34f89f5b2a43b3')]:
 assert r[role]['headSha']==sha
 jobs={j['name']:j['conclusion'] for j in r[role]['jobs']}
 assert len(r['required'])==12 and all(jobs.get(n)=='success' for n in r['required'])
assert r['tested_tree_proof']['identical_full_tree'] and r['tested_tree_proof']['head']==r['target']['headSha']
assert r['tested_tree_proof']['head_tree']==r['tested_tree_proof']['merge_tree']
print('EXACT_CI_GATE_RECEIPTS_OK')
GATE
python3 /tmp/reform-native-check-847.py "$release"
python3 /tmp/reform-native-check-847.py "$fallback"
backup="/opt/webuddy/backups/pre-maps-9edce45a-test-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$backup"
printf '%s\n' "$old" > "$backup/old-app.txt"
cp -p /etc/webuddy.env "$backup/"
systemctl cat webuddy.service > "$backup/service.txt"
rollback(){ systemctl stop webuddy.service; recovery="$old"; if [ "$switched" = 1 ]; then recovery="$fallback"; fi; ln -s "$recovery" /opt/webuddy/app.rollback; mv -Tf /opt/webuddy/app.rollback /opt/webuddy/app; systemctl start webuddy.service; }
trap rollback ERR
systemctl stop webuddy.service
python3 /tmp/reform-native-check-847.py "$release"
tar -czf "$backup/state.tar.gz" -C / opt/webuddy/data opt/webuddy/repos home/ubuntu/.codex etc/webuddy.env etc/systemd/system/webuddy.service "${old#/}" "${fallback#/}"
chmod 600 "$backup/state.tar.gz"
tar -tzf "$backup/state.tar.gz" > "$backup/archive-files.txt"
python3 - "$backup/state.tar.gz" <<'CHECK'
import sys,tarfile,hashlib
from pathlib import Path
with tarfile.open(sys.argv[1]) as archive:
 count=0
 for item in archive:
  if item.isfile():
   original=Path('/')/item.name
   saved=archive.extractfile(item)
   assert hashlib.file_digest(saved,'sha256').digest()==hashlib.file_digest(original.open('rb'),'sha256').digest(),item.name
   count+=1
print('BACKUP_BYTES_VERIFIED',count)
CHECK
ln -s "$release" /opt/webuddy/app.next-review
mv -Tf /opt/webuddy/app.next-review /opt/webuddy/app
switched=1
systemctl start webuddy.service
for i in $(seq 1 15); do if curl -fsS -o /dev/null http://127.0.0.1:8790/login; then break; fi; sleep 1; done
curl -fsS -o /dev/null http://127.0.0.1:8790/login
systemctl is-active webuddy.service
trap - ERR
printf '%s\n' "$backup" > /opt/webuddy/releases/maps-9edce45a/backup-path.txt
printf 'BACKUP=%s\n' "$backup"
