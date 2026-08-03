@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"

where /q python.exe
if errorlevel 1 (
    echo ERROR: Python 3 was not found in PATH. 1>&2
    exit /b 1
)

python.exe "%ROOT%\scripts\biexce.py" %*
exit /b %ERRORLEVEL%
