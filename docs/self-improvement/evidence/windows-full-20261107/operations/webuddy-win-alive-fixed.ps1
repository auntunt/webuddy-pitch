$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; $env:NO_PROXY='127.0.0.1,localhost,::1'
$dir='C:\tmh-runner\work\webuddy-alive-fixed-20261107'
if(Test-Path $dir){throw 'already exists'}
New-Item -ItemType Directory $dir | Out-Null
tar -xzf C:\tmh-runner\work\webuddy-mcp-21f4e73-v2.tar.gz -C $dir
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
$patch='C:\tmh-runner\work\webuddy-alive-patch.tar.gz'
if((Get-FileHash $patch -Algorithm SHA256).Hash.ToLower() -ne '42ea7c015fab98ad2b746f894fe9e9773b38168b0252a2211603a1d48a82ac05'){throw 'patch hash mismatch'}
tar -xzf $patch -C $dir
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
Set-Location $dir
@'
import subprocess,sys,json
cmd=[sys.executable,'-u','-c','import os; from tmh.platform.preview import _alive; print("before",flush=True); print("alive",_alive(os.getpid()),flush=True); print("after",flush=True)']
p=subprocess.run(cmd,creationflags=subprocess.DETACHED_PROCESS,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
print(json.dumps(dict(exit_code=p.returncode,stdout=p.stdout.decode(),stderr=p.stderr.decode())))
assert p.returncode==0 and 'alive True' in p.stdout.decode() and 'after' in p.stdout.decode()
with open('regression.log','wb') as log:
 p=subprocess.run([sys.executable,'-m','pytest','tests/test_windows_execution.py','-vv','-rs','--junitxml=regression.xml'],creationflags=subprocess.DETACHED_PROCESS,stdout=log,stderr=subprocess.STDOUT,timeout=120)
print(json.dumps(dict(regression_exit=p.returncode)))
sys.exit(p.returncode)
'@ | C:\tmh-runner\work\webuddy-windows-full-venv-20261107\Scripts\python.exe -
exit $LASTEXITCODE
