"""Offline dashboard contract tests; no VPN or live model is required."""

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.beacon import parse_beacon
from app.main import app
from app.sources.mock import MockSource
from app.sources.opencode import (
    aggregate_usage,
    normalize_event,
    normalize_session,
)
from app.sources.project_state import ProjectStateSource


client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"


def test_healthz_mock():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["mode"] == "mock"


def test_panels_return_contract_and_provenance():
    sessions = client.get("/api/sessions").json()
    flow = client.get("/api/flow").json()
    hardware = client.get("/api/hardware").json()
    usage = client.get("/api/usage").json()
    assert sessions["sessions"] and sessions["meta"]["mode"] == "mock"
    assert flow["projects"] and flow["meta"]["source"] == "mock"
    assert hardware["gpus"] and hardware["meta"]["mode"] == "mock"
    assert usage["usage"] and usage["meta"]["mode"] == "mock"
    assert client.get("/api/quota").json()["usage"] == usage["usage"]


def test_overview_summarizes_agents_tasks_and_tokens():
    overview = client.get("/api/overview").json()
    assert overview["agents"]["running"] == 1
    assert overview["agents"]["running_ids"] == ["bx-fix"]
    assert overview["tasks"] == {
        "total": 3, "done": 1, "active": 1, "escalated": 0
    }
    assert overview["usage"]["tokens_in"] == 194380


def test_index_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "Mission Control" in response.text


def _valid_beacon():
    return (
        '[BX-STATE] {"project":"p","stage":"B3","task":"t-002",'
        '"status":"coding","round":0,"done":1,"total":3,'
        '"agent":"bx-code","note":"working"}'
    )


def test_beacon_parser_enforces_full_contract():
    parsed = parse_beacon(_valid_beacon())
    assert parsed and parsed["project"] == "p"
    assert parse_beacon("khong phai beacon") is None
    assert parse_beacon("[BX-STATE] {json hong}") is None
    assert parse_beacon('[BX-STATE] {"project":"p","stage":"B3"}') is None
    assert parse_beacon(_valid_beacon().replace('"coding"', '"invalid"')) is None
    assert parse_beacon("'''\n" + _valid_beacon() + "\n'''") is None


def test_mock_event_stream_finite():
    async def collect():
        output = []
        async for event in MockSource().events(limit=3, delay=0):
            output.append(event)
        return output

    events = asyncio.run(collect())
    assert len(events) == 3
    assert any(event["type"] == "beacon" for event in events)


def test_project_state_source_reads_control_and_workflow():
    result = asyncio.run(
        ProjectStateSource((FIXTURES / "project-live",), "test-pc").read()
    )
    assert result.meta["status"] == "ok"
    assert result.data[0]["autopilot"]["mode"] == "RUNNING"
    assert result.data[0]["workflow"]["expected_agent"] == "bx-code"


def test_project_state_source_rejects_wip_violation():
    result = asyncio.run(
        ProjectStateSource((FIXTURES / "project-invalid-wip",), "test-pc").read()
    )
    assert result.data == []
    assert result.meta["status"] == "unavailable"
    assert "WIP=1" in result.meta["message"]


def test_opencode_session_mapping_and_usage_aggregation():
    raw = {
        "id": "ses_1",
        "projectID": "project-id",
        "directory": "/work/example",
        "title": "Implement API",
        "agent": "bx-code",
        "model": {"providerID": "openai", "id": "gpt-test"},
        "time": {"updated": 1785744000000},
        "tokens": {
            "input": 100,
            "output": 25,
            "reasoning": 5,
            "cache": {"read": 10, "write": 2},
        },
        "cost": 0.03,
    }
    mapped = normalize_session(
        raw,
        {"ses_1": {"type": "busy"}},
        machine="dev",
        configured_models={"bx-code": "openai/gpt-configured"},
    )
    assert mapped["status"] == "busy"
    assert mapped["configured_model"] == "openai/gpt-configured"
    assert mapped["actual_model"] == "openai/gpt-test"
    usage = aggregate_usage([mapped, mapped])
    assert usage[0]["sessions"] == 2
    assert usage[0]["tokens_in"] == 200
    assert usage[0]["cost_usd"] == 0.06


def test_event_mapping_redacts_raw_tool_input():
    event = normalize_event(
        {
            "type": "message.part.updated",
            "properties": {
                "sessionID": "ses_1",
                "part": {
                    "type": "tool",
                    "tool": "shell",
                    "state": {
                        "status": "running",
                        "input": {"password": "must-not-leak"},
                    },
                },
            },
        },
        4,
    )
    assert event == {
        "seq": 4,
        "session": "ses_1",
        "event": "message.part.updated",
        "type": "tool",
        "tool": "shell",
        "status": "running",
    }
    text_event = normalize_event(
        {
            "type": "message.part.updated",
            "properties": {
                "sessionID": "ses_1",
                "part": {
                    "type": "text",
                    "text": "secret source content must-not-leak",
                },
            },
        },
        5,
    )
    assert text_event["text"] == "Assistant text updated"
    assert "must-not-leak" not in str(text_event)


def test_sse_route_registered():
    paths = {route.path for route in app.routes}
    assert {"/api/events", "/api/overview", "/api/usage"}.issubset(paths)
