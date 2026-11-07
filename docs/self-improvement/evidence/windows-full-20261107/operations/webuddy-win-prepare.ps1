$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,FreePhysicalMemory
Get-CimInstance Win32_ComputerSystem | Select-Object NumberOfLogicalProcessors,TotalPhysicalMemory
$dir='C:\tmh-runner\work\webuddy-windows-full-21f4e73-20261107'
if (Test-Path $dir) { throw 'isolated directory already exists' }
New-Item -ItemType Directory -Path $dir | Out-Null
Set-Location $dir
git init
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git -c credential.helper= fetch --depth=1 https://github.com/auntunt/webuddy-pitch.git 21f4e73ef021fc12cb29ca0ee96e381a7ee8a27d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git checkout --detach FETCH_HEAD
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m venv C:\tmh-runner\work\webuddy-windows-full-venv-20261107
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& C:\tmh-runner\work\webuddy-windows-full-venv-20261107\Scripts\python.exe -m pip install '.[mcp]' pytest cryptography
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git rev-parse HEAD
& C:\tmh-runner\work\webuddy-windows-full-venv-20261107\Scripts\python.exe -m pip freeze
exit $LASTEXITCODE
