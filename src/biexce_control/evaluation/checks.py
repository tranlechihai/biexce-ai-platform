"""Load human assessment and deterministic JUnit evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from .errors import EvaluationError


STATUSES = {"PASS", "FAIL", "INCONCLUSIVE", "SKIPPED"}
COMPLETION = {"completed", "partial", "blocked", "unknown"}


def load_assessment(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return _empty_assessment()
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise EvaluationError(f"Assessment does not exist: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise EvaluationError(f"Invalid assessment JSON: {error}") from error
    if not isinstance(raw, dict):
        raise EvaluationError("Assessment root must be an object.")
    assessment = _empty_assessment()
    assessment.update(raw)
    _validate_assessment(assessment)
    assessment["provided"] = True
    return assessment


def inspect_junit(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise EvaluationError(f"JUnit report does not exist: {source}")
    try:
        root = ET.parse(source).getroot()
    except ET.ParseError as error:
        raise EvaluationError(f"Invalid JUnit XML {source}: {error}") from error
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        suites = list(root.iter("testsuite"))
    totals = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    duration = 0.0
    for suite in suites:
        for key in totals:
            totals[key] += _integer(suite.get(key, "0"), source)
        duration += _number(suite.get("time", "0"), source)
    if totals["tests"] == 0:
        raise EvaluationError(f"JUnit report has no tests: {source}")
    failed = totals["failures"] + totals["errors"]
    return {
        "source": source.name,
        **totals,
        "passed": totals["tests"] - failed - totals["skipped"],
        "duration_seconds": round(duration, 3),
        "status": "PASS" if failed == 0 else "FAIL",
    }


def combine_junit(reports: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ("tests", "passed", "failures", "errors", "skipped")
    return {
        "count": len(reports),
        "reports": reports,
        **{key: sum(report[key] for report in reports) for key in keys},
        "duration_seconds": round(
            sum(report["duration_seconds"] for report in reports), 3
        ),
        "status": (
            "INCONCLUSIVE"
            if not reports
            else "PASS"
            if all(report["status"] == "PASS" for report in reports)
            else "FAIL"
        ),
    }


def _empty_assessment() -> dict[str, Any]:
    return {
        "provided": False,
        "completion_status": "unknown",
        "human_interventions": None,
        "scope_violations": None,
        "test_weakened": None,
        "critical_security_findings": None,
        "checks": [],
        "notes": "",
    }


def _validate_assessment(value: dict[str, Any]) -> None:
    if value["completion_status"] not in COMPLETION:
        raise EvaluationError("Invalid assessment completion_status.")
    for field in (
        "human_interventions",
        "scope_violations",
        "critical_security_findings",
    ):
        item = value[field]
        if item is not None and (not isinstance(item, int) or item < 0):
            raise EvaluationError(f"Assessment {field} must be a non-negative integer.")
    if value["test_weakened"] not in {True, False, None}:
        raise EvaluationError("Assessment test_weakened must be true, false or null.")
    if not isinstance(value["checks"], list):
        raise EvaluationError("Assessment checks must be an array.")
    for check in value["checks"]:
        if not isinstance(check, dict) or not str(check.get("name", "")).strip():
            raise EvaluationError("Every assessment check needs a name.")
        check["status"] = str(check.get("status", "INCONCLUSIVE")).upper()
        if check["status"] not in STATUSES:
            raise EvaluationError(f"Invalid check status: {check['status']}")


def _integer(value: str, source: Path) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise EvaluationError(f"Invalid JUnit count in {source}: {value}") from error


def _number(value: str, source: Path) -> float:
    try:
        return float(value)
    except ValueError as error:
        raise EvaluationError(f"Invalid JUnit time in {source}: {value}") from error
