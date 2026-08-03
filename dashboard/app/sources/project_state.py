"""Read dashboard flow data from exact project-local BIEXCE state files."""

import json
from pathlib import Path
import re

from .base import PanelSnapshot, snapshot


ACTIVE_TASK_STATUSES = {
    "planning", "coding", "testing", "fixing", "reviewing"
}
TASK_STATUSES = ACTIVE_TASK_STATUSES | {"backlog", "done", "escalated"}
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


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing regular file {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _validate_project_state(value: dict) -> dict:
    project = value.get("project")
    stage = value.get("stage")
    updated = value.get("updated")
    tasks = value.get("tasks")
    if not isinstance(project, str) or not project.strip():
        raise ValueError("PROJECT_STATE project is invalid")
    if not isinstance(stage, str) or not re.fullmatch(r"B[1-5]", stage):
        raise ValueError("PROJECT_STATE stage is invalid")
    if not isinstance(updated, str) or not updated:
        raise ValueError("PROJECT_STATE updated is invalid")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("PROJECT_STATE tasks are missing")

    normalized = []
    active = 0
    seen = set()
    for item in tasks:
        if not isinstance(item, dict):
            raise ValueError("PROJECT_STATE task is invalid")
        task_id = item.get("id")
        title = item.get("title")
        status = item.get("status")
        round_number = item.get("round")
        agent = item.get("agent")
        if not isinstance(task_id, str) or not re.fullmatch(r"t-[0-9]{3}", task_id):
            raise ValueError("PROJECT_STATE task id is invalid")
        if task_id in seen:
            raise ValueError("PROJECT_STATE contains duplicate task ids")
        seen.add(task_id)
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"{task_id} title is invalid")
        if status not in TASK_STATUSES:
            raise ValueError(f"{task_id} status is invalid")
        if isinstance(round_number, bool) or not isinstance(round_number, int):
            raise ValueError(f"{task_id} round is invalid")
        if round_number < 0 or round_number > 3:
            raise ValueError(f"{task_id} round exceeds the fix cap")
        if agent is not None and (
            not isinstance(agent, str) or not agent.startswith("bx-")
        ):
            raise ValueError(f"{task_id} agent is invalid")
        if status in ACTIVE_TASK_STATUSES:
            active += 1
        normalized.append(
            {
                "id": task_id,
                "title": title,
                "status": status,
                "round": round_number,
                "agent": agent,
            }
        )
    if active > 1:
        raise ValueError("PROJECT_STATE violates WIP=1")
    return {
        "project": project,
        "stage": stage,
        "updated": updated,
        "tasks": normalized,
    }


def _optional_state(path: Path, fields: tuple[str, ...]) -> dict | None:
    if not path.exists():
        return None
    value = _read_json(path)
    return {field: value.get(field) for field in fields}


class ProjectStateSource:
    name = "biexce-project-state"

    def __init__(self, roots: tuple[Path, ...], machine: str):
        self.roots = roots
        self.machine = machine

    async def read(self) -> PanelSnapshot:
        projects = []
        errors = []
        observed = None
        for configured_root in self.roots:
            label = configured_root.name or "project"
            try:
                root = configured_root.resolve(strict=True)
                state_dir = root / ".biexce" / "state"
                project = _validate_project_state(
                    _read_json(state_dir / "PROJECT_STATE.json")
                )
                project["machine"] = self.machine
                project["autopilot"] = _optional_state(
                    state_dir / "AUTOPILOT_CONTROL.json",
                    ("mode", "revision", "session_id", "updated_at_utc"),
                )
                workflow = _optional_state(
                    state_dir / "AUTOPILOT_WORKFLOW.json",
                    (
                        "phase", "revision", "current_task_id", "fix_round",
                        "gate_1", "gate_2", "last_agent", "last_result",
                        "blocked_reason", "updated_at_utc",
                    ),
                )
                if workflow:
                    workflow["expected_agent"] = PHASE_AGENTS.get(
                        workflow.get("phase")
                    )
                project["workflow"] = workflow
                projects.append(project)
                if observed is None or project["updated"] > observed:
                    observed = project["updated"]
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                errors.append(f"{label}: {error}")

        if projects and not errors:
            status = "ok"
            message = None
        elif projects:
            status = "degraded"
            message = "; ".join(errors)
        else:
            status = "unavailable" if self.roots else "degraded"
            message = (
                "; ".join(errors)
                if errors
                else "Set BIEXCE_PROJECT_ROOTS to one or more BIEXCE projects."
            )
        return snapshot(
            projects,
            source=self.name,
            mode="live",
            machine=self.machine,
            status=status,
            message=message,
            observed_at=observed,
        )
