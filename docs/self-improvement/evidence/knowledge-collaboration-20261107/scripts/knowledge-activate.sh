#!/bin/bash
set -euo pipefail
exec 9>/opt/webuddy/.release.lock
flock -n 9
release=/opt/webuddy/releases/e961515/app
old=$(readlink /opt/webuddy/app)
python3 /tmp/webuddy-native-check.py "$release"
backup="/opt/webuddy/backups/pre-e961515-test-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$backup"
printf '%s\n' "$old" > "$backup/old-app.txt"
cp -p /etc/webuddy.env "$backup/"
systemctl cat webuddy.service > "$backup/service.txt"
rollback(){ systemctl stop webuddy.service; ln -s "$old" /opt/webuddy/app.rollback; mv -Tf /opt/webuddy/app.rollback /opt/webuddy/app; systemctl start webuddy.service; }
trap rollback ERR
systemctl stop webuddy.service
python3 /tmp/webuddy-native-check.py "$release"
tar -czf "$backup/state.tar.gz" -C / opt/webuddy/data opt/webuddy/repos home/ubuntu/.codex etc/webuddy.env etc/systemd/system/webuddy.service "${old#/}"
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
if [ ! -e /home/ubuntu/.local/bin/tmh ]; then
 install -d -o ubuntu -g ubuntu /home/ubuntu/.local/bin
 install -o ubuntu -g ubuntu -m 755 /tmp/tmh-43 /home/ubuntu/.local/bin/tmh
fi
ln -s "$release" /opt/webuddy/app.next-review
mv -Tf /opt/webuddy/app.next-review /opt/webuddy/app
systemctl start webuddy.service
for i in $(seq 1 15); do if curl -fsS -o /dev/null http://127.0.0.1:8790/login; then break; fi; sleep 1; done
curl -fsS -o /dev/null http://127.0.0.1:8790/login
systemctl is-active webuddy.service
trap - ERR
printf '%s\n' "$backup" > /opt/webuddy/releases/e961515/backup-path.txt
printf 'BACKUP=%s\n' "$backup"
