"""Runtime checks for a generated BIEXCE OpenCode + Slim config."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from .jsonio import read_json
from .service import inspect_generated_config


def _binary(root: Path, name: str) -> Path:
    suffix = ".cmd" if os.name == "nt" else ""
    return root / "node_modules" / ".bin" / f"{name}{suffix}"


def _run(binary: Path, arguments: list[str], root: Path) -> subprocess.CompletedProcess:
    command = [str(binary), *arguments]
    environment = os.environ.copy()
    environment.update(
        {
            "OPENCODE_CONFIG_DIR": str(root),
            "OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS": "true",
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
            "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1",
        }
    )
    return subprocess.run(
        command,
        shell=os.name == "nt",
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def run_generated_doctor(config_dir: str | Path) -> dict[str, object]:
    status = inspect_generated_config(config_dir)
    root = Path(config_dir).expanduser().resolve()
    if not status["ok"] or not status["ready_to_run"]:
        status["structural_ok"] = status["ok"]
        status["ok"] = False
        status["runtime_checks"] = []
        return status

    compatibility = read_json(root / "compatibility.json")
    opencode = _binary(root, "opencode")
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
