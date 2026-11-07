"""Read/write compatibility in fresh SQLite backups, never in live state."""
import json,os,sqlite3,subprocess,sys,tempfile
from pathlib import Path
current,fallback=sys.argv[1:3]
CHILD=r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2]);action=sys.argv[3]
from tmh.platform.store import Store
from tmh.platform import reform
st=Store(root/'platform.db');reform.initialize(root,st)
if action=='create':
 p=st.add_project('RFCOMPAT','Synthetic compatibility fixture',str(root))
 atlas={'built':'fixed','domains':[{'id':'one','title':'One','tables':0}]}
 plan=reform.create(root,p['key'],atlas,dict(title='Compatibility',goal='完整契约'*4000,keep='保留历史',scope_mode='selected',domains=['one'],request_id='compat-create'),'fixture')
 print(json.dumps({'id':plan['id'],'uid':plan['uid'],'goal':plan['goal'],'revision':plan['revision']}))
else:
 ident=json.loads(sys.argv[4]);p=reform.plan(root,'RFCOMPAT',ident['id'],store=st)
 assert all(p[k]==ident[k] for k in ('id','uid','goal'))
 if action=='archive':reform.remove(root,'RFCOMPAT',p['id'])
 else:assert p['archived']
 print(json.dumps({'id':p['id'],'uid':p['uid'],'state':'archived' if p.get('archived') else 'readable'}))
st.db.close()
'''
with tempfile.TemporaryDirectory(prefix='reform-program-compatibility-') as tmp:
 root=Path(tmp)
 src=sqlite3.connect('file:/opt/webuddy/data/platform.db?mode=ro',uri=True)
 dest=sqlite3.connect(root/'platform.db');src.backup(dest);src.close();dest.close()
 legacy=Path('/opt/webuddy/data/reforms')
 if legacy.exists():
  (root/'reforms').mkdir()
  for f in legacy.glob('*.json'):(root/'reforms'/f.name).write_bytes(f.read_bytes())
 def run(program,action,identity=None):
  command=[sys.executable,'-B','-c',CHILD,program,str(root),action]
  if identity:command.append(json.dumps(identity))
  r=subprocess.run(command,capture_output=True,text=True,timeout=20)
  assert r.returncode==0,r.stderr
  return json.loads(r.stdout)
 identity=run(current,'create')
 old=run(fallback,'archive',identity)
 new=run(current,'verify',identity)
 assert old['uid']==new['uid']==identity['uid']
 c=sqlite3.connect(root/'platform.db');assert c.execute('PRAGMA integrity_check').fetchall()==[('ok',)];c.close()
 print(json.dumps({'mode':'fresh_live_database_backup_only','current':Path(current).parent.name,'fallback':Path(fallback).parent.name,'new_write_read_by_fallback':True,'fallback_archive_read_by_current':True,'full_goal_characters':len(identity['goal']),'stable_identity':True,'integrity':'ok'}))
