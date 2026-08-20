"""Launchers that keep Plan/Build isolated from the legacy agent runtime."""

from __future__ import annotations

from pathlib import Path


POSIX = """#!/bin/sh
set -eu
config_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
export OPENCODE_CONFIG_DIR="$config_dir"
export XDG_CONFIG_HOME="$config_dir/.xdg-config"
export OPENCODE_DISABLE_PROJECT_CONFIG=1
export OPENCODE_DISABLE_EXTERNAL_SKILLS=1
export OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1
export OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true
unset OPENCODE_CONFIG BIEXCE_SLIM_CONFIG_DIR
mkdir -p "$XDG_CONFIG_HOME"
case "${OPENCODE_BINARY##*/}" in
    opencode|opencode.exe|opencode.cmd) exec "$OPENCODE_BINARY" "$@" ;;
esac
exec opencode "$@"
"""


WINDOWS = r"""@echo off
setlocal
for %%I in ("%~dp0..") do set "OPENCODE_CONFIG_DIR=%%~fI"
set "XDG_CONFIG_HOME=%OPENCODE_CONFIG_DIR%\.xdg-config"
set "OPENCODE_DISABLE_PROJECT_CONFIG=1"
set "OPENCODE_DISABLE_EXTERNAL_SKILLS=1"
set "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1"
set "OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true"
set "OPENCODE_CONFIG="
set "BIEXCE_SLIM_CONFIG_DIR="
if not exist "%XDG_CONFIG_HOME%" mkdir "%XDG_CONFIG_HOME%"
set "OPENCODE_BINARY_NAME="
if defined OPENCODE_BINARY (
  for %%I in ("%OPENCODE_BINARY%") do set "OPENCODE_BINARY_NAME=%%~nxI"
)
if /I "%OPENCODE_BINARY_NAME%"=="opencode.exe" goto configured
if /I "%OPENCODE_BINARY_NAME%"=="opencode.cmd" goto configured
if /I "%OPENCODE_BINARY_NAME%"=="opencode" goto configured
call opencode %*
exit /b %ERRORLEVEL%
:configured
call "%OPENCODE_BINARY%" %*
exit /b %ERRORLEVEL%
"""


def write_launchers(destination: Path) -> None:
    target = destination / "bin"
    target.mkdir(parents=True)
    posix = target / "biexce-opencode"
    posix.write_text(POSIX, encoding="utf-8", newline="\n")
    posix.chmod(0o755)
    (target / "biexce-opencode.cmd").write_text(
        WINDOWS,
        encoding="utf-8",
        newline="\r\n",
    )
