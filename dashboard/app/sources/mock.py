"""Deterministic offline data for dashboard development and tests."""

import asyncio
import copy

from .base import AgentSource, snapshot


_MACHINE = "dev-01 (MOCK)"
_PROJECT_STATE = {
    "project": "social-backend",
    "machine": _MACHINE,
    "stage": "B3",
    "updated": "2026-08-03T08:15:00Z",
    "autopilot": {
        "mode": "RUNNING",
        "revision": 4,
        "session_id": "ses_mock_001",
        "updated_at_utc": "2026-08-03T08:15:00Z",
    },
    "workflow": {
        "phase": "FIX",
        "revision": 9,
        "current_task_id": "t-002",
        "fix_round": 2,
        "gate_1": "APPROVED",
        "gate_2": "PENDING",
        "last_agent": "bx-test",
        "last_result": "FAIL",
        "blocked_reason": None,
        "updated_at_utc": "2026-08-03T08:15:00Z",
        "expected_agent": "bx-fix",
    },
    "tasks": [
        {
            "id": "t-001", "title": "scaffold", "status": "done",
            "round": 0, "agent": None,
        },
        {
            "id": "t-002", "title": "auth", "status": "fixing",
            "round": 2, "agent": "bx-fix",
        },
        {
            "id": "t-003", "title": "user profile", "status": "backlog",
            "round": 0, "agent": None,
        },
    ],
}

_SESSIONS = [
    {
        "id": "ses_mock_001",
        "machine": _MACHINE,
        "project": "social-backend",
        "agent": "bx-fix",
        "title": "t-002 auth (round 2)",
        "configured_model": "biexce-local/vllm/Qwen/Qwen3.6-27B-FP8",
        "actual_model": "biexce-local/vllm/Qwen/Qwen3.6-27B-FP8",
        "status": "busy",
        "updated": "2026-08-03T08:15:00Z",
        "tokens": {
            "input": 182340, "output": 41210, "reasoning": 0,
            "cache_read": 12000, "cache_write": 0,
        },
        "cost_usd": 0.0,
    },
    {
        "id": "ses_mock_002",
        "machine": _MACHINE,
        "project": "social-backend",
        "agent": "bx-plan",
        "title": "Master plan",
        "configured_model": "openai/gpt-5.6-terra",
        "actual_model": "openai/gpt-5.6-terra",
        "status": "idle",
        "updated": "2026-08-03T08:10:00Z",
        "tokens": {
            "input": 12040, "output": 3110, "reasoning": 920,
            "cache_read": 0, "cache_write": 0,
        },
        "cost_usd": 0.18,
    },
]

_USAGE = [
    {
        "model": "biexce-local/vllm/Qwen/Qwen3.6-27B-FP8",
        "zone": "local",
        "agent": "bx-fix",
        "project": "social-backend",
        "sessions": 1,
        "tokens_in": 182340,
        "tokens_out": 41210,
        "tokens_reasoning": 0,
        "cache_read": 12000,
        "cache_write": 0,
        "cost_usd": 0.0,
        "quota_remaining": None,
    },
    {
        "model": "openai/gpt-5.6-terra",
        "zone": "cloud",
        "agent": "bx-plan",
        "project": "social-backend",
        "sessions": 1,
        "tokens_in": 12040,
        "tokens_out": 3110,
        "tokens_reasoning": 920,
        "cache_read": 0,
        "cache_write": 0,
        "cost_usd": 0.18,
        "quota_remaining": None,
    },
]

_EVENT_SCRIPT = [
    {
        "type": "message", "session": "ses_mock_001", "agent": "bx-fix",
        "text": "Đọc evidence FAIL t-002: token expiry off-by-one.",
    },
    {
        "type": "beacon",
        "line": (
            '[BX-STATE] {"project":"social-backend","stage":"B3",'
            '"task":"t-002","status":"fixing","round":2,"done":1,'
            '"total":3,"agent":"bx-fix","note":"fix JWT expiry"}'
        ),
    },
    {
        "type": "tool", "session": "ses_mock_001", "agent": "bx-fix",
        "tool": "edit", "status": "completed",
    },
]

_HARDWARE = {
    "server": "gpu-node-01 (MOCK)",
    "gpus": [
        {
            "index": 0,
            "name": "RTX PRO 6000 96GB",
            "util_pct": 63,
            "mem_used_mb": 41216,
            "mem_total_mb": 98304,
            "temp_c": 58,
            "power_w": 240,
        }
    ],
    "cpu_pct": 22.5,
    "ram_used_gb": 38.1,
    "ram_total_gb": 128.0,
    "vllm": {
        "tokens_per_s": 92.4,
        "running": 1,
        "waiting": 0,
        "gpu_cache_usage_pct": 31.0,
    },
}


class MockSource(AgentSource):
    name = "mock"
    mode = "mock"

    async def sessions(self):
        return snapshot(
            copy.deepcopy(_SESSIONS),
            source=self.name,
            mode=self.mode,
            machine=_MACHINE,
            observed_at="2026-08-03T08:15:00Z",
        )

    async def flow(self):
        return snapshot(
            [copy.deepcopy(_PROJECT_STATE)],
            source=self.name,
            mode=self.mode,
            machine=_MACHINE,
            observed_at=_PROJECT_STATE["updated"],
        )

    async def hardware(self):
        return snapshot(
            copy.deepcopy(_HARDWARE),
            source=self.name,
            mode=self.mode,
            machine="gpu-node-01 (MOCK)",
        )

    async def usage(self):
        return snapshot(
            copy.deepcopy(_USAGE),
            source=self.name,
            mode=self.mode,
            machine=_MACHINE,
            message="Offline fixture; not billing data.",
        )

    async def events(self, limit=None, delay=1.0):
        count = 0
        while True:
            for event in _EVENT_SCRIPT:
                item = copy.deepcopy(event)
                item["seq"] = count
                yield item
                count += 1
                if limit is not None and count >= limit:
                    return
                if delay:
                    await asyncio.sleep(delay)
