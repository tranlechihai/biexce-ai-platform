@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\biexce-cli") do set "BIEXCE_CLI_ROOT=%%~fI"

where /q python.exe
if errorlevel 1 (
    echo ERROR: Python 3 was not found in PATH. 1>&2
    exit /b 1
)

python.exe "%BIEXCE_CLI_ROOT%\scripts\biexce.py" %*
exit /b %ERRORLEVEL%
