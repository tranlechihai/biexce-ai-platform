"""Safe paths for machine-local evaluation evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import uuid

from .errors import EvaluationError


def default_evaluation_root() -> Path:
    override = os.environ.get("BIEXCE_EVAL_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "biexce" / "evals"
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return state / "biexce" / "evals"


def project_directory(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise EvaluationError(f"Project directory does not exist: {path}")
    return path


def new_run_directory(
    project: Path,
    output: str | Path | None = None,
    label: str | None = None,
) -> Path:
    root = Path(output).expanduser().resolve() if output else default_evaluation_root()
    slug = _slug(label or project.name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = root / f"{stamp}-{slug}-{uuid.uuid4().hex[:8]}"
    if run.exists():
        raise EvaluationError(f"Evaluation run already exists: {run}")
    # Python 3.13 gives mode 0o700 special Windows ACL semantics. Create with
    # platform defaults there so the current process can still traverse it.
    run.mkdir(parents=True)
    if os.name != "nt":
        os.chmod(run, 0o700)
    return run


def report_file(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    candidate = path / "report.json" if path.is_dir() else path
    if not candidate.is_file():
        raise EvaluationError(f"Evaluation report does not exist: {candidate}")
    return candidate


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "run"
