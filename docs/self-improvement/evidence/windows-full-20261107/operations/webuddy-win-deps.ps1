$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8='1'
python -m venv C:\tmh-runner\work\webuddy-windows-full-venv-20261107
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& C:\tmh-runner\work\webuddy-windows-full-venv-20261107\Scripts\python.exe -m pip install 'mcp>=1.30,<2' pytest cryptography
exit $LASTEXITCODE
