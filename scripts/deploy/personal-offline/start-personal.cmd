@echo off
setlocal
set "WEBUDDY_PERSONAL_ROOT=%~dp0"
if exist "%~dp0program\Webuddy\runtime\python\python.exe" goto launch
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference='Stop'; $r=$env:WEBUDDY_PERSONAL_ROOT; $sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; & icacls $r '/inheritance:r' '/grant:r' ('*'+$sid+':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' '/T' '/Q' | Out-Null; if($LASTEXITCODE -ne 0){throw 'Personal folder permissions failed'}; $m=Get-Content -Raw -LiteralPath (Join-Path $r 'PERSONAL.json') | ConvertFrom-Json; $z=Join-Path $r $m.runtime_archive; if((Get-FileHash -Algorithm SHA256 -LiteralPath $z).Hash.ToLowerInvariant() -ne $m.runtime_sha256){throw 'Runtime ZIP integrity check failed'}; if(Test-Path -LiteralPath (Join-Path $r 'program')){throw 'Incomplete program directory exists; preserve it and extract into a new directory'}; Expand-Archive -LiteralPath $z -DestinationPath (Join-Path $r 'program')"
if errorlevel 1 exit /b %errorlevel%
:launch
"%~dp0program\Webuddy\runtime\python\python.exe" -B "%~dp0personal-launch.py" %*
exit /b %errorlevel%
