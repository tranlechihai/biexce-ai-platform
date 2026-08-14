from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "src" / "global" / "slim" / "runtime" / "recovery-core.js"


def run_scenario(
    todo_status: str,
    parent_status: str | None,
    child_status: str | None = None,
):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for plugin behavior tests")
    script = r"""
import { pathToFileURL } from "node:url"
const plugin = await import(pathToFileURL(process.env.BX_PLUGIN).href)
const calls = []
const directory = "C:/workspace"
const status = {}
if (process.env.BX_PARENT_STATUS) {
  status.parent = { type: process.env.BX_PARENT_STATUS }
}
if (process.env.BX_CHILD_STATUS) {
  status.child = { type: process.env.BX_CHILD_STATUS }
}
const response = (data) => Promise.resolve({ data })
const client = { session: {
  list: () => response([
    { id: "older", directory, title: "old", time: { created: 1, updated: 99 } },
    { id: "parent", directory, title: "current", time: { created: 2, updated: 2 } },
  ]),
  status: () => response(status),
  todo: ({ path, query }) => response(path.id === "parent" && query.directory === directory ? [
    { id: "t-1", content: "finish work", status: process.env.BX_TODO_STATUS },
  ] : []),
  children: () => response([{ id: "child", title: "BX-Code" }]),
  messages: ({ path, query }) => response(path.id === "parent" && query.directory === directory ? [{
    info: {
      role: "user", agent: "orchestrator",
      model: { providerID: "openai", modelID: "gpt-test" },
    },
    parts: [{ type: "text", text: "build it" }],
  }] : []),
  promptAsync: (input) => { calls.push(input); return response(undefined) },
} }
const result = await plugin.recoverInterruptedParent(client, directory)
console.log(JSON.stringify({ result, calls }))
"""
    environment = os.environ | {
        "BX_PLUGIN": str(PLUGIN),
        "BX_TODO_STATUS": todo_status,
        "BX_PARENT_STATUS": parent_status or "",
        "BX_CHILD_STATUS": child_status or "",
    }
    completed = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True,
        check=True,
        encoding="utf-8",
        env=environment,
    )
    return json.loads(completed.stdout)


class RecoveryBridgeTests(unittest.TestCase):
    def test_wakes_latest_idle_orchestrator_with_incomplete_todo(self):
        result = run_scenario("in_progress", None)
        self.assertEqual("woken", result["result"]["status"])
        self.assertEqual("parent", result["result"]["sessionID"])
        self.assertEqual(1, len(result["calls"]))
        request = result["calls"][0]
        self.assertEqual("parent", request["path"]["id"])
        self.assertEqual("C:/workspace", request["query"]["directory"])
        self.assertTrue(request["throwOnError"])
        self.assertEqual("orchestrator", request["body"]["agent"])
        self.assertTrue(request["body"]["parts"][0]["synthetic"])
        self.assertIn(
            "child | idle-or-stopped",
            request["body"]["parts"][0]["text"],
        )

    def test_does_not_wake_active_or_completed_session(self):
        for todo_status, parent_status in (
            ("in_progress", "busy"),
            ("completed", None),
        ):
            with self.subTest(todo=todo_status, parent=parent_status):
                result = run_scenario(todo_status, parent_status)
                self.assertEqual("nothing-to-recover", result["result"]["status"])
                self.assertEqual([], result["calls"])

    def test_recovery_prompt_distinguishes_active_and_stopped_children(self):
        active = run_scenario("pending", None, "busy")
        stopped = run_scenario("pending", None)
        active_prompt = active["calls"][0]["body"]["parts"][0]["text"]
        stopped_prompt = stopped["calls"][0]["body"]["parts"][0]["text"]
        self.assertIn("child | busy", active_prompt)
        self.assertIn("If a child is active, monitor it", active_prompt)
        self.assertIn("child | idle-or-stopped", stopped_prompt)
        self.assertIn("re-dispatch only the unfinished lane", stopped_prompt)
        for prompt in (active_prompt, stopped_prompt):
            self.assertIn("Never redo verified completed work", prompt)
            self.assertNotIn("PROJECT_STATE", prompt)
            self.assertNotIn("clear lock", prompt)


if __name__ == "__main__":
    unittest.main()
