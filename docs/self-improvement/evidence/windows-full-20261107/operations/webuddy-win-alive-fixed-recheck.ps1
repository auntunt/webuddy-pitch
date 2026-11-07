$ProgressPreference='SilentlyContinue'; $env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH='C:\tmh-runner\work\webuddy-alive-fixed-20261107'
Set-Location $env:PYTHONPATH
@'
import subprocess,sys,json
with open('regression-source-bound.log','wb') as log:
 p=subprocess.run([sys.executable,'-m','pytest','tests/test_windows_execution.py','-vv','-rs','--junitxml=regression-source-bound.xml'],creationflags=subprocess.DETACHED_PROCESS,stdout=log,stderr=subprocess.STDOUT,timeout=120)
print(json.dumps(dict(regression_exit=p.returncode)))
sys.exit(p.returncode)
'@ | C:\tmh-runner\work\webuddy-windows-full-venv-20261107\Scripts\python.exe -
exit $LASTEXITCODE
