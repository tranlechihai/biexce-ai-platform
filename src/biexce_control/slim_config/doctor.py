"""Runtime checks for a generated BIEXCE OpenCode + Slim config."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from .jsonio import read_json
from .service import inspect_generated_config


EXPECTED_AGENT_MODES = {
    "bx-director": "primary",
    "bx-plan": "all",
    "bx-explore": "all",
    "bx-code": "all",
    "bx-fix": "all",
    "bx-test": "all",
    "bx-review": "all",
}

RUNTIME_COMMAND_TIMEOUT_SECONDS = 120


def _binary(root: Path, name: str) -> Path:
    suffix = ".cmd" if os.name == "nt" else ""
    return root / "node_modules" / ".bin" / f"{name}{suffix}"


def _opencode_launcher(root: Path) -> Path:
    suffix = ".cmd" if os.name == "nt" else ""
    return root / "bin" / f"biexce-opencode{suffix}"


def _run(binary: Path, arguments: list[str], root: Path) -> subprocess.CompletedProcess:
    command = [str(binary), *arguments]
    xdg_roots = {
        "XDG_CONFIG_HOME": root / ".xdg-config",
        "XDG_CACHE_HOME": root / ".xdg-cache",
        "XDG_DATA_HOME": root / ".xdg-data",
        "XDG_STATE_HOME": root / ".xdg-state",
    }
    for directory in xdg_roots.values():
        directory.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "OPENCODE_CONFIG_DIR": str(root),
            **{name: str(path) for name, path in xdg_roots.items()},
            "OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS": "true",
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
            "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1",
        }
    )
    return subprocess.run(
        command,
        shell=(
            os.name == "nt"
            and binary.suffix.lower() in {".cmd", ".bat"}
        ),
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=RUNTIME_COMMAND_TIMEOUT_SECONDS,
        check=False,
    )


def _debug_agent(root: Path, agent_id: str) -> tuple[dict, str]:
    completed = _run(
        _opencode_launcher(root),
        ["debug", "agent", agent_id],
        root,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {}
    detail = completed.stderr.strip() or completed.stdout.strip()
    return payload if completed.returncode == 0 else {}, detail


def probe_role_access(root: Path) -> dict[str, object]:
    failures: list[str] = []
    for agent_id, expected_mode in EXPECTED_AGENT_MODES.items():
        document, detail = _debug_agent(root, agent_id)
        if (
            document.get("name") != agent_id
            or document.get("mode") != expected_mode
            or document.get("hidden") is True
        ):
            failures.append(f"{agent_id}: {detail or 'not registered'}")

    internal, detail = _debug_agent(root, "orchestrator")
    if not (
        internal.get("name") == "orchestrator"
        and internal.get("mode") == "subagent"
        and internal.get("hidden") is True
    ):
        failures.append(f"orchestrator: {detail or 'not hidden'}")

    return {
        "name": "agent_registry",
        "ok": not failures,
        "detail": (
            "exactly seven visible BIEXCE roles; internal orchestrator hidden"
            if not failures
            else " | ".join(failures)
        ),
    }


def run_generated_doctor(config_dir: str | Path) -> dict[str, object]:
    status = inspect_generated_config(config_dir)
    root = Path(config_dir).expanduser().resolve()
    if not status["ok"] or not status["ready_to_run"]:
        status["structural_ok"] = status["ok"]
        status["ok"] = False
        status["runtime_checks"] = []
        return status

    compatibility = read_json(root / "compatibility.json")
    opencode = _opencode_launcher(root)
    slim = _binary(root, "oh-my-opencode-slim")
    runtime_checks: list[dict[str, object]] = []
    if not opencode.is_file() or not slim.is_file():
        status["ready_to_run"] = False
        status["runtime_checks"] = [
            {"name": "binaries", "ok": False, "detail": "Local CLI binaries missing"}
        ]
        return status

    try:
        version = _run(opencode, ["--version"], root)
        actual_version = version.stdout.strip()
        version_ok = (
            version.returncode == 0
            and actual_version == compatibility["opencode"]["prototype_cli"]
        )
        runtime_checks.append(
            {"name": "opencode_version", "ok": version_ok, "detail": actual_version}
        )
        doctor = _run(slim, ["doctor", "--json"], root)
        try:
            document = json.loads(doctor.stdout)
        except json.JSONDecodeError:
            document = {}
        doctor_ok = doctor.returncode == 0 and document.get("ok") is True
        runtime_checks.append(
            {
                "name": "slim_doctor",
                "ok": doctor_ok,
                "detail": "PASS" if doctor_ok else doctor.stderr.strip() or "invalid JSON",
            }
        )
        runtime_checks.append(probe_role_access(root))
    except (OSError, subprocess.SubprocessError) as error:
        runtime_checks.append(
            {"name": "runtime", "ok": False, "detail": str(error)}
        )

    runtime_ok = bool(runtime_checks) and all(
        bool(check["ok"]) for check in runtime_checks
    )
    status["runtime_checks"] = runtime_checks
    status["ready_to_run"] = bool(status["ready_to_run"] and runtime_ok)
    status["ok"] = bool(status["ok"] and runtime_ok)
    return status
