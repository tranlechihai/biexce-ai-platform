"""Contracts shared by every Mission Control data source."""

from dataclasses import dataclass
from datetime import datetime, timezone
import socket
from typing import Any, AsyncIterator, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def default_machine_name() -> str:
    return socket.gethostname() or "unknown"


@dataclass(frozen=True)
class PanelSnapshot:
    """Panel payload plus provenance; mock values can never look live."""

    data: Any
    meta: dict[str, Any]


def snapshot(
    data: Any,
    *,
    source: str,
    mode: str,
    machine: str,
    status: str = "ok",
    message: str | None = None,
    observed_at: str | None = None,
) -> PanelSnapshot:
    meta = {
        "source": source,
        "mode": mode,
        "machine": machine,
        "status": status,
        "collected_at": utc_now(),
        "observed_at": observed_at,
    }
    if message:
        meta["message"] = message
    return PanelSnapshot(data=data, meta=meta)


class AgentSource:
    name = "base"
    mode = "live"

    async def sessions(self) -> PanelSnapshot:
        """OpenCode sessions normalized for the UI."""
        raise NotImplementedError

    async def flow(self) -> PanelSnapshot:
        """Project-local task and Autopilot state."""
        raise NotImplementedError

    async def hardware(self) -> PanelSnapshot:
        """GPU/CPU/RAM and serving metrics."""
        raise NotImplementedError

    async def usage(self) -> PanelSnapshot:
        """Token/cost usage grouped by model, agent and project."""
        raise NotImplementedError

    async def events(
        self, limit: Optional[int] = None, delay: float = 1.0
    ) -> AsyncIterator[dict]:
        """Normalized realtime events. Raw prompts/tool inputs are not exposed."""
        raise NotImplementedError
