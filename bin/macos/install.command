#!/bin/bash
set -u

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
INSTALLER="$ROOT/scripts/biexce_linux.py"
TARGET_PATH="$HOME/.config/opencode"
INSTALL_EXIT=0
PYTHON_COMMAND=""

activate_biexce_command() {
    local profile="$HOME/.zprofile"
    local marker="# BIEXCE command"
    if [[ "${SHELL##*/}" == "bash" ]]; then
        profile="$HOME/.profile"
    fi
    if [[ ! -f "$profile" ]] || ! grep -Fq "$marker" "$profile"; then
        printf '\n%s\nexport PATH="$HOME/.config/opencode/biexce-bin:$PATH"\n' \
            "$marker" >> "$profile" || return 1
    fi
    export PATH="$TARGET_PATH/biexce-bin:$PATH"
}

case "$(uname -m)" in
    arm64) PLATFORM_NAME="Apple Silicon" ;;
    x86_64) PLATFORM_NAME="Intel" ;;
    *) PLATFORM_NAME="$(uname -m)" ;;
esac

printf '\nBiexce OpenCode Agent Harness\n'
printf 'User-global macOS installation - sudo is not required.\n'
printf 'Mac architecture: %s\n\n' "$PLATFORM_NAME"
printf 'Target: "%s"\n\n' "$TARGET_PATH"

if [[ ! -f "$INSTALLER" ]]; then
    printf 'ERROR: scripts/biexce_linux.py was not found.\n' >&2
    printf 'Clone or extract the complete BIEXCE distribution before installing.\n' >&2
    INSTALL_EXIT=1
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
        INSTALL_EXIT=1
    else
        "$PYTHON_COMMAND" "$INSTALLER" install --root "$ROOT" \
            --target "$TARGET_PATH" --platform macos
        INSTALL_EXIT=$?
    fi
fi

if [[ "$INSTALL_EXIT" -eq 0 ]] && ! activate_biexce_command; then
    printf 'ERROR: Could not activate the global biexce command.\n' >&2
    INSTALL_EXIT=1
fi

if [[ "$INSTALL_EXIT" -eq 0 ]]; then
    printf '\nINSTALL PASS\n'
    printf 'Open a new terminal, then run: biexce basic --help\n'
else
    printf '\nINSTALL FAILED\n'
fi

if [[ -t 0 && -t 1 ]]; then
    printf '\nPress Return to close...'
    read -r _
fi

exit "$INSTALL_EXIT"
