import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY_ROOT / "src" / "global" / "runtime" / "job-board.js"


@unittest.skipUnless(shutil.which("node"), "Node.js is required for job board tests")
class PersistentJobBoardTests(unittest.TestCase):
    def test_task_result_history_persists_authoritative_handoffs(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            (project / ".biexce" / "state").mkdir(parents=True)
            script = textwrap.dedent(
                """
                const board = await import(process.env.MODULE_URL)
                const root = process.env.PROJECT
                board.putJob(root, {
                  job_id: "job-t-001-test-bx-test-r0",
                  trace_id: "trace-t-001-test",
                  task_id: "t-001",
                  agent: "bx-test",
                  phase: "TEST",
                  status: "COMPLETED",
                  dependencies: [],
                  read_scope: [".biexce/tasks/t-001.md"],
                  write_scope: [],
                  model: "openai/test",
                  result_status: "PASS",
                })
                const result = {
                  status: "PASS",
                  summary: "11 unit tests passed",
                  changed_files: [],
                  checks: [{
                    command: "python -m unittest discover -s tests -v",
                    exit_code: 0,
                    status: "PASS",
                    output_summary: "11/11 passed",
                  }],
                  artifacts: [],
                }
                board.recordJobResult(
                  root,
                  "job-t-001-test-bx-test-r0",
                  result,
                  "runtime-evidence",
                )
                const history = board.taskResultHistory(root, "t-001")
                console.log(JSON.stringify(history))
                """
            )
            environment = os.environ.copy()
            environment["MODULE_URL"] = MODULE_PATH.resolve().as_uri()
            environment["PROJECT"] = str(project)
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
            history = json.loads(result.stdout)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["event"], "JOB_RESULT_RECORDED")
            self.assertEqual(history[0]["phase"], "TEST")
            self.assertEqual(history[0]["result"]["status"], "PASS")
            self.assertEqual(history[0]["result"]["checks"][0]["exit_code"], 0)

    def test_jobs_leases_atomic_snapshot_and_restart_reconciliation(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            (project / ".biexce" / "state").mkdir(parents=True)
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const board = await import(process.env.MODULE_URL)
                const root = process.env.PROJECT
                const base = (jobID, taskID) => ({
                  job_id: jobID,
                  trace_id: `trace-${taskID}`,
                  task_id: taskID,
                  agent: "bx-code",
                  phase: "CODE",
                  status: "RUNNING",
                  dependencies: [],
                  read_scope: [`.biexce/tasks/${taskID}.md`],
                  write_scope: [`src/${taskID}.py`],
                  model: "biexce-local/model",
                })

                board.putJob(root, base("job-t-001-code", "t-001"))
                board.putJob(root, base("job-t-002-code", "t-002"))
                const leaseOne = board.acquireJobLease(
                  root, "job-t-001-code", "session-one", 60000,
                )
                const leaseTwo = board.acquireJobLease(
                  root, "job-t-002-code", "session-two", 60000,
                )
                const simultaneous = board.loadJobBoard(root)

                const releasedOne = board.releaseJobLease(root, leaseOne)
                const replacementOne = board.acquireJobLease(
                  root, "job-t-001-code", "session-one-new", 60000,
                )
                const staleRelease = board.releaseJobLease(root, leaseOne)
                const replacementStillExists = fs.existsSync(
                  board.jobLeasePath(root, "job-t-001-code"),
                )

                const leaseTwoPath = board.jobLeasePath(root, "job-t-002-code")
                const expiredTwo = JSON.parse(fs.readFileSync(leaseTwoPath, "utf8"))
                expiredTwo.deadline_at_utc = "2000-01-01T00:00:00.000Z"
                fs.writeFileSync(leaseTwoPath, `${JSON.stringify(expiredTwo, null, 2)}\\n`)
                const replacementTwo = board.acquireJobLease(
                  root, "job-t-002-code", "session-two-new", 60000,
                )

                board.releaseJobLease(root, replacementOne)
                board.releaseJobLease(root, replacementTwo)
                const completedAt = new Date().toISOString()
                board.putJob(root, {
                  job_id: "job-t-001-code",
                  status: "COMPLETED",
                  completed_at_utc: completedAt,
                  result_status: "SUCCEEDED",
                })
                board.putJob(root, {
                  job_id: "job-t-002-code",
                  status: "COMPLETED",
                  completed_at_utc: completedAt,
                  result_status: "SUCCEEDED",
                })

                board.putJob(root, base("job-t-003-code", "t-003"))
                const snapshotPath = board.jobBoardPath(root)
                const sidecar = `${snapshotPath}.simulated-crash.tmp`
                fs.writeFileSync(sidecar, "{broken")
                const beforeReconcile = board.loadJobBoard(root)
                const reconciled = board.reconcileJobBoard(root)
                const afterReconcile = board.loadJobBoard(root)
                const events = fs.readFileSync(board.jobEventPath(root), "utf8")
                  .trim().split(/\\r?\\n/).map((line) => JSON.parse(line))

                console.log(JSON.stringify({
                  simultaneousJobs: Object.keys(simultaneous.jobs).sort(),
                  twoLeaseFiles: [leaseOne, leaseTwo].every((lease) =>
                    typeof lease.token === "string" && lease.token.length > 0
                  ),
                  releasedOne,
                  staleRelease,
                  replacementStillExists,
                  timeoutReplacedToken: replacementTwo.token !== leaseTwo.token,
                  sidecarIgnored: beforeReconcile.jobs["job-t-003-code"].status === "RUNNING",
                  recovered: reconciled.recovered,
                  recoveredStatus: afterReconcile.jobs["job-t-003-code"].status,
                  recoveryCount: afterReconcile.jobs["job-t-003-code"].recovery_count,
                  eventNames: events.map((event) => event.event),
                }))
                """
            )
            environment = os.environ.copy()
            environment["MODULE_URL"] = MODULE_PATH.resolve().as_uri()
            environment["PROJECT"] = str(project)
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
                payload["simultaneousJobs"],
                ["job-t-001-code", "job-t-002-code"],
            )
            self.assertTrue(payload["twoLeaseFiles"])
            self.assertTrue(payload["releasedOne"])
            self.assertFalse(payload["staleRelease"])
            self.assertTrue(payload["replacementStillExists"])
            self.assertTrue(payload["timeoutReplacedToken"])
            self.assertTrue(payload["sidecarIgnored"])
            self.assertEqual(payload["recovered"], ["job-t-003-code"])
            self.assertEqual(payload["recoveredStatus"], "QUEUED")
            self.assertEqual(payload["recoveryCount"], 1)
            self.assertIn("JOB_REQUEUED_AFTER_RESTART", payload["eventNames"])


if __name__ == "__main__":
    unittest.main()
