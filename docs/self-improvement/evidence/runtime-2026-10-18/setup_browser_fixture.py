"""Explicit synthetic process recovery fixture; no model or customer acceptance."""
import json, subprocess, sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(BASE))
from tmh.platform.store import Store
root=BASE/'data/runtime-verification'
if root.exists(): raise SystemExit('Refusing to replace existing fixture')
root.mkdir(); repo=root/'source'; repo.mkdir()
(repo/'app.py').write_text('VALUE = 0\n')
(repo/'.gitignore').write_text('__pycache__/\n')
for args in [('init','-q','-b','main'),('add','.'),('-c','user.name=Fixture','-c','user.email=fixture@localhost','commit','-qm','SYNTHETIC recovery baseline')]:
 subprocess.run(['git','-C',str(repo),*args],check=True)
script=root/'checker.py'
script.write_text('''import sys,time,os,signal,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
mode=sys.argv[1]
print("SYNTHETIC local checker, not a model or customer approval",flush=True)
if mode != 'fix':
 print('No model action'); sys.exit(0)
p=Path('app.py'); before=p.read_text(); print('Before: '+before,flush=True)
if 'VALUE = 0' in before:
 p.write_text('VALUE = 1\\n')
 Path('retained-note.txt').write_text('SYNTHETIC partially completed work, retain on retry\\n')
 print('Partial edit retained; starting an owned child that ignores TERM',flush=True)
 child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])
 (root/'child.pid').write_text(str(child.pid))
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 while True: time.sleep(1)
assert 'VALUE = 1' in before and Path('retained-note.txt').exists(), 'Recovery lost code'
p.write_text('VALUE = 2\\n')
print('Recovery read VALUE=1 and retained-note.txt, then completed VALUE=2',flush=True)
''')
(root/'agents.json').write_text(json.dumps({'claude':{'enabled':False},'codex':{'enabled':False},'fixture':{'title':'SYNTHETIC 进程恢复检查器','cmd':[sys.executable,'-u',str(script),'{mode}'],'timeout':2}}))
(root/'autoflow.json').write_text(json.dumps({'on':False,'check':'none','resume':False,'merge':'off','preview':'off','plan':'off','handwork':'off'}))
s=Store(root/'platform.db'); p=s.add_project('RUNTIME','SYNTHETIC 运行恢复验收',str(repo))
t=s.create_ticket(p['id'],'SYNTHETIC：超时后保留已有改动并继续','Codex 技术验收',auto=False)
s.update_ticket(t['id'],'Codex 技术验收',body='隔离技术夹具。先将 VALUE=0 改成1后超时，保留代码及未跟踪文件；用户点击重新运行时必须从1继续改为2。不是模型交付或客户签收。')
(root/'fixture.json').write_text(json.dumps({'project':'RUNTIME','ticket':t['key'],'url':'http://127.0.0.1:8797/#/t/'+t['key']},ensure_ascii=False,indent=2))
s.db.close(); print((root/'fixture.json').read_text())
