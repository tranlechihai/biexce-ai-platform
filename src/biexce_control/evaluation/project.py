"""Read-only project metadata used by evaluation reports."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any


def inspect_project(project: Path) -> dict[str, Any]:
    inside = _git(project, "rev-parse", "--is-inside-work-tree") == "true"
    if not inside:
        return {"name": project.name, "git": False}
    status = _git(project, "status", "--porcelain=v1").splitlines()
    numstat = _git(project, "diff", "--numstat").splitlines()
    additions = deletions = 0
    for line in numstat:
        columns = line.split("\t", 2)
        if len(columns) >= 2:
            additions += int(columns[0]) if columns[0].isdigit() else 0
            deletions += int(columns[1]) if columns[1].isdigit() else 0
    return {
        "name": project.name,
        "git": True,
        "commit": _git(project, "rev-parse", "HEAD") or None,
        "branch": _git(project, "branch", "--show-current") or None,
        "dirty_files": len(status),
        "diff_additions": additions,
        "diff_deletions": deletions,
    }


def _git(project: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""
