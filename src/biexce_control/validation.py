"""Gate 0 artifact, policy, permission, and routing validator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Callable

from .autopilot import AutopilotState, ControlPlaneError, resolve_project_root
from .model_routing import (
    AGENTS,
    ModelRoutingError,
    discover_models,
    load_applied_routing,
    opencode_config_root,
    validate_routing_document,
)


TASK_STATUSES = {
    "backlog",
    "planning",
    "coding",
    "testing",
    "fixing",
    "reviewing",
    "done",
    "escalated",
}
ACTIVE_STATUSES = {"planning", "coding", "testing", "fixing", "reviewing"}
OWNER_ROLES = set(AGENTS)
TASK_ID_PATTERN = re.compile(r"^t-[0-9]{3}$")


class GateValidationError(ControlPlaneError):
    """One or more mandatory Gate 0 checks failed."""

    def __init__(self, report: "ValidationReport") -> None:
        self.report = report
        failures = [check.message for check in report.checks if not check.ok]
        super().__init__("Gate 0 validation failed: " + "; ".join(failures))


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    ok: bool
    message: str

    def to_document(self) -> dict[str, object]:
        return {"name": self.name, "ok": self.ok, "message": self.message}


@dataclass(frozen=True)
class ValidationReport:
    project_root: Path
    checks: tuple[ValidationCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_document(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "project_root": str(self.project_root),
            "checks": [check.to_document() for check in self.checks],
        }


def _read_text(path: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"{label} is empty: {path}")
    return text


def _field(text: str, label: str) -> str | None:
    match = re.search(rf"(?mi)^{re.escape(label)}:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else None


def _scope_item(value: str) -> str:
    trimmed = value.strip()
    inline = re.fullmatch(r"(`+)(.*?)\1", trimmed, flags=re.DOTALL)
    return (inline.group(2).strip() if inline else trimmed).replace("\\", "/")


def _parse_task(path: Path) -> tuple[dict[str, object] | None, list[str]]:
    errors: list[str] = []
    try:
        text = _read_text(path, "task")
    except (OSError, UnicodeError, ValueError) as error:
        return None, [str(error)]
    task_id = path.stem
    title = re.search(rf"(?m)^#\s+{re.escape(task_id)}\s+[—-]\s+(.+)$", text)
    for heading in (
        "## 1. Objective",
        "## 2. Context tối thiểu",
        "## 3. Acceptance criteria",
        "## 4. Boundaries",
    ):
        if heading not in text:
            errors.append(f"{task_id}: missing heading '{heading}'.")
    if not re.search(r"(?m)^- \[ \] .+", text):
        errors.append(f"{task_id}: acceptance criteria are missing.")
    verify_match = re.search(r"(?m)^Verify:\s*`([^`]+)`\s*$", text)
    if not verify_match:
        errors.append(f"{task_id}: Verify command is missing.")
    elif re.match(r"(?i)^N/?A\b", verify_match.group(1).strip()):
        errors.append(f"{task_id}: Verify must be an executable command, not N/A.")
    owner = _field(text, "Owner role")
    writable = _field(text, "Writable files")
    read_only = _field(text, "Read-only inputs")
    out_of_scope = _field(text, "Out-of-scope")
    dependency_line = _field(text, "Depends on")
    effort = None
    dependencies: list[str] = []
    if dependency_line:
        parts = re.split(r"\s*[·|]\s*Effort:\s*", dependency_line, maxsplit=1)
        dependency_text = parts[0].strip()
        effort = parts[1].strip() if len(parts) == 2 else None
        if dependency_text.lower() != "none":
            dependencies = re.findall(r"t-[0-9]{3}", dependency_text)
            normalized = re.sub(r"[\s,]+", "", dependency_text)
            if normalized != "".join(dependencies):
                errors.append(f"{task_id}: dependency syntax is invalid.")
    else:
        errors.append(f"{task_id}: Depends on is missing.")
    if owner not in OWNER_ROLES:
        errors.append(f"{task_id}: owner role is invalid or missing.")
    if owner == "bx-test":
        scopes = [] if (writable or "").strip().lower() == "none" else [
            _scope_item(item)
            for item in (writable or "").split(",")
            if item.strip()
        ]
        if any(
            not item.startswith(".biexce/reports/") or ".." in item.split("/")
            for item in scopes
        ):
            errors.append(
                f"{task_id}: bx-test ownership is verification-only; Writable "
                "files must be none or paths under .biexce/reports/."
            )
    for label, value in (
        ("Writable files", writable),
        ("Read-only inputs", read_only),
        ("Out-of-scope", out_of_scope),
    ):
        if not value:
            errors.append(f"{task_id}: {label} is missing.")
    if effort not in {"S", "M", "L"}:
        errors.append(f"{task_id}: Effort must be S, M, or L.")
    return (
        {
            "id": task_id,
            "title": title.group(1).strip() if title else "",
            "owner": owner,
            "writable": writable,
            "read_only": read_only,
            "out_of_scope": out_of_scope,
            "dependencies": dependencies,
            "effort": effort,
        },
        errors,
    )


def _dependency_errors(tasks: dict[str, dict[str, object]]) -> list[str]:
    errors: list[str] = []
    for task_id, task in tasks.items():
        for dependency in task["dependencies"]:
            if dependency == task_id:
                errors.append(f"{task_id}: cannot depend on itself.")
            elif dependency not in tasks:
                errors.append(f"{task_id}: unknown dependency {dependency}.")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            errors.append(f"Task dependency cycle includes {task_id}.")
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in tasks[task_id]["dependencies"]:
            if dependency in tasks:
                visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)
    return sorted(set(errors))


def _project_artifact_checks(project: Path) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    artifact_root = project / ".biexce"
    try:
        brief = _read_text(artifact_root / "PROJECT_BRIEF.md", "PROJECT_BRIEF")
        project_id = _field(brief, "Project ID")
        if not project_id:
            raise ValueError("PROJECT_BRIEF must define Project ID.")
        checks.append(ValidationCheck("project_brief", True, "PROJECT_BRIEF valid"))
    except (OSError, UnicodeError, ValueError) as error:
        project_id = None
        checks.append(ValidationCheck("project_brief", False, str(error)))
    wip_limit = 1
    try:
        plan = _read_text(artifact_root / "MASTER_PLAN.md", "MASTER_PLAN")
        required = {
            "Fix cap": "3",
            "Reports path": ".biexce/reports",
            "Git/deploy": "forbidden",
        }
        wip_text = _field(plan, "WIP limit")
        try:
            wip_limit = int(wip_text or "")
        except ValueError as error:
            raise ValueError("MASTER_PLAN WIP limit must be an integer.") from error
        if not 1 <= wip_limit <= 4:
            raise ValueError("MASTER_PLAN WIP limit must be between 1 and 4.")
        for label, expected in required.items():
            if (_field(plan, label) or "").lower() != expected.lower():
                raise ValueError(f"MASTER_PLAN requires '{label}: {expected}'.")
        if "Gate 1" not in plan or "Gate 2" not in plan:
            raise ValueError("MASTER_PLAN must preserve Gate 1 and Gate 2.")
        checks.append(ValidationCheck("master_plan", True, "MASTER_PLAN valid"))
    except (OSError, UnicodeError, ValueError) as error:
        plan = ""
        checks.append(ValidationCheck("master_plan", False, str(error)))

    task_root = artifact_root / "tasks"
    task_files = sorted(task_root.glob("t-*.md")) if task_root.is_dir() else []
    tasks: dict[str, dict[str, object]] = {}
    task_errors: list[str] = []
    if not 1 <= len(task_files) <= 50:
        task_errors.append(
            f"Plan must contain 1-50 task files; found {len(task_files)}."
        )
    for path in task_files:
        if not TASK_ID_PATTERN.fullmatch(path.stem):
            task_errors.append(f"Invalid task filename: {path.name}")
            continue
        task, errors = _parse_task(path)
        task_errors.extend(errors)
        if task is not None:
            tasks[path.stem] = task
    task_errors.extend(_dependency_errors(tasks))
    plan_ids = set(re.findall(r"(?m)^-\s+(t-[0-9]{3})\b", plan))
    plan_ids.update(
        re.findall(r"(?m)^\|\s*(t-[0-9]{3})\s*\|", plan)
    )
    if plan and plan_ids != set(tasks):
        task_errors.append(
            "MASTER_PLAN task IDs do not match task files; "
            f"plan={sorted(plan_ids)}, files={sorted(tasks)}."
        )
    checks.append(
        ValidationCheck(
            "task_contracts",
            not task_errors,
            "3-5 task contracts and DAG valid"
            if not task_errors
            else " | ".join(task_errors),
        )
    )

    reports = artifact_root / "reports"
    reports_ok = reports.is_dir() and not reports.is_symlink()
    checks.append(
        ValidationCheck(
            "reports_path",
            reports_ok,
            "reports path valid" if reports_ok else f"Missing reports path: {reports}",
        )
    )

    state_path = artifact_root / "state" / "PROJECT_STATE.json"
    state_errors: list[str] = []
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or set(state) != {
            "project",
            "stage",
            "updated",
            "tasks",
        }:
            raise ValueError("PROJECT_STATE properties are invalid.")
        if project_id and state["project"] != project_id:
            state_errors.append("PROJECT_STATE project differs from PROJECT_BRIEF.")
        if state["stage"] not in {"B1", "B2", "B3", "B4", "B5"}:
            state_errors.append("PROJECT_STATE stage must be B1..B5.")
        try:
            datetime.fromisoformat(str(state["updated"]).replace("Z", "+00:00"))
        except ValueError:
            state_errors.append("PROJECT_STATE updated timestamp is invalid.")
        state_tasks = state["tasks"]
        if not isinstance(state_tasks, list) or not state_tasks:
            state_errors.append("PROJECT_STATE tasks must be non-empty.")
            state_tasks = []
        state_ids: list[str] = []
        active = 0
        for item in state_tasks:
            if not isinstance(item, dict) or set(item) != {
                "id",
                "title",
                "status",
                "round",
                "agent",
            }:
                state_errors.append("PROJECT_STATE contains an invalid task entry.")
                continue
            state_ids.append(item["id"])
            matching_task = tasks.get(item["id"])
            if matching_task and item["title"] != matching_task["title"]:
                state_errors.append(
                    f"{item['id']}: PROJECT_STATE title differs from task file."
                )
            if item["status"] not in TASK_STATUSES:
                state_errors.append(f"{item['id']}: state status is invalid.")
            if item["status"] in ACTIVE_STATUSES:
                active += 1
            if (
                isinstance(item["round"], bool)
                or not isinstance(item["round"], int)
                or not 0 <= item["round"] <= 3
            ):
                state_errors.append(f"{item['id']}: round must be 0..3.")
            if item["agent"] is not None and item["agent"] not in OWNER_ROLES:
                state_errors.append(f"{item['id']}: state agent is invalid.")
        if len(state_ids) != len(set(state_ids)) or set(state_ids) != set(tasks):
            state_errors.append("PROJECT_STATE task IDs differ from task files.")
        if active > wip_limit:
            state_errors.append(
                f"PROJECT_STATE active task count {active} exceeds WIP={wip_limit}."
            )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, KeyError) as error:
        state_errors.append(str(error))
    checks.append(
        ValidationCheck(
            "project_state",
            not state_errors,
            f"PROJECT_STATE matches tasks, WIP<={wip_limit}, fix cap<=3"
            if not state_errors
            else " | ".join(state_errors),
        )
    )
    return checks


def _runtime_contract_checks(opencode_root: Path) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    permission_errors: list[str] = []
    for agent in AGENTS:
        path = opencode_root / "agents" / f"{agent}.md"
        try:
            header = _read_text(path, agent).split("---", 2)[1]
            if not re.search(r"(?m)^\s{2}task:\s*deny\s*$", header):
                permission_errors.append(f"{agent}: task permission is not deny.")
        except (OSError, UnicodeError, ValueError, IndexError) as error:
            permission_errors.append(str(error))
    checks.append(
        ValidationCheck(
            "static_permissions",
            not permission_errors,
            "all seven agents deny nested task statically"
            if not permission_errors
            else " | ".join(permission_errors),
        )
    )
    plugin_path = opencode_root / "plugins" / "biexce-control.js"
    plugin_ok = plugin_path.is_file() and not plugin_path.is_symlink()
    checks.append(
        ValidationCheck(
            "runtime_guard",
            plugin_ok,
            f"runtime guard present: {plugin_path}"
            if plugin_ok
            else f"runtime guard missing: {plugin_path}",
        )
    )
    package_path = opencode_root / "package.json"
    dependency_ok = False
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        dependency_ok = (
            isinstance(package, dict)
            and isinstance(package.get("dependencies"), dict)
            and package["dependencies"].get("@opencode-ai/plugin") == "1.18.4"
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        dependency_ok = False
    checks.append(
        ValidationCheck(
            "runtime_dependency",
            dependency_ok,
            "@opencode-ai/plugin 1.18.4 is pinned"
            if dependency_ok
            else f"Missing runtime dependency in {package_path}",
        )
    )
    return checks


def validate_project(
    project: str | os.PathLike[str] | Path,
    *,
    config_home: str | os.PathLike[str] | Path | None = None,
    opencode_root: str | os.PathLike[str] | Path | None = None,
) -> ValidationReport:
    project_root = resolve_project_root(project)
    checks = _project_artifact_checks(project_root)
    runtime_report = validate_runtime(
        project_root,
        config_home=config_home,
        opencode_root=opencode_root,
    )
    checks.extend(runtime_report.checks)
    return ValidationReport(project_root, tuple(checks))


def validate_runtime(
    project: str | os.PathLike[str] | Path,
    *,
    config_home: str | os.PathLike[str] | Path | None = None,
    opencode_root: str | os.PathLike[str] | Path | None = None,
) -> ValidationReport:
    """Validate only prerequisites required before B1/B2 can run."""
    project_root = resolve_project_root(project)
    runtime_root = opencode_config_root(opencode_root)
    checks = _runtime_contract_checks(runtime_root)
    routing_errors: list[str] = []
    try:
        applied = load_applied_routing(config_home)
        models, warnings = discover_models(runtime_root, include_runtime=False)
        routing_errors.extend(
            validate_routing_document(
                applied["routing"], available_models=models or None
            )
        )
        if warnings and not models:
            routing_errors.extend(warnings)
    except ModelRoutingError as error:
        routing_errors.append(str(error))
    checks.append(
        ValidationCheck(
            "model_routing",
            not routing_errors,
            "seven explicit applied bindings pass policy"
            if not routing_errors
            else " | ".join(routing_errors),
        )
    )
    return ValidationReport(project_root, tuple(checks))


def require_project_valid(
    project: str | os.PathLike[str] | Path,
    *,
    config_home: str | os.PathLike[str] | Path | None = None,
    opencode_root: str | os.PathLike[str] | Path | None = None,
) -> ValidationReport:
    report = validate_project(
        project, config_home=config_home, opencode_root=opencode_root
    )
    if not report.ok:
        raise GateValidationError(report)
    return report


def require_runtime_valid(
    project: str | os.PathLike[str] | Path,
    *,
    config_home: str | os.PathLike[str] | Path | None = None,
    opencode_root: str | os.PathLike[str] | Path | None = None,
) -> ValidationReport:
    report = validate_runtime(
        project, config_home=config_home, opencode_root=opencode_root
    )
    if not report.ok:
        raise GateValidationError(report)
    return report


def arm_validator(
    *,
    config_home: str | os.PathLike[str] | Path | None = None,
    opencode_root: str | os.PathLike[str] | Path | None = None,
) -> Callable[[Path, AutopilotState], None]:
    def validate(project_root: Path, _state: AutopilotState) -> None:
        require_runtime_valid(
            project_root, config_home=config_home, opencode_root=opencode_root
        )

    return validate
