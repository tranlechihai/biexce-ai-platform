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
    repeat: bool = False,
    director: str = "orchestrator",
    include_recovery_message: bool = False,
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
const messages = [{
  info: {
    id: "objective", role: "user", agent: process.env.BX_DIRECTOR,
    model: { providerID: "openai", modelID: "gpt-test" },
  },
  parts: [{ type: "text", text: "build it" }],
}]
if (process.env.BX_RECOVERY_MESSAGE === "1") {
  messages.push({
    info: {
      id: "recovery", role: "user", agent: process.env.BX_DIRECTOR,
      model: { providerID: "openai", modelID: "gpt-test" },
    },
    parts: [{
      type: "text", text: "resume", synthetic: true,
      metadata: {
        "biexce.restartRecovery": "biexce.restart-recovery.v1",
      },
    }],
  })
}
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
  messages: ({ path, query }) => response(
    path.id === "parent" && query.directory === directory ? messages : [],
  ),
  promptAsync: (input) => { calls.push(input); return response(undefined) },
} }
const seen = new Set()
const result = await plugin.recoverInterruptedParent(client, directory, { seen })
const repeated = process.env.BX_REPEAT === "1"
  ? await plugin.recoverInterruptedParent(client, directory, { seen })
  : undefined
console.log(JSON.stringify({ result, repeated, calls }))
"""
    environment = os.environ | {
        "BX_PLUGIN": str(PLUGIN),
        "BX_TODO_STATUS": todo_status,
        "BX_PARENT_STATUS": parent_status or "",
        "BX_CHILD_STATUS": child_status or "",
        "BX_REPEAT": "1" if repeat else "0",
        "BX_DIRECTOR": director,
        "BX_RECOVERY_MESSAGE": "1" if include_recovery_message else "0",
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

    def test_waits_for_active_child_and_wakes_after_child_stops(self):
        active = run_scenario("pending", None, "busy")
        stopped = run_scenario("pending", None)
        self.assertEqual("nothing-to-recover", active["result"]["status"])
        self.assertEqual([], active["calls"])
        stopped_prompt = stopped["calls"][0]["body"]["parts"][0]["text"]
        self.assertIn("child | idle-or-stopped", stopped_prompt)
        self.assertIn("re-dispatch only the unfinished lane", stopped_prompt)
        self.assertIn("Never redo verified completed work", stopped_prompt)
        self.assertNotIn("PROJECT_STATE", stopped_prompt)
        self.assertNotIn("clear lock", stopped_prompt)

    def test_same_snapshot_is_woken_only_once(self):
        result = run_scenario(
            "in_progress",
            None,
            repeat=True,
            include_recovery_message=True,
        )
        self.assertEqual("woken", result["result"]["status"])
        self.assertEqual("already-woken", result["repeated"]["status"])
        self.assertEqual(1, len(result["calls"]))

    def test_user_facing_director_is_preserved(self):
        result = run_scenario("pending", None, director="bx-director")
        request = result["calls"][0]
        self.assertEqual("bx-director", request["body"]["agent"])


if __name__ == "__main__":
    unittest.main()
