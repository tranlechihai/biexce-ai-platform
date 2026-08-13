import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY_ROOT / "src" / "global" / "runtime" / "scheduler.js"
CLOUD_ROUTING = {
    agent: {"primary": "cloud/model"}
    for agent in ("bx-code", "bx-test", "bx-fix", "bx-review")
}
LOCAL_ROUTING = {
    agent: {"primary": "biexce-local/vllm/model"}
    for agent in ("bx-code", "bx-test", "bx-fix", "bx-review")
}


@unittest.skipUnless(shutil.which("node"), "Node.js is required for scheduler tests")
class SchedulerTests(unittest.TestCase):
    def make_project(
        self,
        root: Path,
        *,
        second_scope: str = "src/two.py",
    ) -> Path:
        project = root / "project"
        task_root = project / ".biexce" / "tasks"
        state_root = project / ".biexce" / "state"
        task_root.mkdir(parents=True)
        state_root.mkdir(parents=True)
        (project / ".biexce" / "MASTER_PLAN.md").write_text(
            "# Plan\n\nWIP limit: 2\nFix cap: 3\n",
            encoding="utf-8",
        )
        contracts = {
            "t-001": ("src/one.py", "none"),
            "t-002": (second_scope, "none"),
            "t-003": ("src/three.py", "t-001"),
        }
        for task_id, (scope, dependency) in contracts.items():
            (task_root / f"{task_id}.md").write_text(
                "\n".join(
                    [
                        f"# {task_id}",
                        "",
                        "Owner role: bx-code",
                        f"Writable files: {scope}",
                        "Read-only inputs: src/shared.py",
                        f"Depends on: {dependency}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        state = {
            "project": "scheduler-test",
            "stage": "B2",
            "updated": "2026-08-06T00:00:00Z",
            "tasks": [
                {
                    "id": task_id,
                    "title": f"task {task_id}",
                    "status": "backlog",
                    "round": 0,
                    "agent": None,
                }
                for task_id in contracts
            ],
        }
        (state_root / "PROJECT_STATE.json").write_text(
            json.dumps(state, indent=2) + "\n",
            encoding="utf-8",
        )
        return project

    def run_node(
        self,
        project: Path,
        script: str,
        *,
        routing: dict[str, object] = CLOUD_ROUTING,
    ) -> dict[str, object]:
        environment = os.environ.copy()
        environment["MODULE_URL"] = MODULE_PATH.resolve().as_uri()
        environment["PROJECT"] = str(project)
        environment["ROUTING"] = json.dumps(routing)
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
        return json.loads(result.stdout)

    def test_disjoint_source_writers_are_serialized_in_one_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const one = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
let error = null
try {
  scheduler.claimSchedulerJob({
    projectRoot: root, taskID: "t-002", routing, options,
  })
} catch (caught) {
  error = caught.message
}
const waiting = scheduler.listSchedulerJobs(root, routing).jobs.find(
  (job) => job.task_id === "t-003",
)
console.log(JSON.stringify({ one, error, waiting }))
""",
            )
            self.assertEqual(result["one"]["status"], "RUNNING")
            self.assertIn("SCHEDULER_QUEUED", result["error"])
            self.assertIn("workspace writer is active", result["error"])
            self.assertEqual(result["waiting"]["status"], "WAITING_DEPENDENCY")

    def test_overlapping_writer_is_queued(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(
                Path(temporary),
                second_scope="src/one.py",
            )
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
let error = null
try {
  scheduler.claimSchedulerJob({
    projectRoot: root, taskID: "t-002", routing, options,
  })
} catch (caught) {
  error = caught.message
}
console.log(JSON.stringify({ error }))
""",
            )
            self.assertIn("SCHEDULER_QUEUED", result["error"])
            self.assertIn("write scope conflicts", result["error"])

    def test_local_concurrency_one_queues_second_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
let error = null
try {
  scheduler.claimSchedulerJob({
    projectRoot: root, taskID: "t-002", routing, options,
  })
} catch (caught) {
  error = caught.message
}
console.log(JSON.stringify({ error }))
""",
                routing=LOCAL_ROUTING,
            )
            self.assertIn("SCHEDULER_WAITING_MODEL", result["error"])
            self.assertIn("local model concurrency reached", result["error"])

    def test_dependency_becomes_ready_only_after_full_task_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const before = scheduler.listSchedulerJobs(root, routing).jobs.find(
  (job) => job.task_id === "t-003",
).status
for (const result of ["SUCCEEDED", "PASS", "APPROVE"]) {
  const job = scheduler.claimSchedulerJob({
    projectRoot: root, taskID: "t-001", routing, options,
  })
  scheduler.completeSchedulerJob(root, job.job_id, result)
}
const after = scheduler.listSchedulerJobs(root, routing).jobs.find(
  (job) => job.task_id === "t-003",
).status
console.log(JSON.stringify({ before, after }))
""",
            )
            self.assertEqual(result["before"], "WAITING_DEPENDENCY")
            self.assertEqual(result["after"], "READY")

    def test_failed_code_check_routes_to_bounded_fix_not_same_code_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const code = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", requestedAgent: "bx-code",
  routing, options,
})
const completed = scheduler.completeSchedulerJob(root, code.job_id, "FAILED")
let duplicate = null
try {
  scheduler.claimSchedulerJob({
    projectRoot: root, taskID: "t-001", requestedAgent: "bx-code",
    routing, options,
  })
} catch (error) {
  duplicate = error.message
}
const fix = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", requestedAgent: "bx-fix",
  routing, options,
})
console.log(JSON.stringify({ code, completed, duplicate, fix }))
""",
            )
            self.assertEqual(result["completed"]["task"]["phase"], "FIX")
            self.assertEqual(result["completed"]["task"]["status"], "READY")
            self.assertEqual(result["completed"]["task"]["fix_round"], 1)
            self.assertIn("requires bx-fix, not bx-code", result["duplicate"])
            self.assertEqual(result["fix"]["phase"], "FIX")
            self.assertEqual(result["fix"]["agent"], "bx-fix")

    def test_legacy_completed_failed_writer_migrates_to_bounded_fix(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const jobs = await import(new URL("./job-board.js", process.env.MODULE_URL))
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const code = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", requestedAgent: "bx-code",
  routing, options,
})
jobs.putJob(root, {
  ...code,
  trace_id: "trace-legacy-failed",
  status: "COMPLETED",
  started_at_utc: "2026-08-12T01:00:00Z",
  completed_at_utc: "2026-08-12T01:01:00Z",
  result_status: "FAILED",
})
scheduler.releaseSchedulerJob(
  root,
  code.job_id,
  "Legacy runtime terminal-blocked a validated structured failure",
  { recoverable: false },
)
const recovery = scheduler.recoverSchedulerBlockers(
  root,
  { allowStandard: true },
)
const fix = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", requestedAgent: "bx-fix",
  routing, options,
})
console.log(JSON.stringify({ recovery, fix }))
""",
            )
            self.assertEqual(
                result["recovery"]["recovery_reasons"],
                {"t-001": "CHECK_FAILED"},
            )
            self.assertEqual(result["fix"]["phase"], "FIX")
            self.assertEqual(result["fix"]["agent"], "bx-fix")
            self.assertEqual(result["fix"]["fix_round"], 1)

    def test_each_phase_gets_its_own_job_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const code = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.completeSchedulerJob(root, code.job_id, "SUCCEEDED")
const test = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
console.log(JSON.stringify({ code, test }))
""",
            )
            self.assertNotEqual(result["code"]["job_id"], result["test"]["job_id"])
            self.assertIn("-code-bx-code-", result["code"]["job_id"])
            self.assertIn("-test-bx-test-", result["test"]["job_id"])

    def test_verification_only_task_starts_with_bx_test(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            task_path = project / ".biexce" / "tasks" / "t-001.md"
            task_path.write_text(
                task_path.read_text(encoding="utf-8")
                .replace("Owner role: bx-code", "Owner role: bx-test")
                .replace("Writable files: src/one.py", "Writable files: none"),
                encoding="utf-8",
            )
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const before = scheduler.listSchedulerJobs(root, routing).jobs.find(
  (job) => job.task_id === "t-001",
)
const test = scheduler.claimSchedulerJob({
  projectRoot: root,
  taskID: "t-001",
  requestedAgent: "bx-test",
  routing,
  options,
})
scheduler.completeSchedulerJob(root, test.job_id, "PASS")
const review = scheduler.claimSchedulerJob({
  projectRoot: root,
  taskID: "t-001",
  requestedAgent: "bx-review",
  routing,
  options,
})
console.log(JSON.stringify({ before, test, review }))
""",
            )
            self.assertEqual(result["before"]["phase"], "TEST")
            self.assertEqual(result["before"]["agent"], "bx-test")
            self.assertEqual(result["test"]["phase"], "TEST")
            self.assertEqual(result["test"]["write_scope"], [])
            self.assertEqual(result["review"]["phase"], "TASK_REVIEW")

    def test_verification_report_task_starts_with_bx_test_and_only_owns_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            task_path = project / ".biexce" / "tasks" / "t-001.md"
            task_path.write_text(
                task_path.read_text(encoding="utf-8")
                .replace("Owner role: bx-code", "Owner role: bx-test")
                .replace(
                    "Writable files: src/one.py",
                    "Writable files: .biexce/reports/integration-regression.md",
                ),
                encoding="utf-8",
            )
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
scheduler.initializeScheduler(root, {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
})
const listed = scheduler.listSchedulerJobs(root, routing).jobs.find(
  (job) => job.task_id === "t-001",
)
const claimed = scheduler.claimSchedulerJob({
  projectRoot: root,
  taskID: "t-001",
  requestedAgent: "bx-test",
  routing,
})
console.log(JSON.stringify({ listed, claimed }))
""",
            )
            expected = [".biexce/reports/integration-regression.md"]
            self.assertEqual(result["listed"]["phase"], "TEST")
            self.assertEqual(result["listed"]["agent"], "bx-test")
            self.assertEqual(result["claimed"]["write_scope"], expected)

    def test_legacy_verification_only_code_blocker_recovers_to_test(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            blocked = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const code = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
const released = scheduler.releaseSchedulerJob(
  root,
  code.job_id,
  "CONTRACT: verification-only owner role bx-test routing/ownership conflict",
  { recoverable: false },
)
console.log(JSON.stringify({ code, released }))
""",
            )
            self.assertEqual(blocked["released"]["task"]["phase"], "BLOCKED")
            task_path = project / ".biexce" / "tasks" / "t-001.md"
            task_path.write_text(
                task_path.read_text(encoding="utf-8")
                .replace("Owner role: bx-code", "Owner role: bx-test")
                .replace(
                    "Writable files: src/one.py",
                    "Writable files: .biexce/reports/integration-regression.md",
                ),
                encoding="utf-8",
            )
            recovered = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const recovery = scheduler.recoverSchedulerBlockers(root, { allowStandard: true })
const next = scheduler.claimSchedulerJob({
  projectRoot: root,
  taskID: "t-001",
  requestedAgent: "bx-test",
  routing,
})
console.log(JSON.stringify({ recovery, next }))
""",
            )
            self.assertEqual(recovered["recovery"]["recovered_tasks"], ["t-001"])
            self.assertEqual(recovered["next"]["phase"], "TEST")
            self.assertEqual(recovered["next"]["agent"], "bx-test")
            self.assertEqual(
                recovered["next"]["write_scope"],
                [".biexce/reports/integration-regression.md"],
            )

    def test_generated_python_artifact_blocker_recovers_only_to_test(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const code = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.completeSchedulerJob(root, code.job_id, "SUCCEEDED")
const test = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.releaseSchedulerJob(
  root,
  test.job_id,
  "CONTRACT: runtime diff exceeds writable scope: src/__pycache__/one.cpython-313.pyc",
  { recoverable: false },
)
const recovery = scheduler.recoverSchedulerBlockers(root)
const recovered = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
console.log(JSON.stringify({ code, test, recovery, recovered }))
""",
            )
            self.assertTrue(result["recovery"]["changed"])
            self.assertEqual(result["recovery"]["recovered_tasks"], ["t-001"])
            self.assertEqual(result["recovered"]["phase"], "TEST")
            self.assertEqual(result["recovered"]["agent"], "bx-test")
            self.assertNotEqual(result["code"]["job_id"], result["recovered"]["job_id"])

    def test_legacy_unittest_na_blocker_recovers_only_when_tests_exist(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            (project / ".biexce" / "PROJECT_BRIEF.md").write_text(
                "# Brief\n\nPython standard library with unittest.\n",
                encoding="utf-8",
            )
            task_path = project / ".biexce" / "tasks" / "t-001.md"
            task_path.write_text(
                task_path.read_text(encoding="utf-8")
                + "\nVerify: `N/A — legacy command omitted`\n",
                encoding="utf-8",
            )
            test_root = project / "tests"
            test_root.mkdir()
            (test_root / "test_one.py").write_text(
                "import unittest\n",
                encoding="utf-8",
            )
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const code = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.completeSchedulerJob(root, code.job_id, "SUCCEEDED")
const test = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.completeSchedulerJob(root, test.job_id, "INCONCLUSIVE")
const retry = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.completeSchedulerJob(root, retry.job_id, "INCONCLUSIVE")
const recovery = scheduler.recoverSchedulerBlockers(root)
const recovered = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
console.log(JSON.stringify({ recovery, recovered }))
""",
            )
            self.assertTrue(result["recovery"]["changed"])
            self.assertEqual(result["recovery"]["recovered_tasks"], ["t-001"])
            self.assertEqual(result["recovered"]["phase"], "TEST")
            self.assertEqual(result["recovered"]["agent"], "bx-test")

    def test_real_out_of_scope_blocker_is_not_auto_recovered(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const code = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.completeSchedulerJob(root, code.job_id, "SUCCEEDED")
const test = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.releaseSchedulerJob(
  root,
  test.job_id,
  "CONTRACT: runtime diff exceeds writable scope: secrets.txt",
  { recoverable: false },
)
const recovery = scheduler.recoverSchedulerBlockers(root, { allowStandard: true })
const snapshot = scheduler.listSchedulerJobs(root, routing).jobs.find(
  (job) => job.task_id === "t-001",
)
console.log(JSON.stringify({ recovery, snapshot }))
""",
            )
            self.assertFalse(result["recovery"]["changed"])
            self.assertEqual(result["snapshot"]["status"], "BLOCKED")

    def test_standard_legacy_project_scope_drift_reverifies_before_fix(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const jobs = await import(new URL("./job-board.js", process.env.MODULE_URL))
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const code = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
jobs.putJob(root, {
  ...code,
  trace_id: "trace-legacy-scope",
  status: "FAILED",
  completed_at_utc: "2026-08-12T01:05:00Z",
  result_status: null,
  error: "CONTRACT: runtime diff exceeds writable scope: tests/test_old_contract.py",
})
scheduler.releaseSchedulerJob(
  root,
  code.job_id,
  "Legacy blocked task not eligible for runtime migration",
  { recoverable: false },
)
const recovery = scheduler.recoverSchedulerBlockers(root, {
  allowStandard: true,
})
const recovered = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", requestedAgent: "bx-test", routing, options,
})
scheduler.completeSchedulerJob(root, recovered.job_id, "FAIL")
const fix = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", requestedAgent: "bx-fix", routing, options,
})
console.log(JSON.stringify({ recovery, recovered, fix }))
""",
            )
            self.assertEqual(
                result["recovery"]["recovery_reasons"],
                {"t-001": "PROJECT_SCOPE_REVERIFY"},
            )
            self.assertEqual(result["recovered"]["phase"], "TEST")
            self.assertEqual(result["recovered"]["agent"], "bx-test")
            self.assertEqual(result["fix"]["phase"], "FIX")
            self.assertEqual(result["fix"]["agent"], "bx-fix")
            self.assertEqual(result["fix"]["fix_round"], 1)

    def test_standard_legacy_scope_summary_without_paths_reverifies(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const code = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.releaseSchedulerJob(
  root,
  code.job_id,
  "CONTRACT: read-only test conflicts with approved task writable scope",
  { recoverable: false },
)
const recovery = scheduler.recoverSchedulerBlockers(root, {
  allowStandard: true,
})
const recovered = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", requestedAgent: "bx-test", routing, options,
})
console.log(JSON.stringify({ recovery, recovered }))
""",
            )
            self.assertEqual(
                result["recovery"]["recovery_reasons"],
                {"t-001": "PROJECT_SCOPE_REVERIFY"},
            )
            self.assertEqual(result["recovered"]["phase"], "TEST")

    def test_standard_fix_cap_gets_one_audited_adjudication(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
import fs from "node:fs"
const scheduler = await import(process.env.MODULE_URL)
const reconciler = await import(
  new URL("./reconciler.js", process.env.MODULE_URL)
)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const statePath = scheduler.schedulerStatePath(root)
const state = JSON.parse(fs.readFileSync(statePath, "utf8"))
state.tasks["t-001"] = {
  ...state.tasks["t-001"],
  phase: "BLOCKED",
  status: "BLOCKED",
  fix_round: 3,
  last_job_id: "job-t-001-task_review-bx-review-r3",
  last_result: "CHANGES_REQUIRED",
  error: "Fix cap blocked t-001",
}
fs.writeFileSync(statePath, JSON.stringify(state, null, 2) + "\n")

const first = reconciler.reconcileRuntimeState(root, {
  recoverBlockers: true,
  allowStandard: true,
  phaseByTask: { "t-001": "TASK_REVIEW" },
})
const fix = scheduler.claimSchedulerJob({
  projectRoot: root,
  taskID: "t-001",
  requestedAgent: "bx-fix",
  routing,
  options,
})
scheduler.completeSchedulerJob(root, fix.job_id, "SUCCEEDED")
const test = scheduler.claimSchedulerJob({
  projectRoot: root,
  taskID: "t-001",
  requestedAgent: "bx-test",
  routing,
  options,
})
scheduler.completeSchedulerJob(root, test.job_id, "FAIL")
const second = reconciler.reconcileRuntimeState(root, {
  recoverBlockers: true,
  allowStandard: true,
  phaseByTask: { "t-001": "TEST" },
})
const snapshot = scheduler.listSchedulerJobs(root, routing).jobs.find(
  (job) => job.task_id === "t-001",
)
console.log(JSON.stringify({ first, fix, test, second, snapshot }))
""",
            )
            self.assertEqual(result["first"]["recovered_tasks"], ["t-001"])
            self.assertEqual(
                result["first"]["recovered_routes"], {"t-001": "FIX"}
            )
            self.assertEqual(
                result["first"]["recovery_reasons"],
                {"t-001": "FIX_CAP_STANDARD_ADJUDICATION"},
            )
            self.assertEqual(result["fix"]["fix_round"], 3)
            self.assertEqual(result["test"]["fix_round"], 3)
            self.assertEqual(result["second"]["recovered_tasks"], [])
            self.assertEqual(result["snapshot"]["status"], "BLOCKED")
            self.assertEqual(result["snapshot"]["fix_round"], 3)

    def test_critical_fix_cap_remains_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
import fs from "node:fs"
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const statePath = scheduler.schedulerStatePath(root)
const state = JSON.parse(fs.readFileSync(statePath, "utf8"))
state.tasks["t-001"] = {
  ...state.tasks["t-001"],
  phase: "BLOCKED",
  status: "BLOCKED",
  fix_round: 3,
  last_job_id: "job-t-001-task_review-bx-review-r3",
  last_result: "CHANGES_REQUIRED",
  error: "Fix cap blocked t-001",
}
fs.writeFileSync(statePath, JSON.stringify(state, null, 2) + "\n")
const recovery = scheduler.recoverSchedulerBlockers(root, {
  allowStandard: false,
  phaseByTask: { "t-001": "TASK_REVIEW" },
})
const snapshot = scheduler.listSchedulerJobs(root, routing).jobs.find(
  (job) => job.task_id === "t-001",
)
console.log(JSON.stringify({ recovery, snapshot }))
""",
            )
            self.assertFalse(result["recovery"]["changed"])
            self.assertEqual(result["snapshot"]["status"], "BLOCKED")

    def test_historical_parallel_diff_blocker_recovers_to_original_phase(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const jobs = await import(new URL("./job-board.js", process.env.MODULE_URL))
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const one = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
const two = scheduler.listSchedulerJobs(root, routing).jobs.find(
  (job) => job.task_id === "t-002",
)
jobs.putJob(root, {
  ...one,
  trace_id: "trace-one",
  status: "FAILED",
  started_at_utc: "2026-08-12T01:00:00Z",
  completed_at_utc: "2026-08-12T01:05:00Z",
  error: "parallel diff was attributed to this job",
})
jobs.putJob(root, {
  ...two,
  trace_id: "trace-two",
  status: "COMPLETED",
  started_at_utc: "2026-08-12T01:01:00Z",
  completed_at_utc: "2026-08-12T01:02:00Z",
  result_status: "SUCCEEDED",
})
scheduler.releaseSchedulerJob(
  root,
  one.job_id,
  "CONTRACT: runtime diff exceeds writable scope: src/two.py",
  { recoverable: false },
)
const recovery = scheduler.recoverSchedulerBlockers(root, { allowStandard: true })
const recovered = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
console.log(JSON.stringify({ recovery, recovered }))
""",
            )
            self.assertEqual(
                result["recovery"]["recovery_reasons"],
                {"t-001": "PARALLEL_DIFF_ATTRIBUTION"},
            )
            self.assertEqual(result["recovered"]["phase"], "CODE")
            self.assertEqual(result["recovered"]["agent"], "bx-code")

    def test_cross_task_diff_without_job_history_gets_one_fresh_baseline_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const first = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.releaseSchedulerJob(
  root,
  first.job_id,
  "CONTRACT: runtime diff exceeds writable scope: src/two.py",
  { recoverable: false },
)
const firstRecovery = scheduler.recoverSchedulerBlockers(root)
const retry = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.releaseSchedulerJob(
  root,
  retry.job_id,
  "CONTRACT: runtime diff exceeds writable scope: src/two.py",
  { recoverable: false },
)
const secondRecovery = scheduler.recoverSchedulerBlockers(root)
const snapshot = scheduler.listSchedulerJobs(root, routing).jobs.find(
  (job) => job.task_id === "t-001",
)
console.log(JSON.stringify({
  firstRecovery,
  secondRecovery,
  retry,
  snapshot,
}))
""",
            )
            self.assertEqual(
                result["firstRecovery"]["recovery_reasons"],
                {"t-001": "CROSS_TASK_DIFF_REBASE"},
            )
            self.assertEqual(result["retry"]["phase"], "CODE")
            self.assertFalse(result["secondRecovery"]["changed"])
            self.assertEqual(result["snapshot"]["status"], "BLOCKED")

    def test_missing_fix_evidence_blocker_recovers_to_test(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.make_project(Path(temporary))
            result = self.run_node(
                project,
                r"""
const scheduler = await import(process.env.MODULE_URL)
const root = process.env.PROJECT
const routing = JSON.parse(process.env.ROUTING)
const options = {
  localConcurrency: 1,
  cloudConcurrency: 3,
  readOnlyConcurrency: 4,
}
scheduler.initializeScheduler(root, options)
const code = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.completeSchedulerJob(root, code.job_id, "SUCCEEDED")
const test = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.completeSchedulerJob(root, test.job_id, "PASS")
const review = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.completeSchedulerJob(root, review.job_id, "CHANGES_REQUIRED")
const fix = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
scheduler.releaseSchedulerJob(
  root,
  fix.job_id,
  "CONTRACT: child reported failure: required failing evidence is missing",
  { recoverable: false },
)
const recovery = scheduler.recoverSchedulerBlockers(root)
const recovered = scheduler.claimSchedulerJob({
  projectRoot: root, taskID: "t-001", routing, options,
})
console.log(JSON.stringify({ recovery, recovered }))
""",
            )
            self.assertTrue(result["recovery"]["changed"])
            self.assertEqual(result["recovery"]["recovered_tasks"], ["t-001"])
            self.assertEqual(result["recovered"]["phase"], "TEST")
            self.assertEqual(result["recovered"]["agent"], "bx-test")


if __name__ == "__main__":
    unittest.main()
