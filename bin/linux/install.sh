#!/usr/bin/env bash
set -u

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
INSTALLER="$ROOT/scripts/biexce_linux.py"
TARGET_PATH="$HOME/.config/opencode"
INSTALL_EXIT=0

activate_biexce_command() {
    local profile="$HOME/.profile"
    local marker="# BIEXCE command"
    if [[ ! -f "$profile" ]] || ! grep -Fq "$marker" "$profile"; then
        printf '\n%s\nexport PATH="$HOME/.config/opencode/biexce-bin:$PATH"\n' \
            "$marker" >> "$profile" || return 1
    fi
    export PATH="$TARGET_PATH/biexce-bin:$PATH"
}

printf '\nBiexce OpenCode Agent Harness\n'
printf 'User-global Linux installation - sudo is not required.\n\n'
printf 'Target: "%s"\n\n' "$TARGET_PATH"

if [[ ! -f "$INSTALLER" ]]; then
    printf 'ERROR: scripts/biexce_linux.py was not found.\n' >&2
    INSTALL_EXIT=1
elif ! command -v python3 >/dev/null 2>&1; then
    printf 'ERROR: python3 was not found in PATH.\n' >&2
    INSTALL_EXIT=1
else
    python3 "$INSTALLER" install --root "$ROOT" --target "$TARGET_PATH" \
        --platform linux
    INSTALL_EXIT=$?
fi

if [[ "$INSTALL_EXIT" -eq 0 ]] && ! activate_biexce_command; then
    printf 'ERROR: Could not add the biexce command to %s.\n' "$HOME/.profile" >&2
    INSTALL_EXIT=1
fi

if [[ "$INSTALL_EXIT" -eq 0 ]]; then
    printf '\nINSTALL PASS\n'
    printf 'Open a new terminal, then run: biexce basic --help\n'
else
    printf '\nINSTALL FAILED\n'
fi

exit "$INSTALL_EXIT"
