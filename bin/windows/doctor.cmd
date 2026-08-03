@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass ^
    -File "%ROOT%\scripts\doctor.ps1" %*
exit /b %ERRORLEVEL%
