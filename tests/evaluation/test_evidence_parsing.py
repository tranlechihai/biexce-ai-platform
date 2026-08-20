from __future__ import annotations

import unittest

from support import temporary_directory, write_junit, write_session

from biexce_control.evaluation.checks import inspect_junit
from biexce_control.evaluation.redaction import redact
from biexce_control.evaluation.session import combine_sessions, inspect_session_export


def _session_summary(started_at: float, ended_at: float) -> dict:
    return {
        "models": [],
        "providers": [],
        "message_count": 0,
        "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0},
        "tool_calls": 0,
        "tool_failures": 0,
        "compactions": 0,
        "errors": 0,
        "started_at_epoch": started_at,
        "ended_at_epoch": ended_at,
    }


class EvidenceParsingTest(unittest.TestCase):
    def test_session_export_is_reduced_to_aggregate_metrics(self):
        with temporary_directory() as root:
            result = inspect_session_export(write_session(root / "session.json"))

        self.assertEqual(result["models"], ["biexce-local/vllm/test-model"])
        self.assertEqual(result["message_count"], 2)
        self.assertEqual(result["tokens"]["input"], 100)
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(result["tool_failures"], 0)
        self.assertEqual(result["duration_seconds"], 5.0)

    def test_parallel_sessions_report_wall_clock_and_agent_time_separately(self):
        sessions = [
            {
                **_session_summary(100.0, 110.0),
                "duration_seconds": 10.0,
            },
            {
                **_session_summary(102.0, 112.0),
                "duration_seconds": 10.0,
            },
        ]

        result = combine_sessions(sessions)

        self.assertEqual(result["duration_seconds"], 12.0)
        self.assertEqual(result["agent_duration_seconds"], 20.0)

    def test_junit_counts_pass_and_failure(self):
        with temporary_directory() as root:
            passed = inspect_junit(write_junit(root / "pass.xml"))
            failed = inspect_junit(write_junit(root / "fail.xml", failures=1))

        self.assertEqual(passed["status"], "PASS")
        self.assertEqual(passed["passed"], 3)
        self.assertEqual(failed["status"], "FAIL")
        self.assertEqual(failed["passed"], 2)

    def test_redaction_removes_structured_and_inline_secrets(self):
        api_key_name = "api" + "_key"
        bearer_value = "Bearer " + "abc.def.ghi.jklmnop"
        sk_value = "s" + "k-" + "example123456789"
        result = redact({
            api_key_name: "secret" + "-value",
            "message": f"Authorization: {bearer_value} and {sk_value}",
            "header": "x-bf-vk: private-key",
        })

        self.assertEqual(result[api_key_name], "[REDACTED]")
        self.assertNotIn("abc.def", result["message"])
        self.assertNotIn(sk_value, result["message"])
        self.assertNotIn("private-key", result["header"])


if __name__ == "__main__":
    unittest.main()
