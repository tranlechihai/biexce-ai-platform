"""Project-local, fail-closed state for BIEXCE Autopilot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Callable


SCHEMA_ID = (
    "https://schemas.biexce.local/control-plane/"
    "autopilot-state-v1.schema.json"
)
SCHEMA_VERSION = 1
STATE_FILENAME = "AUTOPILOT_CONTROL.json"
STATE_RELATIVE_PATH = Path(".biexce") / "state" / STATE_FILENAME
MODES = ("OFF", "ON_IDLE", "ARMED", "RUNNING", "PAUSED")
ACTIONS = ("on", "arm", "start", "pause", "off")
SOURCES = ("cli", "desktop", "migration")

_STATE_KEYS = {
    "$schema",
    "schema_version",
    "project_root",
    "mode",
    "revision",
    "updated_at_utc",
    "updated_by",
    "reason",
    "source",
    "action",
    "session_id",
}


class ControlPlaneError(RuntimeError):
    """Base error for control-plane state and transitions."""


class StateValidationError(ControlPlaneError):
    """The persisted state cannot be trusted and must fail closed."""


class InvalidTransitionError(ControlPlaneError):
    """The requested action is not valid for the current mode."""


class ArmValidationRequiredError(ControlPlaneError):
    """Arm is blocked until the Gate 0 validator is connected."""


@dataclass(frozen=True)
class AutopilotState:
    project_root: Path
    mode: str
    revision: int
    updated_at_utc: str | None
    updated_by: str | None
    reason: str
    source: str
    action: str | None
    session_id: str | None
    persisted: bool

    @classmethod
    def fail_closed_default(cls, project_root: Path) -> "AutopilotState":
        return cls(
            project_root=project_root,
            mode="OFF",
            revision=0,
            updated_at_utc=None,
            updated_by=None,
            reason="No control state file; fail-closed default.",
            source="default",
            action=None,
            session_id=None,
            persisted=False,
        )

    def to_document(self) -> dict[str, object]:
        if not self.persisted:
            raise ControlPlaneError("Default state is not a persisted document.")
        return {
            "$schema": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "project_root": str(self.project_root),
            "mode": self.mode,
            "revision": self.revision,
            "updated_at_utc": self.updated_at_utc,
            "updated_by": self.updated_by,
            "reason": self.reason,
            "source": self.source,
            "action": self.action,
            "session_id": self.session_id,
        }


ArmValidator = Callable[[Path, AutopilotState], None]


def resolve_project_root(project: str | os.PathLike[str] | Path) -> Path:
    try:
        project_root = Path(project).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ControlPlaneError(f"Project path cannot be resolved: {error}")
    if not project_root.is_dir():
        raise ControlPlaneError(f"Project path is not a directory: {project_root}")
    return project_root


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((str(path), str(root))) == str(root)
    except ValueError:
        return False


def state_path_for(project_root: Path) -> Path:
    project_root = resolve_project_root(project_root)
    state_path = project_root / STATE_RELATIVE_PATH

    existing_parent = state_path.parent
    while not existing_parent.exists() and existing_parent != project_root:
        existing_parent = existing_parent.parent
    try:
        resolved_parent = existing_parent.resolve(strict=True)
    except OSError as error:
        raise ControlPlaneError(f"State parent cannot be resolved: {error}")
    if not _is_within(resolved_parent, project_root):
        raise ControlPlaneError(
            "Autopilot state path escapes the project through a symlink."
        )
    if state_path.is_symlink():
        raise ControlPlaneError("Autopilot state file must not be a symlink.")
    return state_path


def _require_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateValidationError(f"{label} must be a non-empty string.")
    if len(value) > maximum:
        raise StateValidationError(f"{label} exceeds {maximum} characters.")
    return value


def _validate_utc_timestamp(value: object) -> str:
    text = _require_text(value, "updated_at_utc", 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise StateValidationError(f"updated_at_utc is invalid: {error}")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise StateValidationError("updated_at_utc must include the UTC offset.")
    return text


def _state_from_document(
    document: object,
    project_root: Path,
) -> AutopilotState:
    if not isinstance(document, dict):
        raise StateValidationError("Autopilot state root must be a JSON object.")
    if set(document) != _STATE_KEYS:
        missing = sorted(_STATE_KEYS.difference(document))
        extra = sorted(set(document).difference(_STATE_KEYS))
        raise StateValidationError(
            f"Autopilot state properties mismatch; missing={missing}, extra={extra}."
        )
    if document["$schema"] != SCHEMA_ID:
        raise StateValidationError("Autopilot state schema identifier is invalid.")
    if document["schema_version"] != SCHEMA_VERSION:
        raise StateValidationError("Autopilot state schema version is unsupported.")

    stored_root_text = _require_text(document["project_root"], "project_root", 4096)
    try:
        stored_root = Path(stored_root_text).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise StateValidationError(f"Stored project_root cannot be resolved: {error}")
    if not _same_path(stored_root, project_root):
        raise StateValidationError(
            "Autopilot state belongs to a different project root."
        )

    mode = document["mode"]
    if mode not in MODES:
        raise StateValidationError(f"Unsupported Autopilot mode: {mode!r}.")
    revision = document["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise StateValidationError("revision must be an integer greater than zero.")
    updated_at_utc = _validate_utc_timestamp(document["updated_at_utc"])
    updated_by = _require_text(document["updated_by"], "updated_by", 256)
    reason = _require_text(document["reason"], "reason", 1000)
    source = document["source"]
    if source not in SOURCES:
        raise StateValidationError(f"Unsupported control source: {source!r}.")
    action = document["action"]
    if action not in ACTIONS:
        raise StateValidationError(f"Unsupported control action: {action!r}.")
    session_id = document["session_id"]
    if session_id is not None:
        session_id = _require_text(session_id, "session_id", 256)

    return AutopilotState(
        project_root=project_root,
        mode=mode,
        revision=revision,
        updated_at_utc=updated_at_utc,
        updated_by=updated_by,
        reason=reason,
        source=source,
        action=action,
        session_id=session_id,
        persisted=True,
    )


def load_state(project: str | os.PathLike[str] | Path) -> AutopilotState:
    project_root = resolve_project_root(project)
    state_path = state_path_for(project_root)
    if not state_path.exists():
        return AutopilotState.fail_closed_default(project_root)
    if not state_path.is_file():
        raise StateValidationError(f"Autopilot state is not a file: {state_path}")
    try:
        document = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StateValidationError(
            f"Autopilot state is unreadable; effective mode is OFF: {error}"
        )
    return _state_from_document(document, project_root)


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _write_state(state: AutopilotState) -> None:
    state_path = state_path_for(state.project_root)
    state_directory = state_path.parent
    try:
        state_directory.mkdir(parents=True, exist_ok=True)
        resolved_directory = state_directory.resolve(strict=True)
    except OSError as error:
        raise ControlPlaneError(f"Cannot create Autopilot state directory: {error}")
    if not _is_within(resolved_directory, state.project_root):
        raise ControlPlaneError(
            "Autopilot state directory escaped the project during creation."
        )
    if state_path.is_symlink():
        raise ControlPlaneError("Autopilot state file must not be a symlink.")

    payload = (
        json.dumps(state.to_document(), indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{STATE_FILENAME}.",
            suffix=".tmp",
            dir=state_directory,
        )
        temporary_path = Path(temporary_name)
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        json.loads(temporary_path.read_text(encoding="utf-8"))
        os.replace(temporary_path, state_path)
        temporary_path = None
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ControlPlaneError(f"Cannot persist Autopilot state atomically: {error}")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _target_mode(action: str, current: AutopilotState) -> str:
    if action == "off":
        return "OFF"
    if action == "on" and current.mode == "OFF":
        return "ON_IDLE"
    if action == "arm" and current.mode == "ON_IDLE":
        return "ARMED"
    if action == "start" and current.mode in ("ARMED", "PAUSED"):
        return "RUNNING"
    if action == "pause" and current.mode == "RUNNING":
        return "PAUSED"

    idempotent = {
        "on": "ON_IDLE",
        "arm": "ARMED",
        "start": "RUNNING",
        "pause": "PAUSED",
        "off": "OFF",
    }
    if current.persisted and current.mode == idempotent[action]:
        return current.mode
    raise InvalidTransitionError(
        f"Action '{action}' is invalid while Autopilot is {current.mode}."
    )


def apply_action(
    project: str | os.PathLike[str] | Path,
    action: str,
    *,
    actor: str,
    reason: str,
    source: str = "cli",
    session_id: str | None = None,
    arm_validator: ArmValidator | None = None,
) -> tuple[AutopilotState, bool]:
    if action not in ACTIONS:
        raise ControlPlaneError(f"Unsupported Autopilot action: {action!r}.")
    actor = _require_text(actor, "actor", 256)
    reason = _require_text(reason, "reason", 1000)
    if source not in SOURCES:
        raise ControlPlaneError(f"Unsupported control source: {source!r}.")
    if session_id is not None:
        session_id = _require_text(session_id, "session_id", 256)

    current = load_state(project)
    target_mode = _target_mode(action, current)
    if target_mode == current.mode and current.persisted:
        return current, False
    if action == "arm":
        if arm_validator is None:
            raise ArmValidationRequiredError(
                "Arm is fail-closed until G0.7 validates artifacts, model routing, "
                "policy and permissions."
            )
        arm_validator(current.project_root, current)

    next_state = AutopilotState(
        project_root=current.project_root,
        mode=target_mode,
        revision=current.revision + 1,
        updated_at_utc=_utc_timestamp(),
        updated_by=actor,
        reason=reason,
        source=source,
        action=action,
        session_id=session_id,
        persisted=True,
    )
    _write_state(next_state)
    return next_state, True
