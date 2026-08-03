"""Biexce Mission Control API and single-page dashboard."""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from .beacon import parse_beacon
from .config import settings
from .sources.mock import MockSource
from .sources.opencode import OpencodeServeSource
from .sources.project_state import ACTIVE_TASK_STATUSES


app = FastAPI(title="Biexce Mission Control", version="0.4.0-dev")
_INDEX = Path(__file__).parent / "templates" / "index.html"


def build_source():
    if settings.mock:
        return MockSource()
    return OpencodeServeSource(
        settings.opencode_serve_url,
        project_roots=settings.project_roots,
        machine=settings.machine_name,
        routing_file=settings.routing_file,
        session_limit=settings.session_limit,
    )


source = build_source()


def _response(key, panel):
    return {key: panel.data, "meta": panel.meta}


@app.get("/", response_class=HTMLResponse)
async def index():
    return _INDEX.read_text(encoding="utf-8")


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "mode": source.mode,
        "source": source.name,
        "version": app.version,
    }


@app.get("/api/sessions")
async def api_sessions():
    return _response("sessions", await source.sessions())


@app.get("/api/flow")
async def api_flow():
    return _response("projects", await source.flow())


@app.get("/api/hardware")
async def api_hardware():
    panel = await source.hardware()
    return {**panel.data, "meta": panel.meta}


@app.get("/api/usage")
async def api_usage():
    return _response("usage", await source.usage())


@app.get("/api/quota")
async def api_quota_compatibility():
    """Compatibility alias retained for the original B1 client."""
    return await api_usage()


@app.get("/api/overview")
async def api_overview():
    sessions, flow, usage = await asyncio.gather(
        source.sessions(), source.flow(), source.usage()
    )
    tasks = [
        task
        for project in flow.data
        for task in project.get("tasks", [])
    ]
    busy_agents = sorted(
        {
            item["agent"]
            for item in sessions.data
            if item.get("status") == "busy" and item.get("agent")
        }
    )
    return {
        "agents": {
            "running": len(busy_agents),
            "running_ids": busy_agents,
            "sessions": len(sessions.data),
        },
        "tasks": {
            "total": len(tasks),
            "done": sum(task.get("status") == "done" for task in tasks),
            "active": sum(
                task.get("status") in ACTIVE_TASK_STATUSES for task in tasks
            ),
            "escalated": sum(
                task.get("status") == "escalated" for task in tasks
            ),
        },
        "usage": {
            "tokens_in": sum(row.get("tokens_in", 0) for row in usage.data),
            "tokens_out": sum(row.get("tokens_out", 0) for row in usage.data),
            "cost_usd": round(
                sum(row.get("cost_usd", 0) for row in usage.data), 6
            ),
        },
        "meta": {
            "sessions": sessions.meta,
            "flow": flow.meta,
            "usage": usage.meta,
        },
    }


@app.get("/api/events")
async def api_events():
    """SSE feed with strict beacon parsing and sanitized OpenCode events."""

    async def generate():
        async for event in source.events(delay=settings.poll_interval):
            if event.get("type") == "beacon":
                parsed = parse_beacon(event.get("line", ""))
                if parsed:
                    event = {**event, "parsed": parsed}
                else:
                    event = {
                        "seq": event.get("seq"),
                        "type": "warning",
                        "text": "Rejected invalid BX-STATE beacon.",
                    }
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
