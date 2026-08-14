"""Canonical task status behavior."""

CANONICAL_STATUSES = ("open", "closed")


def normalize_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in CANONICAL_STATUSES:
        raise ValueError(f"unsupported status: {value}")
    return normalized


def status_label(value: str) -> str:
    return normalize_status(value).title()
