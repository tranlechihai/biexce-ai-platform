"""Human-readable evaluation and comparison reports."""

from __future__ import annotations

from typing import Any


def evaluation_markdown(report: dict[str, Any]) -> str:
    score = report["scorecard"]
    workflow = report["workflow"]
    junit = report["junit"]
    lines = [
        f"# BIEXCE Evaluation — {report['run_id']}",
        "",
        f"- Verdict: **{score['verdict']}**",
        f"- Score: **{score['score']}/100** (promotion: {score['promotion_threshold']})",
        f"- Project: `{report['project']['name']}`",
        f"- Created: `{report['created_at_utc']}`",
        "",
        "## Hard gates",
        "",
        "| Gate | Result |",
        "| --- | --- |",
    ]
    lines.extend(
        f"| {name} | {status} |"
        for name, status in score["hard_gates"].items()
    )
    lines.extend([
        "",
        "## Score",
        "",
        "| Component | Points |",
        "| --- | ---: |",
    ])
    lines.extend(
        f"| {name} | {points} |"
        for name, points in score["components"].items()
    )
    lines.extend([
        "",
        "## Workflow",
        "",
        f"- Session exports: {workflow['count']}",
        f"- Models: {', '.join(workflow['models']) or '-'}",
        f"- Messages: {workflow['message_count']}",
        f"- Tool calls/failures: {workflow['tool_calls']}/{workflow['tool_failures']}",
        f"- Compactions/errors: {workflow['compactions']}/{workflow['errors']}",
        f"- Wall-clock duration: {workflow['duration_seconds']} seconds",
        f"- Total agent time: {workflow['agent_duration_seconds']} seconds",
        "",
        "## Verification",
        "",
        f"- JUnit: {junit['status']} ({junit['passed']}/{junit['tests']} passed)",
    ])
    for check in report["assessment"]["checks"]:
        lines.append(f"- {check['name']}: {check['status']}")
    notes = report["assessment"].get("notes", "")
    if notes:
        lines.extend(["", "## Notes", "", str(notes)])
    lines.extend([
        "",
        "> Raw prompts, source content and credentials are not stored in this report.",
        "",
    ])
    return "\n".join(lines)


def comparison_markdown(comparison: dict[str, Any]) -> str:
    return "\n".join([
        "# BIEXCE Evaluation Comparison",
        "",
        f"- Decision: **{comparison['decision']}**",
        f"- Baseline: `{comparison['baseline']['run_id']}` "
        f"({comparison['baseline']['verdict']}, {comparison['baseline']['score']})",
        f"- Candidate: `{comparison['candidate']['run_id']}` "
        f"({comparison['candidate']['verdict']}, {comparison['candidate']['score']})",
        f"- Score delta: {comparison['delta']['score']:+.1f}",
        f"- Duration delta: {comparison['delta']['duration_seconds']:+.3f}s",
        f"- Tool-failure delta: {comparison['delta']['tool_failures']:+d}",
        f"- Human-intervention delta: {comparison['delta']['human_interventions']:+d}",
        "",
    ])
