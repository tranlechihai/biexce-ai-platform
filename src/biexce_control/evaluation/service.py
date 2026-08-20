"""Collect, score and compare BIEXCE workflow evaluations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Any

from .checks import combine_junit, inspect_junit, load_assessment
from .errors import EvaluationError
from .paths import new_run_directory, project_directory, report_file
from .project import inspect_project
from .redaction import redact
from .reporting import comparison_markdown, evaluation_markdown
from .scoring import score_report
from .session import combine_sessions, inspect_session_export


SCHEMA_VERSION = 1


def collect_evaluation(
    project: str | Path,
    *,
    session_exports: list[str | Path] | None = None,
    junit_reports: list[str | Path] | None = None,
    assessment_path: str | Path | None = None,
    output: str | Path | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    root = project_directory(project)
    run = new_run_directory(root, output, label)
    try:
        sessions = [inspect_session_export(path) for path in session_exports or []]
        junit = [inspect_junit(path) for path in junit_reports or []]
        report: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run.name,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": inspect_project(root),
            "workflow": combine_sessions(sessions),
            "junit": combine_junit(junit),
            "assessment": load_assessment(assessment_path),
        }
        report = redact(report)
        report["scorecard"] = score_report(report)
        _write_report(run, report)
    except Exception:
        try:
            shutil.rmtree(run)
        except OSError:
            pass
        raise
    return _result(run, report)


def rescore_evaluation(value: str | Path) -> dict[str, Any]:
    path = report_file(value)
    report = _load_report(path)
    report["scorecard"] = score_report(report)
    _write_json(path, report)
    (path.parent / "report.md").write_text(
        evaluation_markdown(report), encoding="utf-8", newline="\n"
    )
    return _result(path.parent, report)


def compare_evaluations(
    baseline: str | Path,
    candidate: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    base = _load_report(report_file(baseline))
    current = _load_report(report_file(candidate))
    comparison = _comparison(base, current)
    if output:
        target = Path(output).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        _write_json(target / "comparison.json", comparison)
        (target / "comparison.md").write_text(
            comparison_markdown(comparison), encoding="utf-8", newline="\n"
        )
    return comparison


def _comparison(base: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    base_score = base["scorecard"]
    current_score = current["scorecard"]
    interventions = lambda item: item["assessment"]["human_interventions"] or 0
    decision = (
        "PROMOTE"
        if current_score["verdict"] == "PASS"
        and current_score["score"] >= base_score["score"]
        else "HOLD"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "baseline": _summary(base),
        "candidate": _summary(current),
        "delta": {
            "score": round(current_score["score"] - base_score["score"], 1),
            "duration_seconds": round(
                current["workflow"]["duration_seconds"]
                - base["workflow"]["duration_seconds"], 3
            ),
            "tool_failures": (
                current["workflow"]["tool_failures"]
                - base["workflow"]["tool_failures"]
            ),
            "human_interventions": interventions(current) - interventions(base),
        },
    }


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": report["run_id"],
        "verdict": report["scorecard"]["verdict"],
        "score": report["scorecard"]["score"],
    }


def _result(run: Path, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "run_id": report["run_id"],
        "run_dir": str(run),
        "report_json": str(run / "report.json"),
        "report_markdown": str(run / "report.md"),
        **report["scorecard"],
    }


def _write_report(run: Path, report: dict[str, Any]) -> None:
    _write_json(run / "report.json", report)
    (run / "report.md").write_text(
        evaluation_markdown(report), encoding="utf-8", newline="\n"
    )
    for path in run.iterdir():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _load_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise EvaluationError(f"Invalid evaluation report: {error}") from error
    if not isinstance(report, dict) or report.get("schema_version") != SCHEMA_VERSION:
        raise EvaluationError(f"Unsupported evaluation report: {path}")
    return report
