import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from tests.unit.test_scheduler import CLOUD_ROUTING, SchedulerTests


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = REPOSITORY_ROOT / "src" / "global" / "runtime"


@unittest.skipUnless(shutil.which("node"), "Node.js is required for reconciler tests")
class RuntimeReconcilerTests(unittest.TestCase):
    def test_orphaned_running_job_requeues_scheduler_without_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = SchedulerTests(methodName="runTest").make_project(
                Path(temporary)
            )
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const scheduler = await import(process.env.SCHEDULER_URL)
                const board = await import(process.env.BOARD_URL)
                const reconciler = await import(process.env.RECONCILER_URL)
                const root = process.env.PROJECT
                const routing = JSON.parse(process.env.ROUTING)
                const options = {
                  localConcurrency: 1,
                  cloudConcurrency: 3,
                  readOnlyConcurrency: 4,
                }

                scheduler.initializeScheduler(root, options)
                const claimed = scheduler.claimSchedulerJob({
                  projectRoot: root,
                  taskID: "t-001",
                  requestedAgent: "bx-code",
                  routing,
                  options,
                })
                board.putJob(root, {
                  job_id: claimed.job_id,
                  trace_id: "trace-power-loss",
                  task_id: claimed.task_id,
                  agent: claimed.agent,
                  session_id: "lost-child",
                  phase: claimed.phase,
                  status: "RUNNING",
                  dependencies: claimed.dependencies,
                  read_scope: claimed.read_scope,
                  write_scope: claimed.write_scope,
                  model: claimed.model,
                })

                const first = reconciler.reconcileRuntimeState(root)
                const second = reconciler.reconcileRuntimeState(root)
                const state = scheduler.loadSchedulerState(root)
                const persisted = board.loadJobBoard(root)
                const next = scheduler.planSchedulerBatch(root, routing, 2).jobs
                const events = fs.readFileSync(board.jobEventPath(root), "utf8")
                  .trim().split(/\r?\n/).map((line) => JSON.parse(line))

                console.log(JSON.stringify({
                  claimed_job: claimed.job_id,
                  first,
                  second,
                  task: state.tasks["t-001"],
                  job: persisted.jobs[claimed.job_id],
                  next_jobs: next.map((job) => job.job_id),
                  reconcile_events: events.filter((event) =>
                    event.event === "RUNTIME_STATE_RECONCILED"
                  ),
                }))
                """
            )
            environment = os.environ.copy()
            environment.update(
                {
                    "PROJECT": str(project),
                    "ROUTING": json.dumps(CLOUD_ROUTING),
                    "SCHEDULER_URL": (RUNTIME_ROOT / "scheduler.js").as_uri(),
                    "BOARD_URL": (RUNTIME_ROOT / "job-board.js").as_uri(),
                    "RECONCILER_URL": (RUNTIME_ROOT / "reconciler.js").as_uri(),
                }
            )
            result = subprocess.run(
                [shutil.which("node"), "--input-type=module", "-e", script],
                cwd=REPOSITORY_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload["first"]["recovered_jobs"],
                [payload["claimed_job"]],
            )
            self.assertEqual(
                payload["first"]["released_scheduler_jobs"],
                [payload["claimed_job"]],
            )
            self.assertEqual(payload["second"]["released_scheduler_jobs"], [])
            self.assertEqual(payload["task"]["status"], "READY")
            self.assertIsNone(payload["task"]["active_job_id"])
            self.assertEqual(payload["job"]["status"], "QUEUED")
            self.assertEqual(payload["job"]["recovery_count"], 1)
            self.assertIn(payload["claimed_job"], payload["next_jobs"])
            self.assertEqual(
                payload["next_jobs"].count(payload["claimed_job"]),
                1,
            )
            self.assertEqual(len(payload["reconcile_events"]), 1)


if __name__ == "__main__":
    unittest.main()
