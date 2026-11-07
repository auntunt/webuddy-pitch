$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; $env:NO_PROXY='127.0.0.1,localhost,::1'
$archive='C:\tmh-runner\work\webuddy-win-source-21f4e73.tar'
$until=(Get-Date).AddMinutes(35)
while (!(Test-Path $archive) -or (Get-Item $archive).Length -ne 39209984) {
 if ((Get-Date) -gt $until) { throw 'full source transfer incomplete' }; Start-Sleep 10
}
$actual=(Get-FileHash $archive -Algorithm SHA256).Hash.ToLower()
if ($actual -ne 'f01c90d112a5bf12953a464a6730c6a09ddc5c61c27f6cd8a283dcff849fa282') { throw 'source archive hash mismatch' }
$dir='C:\tmh-runner\work\webuddy-full-a9ce6f20-20261107'
if (Test-Path $dir) { throw 'full suite directory already exists' }
New-Item -ItemType Directory $dir | Out-Null
tar -xf $archive -C $dir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Set-Location $dir
git fetch C:/tmh-runner/work/webuddy-win-a9-delta.bundle HEAD
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git checkout --detach FETCH_HEAD
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$commit=(git rev-parse HEAD)
if ($commit -ne 'a9ce6f20f3ebb8d29440d3d884110db62973d5c6') { throw 'commit mismatch' }
Write-Output "source_archive_sha256=$actual commit=$commit"
git status --short
$proof='C:\tmh-runner\work\webuddy-full-a9ce6f20-proof-20261107'
New-Item -ItemType Directory $proof | Out-Null
New-Item -ItemType Directory "$proof\home" | Out-Null
$env:HOME="$proof\home"; $env:USERPROFILE=$env:HOME
Remove-Item Env:WEBUDDY_TOKEN,Env:WEBUDDY_OPERATOR_TOKEN,Env:WEBUDDY_CREDENTIAL_FILE -ErrorAction SilentlyContinue
$python='C:\tmh-runner\work\webuddy-windows-full-venv-20261107\Scripts\python.exe'
& $python -m pip install . --no-deps
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m pip freeze | Out-File "$proof\dependencies.txt" -Encoding utf8
@'
import datetime,json,subprocess,sys
from pathlib import Path
proof=Path(sys.argv[1]); jobs=[]
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
for i in range(8):
    log=(proof/('shard%d-driver.log'%i)).open('wb')
    cmd=[sys.executable,'scripts/windows-suite-audit.py','--shard',str(i),'--shards','8','--output',str(proof/('shard%d'%i))]
    p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.DETACHED_PROCESS)
    jobs.append((i,p,log,cmd))
results=[]
for i,p,log,cmd in jobs:
    code=p.wait();log.close();results.append(dict(shard=i,exit_code=code,command=cmd))
result=dict(started=start,ended=datetime.datetime.now(datetime.timezone.utc).isoformat(),commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),results=results)
(proof/'run.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
sys.exit(int(any(x['exit_code'] for x in results)))
'@ | Out-File "$proof\launch.py" -Encoding utf8
& $python "$proof\launch.py" $proof
$code=$LASTEXITCODE
Write-Output "full_suite_exit=$code"
git status --short
exit $code
