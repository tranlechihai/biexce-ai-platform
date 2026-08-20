"""Extract aggregate metrics from OpenCode session exports."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterator

from .errors import EvaluationError


def inspect_session_export(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise EvaluationError(f"Session export does not exist: {source}")
    document = _load_json(source)
    messages = _messages(document)
    models: set[str] = set()
    providers: set[str] = set()
    roles: dict[str, int] = {}
    tokens = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0}
    tool_calls = tool_failures = compactions = errors = 0
    timestamps: list[float] = []

    for message in messages:
        info = message.get("info", message)
        role = str(info.get("role", "unknown"))
        roles[role] = roles.get(role, 0) + 1
        _collect_model(info, providers, models)
        _collect_tokens(info, tokens)
        timestamps.extend(_timestamps(info))
        if info.get("error"):
            errors += 1
        parts = message.get("parts", [])
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            kind = str(part.get("type", ""))
            if kind == "tool":
                tool_calls += 1
                state = part.get("state", {})
                if isinstance(state, dict) and state.get("status") in {"error", "failed"}:
                    tool_failures += 1
            elif kind in {"compaction", "summary"}:
                compactions += 1
            timestamps.extend(_timestamps(part))

    started_at = min(timestamps) if timestamps else None
    ended_at = max(timestamps) if timestamps else None
    duration = ended_at - started_at if len(timestamps) > 1 else None
    return {
        "source": source.name,
        "session_ids": sorted(_session_ids(document)),
        "message_count": len(messages),
        "roles": dict(sorted(roles.items())),
        "providers": sorted(providers),
        "models": sorted(models),
        "tokens": tokens,
        "tool_calls": tool_calls,
        "tool_failures": tool_failures,
        "compactions": compactions,
        "errors": errors,
        "started_at_epoch": started_at,
        "ended_at_epoch": ended_at,
        "duration_seconds": round(duration, 3) if duration is not None else None,
    }


def combine_sessions(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    token_keys = ("input", "output", "reasoning", "cache_read")
    starts = [
        session["started_at_epoch"]
        for session in sessions
        if session["started_at_epoch"] is not None
    ]
    ends = [
        session["ended_at_epoch"]
        for session in sessions
        if session["ended_at_epoch"] is not None
    ]
    wall_duration = max(ends) - min(starts) if starts and ends else 0
    agent_duration = sum(session["duration_seconds"] or 0 for session in sessions)
    return {
        "count": len(sessions),
        "sessions": sessions,
        "models": sorted({item for session in sessions for item in session["models"]}),
        "providers": sorted({item for session in sessions for item in session["providers"]}),
        "message_count": sum(session["message_count"] for session in sessions),
        "tokens": {
            key: sum(session["tokens"][key] for session in sessions)
            for key in token_keys
        },
        "tool_calls": sum(session["tool_calls"] for session in sessions),
        "tool_failures": sum(session["tool_failures"] for session in sessions),
        "compactions": sum(session["compactions"] for session in sessions),
        "errors": sum(session["errors"] for session in sessions),
        "duration_seconds": round(wall_duration, 3),
        "agent_duration_seconds": round(agent_duration, 3),
    }


def _load_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig")
    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not starts:
        raise EvaluationError(f"Session export is not JSON: {path}")
    try:
        value, _ = json.JSONDecoder().raw_decode(text[min(starts):])
        return value
    except json.JSONDecodeError as error:
        raise EvaluationError(f"Invalid session export {path}: {error}") from error


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _messages(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, dict) and isinstance(document.get("messages"), list):
        return [item for item in document["messages"] if isinstance(item, dict)]
    return [
        item for item in _walk(document)
        if "parts" in item and isinstance(item.get("info", item), dict)
    ]


def _collect_model(info: dict[str, Any], providers: set[str], models: set[str]) -> None:
    provider = info.get("providerID") or info.get("provider_id")
    model = info.get("modelID") or info.get("model_id")
    if provider:
        providers.add(str(provider))
    if model:
        models.add(f"{provider}/{model}" if provider else str(model))


def _collect_tokens(info: dict[str, Any], totals: dict[str, int]) -> None:
    usage = info.get("tokens") or info.get("usage") or {}
    if not isinstance(usage, dict):
        return
    aliases = {
        "input": "input",
        "output": "output",
        "reasoning": "reasoning",
        "cacheRead": "cache_read",
    }
    for source, target in aliases.items():
        value = usage.get(source, 0)
        if isinstance(value, (int, float)):
            totals[target] += int(value)


def _timestamps(value: dict[str, Any]) -> list[float]:
    time = value.get("time", {})
    if not isinstance(time, dict):
        return []
    return [stamp for stamp in (_timestamp(item) for item in time.values()) if stamp is not None]


def _timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value) / 1000 if value > 10_000_000_000 else float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _session_ids(document: Any) -> set[str]:
    return {
        str(value)
        for item in _walk(document)
        for value in (item.get("sessionID"), item.get("session_id"), item.get("id"))
        if isinstance(value, str) and value.startswith("ses_")
    }
