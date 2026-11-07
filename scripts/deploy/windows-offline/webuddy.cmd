@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUTF8=1"
"%~dp0runtime\python\python.exe" -B "%~dp0launcher.py" %*
exit /b %errorlevel%
