@echo off
setlocal EnableExtensions

title Biexce OpenCode Agent Installer
for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"
set "INSTALL_SCRIPT=%ROOT%\scripts\install.ps1"
set "VERIFY_SCRIPT=%ROOT%\scripts\verify.ps1"
set "TARGET_PATH=%USERPROFILE%\.config\opencode"

echo.
echo Biexce OpenCode Agent Harness
echo User-global installation - administrator rights are not required.
echo.

if not exist "%INSTALL_SCRIPT%" (
    echo ERROR: scripts\install.ps1 was not found.
    echo Clone or extract the complete BIEXCE distribution before installing.
    goto :failure
)
if not exist "%VERIFY_SCRIPT%" (
    echo ERROR: scripts\verify.ps1 was not found.
    echo Clone or extract the complete BIEXCE distribution before installing.
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
    -File "%INSTALL_SCRIPT%" -TargetPath "%TARGET_PATH%" -ActivateCommand

set "INSTALL_EXIT=%ERRORLEVEL%"
if not "%INSTALL_EXIT%"=="0" goto :failure

echo.
echo INSTALL PASS
echo Open a new terminal, then run: biexce auto on
goto :finish

:failure
if not defined INSTALL_EXIT set "INSTALL_EXIT=1"
echo.
echo INSTALL FAILED

:finish
echo.
echo Press any key to close.
pause >nul
exit /b %INSTALL_EXIT%
