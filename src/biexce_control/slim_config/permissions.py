"""OpenCode tool permissions for the seven BIEXCE roles."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SECRET_READ_RULES = {
    "*": "allow",
    "*.env": "deny",
    "*.env.*": "deny",
    "*.pem": "deny",
    "*.key": "deny",
    "*.pfx": "deny",
    "*.p12": "deny",
    "*credentials*.json": "deny",
    "*secrets*.yaml": "deny",
    "*secrets*.yml": "deny",
}

SHELL_RULES = {
    "*": "ask",
    "pwd": "allow",
    "ls*": "allow",
    "Get-Location*": "allow",
    "Get-ChildItem*": "allow",
    "git status*": "allow",
    "git diff*": "allow",
    "git log*": "allow",
    "python --version": "allow",
    "python3 --version": "allow",
    "python -m unittest*": "allow",
    "python3 -m unittest*": "allow",
    "python -m pytest*": "allow",
    "python3 -m pytest*": "allow",
    "python -m compileall*": "allow",
    "python3 -m compileall*": "allow",
    "pytest*": "allow",
    "node --check*": "allow",
    "npm test*": "allow",
    "npm run test*": "allow",
    "npm run lint*": "allow",
    "npm run typecheck*": "allow",
    "npm run build*": "allow",
    "pnpm test*": "allow",
    "yarn test*": "allow",
    "dotnet test*": "allow",
    "dotnet build*": "allow",
    "go test*": "allow",
    "cargo test*": "allow",
    "cargo check*": "allow",
    "mvn test*": "allow",
    "./mvnw test*": "allow",
    "gradle test*": "allow",
    "./gradlew test*": "allow",
    "git reset*": "ask",
    "git clean*": "ask",
    "git push*": "ask",
    "git commit*": "ask",
    "rm *": "ask",
    "rmdir *": "ask",
    "del *": "ask",
    "Remove-Item *": "ask",
    "kubectl *": "ask",
    "terraform apply*": "ask",
    "terraform destroy*": "ask",
}

READ_ONLY_SHELL_RULES = {
    "*": "deny",
    "git status*": "allow",
    "git diff*": "allow",
    "git log*": "allow",
    "git show*": "allow",
}


def _artifact_edit_rules(filename: str | None = None) -> dict[str, str]:
    if filename:
        return {
            "*": "deny",
            f".biexce/{filename}": "allow",
            f"**/.biexce/{filename}": "allow",
        }
    return {"*": "deny", ".biexce/**": "allow", "**/.biexce/**": "allow"}


def role_permission(role: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "read": deepcopy(SECRET_READ_RULES),
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "lsp": "allow",
        "task": "deny",
        "external_directory": "ask",
    }
    if role == "bx-director":
        base.update(
            {
                "edit": _artifact_edit_rules(),
                "bash": "deny",
                "task": "allow",
                "question": "allow",
                "todowrite": "allow",
            }
        )
    elif role == "bx-explore":
        base.update(
            {
                "edit": _artifact_edit_rules("CODEBASE_BRIEF.md"),
                "bash": "deny",
            }
        )
    elif role == "bx-plan":
        base.update({"edit": _artifact_edit_rules(), "bash": "deny"})
    elif role == "bx-review":
        base.update(
            {"edit": "deny", "bash": deepcopy(READ_ONLY_SHELL_RULES)}
        )
    else:
        base.update({"edit": "allow", "bash": deepcopy(SHELL_RULES)})
    return base


def global_permission() -> dict[str, Any]:
    """Safe user-controlled baseline without legacy workflow blockers."""
    return {
        "*": "ask",
        "read": deepcopy(SECRET_READ_RULES),
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "lsp": "allow",
        "skill": "allow",
        "edit": "ask",
        "task": "ask",
        "external_directory": "ask",
        "webfetch": "ask",
        "websearch": "ask",
        "bash": deepcopy(SHELL_RULES),
    }
