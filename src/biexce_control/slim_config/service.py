"""High-level build and inspection services for BIEXCE Slim configs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..model_routing import AGENTS, load_applied_routing, opencode_config_root
from .builder import build_config, build_prototype
from .catalog import EXPECTED_TEMPLATES, ROLE_ORDER, SLIM_IDS
from .errors import SlimConfigError
from .jsonio import read_json


def _models_from_applied(config_home: str | Path | None) -> dict[str, str]:
    applied = load_applied_routing(config_home)
    routing = applied.get("routing")
    bindings = routing.get("agents") if isinstance(routing, dict) else None
    if not isinstance(bindings, dict):
        raise SlimConfigError("Applied routing has no agent bindings.")
    models: dict[str, str] = {}
    for role in AGENTS:
        binding = bindings.get(role)
        primary = binding.get("primary") if isinstance(binding, dict) else None
        if not isinstance(primary, str) or not primary:
            raise SlimConfigError(f"Applied routing has no primary for {role}.")
        models[role] = primary
    return models


def build_from_user_routing(
    output: Path,
    *,
    config_home: str | Path | None = None,
    opencode_root: str | Path | None = None,
    routing_file: Path | None = None,
) -> Path:
    base = opencode_config_root(opencode_root) / "opencode.json"
    if routing_file is not None:
        return build_prototype(routing_file, output, base)
    return build_config(_models_from_applied(config_home), output, base)


def _check(name: str, ok: bool, detail: str) -> dict[str, object]:
    return {"name": name, "ok": ok, "detail": detail}


def inspect_generated_config(config_dir: str | Path) -> dict[str, object]:
    root = Path(config_dir).expanduser().resolve()
    checks: list[dict[str, object]] = []
    if root.is_symlink() or not root.is_dir():
        return {
            "ok": False,
            "config_dir": str(root),
            "checks": [_check("config_dir", False, "Directory is missing or unsafe")],
        }
    try:
        opencode = read_json(root / "opencode.json")
        slim = read_json(root / "oh-my-opencode-slim.json")
        package = read_json(root / "package.json")
        compatibility = read_json(root / "compatibility.json")
    except SlimConfigError as error:
        return {
            "ok": False,
            "config_dir": str(root),
            "checks": [_check("documents", False, str(error))],
        }

    expected_plugin = [
        f"{compatibility['slim']['package']}@{compatibility['slim']['version']}",
        "./plugins/biexce-role-access.js",
        "./plugins/biexce-recovery.js",
    ]
    checks.append(
        _check("opencode", opencode.get("plugin") == expected_plugin, str(expected_plugin))
    )
    agents = slim.get("agents")
    actual_agents = set(agents) if isinstance(agents, dict) else set()
    checks.append(
        _check("roles", actual_agents == set(SLIM_IDS.values()), "seven BIEXCE roles")
    )
    models_ok = isinstance(agents, dict) and all(
        isinstance(agents.get(SLIM_IDS[role], {}).get("model"), str)
        for role in ROLE_ORDER
    )
    checks.append(_check("models", models_ok, "seven explicit provider/model bindings"))
    checks.append(
        _check("command", (root / "commands" / "bx-auto.md").is_file(), "/bx-auto")
    )
    templates = {
        path.name for path in (root / "biexce" / "templates").glob("*.md")
    }
    checks.append(
        _check("templates", templates == EXPECTED_TEMPLATES, "workflow artifacts")
    )
    recovery_ok = (
        (root / "plugins" / "biexce-recovery.js").is_file()
        and (root / "runtime" / "recovery-core.js").is_file()
    )
    checks.append(_check("recovery", recovery_ok, "native session recovery bridge"))
    access_ok = (
        (root / "plugins" / "biexce-role-access.js").is_file()
        and (root / "runtime" / "role-access.js").is_file()
    )
    checks.append(
        _check("role_access", access_ok, "seven directly selectable BIEXCE roles")
    )
    launcher_ok = (
        (root / "bin" / "biexce-opencode").is_file()
        and (root / "bin" / "biexce-opencode.cmd").is_file()
        and (root / ".xdg-config" / "opencode").is_dir()
    )
    checks.append(
        _check("launcher", launcher_ok, "isolated OpenCode launcher")
    )
    dependencies = package.get("dependencies")
    pins_ok = isinstance(dependencies, dict) and all(
        dependencies.get(name) == version
        for name, version in (
            (compatibility["slim"]["package"], compatibility["slim"]["version"]),
            ("@opencode-ai/sdk", compatibility["opencode"]["prototype_sdk"]),
            ("@opencode-ai/plugin", compatibility["opencode"]["prototype_plugin"]),
        )
    )
    checks.append(_check("pins", pins_ok, "exact Slim and OpenCode SDK versions"))
    installed = (root / "node_modules").is_dir()
    checks.append(_check("dependencies", installed, "npm install required"))
    structural = all(bool(item["ok"]) for item in checks if item["name"] != "dependencies")
    return {
        "ok": structural,
        "ready_to_run": structural and installed,
        "config_dir": str(root),
        "checks": checks,
    }
