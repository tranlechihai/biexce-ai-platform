"""Environment-only configuration for Mission Control."""

import os
from pathlib import Path

from .sources.base import default_machine_name


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _project_roots(value: str | None) -> tuple[Path, ...]:
    if not value:
        return ()
    roots = []
    for item in value.split(os.pathsep):
        item = item.strip()
        if item:
            roots.append(Path(item).expanduser())
    return tuple(roots)


class Settings:
    def __init__(self):
        self.mock = _bool(os.environ.get("BIEXCE_DASHBOARD_MOCK"), True)
        self.port = int(os.environ.get("BIEXCE_DASHBOARD_PORT", "8090"))
        self.opencode_serve_url = os.environ.get(
            "OPENCODE_SERVE_URL", "http://127.0.0.1:4096"
        )
        self.poll_interval = max(
            0.2, float(os.environ.get("BIEXCE_DASHBOARD_POLL", "2.0"))
        )
        self.machine_name = os.environ.get(
            "BIEXCE_MACHINE_NAME", default_machine_name()
        )
        self.project_roots = _project_roots(
            os.environ.get("BIEXCE_PROJECT_ROOTS")
        )
        self.routing_file = Path(
            os.environ.get(
                "BIEXCE_ROUTING_FILE",
                str(Path.home() / ".config" / "biexce" / "model-routing.json"),
            )
        ).expanduser()
        self.session_limit = min(
            500, max(1, int(os.environ.get("BIEXCE_SESSION_LIMIT", "100")))
        )


settings = Settings()
