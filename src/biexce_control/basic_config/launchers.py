"""Launchers that keep Plan/Build isolated from the legacy agent runtime."""

from __future__ import annotations

from pathlib import Path


POSIX = """#!/bin/sh
set -eu
config_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
export OPENCODE_CONFIG_DIR="$config_dir"
export OPENCODE_DISABLE_PROJECT_CONFIG=1
export OPENCODE_DISABLE_EXTERNAL_SKILLS=1
export OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1
export OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true
if [ -n "${OPENCODE_BINARY:-}" ]; then
    exec "$OPENCODE_BINARY" "$@"
fi
exec opencode "$@"
"""


WINDOWS = r"""@echo off
setlocal
for %%I in ("%~dp0..") do set "OPENCODE_CONFIG_DIR=%%~fI"
set "OPENCODE_DISABLE_PROJECT_CONFIG=1"
set "OPENCODE_DISABLE_EXTERNAL_SKILLS=1"
set "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1"
set "OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true"
if defined OPENCODE_BINARY (
  call "%OPENCODE_BINARY%" %*
) else (
  call opencode %*
)
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
