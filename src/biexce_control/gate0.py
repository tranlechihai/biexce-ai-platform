"""Executable Gate 0 acceptance matrix with explicit infrastructure blockers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .autopilot import ControlPlaneError
from .model_routing import (
    LOCAL_MODEL,
    opencode_config_root,
    resolve_config_reference,
    routing_status,
)
from .validation import validate_project


MatrixStatus = Literal["PASS", "FAIL", "BLOCKED"]


@dataclass(frozen=True)
class MatrixCheck:
    layer: str
    name: str
    status: MatrixStatus
    detail: str

    def to_document(self) -> dict[str, str]:
        return {
            "layer": self.layer,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }


def _opencode_version(root: Path) -> MatrixCheck:
    executable = shutil.which("opencode")
    if executable is None:
        return MatrixCheck("user-dev", "opencode_1_18", "BLOCKED", "CLI not found")
    environment = os.environ.copy()
    environment["OPENCODE_CONFIG_DIR"] = str(root)
    environment["OPENCODE_DISABLE_PROJECT_CONFIG"] = "1"
    try:
        result = subprocess.run(
            [executable, "--version"],
            cwd=tempfile.gettempdir(),
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return MatrixCheck("user-dev", "opencode_1_18", "FAIL", str(error))
    output = (result.stdout + "\n" + result.stderr).strip()
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", output)
    if result.returncode != 0 or not match:
        return MatrixCheck(
            "user-dev", "opencode_1_18", "FAIL", output or "empty version"
        )
    version = tuple(int(part) for part in match.groups())
    status: MatrixStatus = "PASS" if (1, 18, 4) <= version < (1, 19, 0) else "FAIL"
    return MatrixCheck(
        "user-dev", "opencode_1_18", status, ".".join(match.groups())
    )


def _local_endpoint(root: Path) -> tuple[str | None, str | None]:
    try:
        config = json.loads((root / "opencode.json").read_text(encoding="utf-8"))
        provider = config["provider"]["biexce-local"]
        raw_endpoint = provider["options"]["baseURL"]
        endpoint = resolve_config_reference(raw_endpoint)
        if endpoint is None:
            return None, "BIEXCE_LOCAL_BASE_URL is not set"
        return endpoint, None
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        return None, str(error)


def _gateway_checks(root: Path) -> list[MatrixCheck]:
    endpoint, error = _local_endpoint(root)
    if endpoint is None:
        return [MatrixCheck("server", "bifrost", "FAIL", error or "missing")]
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return [
            MatrixCheck(
                "server",
                "bifrost",
                "FAIL",
                "BIEXCE_LOCAL_BASE_URL must be an absolute HTTP(S) URL",
            )
        ]
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    checks: list[MatrixCheck] = []
    try:
        with socket.create_connection((parsed.hostname, port), timeout=3):
            pass
        checks.append(
            MatrixCheck(
                "server",
                "bifrost_tcp",
                "PASS",
                f"{parsed.hostname}:{port} reachable",
            )
        )
    except OSError as probe_error:
        checks.append(
            MatrixCheck("server", "bifrost_tcp", "FAIL", str(probe_error))
        )
        return checks
    models_url = endpoint.rstrip("/") + "/models"
    try:
        with urlopen(Request(models_url, method="GET"), timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        ids = {
            item.get("id")
            for item in payload.get("data", [])
            if isinstance(item, dict)
        }
        model_id = LOCAL_MODEL.split("/", 1)[1]
        ok = model_id in ids or LOCAL_MODEL in ids
        checks.append(
            MatrixCheck(
                "server",
                "bifrost_models",
                "PASS" if ok else "FAIL",
                f"model count={len(ids)}; expected={model_id}",
            )
        )
    except HTTPError as http_error:
        status: MatrixStatus = (
            "BLOCKED" if http_error.code in {401, 403} else "FAIL"
        )
        checks.append(
            MatrixCheck(
                "server",
                "bifrost_models",
                status,
                f"HTTP {http_error.code}; per-user credential required",
            )
        )
    except (OSError, URLError, UnicodeError, json.JSONDecodeError) as api_error:
        checks.append(MatrixCheck("server", "bifrost_models", "FAIL", str(api_error)))
    return checks


def _load_server_evidence(path: str | os.PathLike[str] | Path | None) -> list[MatrixCheck]:
    names = ("vllm", "gpu", "quota", "concurrency")
    if path is None:
        return [
            MatrixCheck(
                "server",
                name,
                "BLOCKED",
                "No signed LIVE server evidence was supplied",
            )
            for name in names
        ]
    evidence_path = Path(path).expanduser().resolve()
    try:
        document = json.loads(evidence_path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or set(document) != {
            "schema_version",
            "source",
            "captured_at_utc",
            "checks",
        }:
            raise ValueError("evidence properties are invalid")
        if document["schema_version"] != 1 or document["source"] != "LIVE":
            raise ValueError("evidence must be schema v1 and source LIVE")
        datetime.fromisoformat(str(document["captured_at_utc"]).replace("Z", "+00:00"))
        evidence_checks = document["checks"]
        if not isinstance(evidence_checks, dict) or set(evidence_checks) != set(names):
            raise ValueError("evidence must contain vllm/gpu/quota/concurrency")
        result = []
        for name in names:
            item = evidence_checks[name]
            if not isinstance(item, dict) or set(item) != {"ok", "detail"}:
                raise ValueError(f"invalid evidence check: {name}")
            result.append(
                MatrixCheck(
                    "server",
                    name,
                    "PASS" if item["ok"] is True else "FAIL",
                    str(item["detail"]),
                )
            )
        return result
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return [MatrixCheck("server", "live_evidence", "FAIL", str(error))]


def _inference_check(root: Path, enabled: bool) -> MatrixCheck:
    if not enabled:
        return MatrixCheck(
            "e2e",
            "gateway_to_model",
            "BLOCKED",
            "Live inference not requested; rerun with --live-inference and valid credential.",
        )
    endpoint, error = _local_endpoint(root)
    if endpoint is None:
        return MatrixCheck("e2e", "gateway_to_model", "FAIL", error or "missing")
    body = json.dumps(
        {
            "model": LOCAL_MODEL.split("/", 1)[1],
            "messages": [{"role": "user", "content": "Reply exactly OK"}],
            "max_tokens": 8,
            "temperature": 0,
        }
    ).encode("utf-8")
    request = Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        model = payload.get("model")
        choices = payload.get("choices")
        ok = isinstance(model, str) and isinstance(choices, list) and bool(choices)
        return MatrixCheck(
            "e2e",
            "gateway_to_model",
            "PASS" if ok else "FAIL",
            f"actual_model={model}; choices={len(choices) if isinstance(choices, list) else 0}",
        )
    except HTTPError as http_error:
        status: MatrixStatus = (
            "BLOCKED" if http_error.code in {401, 403} else "FAIL"
        )
        return MatrixCheck(
            "e2e",
            "gateway_to_model",
            status,
            f"HTTP {http_error.code}; per-user credential may be required",
        )
    except (OSError, URLError, UnicodeError, json.JSONDecodeError) as error:
        return MatrixCheck("e2e", "gateway_to_model", "FAIL", str(error))


def run_gate0_matrix(
    project: str | os.PathLike[str] | Path,
    *,
    config_home: str | os.PathLike[str] | Path | None = None,
    opencode_root: str | os.PathLike[str] | Path | None = None,
    server_evidence: str | os.PathLike[str] | Path | None = None,
    live_inference: bool = False,
) -> dict[str, object]:
    runtime_root = opencode_config_root(opencode_root)
    validation = validate_project(
        project, config_home=config_home, opencode_root=runtime_root
    )
    routing = routing_status(config_home)
    checks: list[MatrixCheck] = [
        MatrixCheck(
            "user-dev",
            "artifact_mode_permission_model",
            "PASS" if validation.ok else "FAIL",
            "Gate 0 validator PASS" if validation.ok else "validator failures present",
        ),
        MatrixCheck(
            "user-dev",
            "routing_applied",
            "PASS" if routing["valid"] and routing["applied"] else "FAIL",
            "seven bindings applied"
            if routing["valid"] and routing["applied"]
            else "routing invalid or not applied",
        ),
        _opencode_version(runtime_root),
    ]
    checks.extend(_gateway_checks(runtime_root))
    checks.extend(_load_server_evidence(server_evidence))
    checks.append(_inference_check(runtime_root, live_inference))
    counts = {
        status: sum(check.status == status for check in checks)
        for status in ("PASS", "FAIL", "BLOCKED")
    }
    return {
        "ok": counts["FAIL"] == 0 and counts["BLOCKED"] == 0,
        "implementation_ok": all(
            check.status == "PASS" for check in checks if check.layer == "user-dev"
        ),
        "counts": counts,
        "checks": [check.to_document() for check in checks],
    }


def require_matrix_pass(document: dict[str, object]) -> None:
    if not document.get("ok"):
        raise ControlPlaneError("Gate 0 matrix is not fully PASS.")
