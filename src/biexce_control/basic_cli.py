"""CLI adapter for the lean Plan/Build OpenCode configuration."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from .basic_config import build_config, inspect_config, run_doctor


Printer = Callable[..., None]


def add_basic_parser(commands: argparse._SubParsersAction) -> None:
    basic = commands.add_parser(
        "basic",
        help="Build a clean OpenCode configuration with Plan and Build only.",
    )
    actions = basic.add_subparsers(dest="action", required=True)

    setup = actions.add_parser("setup")
    setup.add_argument("--output", required=True, type=Path)
    setup.add_argument("--plan-model", required=True)
    setup.add_argument("--build-model", required=True)
    setup.add_argument(
        "--opencode-config-dir",
        type=Path,
        help="Source provider catalog; defaults to the user OpenCode config.",
    )
    setup.add_argument("--json", action="store_true", dest="as_json")

    for action in ("status", "doctor"):
        inspect = actions.add_parser(action)
        inspect.add_argument("--config-dir", required=True, type=Path)
        inspect.add_argument("--opencode-binary")
        inspect.add_argument("--json", action="store_true", dest="as_json")


def handle_basic(arguments: argparse.Namespace, printer: Printer) -> int:
    if arguments.action == "setup":
        output = build_config(
            arguments.output,
            plan_model=arguments.plan_model,
            build_model=arguments.build_model,
            source_config_dir=arguments.opencode_config_dir,
        )
        payload = inspect_config(output)
        payload["built"] = True
        printer(payload, as_json=arguments.as_json)
        return 0 if payload["ok"] else 2

    payload = (
        run_doctor(arguments.config_dir, arguments.opencode_binary)
        if arguments.action == "doctor"
        else inspect_config(arguments.config_dir)
    )
    printer(payload, as_json=arguments.as_json)
    key = "ready_to_run" if arguments.action == "doctor" else "ok"
    return 0 if payload[key] else 2
