$ProgressPreference='SilentlyContinue'; $env:PYTHONUTF8='1'
@'
import subprocess,sys,json
from pathlib import Path
for label in ['webuddy-mcp-21f4e73-20261107','webuddy-alive-fixed-20261107']:
 root=Path('C:/tmh-runner/work')/label
 code="from pathlib import Path; import sys,json; from tmh.platform.supervised_process import run_supervised; p=Path('supervisor-diagnostic'); r=run_supervised([sys.executable,'-c','print(123)'],folder=p,owner={'token':'synthetic','run_id':1,'data_dir':str(p)},timeout=15); print(json.dumps({'returncode':r.returncode,'reason':r.reason,'cleanup':r.cleanup})); print((p/'supervisor-result.json').read_text() if (p/'supervisor-result.json').exists() else 'no final receipt')"
 p=subprocess.run([sys.executable,'-c',code],cwd=root,creationflags=subprocess.DETACHED_PROCESS,capture_output=True,timeout=30)
 print(json.dumps(dict(source=label,exit_code=p.returncode,stdout=p.stdout.decode(),stderr=p.stderr.decode())))
'@ | C:\tmh-runner\work\webuddy-windows-full-venv-20261107\Scripts\python.exe -
exit $LASTEXITCODE
