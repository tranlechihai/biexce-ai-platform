"""CLI adapter for isolated BIEXCE OpenCode + Slim configurations."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from .slim_config.service import build_from_user_routing, inspect_generated_config
from .slim_config.doctor import run_generated_doctor


Printer = Callable[..., None]


def add_slim_parser(commands: argparse._SubParsersAction) -> None:
    slim = commands.add_parser(
        "slim",
        help="Build and inspect an isolated OpenCode + Slim configuration.",
    )
    actions = slim.add_subparsers(dest="action", required=True)

    for action in ("setup", "build"):
        build = actions.add_parser(action)
        build.add_argument("--output", required=True, type=Path)
        build.add_argument(
            "--routing",
            type=Path,
            help=(
                "Optional seven-role routing file; defaults to applied "
                "BIEXCE routing."
            ),
        )
        build.add_argument("--config-home")
        build.add_argument("--opencode-config-dir")
        build.add_argument("--json", action="store_true", dest="as_json")

    for action in ("status", "doctor"):
        inspect = actions.add_parser(action)
        inspect.add_argument("--config-dir", required=True, type=Path)
        inspect.add_argument("--json", action="store_true", dest="as_json")


def handle_slim(arguments: argparse.Namespace, printer: Printer) -> int:
    if arguments.action in {"setup", "build"}:
        output = build_from_user_routing(
            arguments.output,
            config_home=arguments.config_home,
            opencode_root=arguments.opencode_config_dir,
            routing_file=arguments.routing,
        )
        payload = inspect_generated_config(output)
        payload["built"] = True
        printer(payload, as_json=arguments.as_json)
        return 0 if payload["ok"] else 2

    payload = (
        run_generated_doctor(arguments.config_dir)
        if arguments.action == "doctor"
        else inspect_generated_config(arguments.config_dir)
    )
    printer(payload, as_json=arguments.as_json)
    required = "ready_to_run" if arguments.action == "doctor" else "ok"
    return 0 if payload[required] else 2
