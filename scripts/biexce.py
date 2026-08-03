#!/usr/bin/env python3

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from biexce_control.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
