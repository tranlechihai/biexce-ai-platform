"""Redact secret-like values before evidence is persisted."""

from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEY = re.compile(
    r"(^|_)(authorization|cookie|credential|password|secret|token|api_?key|virtual_?key)($|_)",
    re.IGNORECASE,
)
TEXT_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)(x-bf-vk\s*[:=]\s*)\S+"),
)


def redact(value: Any, key: str = "") -> Any:
    if key and SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item): redact(content, str(item)) for item, content in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        result = value
        for pattern in TEXT_PATTERNS:
            replacement = r"\1[REDACTED]" if pattern.groups else "[REDACTED]"
            result = pattern.sub(replacement, result)
        return result
    return value
