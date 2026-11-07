$ProgressPreference='SilentlyContinue'; $env:PYTHONUTF8='1'
Set-Location C:\tmh-runner\work\webuddy-mcp-21f4e73-20261107
@'
import subprocess,sys,json
cmd=[sys.executable,'-u','-c','import os; from tmh.platform.preview import _alive; print("before",flush=True); print("alive",_alive(os.getpid()),flush=True); print("after",flush=True)']
p=subprocess.run(cmd,creationflags=subprocess.DETACHED_PROCESS,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
print(json.dumps(dict(command=cmd,exit_code=p.returncode,stdout=p.stdout.decode(),stderr=p.stderr.decode())))
'@ | C:\tmh-runner\work\webuddy-windows-full-venv-20261107\Scripts\python.exe -
exit $LASTEXITCODE
