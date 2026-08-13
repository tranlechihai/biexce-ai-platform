import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPOSITORY_ROOT / "src" / "global" / "runtime" / "session-registry.js"
)


class RuntimeSessionRegistryTests(unittest.TestCase):
    def run_node(self, project, script):
        environment = os.environ.copy()
        environment["MODULE_URL"] = MODULE_PATH.resolve().as_uri()
        environment["PROJECT_ROOT"] = str(project)
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_registry_is_atomic_and_only_active_records_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.run_node(
                project,
                r"""
import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
const registry = await import(process.env.MODULE_URL)
const root = process.env.PROJECT_ROOT
const jobID = "job-explore-r0"

registry.putSessionRecord(root, {
  job_id: jobID,
  session_id: "ses-child",
  parent_session_id: "ses-parent",
  agent: "bx-explore",
  model: "biexce-local/vllm/model",
  status: "ACTIVE",
  attempt: 1,
  last_error: null,
})
assert.equal(registry.resumableSession(root, jobID, "bx-explore").session_id, "ses-child")
registry.putSessionRecord(root, {
  job_id: jobID,
  status: "RETRYING",
  attempt: 2,
  last_error: "TRANSPORT: reset",
})
assert.equal(registry.resumableSession(root, jobID, "bx-explore").attempt, 2)
registry.putSessionRecord(root, {
  job_id: jobID,
  status: "COMPLETED",
  last_error: null,
})
assert.equal(registry.resumableSession(root, jobID, "bx-explore"), null)
const files = fs.readdirSync(path.join(root, ".biexce", "state"))
assert.deepEqual(files, ["AUTOPILOT_SESSIONS.json"])
"""
            )
            registry_path = (
                project / ".biexce" / "state" / "AUTOPILOT_SESSIONS.json"
            )
            value = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(value["sessions"]["job-explore-r0"]["status"], "COMPLETED")
            registry_path.write_text("{}", encoding="utf-8")
            self.run_node(
                project,
                r"""
import assert from "node:assert/strict"
const registry = await import(process.env.MODULE_URL)
assert.throws(
  () => registry.loadSessionRegistry(process.env.PROJECT_ROOT),
  /session registry properties mismatch/,
)
"""
            )


if __name__ == "__main__":
    unittest.main()
