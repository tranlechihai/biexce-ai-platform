"""Filesystem-safe assembly of an isolated Slim prototype config."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from .catalog import (
    COMMAND_SOURCE,
    COMPATIBILITY_PATH,
    EXPECTED_COMMANDS,
    EXPECTED_PROMPTS,
    EXPECTED_PLUGINS,
    EXPECTED_RUNTIME,
    EXPECTED_TEMPLATES,
    PLUGIN_SOURCE,
    RUNTIME_SOURCE,
    PROMPT_SOURCE,
    SKILLS,
    SOURCE_GLOBAL,
    TEMPLATE_SOURCE,
)
from .config import (
    load_routing,
    opencode_document,
    package_document,
    slim_document,
    validate_models,
)
from .errors import PrototypeError
from .jsonio import read_json, write_json
from .launchers import write_launchers


def _global_config_roots() -> set[Path]:
    roots = {(Path.home() / ".config" / "opencode").resolve()}
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.add((Path(appdata) / "opencode").resolve())
    return roots


def validate_output_path(output: Path) -> Path:
    resolved = output.expanduser().resolve()
    for global_root in _global_config_roots():
        if resolved == global_root or global_root in resolved.parents:
            raise PrototypeError(
                f"Refusing to write prototype into user-global config: {resolved}"
            )
    if resolved.exists():
        raise PrototypeError(f"Output already exists; choose a fresh path: {resolved}")
    return resolved


def _skill_index() -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in sorted((SOURCE_GLOBAL / "skills").rglob("SKILL.md")):
        skill_id = path.parent.name
        if skill_id in index:
            raise PrototypeError(f"Duplicate skill ID in source: {skill_id}")
        index[skill_id] = path
    return index


def _copy_prompts(destination: Path) -> None:
    target = destination / "oh-my-opencode-slim"
    target.mkdir(parents=True)
    discovered = {path.name for path in PROMPT_SOURCE.glob("*.md")}
    if discovered != EXPECTED_PROMPTS:
        raise PrototypeError(
            "Prompt set mismatch: expected "
            f"{sorted(EXPECTED_PROMPTS)}, got {sorted(discovered)}"
        )
    for name in sorted(EXPECTED_PROMPTS):
        shutil.copy2(PROMPT_SOURCE / name, target / name)


def _copy_plugins(destination: Path) -> None:
    target = destination / "plugins"
    target.mkdir(parents=True)
    discovered = {path.name for path in PLUGIN_SOURCE.glob("*.js")}
    if discovered != EXPECTED_PLUGINS:
        raise PrototypeError(
            "Plugin set mismatch: expected "
            f"{sorted(EXPECTED_PLUGINS)}, got {sorted(discovered)}"
        )
    for name in sorted(EXPECTED_PLUGINS):
        shutil.copy2(PLUGIN_SOURCE / name, target / name)


def _copy_runtime(destination: Path) -> None:
    target = destination / "runtime"
    target.mkdir(parents=True)
    discovered = {path.name for path in RUNTIME_SOURCE.glob("*.js")}
    if discovered != EXPECTED_RUNTIME:
        raise PrototypeError(
            "Runtime bridge set mismatch: expected "
            f"{sorted(EXPECTED_RUNTIME)}, got {sorted(discovered)}"
        )
    for name in sorted(EXPECTED_RUNTIME):
        shutil.copy2(RUNTIME_SOURCE / name, target / name)


def _copy_exact_set(
    source: Path,
    destination: Path,
    expected: set[str],
    label: str,
) -> None:
    discovered = {path.name for path in source.glob("*.md")}
    if discovered != expected:
        raise PrototypeError(
            f"{label} set mismatch: expected "
            f"{sorted(expected)}, got {sorted(discovered)}"
        )
    destination.mkdir(parents=True)
    for name in sorted(expected):
        shutil.copy2(source / name, destination / name)


def _copy_skills(destination: Path) -> None:
    index = _skill_index()
    selected = sorted({skill for values in SKILLS.values() for skill in values})
    missing = [skill for skill in selected if skill not in index]
    if missing:
        raise PrototypeError(f"Missing source skills: {missing}")
    for skill in selected:
        source = index[skill]
        relative = source.relative_to(SOURCE_GLOBAL / "skills")
        target = destination / "skills" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _assemble(
    staging: Path,
    models: dict[str, str],
    compatibility: dict,
    base_config: Path,
) -> None:
    write_json(staging / "opencode.json", opencode_document(compatibility, base_config))
    write_json(staging / "oh-my-opencode-slim.json", slim_document(models))
    write_json(staging / "package.json", package_document(compatibility))
    write_json(staging / "compatibility.json", compatibility)
    (staging / "runtime.env.example").write_text(
        "OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true\n",
        encoding="utf-8",
        newline="\n",
    )
    _copy_prompts(staging)
    _copy_plugins(staging)
    _copy_runtime(staging)
    _copy_exact_set(
        COMMAND_SOURCE,
        staging / "commands",
        EXPECTED_COMMANDS,
        "Command",
    )
    _copy_exact_set(
        TEMPLATE_SOURCE,
        staging / "biexce" / "templates",
        EXPECTED_TEMPLATES,
        "Template",
    )
    _copy_skills(staging)
    write_launchers(staging)


def build_prototype(
    routing_path: Path,
    output_path: Path,
    base_opencode_path: Path | None = None,
) -> Path:
    models = load_routing(routing_path)
    return build_config(models, output_path, base_opencode_path)


def build_config(
    models: dict[str, str],
    output_path: Path,
    base_opencode_path: Path | None = None,
) -> Path:
    if set(models) != set(SKILLS):
        raise PrototypeError(
            "Models must contain exactly all seven BIEXCE role IDs."
        )
    output = validate_output_path(output_path)
    compatibility = read_json(COMPATIBILITY_PATH)
    base_config = (
        base_opencode_path.expanduser().resolve()
        if base_opencode_path is not None
        else SOURCE_GLOBAL / "opencode.json"
    )
    validate_models(models, read_json(base_config))

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".{output.name}.tmp-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        _assemble(staging, models, compatibility, base_config)
        staging.replace(output)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return output
