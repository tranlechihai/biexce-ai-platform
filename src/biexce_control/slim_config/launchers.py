"""Generate launchers that isolate Slim from legacy OpenCode config."""

from __future__ import annotations

from pathlib import Path


POSIX_LAUNCHER = """#!/bin/sh
set -eu
config_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
export OPENCODE_CONFIG_DIR="$config_dir"
export XDG_CONFIG_HOME="$config_dir/.xdg-config"
export OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true
export OPENCODE_DISABLE_PROJECT_CONFIG=1
export OPENCODE_DISABLE_EXTERNAL_SKILLS=1
export OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1
exec "$config_dir/node_modules/.bin/opencode" "$@"
"""

WINDOWS_LAUNCHER = r"""@echo off
setlocal
for %%I in ("%~dp0..") do set "BIEXCE_CONFIG_DIR=%%~fI"
set "OPENCODE_CONFIG_DIR=%BIEXCE_CONFIG_DIR%"
set "XDG_CONFIG_HOME=%BIEXCE_CONFIG_DIR%\.xdg-config"
set "OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true"
set "OPENCODE_DISABLE_PROJECT_CONFIG=1"
set "OPENCODE_DISABLE_EXTERNAL_SKILLS=1"
set "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1"
call "%BIEXCE_CONFIG_DIR%\node_modules\.bin\opencode.cmd" %*
exit /b %ERRORLEVEL%
"""


def write_launchers(destination: Path) -> None:
    bin_dir = destination / "bin"
    bin_dir.mkdir(parents=True)
    posix = bin_dir / "biexce-opencode"
    posix.write_text(POSIX_LAUNCHER, encoding="utf-8", newline="\n")
    posix.chmod(0o755)
    (bin_dir / "biexce-opencode.cmd").write_text(
        WINDOWS_LAUNCHER,
        encoding="utf-8",
        newline="\r\n",
    )
    (destination / ".xdg-config" / "opencode").mkdir(parents=True)
