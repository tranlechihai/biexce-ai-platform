"""Runtime checks for a generated BIEXCE OpenCode + Slim config."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

from .jsonio import read_json
from .service import inspect_generated_config


EXPECTED_AGENT_MODES = {
    "orchestrator": "primary",
    "bx-plan": "all",
    "bx-explore": "all",
    "bx-code": "all",
    "bx-fix": "all",
    "bx-test": "all",
    "bx-review": "all",
}
ROLE_PROBE = r"""
import { pathToFileURL } from "node:url"
const bridge = await import(pathToFileURL(process.argv[1]).href)
const ids = ["orchestrator", "bx-plan", "bx-explore", "bx-code",
  "bx-fix", "bx-test", "bx-review"]
const agent = Object.fromEntries(ids.map((id) => [id,
  { mode: "subagent", hidden: true }]))
agent["bx-director"] = { mode: "primary", displayName: "BX-Director" }
const result = bridge.exposeUserFacingRoles({ agent })
console.log(JSON.stringify({ result, agent }))
"""


def _binary(root: Path, name: str) -> Path:
    suffix = ".cmd" if os.name == "nt" else ""
    return root / "node_modules" / ".bin" / f"{name}{suffix}"


def _run(binary: Path, arguments: list[str], root: Path) -> subprocess.CompletedProcess:
    command = [str(binary), *arguments]
    environment = os.environ.copy()
    environment.update(
        {
            "OPENCODE_CONFIG_DIR": str(root),
            "XDG_CONFIG_HOME": str(root / ".xdg-config"),
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
        timeout=30,
        check=False,
    )


def probe_role_access(root: Path) -> dict[str, object]:
    node = shutil.which("node")
    if not node:
        return {"name": "agent_registry", "ok": False, "detail": "Node.js missing"}
    bridge = root / "runtime" / "role-access.js"
    completed = _run(
        Path(node),
        ["--input-type=module", "--eval", ROLE_PROBE, str(bridge)],
        root,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {}
    agents = payload.get("agent") if isinstance(payload, dict) else None
    registry_ok = (
        completed.returncode == 0
        and payload.get("result", {}).get("ok") is True
        and isinstance(agents, dict)
        and set(agents) == set(EXPECTED_AGENT_MODES)
        and all(
            agents[name].get("mode") == mode
            and agents[name].get("hidden") is not True
            for name, mode in EXPECTED_AGENT_MODES.items()
        )
    )
    return {
        "name": "agent_registry",
        "ok": registry_ok,
        "detail": (
            "one visible BX-Director and six selectable specialists"
            if registry_ok
            else completed.stderr.strip() or "role access probe failed"
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
