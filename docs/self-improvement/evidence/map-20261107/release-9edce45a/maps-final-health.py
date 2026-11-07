import json,hashlib,sqlite3,subprocess,urllib.request,urllib.error
from pathlib import Path
app=Path('/opt/webuddy/app');r=json.loads((app/'RELEASE.json').read_text());assert r['commit']=='9edce45a5364d7f20a373929815bbbfec40a3c7f'
for f,h in json.loads((app/'MANIFEST.json').read_text()).items():assert hashlib.sha256((app/f).read_bytes()).hexdigest()==h
for p in Path('/opt/webuddy/data').rglob('*.db'):
 c=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);assert c.execute('pragma integrity_check').fetchall()==[('ok',)];c.close()
print('RELEASE_MANIFEST_DATABASE_OK')
print(subprocess.check_output(['systemctl','show','webuddy.service','-p','ActiveState','-p','SubState','-p','MainPID','-p','NRestarts','-p','ActiveEnterTimestamp'],text=True))
for path,expected in [('/login',200),('/t/default/api/projects',401)]:
 try:code=urllib.request.urlopen('http://127.0.0.1:8790'+path).status
 except urllib.error.HTTPError as e:code=e.code
 assert code==expected,(path,code)
 print(path,code)

pid=int(subprocess.check_output(['systemctl','show','webuddy.service','--value','-p','MainPID'],text=True))
assert Path('/proc/%s/cwd'%pid).resolve()==app.resolve()
print('RUNNING_CWD_OK',pid)
for origin in ['http://127.0.0.1:8790','https://webuddy.bbstack.date']:
 for path,expected in [('/login',200),('/t/default/api/projects',401)]:
  try:code=urllib.request.urlopen(origin+path,timeout=20).status
  except urllib.error.HTTPError as e:code=e.code
  assert code==expected,(origin,path,code)
  print(origin,path,code)
print('HEALTH_AT',__import__('datetime').datetime.now().astimezone().isoformat())

state = dict(line.split('=',1) for line in subprocess.check_output(['systemctl','show','webuddy.service','-p','ActiveState','-p','SubState','-p','NRestarts'],text=True).splitlines())
assert state==dict(ActiveState='active',SubState='running',NRestarts='0'),state
print('SERVICE_ACTIVE_RUNNING_ZERO_RESTARTS')
