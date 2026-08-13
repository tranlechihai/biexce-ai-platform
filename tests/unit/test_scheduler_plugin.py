import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from tests.unit import test_runtime_workflow as runtime_workflow


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("node"), "Node.js is required for plugin tests")
class SchedulerPluginTests(unittest.TestCase):
    def prepare(self, root: Path, *, local_code: bool = False):
        helper = runtime_workflow.RuntimeWorkflowTests(methodName="runTest")
        return helper.prepare_parallel(root, local_code=local_code)

    def run_node(
        self,
        project: Path,
        config: Path,
        plugin: Path,
        script: str,
        *,
        extra_environment: dict[str, str] | None = None,
    ) -> dict[str, object]:
        environment = os.environ.copy()
        if extra_environment:
            environment.update(extra_environment)
        environment["BIEXCE_CONFIG_HOME"] = str(config)
        environment["BIEXCE_AGENT_TIMEOUT_MS"] = "5000"
        environment["BIEXCE_CONTROL_POLL_MS"] = "50"
        environment["PROJECT"] = str(project)
        environment["PLUGIN_URL"] = plugin.resolve().as_uri()
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_driver_owns_pre_execution_and_stops_at_gate_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            helper = runtime_workflow.RuntimeWorkflowTests(methodName="runTest")
            project, config, plugin = helper.prepare(Path(temporary))
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                const agents = []
                const titles = []
                const client = { session: {
                  create: async (request) => {
                    const id = "planning-child-" + (++childCount)
                    titles.push(request.body.title)
                    return { data: { id } }
                  },
                  prompt: async (request) => {
                    agents.push(request.body.agent)
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    const status = workflow.phase === "PLAN_REVIEW"
                      ? "PLAN_OK"
                      : "SUCCEEDED"
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        status,
                        summary: workflow.phase + " complete",
                        extra_debug_field: "ignored reporting metadata",
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: status }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                  },
                )
                const workflow = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                  "utf8",
                ))
                console.log(JSON.stringify({
                  metadata: result.metadata,
                  agents,
                  titles,
                  workflowPhase: workflow.phase,
                  preflight: fs.readFileSync(
                    process.env.PROJECT + "/.biexce/reports/PREFLIGHT_REPORT.md",
                    "utf8",
                  ),
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(
                payload["agents"], ["bx-explore", "bx-plan", "bx-review"], payload
            )
            self.assertEqual(payload["metadata"]["terminal_reason"], "WAITING_GATE_1")
            self.assertEqual(payload["metadata"]["completed_jobs"], 3)
            self.assertEqual(payload["workflowPhase"], "WAITING_GATE_1")
            self.assertIn("Result: PASS", payload["preflight"])
            self.assertTrue(all(title.startswith("[BX]") for title in payload["titles"]))

    def test_duplicate_driver_cannot_mutate_plan_during_read_only_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            helper = runtime_workflow.RuntimeWorkflowTests(methodName="runTest")
            project, config, plugin = helper.prepare(Path(temporary))
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                let releaseReview = null
                let markReviewStarted = null
                const reviewStarted = new Promise((resolve) => {
                  markReviewStarted = resolve
                })
                const reviewRelease = new Promise((resolve) => {
                  releaseReview = resolve
                })
                const client = { session: {
                  create: async () => ({ data: { id: "child-" + (++childCount) } }),
                  prompt: async (request) => {
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    if (workflow.phase === "PLAN_REVIEW") {
                      markReviewStarted()
                      await reviewRelease
                    }
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        status: workflow.phase === "PLAN_REVIEW"
                          ? "PLAN_OK"
                          : "SUCCEEDED",
                        summary: workflow.phase + " complete",
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  metadata: () => {},
                }
                const firstDriver = hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  context,
                )
                await reviewStarted
                const planPath = process.env.PROJECT + "/.biexce/MASTER_PLAN.md"
                const beforeDuplicate = fs.readFileSync(planPath, "utf8")
                const duplicate = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  context,
                )
                const afterDuplicate = fs.readFileSync(planPath, "utf8")
                releaseReview()
                const first = await firstDriver
                console.log(JSON.stringify({
                  first: first.metadata,
                  duplicate: duplicate.metadata,
                  planUnchanged: beforeDuplicate === afterDuplicate,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertTrue(payload["planUnchanged"], payload)
            self.assertEqual(
                payload["duplicate"]["driver_status"], "WAITING_AGENT", payload
            )
            self.assertEqual(
                payload["duplicate"]["terminal_reason"],
                "ACTIVE_JOBS_IN_PROGRESS",
                payload,
            )
            self.assertEqual(
                payload["first"]["terminal_reason"], "WAITING_GATE_1", payload
            )

    def test_driver_recovers_plan_review_baseline_drift_without_state_edit(self):
        with tempfile.TemporaryDirectory() as temporary:
            helper = runtime_workflow.RuntimeWorkflowTests(methodName="runTest")
            project, config, plugin = helper.prepare(Path(temporary))
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                let reviewCount = 0
                const client = { session: {
                  create: async () => ({ data: { id: "child-" + (++childCount) } }),
                  prompt: async (request) => {
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    if (workflow.phase === "PLAN_REVIEW") {
                      reviewCount += 1
                      if (reviewCount === 1) {
                        fs.appendFileSync(
                          process.env.PROJECT + "/.biexce/MASTER_PLAN.md",
                          "\n",
                        )
                      }
                    }
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        status: workflow.phase === "PLAN_REVIEW"
                          ? "PLAN_OK"
                          : "SUCCEEDED",
                        summary: workflow.phase + " complete",
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  metadata: () => {},
                }
                const result = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  context,
                )
                const recoveryPath =
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_RECOVERY.jsonl"
                const recovery = fs.readFileSync(recoveryPath, "utf8")
                  .trim().split(/\r?\n/).map((line) => JSON.parse(line))
                console.log(JSON.stringify({
                  metadata: result.metadata,
                  reviewCount,
                  recovery,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["reviewCount"], 2, payload)
            self.assertEqual(
                payload["metadata"]["terminal_reason"], "WAITING_GATE_1", payload
            )
            self.assertEqual(
                payload["recovery"][-1]["event"],
                "PLAN_REVIEW_BASELINE_REBASED",
                payload,
            )

    def test_plan_review_source_mutation_remains_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            helper = runtime_workflow.RuntimeWorkflowTests(methodName="runTest")
            project, config, plugin = helper.prepare(Path(temporary))
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                let reviewCount = 0
                const client = { session: {
                  create: async () => ({ data: { id: "child-" + (++childCount) } }),
                  prompt: async (request) => {
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    if (workflow.phase === "PLAN_REVIEW") {
                      reviewCount += 1
                      fs.writeFileSync(
                        process.env.PROJECT + "/src/reviewer-mutation.py",
                        "unexpected = True\n",
                      )
                    }
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        status: workflow.phase === "PLAN_REVIEW"
                          ? "PLAN_OK"
                          : "SUCCEEDED",
                        summary: workflow.phase + " complete",
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  metadata: () => {},
                }
                const first = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  context,
                )
                const second = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  context,
                )
                console.log(JSON.stringify({
                  first: first.metadata,
                  second: second.metadata,
                  reviewCount,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["reviewCount"], 1, payload)
            self.assertEqual(
                payload["first"]["terminal_reason"],
                "DRIVER_RUNTIME_ERROR",
                payload,
            )
            self.assertEqual(
                payload["second"]["terminal_reason"],
                "WORKFLOW_BLOCKED",
                payload,
            )

    def test_gate_one_preflight_rejects_unsafe_write_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            helper = runtime_workflow.RuntimeWorkflowTests(methodName="runTest")
            project, config, plugin = helper.prepare(Path(temporary))
            helper.set_waiting_gate_one(project)
            task = project / ".biexce" / "tasks" / "t-001.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "Writable files: src/calculator.py",
                    "Writable files: **",
                ),
                encoding="utf-8",
            )
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const hooks = await BiexceControlPlugin({ client: {} })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                let message = ""
                try {
                  await hooks.tool.biexce_gate.execute(
                    { gate: "1", summary: "Approve reviewed plan" },
                    {
                      agent: "bx-director",
                      sessionID: "session-1",
                      directory: process.env.PROJECT,
                      ask: async () => {},
                    },
                  )
                } catch (error) {
                  message = error.message
                }
                const workflow = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                  "utf8",
                ))
                console.log(JSON.stringify({ message, phase: workflow.phase }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertIn("unsafe Writable files scope", payload["message"])
            self.assertEqual(payload["phase"], "WAITING_GATE_1")

    @unittest.skipIf(os.name == "nt", "POSIX executable symlink behavior")
    def test_gate_one_preflight_accepts_executable_symlink_on_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            helper = runtime_workflow.RuntimeWorkflowTests(methodName="runTest")
            project, config, plugin = helper.prepare(Path(temporary))
            helper.set_waiting_gate_one(project)
            executable_root = Path(temporary) / "bin"
            executable_root.mkdir()
            real_executable = executable_root / "python3.14"
            real_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            real_executable.chmod(0o755)
            (executable_root / "python3").symlink_to(real_executable.name)
            for task in (project / ".biexce" / "tasks").glob("t-*.md"):
                task.write_text(
                    task.read_text(encoding="utf-8").replace(
                        "python -m unittest discover -s tests -v",
                        "python3 -m unittest discover -s tests -v",
                    ),
                    encoding="utf-8",
                )
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const hooks = await BiexceControlPlugin({ client: {} })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                await hooks.tool.biexce_gate.execute(
                  { gate: "1", summary: "Approve reviewed plan" },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    ask: async () => {},
                  },
                )
                const workflow = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                  "utf8",
                ))
                console.log(JSON.stringify({ phase: workflow.phase }))
                """
            )
            payload = self.run_node(
                project,
                config,
                plugin,
                script,
                extra_environment={
                    "PATH": str(executable_root) + os.pathsep + os.environ.get("PATH", "")
                },
            )
            self.assertEqual(payload["phase"], "CODE")

    def test_fastapi_shaped_five_task_workflow_reaches_gate_two(self):
        with tempfile.TemporaryDirectory() as temporary:
            helper = runtime_workflow.RuntimeWorkflowTests(methodName="runTest")
            project, config, plugin = helper.prepare(Path(temporary))
            task_root = project / ".biexce" / "tasks"
            for task_file in task_root.glob("t-*.md"):
                task_file.unlink()
            plan = """# Master Plan: FastAPI-shaped backend fixture

WIP limit: 2
Fix cap: 3
Reports path: .biexce/reports
Git/deploy: forbidden

## Task DAG

- t-001: core and persistence
- t-002: authentication; depends on t-001
- t-003: projects; depends on t-001
- t-004: issues; depends on t-002 and t-003
- t-005: application integration; depends on t-004

## Human Gates

- Gate 1: Human approves the reviewed plan before source execution.
- Gate 2: Human accepts integration evidence before project closure.
"""
            (project / ".biexce" / "MASTER_PLAN.md").write_text(
                plan, encoding="utf-8"
            )
            contracts = {
                "t-001": ("core and persistence", "app/core.py, app/db.py", "none"),
                "t-002": ("authentication", "app/auth.py, tests/test_auth.py", "t-001"),
                "t-003": ("projects", "app/projects.py, tests/test_projects.py", "t-001"),
                "t-004": ("issues", "app/issues.py, tests/test_issues.py", "t-002, t-003"),
                "t-005": (
                    "application integration",
                    "app/main.py, tests/test_integration.py, README.md",
                    "t-004",
                ),
            }
            for task_id, (title, writable, dependencies) in contracts.items():
                (task_root / f"{task_id}.md").write_text(
                    f"""# {task_id}: {title}

## 1. Objective
Deliver one bounded backend increment.

## 2. Context
FastAPI-shaped multi-module acceptance fixture.

## 3. Acceptance criteria
- [ ] The bounded module is implemented and verified.
Verify: `python -m unittest discover -s tests -v`

## 4. Boundaries
Owner role: bx-code
Writable files: {writable}
Read-only inputs: .biexce/PROJECT_BRIEF.md, .biexce/MASTER_PLAN.md
Out-of-scope: Git, deployment, credentials, production data
Depends on: {dependencies} | Effort: S
""",
                    encoding="utf-8",
                )
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                import path from "node:path"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                let active = 0
                let maxActive = 0
                let protectedWriteDenied = false
                const codeFiles = {
                  "t-001": "app/core.py",
                  "t-002": "app/auth.py",
                  "t-003": "app/projects.py",
                  "t-004": "app/issues.py",
                  "t-005": "app/main.py",
                }
                const client = { session: {
                  create: async () => ({ data: { id: "fastapi-child-" + (++childCount) } }),
                  prompt: async (request) => {
                    active += 1
                    maxActive = Math.max(maxActive, active)
                    await new Promise((resolve) => setTimeout(resolve, 5))
                    const text = request.body.parts[0].text
                    const phase = text.match(/phase=([A-Z_]+)/)[1]
                    const taskMatch = text.match(/task_id=(t-[0-9]{3})/)
                    const taskID = taskMatch ? taskMatch[1] : null
                    if (phase === "CODE") {
                      const relative = codeFiles[taskID]
                      const target = path.join(process.env.PROJECT, relative)
                      fs.mkdirSync(path.dirname(target), { recursive: true })
                      fs.writeFileSync(target, `# ${taskID} backend module\n`)
                      if (taskID === "t-001") {
                        // Standard delivery may discover one extra source file
                        // that the planner did not predict. Runtime should keep
                        // it instead of blocking the whole project.
                        const discovered = path.join(
                          process.env.PROJECT,
                          "app/generated_helper.py",
                        )
                        await hooks["tool.execute.before"](
                          {
                            tool: "write_file",
                            sessionID: request.path.id,
                            callID: "discovered-source-write",
                          },
                          { args: { path: discovered } },
                        )
                        fs.writeFileSync(
                          discovered,
                          "# discovered implementation helper\n",
                        )
                        try {
                          await hooks["tool.execute.before"](
                            {
                              tool: "write_file",
                              sessionID: request.path.id,
                              callID: "protected-state-write",
                            },
                            { args: { path: path.join(
                              process.env.PROJECT,
                              ".biexce/state/PROJECT_STATE.json",
                            ) } },
                          )
                        } catch (error) {
                          protectedWriteDenied = error.message.includes("WRITE_DENY")
                        }
                      }
                    }
                    const status = {
                      EXPLORE: "SUCCEEDED",
                      PLAN: "SUCCEEDED",
                      PLAN_REVIEW: "PLAN_OK",
                      CODE: "SUCCEEDED",
                      TEST: "PASS",
                      TASK_REVIEW: "APPROVE",
                      INTEGRATION_TEST: "PASS",
                      INTEGRATION_REVIEW: "APPROVE",
                    }[phase]
                    const checks = ["TEST", "INTEGRATION_TEST"].includes(phase)
                      ? [{
                          command: "python -m unittest discover -s tests -v",
                          exit_code: 0,
                          status: "PASS",
                          output_summary: "fixture verification passed",
                        }]
                      : []
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        status,
                        summary: (taskID || "project") + " " + phase + " complete",
                        checks,
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    active -= 1
                    return { data: { parts: [{ type: "text", text: status }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  metadata: () => {},
                }
                const planning = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true }, context,
                )
                let delivery = { metadata: null }
                let scheduler = { tasks: {} }
                if (planning.metadata.terminal_reason === "WAITING_GATE_1") {
                  await hooks.tool.biexce_gate.execute(
                    { gate: "1", summary: "Plan and preflight approved" },
                    { ...context, ask: async () => {} },
                  )
                  delivery = await hooks.tool.biexce_drive.execute(
                    { profile: "standard", allow_critical_downgrade: true }, context,
                  )
                  scheduler = JSON.parse(fs.readFileSync(
                    process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                    "utf8",
                  ))
                }
                console.log(JSON.stringify({
                  planning: planning.metadata,
                  delivery: delivery.metadata,
                  childCount,
                  maxActive,
                  taskPhases: Object.fromEntries(Object.entries(scheduler.tasks).map(
                    ([id, task]) => [id, task.phase],
                  )),
                  discoveredSource: fs.existsSync(
                    process.env.PROJECT + "/app/generated_helper.py",
                  ),
                  protectedWriteDenied,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(
                payload["planning"]["terminal_reason"], "WAITING_GATE_1", payload
            )
            self.assertEqual(
                payload["delivery"]["terminal_reason"], "WAITING_GATE_2", payload
            )
            self.assertEqual(payload["childCount"], 20)
            self.assertGreaterEqual(payload["maxActive"], 2)
            self.assertTrue(payload["discoveredSource"])
            self.assertTrue(payload["protectedWriteDenied"])
            self.assertEqual(
                payload["taskPhases"],
                {f"t-{index:03d}": "DONE" for index in range(1, 6)},
            )

    def test_disjoint_writer_sessions_are_visible_but_serialized(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                let releaseFirst
                const firstBarrier = new Promise((resolve) => { releaseFirst = resolve })
                let signalFirstStarted
                const firstStarted = new Promise((resolve) => { signalFirstStarted = resolve })
                const created = []
                const updates = []
                let crossScopeWriteDenied = false
                const submit = async (request) => {
                  const text = request.body.parts[0].text
                  const taskID = text.match(/task_id=(t-[0-9]{3})/)[1]
                  const phase = text.match(/phase=([A-Z_]+)/)[1]
                  const workflow = JSON.parse(fs.readFileSync(
                    process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                    "utf8",
                  ))
                  await hooks.tool.biexce_submit_result.execute(
                    { result_json: JSON.stringify({
                      $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                      schema_version: 1,
                      workflow_revision: workflow.revision,
                      phase,
                      task_id: taskID,
                      agent: request.body.agent,
                      status: "SUCCEEDED",
                      summary: taskID + " code complete",
                      changed_files: [],
                      checks: [],
                      artifacts: [],
                    }) },
                    {
                      agent: request.body.agent,
                      sessionID: request.path.id,
                      directory: process.env.PROJECT,
                    },
                  )
                }
                const client = { session: {
                  create: async (request) => {
                    const id = "parallel-child-" + (++childCount)
                    created.push({
                      id,
                      parentID: request.body.parentID,
                      title: request.body.title,
                    })
                    return { data: { id } }
                  },
                  prompt: async (request) => {
                    const text = request.body.parts[0].text
                    const taskID = text.match(/task_id=(t-[0-9]{3})/)[1]
                    const relative = taskID === "t-001"
                      ? "src/calculator.py"
                      : "src/multiply.py"
                    if (taskID === "t-001") {
                      signalFirstStarted()
                      try {
                        await hooks["tool.execute.before"](
                          {
                            tool: "write_file",
                            sessionID: request.path.id,
                            callID: "cross-scope-write",
                          },
                          { args: { path: process.env.PROJECT + "/src/multiply.py" } },
                        )
                      } catch (error) {
                        crossScopeWriteDenied = error.message.includes("WRITE_DENY")
                      }
                      await firstBarrier
                    }
                    fs.mkdirSync(process.env.PROJECT + "/src", { recursive: true })
                    fs.writeFileSync(
                      process.env.PROJECT + "/" + relative,
                      "# " + taskID + "\n",
                    )
                    await submit(request)
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const context = () => ({
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  metadata: (value) => updates.push(value),
                })
                const firstPromise = hooks.tool.biexce_start_job.execute(
                  { task_id: "t-001", capability: "bx-code" },
                  context(),
                )
                await firstStarted
                let queuedError = null
                try {
                  await hooks.tool.biexce_start_job.execute(
                    { task_id: "t-002", capability: "bx-code" },
                    context(),
                  )
                } catch (error) {
                  queuedError = error.message
                }
                releaseFirst()
                const first = await firstPromise
                const second = await hooks.tool.biexce_start_job.execute(
                  { task_id: "t-002", capability: "bx-code" },
                  context(),
                )
                const scheduler = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                  "utf8",
                ))
                const workflow = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                  "utf8",
                ))
                const status = await hooks.tool.biexce_job_status.execute(
                  { job_id: first.metadata.job_id },
                  context(),
                )
                console.log(JSON.stringify({
                  created,
                  updates,
                  first: first.metadata,
                  second: second.metadata,
                  phases: {
                    first: scheduler.tasks["t-001"].phase,
                    second: scheduler.tasks["t-002"].phase,
                  },
                  workflowPhase: workflow.phase,
                  runtimeStatus: status.metadata.runtime_status,
                  crossScopeWriteDenied,
                  queuedError,
                  changedFiles: {
                    first: first.metadata.result.changed_files,
                    second: second.metadata.result.changed_files,
                  },
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(len(payload["created"]), 2)
            self.assertEqual(
                {item["parentID"] for item in payload["created"]},
                {"session-1"},
            )
            self.assertTrue(
                any("[BX][t-001][CODE] bx-code" in item["title"]
                    for item in payload["created"])
            )
            self.assertTrue(
                any("[BX][t-002][CODE] bx-code" in item["title"]
                    for item in payload["created"])
            )
            self.assertNotEqual(
                payload["first"]["child_session_id"],
                payload["second"]["child_session_id"],
            )
            self.assertEqual(payload["phases"], {"first": "TEST", "second": "TEST"})
            self.assertEqual(payload["workflowPhase"], "CODE")
            self.assertEqual(payload["runtimeStatus"], "COMPLETED")
            self.assertTrue(payload["crossScopeWriteDenied"])
            self.assertIn("workspace writer is active", payload["queuedError"])
            self.assertEqual(
                payload["changedFiles"],
                {
                    "first": ["src/calculator.py"],
                    "second": ["src/multiply.py"],
                },
            )
            self.assertTrue(payload["updates"])
            self.assertTrue(
                all(
                    item["metadata"]["contract"] == "biexce-observability-v1"
                    for item in payload["updates"]
                )
            )
            self.assertIn(
                "RUNNING",
                {item["metadata"]["runtimeStatus"] for item in payload["updates"]},
            )
            self.assertIn(
                "DONE",
                {item["metadata"]["runtimeStatus"] for item in payload["updates"]},
            )

    def test_opencode_patch_text_is_checked_against_job_write_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                const client = { session: {
                  create: async () => ({ data: { id: "patch-text-child" } }),
                  prompt: async (request) => {
                    await hooks["tool.execute.before"](
                      { sessionID: request.path.id, tool: "apply_patch" },
                      { args: { patchText: [
                        "*** Begin Patch",
                        "*** Add File: src/calculator.py",
                        "+def add(a, b):",
                        "+    return a + b",
                        "*** End Patch",
                      ].join("\\n") } },
                    )
                    fs.writeFileSync(
                      process.env.PROJECT + "/src/calculator.py",
                      "def add(a, b):\\n    return a + b\\n",
                    )
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: "CODE",
                        task_id: "t-001",
                        agent: "bx-code",
                        status: "SUCCEEDED",
                        summary: "calculator source created with scoped apply_patch",
                        changed_files: ["src/calculator.py"],
                        checks: [],
                        artifacts: ["src/calculator.py"],
                      }) },
                      {
                        agent: "bx-code",
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_start_job.execute(
                  { task_id: "t-001", capability: "bx-code" },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                  },
                )
                const board = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_JOBS.json",
                  "utf8",
                ))
                console.log(JSON.stringify({
                  exists: fs.existsSync(process.env.PROJECT + "/src/calculator.py"),
                  job: board.jobs[result.metadata.job_id],
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertTrue(payload["exists"])
            self.assertEqual(payload["job"]["status"], "COMPLETED")
            self.assertEqual(payload["job"]["result_status"], "SUCCEEDED")

    def test_failed_code_result_routes_to_fix_without_repeating_code_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const workflowPolicy = await import(
                  new URL("../runtime/workflow-policy.js", process.env.PLUGIN_URL)
                )
                let hooks = null
                let promptText = ""
                const client = { session: {
                  create: async () => ({ data: { id: "failed-result-child" } }),
                  prompt: async (request) => {
                    promptText = request.body.parts[0].text
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: "CODE",
                        task_id: "t-001",
                        agent: "bx-code",
                        status: "FAILED",
                        summary: "write tool was denied before source creation",
                        changed_files: [],
                        checks: [{
                          command: "apply_patch src/calculator.py",
                          exit_code: null,
                          status: "FAIL",
                          output_summary: "scheduler denied the write tool",
                        }],
                        artifacts: [],
                      }) },
                      {
                        agent: "bx-code",
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "blocked" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                workflowPolicy.selectAndPersistWorkflowPolicy(
                  process.env.PROJECT,
                  { requestedProfile: "standard", allowCriticalDowngrade: true },
                )
                const result = await hooks.tool.biexce_start_job.execute(
                  { task_id: "t-001", capability: "bx-code" },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                  },
                )
                let duplicate = ""
                try {
                  await hooks.tool.biexce_start_job.execute(
                    { task_id: "t-001", capability: "bx-code" },
                    {
                      agent: "bx-director",
                      sessionID: "session-1",
                      directory: process.env.PROJECT,
                      metadata: () => {},
                    },
                  )
                } catch (error) {
                  duplicate = error.message
                }
                const board = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_JOBS.json",
                  "utf8",
                ))
                const scheduler = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                  "utf8",
                ))
                const events = fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_EVENTS.jsonl",
                  "utf8",
                ).trim().split(/\\r?\\n/).map((line) => JSON.parse(line))
                console.log(JSON.stringify({
                  result: result.metadata,
                  duplicate,
                  job: Object.values(board.jobs)[0],
                  task: scheduler.tasks["t-001"],
                  repairAuthority: promptText.includes(
                    "[STANDARD RUNTIME REPAIR AUTHORITY]"
                  ),
                  shadow: events.filter((event) =>
                    event.event === "FAILURE_POLICY_SHADOW"
                  ),
                }))
                """
            )
            payload = self.run_node(
                project,
                config,
                plugin,
                script,
                extra_environment={"BIEXCE_FAILURE_POLICY_MODE": "shadow"},
            )
            self.assertEqual(payload["job"]["status"], "COMPLETED")
            self.assertEqual(payload["job"]["result_status"], "FAILED")
            self.assertEqual(payload["task"]["status"], "READY")
            self.assertEqual(payload["task"]["phase"], "FIX")
            self.assertEqual(payload["task"]["fix_round"], 1)
            self.assertTrue(payload["repairAuthority"])
            self.assertIn("requires bx-fix, not bx-code", payload["duplicate"])
            # The only shadow event comes from the deliberate invalid second
            # bx-code launch. The structured CODE failure itself completed and
            # transitioned to FIX instead of entering exception recovery.
            self.assertEqual(len(payload["shadow"]), 1)

    def test_driver_migrates_legacy_failed_writer_after_standard_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const scheduler = await import(
                  new URL("../runtime/scheduler.js", process.env.PLUGIN_URL)
                )
                const jobs = await import(
                  new URL("../runtime/job-board.js", process.env.PLUGIN_URL)
                )
                const workflowPolicy = await import(
                  new URL("../runtime/workflow-policy.js", process.env.PLUGIN_URL)
                )
                const root = process.env.PROJECT
                const routing = JSON.parse(fs.readFileSync(
                  process.env.BIEXCE_CONFIG_HOME + "/model-routing.applied.json",
                  "utf8",
                )).routing.agents
                scheduler.initializeScheduler(root, {
                  localConcurrency: 1,
                  cloudConcurrency: 3,
                  readOnlyConcurrency: 4,
                })
                const legacy = scheduler.claimSchedulerJob({
                  projectRoot: root,
                  taskID: "t-001",
                  requestedAgent: "bx-code",
                  routing,
                })
                jobs.putJob(root, {
                  ...legacy,
                  trace_id: "trace-legacy-plugin",
                  status: "COMPLETED",
                  started_at_utc: "2026-08-12T01:00:00Z",
                  completed_at_utc: "2026-08-12T01:01:00Z",
                  result_status: "FAILED",
                })
                scheduler.releaseSchedulerJob(
                  root,
                  legacy.job_id,
                  "Legacy runtime terminal-blocked a validated structured failure",
                  { recoverable: false },
                )
                workflowPolicy.selectAndPersistWorkflowPolicy(root, {
                  requestedProfile: "critical",
                  actor: "legacy-runtime",
                })

                let hooks = null
                let childCount = 0
                const agents = []
                const client = { session: {
                  create: async () => ({ data: { id: "migration-child-" + (++childCount) } }),
                  prompt: async (request) => {
                    agents.push(request.body.agent)
                    const text = request.body.parts[0].text
                    const phase = text.match(/phase=([A-Z_]+)/)[1]
                    const taskMatch = text.match(/task_id=(t-[0-9]{3})/)
                    const taskID = taskMatch ? taskMatch[1] : null
                    const status = {
                      CODE: "SUCCEEDED",
                      FIX: "SUCCEEDED",
                      TEST: "PASS",
                      TASK_REVIEW: "APPROVE",
                      INTEGRATION_TEST: "PASS",
                      INTEGRATION_REVIEW: "APPROVE",
                    }[phase]
                    const workflow = JSON.parse(fs.readFileSync(
                      root + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase,
                        task_id: taskID,
                        agent: request.body.agent,
                        status,
                        summary: (taskID || "project") + " " + phase + " " + status,
                        changed_files: [],
                        checks: ["TEST", "INTEGRATION_TEST"].includes(phase) ? [{
                          command: "python -m unittest discover -s tests -v",
                          exit_code: 0,
                          status: "PASS",
                          output_summary: "regression passed",
                        }] : [],
                        artifacts: [],
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: root,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: status }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  {
                    agent: "bx-director",
                    sessionID: "migration-director",
                    directory: root,
                    metadata: () => {},
                  },
                )
                const policy = workflowPolicy.loadWorkflowPolicy(root, { required: true })
                console.log(JSON.stringify({
                  metadata: result.metadata,
                  firstAgent: agents[0],
                  policy: policy.effective_profile,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["firstAgent"], "bx-fix")
            self.assertEqual(payload["policy"], "standard")
            self.assertEqual(
                payload["metadata"]["terminal_reason"],
                "WAITING_GATE_2",
            )

    def test_snapshot_ignores_file_that_vanishes_between_readdir_and_lstat(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const transient = process.env.PROJECT + "/transient.tmp"
                fs.writeFileSync(transient, "temporary")
                const originalLstat = fs.lstatSync
                let injected = false
                fs.lstatSync = (target, ...args) => {
                  if (!injected && String(target).endsWith("transient.tmp")) {
                    injected = true
                    fs.unlinkSync(transient)
                    const error = new Error("fixture vanished")
                    error.code = "ENOENT"
                    throw error
                  }
                  return originalLstat(target, ...args)
                }
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                const client = { session: {
                  create: async () => ({ data: { id: "snapshot-race-child" } }),
                  prompt: async (request) => {
                    fs.writeFileSync(
                      process.env.PROJECT + "/src/calculator.py",
                      "def add(a, b):\\n    return a + b\\n",
                    )
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: "CODE",
                        task_id: "t-001",
                        agent: "bx-code",
                        status: "SUCCEEDED",
                        summary: "source created after transient snapshot entry vanished",
                        changed_files: ["src/calculator.py"],
                        checks: [],
                        artifacts: ["src/calculator.py"],
                      }) },
                      {
                        agent: "bx-code",
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_start_job.execute(
                  { task_id: "t-001", capability: "bx-code" },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                  },
                )
                console.log(JSON.stringify({
                  injected,
                  completed: result.metadata.result.status,
                  transientExists: fs.existsSync(transient),
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertTrue(payload["injected"])
            self.assertEqual(payload["completed"], "SUCCEEDED")
            self.assertFalse(payload["transientExists"])

    def test_verification_only_job_writes_report_but_cannot_write_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            task_path = project / ".biexce" / "tasks" / "t-001.md"
            task_path.write_text(
                task_path.read_text(encoding="utf-8")
                .replace("Owner role: bx-code", "Owner role: bx-test")
                .replace(
                    "Writable files: src/calculator.py",
                    "Writable files: .biexce/reports/integration-regression.md",
                ),
                encoding="utf-8",
            )
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let sourceDenied = false
                const client = { session: {
                  create: async () => ({ data: { id: "report-test-child" } }),
                  prompt: async (request) => {
                    await hooks["tool.execute.before"](
                      { sessionID: request.path.id, tool: "apply_patch" },
                      { args: { patchText: [
                        "*** Begin Patch",
                        "*** Add File: .biexce/reports/integration-regression.md",
                        "+PASS",
                        "*** End Patch",
                      ].join("\\n") } },
                    )
                    try {
                      await hooks["tool.execute.before"](
                        { sessionID: request.path.id, tool: "apply_patch" },
                        { args: { patchText: [
                          "*** Begin Patch",
                          "*** Add File: src/forbidden.py",
                          "+forbidden = True",
                          "*** End Patch",
                        ].join("\\n") } },
                      )
                    } catch (error) {
                      sourceDenied = error.message.includes("WRITE_DENY")
                    }
                    fs.writeFileSync(
                      process.env.PROJECT + "/.biexce/reports/integration-regression.md",
                      "PASS\\n",
                    )
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: "TEST",
                        task_id: "t-001",
                        agent: "bx-test",
                        status: "PASS",
                        summary: "verification report persisted",
                        changed_files: [
                          ".biexce/reports/integration-regression.md",
                        ],
                        checks: [{
                          command: "python -m unittest discover -s tests -v",
                          exit_code: 0,
                          status: "PASS",
                          output_summary: "all tests passed",
                        }],
                        artifacts: [
                          ".biexce/reports/integration-regression.md",
                        ],
                      }) },
                      {
                        agent: "bx-test",
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "PASS" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                const runtimeConfig = { default_agent: "bx-director", agent: {} }
                await hooks.config(runtimeConfig)
                const result = await hooks.tool.biexce_start_job.execute(
                  { task_id: "t-001", capability: "bx-test" },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                  },
                )
                console.log(JSON.stringify({
                  result: result.metadata.result,
                  sourceDenied,
                  editPermission: runtimeConfig.agent["bx-test"].permission.edit,
                  reportExists: fs.existsSync(
                    process.env.PROJECT + "/.biexce/reports/integration-regression.md",
                  ),
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["result"]["status"], "PASS")
            self.assertTrue(payload["sourceDenied"])
            self.assertTrue(payload["reportExists"])
            self.assertEqual(
                payload["editPermission"][".biexce/reports/**"], "allow"
            )

    def test_markdown_write_scope_and_cross_run_retry_keep_original_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            task_path = project / ".biexce" / "tasks" / "t-001.md"
            task_path.write_text(
                task_path.read_text(encoding="utf-8").replace(
                    "Writable files: src/calculator.py",
                    "Writable files: `src/calculator.py`",
                ),
                encoding="utf-8",
            )
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  metadata: () => {},
                }
                let firstHooks = null
                const firstClient = { session: {
                  create: async () => ({ data: { id: "baseline-child" } }),
                  prompt: async () => {
                    fs.writeFileSync(
                      process.env.PROJECT + "/src/calculator.py",
                      "def add(a, b):\\n    return a + b\\n",
                    )
                    throw Object.assign(new Error("bad gateway"), {
                      code: "ECONNRESET",
                    })
                  },
                  abort: async () => ({ data: true }),
                }}
                firstHooks = await BiexceControlPlugin({ client: firstClient })
                await firstHooks.config({ default_agent: "bx-director", agent: {} })
                let firstError = ""
                try {
                  await firstHooks.tool.biexce_start_job.execute(
                    { task_id: "t-001", capability: "bx-code" },
                    context,
                  )
                } catch (error) {
                  firstError = error.message
                }

                let resumedHooks = null
                const resumedClient = { session: {
                  create: async () => {
                    throw new Error("retry unexpectedly created a new session")
                  },
                  get: async () => ({ data: { id: "baseline-child" } }),
                  prompt: async (request) => {
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await resumedHooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: "CODE",
                        task_id: "t-001",
                        agent: "bx-code",
                        status: "SUCCEEDED",
                        summary: "calculator created before transport retry",
                        changed_files: ["src/calculator.py"],
                        checks: [],
                        artifacts: ["src/calculator.py"],
                      }) },
                      {
                        agent: "bx-code",
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                resumedHooks = await BiexceControlPlugin({ client: resumedClient })
                await resumedHooks.config({ default_agent: "bx-director", agent: {} })
                const result = await resumedHooks.tool.biexce_start_job.execute(
                  { task_id: "t-001", capability: "bx-code" },
                  context,
                )
                const board = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_JOBS.json",
                  "utf8",
                ))
                const job = board.jobs[result.metadata.job_id]
                const baselineDirectory =
                  process.env.PROJECT + "/.biexce/state/job-baselines"
                console.log(JSON.stringify({
                  firstError,
                  metadata: result.metadata,
                  job,
                  baselineRemoved: !fs.existsSync(baselineDirectory),
                }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
            environment["BIEXCE_AGENT_TIMEOUT_MS"] = "5000"
            environment["BIEXCE_CONTROL_POLL_MS"] = "50"
            environment["BIEXCE_TRANSPORT_RETRIES"] = "0"
            environment["PROJECT"] = str(project)
            environment["PLUGIN_URL"] = plugin.resolve().as_uri()
            result = subprocess.run(
                [shutil.which("node"), "--input-type=module", "-e", script],
                cwd=REPOSITORY_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("[TRANSPORT]", payload["firstError"])
            self.assertTrue(payload["metadata"]["session_resumed"])
            self.assertEqual(
                payload["job"]["write_scope"],
                ["src/calculator.py"],
            )
            self.assertEqual(payload["job"]["status"], "COMPLETED")
            self.assertTrue(payload["baselineRemoved"])

    def test_changed_file_reporting_drift_is_normalized_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let promptCount = 0
                const client = { session: {
                  create: async () => ({ data: { id: "contract-child" } }),
                  prompt: async (request) => {
                    promptCount += 1
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: "CODE",
                        task_id: "t-001",
                        agent: "bx-code",
                        status: "SUCCEEDED",
                        summary: "incorrect write claim fixture",
                        changed_files: ["src/calculator.py"],
                        checks: [],
                        artifacts: [],
                      }) },
                      {
                        agent: "bx-code",
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                let message = ""
                let started = null
                try {
                  started = await hooks.tool.biexce_start_job.execute(
                    { task_id: "t-001", capability: "bx-code" },
                    {
                      agent: "bx-director",
                      sessionID: "session-1",
                      directory: process.env.PROJECT,
                      metadata: () => {},
                    },
                  )
                } catch (error) {
                  message = error.message
                }
                const board = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_JOBS.json",
                  "utf8",
                ))
                const job = Object.values(board.jobs).find(
                  (value) => value.task_id === "t-001" && value.phase === "CODE",
                )
                console.log(JSON.stringify({ message, promptCount, job, started }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["message"], "")
            self.assertEqual(payload["promptCount"], 1)
            self.assertEqual(payload["job"]["attempt"], 1)
            self.assertEqual(payload["job"]["status"], "COMPLETED")
            self.assertIsNone(payload["job"]["error"])
            self.assertEqual(
                payload["started"]["metadata"]["result"]["changed_files"],
                [],
            )

    def test_autonomous_driver_drains_parallel_tasks_to_integration(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                let active = 0
                let maxActive = 0
                let integrationAttempts = 0
                const client = { session: {
                  create: async () => ({
                    data: { id: "driver-child-" + (++childCount) },
                  }),
                  prompt: async (request) => {
                    active += 1
                    maxActive = Math.max(maxActive, active)
                    await new Promise((resolve) => setTimeout(resolve, 10))
                    const text = request.body.parts[0].text
                    const taskMatch = text.match(/task_id=(t-[0-9]{3})/)
                    const taskID = taskMatch ? taskMatch[1] : null
                    const phase = text.match(/phase=([A-Z_]+)/)[1]
                    let status = {
                      CODE: "SUCCEEDED",
                      TEST: "PASS",
                      TASK_REVIEW: "APPROVE",
                      INTEGRATION_TEST: "PASS",
                      INTEGRATION_FIX: "SUCCEEDED",
                      INTEGRATION_REVIEW: "APPROVE",
                    }[phase]
                    if (phase === "INTEGRATION_TEST") {
                      integrationAttempts += 1
                      if (integrationAttempts === 1) status = "FAIL"
                    }
                    if (phase === "INTEGRATION_FIX") {
                      fs.writeFileSync(
                        process.env.PROJECT + "/integration-repair.txt",
                        "integration repair applied\\n",
                      )
                    }
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase,
                        task_id: taskID,
                        agent: request.body.agent,
                        status,
                        summary: (taskID || "project") + " " + phase + " complete",
                        changed_files: [],
                        checks: ["TEST", "INTEGRATION_TEST"].includes(phase) ? [{
                          command: "python -m unittest",
                          exit_code: status === "PASS" ? 0 : 1,
                          status: status === "PASS" ? "PASS" : "FAIL",
                          output_summary: status === "PASS" ? "pass" : "failed once",
                        }] : [],
                        artifacts: [],
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    active -= 1
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                  },
                )
                const gate = await hooks.tool.biexce_gate.execute(
                  { gate: "2", summary: "Integration and review passed." },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                    ask: async () => {},
                  },
                )
                const scheduler = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                  "utf8",
                ))
                const policy = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_POLICY.json",
                  "utf8",
                ))
                const finalWorkflow = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                  "utf8",
                ))
                const finalControl = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_CONTROL.json",
                  "utf8",
                ))
                console.log(JSON.stringify({
                  metadata: result.metadata,
                  phases: Object.fromEntries(Object.entries(scheduler.tasks).map(
                    ([id, task]) => [id, task.phase],
                  )),
                  policy,
                  childCount,
                  maxActive,
                  integrationReport: fs.existsSync(
                    process.env.PROJECT + "/.biexce/reports/INTEGRATION_REPORT.md",
                  ),
                  finalReport: fs.existsSync(
                    process.env.PROJECT + "/.biexce/reports/FINAL_REPORT.md",
                  ),
                  integrationRepair: fs.existsSync(
                    process.env.PROJECT + "/integration-repair.txt",
                  ),
                  integrationAttempts,
                  gate: gate.metadata,
                  finalWorkflow: finalWorkflow.phase,
                  finalControl: finalControl.mode,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["metadata"]["terminal_reason"], "WAITING_GATE_2")
            self.assertEqual(payload["metadata"]["completed_jobs"], 13)
            self.assertEqual(
                payload["phases"],
                {"t-001": "DONE", "t-002": "DONE", "t-003": "DONE"},
            )
            self.assertEqual(payload["policy"]["effective_profile"], "standard")
            self.assertEqual(payload["policy"]["driver_status"], "WAITING_HUMAN")
            self.assertEqual(payload["childCount"], 13)
            self.assertGreaterEqual(payload["maxActive"], 2)
            self.assertEqual(payload["integrationAttempts"], 2)
            self.assertTrue(payload["integrationRepair"])
            self.assertTrue(payload["integrationReport"])
            self.assertTrue(payload["finalReport"])
            self.assertTrue(payload["gate"]["approved"])
            self.assertEqual(payload["finalWorkflow"], "COMPLETE")
            self.assertEqual(payload["finalControl"], "OFF")

    def test_driver_recovers_legacy_unittest_na_blocker_without_state_edit(self):
        with tempfile.TemporaryDirectory() as temporary:
            helper = runtime_workflow.RuntimeWorkflowTests(methodName="runTest")
            project, config, plugin = helper.prepare(Path(temporary))
            helper.set_waiting_gate_one(project)
            helper.approve_runtime_gate(project, config, plugin, 1)
            task_path = project / ".biexce" / "tasks" / "t-001.md"
            task_path.write_text(
                task_path.read_text(encoding="utf-8").replace(
                    "Verify: `python -m unittest discover -s tests -v`",
                    "Verify: `N/A — legacy command omitted`",
                ),
                encoding="utf-8",
            )
            test_root = project / "tests"
            test_root.mkdir(exist_ok=True)
            (test_root / "test_calculator.py").write_text(
                "import unittest\n",
                encoding="utf-8",
            )
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                let testAttempts = 0
                const client = { session: {
                  create: async () => ({
                    data: { id: "legacy-recovery-child-" + (++childCount) },
                  }),
                  prompt: async (request) => {
                    const text = request.body.parts[0].text
                    const taskMatch = text.match(/task_id=(t-[0-9]{3})/)
                    const taskID = taskMatch ? taskMatch[1] : null
                    const phase = text.match(/phase=([A-Z_]+)/)[1]
                    let status = {
                      CODE: "SUCCEEDED",
                      TEST: "PASS",
                      TASK_REVIEW: "APPROVE",
                      INTEGRATION_TEST: "PASS",
                      INTEGRATION_REVIEW: "APPROVE",
                    }[phase]
                    if (phase === "TEST") {
                      testAttempts += 1
                      if (testAttempts === 1) status = "INCONCLUSIVE"
                    }
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    const checks = ["TEST", "INTEGRATION_TEST"].includes(phase) ? [{
                      command: "python -m unittest discover -s tests -v",
                      exit_code: status === "PASS" ? 0 : null,
                      status: status === "PASS" ? "PASS" : "NOT_RUN",
                      output_summary: status === "PASS"
                        ? "unittest passed"
                        : "legacy story omitted command",
                    }] : []
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase,
                        task_id: taskID,
                        agent: request.body.agent,
                        status,
                        summary: taskID + " " + phase + " " + status,
                        changed_files: [],
                        checks,
                        artifacts: [],
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: status }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  metadata: () => {},
                }
                const first = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  context,
                )
                const second = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  context,
                )
                const scheduler = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                  "utf8",
                ))
                const workflow = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                  "utf8",
                ))
                console.log(JSON.stringify({
                  first: first.metadata,
                  second: second.metadata,
                  testAttempts,
                  workflowPhase: workflow.phase,
                  taskPhases: Object.fromEntries(Object.entries(scheduler.tasks).map(
                    ([id, task]) => [id, task.phase],
                  )),
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["first"]["terminal_reason"], "WAITING_GATE_2")
            self.assertEqual(payload["second"]["terminal_reason"], "WAITING_GATE_2")
            self.assertEqual(payload["workflowPhase"], "WAITING_GATE_2")
            self.assertEqual(
                payload["taskPhases"],
                {"t-001": "DONE", "t-002": "DONE", "t-003": "DONE"},
            )
            self.assertEqual(payload["testAttempts"], 4)

    def test_driver_migrates_legacy_scope_blocker_and_syncs_stale_pointer(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const scheduler = await import(
                  new URL("../runtime/scheduler.js", process.env.PLUGIN_URL)
                )
                const root = process.env.PROJECT
                const schedulerPath = root + "/.biexce/state/AUTOPILOT_SCHEDULER.json"
                const projectStatePath = root + "/.biexce/state/PROJECT_STATE.json"
                const workflowPath = root + "/.biexce/state/AUTOPILOT_WORKFLOW.json"
                scheduler.initializeScheduler(root, {
                  localConcurrency: 4,
                  cloudConcurrency: 3,
                  readOnlyConcurrency: 4,
                })
                const state = scheduler.loadSchedulerState(root)
                const now = "2026-08-12T01:00:00.000Z"
                const blockedJob = "job-t-002-code-bx-code-r0"
                state.revision += 1
                state.updated_at_utc = now
                state.tasks["t-001"] = {
                  ...state.tasks["t-001"],
                  phase: "DONE",
                  status: "DONE",
                  last_job_id: "job-t-001-task_review-bx-review-r0",
                  last_result: "APPROVE",
                  updated_at_utc: now,
                }
                state.tasks["t-002"] = {
                  ...state.tasks["t-002"],
                  phase: "BLOCKED",
                  status: "BLOCKED",
                  last_job_id: blockedJob,
                  error: "CONTRACT: runtime diff exceeds writable scope: tests/test_old_contract.py",
                  updated_at_utc: now,
                }
                fs.writeFileSync(schedulerPath, JSON.stringify(state, null, 2) + "\n")
                const project = JSON.parse(fs.readFileSync(projectStatePath, "utf8"))
                for (const task of project.tasks) {
                  task.status = task.id === "t-001"
                    ? "done"
                    : task.id === "t-002" ? "escalated" : "backlog"
                  task.agent = null
                }
                project.stage = "B3"
                fs.writeFileSync(projectStatePath, JSON.stringify(project, null, 2) + "\n")
                let hooks = null
                let childCount = 0
                let pointerAtFirstPrompt = null
                let phaseAtFirstPrompt = null
                let scopeTestFailed = false
                const phasesSeen = []
                const client = { session: {
                  create: async () => ({
                    data: { id: "stale-pointer-child-" + (++childCount) },
                  }),
                  prompt: async (request) => {
                    const text = request.body.parts[0].text
                    const phase = text.match(/phase=([A-Z_]+)/)[1]
                    const taskMatch = text.match(/task_id=(t-[0-9]{3})/)
                    const taskID = taskMatch ? taskMatch[1] : null
                    phasesSeen.push(taskID + ":" + phase)
                    if (pointerAtFirstPrompt === null) {
                      pointerAtFirstPrompt = JSON.parse(
                        fs.readFileSync(workflowPath, "utf8")
                      ).current_task_id
                      phaseAtFirstPrompt = phase
                    }
                    let status = {
                      CODE: "SUCCEEDED",
                      FIX: "SUCCEEDED",
                      TEST: "PASS",
                      TASK_REVIEW: "APPROVE",
                      INTEGRATION_TEST: "PASS",
                      INTEGRATION_REVIEW: "APPROVE",
                    }[phase]
                    if (taskID === "t-002" && phase === "TEST" && !scopeTestFailed) {
                      scopeTestFailed = true
                      status = "FAIL"
                    }
                    const workflow = JSON.parse(fs.readFileSync(workflowPath, "utf8"))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase,
                        task_id: taskID,
                        agent: request.body.agent,
                        status,
                        summary: (taskID || "project") + " " + phase + " " + status,
                        changed_files: [],
                        checks: ["TEST", "INTEGRATION_TEST"].includes(phase) ? [{
                          command: "python -m unittest discover -s tests -v",
                          exit_code: status === "PASS" ? 0 : 1,
                          status: status === "PASS" ? "PASS" : "FAIL",
                          output_summary: status === "PASS"
                            ? "tests passed"
                            : "legacy contract expectation failed",
                        }] : [],
                        artifacts: [],
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: root,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: status }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: root,
                    metadata: () => {},
                  },
                )
                const recoveryEvents = fs.readFileSync(
                  root + "/.biexce/state/AUTOPILOT_EVENTS.jsonl",
                  "utf8",
                ).trim().split(/\r?\n/).map((line) => JSON.parse(line))
                  .filter((event) => event.event === "RUNTIME_TASK_RECOVERED")
                console.log(JSON.stringify({
                  pointerAtFirstPrompt,
                  phaseAtFirstPrompt,
                  phasesSeen,
                  terminalReason: result.metadata.terminal_reason,
                  recoveredTasks: result.metadata.recovered_tasks,
                  recoveryRoutes: result.metadata.recovered_routes,
                  recoveryReasons: result.metadata.recovery_reasons,
                  recoveryEvents,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["pointerAtFirstPrompt"], "t-002")
            self.assertEqual(payload["phaseAtFirstPrompt"], "TEST")
            task_two_phases = [
                phase for phase in payload["phasesSeen"]
                if phase.startswith("t-002:")
            ]
            self.assertEqual(
                task_two_phases[:3],
                ["t-002:TEST", "t-002:FIX", "t-002:TEST"],
            )
            self.assertEqual(payload["terminalReason"], "WAITING_GATE_2")
            self.assertEqual(payload["recoveredTasks"], ["t-002"])
            self.assertEqual(payload["recoveryRoutes"], {"t-002": "TEST"})
            self.assertEqual(
                payload["recoveryReasons"],
                {"t-002": "PROJECT_SCOPE_REVERIFY"},
            )
            self.assertEqual(len(payload["recoveryEvents"]), 1)

    def test_driver_adjudicates_fix_cap_once_and_reaches_gate_two(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const scheduler = await import(
                  new URL("../runtime/scheduler.js", process.env.PLUGIN_URL)
                )
                const jobs = await import(
                  new URL("../runtime/job-board.js", process.env.PLUGIN_URL)
                )
                const root = process.env.PROJECT
                const schedulerPath = root + "/.biexce/state/AUTOPILOT_SCHEDULER.json"
                const projectStatePath = root + "/.biexce/state/PROJECT_STATE.json"
                const workflowPath = root + "/.biexce/state/AUTOPILOT_WORKFLOW.json"
                scheduler.initializeScheduler(root, {
                  localConcurrency: 4,
                  cloudConcurrency: 3,
                  readOnlyConcurrency: 4,
                })
                const state = scheduler.loadSchedulerState(root)
                const now = "2026-08-12T02:00:00.000Z"
                state.revision += 1
                state.updated_at_utc = now
                state.tasks["t-001"] = {
                  ...state.tasks["t-001"],
                  phase: "DONE",
                  status: "DONE",
                  last_job_id: "job-t-001-task_review-bx-review-r0",
                  last_result: "APPROVE",
                  updated_at_utc: now,
                }
                state.tasks["t-002"] = {
                  ...state.tasks["t-002"],
                  phase: "BLOCKED",
                  status: "BLOCKED",
                  fix_round: 3,
                  last_job_id: "job-t-002-task_review-bx-review-r3",
                  last_result: "CHANGES_REQUIRED",
                  error: "Fix cap blocked t-002",
                  updated_at_utc: now,
                }
                fs.writeFileSync(schedulerPath, JSON.stringify(state, null, 2) + "\n")
                jobs.putJob(root, {
                  job_id: "job-t-002-task_review-bx-review-r3",
                  trace_id: "trace-fix-cap",
                  task_id: "t-002",
                  agent: "bx-review",
                  session_id: null,
                  phase: "TASK_REVIEW",
                  status: "COMPLETED",
                  dependencies: state.tasks["t-002"].dependencies,
                  read_scope: state.tasks["t-002"].read_scope,
                  write_scope: [],
                  model: "openai/gpt-5.6-terra",
                  attempt: 1,
                  recovery_count: 0,
                  started_at_utc: now,
                  deadline_at_utc: null,
                  completed_at_utc: now,
                  result_status: "CHANGES_REQUIRED",
                  error: "Fix cap blocked t-002",
                })
                const project = JSON.parse(fs.readFileSync(projectStatePath, "utf8"))
                for (const task of project.tasks) {
                  task.status = task.id === "t-001"
                    ? "done"
                    : task.id === "t-002" ? "escalated" : "backlog"
                  task.round = task.id === "t-002" ? 3 : task.round
                  task.agent = null
                }
                project.stage = "B3"
                fs.writeFileSync(projectStatePath, JSON.stringify(project, null, 2) + "\n")
                const workflow = JSON.parse(fs.readFileSync(workflowPath, "utf8"))
                workflow.phase = "BLOCKED"
                workflow.current_task_id = "t-002"
                workflow.fix_round = 3
                workflow.last_agent = "bx-review"
                workflow.last_result = "CHANGES_REQUIRED"
                workflow.blocked_reason = "Fix cap blocked t-002"
                workflow.updated_at_utc = now
                fs.writeFileSync(workflowPath, JSON.stringify(workflow, null, 2) + "\n")

                let hooks = null
                let childCount = 0
                const phasesSeen = []
                const client = { session: {
                  create: async () => ({
                    data: { id: "fix-cap-child-" + (++childCount) },
                  }),
                  prompt: async (request) => {
                    const text = request.body.parts[0].text
                    const phase = text.match(/phase=([A-Z_]+)/)[1]
                    const taskMatch = text.match(/task_id=(t-[0-9]{3})/)
                    const taskID = taskMatch ? taskMatch[1] : null
                    phasesSeen.push((taskID || "project") + ":" + phase)
                    const status = {
                      CODE: "SUCCEEDED",
                      FIX: "SUCCEEDED",
                      TEST: "PASS",
                      TASK_REVIEW: "APPROVE",
                      INTEGRATION_TEST: "PASS",
                      INTEGRATION_REVIEW: "APPROVE",
                    }[phase]
                    const current = JSON.parse(fs.readFileSync(workflowPath, "utf8"))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: current.revision,
                        phase,
                        task_id: taskID,
                        agent: request.body.agent,
                        status,
                        summary: (taskID || "project") + " " + phase + " " + status,
                        changed_files: [],
                        checks: ["TEST", "INTEGRATION_TEST"].includes(phase) ? [{
                          command: "python -m unittest discover -s tests -v",
                          exit_code: 0,
                          status: "PASS",
                          output_summary: "tests passed",
                        }] : [],
                        artifacts: [],
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: root,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: status }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: root,
                    metadata: () => {},
                  },
                )
                console.log(JSON.stringify({
                  metadata: result.metadata,
                  phasesSeen,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(
                payload["metadata"]["terminal_reason"], "WAITING_GATE_2"
            )
            self.assertEqual(payload["metadata"]["recovered_tasks"], ["t-002"])
            self.assertEqual(
                payload["metadata"]["recovered_routes"], {"t-002": "FIX"}
            )
            self.assertEqual(
                payload["metadata"]["recovery_reasons"],
                {"t-002": "FIX_CAP_STANDARD_ADJUDICATION"},
            )
            self.assertEqual(payload["phasesSeen"][0], "t-002:FIX")
            self.assertIn("t-002:TEST", payload["phasesSeen"])
            self.assertIn("t-002:TASK_REVIEW", payload["phasesSeen"])

    def test_driver_carries_test_and_review_evidence_into_downstream_jobs(self):
        with tempfile.TemporaryDirectory() as temporary:
            helper = runtime_workflow.RuntimeWorkflowTests(methodName="runTest")
            project, config, plugin = helper.prepare(Path(temporary))
            helper.set_waiting_gate_one(project)
            helper.approve_runtime_gate(project, config, plugin, 1)
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                let firstReview = true
                let reviewSawTestEvidence = false
                let fixSawReviewEvidence = false
                const client = { session: {
                  create: async () => ({
                    data: { id: "evidence-child-" + (++childCount) },
                  }),
                  prompt: async (request) => {
                    const text = request.body.parts[0].text
                    const taskMatch = text.match(/task_id=(t-[0-9]{3})/)
                    const taskID = taskMatch ? taskMatch[1] : null
                    const phase = text.match(/phase=([A-Z_]+)/)[1]
                    if (phase === "TASK_REVIEW") {
                      reviewSawTestEvidence ||= text.includes(
                        "RUNTIME-AUTHORITATIVE PRIOR TASK EVIDENCE",
                      ) && text.includes('"phase": "TEST"') &&
                        text.includes('"status": "PASS"')
                    }
                    if (phase === "FIX") {
                      fixSawReviewEvidence ||= text.includes(
                        "RUNTIME-AUTHORITATIVE PRIOR TASK EVIDENCE",
                      ) && text.includes('"phase": "TASK_REVIEW"') &&
                        text.includes("calculator/__init__.py:1")
                    }
                    let status = {
                      CODE: "SUCCEEDED",
                      FIX: "SUCCEEDED",
                      TEST: "PASS",
                      TASK_REVIEW: "APPROVE",
                      INTEGRATION_TEST: "PASS",
                      INTEGRATION_REVIEW: "APPROVE",
                    }[phase]
                    let summary = taskID + " " + phase + " " + status
                    if (phase === "TASK_REVIEW" && taskID === "t-001" && firstReview) {
                      firstReview = false
                      status = "CHANGES_REQUIRED"
                      summary = "[Major] calculator/__init__.py:1 — acceptance mismatch"
                    }
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    const checks = ["TEST", "INTEGRATION_TEST"].includes(phase) ? [{
                      command: "python -m unittest discover -s tests -v",
                      exit_code: 0,
                      status: "PASS",
                      output_summary: "all tests passed",
                    }] : []
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase,
                        task_id: taskID,
                        agent: request.body.agent,
                        status,
                        summary,
                        changed_files: [],
                        checks,
                        artifacts: [],
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: status }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                  },
                )
                const events = fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_EVENTS.jsonl",
                  "utf8",
                ).trim().split(/\r?\n/).map((line) => JSON.parse(line))
                console.log(JSON.stringify({
                  metadata: result.metadata,
                  reviewSawTestEvidence,
                  fixSawReviewEvidence,
                  resultEvents: events.filter(
                    (event) => event.event === "JOB_RESULT_RECORDED",
                  ).length,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["metadata"]["terminal_reason"], "WAITING_GATE_2")
            self.assertTrue(payload["reviewSawTestEvidence"])
            self.assertTrue(payload["fixSawReviewEvidence"])
            self.assertEqual(payload["resultEvents"], 14)

    def test_local_model_capacity_blocks_second_parallel_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(
                Path(temporary),
                local_code=True,
            )
            script = textwrap.dedent(
                """
                process.env.BIEXCE_LOCAL_CONCURRENCY = "1"
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                let signalStarted
                let releaseFirst
                const started = new Promise((resolve) => { signalStarted = resolve })
                const release = new Promise((resolve) => { releaseFirst = resolve })
                const client = { session: {
                  create: async () => ({
                    data: { id: "local-child-" + (++childCount) },
                  }),
                  prompt: async (request) => {
                    signalStarted()
                    await release
                    const text = request.body.parts[0].text
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: "CODE",
                        task_id: text.match(/task_id=(t-[0-9]{3})/)[1],
                        agent: "bx-code",
                        status: "SUCCEEDED",
                        summary: "local code complete",
                        changed_files: [],
                        checks: [],
                        artifacts: [],
                      }) },
                      {
                        agent: "bx-code",
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  metadata: () => {},
                }
                const first = hooks.tool.biexce_start_job.execute(
                  { task_id: "t-001", capability: "bx-code" },
                  context,
                )
                await started
                let blocked = ""
                try {
                  await hooks.tool.biexce_start_job.execute(
                    { task_id: "t-002", capability: "bx-code" },
                    context,
                  )
                } catch (error) {
                  blocked = error.message
                }
                releaseFirst()
                await first
                const scheduler = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                  "utf8",
                ))
                console.log(JSON.stringify({
                  blocked,
                  childCount,
                  secondStatus: scheduler.tasks["t-002"].status,
                  localConcurrency: scheduler.local_concurrency,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertIn("SCHEDULER_WAITING_MODEL", payload["blocked"])
            self.assertEqual(payload["childCount"], 1)
            self.assertEqual(payload["secondStatus"], "BACKLOG")
            self.assertEqual(payload["localConcurrency"], 1)

    def test_driver_pause_stops_between_batches_without_manual_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                const client = { session: {
                  create: async () => ({
                    data: { id: "pause-child-" + (++childCount) },
                  }),
                  prompt: async (request) => {
                    const text = request.body.parts[0].text
                    const taskID = text.match(/task_id=(t-[0-9]{3})/)[1]
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: "CODE",
                        task_id: taskID,
                        agent: "bx-code",
                        status: "SUCCEEDED",
                        summary: "code complete before pause",
                        changed_files: [],
                        checks: [],
                        artifacts: [],
                      }) },
                      {
                        agent: "bx-code",
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    const controlPath =
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_CONTROL.json"
                    const control = JSON.parse(fs.readFileSync(controlPath, "utf8"))
                    control.mode = "PAUSED"
                    control.revision += 1
                    control.action = "pause"
                    control.reason = "unit test pause"
                    fs.writeFileSync(controlPath, JSON.stringify(control, null, 2) + "\\n")
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_drive.execute(
                  { profile: "critical", allow_critical_downgrade: false },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                  },
                )
                const scheduler = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                  "utf8",
                ))
                console.log(JSON.stringify({
                  metadata: result.metadata,
                  childCount,
                  firstPhase: scheduler.tasks["t-001"].phase,
                  firstStatus: scheduler.tasks["t-001"].status,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["metadata"]["driver_status"], "PAUSED")
            self.assertEqual(payload["metadata"]["terminal_reason"], "CONTROL_STOPPED")
            self.assertEqual(payload["childCount"], 1)
            self.assertEqual(payload["firstPhase"], "TEST")
            self.assertEqual(payload["firstStatus"], "READY")

    def test_driver_finishes_independent_work_before_reporting_blocker(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                const client = { session: {
                  create: async () => ({
                    data: { id: "block-child-" + (++childCount) },
                  }),
                  prompt: async (request) => {
                    const text = request.body.parts[0].text
                    const taskID = text.match(/task_id=(t-[0-9]{3})/)[1]
                    const phase = text.match(/phase=([A-Z_]+)/)[1]
                    const status = phase === "CODE"
                      ? "SUCCEEDED"
                      : phase === "TEST"
                        ? taskID === "t-001" ? "INCONCLUSIVE" : "PASS"
                        : "APPROVE"
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase,
                        task_id: taskID,
                        agent: request.body.agent,
                        status,
                        summary: taskID + " " + status,
                        changed_files: [],
                        checks: phase === "TEST" ? [{
                          command: "fixture-check",
                          exit_code: status === "PASS" ? 0 : 2,
                          status: status === "PASS" ? "PASS" : "FAIL",
                          output_summary: status,
                        }] : [],
                        artifacts: [],
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: status }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                  },
                )
                const scheduler = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                  "utf8",
                ))
                console.log(JSON.stringify({
                  metadata: result.metadata,
                  phases: Object.fromEntries(Object.entries(scheduler.tasks).map(
                    ([id, task]) => [id, task.phase],
                  )),
                  childCount,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertEqual(payload["metadata"]["driver_status"], "PAUSED")
            self.assertEqual(
                payload["metadata"]["terminal_reason"],
                "AGENT_RETRY_EXHAUSTED",
            )
            self.assertEqual(payload["phases"]["t-001"], "TEST")
            self.assertEqual(payload["phases"]["t-002"], "DONE")
            self.assertEqual(payload["phases"]["t-003"], "CODE")
            self.assertGreaterEqual(payload["childCount"], 5)

    def test_cancel_then_resume_requires_no_manual_state_edit(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let childCount = 0
                let abortCount = 0
                let firstPrompt = true
                let signalStarted
                const started = new Promise((resolve) => { signalStarted = resolve })
                const client = { session: {
                  create: async () => ({
                    data: { id: "resume-child-" + (++childCount) },
                  }),
                  prompt: async (request) => {
                    if (firstPrompt) {
                      firstPrompt = false
                      signalStarted()
                      return await new Promise(() => {})
                    }
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: "CODE",
                        task_id: "t-001",
                        agent: "bx-code",
                        status: "SUCCEEDED",
                        summary: "resumed code complete",
                        changed_files: [],
                        checks: [],
                        artifacts: [],
                      }) },
                      {
                        agent: "bx-code",
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                  abort: async () => {
                    abortCount += 1
                    return { data: true }
                  },
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  metadata: () => {},
                }
                const jobID = "job-t-001-code-bx-code-r0"
                const running = hooks.tool.biexce_start_job.execute(
                  { task_id: "t-001", capability: "bx-code" },
                  context,
                )
                await started
                const cancelled = await hooks.tool.biexce_cancel_job.execute(
                  { job_id: jobID, reason: "operator requested retry" },
                  context,
                )
                let firstError = ""
                try {
                  await running
                } catch (error) {
                  firstError = error.message
                }
                const before = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                  "utf8",
                ))
                const resumed = await hooks.tool.biexce_resume_job.execute(
                  { job_id: jobID },
                  context,
                )
                const after = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                  "utf8",
                ))
                console.log(JSON.stringify({
                  cancelled: cancelled.metadata.cancelled,
                  firstError,
                  beforeStatus: before.tasks["t-001"].status,
                  childCount,
                  abortCount,
                  resumed: resumed.metadata,
                  afterPhase: after.tasks["t-001"].phase,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertTrue(payload["cancelled"])
            self.assertIn("CANCELLED", payload["firstError"])
            self.assertEqual(payload["beforeStatus"], "READY")
            self.assertEqual(payload["childCount"], 2)
            self.assertGreaterEqual(payload["abortCount"], 1)
            self.assertEqual(payload["resumed"]["task_next_phase"], "TEST")
            self.assertEqual(payload["afterPhase"], "TEST")

    def test_direct_ui_abort_is_cancelled_and_releases_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const client = { session: {
                  create: async () => ({ data: { id: "ui-aborted-child" } }),
                  prompt: async () => {
                    throw new Error("Request aborted by OpenCode UI")
                  },
                  abort: async () => ({ data: true }),
                }}
                const hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                let runtimeError = ""
                try {
                  await hooks.tool.biexce_start_job.execute(
                    { task_id: "t-001", capability: "bx-code" },
                    {
                      agent: "bx-director",
                      sessionID: "session-1",
                      directory: process.env.PROJECT,
                      metadata: () => {},
                    },
                  )
                } catch (error) {
                  runtimeError = error.message
                }
                const scheduler = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SCHEDULER.json",
                  "utf8",
                ))
                const jobs = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_JOBS.json",
                  "utf8",
                ))
                const sessions = JSON.parse(fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_SESSIONS.json",
                  "utf8",
                ))
                const jobID = "job-t-001-code-bx-code-r0"
                console.log(JSON.stringify({
                  runtimeError,
                  schedulerStatus: scheduler.tasks["t-001"].status,
                  activeJob: scheduler.tasks["t-001"].active_job_id,
                  jobStatus: jobs.jobs[jobID].status,
                  sessionStatus: sessions.sessions[jobID].status,
                }))
                """
            )
            payload = self.run_node(project, config, plugin, script)
            self.assertIn("CANCELLED", payload["runtimeError"])
            self.assertEqual(payload["schedulerStatus"], "READY")
            self.assertIsNone(payload["activeJob"])
            self.assertEqual(payload["jobStatus"], "CANCELLED")
            self.assertEqual(payload["sessionStatus"], "CANCELLED")

    def test_driver_reconciles_power_loss_and_continues_without_manual_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const scheduler = await import(new URL(
                  "../runtime/scheduler.js", process.env.PLUGIN_URL,
                ))
                const board = await import(new URL(
                  "../runtime/job-board.js", process.env.PLUGIN_URL,
                ))
                const routing = JSON.parse(fs.readFileSync(
                  process.env.CONFIG + "/model-routing.applied.json", "utf8",
                )).routing.agents
                const options = {
                  localConcurrency: 1,
                  cloudConcurrency: 3,
                  readOnlyConcurrency: 4,
                }
                scheduler.initializeScheduler(process.env.PROJECT, options)
                const orphaned = scheduler.claimSchedulerJob({
                  projectRoot: process.env.PROJECT,
                  taskID: "t-001",
                  requestedAgent: "bx-code",
                  routing,
                  options,
                })
                board.putJob(process.env.PROJECT, {
                  job_id: orphaned.job_id,
                  trace_id: "trace-power-loss-plugin",
                  task_id: orphaned.task_id,
                  agent: orphaned.agent,
                  session_id: "lost-child-session",
                  phase: orphaned.phase,
                  status: "RUNNING",
                  dependencies: orphaned.dependencies,
                  read_scope: orphaned.read_scope,
                  write_scope: orphaned.write_scope,
                  model: orphaned.model,
                })

                let hooks = null
                const created = []
                const client = { session: {
                  create: async (request) => {
                    const id = "restart-child-" + (created.length + 1)
                    created.push({ id, title: request.body.title })
                    return { data: { id } }
                  },
                  prompt: async (request) => {
                    const text = request.body.parts[0].text
                    const phase = text.match(/phase=([A-Z_]+)/)[1]
                    const taskMatch = text.match(/task_id=(t-[0-9]{3})/)
                    const taskID = taskMatch ? taskMatch[1] : null
                    const status = {
                      CODE: "SUCCEEDED",
                      TEST: "PASS",
                      FIX: "SUCCEEDED",
                      TASK_REVIEW: "APPROVE",
                      INTEGRATION_TEST: "PASS",
                      INTEGRATION_REVIEW: "APPROVE",
                    }[phase]
                    const workflow = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_WORKFLOW.json",
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase,
                        task_id: taskID,
                        agent: request.body.agent,
                        status,
                        summary: (taskID || "project") + " " + phase + " complete",
                        changed_files: [],
                        checks: ["TEST", "INTEGRATION_TEST"].includes(phase) ? [{
                          command: "python -m unittest",
                          exit_code: 0,
                          status: "PASS",
                          output_summary: "all tests passed",
                        }] : [],
                        artifacts: [],
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: status }] } }
                  },
                  abort: async () => ({ data: true }),
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                const result = await hooks.tool.biexce_drive.execute(
                  { profile: "standard", allow_critical_downgrade: true },
                  {
                    agent: "bx-director",
                    sessionID: "session-after-restart",
                    directory: process.env.PROJECT,
                    metadata: () => {},
                  },
                )
                const events = fs.readFileSync(
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_EVENTS.jsonl",
                  "utf8",
                ).trim().split(/\r?\n/).map((line) => JSON.parse(line))
                const finalScheduler = scheduler.loadSchedulerState(process.env.PROJECT)
                console.log(JSON.stringify({
                  orphaned: orphaned.job_id,
                  metadata: result.metadata,
                  created,
                  firstTask: finalScheduler.tasks["t-001"],
                  reconcileEvents: events.filter(
                    (event) => event.event === "RUNTIME_STATE_RECONCILED",
                  ),
                }))
                """
            )
            payload = self.run_node(
                project,
                config,
                plugin,
                script,
                extra_environment={"CONFIG": str(config)},
            )
            self.assertEqual(
                payload["metadata"]["terminal_reason"], "WAITING_GATE_2", payload
            )
            self.assertEqual(
                payload["metadata"]["reconciled_jobs"], [payload["orphaned"]]
            )
            self.assertEqual(payload["firstTask"]["phase"], "DONE")
            self.assertIsNone(payload["firstTask"]["active_job_id"])
            self.assertEqual(len(payload["reconcileEvents"]), 1)
            self.assertTrue(payload["created"][0]["title"].startswith("[BX][t-001][CODE]"))

    def test_driver_does_not_steal_a_live_session_with_an_active_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                r"""
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const scheduler = await import(new URL(
                  "../runtime/scheduler.js", process.env.PLUGIN_URL,
                ))
                const board = await import(new URL(
                  "../runtime/job-board.js", process.env.PLUGIN_URL,
                ))
                const routing = JSON.parse(fs.readFileSync(
                  process.env.CONFIG + "/model-routing.applied.json", "utf8",
                )).routing.agents
                const options = {
                  localConcurrency: 1,
                  cloudConcurrency: 3,
                  readOnlyConcurrency: 4,
                }
                scheduler.initializeScheduler(process.env.PROJECT, options)
                const active = scheduler.claimSchedulerJob({
                  projectRoot: process.env.PROJECT,
                  taskID: "t-001",
                  requestedAgent: "bx-code",
                  routing,
                  options,
                })
                board.putJob(process.env.PROJECT, {
                  job_id: active.job_id,
                  trace_id: "trace-live-owner",
                  task_id: active.task_id,
                  agent: active.agent,
                  session_id: "live-child",
                  phase: active.phase,
                  status: "RUNNING",
                  dependencies: active.dependencies,
                  read_scope: active.read_scope,
                  write_scope: active.write_scope,
                  model: active.model,
                })
                const lease = board.acquireJobLease(
                  process.env.PROJECT, active.job_id, "session-1", 60000,
                )
                board.putJob(process.env.PROJECT, {
                  job_id: active.job_id,
                  deadline_at_utc: lease.deadline_at_utc,
                })
                const hooks = await BiexceControlPlugin({ client: { session: {} } })
                await hooks.config({ default_agent: "bx-director", agent: {} })
                let error = ""
                try {
                  await hooks.tool.biexce_drive.execute(
                    { profile: "standard", allow_critical_downgrade: true },
                    {
                      agent: "bx-director",
                      sessionID: "intruder-session",
                      directory: process.env.PROJECT,
                      metadata: () => {},
                    },
                  )
                } catch (caught) {
                  error = caught.message
                }
                const state = scheduler.loadSchedulerState(process.env.PROJECT)
                console.log(JSON.stringify({
                  error,
                  task: state.tasks["t-001"],
                  control: JSON.parse(fs.readFileSync(
                    process.env.PROJECT + "/.biexce/state/AUTOPILOT_CONTROL.json",
                    "utf8",
                  )),
                }))
                """
            )
            payload = self.run_node(
                project,
                config,
                plugin,
                script,
                extra_environment={"CONFIG": str(config)},
            )
            self.assertIn("armed for another session", payload["error"])
            self.assertEqual(payload["task"]["status"], "RUNNING")
            self.assertEqual(payload["task"]["active_job_id"], payload["task"]["last_job_id"])
            self.assertEqual(payload["control"]["session_id"], "session-1")


if __name__ == "__main__":
    unittest.main()
