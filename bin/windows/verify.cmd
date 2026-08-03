@echo off
setlocal EnableExtensions

title Biexce OpenCode Agent Verifier
for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"
set "VERIFY_SCRIPT=%ROOT%\scripts\verify.ps1"
set "TARGET_PATH=%USERPROFILE%\.config\opencode"

echo.
echo Biexce OpenCode Agent Harness
echo Static verification is required. Runtime verification is optional.
echo.

if not exist "%VERIFY_SCRIPT%" (
    echo ERROR: scripts\verify.ps1 was not found.
    echo Clone or extract the complete BIEXCE distribution before verifying.
    goto :failure
)

where /q powershell.exe
if errorlevel 1 (
    echo ERROR: Windows PowerShell was not found.
    goto :failure
)

echo Target: "%TARGET_PATH%"
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass ^
    -File "%VERIFY_SCRIPT%" -TargetPath "%TARGET_PATH%"

set "VERIFY_EXIT=%ERRORLEVEL%"
if not "%VERIFY_EXIT%"=="0" goto :failure

echo.
echo VERIFY PASS
goto :finish

:failure
if not defined VERIFY_EXIT set "VERIFY_EXIT=1"
echo.
echo VERIFY FAILED

:finish
echo.
echo Press any key to close.
pause >nul
exit /b %VERIFY_EXIT%
