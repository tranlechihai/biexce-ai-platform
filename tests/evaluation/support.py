from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


@contextmanager
def temporary_directory():
    root = Path(tempfile.gettempdir()) / f"biexce-eval-test-{uuid.uuid4().hex}"
    root.mkdir(mode=0o755)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def write_session(path: Path, *, failed_tool: bool = False) -> Path:
    return write_json(path, {
        "info": {"id": "ses_parent", "title": "Evaluation fixture"},
        "messages": [
            {
                "info": {
                    "id": "msg_user",
                    "sessionID": "ses_parent",
                    "role": "user",
                    "time": {"created": 1_000_000_000_000},
                },
                "parts": [{"type": "text", "text": "Implement fixture"}],
            },
            {
                "info": {
                    "id": "msg_assistant",
                    "sessionID": "ses_parent",
                    "role": "assistant",
                    "providerID": "biexce-local",
                    "modelID": "vllm/test-model",
                    "tokens": {"input": 100, "output": 25, "reasoning": 5},
                    "time": {
                        "created": 1_000_000_001_000,
                        "completed": 1_000_000_005_000,
                    },
                },
                "parts": [{
                    "type": "tool",
                    "state": {"status": "error" if failed_tool else "completed"},
                }],
            },
        ],
    })


def write_junit(path: Path, *, failures: int = 0) -> Path:
    path.write_text(
        f'<testsuite tests="3" failures="{failures}" errors="0" '
        'skipped="0" time="1.25"></testsuite>',
        encoding="utf-8",
    )
    return path


def write_assessment(path: Path, **overrides) -> Path:
    value = {
        "completion_status": "completed",
        "human_interventions": 0,
        "scope_violations": 0,
        "test_weakened": False,
        "critical_security_findings": 0,
        "checks": [
            {"name": "lint", "status": "PASS"},
            {"name": "browser-smoke", "status": "PASS"},
        ],
        "notes": "Clean run",
    }
    value.update(overrides)
    return write_json(path, value)
