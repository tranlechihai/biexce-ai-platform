"""Live adapters for OpenCode 1.18.x and project-local BIEXCE state."""

from datetime import datetime, timezone
import json
from pathlib import Path

from .base import AgentSource, PanelSnapshot, snapshot
from .project_state import ProjectStateSource


def _number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return value


def _timestamp(milliseconds) -> str | None:
    if isinstance(milliseconds, bool) or not isinstance(milliseconds, (int, float)):
        return None
    return datetime.fromtimestamp(
        milliseconds / 1000, tz=timezone.utc
    ).isoformat(timespec="seconds").replace("+00:00", "Z")


def _model_id(model: object) -> str | None:
    if not isinstance(model, dict):
        return None
    provider = model.get("providerID")
    identifier = model.get("id") or model.get("modelID")
    if not isinstance(provider, str) or not isinstance(identifier, str):
        return None
    if identifier.startswith(provider + "/"):
        return identifier
    return f"{provider}/{identifier}"


def load_configured_models(path: Path) -> dict[str, str]:
    """Read only primary bindings; malformed local config degrades to unknown."""
    try:
        if path.is_symlink() or not path.is_file():
            return {}
        document = json.loads(path.read_text(encoding="utf-8"))
        agents = document.get("agents", {})
        return {
            agent: binding["primary"]
            for agent, binding in agents.items()
            if isinstance(binding, dict)
            and isinstance(binding.get("primary"), str)
        }
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
        return {}


def normalize_session(
    item: dict,
    status_by_id: dict,
    *,
    machine: str,
    configured_models: dict[str, str],
) -> dict:
    session_id = str(item.get("id") or "")
    agent = item.get("agent") if isinstance(item.get("agent"), str) else None
    model = _model_id(item.get("model"))
    directory = item.get("directory")
    project = (
        Path(directory).name
        if isinstance(directory, str) and directory
        else str(item.get("projectID") or "unknown")
    )
    time = item.get("time") if isinstance(item.get("time"), dict) else {}
    tokens = item.get("tokens") if isinstance(item.get("tokens"), dict) else {}
    cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
    status = status_by_id.get(session_id, {})
    status_type = status.get("type") if isinstance(status, dict) else status
    if status_type not in {"busy", "idle", "retry"}:
        status_type = "idle"
    return {
        "id": session_id,
        "machine": machine,
        "project": project,
        "agent": agent,
        "title": str(item.get("title") or session_id),
        "configured_model": configured_models.get(agent) if agent else None,
        "actual_model": model,
        "status": status_type,
        "updated": _timestamp(time.get("updated")),
        "tokens": {
            "input": _number(tokens.get("input")),
            "output": _number(tokens.get("output")),
            "reasoning": _number(tokens.get("reasoning")),
            "cache_read": _number(cache.get("read")),
            "cache_write": _number(cache.get("write")),
        },
        "cost_usd": _number(item.get("cost")),
    }


def aggregate_usage(sessions: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], dict] = {}
    for session in sessions:
        model = session.get("actual_model") or "unknown"
        agent = session.get("agent") or "unknown"
        project = session.get("project") or "unknown"
        key = (model, agent, project)
        if key not in grouped:
            grouped[key] = {
                "model": model,
                "zone": "local" if model.startswith("biexce-local/") else "cloud",
                "agent": agent,
                "project": project,
                "sessions": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "tokens_reasoning": 0,
                "cache_read": 0,
                "cache_write": 0,
                "cost_usd": 0.0,
                "quota_remaining": None,
            }
        row = grouped[key]
        tokens = session.get("tokens", {})
        row["sessions"] += 1
        row["tokens_in"] += _number(tokens.get("input"))
        row["tokens_out"] += _number(tokens.get("output"))
        row["tokens_reasoning"] += _number(tokens.get("reasoning"))
        row["cache_read"] += _number(tokens.get("cache_read"))
        row["cache_write"] += _number(tokens.get("cache_write"))
        row["cost_usd"] += _number(session.get("cost_usd"))
    return sorted(
        grouped.values(),
        key=lambda row: row["tokens_in"] + row["tokens_out"],
        reverse=True,
    )


def normalize_event(payload: object, seq: int) -> dict | None:
    """Expose operational fields only, never raw prompt/tool input payloads."""
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("payload"), dict):
        payload = payload["payload"]
    event_type = payload.get("type")
    properties = payload.get("properties")
    if not isinstance(event_type, str) or not isinstance(properties, dict):
        return None
    session_id = properties.get("sessionID")
    base = {"seq": seq, "session": session_id, "event": event_type}

    if event_type in {"session.status", "session.idle"}:
        status = properties.get("status", {})
        status_type = (
            status.get("type") if isinstance(status, dict) else "idle"
        )
        return {**base, "type": "status", "status": status_type or "idle"}

    if event_type == "message.updated":
        info = properties.get("info", {})
        if not isinstance(info, dict):
            return None
        tokens = info.get("tokens") if isinstance(info.get("tokens"), dict) else {}
        return {
            **base,
            "type": "usage" if info.get("role") == "assistant" else "message",
            "agent": info.get("agent"),
            "model": _model_id(
                {
                    "providerID": info.get("providerID"),
                    "modelID": info.get("modelID"),
                }
            ),
            "tokens_in": _number(tokens.get("input")),
            "tokens_out": _number(tokens.get("output")),
            "cost_usd": _number(info.get("cost")),
        }

    if event_type == "message.part.updated":
        part = properties.get("part", {})
        if not isinstance(part, dict):
            return None
        if part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str) and text.startswith("[BX-STATE] "):
                return {**base, "type": "beacon", "line": text}
            return {
                **base,
                "type": "message",
                "text": "Assistant text updated",
            }
        if part.get("type") == "tool":
            state = part.get("state", {})
            return {
                **base,
                "type": "tool",
                "tool": part.get("tool"),
                "status": state.get("status") if isinstance(state, dict) else None,
            }

    if event_type in {"session.created", "session.updated"}:
        info = properties.get("info", {})
        return {
            **base,
            "type": "session",
            "agent": info.get("agent") if isinstance(info, dict) else None,
            "text": info.get("title") if isinstance(info, dict) else None,
        }
    if event_type == "session.error":
        return {**base, "type": "error", "text": "OpenCode session error"}
    if event_type in {"permission.asked", "permission.v2.asked"}:
        return {
            **base,
            "type": "permission",
            "text": properties.get("permission") or properties.get("action"),
        }
    if event_type == "session.next.agent.switched":
        return {**base, "type": "agent", "agent": properties.get("agent")}
    if event_type == "session.next.model.switched":
        return {
            **base,
            "type": "model",
            "model": _model_id(properties.get("model")),
        }
    return {**base, "type": "event"}


class OpencodeServeSource(AgentSource):
    name = "opencode-serve"
    mode = "live"

    def __init__(
        self,
        base_url: str,
        *,
        project_roots: tuple[Path, ...] = (),
        machine: str = "unknown",
        routing_file: Path | None = None,
        session_limit: int = 100,
    ):
        self.base_url = base_url.rstrip("/")
        self.machine = machine
        self.routing_file = routing_file or Path("")
        self.session_limit = session_limit
        self.project_state = ProjectStateSource(project_roots, machine)

    def _client(self):
        import httpx

        return httpx.AsyncClient(base_url=self.base_url, timeout=5.0)

    async def sessions(self) -> PanelSnapshot:
        try:
            async with self._client() as client:
                session_response = await client.get(
                    "/session",
                    params={"roots": "true", "limit": self.session_limit},
                )
                session_response.raise_for_status()
                status_response = await client.get("/session/status")
                status_response.raise_for_status()
                items = session_response.json()
                statuses = status_response.json()
            if not isinstance(items, list) or not isinstance(statuses, dict):
                raise ValueError("OpenCode returned an unexpected session schema")
            configured = load_configured_models(self.routing_file)
            normalized = [
                normalize_session(
                    item,
                    statuses,
                    machine=self.machine,
                    configured_models=configured,
                )
                for item in items
                if isinstance(item, dict)
            ]
            normalized.sort(
                key=lambda item: item.get("updated") or "", reverse=True
            )
            normalized.sort(key=lambda item: item["status"] != "busy")
            observed = max(
                (
                    item["updated"]
                    for item in normalized
                    if item.get("updated")
                ),
                default=None,
            )
            return snapshot(
                normalized,
                source=self.name,
                mode=self.mode,
                machine=self.machine,
                observed_at=observed,
            )
        except Exception as error:
            return snapshot(
                [],
                source=self.name,
                mode=self.mode,
                machine=self.machine,
                status="unavailable",
                message=f"OpenCode unavailable: {type(error).__name__}",
            )

    async def flow(self) -> PanelSnapshot:
        return await self.project_state.read()

    async def hardware(self) -> PanelSnapshot:
        return snapshot(
            {
                "server": self.machine,
                "gpus": [],
                "cpu_pct": None,
                "ram_used_gb": None,
                "ram_total_gb": None,
                "vllm": None,
            },
            source="server-telemetry",
            mode=self.mode,
            machine=self.machine,
            status="unavailable",
            message="GPU/vLLM collector is not connected.",
        )

    async def usage(self) -> PanelSnapshot:
        sessions = await self.sessions()
        rows = aggregate_usage(sessions.data)
        status = sessions.meta["status"]
        message = sessions.meta.get("message")
        if status == "ok":
            status = "degraded"
            message = (
                "OpenCode token/cost totals are live; Bifrost quota "
                "and server reconciliation are not connected."
            )
        return snapshot(
            rows,
            source="opencode-session-usage",
            mode=self.mode,
            machine=self.machine,
            status=status,
            message=message,
            observed_at=sessions.meta.get("observed_at"),
        )

    async def events(self, limit=None, delay=1.0):
        count = 0
        try:
            async with self._client() as client:
                async with client.stream("GET", "/event") as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            payload = json.loads(line[len("data:"):].strip())
                        except json.JSONDecodeError:
                            continue
                        event = normalize_event(payload, count)
                        if event is None:
                            continue
                        yield event
                        count += 1
                        if limit is not None and count >= limit:
                            return
        except Exception as error:
            yield {
                "seq": count,
                "type": "source",
                "status": "unavailable",
                "text": f"OpenCode event stream unavailable: {type(error).__name__}",
            }
