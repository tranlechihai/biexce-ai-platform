"""Task-board summary behavior."""

from collections.abc import Iterable

from .status import CANONICAL_STATUSES, normalize_status


def count_statuses(values: Iterable[str]) -> dict[str, int]:
    counts = {status: 0 for status in CANONICAL_STATUSES}
    for value in values:
        counts[normalize_status(value)] += 1
    return counts
