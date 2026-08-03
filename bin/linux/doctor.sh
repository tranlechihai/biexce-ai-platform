#!/usr/bin/env bash
set -u

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
TARGET_PATH="${1:-$HOME/.config/opencode}"
exec python3 "$ROOT/scripts/biexce_linux.py" doctor --root "$ROOT" --target "$TARGET_PATH"
