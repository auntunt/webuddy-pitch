$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
$p='C:\tmh-runner\work\webuddy-full-e282afab-proof-20261107'
$until=(Get-Date).AddMinutes(20)
while(!(Test-Path "$p\run.json")){if((Get-Date) -gt $until){throw 'primary still running'};Start-Sleep 10}
Set-Location 'C:\tmh-runner\work\webuddy-full-e282afab-20261107'
$env:HOME="$p\home";$env:USERPROFILE=$env:HOME;$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';$env:NO_PROXY='127.0.0.1,localhost,::1'
Remove-Item Env:WEBUDDY_TOKEN,Env:WEBUDDY_OPERATOR_TOKEN,Env:WEBUDDY_CREDENTIAL_FILE -ErrorAction SilentlyContinue
@'
import json,subprocess,sys,time,concurrent.futures,datetime
from pathlib import Path
proof=Path(sys.argv[1]); out=proof/'supplement';out.mkdir()
modules=[]
for p in proof.glob('shard*/summary.json'):
 for r in json.loads(p.read_text())['results']:
  if r['timed_out'] or not r['junit_exists']:modules.append(r['module'])
cases=[]
for module in modules:
 if '::' in module:raise RuntimeError('individual case did not finish; retain unresolved: '+module)
 c=subprocess.run([sys.executable,'-m','pytest',module,'--collect-only','-q','-p','no:cacheprovider'],capture_output=True,timeout=60)
 (out/(module.replace('/','__')+'-collect.log')).write_bytes(c.stdout+c.stderr)
 c.check_returncode()
 found=[s.strip() for s in c.stdout.decode().splitlines() if s.startswith(module+'::')]
 assert found;cases+=found

def run(case):
 stem=case.replace('/','__').replace('::','__');xml=out/(stem+'.xml');start=time.monotonic()
 cmd=[sys.executable,'-m','pytest',case,'-vv','-rs','--full-trace','-p','no:cacheprovider','--junitxml='+str(xml)]
 with (out/(stem+'.log')).open('wb') as f:
  p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.DETACHED_PROCESS);timeout=False
  try:code=p.wait(timeout=300)
  except subprocess.TimeoutExpired:
   timeout=True;subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=f,stderr=subprocess.STDOUT);code=p.wait()
 return dict(case=case,command=cmd,exit_code=code,timed_out=timeout,junit_exists=xml.exists(),seconds=round(time.monotonic()-start,3))
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,cases))
r=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),started=start,ended=datetime.datetime.now(datetime.timezone.utc).isoformat(),original_modules=modules,selected=cases,results=results)
(out/'run.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
sys.exit(int(any(x['exit_code'] or x['timed_out'] or not x['junit_exists'] for x in results)))
'@ | Out-File "$p\complete-timeouts.py" -Encoding utf8
& 'C:\tmh-runner\work\webuddy-windows-full-venv-20261107\Scripts\python.exe' "$p\complete-timeouts.py" $p
exit $LASTEXITCODE
