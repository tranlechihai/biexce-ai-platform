#!/usr/bin/env python3
"""CLI facade for the isolated OpenCode + Slim config builder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from biexce_control.slim_config import (  # noqa: E402
    ROLE_ORDER,
    SLIM_IDS,
    PrototypeError,
    build_prototype,
    load_routing,
    validate_output_path,
)

__all__ = [
    "PrototypeError",
    "ROLE_ORDER",
    "SLIM_IDS",
    "build_prototype",
    "load_routing",
    "validate_output_path",
]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an isolated BIEXCE Slim prototype config."
    )
    parser.add_argument("--routing", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--base-opencode",
        type=Path,
        help=(
            "Optional existing OpenCode config to copy provider definitions "
            "from. It is read-only; output is still isolated."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        output = build_prototype(args.routing, args.output, args.base_opencode)
    except PrototypeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
