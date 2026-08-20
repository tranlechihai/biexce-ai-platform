"""Structural and runtime checks for generated Plan/Build configurations."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .errors import BasicConfigError


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BasicConfigError(f"Cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise BasicConfigError(f"JSON root must be an object: {path}")
    return value


def _check(name: str, ok: bool, detail: str) -> dict[str, object]:
    return {"name": name, "ok": ok, "detail": detail}


def inspect_config(config_dir: str | Path) -> dict[str, object]:
    root = Path(config_dir).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        return {
            "ok": False,
            "config_dir": str(root),
            "checks": [_check("config_dir", False, "Directory is missing or unsafe")],
        }
    try:
        config = _read_json(root / "opencode.json")
        marker = _read_json(root / "biexce-basic.json")
    except BasicConfigError as error:
        return {
            "ok": False,
            "config_dir": str(root),
            "checks": [_check("documents", False, str(error))],
        }

    agents = config.get("agent")
    roles_ok = isinstance(agents, dict) and set(agents) == {"plan", "build"}
    model_ok = roles_ok and all(
        isinstance(agents[name].get("model"), str) for name in ("plan", "build")
    )
    skills = list((root / "skills").rglob("SKILL.md"))
    checks = [
        _check("workflow", marker.get("workflow") == "plan-build", "Plan/Build"),
        _check("roles", roles_ok, "exactly Plan and Build"),
        _check("models", model_ok, "two explicit model bindings"),
        _check("plugins", "plugin" not in config, "no legacy or Slim plugin"),
        _check(
            "prompts",
            all(
                (root / "prompts" / f"{role}.md").is_file()
                for role in ("plan", "build")
            ),
            "Plan/Build prompts",
        ),
        _check("rules", (root / "AGENTS.md").is_file(), "shared BIEXCE rules"),
        _check("skills", len(skills) >= 40, f"{len(skills)} skills available"),
        _check(
            "launcher",
            all(
                (root / "bin" / name).is_file()
                for name in ("biexce-opencode", "biexce-opencode.cmd")
            ),
            "cross-platform launchers",
        ),
    ]
    return {
        "ok": all(bool(item["ok"]) for item in checks),
        "ready_to_run": False,
        "config_dir": str(root),
        "checks": checks,
    }


def _launcher_command(root: Path, *arguments: str) -> list[str]:
    if os.name == "nt":
        launcher = root / "bin" / "biexce-opencode.cmd"
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(launcher), *arguments]
    return [str(root / "bin" / "biexce-opencode"), *arguments]


def _run_launcher(
    root: Path,
    *arguments: str,
    opencode_binary: str | None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if opencode_binary:
        environment["OPENCODE_BINARY"] = opencode_binary
    return subprocess.run(
        _launcher_command(root, *arguments),
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env=environment,
    )


def _registry_check(root: Path, binary: str | None) -> dict[str, object]:
    completed = _run_launcher(
        root,
        "debug",
        "config",
        opencode_binary=binary,
    )
    effective = json.loads(completed.stdout)
    agents = effective.get("agent", {})
    expected = _read_json(root / "biexce-basic.json").get("models", {})
    active = all(
        isinstance(agents.get(name), dict)
        and agents[name].get("disable") is not True
        and agents[name].get("model") == expected.get(name)
        for name in ("plan", "build")
    )
    forbidden = ("bx-director", "bx-plan", "orchestrator")
    legacy = any(
        isinstance(agents.get(name), dict)
        and agents[name].get("disable") is not True
        for name in forbidden
    )
    plugins = " ".join(str(item) for item in effective.get("plugin", []))
    isolated = not legacy and "biexce-control" not in plugins and "oh-my" not in plugins
    return _check(
        "agent_registry",
        active and isolated,
        "active Plan/Build registry without legacy runtime"
        if active and isolated
        else "Plan/Build disabled or legacy runtime leaked into effective config",
    )


def run_doctor(
    config_dir: str | Path,
    opencode_binary: str | None = None,
) -> dict[str, object]:
    result = inspect_config(config_dir)
    if not result["ok"]:
        return result
    root = Path(config_dir).expanduser().resolve()
    binary = opencode_binary
    runtime_checks: list[dict[str, object]] = []
    configured = binary or os.environ.get("OPENCODE_BINARY") or shutil.which("opencode")
    if configured is None:
        runtime_checks.append(_check("opencode", False, "OpenCode CLI not found"))
    else:
        try:
            completed = _run_launcher(
                root,
                "--version",
                opencode_binary=binary,
            )
            version = (completed.stdout or completed.stderr).strip()
            runtime_checks.append(_check("opencode", True, version))
            runtime_checks.append(_registry_check(root, binary))
        except (OSError, subprocess.SubprocessError) as error:
            runtime_checks.append(_check("opencode", False, str(error)))
        except (BasicConfigError, json.JSONDecodeError) as error:
            runtime_checks.append(_check("agent_registry", False, str(error)))
    result["runtime_checks"] = runtime_checks
    result["ready_to_run"] = all(bool(item["ok"]) for item in runtime_checks)
    return result
