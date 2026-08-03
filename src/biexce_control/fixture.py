"""Safe initialization and reset of the deterministic self-test project."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid

from .autopilot import ControlPlaneError


FIXTURE_ID = "self-test-project-v1"
MARKER_RELATIVE_PATH = Path(".biexce") / "FIXTURE.json"


class FixtureError(ControlPlaneError):
    """Fixture initialization or reset is unsafe or invalid."""


def template_root() -> Path:
    root = Path(__file__).resolve().parent / "resources" / "self-test-project"
    if not root.is_dir():
        raise FixtureError(f"Fixture template is missing: {root}")
    return root


def _target(value: str | os.PathLike[str] | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path == Path(path.anchor) or path == Path.home().resolve():
        raise FixtureError("Refusing to use a filesystem or home root as fixture.")
    return path


def _read_marker(target: Path) -> dict[str, object]:
    marker = target / MARKER_RELATIVE_PATH
    try:
        document = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise FixtureError(f"Fixture marker is missing or invalid: {error}")
    if not isinstance(document, dict) or document.get("fixture_id") != FIXTURE_ID:
        raise FixtureError("Target is not a BIEXCE self-test project.")
    return document


def init_fixture(value: str | os.PathLike[str] | Path) -> Path:
    target = _target(value)
    if target.exists():
        if not target.is_dir():
            raise FixtureError(f"Fixture target is not a directory: {target}")
        if any(target.iterdir()):
            raise FixtureError(f"Fixture target must be empty: {target}")
    else:
        target.mkdir(parents=True)
    try:
        shutil.copytree(template_root(), target, dirs_exist_ok=True)
        (target / "tests").mkdir(exist_ok=True)
        _read_marker(target)
    except Exception:
        if target.exists() and not any(target.iterdir()):
            target.rmdir()
        raise
    return target


def reset_fixture(
    value: str | os.PathLike[str] | Path,
    *,
    confirmation: str,
) -> Path:
    target = _target(value)
    if confirmation != FIXTURE_ID:
        raise FixtureError(f"Reset requires --confirm-reset {FIXTURE_ID}.")
    if not target.is_dir() or target.is_symlink():
        raise FixtureError(f"Fixture target is missing or unsafe: {target}")
    _read_marker(target)
    parent = target.parent
    stage: Path | None = Path(
        tempfile.mkdtemp(prefix=".biexce-fixture-stage-", dir=parent)
    )
    backup = parent / f".biexce-fixture-backup-{uuid.uuid4().hex}"
    moved = False
    try:
        shutil.copytree(template_root(), stage, dirs_exist_ok=True)
        (stage / "tests").mkdir(exist_ok=True)
        _read_marker(stage)
        os.replace(target, backup)
        moved = True
        os.replace(stage, target)
        stage = None
        shutil.rmtree(backup)
        moved = False
    except Exception as error:
        if moved and backup.exists() and not target.exists():
            os.replace(backup, target)
            moved = False
        raise FixtureError(f"Fixture reset failed safely: {error}")
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if backup.exists() and not moved:
            shutil.rmtree(backup, ignore_errors=True)
    return target


def fixture_status(value: str | os.PathLike[str] | Path) -> dict[str, object]:
    target = _target(value)
    marker = _read_marker(target)
    tasks = sorted((target / ".biexce" / "tasks").glob("t-*.md"))
    return {
        "fixture_id": marker["fixture_id"],
        "project_root": str(target),
        "task_count": len(tasks),
        "tasks": [path.stem for path in tasks],
    }
