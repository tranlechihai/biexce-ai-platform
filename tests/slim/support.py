"""Shared helpers for Slim prototype regression tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_ROOT = REPOSITORY_ROOT / "prototype" / "slim"
SLIM_SOURCE = REPOSITORY_ROOT / "src" / "global" / "slim"
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from biexce_control import slim_config as prototype  # noqa: E402


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_map(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@contextmanager
def temporary_directory():
    # Python 3.13 mode 0700 temp dirs can receive unusable Windows sandbox ACLs.
    path = Path(tempfile.gettempdir()) / f"biexce-slim-test-{uuid.uuid4().hex}"
    path.mkdir(mode=0o755)
    try:
        yield path
    finally:
        shutil.rmtree(path)


class GeneratorTestCase(unittest.TestCase):
    def setUp(self):
        self.routing = PROTOTYPE_ROOT / "routing.example.json"
        self.source_config = REPOSITORY_ROOT / "src" / "global" / "opencode.json"

    def build(self, parent: Path, name: str = "config") -> Path:
        output = parent / name
        prototype.build_prototype(self.routing, output)
        return output
