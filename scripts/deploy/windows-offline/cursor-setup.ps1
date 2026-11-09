$ErrorActionPreference = 'Stop'
# Runs as the installing user. Existing Cursor login and settings are preserved.
$locations = @(
  "$env:LOCALAPPDATA\cursor-agent\agent.cmd",
  "$env:LOCALAPPDATA\Programs\cursor-agent\agent.cmd"
)
if ((Get-Command agent -ErrorAction SilentlyContinue) -or ($locations | Where-Object { Test-Path -LiteralPath $_ })) { exit 0 }
$download = Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetRandomFileName() + '.ps1')
try {
  Invoke-WebRequest -Uri 'https://cursor.com/install?win32=true' -OutFile $download -UseBasicParsing
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $download
  if ($LASTEXITCODE -ne 0) { throw 'Cursor CLI installer failed. Check network access to cursor.com.' }
} finally { Remove-Item -LiteralPath $download -ErrorAction SilentlyContinue }
