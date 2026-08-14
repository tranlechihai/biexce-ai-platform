"""Small UTF-8 JSON helpers with consistent prototype errors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import PrototypeError


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrototypeError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PrototypeError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
