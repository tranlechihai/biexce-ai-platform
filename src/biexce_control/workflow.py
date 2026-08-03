"""Autopilot workflow state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable

from .autopilot import ControlPlaneError, resolve_project_root


WORKFLOW_SCHEMA_ID = (
    "https://schemas.biexce.local/control-plane/"
    "autopilot-workflow-v1.schema.json"
)
WORKFLOW_SCHEMA_VERSION = 1
WORKFLOW_FILENAME = "AUTOPILOT_WORKFLOW.json"
WORKFLOW_RELATIVE_PATH = Path(".biexce") / "state" / WORKFLOW_FILENAME

PHASES = (
    "EXPLORE", "PLAN", "PLAN_REVIEW", "WAITING_GATE_1", "CODE", "TEST",
    "FIX", "TASK_REVIEW", "INTEGRATION_TEST", "INTEGRATION_REVIEW",
    "WAITING_GATE_2", "COMPLETE", "BLOCKED",
)
PHASE_AGENTS = {
    "EXPLORE": "bx-explore",
    "PLAN": "bx-plan",
    "PLAN_REVIEW": "bx-review",
    "CODE": "bx-code",
    "TEST": "bx-test",
    "FIX": "bx-fix",
    "TASK_REVIEW": "bx-review",
    "INTEGRATION_TEST": "bx-test",
    "INTEGRATION_REVIEW": "bx-review",
}
GATE_STATUSES = ("PENDING", "APPROVED")

_STATE_KEYS = {
    "$schema", "schema_version", "project_root", "phase", "revision",
    "current_task_id", "plan_revision", "fix_round", "gate_1",
    "gate_1_approved_by", "gate_1_approved_at_utc", "gate_2",
    "gate_2_approved_by", "gate_2_approved_at_utc", "last_agent",
    "last_result", "blocked_reason", "updated_at_utc", "updated_by",
}


class WorkflowStateError(ControlPlaneError):
    """The workflow state is missing, invalid, or cannot advance safely."""


@dataclass(frozen=True)
class WorkflowState:
    project_root: Path
    phase: str
    revision: int
    current_task_id: str | None
    plan_revision: int
    fix_round: int
    gate_1: str
    gate_1_approved_by: str | None
    gate_1_approved_at_utc: str | None
    gate_2: str
    gate_2_approved_by: str | None
    gate_2_approved_at_utc: str | None
    last_agent: str | None
    last_result: str | None
    blocked_reason: str | None
    updated_at_utc: str
    updated_by: str

    @property
    def expected_agent(self) -> str | None:
        return PHASE_AGENTS.get(self.phase)

    def to_document(self) -> dict[str, object]:
        return {
            "$schema": WORKFLOW_SCHEMA_ID,
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "project_root": str(self.project_root),
            "phase": self.phase,
            "revision": self.revision,
            "current_task_id": self.current_task_id,
            "plan_revision": self.plan_revision,
            "fix_round": self.fix_round,
            "gate_1": self.gate_1,
            "gate_1_approved_by": self.gate_1_approved_by,
            "gate_1_approved_at_utc": self.gate_1_approved_at_utc,
            "gate_2": self.gate_2,
            "gate_2_approved_by": self.gate_2_approved_by,
            "gate_2_approved_at_utc": self.gate_2_approved_at_utc,
            "last_agent": self.last_agent,
            "last_result": self.last_result,
            "blocked_reason": self.blocked_reason,
            "updated_at_utc": self.updated_at_utc,
            "updated_by": self.updated_by,
        }


GateValidator = Callable[[Path], None]


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((str(path), str(root))) == str(root)
    except ValueError:
        return False


def _optional_text(value: object, label: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise WorkflowStateError(f"{label} must be null or a non-empty string.")
    if len(value) > maximum:
        raise WorkflowStateError(f"{label} exceeds {maximum} characters.")
    return value


def _required_text(value: object, label: str, maximum: int) -> str:
    result = _optional_text(value, label, maximum)
    if result is None:
        raise WorkflowStateError(f"{label} must be a non-empty string.")
    return result


def _timestamp(value: object, label: str, *, optional: bool) -> str | None:
    text = _optional_text(value, label, 64) if optional else _required_text(
        value, label, 64
    )
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise WorkflowStateError(f"{label} is invalid: {error}")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise WorkflowStateError(f"{label} must include the UTC offset.")
    return text


def workflow_path_for(project: str | os.PathLike[str] | Path) -> Path:
    project_root = resolve_project_root(project)
    path = project_root / WORKFLOW_RELATIVE_PATH
    parent = path.parent
    while not parent.exists() and parent != project_root:
        parent = parent.parent
    resolved_parent = parent.resolve(strict=True)
    if not _is_within(resolved_parent, project_root):
        raise WorkflowStateError("Workflow state path escapes the project root.")
    if path.is_symlink():
        raise WorkflowStateError("Workflow state file must not be a symlink.")
    return path


def _state_from_document(document: object, project_root: Path) -> WorkflowState:
    if not isinstance(document, dict) or set(document) != _STATE_KEYS:
        raise WorkflowStateError("Workflow state properties mismatch.")
    if document["$schema"] != WORKFLOW_SCHEMA_ID:
        raise WorkflowStateError("Workflow schema identifier is invalid.")
    if document["schema_version"] != WORKFLOW_SCHEMA_VERSION:
        raise WorkflowStateError("Workflow schema version is unsupported.")

    stored_root = Path(
        _required_text(document["project_root"], "project_root", 4096)
    ).expanduser().resolve(strict=True)
    if not _same_path(stored_root, project_root):
        raise WorkflowStateError("Workflow state belongs to another project.")
    phase = document["phase"]
    if phase not in PHASES:
        raise WorkflowStateError(f"Unsupported workflow phase: {phase!r}.")
    revision = document["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise WorkflowStateError("revision must be an integer greater than zero.")
    current_task_id = _optional_text(
        document["current_task_id"], "current_task_id", 64
    )
    if current_task_id is not None and not re.fullmatch(r"t-[0-9]{3}", current_task_id):
        raise WorkflowStateError("current_task_id must match t-NNN.")
    plan_revision = document["plan_revision"]
    fix_round = document["fix_round"]
    for value, label, maximum in (
        (plan_revision, "plan_revision", 2),
        (fix_round, "fix_round", 3),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
            raise WorkflowStateError(f"{label} must be between 0 and {maximum}.")

    gate_1 = document["gate_1"]
    gate_2 = document["gate_2"]
    if gate_1 not in GATE_STATUSES or gate_2 not in GATE_STATUSES:
        raise WorkflowStateError("Gate status must be PENDING or APPROVED.")
    gate_1_by = _optional_text(document["gate_1_approved_by"], "gate_1_approved_by", 256)
    gate_1_at = _timestamp(document["gate_1_approved_at_utc"], "gate_1_approved_at_utc", optional=True)
    gate_2_by = _optional_text(document["gate_2_approved_by"], "gate_2_approved_by", 256)
    gate_2_at = _timestamp(document["gate_2_approved_at_utc"], "gate_2_approved_at_utc", optional=True)
    if (gate_1 == "APPROVED") != (gate_1_by is not None and gate_1_at is not None):
        raise WorkflowStateError("Gate 1 approval metadata is inconsistent.")
    if (gate_2 == "APPROVED") != (gate_2_by is not None and gate_2_at is not None):
        raise WorkflowStateError("Gate 2 approval metadata is inconsistent.")

    return WorkflowState(
        project_root=project_root,
        phase=phase,
        revision=revision,
        current_task_id=current_task_id,
        plan_revision=plan_revision,
        fix_round=fix_round,
        gate_1=gate_1,
        gate_1_approved_by=gate_1_by,
        gate_1_approved_at_utc=gate_1_at,
        gate_2=gate_2,
        gate_2_approved_by=gate_2_by,
        gate_2_approved_at_utc=gate_2_at,
        last_agent=_optional_text(document["last_agent"], "last_agent", 64),
        last_result=_optional_text(document["last_result"], "last_result", 128),
        blocked_reason=_optional_text(document["blocked_reason"], "blocked_reason", 1000),
        updated_at_utc=_timestamp(document["updated_at_utc"], "updated_at_utc", optional=False) or "",
        updated_by=_required_text(document["updated_by"], "updated_by", 256),
    )


def load_workflow(
    project: str | os.PathLike[str] | Path, *, required: bool = False
) -> WorkflowState | None:
    project_root = resolve_project_root(project)
    path = workflow_path_for(project_root)
    if not path.exists():
        if required:
            raise WorkflowStateError(
                "Autopilot workflow is not initialized; run 'biexce auto start'."
            )
        return None
    if not path.is_file():
        raise WorkflowStateError(f"Workflow state is not a file: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorkflowStateError(f"Workflow state is unreadable: {error}")
    return _state_from_document(document, project_root)


def _write_workflow(state: WorkflowState) -> None:
    path = workflow_path_for(state.project_root)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    resolved_directory = directory.resolve(strict=True)
    if not _is_within(resolved_directory, state.project_root):
        raise WorkflowStateError("Workflow directory escapes the project root.")
    payload = (json.dumps(state.to_document(), indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{WORKFLOW_FILENAME}.", suffix=".tmp", dir=directory
        )
        temporary_path = Path(name)
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
        os.replace(temporary_path, path)
        temporary_path = None
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorkflowStateError(f"Cannot persist workflow state atomically: {error}")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def initialize_workflow(
    project: str | os.PathLike[str] | Path, *, actor: str
) -> tuple[WorkflowState, bool]:
    project_root = resolve_project_root(project)
    existing = load_workflow(project_root)
    if existing is not None:
        return existing, False
    actor = _required_text(actor, "actor", 256)
    state = WorkflowState(
        project_root=project_root,
        phase="EXPLORE",
        revision=1,
        current_task_id=None,
        plan_revision=0,
        fix_round=0,
        gate_1="PENDING",
        gate_1_approved_by=None,
        gate_1_approved_at_utc=None,
        gate_2="PENDING",
        gate_2_approved_by=None,
        gate_2_approved_at_utc=None,
        last_agent=None,
        last_result="WORKFLOW_INITIALIZED",
        blocked_reason=None,
        updated_at_utc=_utc_timestamp(),
        updated_by=actor,
    )
    _write_workflow(state)
    return state, True


def _task_dependencies(path: Path) -> tuple[str, ...]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?mi)^Depends on:\s*(.+?)(?:\s*[·|]\s*Effort:|$)", text)
    if not match or match.group(1).strip().lower() == "none":
        return ()
    return tuple(re.findall(r"t-[0-9]{3}", match.group(1)))


def _next_ready_task(project_root: Path) -> tuple[str | None, bool]:
    state_path = project_root / ".biexce" / "state" / "PROJECT_STATE.json"
    try:
        document = json.loads(state_path.read_text(encoding="utf-8"))
        tasks = document["tasks"]
        if not isinstance(tasks, list) or not tasks:
            raise ValueError("PROJECT_STATE tasks must be non-empty.")
        done = {
            item["id"]
            for item in tasks
            if isinstance(item, dict) and item.get("status") == "done"
        }
        pending = [
            item
            for item in tasks
            if isinstance(item, dict) and item.get("status") == "backlog"
        ]
        if not pending:
            all_done = all(
                isinstance(item, dict) and item.get("status") == "done"
                for item in tasks
            )
            return None, all_done
        for item in pending:
            task_id = item.get("id")
            if not isinstance(task_id, str):
                continue
            dependencies = _task_dependencies(
                project_root / ".biexce" / "tasks" / f"{task_id}.md"
            )
            if all(dependency in done for dependency in dependencies):
                return task_id, False
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError) as error:
        raise WorkflowStateError(f"Cannot select the next task: {error}")
    raise WorkflowStateError("No backlog task is ready; dependency DAG is blocked.")


def _require_final_reports(project_root: Path) -> None:
    project_state_path = project_root / ".biexce" / "state" / "PROJECT_STATE.json"
    try:
        project_state = json.loads(project_state_path.read_text(encoding="utf-8"))
        tasks = project_state["tasks"]
        if project_state["stage"] not in {"B4", "B5"}:
            raise WorkflowStateError("Gate 2 requires PROJECT_STATE stage B4 or B5.")
        if not isinstance(tasks, list) or not tasks or not all(
            isinstance(task, dict) and task.get("status") == "done" for task in tasks
        ):
            raise WorkflowStateError("Gate 2 requires every task to be done.")
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError) as error:
        raise WorkflowStateError(f"Gate 2 cannot validate PROJECT_STATE: {error}")
    reports = project_root / ".biexce" / "reports"
    for name in ("INTEGRATION_REPORT.md", "FINAL_REPORT.md"):
        path = reports / name
        if path.is_symlink() or not path.is_file():
            raise WorkflowStateError(f"Gate 2 requires {path}.")
        try:
            if not path.read_text(encoding="utf-8").strip():
                raise WorkflowStateError(f"Gate 2 report is empty: {path}")
        except (OSError, UnicodeError) as error:
            raise WorkflowStateError(f"Gate 2 cannot read {path}: {error}")


def approve_gate(
    project: str | os.PathLike[str] | Path,
    gate: int,
    *,
    actor: str,
    gate_1_validator: GateValidator | None = None,
) -> WorkflowState:
    state = load_workflow(project, required=True)
    assert state is not None
    actor = _required_text(actor, "actor", 256)
    now = _utc_timestamp()
    if gate == 1:
        if state.phase != "WAITING_GATE_1" or state.gate_1 != "PENDING":
            raise WorkflowStateError(
                f"Gate 1 approval is invalid while workflow phase is {state.phase}."
            )
        if gate_1_validator is None:
            raise WorkflowStateError("Gate 1 validator is required.")
        gate_1_validator(state.project_root)
        task_id, all_done = _next_ready_task(state.project_root)
        phase = "INTEGRATION_TEST" if all_done else "CODE"
        if not all_done and task_id is None:
            raise WorkflowStateError("Gate 1 found no executable task.")
        next_state = replace(
            state,
            phase=phase,
            revision=state.revision + 1,
            current_task_id=task_id,
            gate_1="APPROVED",
            gate_1_approved_by=actor,
            gate_1_approved_at_utc=now,
            last_agent=None,
            last_result="GATE_1_APPROVED",
            blocked_reason=None,
            updated_at_utc=now,
            updated_by=actor,
        )
    elif gate == 2:
        if state.phase != "WAITING_GATE_2" or state.gate_2 != "PENDING":
            raise WorkflowStateError(
                f"Gate 2 approval is invalid while workflow phase is {state.phase}."
            )
        _require_final_reports(state.project_root)
        next_state = replace(
            state,
            phase="COMPLETE",
            revision=state.revision + 1,
            current_task_id=None,
            gate_2="APPROVED",
            gate_2_approved_by=actor,
            gate_2_approved_at_utc=now,
            last_agent=None,
            last_result="GATE_2_APPROVED",
            blocked_reason=None,
            updated_at_utc=now,
            updated_by=actor,
        )
    else:
        raise WorkflowStateError("Gate must be 1 or 2.")
    _write_workflow(next_state)
    return next_state


def workflow_payload(state: WorkflowState | None) -> dict[str, object] | None:
    if state is None:
        return None
    return {
        "state_path": str(workflow_path_for(state.project_root)),
        "phase": state.phase,
        "revision": state.revision,
        "expected_agent": state.expected_agent,
        "current_task_id": state.current_task_id,
        "plan_revision": state.plan_revision,
        "fix_round": state.fix_round,
        "gate_1": state.gate_1,
        "gate_2": state.gate_2,
        "last_agent": state.last_agent,
        "last_result": state.last_result,
        "blocked_reason": state.blocked_reason,
        "updated_at_utc": state.updated_at_utc,
        "updated_by": state.updated_by,
    }
