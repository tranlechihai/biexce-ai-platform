#!/usr/bin/env bash
set -u

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
VERIFIER="$ROOT/scripts/biexce_linux.py"
TARGET_PATH="${1:-$HOME/.config/opencode}"
VERIFY_EXIT=0

if [[ ! -f "$VERIFIER" ]]; then
    printf 'ERROR: scripts/biexce_linux.py was not found.\n' >&2
    VERIFY_EXIT=1
elif ! command -v python3 >/dev/null 2>&1; then
    printf 'ERROR: python3 was not found in PATH.\n' >&2
    VERIFY_EXIT=1
else
    python3 "$VERIFIER" verify --root "$ROOT" --target "$TARGET_PATH" \
        --platform linux
    VERIFY_EXIT=$?
fi

if [[ "$VERIFY_EXIT" -eq 0 ]]; then
    printf 'VERIFY PASS\n'
else
    printf 'VERIFY FAILED\n'
fi

exit "$VERIFY_EXIT"
