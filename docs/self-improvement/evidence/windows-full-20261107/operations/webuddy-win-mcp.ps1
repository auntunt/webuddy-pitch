$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; $env:NO_PROXY='127.0.0.1,localhost,::1'
$archive='C:\tmh-runner\work\webuddy-mcp-21f4e73-v2.tar.gz'
$expected='95ecb54d51de203375fcd29d2492d81d1c3ad55a749abd26582138a29d91dea3'
$until=(Get-Date).AddMinutes(8)
do {
  if ((Test-Path $archive) -and ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() -eq $expected)) { break }
  if ((Get-Date) -gt $until) { throw 'MCP source transfer incomplete' }
  Start-Sleep -Seconds 5
} while ($true)
$dir='C:\tmh-runner\work\webuddy-mcp-21f4e73-20261107'
if (Test-Path $dir) { throw 'MCP isolated directory already exists' }
New-Item -ItemType Directory $dir | Out-Null
tar -xzf $archive -C $dir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Set-Location $dir
New-Item -ItemType Directory "$dir\isolated-home" | Out-Null
$env:HOME="$dir\isolated-home"; $env:USERPROFILE=$env:HOME
Remove-Item Env:WEBUDDY_TOKEN,Env:WEBUDDY_OPERATOR_TOKEN,Env:WEBUDDY_CREDENTIAL_FILE -ErrorAction SilentlyContinue
Write-Output "source_archive_sha256=$expected source_commit=21f4e73ef021fc12cb29ca0ee96e381a7ee8a27d scope=tmh+official_mcp_test"
& C:\tmh-runner\work\webuddy-windows-full-venv-20261107\Scripts\python.exe -m pytest tests/test_workbench_mcp.py -vv -rs --junitxml=mcp.xml *> mcp.log
$code=$LASTEXITCODE
Get-Content mcp.log -Tail 18
Write-Output "pytest_exit=$code"
exit $code
