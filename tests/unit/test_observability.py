import json
from pathlib import Path
import shutil
import subprocess
import textwrap
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPOSITORY_ROOT / "src" / "global" / "runtime" / "observability.js"


@unittest.skipUnless(shutil.which("node"), "Node.js is required")
class ObservabilityContractTests(unittest.TestCase):
    def run_node(self, script: str) -> dict[str, object]:
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_projection_is_opencode_native_and_contains_no_prompt(self):
        script = textwrap.dedent(
            f"""
            const module = await import({json.dumps(MODULE.as_uri())})
            const update = module.observabilityUpdate({{
              parentSessionId: "parent-1",
              sessionId: "child-1",
              jobId: "job-1",
              traceId: "trace-1",
              agent: "bx-test",
              phase: "TEST",
              taskId: "t-002",
              status: "RETRYING",
              configuredModel: "biexce-local/model-a",
              actualModel: "biexce-local/model-b",
              modelZone: "local",
              attempt: 2,
              fallbackUsed: true,
              sessionResumed: false,
              schedulerRevision: 4,
              dependencies: ["t-001"],
            }})
            console.log(JSON.stringify({{
              update,
              serialized: JSON.stringify(update),
              title: module.childSessionTitle({{
                agent: "bx-test", phase: "TEST", taskId: "t-002",
              }}),
            }}))
            """
        )
        payload = self.run_node(script)
        self.assertEqual(payload["title"], "[BX][t-002][TEST] bx-test")
        self.assertEqual(
            payload["update"]["title"],
            "bx-test | RETRYING | t-002 | TEST | attempt 2",
        )
        metadata = payload["update"]["metadata"]
        self.assertEqual(metadata["contract"], "biexce-observability-v1")
        self.assertEqual(metadata["runtimeStatus"], "RETRYING")
        self.assertEqual(metadata["dependencies"], ["t-001"])
        self.assertNotIn("prompt", payload["serialized"].lower())

    def test_usage_is_real_only_and_accepts_zero_cost(self):
        script = textwrap.dedent(
            f"""
            const module = await import({json.dumps(MODULE.as_uri())})
            const missing = module.responseUsage({{ parts: [] }})
            const present = module.responseUsage({{
              info: {{
                cost: 0,
                time: {{ created: 1000, completed: 1750 }},
                tokens: {{
                  input: 120,
                  output: 30,
                  reasoning: 8,
                  cache: {{ read: 10, write: 2 }},
                }},
              }},
              parts: [],
            }})
            console.log(JSON.stringify({{ missing, present }}))
            """
        )
        payload = self.run_node(script)
        self.assertIsNone(payload["missing"])
        self.assertEqual(payload["present"]["inputTokens"], 120)
        self.assertEqual(payload["present"]["outputTokens"], 30)
        self.assertEqual(payload["present"]["reasoningTokens"], 8)
        self.assertEqual(payload["present"]["cacheReadTokens"], 10)
        self.assertEqual(payload["present"]["cacheWriteTokens"], 2)
        self.assertEqual(payload["present"]["cost"], 0)
        self.assertEqual(payload["present"]["durationMs"], 750)

    def test_error_projection_exposes_codes_not_sensitive_detail(self):
        script = textwrap.dedent(
            f"""
            const module = await import({json.dumps(MODULE.as_uri())})
            const update = module.observabilityUpdate({{
              parentSessionId: "parent-1",
              sessionId: "child-1",
              jobId: "job-1",
              agent: "bx-code",
              phase: "CODE",
              taskId: "t-003",
              status: "ERROR",
              errorCode: "TIMEOUT",
              errorKind: "TRANSPORT",
              error: "secret token must never be projected",
            }})
            console.log(JSON.stringify(update))
            """
        )
        payload = self.run_node(script)
        serialized = json.dumps(payload)
        self.assertIn("TIMEOUT", serialized)
        self.assertIn("TRANSPORT", serialized)
        self.assertNotIn("secret token", serialized)


if __name__ == "__main__":
    unittest.main()
