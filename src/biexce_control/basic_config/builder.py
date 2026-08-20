"""Atomic builder for an isolated BIEXCE Plan/Build configuration."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from .documents import (
    marker_document,
    opencode_document,
    source_config_path,
    validate_catalog,
    validate_model,
)
from .errors import BasicConfigError
from .launchers import write_launchers


SOURCE_GLOBAL = Path(__file__).resolve().parents[2] / "global"
SOURCE_BASIC = SOURCE_GLOBAL / "basic"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BasicConfigError(f"Cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise BasicConfigError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _global_config_roots() -> set[Path]:
    roots = {(Path.home() / ".config" / "opencode").resolve()}
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.add((Path(appdata) / "opencode").resolve())
    return roots


def _validate_output(output: Path) -> Path:
    resolved = output.expanduser().resolve()
    if resolved.exists():
        raise BasicConfigError(f"Output already exists: {resolved}")
    if any(resolved == root for root in _global_config_roots()):
        raise BasicConfigError("Refusing to replace the user OpenCode config directly.")
    return resolved


def _copy_skills(destination: Path) -> None:
    source = SOURCE_GLOBAL / "skills"
    for source_file in sorted(source.rglob("*")):
        relative = source_file.relative_to(source)
        if not source_file.is_file() or "_TEMPLATE" in relative.parts:
            continue
        target = destination / "skills" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)


def _assemble(
    destination: Path,
    source: dict[str, Any],
    plan_model: str,
    build_model: str,
) -> None:
    _write_json(
        destination / "opencode.json",
        opencode_document(
            source,
            plan_model=plan_model,
            build_model=build_model,
        ),
    )
    _write_json(
        destination / "biexce-basic.json",
        marker_document(plan_model, build_model),
    )
    shutil.copy2(SOURCE_BASIC / "AGENTS.md", destination / "AGENTS.md")
    shutil.copytree(SOURCE_BASIC / "prompts", destination / "prompts")
    _copy_skills(destination)
    write_launchers(destination)


def build_config(
    output: Path,
    *,
    plan_model: str,
    build_model: str,
    source_config_dir: Path | None = None,
) -> Path:
    validate_model(plan_model, "Plan model")
    validate_model(build_model, "Build model")
    source = _read_json(source_config_path(source_config_dir))
    validate_catalog(plan_model, source, "Plan")
    validate_catalog(build_model, source, "Build")

    target = _validate_output(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.tmp-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        _assemble(staging, source, plan_model, build_model)
        staging.replace(target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return target
