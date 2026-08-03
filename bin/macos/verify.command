#!/bin/bash
set -u

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
VERIFIER="$ROOT/scripts/biexce_linux.py"
TARGET_PATH="$HOME/.config/opencode"
VERIFY_EXIT=0
PYTHON_COMMAND=""

case "$(uname -m)" in
    arm64) PLATFORM_NAME="Apple Silicon" ;;
    x86_64) PLATFORM_NAME="Intel" ;;
    *) PLATFORM_NAME="$(uname -m)" ;;
esac

printf '\nBiexce OpenCode Agent Harness\n'
printf 'User-global macOS verification.\n'
printf 'Mac architecture: %s\n\n' "$PLATFORM_NAME"
printf 'Target: "%s"\n\n' "$TARGET_PATH"

if [[ ! -f "$VERIFIER" ]]; then
    printf 'ERROR: scripts/biexce_linux.py was not found.\n' >&2
    printf 'Clone or extract the complete BIEXCE distribution before verifying.\n' >&2
    VERIFY_EXIT=1
else
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_COMMAND="$(command -v python3)"
    else
        for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
            if [[ -x "$candidate" ]]; then
                PYTHON_COMMAND="$candidate"
                break
            fi
        done
    fi

    if [[ -z "$PYTHON_COMMAND" ]]; then
        printf 'ERROR: python3 was not found. Install Python 3, then run this file again.\n' >&2
        VERIFY_EXIT=1
    else
        "$PYTHON_COMMAND" "$VERIFIER" verify --root "$ROOT" \
            --target "$TARGET_PATH" --platform macos
        VERIFY_EXIT=$?
    fi
fi

if [[ "$VERIFY_EXIT" -eq 0 ]]; then
    printf '\nVERIFY PASS\n'
else
    printf '\nVERIFY FAILED\n'
fi

if [[ -t 0 && -t 1 ]]; then
    printf '\nPress Return to close...'
    read -r _
fi

exit "$VERIFY_EXIT"
