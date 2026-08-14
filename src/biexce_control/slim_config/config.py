"""Validate inputs and build OpenCode/Slim configuration documents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .catalog import (
    DESCRIPTIONS,
    DISPLAY_NAMES,
    ROLE_ORDER,
    ROUTING_BLOCKS,
    SKILLS,
    SLIM_IDS,
)
from .errors import PrototypeError
from .jsonio import read_json
from .permissions import global_permission, role_permission


def load_routing(path: Path) -> dict[str, str]:
    document = read_json(path)
    if document.get("schema_version") != 1:
        raise PrototypeError("Routing schema_version must be 1.")
    models = document.get("models")
    if not isinstance(models, dict) or set(models) != set(ROLE_ORDER):
        raise PrototypeError("Routing must contain exactly all seven BIEXCE role IDs.")
    for role in ROLE_ORDER:
        model = models[role]
        if not isinstance(model, str) or not re.fullmatch(r"[^\s/]+/[^\s]+", model):
            raise PrototypeError(
                f"{role} model must use provider/model format: {model!r}"
            )
    return {role: models[role] for role in ROLE_ORDER}


def validate_models(
    models: dict[str, str],
    source: dict[str, Any],
) -> None:
    providers = source.get("provider", {})
    if not isinstance(providers, dict):
        raise PrototypeError("Base OpenCode provider config must be an object.")
    for role, model in models.items():
        provider_id, model_id = model.split("/", 1)
        provider = providers.get(provider_id)
        if provider is None:
            continue
        if not isinstance(provider, dict) or not isinstance(
            provider.get("models"), dict
        ):
            raise PrototypeError(
                f"Provider {provider_id!r} has no model catalog in base config."
            )
        if model_id not in provider["models"]:
            raise PrototypeError(
                f"{role} selects {model!r}, but that model is missing from "
                f"provider {provider_id!r} in the base OpenCode config."
            )


def slim_document(models: dict[str, str]) -> dict[str, Any]:
    agents: dict[str, Any] = {}
    for role in ROLE_ORDER:
        slim_id = SLIM_IDS[role]
        definition: dict[str, Any] = {
            "model": models[role],
            "displayName": DISPLAY_NAMES[role],
            "temperature": 0.1,
            "skills": list(SKILLS[role]),
            "mcps": [],
            "permission": role_permission(role),
        }
        if role != "bx-director":
            definition["description"] = DESCRIPTIONS[role]
            definition["orchestratorPrompt"] = (
                f"@{slim_id}\n- Role: {ROUTING_BLOCKS[role]}"
            )
        agents[slim_id] = definition

    return {
        "$schema": (
            "https://unpkg.com/oh-my-opencode-slim@2.2.13/"
            "oh-my-opencode-slim.schema.json"
        ),
        "autoUpdate": False,
        "disabled_agents": [
            "explorer",
            "librarian",
            "oracle",
            "designer",
            "fixer",
            "observer",
            "council",
        ],
        "agents": agents,
        "backgroundJobs": {
            "strategy": "checkpoint-compatible",
            "maxRetainedSnapshots": 20,
            "orchestratorWake": {
                "enabled": True,
                "intervalMs": 300000,
            },
        },
        "multiplexer": {"type": "none"},
        "companion": {"enabled": False},
        "image_routing": "direct",
    }


def opencode_document(
    compatibility: dict[str, Any],
    base_opencode_path: Path,
) -> dict[str, Any]:
    source = read_json(base_opencode_path)
    source.pop("agent", None)
    for server in source.get("mcp", {}).values():
        if isinstance(server, dict):
            server["enabled"] = False
    source["plugin"] = [
        f"{compatibility['slim']['package']}@{compatibility['slim']['version']}",
        "./plugins/biexce-recovery.js",
    ]
    source["default_agent"] = "orchestrator"
    source["subagent_depth"] = 1
    source["autoupdate"] = False
    source["permission"] = global_permission()
    return source


def package_document(compatibility: dict[str, Any]) -> dict[str, Any]:
    return {
        "private": True,
        "type": "module",
        "devDependencies": {
            "opencode-ai": compatibility["opencode"]["prototype_cli"],
        },
        "dependencies": {
            "@opencode-ai/plugin": compatibility["opencode"]["prototype_plugin"],
            "@opencode-ai/sdk": compatibility["opencode"]["prototype_sdk"],
            compatibility["slim"]["package"]: compatibility["slim"]["version"],
            "zod": compatibility["runtime"]["zod"],
        },
    }
