"""Command-line adapter for reproducible workflow evaluations."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from .evaluation import collect_evaluation, compare_evaluations, rescore_evaluation


Printer = Callable[..., None]


def add_eval_parser(commands: argparse._SubParsersAction) -> None:
    evaluation = commands.add_parser(
        "eval", help="Collect and compare Plan/Build workflow evidence."
    )
    actions = evaluation.add_subparsers(dest="action", required=True)

    collect = actions.add_parser("collect")
    collect.add_argument("--project", required=True, type=Path)
    collect.add_argument("--session-export", action="append", default=[], type=Path)
    collect.add_argument("--junit", action="append", default=[], type=Path)
    collect.add_argument("--assessment", type=Path)
    collect.add_argument("--output", type=Path)
    collect.add_argument("--label")
    collect.add_argument("--json", action="store_true", dest="as_json")

    score = actions.add_parser("score")
    score.add_argument("--run", required=True, type=Path)
    score.add_argument("--json", action="store_true", dest="as_json")

    compare = actions.add_parser("compare")
    compare.add_argument("--baseline", required=True, type=Path)
    compare.add_argument("--candidate", required=True, type=Path)
    compare.add_argument("--output", type=Path)
    compare.add_argument("--json", action="store_true", dest="as_json")


def handle_eval(arguments: argparse.Namespace, printer: Printer) -> int:
    if arguments.action == "collect":
        payload = collect_evaluation(
            arguments.project,
            session_exports=arguments.session_export,
            junit_reports=arguments.junit,
            assessment_path=arguments.assessment,
            output=arguments.output,
            label=arguments.label,
        )
    elif arguments.action == "score":
        payload = rescore_evaluation(arguments.run)
    else:
        payload = compare_evaluations(
            arguments.baseline, arguments.candidate, arguments.output
        )
    printer(payload, as_json=arguments.as_json)
    if payload.get("decision") == "HOLD":
        return 3
    verdict = payload.get("verdict")
    return 0 if verdict in {None, "PASS", "INCONCLUSIVE"} else 3
