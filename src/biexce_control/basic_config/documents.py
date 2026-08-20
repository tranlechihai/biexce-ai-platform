"""Create deterministic OpenCode documents for the Plan/Build workflow."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .errors import BasicConfigError


MODEL_PATTERN = re.compile(r"[^\s/]+/[^\s]+")
PRESERVED_KEYS = ("$schema", "provider", "mcp", "watcher")


def validate_model(model: str, label: str) -> None:
    if not isinstance(model, str) or not MODEL_PATTERN.fullmatch(model):
        raise BasicConfigError(
            f"{label} must use an exact provider/model ID: {model!r}"
        )


def validate_catalog(model: str, source: dict[str, Any], label: str) -> None:
    provider_id, model_id = model.split("/", 1)
    providers = source.get("provider", {})
    if not isinstance(providers, dict):
        raise BasicConfigError("Source OpenCode provider config must be an object.")
    provider = providers.get(provider_id)
    if provider is None:
        return
    models = provider.get("models") if isinstance(provider, dict) else None
    if not isinstance(models, dict) or model_id not in models:
        raise BasicConfigError(
            f"{label} selects {model!r}, but it is absent from provider "
            f"{provider_id!r} in the source OpenCode config."
        )


def _task_permission() -> dict[str, str]:
    return {"*": "deny", "explore": "allow", "general": "allow"}


def opencode_document(
    source: dict[str, Any],
    *,
    plan_model: str,
    build_model: str,
) -> dict[str, Any]:
    document = {
        key: copy.deepcopy(source[key])
        for key in PRESERVED_KEYS
        if key in source
    }
    document.setdefault("$schema", "https://opencode.ai/config.json")
    document.update(
        {
            "autoupdate": False,
            "default_agent": "plan",
            "share": "disabled",
            "subagent_depth": 1,
            "agent": {
                "plan": {
                    "description": "Read-only planning with BIEXCE guidance.",
                    "mode": "primary",
                    "model": plan_model,
                    "prompt": "{file:./prompts/plan.md}",
                    "temperature": 0.1,
                    "permission": {
                        "edit": "deny",
                        "task": _task_permission(),
                    },
                },
                "build": {
                    "description": "Implementation, testing, and repair.",
                    "mode": "primary",
                    "model": build_model,
                    "prompt": "{file:./prompts/build.md}",
                    "temperature": 0.1,
                    "permission": {"task": _task_permission()},
                },
            },
        }
    )
    return document


def marker_document(plan_model: str, build_model: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "workflow": "plan-build",
        "roles": ["plan", "build"],
        "models": {"plan": plan_model, "build": build_model},
        "skills": "all",
    }


def source_config_path(source_config_dir: Path | None) -> Path:
    if source_config_dir is not None:
        return source_config_dir.expanduser().resolve() / "opencode.json"
    return Path.home() / ".config" / "opencode" / "opencode.json"
