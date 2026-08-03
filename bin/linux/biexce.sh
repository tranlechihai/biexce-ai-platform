#!/usr/bin/env bash
set -u

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
    printf 'ERROR: Python 3 was not found in PATH.\n' >&2
    exit 1
fi

exec python3 "$ROOT/scripts/biexce.py" "$@"
