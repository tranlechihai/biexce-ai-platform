import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
GLOBAL_ROOT = SOURCE_ROOT / "global"
PLUGIN_PATH = GLOBAL_ROOT / "plugins" / "biexce-control.js"
FAILURE_POLICY_PATH = GLOBAL_ROOT / "runtime" / "failure-policy.js"
SCOPE_POLICY_PATH = GLOBAL_ROOT / "runtime" / "scope-policy.js"
JOB_BOARD_PATH = GLOBAL_ROOT / "runtime" / "job-board.js"
RESILIENCE_PATH = GLOBAL_ROOT / "runtime" / "resilience.js"
SESSION_REGISTRY_PATH = GLOBAL_ROOT / "runtime" / "session-registry.js"
SCHEDULER_PATH = GLOBAL_ROOT / "runtime" / "scheduler.js"
SUPERVISOR_PATH = GLOBAL_ROOT / "runtime" / "supervisor.js"
WORKFLOW_POLICY_PATH = GLOBAL_ROOT / "runtime" / "workflow-policy.js"
OBSERVABILITY_PATH = GLOBAL_ROOT / "runtime" / "observability.js"
RECONCILER_PATH = GLOBAL_ROOT / "runtime" / "reconciler.js"
sys.path.insert(0, str(SOURCE_ROOT))

from biexce_control import apply_action, initialize_workflow  # noqa: E402
from biexce_control.fixture import init_fixture  # noqa: E402
from biexce_control.model_routing import (  # noqa: E402
    LOCAL_MODEL,
    apply_routing,
    build_profile,
    clear_fallback,
    save_routing,
    set_fallback,
    set_primary,
)
from biexce_control.validation import validate_project  # noqa: E402
from biexce_control.workflow import (  # noqa: E402
    load_workflow,
    resolve_blocked_workflow,
    workflow_path_for,
)


CLOUD_MODEL = "cloud-provider/strong-model"


@unittest.skipUnless(shutil.which("node"), "Node.js is required for plugin tests")
class RuntimeWorkflowTests(unittest.TestCase):
    def test_agent_result_schema_contract_is_versioned(self):
        schema = json.loads(
            (
                SOURCE_ROOT
                / "biexce_control"
                / "schemas"
                / "agent-result-v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            {
                "$schema", "schema_version", "workflow_revision", "phase",
                "task_id", "agent", "status", "summary", "changed_files",
                "checks", "artifacts",
            },
        )

    def prepare(self, root: Path) -> tuple[Path, Path, Path]:
        project = root / "project"
        config = root / "config"
        runtime = root / "runtime"
        runtime_plugin = runtime / "plugins" / "biexce-control.js"
        runtime_failure_policy = runtime / "runtime" / "failure-policy.js"
        runtime_scope_policy = runtime / "runtime" / "scope-policy.js"
        runtime_job_board = runtime / "runtime" / "job-board.js"
        runtime_resilience = runtime / "runtime" / "resilience.js"
        runtime_session_registry = runtime / "runtime" / "session-registry.js"
        runtime_scheduler = runtime / "runtime" / "scheduler.js"
        runtime_supervisor = runtime / "runtime" / "supervisor.js"
        runtime_workflow_policy = runtime / "runtime" / "workflow-policy.js"
        runtime_observability = runtime / "runtime" / "observability.js"
        runtime_reconciler = runtime / "runtime" / "reconciler.js"
        module_root = runtime / "node_modules" / "@opencode-ai" / "plugin"
        runtime_plugin.parent.mkdir(parents=True)
        runtime_job_board.parent.mkdir(parents=True)
        module_root.mkdir(parents=True)
        shutil.copy2(PLUGIN_PATH, runtime_plugin)
        shutil.copy2(FAILURE_POLICY_PATH, runtime_failure_policy)
        shutil.copy2(SCOPE_POLICY_PATH, runtime_scope_policy)
        shutil.copy2(JOB_BOARD_PATH, runtime_job_board)
        shutil.copy2(RESILIENCE_PATH, runtime_resilience)
        shutil.copy2(SESSION_REGISTRY_PATH, runtime_session_registry)
        shutil.copy2(SCHEDULER_PATH, runtime_scheduler)
        shutil.copy2(SUPERVISOR_PATH, runtime_supervisor)
        shutil.copy2(WORKFLOW_POLICY_PATH, runtime_workflow_policy)
        shutil.copy2(OBSERVABILITY_PATH, runtime_observability)
        shutil.copy2(RECONCILER_PATH, runtime_reconciler)
        (module_root / "package.json").write_text(
            json.dumps(
                {
                    "name": "@opencode-ai/plugin",
                    "type": "module",
                    "exports": "./index.js",
                }
            ),
            encoding="utf-8",
        )
        (module_root / "index.js").write_text(
            textwrap.dedent(
                """
                const chain = { min() { return this }, max() { return this } }
                export const tool = (definition) => definition
                tool.schema = {
                  boolean: () => chain,
                  enum: () => chain,
                  string: () => chain,
                }
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        init_fixture(project)
        (project / ".biexce" / "CODEBASE_BRIEF.md").write_text(
            "# Codebase Brief\n\nFixture source and tests.\n", encoding="utf-8"
        )
        routing = build_profile(
            "cloud-strong", actor="tester", cloud_model=CLOUD_MODEL
        )
        save_routing(routing, config)
        apply_routing(
            actor="tester",
            config_home=config,
            available_models={LOCAL_MODEL, CLOUD_MODEL},
        )
        apply_action(project, "on", actor="tester", reason="enable")
        apply_action(
            project,
            "arm",
            actor="tester",
            reason="runtime workflow test",
            arm_validator=lambda _project, _state: None,
        )
        apply_action(
            project,
            "start",
            actor="tester",
            reason="run",
            session_id="session-1",
        )
        initialize_workflow(project, actor="tester")
        return project, config, runtime_plugin

    def test_runtime_contract_embeds_an_exact_agent_result_template(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, _, runtime_plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                const { runtimeContract } = await import(process.env.PLUGIN_URL)
                const contract = runtimeContract({
                  revision: 7,
                  phase: "EXPLORE",
                  current_task_id: null,
                }, "bx-explore")
                console.log(contract)
                """
            )
            environment = os.environ.copy()
            environment["PLUGIN_URL"] = runtime_plugin.resolve().as_uri()
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
            self.assertIn(
                '"$schema": "https://schemas.biexce.local/runtime/agent-result-v1.schema.json"',
                result.stdout,
            )
            self.assertIn('"schema_version": 1', result.stdout)
            self.assertIn('"workflow_revision": 7', result.stdout)
            self.assertIn('"phase": "EXPLORE"', result.stdout)
            self.assertIn('"task_id": null', result.stdout)
            self.assertIn('"agent": "bx-explore"', result.stdout)
            self.assertIn('"status": "SUCCEEDED"', result.stdout)
            self.assertIn("canonical fields", result.stdout)
            self.assertIn("identity and verification evidence remain strictly validated", result.stdout)

    def test_review_runtime_contract_bounds_the_raw_diff_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, _, runtime_plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                const { runtimeContract } = await import(process.env.PLUGIN_URL)
                const contract = (phase) => runtimeContract({
                  revision: 7,
                  phase,
                  current_task_id: phase === "TASK_REVIEW" ? "t-001" : null,
                }, "bx-review")
                console.log(JSON.stringify({
                  plan: contract("PLAN_REVIEW"),
                  task: contract("TASK_REVIEW"),
                  integration: contract("INTEGRATION_REVIEW"),
                }))
                """
            )
            environment = os.environ.copy()
            environment["PLUGIN_URL"] = runtime_plugin.resolve().as_uri()
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
            contracts = json.loads(result.stdout)
            self.assertIn("does not authorize raw source or raw diff", contracts["plan"])
            for phase in ("task", "integration"):
                self.assertIn("standing Zone A", contracts[phase])
                self.assertIn("This is read-only", contracts[phase])
                self.assertIn("Never read, quote, summarize, or echo Zone C", contracts[phase])

    def test_test_runtime_contract_supplies_deterministic_unittest_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, _, runtime_plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                const { runtimeContract } = await import(process.env.PLUGIN_URL)
                console.log(runtimeContract({
                  revision: 7,
                  phase: "TEST",
                  current_task_id: "t-001",
                }, "bx-test"))
                """
            )
            environment = os.environ.copy()
            environment["PLUGIN_URL"] = runtime_plugin.resolve().as_uri()
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
            self.assertIn(
                "python -m unittest discover -s tests -v",
                result.stdout,
            )
            self.assertIn("even when a legacy story says Verify N/A", result.stdout)

    def run_steps(
        self,
        project: Path,
        config: Path,
        runtime_plugin: Path,
        steps: list[tuple[str, str]],
    ) -> dict[str, object]:
        script = textwrap.dedent(
            """
            import fs from "node:fs"
            const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
            const steps = JSON.parse(process.env.STEPS)
            const outputs = [...steps.map((step) => step.output)]
            let child = 0
            let hooks = null
            const statusFor = (output) => {
              if (output.includes("PLAN NEEDS REVISION")) return "PLAN_NEEDS_REVISION"
              if (output.includes("PLAN OK")) return "PLAN_OK"
              if (output.includes("APPROVE WITH MINOR NOTES")) return "APPROVE_WITH_MINOR_NOTES"
              if (output.includes("CHANGES REQUIRED")) return "CHANGES_REQUIRED"
              if (output.includes("VERDICT: APPROVE")) return "APPROVE"
              if (output.includes("VERDICT: INCONCLUSIVE")) return "INCONCLUSIVE"
              if (output.includes("VERDICT: FAIL")) return "FAIL"
              if (output.includes("VERDICT: PASS")) return "PASS"
              return "SUCCEEDED"
            }
            const client = { session: {
              create: async () => ({ data: { id: `child-${++child}` } }),
              prompt: async (request) => {
                const output = outputs.shift()
                const workflow = JSON.parse(fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                  "utf8",
                ))
                const status = statusFor(output)
                const result = {
                  $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                  schema_version: 1,
                  workflow_revision: workflow.revision,
                  phase: workflow.phase,
                  task_id: workflow.current_task_id,
                  agent: request.body.agent,
                  status,
                  summary: output,
                  changed_files: [],
                  checks: status === "PASS" ? [{
                    command: "fixture-check",
                    exit_code: 0,
                    status: "PASS",
                    output_summary: "fixture check passed",
                  }] : status === "FAIL" ? [{
                    command: "fixture-check",
                    exit_code: 1,
                    status: "FAIL",
                    output_summary: "fixture check failed",
                  }] : status === "INCONCLUSIVE" ? [{
                    command: "fixture-check",
                    exit_code: null,
                    status: "NOT_RUN",
                    output_summary: "fixture check could not run",
                  }] : [],
                  artifacts: workflow.phase === "EXPLORE"
                    ? [".biexce/CODEBASE_BRIEF.md"]
                    : workflow.phase === "PLAN"
                      ? [".biexce/MASTER_PLAN.md"]
                      : [],
                }
                await hooks.tool.biexce_submit_result.execute(
                  { result_json: JSON.stringify(result) },
                  {
                    agent: request.body.agent,
                    sessionID: request.path.id,
                    directory: process.env.PROJECT,
                  },
                )
                return { data: { parts: [{ type: "text", text: output }] } }
              },
            }}
            hooks = await BiexceControlPlugin({ client })
            await hooks.config({ default_agent: "bx-code", agent: {} })
            const transitions = []
            for (const step of steps) {
              const result = await hooks.tool.biexce_delegate.execute(
                { agent: step.agent, description: step.agent, prompt: "fixture task" },
                {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                },
              )
              transitions.push(result.metadata.next_phase)
            }
            const workflow = JSON.parse(fs.readFileSync(
              `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
              "utf8",
            ))
            console.log(JSON.stringify({ transitions, workflow }))
            """
        )
        environment = os.environ.copy()
        environment["BIEXCE_CONFIG_HOME"] = str(config)
        environment["PROJECT"] = str(project)
        environment["PLUGIN_URL"] = runtime_plugin.resolve().as_uri()
        environment["STEPS"] = json.dumps(
            [{"agent": agent, "output": output} for agent, output in steps]
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
        return json.loads(result.stdout)

    def approve_runtime_gate(
        self,
        project: Path,
        config: Path,
        runtime_plugin: Path,
        gate: int,
    ) -> dict[str, object]:
        script = textwrap.dedent(
            """
            import fs from "node:fs"
            const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
            const hooks = await BiexceControlPlugin({ client: {} })
            await hooks.config({ default_agent: "bx-code", agent: {} })
            const result = await hooks.tool.biexce_gate.execute(
              { gate: process.env.GATE, summary: "Runtime gate test." },
              {
                agent: "bx-director",
                sessionID: "session-1",
                directory: process.env.PROJECT,
                ask: async () => {},
              },
            )
            const workflow = JSON.parse(fs.readFileSync(
              `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
              "utf8",
            ))
            const control = JSON.parse(fs.readFileSync(
              `${process.env.PROJECT}/.biexce/state/AUTOPILOT_CONTROL.json`,
              "utf8",
            ))
            console.log(JSON.stringify({ metadata: result.metadata, workflow, control }))
            """
        )
        environment = os.environ.copy()
        environment["BIEXCE_CONFIG_HOME"] = str(config)
        environment["PROJECT"] = str(project)
        environment["PLUGIN_URL"] = runtime_plugin.resolve().as_uri()
        environment["GATE"] = str(gate)
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

    def set_waiting_gate_one(self, project: Path) -> None:
        path = workflow_path_for(project)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["phase"] = "WAITING_GATE_1"
        document["last_agent"] = "bx-review"
        document["last_result"] = "PLAN OK"
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        state_path = project / ".biexce" / "state" / "PROJECT_STATE.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["stage"] = "B2"
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def set_waiting_gate_two(self, project: Path) -> None:
        path = workflow_path_for(project)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["phase"] = "WAITING_GATE_2"
        document["gate_1"] = "APPROVED"
        document["gate_1_approved_by"] = "human"
        document["gate_1_approved_at_utc"] = "2026-08-02T00:00:00Z"
        document["last_agent"] = "bx-review"
        document["last_result"] = "APPROVE"
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

        state_path = project / ".biexce" / "state" / "PROJECT_STATE.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["stage"] = "B5"
        for task in state["tasks"]:
            task["status"] = "done"
            task["agent"] = None
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        reports = project / ".biexce" / "reports"
        (reports / "INTEGRATION_REPORT.md").write_text(
            "# Integration\n\nPASS\n", encoding="utf-8"
        )
        (reports / "FINAL_REPORT.md").write_text(
            "# Final\n\nReady.\n", encoding="utf-8"
        )

    def prepare_parallel(
        self,
        root: Path,
        *,
        local_code: bool = False,
    ) -> tuple[Path, Path, Path]:
        project, config, plugin = self.prepare(root)
        plan_path = project / ".biexce" / "MASTER_PLAN.md"
        plan = plan_path.read_text(encoding="utf-8")
        plan_path.write_text(
            plan.replace("WIP limit: 1", "WIP limit: 2"),
            encoding="utf-8",
        )
        second = project / ".biexce" / "tasks" / "t-002.md"
        second.write_text(
            second.read_text(encoding="utf-8").replace(
                "Depends on: t-001",
                "Depends on: none",
            ).replace(
                "Writable files: src/calculator.py",
                "Writable files: src/multiply.py",
            ),
            encoding="utf-8",
        )
        third = project / ".biexce" / "tasks" / "t-003.md"
        third.write_text(
            third.read_text(encoding="utf-8").replace(
                "Depends on: t-002",
                "Depends on: t-001",
            ),
            encoding="utf-8",
        )
        if local_code:
            clear_fallback(
                "bx-code",
                actor="tester",
                config_home=config,
            )
            set_primary(
                "bx-code",
                LOCAL_MODEL,
                actor="tester",
                config_home=config,
            )
            apply_routing(
                actor="tester",
                config_home=config,
                available_models={LOCAL_MODEL, CLOUD_MODEL},
            )
        self.set_waiting_gate_one(project)
        self.approve_runtime_gate(project, config, plugin, 1)
        return project, config, plugin

    def set_test_phase(self, project: Path) -> None:
        path = workflow_path_for(project)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["phase"] = "TEST"
        document["current_task_id"] = "t-001"
        document["gate_1"] = "APPROVED"
        document["gate_1_approved_by"] = "human"
        document["gate_1_approved_at_utc"] = "2026-08-02T00:00:00Z"
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

        state_path = project / ".biexce" / "state" / "PROJECT_STATE.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["stage"] = "B3"
        for task in state["tasks"]:
            task["status"] = "coding" if task["id"] == "t-001" else "backlog"
            task["agent"] = "bx-code" if task["id"] == "t-001" else None
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def run_result_contract_case(
        self,
        project: Path,
        config: Path,
        plugin: Path,
        mode: str,
    ) -> dict[str, object]:
        script = textwrap.dedent(
            """
            import fs from "node:fs"
            const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
            let hooks = null
            let submitted = null
            const mode = process.env.MODE
            const testModes = new Set([
              "no-evidence", "fail-no-evidence", "inconclusive-no-evidence",
            ])
            const agent = testModes.has(mode) ? "bx-test" : "bx-explore"
            const client = { session: {
              create: async () => ({ data: { id: "contract-child" } }),
              prompt: async (request) => {
                if (mode === "out-of-scope") {
                  fs.writeFileSync(`${process.env.PROJECT}/outside.txt`, "not allowed\\n")
                }
                const workflow = JSON.parse(fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                  "utf8",
                ))
                if (mode === "malformed") {
                  await hooks.tool.biexce_submit_result.execute(
                    { result_json: "{" },
                    { agent, sessionID: request.path.id, directory: process.env.PROJECT },
                  )
                } else {
                  const result = {
                    $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                    schema_version: 1,
                    workflow_revision: mode === "stale"
                      ? workflow.revision + 1
                      : workflow.revision,
                    phase: workflow.phase,
                    task_id: workflow.current_task_id,
                    agent,
                    status: mode === "no-evidence"
                      ? "PASS"
                      : mode === "fail-no-evidence"
                        ? "FAIL"
                        : mode === "inconclusive-no-evidence"
                          ? "INCONCLUSIVE"
                          : "SUCCEEDED",
                    summary: "contract fixture",
                    changed_files: mode === "out-of-scope" ? ["outside.txt"] : [],
                    checks: [],
                    artifacts: testModes.has(mode)
                      ? []
                      : [".biexce/CODEBASE_BRIEF.md"],
                  }
                  submitted = result
                  await hooks.tool.biexce_submit_result.execute(
                    { result_json: JSON.stringify(result) },
                    { agent, sessionID: request.path.id, directory: process.env.PROJECT },
                  )
                }
                return { data: { parts: [{ type: "text", text: "done" }] } }
              },
            }}
            hooks = await BiexceControlPlugin({ client })
            await hooks.config({ default_agent: "bx-code", agent: {} })
            let message = ""
            try {
              await hooks.tool.biexce_delegate.execute(
                { agent, description: mode, prompt: "contract fixture" },
                {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                },
              )
            } catch (error) {
              message = error.message
            }
            let lateMessage = ""
            if (mode === "late") {
              try {
                await hooks.tool.biexce_submit_result.execute(
                  { result_json: JSON.stringify(submitted) },
                  {
                    agent,
                    sessionID: "contract-child",
                    directory: process.env.PROJECT,
                  },
                )
              } catch (error) {
                lateMessage = error.message
              }
            }
            const workflow = JSON.parse(fs.readFileSync(
              `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
              "utf8",
            ))
            console.log(JSON.stringify({ message, lateMessage, workflow }))
            """
        )
        environment = os.environ.copy()
        environment["BIEXCE_CONFIG_HOME"] = str(config)
        environment["PROJECT"] = str(project)
        environment["PLUGIN_URL"] = plugin.resolve().as_uri()
        environment["MODE"] = mode
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

    def test_malformed_agent_result_is_rejected_without_advancing(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            payload = self.run_result_contract_case(
                project, config, plugin, "malformed"
            )
            self.assertIn("not valid JSON", payload["message"])
            self.assertEqual(payload["workflow"]["phase"], "BLOCKED")

    def test_stale_agent_identity_is_rejected_after_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            payload = self.run_result_contract_case(
                project, config, plugin, "stale"
            )
            self.assertIn("stale or belongs to another job", payload["message"])
            self.assertEqual(payload["workflow"]["phase"], "BLOCKED")

    def test_pass_without_exit_code_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            self.set_test_phase(project)
            payload = self.run_result_contract_case(
                project, config, plugin, "no-evidence"
            )
            self.assertIn("PASS requires", payload["message"])
            self.assertEqual(payload["workflow"]["phase"], "BLOCKED")

    def test_fail_without_failed_check_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            self.set_test_phase(project)
            payload = self.run_result_contract_case(
                project, config, plugin, "fail-no-evidence"
            )
            self.assertIn("FAIL requires", payload["message"])
            self.assertEqual(payload["workflow"]["phase"], "BLOCKED")

    def test_inconclusive_without_not_run_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            self.set_test_phase(project)
            payload = self.run_result_contract_case(
                project, config, plugin, "inconclusive-no-evidence"
            )
            self.assertIn("INCONCLUSIVE requires", payload["message"])
            self.assertEqual(payload["workflow"]["phase"], "BLOCKED")

    def test_out_of_scope_change_is_rejected_without_advancing(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            payload = self.run_result_contract_case(
                project, config, plugin, "out-of-scope"
            )
            self.assertIn("exceeds writable scope", payload["message"])
            self.assertEqual(payload["workflow"]["phase"], "BLOCKED")

    def test_late_result_cannot_overwrite_completed_job_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            payload = self.run_result_contract_case(project, config, plugin, "late")
            self.assertEqual(payload["message"], "")
            self.assertIn("no matching active child job", payload["lateMessage"])
            self.assertEqual(payload["workflow"]["phase"], "PLAN")
            self.assertEqual(payload["workflow"]["revision"], 2)

    def test_full_b1_to_b5_flow_stops_at_both_human_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            planning = self.run_steps(
                project,
                config,
                plugin,
                [
                    ("bx-explore", "Codebase brief ready."),
                    ("bx-plan", "Plan and task contracts ready."),
                    ("bx-review", "Plan is bounded.\nVERDICT: PLAN OK"),
                ],
            )
            self.assertEqual(
                planning["transitions"],
                ["PLAN", "PLAN_REVIEW", "WAITING_GATE_1"],
            )
            self.assertEqual(load_workflow(project).phase, "WAITING_GATE_1")

            approved = self.approve_runtime_gate(project, config, plugin, 1)
            self.assertEqual(approved["workflow"]["phase"], "CODE")
            self.assertEqual(approved["workflow"]["current_task_id"], "t-001")

            execution = self.run_steps(
                project,
                config,
                plugin,
                [
                    ("bx-code", "Task t-001 implemented."),
                    ("bx-test", "Checks pass.\nVERDICT: PASS"),
                    ("bx-review", "Diff accepted.\nVERDICT: APPROVE"),
                    ("bx-code", "Task t-002 implemented."),
                    ("bx-test", "Checks pass.\nVERDICT: PASS"),
                    ("bx-review", "Diff accepted.\nVERDICT: APPROVE"),
                    ("bx-code", "Task t-003 implemented."),
                    ("bx-test", "Checks pass.\nVERDICT: PASS"),
                    ("bx-review", "Diff accepted.\nVERDICT: APPROVE"),
                    ("bx-test", "Regression passes.\nVERDICT: PASS"),
                    ("bx-review", "Integration accepted.\nVERDICT: APPROVE"),
                ],
            )
            self.assertEqual(execution["workflow"]["phase"], "WAITING_GATE_2")
            board = json.loads(
                (project / ".biexce" / "state" / "AUTOPILOT_JOBS.json").read_text(
                    encoding="utf-8"
                )
            )
            plan_review = next(
                job for job in board["jobs"].values()
                if job["phase"] == "PLAN_REVIEW"
            )
            integration_review = next(
                job for job in board["jobs"].values()
                if job["phase"] == "INTEGRATION_REVIEW"
            )
            self.assertNotIn("**", plan_review["read_scope"])
            self.assertIn("**", integration_review["read_scope"])
            project_state = json.loads(
                (project / ".biexce" / "state" / "PROJECT_STATE.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(all(task["status"] == "done" for task in project_state["tasks"]))
            self.assertEqual(project_state["stage"], "B5")

            reports = project / ".biexce" / "reports"
            (reports / "INTEGRATION_REPORT.md").write_text(
                "# Integration report\n\nPASS\n", encoding="utf-8"
            )
            (reports / "FINAL_REPORT.md").write_text(
                "# Final report\n\nReady.\n", encoding="utf-8"
            )
            completed = self.approve_runtime_gate(project, config, plugin, 2)
            self.assertEqual(completed["workflow"]["phase"], "COMPLETE")
            self.assertEqual(completed["control"]["mode"], "OFF")
            self.assertEqual(list((project / ".biexce" / "state").glob("*.tmp")), [])

    def test_plan_generates_project_state_without_human_json_editing(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            state_path = project / ".biexce" / "state" / "PROJECT_STATE.json"
            state_path.unlink()
            result = self.run_steps(
                project,
                config,
                plugin,
                [
                    ("bx-explore", "Codebase brief ready."),
                    ("bx-plan", "Plan and task contracts ready."),
                ],
            )
            self.assertEqual(result["workflow"]["phase"], "PLAN_REVIEW")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["project"], "biexce-self-test-calculator")
            self.assertEqual([task["id"] for task in state["tasks"]], [
                "t-001", "t-002", "t-003",
            ])
            self.assertTrue(all(task["status"] == "backlog" for task in state["tasks"]))

    def test_runtime_migrates_legacy_workflow_before_transition(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            path = workflow_path_for(project)
            legacy = json.loads(path.read_text(encoding="utf-8"))
            legacy.pop("transition_authority")
            legacy["$schema"] = (
                "https://schemas.biexce.local/control-plane/"
                "autopilot-workflow-v1.schema.json"
            )
            legacy["schema_version"] = 1
            path.write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")

            result = self.run_steps(
                project,
                config,
                plugin,
                [("bx-explore", "Codebase brief ready.")],
            )

            self.assertEqual(result["workflow"]["schema_version"], 2)
            self.assertEqual(
                result["workflow"]["transition_authority"], "biexce-runtime"
            )
            self.assertEqual(result["workflow"]["phase"], "PLAN")
            self.assertEqual(result["workflow"]["revision"], 2)

    def test_fourth_failure_blocks_after_three_fix_rounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            self.set_waiting_gate_one(project)
            self.approve_runtime_gate(project, config, plugin, 1)
            result = self.run_steps(
                project,
                config,
                plugin,
                [
                    ("bx-code", "Initial implementation."),
                    ("bx-test", "Failure one.\nVERDICT: FAIL"),
                    ("bx-fix", "Fix one."),
                    ("bx-test", "Failure two.\nVERDICT: FAIL"),
                    ("bx-fix", "Fix two."),
                    ("bx-test", "Failure three.\nVERDICT: FAIL"),
                    ("bx-fix", "Fix three."),
                    ("bx-test", "Failure four.\nVERDICT: FAIL"),
                ],
            )
            self.assertEqual(result["workflow"]["phase"], "BLOCKED")
            self.assertEqual(result["workflow"]["fix_round"], 3)
            project_state = json.loads(
                (project / ".biexce" / "state" / "PROJECT_STATE.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(project_state["tasks"][0]["status"], "escalated")
            self.assertEqual(project_state["tasks"][0]["round"], 3)

    def test_runtime_consumes_manual_fix_command_and_writes_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            self.set_waiting_gate_one(project)
            self.approve_runtime_gate(project, config, plugin, 1)
            self.run_steps(
                project,
                config,
                plugin,
                [
                    ("bx-code", "Initial implementation."),
                    ("bx-test", "Failure one.\nVERDICT: FAIL"),
                    ("bx-fix", "Fix one."),
                    ("bx-test", "Failure two.\nVERDICT: FAIL"),
                    ("bx-fix", "Fix two."),
                    ("bx-test", "Failure three.\nVERDICT: FAIL"),
                    ("bx-fix", "Fix three."),
                    ("bx-test", "Failure four.\nVERDICT: FAIL"),
                ],
            )
            unchanged, command = resolve_blocked_workflow(
                project,
                action="manual-fix",
                actor="human",
                reason="Apply one approved bounded fix.",
            )
            self.assertEqual(unchanged.phase, "BLOCKED")

            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const hooks = await BiexceControlPlugin({ client: {} })
                await hooks.config({ default_agent: "bx-code", agent: {} })
                await hooks["chat.message"]({
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  model: { providerID: "cloud-provider", modelID: "strong-model" },
                })
                const root = `${process.env.PROJECT}/.biexce/state`
                console.log(JSON.stringify({
                  workflow: JSON.parse(fs.readFileSync(`${root}/AUTOPILOT_WORKFLOW.json`, "utf8")),
                  project: JSON.parse(fs.readFileSync(`${root}/PROJECT_STATE.json`, "utf8")),
                  commandExists: fs.existsSync(`${root}/AUTOPILOT_COMMAND.json`),
                  audit: fs.readFileSync(`${root}/AUTOPILOT_RECOVERY.jsonl`, "utf8").trim(),
                }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
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
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            event = json.loads(payload["audit"])
            self.assertEqual(payload["workflow"]["phase"], "FIX")
            self.assertEqual(
                payload["workflow"]["revision"], command["workflow_revision"] + 1
            )
            self.assertFalse(payload["commandExists"])
            self.assertEqual(payload["project"]["tasks"][0]["status"], "fixing")
            self.assertEqual(payload["project"]["tasks"][0]["agent"], "bx-fix")
            self.assertEqual(event["workflow_revision_before"], command["workflow_revision"])
            self.assertEqual(
                event["workflow_revision_after"], command["workflow_revision"] + 1
            )

    def test_third_plan_rejection_blocks_after_two_revisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            result = self.run_steps(
                project,
                config,
                plugin,
                [
                    ("bx-explore", "Codebase brief ready."),
                    ("bx-plan", "Initial plan ready."),
                    ("bx-review", "Revise.\nVERDICT: PLAN NEEDS REVISION"),
                    ("bx-plan", "Revision one ready."),
                    ("bx-review", "Revise.\nVERDICT: PLAN NEEDS REVISION"),
                    ("bx-plan", "Revision two ready."),
                    ("bx-review", "Still unsafe.\nVERDICT: PLAN NEEDS REVISION"),
                ],
            )
            self.assertEqual(result["workflow"]["phase"], "BLOCKED")
            self.assertEqual(result["workflow"]["plan_revision"], 2)
            self.assertEqual(
                result["workflow"]["blocked_reason"], "Plan revision cap reached"
            )

    def test_per_job_lease_blocks_duplicate_job_across_instances(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let releasePrompt
                let signalStarted
                let firstHooks
                const started = new Promise((resolve) => { signalStarted = resolve })
                const held = new Promise((resolve) => { releasePrompt = resolve })
                const client = { session: {
                  create: async () => ({ data: { id: "child" } }),
                  prompt: async (request) => {
                    signalStarted()
                    await held
                    const workflow = JSON.parse(fs.readFileSync(
                      `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                      "utf8",
                    ))
                    await firstHooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: workflow.phase,
                        task_id: workflow.current_task_id,
                        agent: request.body.agent,
                        status: "SUCCEEDED",
                        summary: "explore complete",
                        changed_files: [],
                        checks: [],
                        artifacts: [".biexce/CODEBASE_BRIEF.md"],
                      }) },
                      { agent: request.body.agent, sessionID: request.path.id, directory: process.env.PROJECT },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                }}
                firstHooks = await BiexceControlPlugin({ client })
                const secondHooks = await BiexceControlPlugin({ client })
                await firstHooks.config({ default_agent: "bx-code", agent: {} })
                await secondHooks.config({ default_agent: "bx-code", agent: {} })
                const args = { agent: "bx-explore", description: "explore", prompt: "fixture" }
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                }
                const first = firstHooks.tool.biexce_delegate.execute(args, context)
                await started
                let denied = false
                try {
                  await secondHooks.tool.biexce_delegate.execute(args, context)
                } catch (error) {
                  denied = error.message.includes("job lease is already active")
                }
                releasePrompt()
                await first
                const leases = `${process.env.PROJECT}/.biexce/state/leases`
                const remaining = fs.existsSync(leases)
                  ? fs.readdirSync(leases).filter((name) => name.endsWith(".json"))
                  : []
                if (!denied || remaining.length !== 0) {
                  throw new Error("per-job lease failed")
                }
                console.log(JSON.stringify({ ok: true }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
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
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)["ok"])

    def test_child_is_visible_and_long_lived_server_command_is_denied(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks
                let permissionHooks
                let processDenied = false
                let commandDenied = false
                let allowedWritePermission = null
                let deniedWritePermission = null
                let outsideWriteDenied = false
                const permissionReplies = []
                const metadata = []
                const client = {
                  postSessionIdPermissionsPermissionId: async (request) => {
                    permissionReplies.push(request.body.response)
                    return { data: true }
                  },
                  session: {
                  create: async () => ({ data: { id: "visible-child" } }),
                  prompt: async (request) => {
                    try {
                      await hooks["tool.execute.before"](
                        { tool: "bash", sessionID: "visible-child", callID: "call-1" },
                        { args: { command: "python -m uvicorn app.main:app --port 8199" } },
                      )
                    } catch (error) {
                      processDenied = error.message.includes("PROCESS_DENY")
                    }
                    await permissionHooks.event({ event: {
                      type: "permission.updated",
                      properties: {
                        id: "permission-allow",
                        permission: "edit",
                        sessionID: "visible-child",
                        metadata: {
                          filepath: `${process.env.PROJECT}/.biexce/CODEBASE_BRIEF.md`,
                        },
                      },
                    } })
                    allowedWritePermission = permissionReplies.at(-1)
                    const replyCount = permissionReplies.length
                    await permissionHooks.event({ event: {
                      type: "permission.asked",
                      properties: {
                        id: "permission-deny",
                        permission: "edit",
                        sessionID: "visible-child",
                        metadata: {
                          filepath: `${process.env.PROJECT}/src/outside-scope.py`,
                        },
                      },
                    } })
                    deniedWritePermission = permissionReplies.length === replyCount
                      ? null
                      : permissionReplies.at(-1)
                    try {
                      await hooks["tool.execute.before"](
                        {
                          tool: "write_file",
                          sessionID: "visible-child",
                          callID: "outside-write",
                        },
                        {
                          args: {
                            path: `${process.env.PROJECT}/src/outside-scope.py`,
                            content: "forbidden",
                          },
                        },
                      )
                    } catch (error) {
                      outsideWriteDenied = error.message.includes("WRITE_DENY")
                    }
                    try {
                      await hooks.tool.biexce_run_command.execute(
                        { command: "node --version" },
                        {
                          agent: request.body.agent,
                          sessionID: request.path.id,
                          directory: process.env.PROJECT,
                        },
                      )
                    } catch (error) {
                      commandDenied = error.message.includes("artifact/read-only role")
                    }
                    fs.writeFileSync(
                      `${process.env.PROJECT}/.biexce/CODEBASE_BRIEF.md`,
                      "# Codebase Brief\\n\\nGreen-field fixture.\\n",
                    )
                    const workflow = JSON.parse(fs.readFileSync(
                      `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                      "utf8",
                    ))
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: workflow.phase,
                        task_id: workflow.current_task_id,
                        agent: request.body.agent,
                        status: "SUCCEEDED",
                        summary: "codebase brief ready",
                        changed_files: [".biexce/CODEBASE_BRIEF.md"],
                        checks: [],
                        artifacts: [".biexce/CODEBASE_BRIEF.md"],
                      }) },
                      { agent: request.body.agent, sessionID: request.path.id, directory: process.env.PROJECT },
                    )
                    return { data: { parts: [{ type: "text", text: "brief ready" }] } }
                  },
                  },
                }
                hooks = await BiexceControlPlugin({ client })
                permissionHooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-code", agent: {} })
                const result = await hooks.tool.biexce_delegate.execute(
                  { agent: "bx-explore", description: "visible explore", prompt: "fixture" },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    metadata: (value) => metadata.push(value),
                  },
                )
                const shell = { env: {} }
                await hooks["shell.env"](
                  { cwd: process.env.PROJECT, sessionID: "visible-child" },
                  shell,
                )
                console.log(JSON.stringify({
                  processDenied,
                      commandDenied,
                      allowedWritePermission,
                      deniedWritePermission,
                      outsideWriteDenied,
                  metadata: result.metadata,
                  titles: metadata.map((item) => item.title),
                }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
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
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["processDenied"])
            self.assertTrue(payload["commandDenied"])
            self.assertEqual(payload["allowedWritePermission"], "once")
            self.assertIsNone(payload["deniedWritePermission"])
            self.assertTrue(payload["outsideWriteDenied"])
            self.assertEqual(payload["metadata"]["sessionId"], "visible-child")
            self.assertEqual(payload["metadata"]["agent"], "bx-explore")
            self.assertTrue(any("RUNNING" in title for title in payload["titles"]))
            self.assertTrue(any("DONE" in title for title in payload["titles"]))

    def test_plan_reporting_drift_is_normalized_without_duplicate_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            # Mirror the real OpenChamber failure: the Director produced a
            # complete human brief but omitted the machine-owned Project ID.
            (project / ".biexce" / "PROJECT_BRIEF.md").write_text(
                "# PROJECT_BRIEF — live-shaped fixture\n\n"
                "## Goal\nBuild the calculator acceptance package.\n",
                encoding="utf-8",
            )
            (project / ".biexce" / "MASTER_PLAN.md").write_text(
                "# MASTER_PLAN — live-shaped fixture\n\n"
                "WIP limit: 1\nFix cap: 3\n"
                "Reports path: .biexce/reports\nGit/deploy: forbidden\n\n"
                "## Task DAG\n\n"
                "| ID | Goal |\n| --- | --- |\n"
                "| t-001 | addition and subtraction |\n"
                "| t-002 | multiplication and division |\n"
                "| t-003 | regression coverage |\n\n"
                "## Integration\nRun the complete unittest suite.\n",
                encoding="utf-8",
            )
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks
                let created = 0
                let aliasDenied = false
                let commandDenied = false
                let prematurePermission = null
                let multiPathPermission = null
                let multiPathAsk = null
                const permissionReplies = []
                const client = {
                  postSessionIdPermissionsPermissionId: async (request) => {
                    permissionReplies.push(request.body.response)
                    return { data: true }
                  },
                  session: {
                  create: async () => ({ data: { id: `child-${++created}` } }),
                  prompt: async (request) => {
                    const workflow = JSON.parse(fs.readFileSync(
                      `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                      "utf8",
                    ))
                    let changedFiles = []
                    let artifacts = [".biexce/CODEBASE_BRIEF.md"]
                    if (request.body.agent === "bx-plan") {
                      const planPaths = [
                        `${process.env.PROJECT}/.biexce/MASTER_PLAN.md`,
                        `${process.env.PROJECT}/.biexce/tasks/t-001.md`,
                      ]
                      // OpenCode can emit an ambiguous legacy update before
                      // the precise multi-file permission request. It must not
                      // be rejected before the exact paths arrive.
                      await hooks.event({ event: {
                        type: "permission.updated",
                        properties: {
                          id: "plan-legacy-edit",
                          type: "edit",
                          sessionID: request.path.id,
                          pattern: "*",
                          metadata: {},
                        },
                      } })
                      prematurePermission = permissionReplies.at(-1) || null
                      await hooks.event({ event: {
                        type: "permission.asked",
                        properties: {
                          id: "plan-multi-path-edit",
                          permission: "edit",
                          sessionID: request.path.id,
                          patterns: planPaths,
                          metadata: {},
                        },
                      } })
                      multiPathPermission = permissionReplies.at(-1)
                      const permissionOutput = { status: "ask" }
                      await hooks["permission.ask"](
                        {
                          type: "edit",
                          sessionID: request.path.id,
                          pattern: planPaths,
                        },
                        permissionOutput,
                      )
                      multiPathAsk = permissionOutput.status
                      try {
                        await hooks["tool.execute.before"](
                          {
                            tool: "write_file",
                            sessionID: request.path.id,
                            callID: "plan-brief-write",
                          },
                          {
                            args: {
                              path: `${process.env.PROJECT}/.biexce/PROJECT_BRIEF.md`,
                              content: "forbidden",
                            },
                          },
                        )
                      } catch (error) {
                        aliasDenied = error.message.includes("WRITE_DENY")
                      }
                      try {
                        await hooks.tool.biexce_run_command.execute(
                          { command: "node --version" },
                          {
                            agent: request.body.agent,
                            sessionID: request.path.id,
                            directory: process.env.PROJECT,
                          },
                        )
                      } catch (error) {
                        commandDenied = error.message.includes("artifact/read-only role")
                      }
                      fs.appendFileSync(
                        `${process.env.PROJECT}/.biexce/MASTER_PLAN.md`,
                        "\\n<!-- plan refreshed -->\\n",
                      )
                      fs.appendFileSync(
                        `${process.env.PROJECT}/.biexce/tasks/t-001.md`,
                        "\\n<!-- task refreshed -->\\n",
                      )
                      // Deliberately omit the task file. The runtime must use
                      // its in-scope filesystem diff instead of re-running Plan.
                      changedFiles = [".biexce/MASTER_PLAN.md"]
                      artifacts = [
                        ".biexce/MASTER_PLAN.md",
                        ".biexce/tasks/t-001.md",
                      ]
                    }
                    if (request.body.agent !== "bx-plan") {
                      await hooks.tool.biexce_submit_result.execute(
                        { result_json: JSON.stringify({
                          $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                          schema_version: 1,
                          workflow_revision: workflow.revision,
                          phase: workflow.phase,
                          task_id: workflow.current_task_id,
                          agent: request.body.agent,
                          status: "SUCCEEDED",
                          summary: "fixture result",
                          changed_files: changedFiles,
                          checks: [],
                          artifacts,
                        }) },
                        {
                          agent: request.body.agent,
                          sessionID: request.path.id,
                          directory: process.env.PROJECT,
                        },
                      )
                    }
                    return { data: { parts: [{
                      type: "text",
                      text: "Plan artifacts complete.\\nBIEXCE_STATUS: SUCCEEDED",
                    }] } }
                  },
                  },
                }
                hooks = await BiexceControlPlugin({ client })
                const runtimeConfig = { default_agent: "bx-code", agent: {} }
                await hooks.config(runtimeConfig)
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                }
                await hooks.tool.biexce_delegate.execute(
                  { agent: "bx-explore", description: "explore", prompt: "fixture" },
                  context,
                )
                const planned = await hooks.tool.biexce_delegate.execute(
                  { agent: "bx-plan", description: "plan", prompt: "fixture" },
                  context,
                )
                const workflow = JSON.parse(fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                  "utf8",
                ))
                const brief = fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/PROJECT_BRIEF.md`, "utf8",
                )
                const plan = fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/MASTER_PLAN.md`, "utf8",
                )
                console.log(JSON.stringify({
                  created,
                  aliasDenied,
                  commandDenied,
                  prematurePermission,
                  multiPathPermission,
                  multiPathAsk,
                  planCommandPermission:
                    runtimeConfig.agent["bx-plan"].permission.biexce_run_command,
                  workflowPhase: workflow.phase,
                  normalized: planned.metadata.result.changed_files,
                  resultSource: planned.metadata.result_source,
                  attemptCount: planned.metadata.attempt_count,
                  projectID: brief.match(/^Project ID:\\s*(.+)$/mi)?.[1] || null,
                  reportsReady: fs.existsSync(
                    `${process.env.PROJECT}/.biexce/reports`,
                  ),
                  humanGatesReady:
                    /Gate 1/i.test(plan) && /Gate 2/i.test(plan),
                }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
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
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["created"], 2)
            self.assertTrue(payload["aliasDenied"])
            self.assertTrue(payload["commandDenied"])
            self.assertIsNone(payload["prematurePermission"])
            self.assertEqual(payload["multiPathPermission"], "once")
            self.assertEqual(payload["multiPathAsk"], "allow")
            self.assertEqual(payload["planCommandPermission"], "deny")
            self.assertEqual(payload["workflowPhase"], "PLAN_REVIEW")
            self.assertEqual(payload["resultSource"], "runtime-evidence")
            self.assertEqual(
                payload["normalized"],
                [".biexce/MASTER_PLAN.md", ".biexce/tasks/t-001.md"],
            )
            self.assertEqual(payload["attemptCount"], 1)
            self.assertEqual(payload["projectID"], "project")
            self.assertTrue(payload["reportsReady"])
            self.assertTrue(payload["humanGatesReady"])
            validation = validate_project(
                project, config_home=config, opencode_root=GLOBAL_ROOT
            )
            checks = {check.name: check for check in validation.checks}
            for name in (
                "project_brief",
                "master_plan",
                "task_contracts",
                "reports_path",
                "project_state",
            ):
                self.assertTrue(checks[name].ok, checks[name].message)

    def test_runtime_finalizes_review_code_and_test_without_manual_submit(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            planning = self.run_steps(
                project,
                config,
                plugin,
                [
                    ("bx-explore", "Codebase brief ready."),
                    ("bx-plan", "Plan and task contracts ready."),
                ],
            )
            self.assertEqual(planning["workflow"]["phase"], "PLAN_REVIEW")
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks = null
                let child = 0
                const client = { session: {
                  create: async () => ({ data: { id: `auto-child-${++child}` } }),
                  prompt: async (request) => {
                    if (request.body.agent === "bx-test") {
                      await hooks.tool.biexce_run_command.execute(
                        { command: "node --version" },
                        {
                          agent: request.body.agent,
                          sessionID: request.path.id,
                          directory: process.env.PROJECT,
                        },
                      )
                      return { data: { parts: [{
                        type: "text", text: "Checks passed.\\nBIEXCE_STATUS: PASS",
                      }] } }
                    }
                    if (request.body.agent === "bx-code") {
                      fs.mkdirSync(`${process.env.PROJECT}/src/__pycache__`, {
                        recursive: true,
                      })
                      fs.writeFileSync(
                        `${process.env.PROJECT}/src/calculator.py`,
                        "def add(a, b):\\n    return a + b\\n",
                      )
                      fs.writeFileSync(
                        `${process.env.PROJECT}/src/__pycache__/` +
                          `calculator.cpython-313.pyc`,
                        Buffer.from([0x42, 0x58]),
                      )
                    }
                    const status = request.body.agent === "bx-review"
                      ? "PLAN_OK"
                      : "SUCCEEDED"
                    return { data: { parts: [{
                      type: "text", text: `BIEXCE_STATUS: ${status}`,
                    }] } }
                  },
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-code", agent: {} })
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                }
                const review = await hooks.tool.biexce_delegate.execute(
                  { agent: "bx-review", description: "review", prompt: "review" },
                  context,
                )
                await hooks.tool.biexce_gate.execute(
                  { gate: "1", summary: "approve fixture plan" },
                  { ...context, ask: async () => {} },
                )
                const code = await hooks.tool.biexce_delegate.execute(
                  { agent: "bx-code", description: "code", prompt: "code" },
                  context,
                )
                const test = await hooks.tool.biexce_delegate.execute(
                  { agent: "bx-test", description: "test", prompt: "test" },
                  context,
                )
                const workflow = JSON.parse(fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                  "utf8",
                ))
                console.log(JSON.stringify({
                  sources: [
                    review.metadata.result_source,
                    code.metadata.result_source,
                    test.metadata.result_source,
                  ],
                  testStatus: test.metadata.result.status,
                  codeChanged: code.metadata.result.changed_files,
                  checks: test.metadata.result.checks,
                  phase: workflow.phase,
                }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
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
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["sources"], ["runtime-evidence"] * 3)
            self.assertEqual(payload["testStatus"], "PASS")
            self.assertEqual(payload["codeChanged"], ["src/calculator.py"])
            self.assertEqual(payload["checks"][0]["status"], "PASS")
            self.assertEqual(payload["phase"], "TASK_REVIEW")

    def test_out_of_scope_plan_diff_blocks_once_and_cannot_redelegate(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let hooks
                let created = 0
                const client = { session: {
                  create: async () => ({ data: { id: `child-${++created}` } }),
                  prompt: async (request) => {
                    const workflow = JSON.parse(fs.readFileSync(
                      `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                      "utf8",
                    ))
                    let changedFiles = []
                    let artifacts = [".biexce/CODEBASE_BRIEF.md"]
                    if (request.body.agent === "bx-plan") {
                      fs.appendFileSync(
                        `${process.env.PROJECT}/.biexce/PROJECT_BRIEF.md`,
                        "\\nunauthorized plan edit\\n",
                      )
                      fs.appendFileSync(
                        `${process.env.PROJECT}/.biexce/MASTER_PLAN.md`,
                        "\\n<!-- plan refreshed -->\\n",
                      )
                      changedFiles = [".biexce/MASTER_PLAN.md"]
                      artifacts = [".biexce/MASTER_PLAN.md"]
                    }
                    await hooks.tool.biexce_submit_result.execute(
                      { result_json: JSON.stringify({
                        $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                        schema_version: 1,
                        workflow_revision: workflow.revision,
                        phase: workflow.phase,
                        task_id: workflow.current_task_id,
                        agent: request.body.agent,
                        status: "SUCCEEDED",
                        summary: "fixture result",
                        changed_files: changedFiles,
                        checks: [],
                        artifacts,
                      }) },
                      {
                        agent: request.body.agent,
                        sessionID: request.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "done" }] } }
                  },
                }}
                hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-code", agent: {} })
                const context = {
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                }
                await hooks.tool.biexce_delegate.execute(
                  { agent: "bx-explore", description: "explore", prompt: "fixture" },
                  context,
                )
                const workflowPath =
                  `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`
                const planWorkflow = JSON.parse(fs.readFileSync(
                  workflowPath, "utf8",
                ))
                let firstError = ""
                try {
                  await hooks.tool.biexce_delegate.execute(
                    { agent: "bx-plan", description: "plan", prompt: "fixture" },
                    context,
                  )
                } catch (error) {
                  firstError = error.message
                }
                const blockedWorkflow = JSON.parse(fs.readFileSync(
                  workflowPath, "utf8",
                ))
                // Simulate a stale parent replaying the pre-failure workflow.
                // The terminal job record must still prevent another child.
                fs.writeFileSync(
                  workflowPath,
                  JSON.stringify(planWorkflow, null, 2) + "\\n",
                )
                let secondError = ""
                try {
                  await hooks.tool.biexce_delegate.execute(
                    { agent: "bx-plan", description: "plan again", prompt: "fixture" },
                    context,
                  )
                } catch (error) {
                  secondError = error.message
                }
                const stateRoot = `${process.env.PROJECT}/.biexce/state`
                const board = JSON.parse(fs.readFileSync(
                  `${stateRoot}/AUTOPILOT_JOBS.json`, "utf8",
                ))
                const planJob = Object.values(board.jobs).find(
                  (job) => job.agent === "bx-plan",
                )
                const baseline = `${stateRoot}/job-baselines/${planJob.job_id}.json`
                console.log(JSON.stringify({
                  created,
                  firstError,
                  secondError,
                  workflowPhase: blockedWorkflow.phase,
                  blockedReason: blockedWorkflow.blocked_reason,
                  jobStatus: planJob.status,
                  attempt: planJob.attempt,
                  baselineExists: fs.existsSync(baseline),
                }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
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
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["created"], 2)
            self.assertIn("runtime diff exceeds writable scope", payload["firstError"])
            self.assertIn("BIEXCE_AUTOPILOT_TERMINAL_JOB", payload["secondError"])
            self.assertEqual(payload["workflowPhase"], "BLOCKED")
            self.assertIn("Terminal CONTRACT failure", payload["blockedReason"])
            self.assertEqual(payload["jobStatus"], "FAILED")
            self.assertEqual(payload["attempt"], 1)
            self.assertFalse(payload["baselineExists"])

    def test_hung_child_times_out_aborts_and_releases_the_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let aborts = 0
                const metadata = []
                const client = { session: {
                  create: async () => ({ data: { id: "hung-child" } }),
                  prompt: async () => await new Promise(() => {}),
                  abort: async () => { aborts += 1; return { data: true } },
                }}
                const hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-code", agent: {} })
                let message = ""
                try {
                  await hooks.tool.biexce_delegate.execute(
                    { agent: "bx-explore", description: "hung explore", prompt: "fixture" },
                    {
                      agent: "bx-director",
                      sessionID: "session-1",
                      directory: process.env.PROJECT,
                      metadata: (value) => metadata.push(value),
                    },
                  )
                } catch (error) {
                  message = error.message
                }
                const leases = `${process.env.PROJECT}/.biexce/state/leases`
                const remaining = fs.existsSync(leases)
                  ? fs.readdirSync(leases).filter((name) => name.endsWith(".json"))
                  : []
                const jobs = JSON.parse(fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/state/AUTOPILOT_JOBS.json`,
                  "utf8",
                ))
                console.log(JSON.stringify({
                  message,
                  aborts,
                  leaseCount: remaining.length,
                  jobStatus: Object.values(jobs.jobs)[0].status,
                  titles: metadata.map((item) => item.title),
                }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
            environment["BIEXCE_AGENT_TIMEOUT_MS"] = "1000"
            environment["BIEXCE_CONTROL_POLL_MS"] = "100"
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
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("timed out", payload["message"])
            self.assertEqual(payload["aborts"], 1)
            self.assertEqual(payload["leaseCount"], 0)
            self.assertEqual(payload["jobStatus"], "TIMED_OUT")
            self.assertTrue(any("RUNNING" in title for title in payload["titles"]))
            self.assertTrue(
                any("TIMED_OUT" in title for title in payload["titles"])
            )

    def test_autopilot_off_aborts_child_marks_cancelled_and_releases_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let aborts = 0
                let signalStarted
                const started = new Promise((resolve) => { signalStarted = resolve })
                const client = { session: {
                  create: async () => ({ data: { id: "cancelled-child" } }),
                  prompt: async () => {
                    signalStarted()
                    return await new Promise(() => {})
                  },
                  abort: async () => { aborts += 1; return { data: true } },
                }}
                const hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-code", agent: {} })
                const delegated = hooks.tool.biexce_delegate.execute(
                  { agent: "bx-explore", description: "cancel explore", prompt: "fixture" },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                  },
                )
                await started
                const controlPath =
                  process.env.PROJECT + "/.biexce/state/AUTOPILOT_CONTROL.json"
                const control = JSON.parse(fs.readFileSync(controlPath, "utf8"))
                control.mode = "OFF"
                control.revision += 1
                control.reason = "test requested stop"
                control.updated_at_utc = new Date().toISOString()
                control.updated_by = "test"
                fs.writeFileSync(controlPath, JSON.stringify(control, null, 2) + "\\n")
                let message = ""
                try {
                  await delegated
                } catch (error) {
                  message = error.message
                }
                const stateRoot = process.env.PROJECT + "/.biexce/state"
                const jobs = JSON.parse(fs.readFileSync(
                  stateRoot + "/AUTOPILOT_JOBS.json", "utf8"
                ))
                const projectState = JSON.parse(fs.readFileSync(
                  stateRoot + "/PROJECT_STATE.json", "utf8"
                ))
                const leaseRoot = stateRoot + "/leases"
                const leases = fs.existsSync(leaseRoot)
                  ? fs.readdirSync(leaseRoot).filter((name) => name.endsWith(".json"))
                  : []
                console.log(JSON.stringify({
                  message,
                  aborts,
                  jobStatus: Object.values(jobs.jobs)[0].status,
                  leaseCount: leases.length,
                  firstTask: projectState.tasks[0],
                }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
            environment["BIEXCE_AGENT_TIMEOUT_MS"] = "10000"
            environment["BIEXCE_CONTROL_POLL_MS"] = "100"
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
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("control stopped", payload["message"])
            self.assertEqual(payload["aborts"], 1)
            self.assertEqual(payload["jobStatus"], "CANCELLED")
            self.assertEqual(payload["leaseCount"], 0)
            self.assertEqual(payload["firstTask"]["status"], "backlog")
            self.assertIsNone(payload["firstTask"]["agent"])

    def test_director_cannot_write_runtime_state_after_parent_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            script = textwrap.dedent(
                """
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const permissionReplies = []
                const client = {
                  postSessionIdPermissionsPermissionId: async (request) => {
                    permissionReplies.push(request.body.response)
                    return { data: true }
                  },
                }
                const hooks = await BiexceControlPlugin({ client })
                await hooks.config({ default_agent: "bx-code", agent: {} })
                await hooks["chat.message"]({
                  agent: "bx-director",
                  sessionID: "session-1",
                  directory: process.env.PROJECT,
                  model: { providerID: "cloud-provider", modelID: "strong-model" },
                })
                const statePath =
                  process.env.PROJECT + "/.biexce/state/PROJECT_STATE.json"
                const briefPath =
                  process.env.PROJECT + "/.biexce/PROJECT_BRIEF.md"
                let denied = ""
                try {
                  await hooks["tool.execute.before"](
                    { tool: "write", sessionID: "session-1", callID: "director-state" },
                    { args: { filePath: statePath, content: "{}" } },
                  )
                } catch (error) {
                  denied = error.message
                }
                let briefAllowed = true
                try {
                  await hooks["tool.execute.before"](
                    { tool: "write", sessionID: "session-1", callID: "director-brief" },
                    { args: { filePath: briefPath, content: "# Brief" } },
                  )
                } catch {
                  briefAllowed = false
                }
                const statePermission = { status: "ask" }
                await hooks["permission.ask"]({
                  type: "edit",
                  sessionID: "session-1",
                  metadata: { filepath: statePath },
                }, statePermission)
                const briefPermission = { status: "ask" }
                await hooks["permission.ask"]({
                  type: "edit",
                  sessionID: "session-1",
                  metadata: { filepath: briefPath },
                }, briefPermission)
                await hooks.event({ event: {
                  type: "permission.asked",
                  properties: {
                    id: "director-state-permission",
                    permission: "edit",
                    sessionID: "session-1",
                    metadata: { filepath: statePath },
                  },
                } })
                await hooks.event({ event: {
                  type: "permission.asked",
                  properties: {
                    id: "director-brief-permission",
                    permission: "edit",
                    sessionID: "session-1",
                    metadata: { filepath: briefPath },
                  },
                } })
                console.log(JSON.stringify({
                  denied,
                  briefAllowed,
                  statePermission: statePermission.status,
                  briefPermission: briefPermission.status,
                  permissionReplies,
                }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
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
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("BIEXCE_DIRECTOR_WRITE_DENY", payload["denied"])
            self.assertTrue(payload["briefAllowed"])
            self.assertEqual(payload["statePermission"], "deny")
            self.assertEqual(payload["briefPermission"], "allow")
            self.assertEqual(payload["permissionReplies"], ["once"])

    def test_human_gate_is_confirmed_inside_opencode_and_completes(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            self.set_waiting_gate_two(project)
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const hooks = await BiexceControlPlugin({ client: {} })
                const config = { default_agent: "bx-code", agent: {} }
                await hooks.config(config)
                const permission = { status: "allow" }
                await hooks["permission.ask"](
                  { type: "biexce_gate_approval" }, permission,
                )
                let request = null
                const result = await hooks.tool.biexce_gate.execute(
                  { gate: "2", summary: "All tasks and reports are ready." },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                    ask: async (input) => { request = input },
                  },
                )
                const workflow = JSON.parse(fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                  "utf8",
                ))
                const control = JSON.parse(fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/state/AUTOPILOT_CONTROL.json`,
                  "utf8",
                ))
                console.log(JSON.stringify({
                  permission,
                  directorPermission: config.agent["bx-director"].permission,
                  request,
                  metadata: result.metadata,
                  workflow,
                  control,
                }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
            environment["BIEXCE_CLI_ENTRYPOINT"] = str(
                REPOSITORY_ROOT / "scripts" / "biexce.py"
            )
            environment["BIEXCE_OPENCODE_CONFIG_DIR"] = str(GLOBAL_ROOT)
            environment["BIEXCE_PYTHON"] = sys.executable
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
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["permission"]["status"], "ask")
            self.assertEqual(
                payload["directorPermission"]["biexce_gate_approval"], "ask"
            )
            self.assertEqual(payload["request"]["always"], [])
            self.assertEqual(payload["request"]["permission"], "biexce_gate_approval")
            self.assertEqual(payload["metadata"]["next_phase"], "COMPLETE")
            self.assertEqual(payload["workflow"]["phase"], "COMPLETE")
            self.assertEqual(payload["control"]["mode"], "OFF")

    def test_rejected_opencode_gate_does_not_change_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            self.set_waiting_gate_two(project)
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                const hooks = await BiexceControlPlugin({ client: {} })
                await hooks.config({ default_agent: "bx-code", agent: {} })
                let rejected = false
                try {
                  await hooks.tool.biexce_gate.execute(
                    { gate: "2", summary: "Ready for final acceptance." },
                    {
                      agent: "bx-director",
                      sessionID: "session-1",
                      directory: process.env.PROJECT,
                      ask: async () => { throw new Error("user rejected") },
                    },
                  )
                } catch (error) {
                  rejected = error.message.includes("user rejected")
                }
                const workflow = JSON.parse(fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                  "utf8",
                ))
                const control = JSON.parse(fs.readFileSync(
                  `${process.env.PROJECT}/.biexce/state/AUTOPILOT_CONTROL.json`,
                  "utf8",
                ))
                console.log(JSON.stringify({ rejected, workflow, control }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
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
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["rejected"])
            self.assertEqual(payload["workflow"]["phase"], "WAITING_GATE_2")
            self.assertEqual(payload["control"]["mode"], "RUNNING")
    def run_runtime_resilience_scenario(
        self,
        project: Path,
        config: Path,
        runtime_plugin: Path,
        scenario: str,
    ) -> dict[str, object]:
        script = textwrap.dedent(
            """
            import fs from "node:fs"
            const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
            const scenario = process.env.SCENARIO
            const calls = []
            let createCount = 0

            const submitSuccess = async (hooks, request) => {
              const workflow = JSON.parse(fs.readFileSync(
                `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
                "utf8",
              ))
              const result = {
                $schema: "https://schemas.biexce.local/runtime/agent-result-v1.schema.json",
                schema_version: 1,
                workflow_revision: workflow.revision,
                phase: workflow.phase,
                task_id: workflow.current_task_id,
                agent: request.body.agent,
                status: "SUCCEEDED",
                summary: "runtime resilience success",
                changed_files: [],
                checks: [],
                artifacts: [".biexce/CODEBASE_BRIEF.md"],
              }
              await hooks.tool.biexce_submit_result.execute(
                { result_json: JSON.stringify(result) },
                {
                  agent: request.body.agent,
                  sessionID: request.path.id,
                  directory: process.env.PROJECT,
                },
              )
              return { data: { parts: [{ type: "text", text: "PASS" }] } }
            }

            let hooks = null
            const client = { session: {
              create: async () => {
                createCount += 1
                return { data: { id: "child-stable" } }
              },
              get: async () => ({ data: { id: "child-stable" } }),
              prompt: async (request) => {
                const model =
                  `${request.body.model.providerID}/${request.body.model.modelID}`
                calls.push(model)
                if (scenario === "retry" && calls.length === 1) {
                  throw Object.assign(new Error("connection reset"), {
                    code: "ECONNRESET",
                  })
                }
                if (scenario === "fallback" && calls.length === 1) {
                  throw new Error("model not found")
                }
                return submitSuccess(hooks, request)
              },
            }}
            hooks = await BiexceControlPlugin({ client })
            await hooks.config({ default_agent: "bx-code", agent: {} })

            let firstError = null
            if (scenario === "resume") {
              client.session.prompt = async (request) => {
                const model =
                  `${request.body.model.providerID}/${request.body.model.modelID}`
                calls.push(model)
                throw Object.assign(new Error("connection reset"), {
                  code: "ECONNRESET",
                })
              }
              try {
                await hooks.tool.biexce_delegate.execute(
                  { agent: "bx-explore", description: "explore", prompt: "fixture" },
                  {
                    agent: "bx-director",
                    sessionID: "session-1",
                    directory: process.env.PROJECT,
                  },
                )
              } catch (error) {
                firstError = error.message
              }
              let resumedHooks = null
              const resumedClient = { session: {
                create: async () => {
                  throw new Error("resume unexpectedly created a new session")
                },
                get: async () => ({ data: { id: "child-stable" } }),
                prompt: async (request) => {
                  const model =
                    `${request.body.model.providerID}/${request.body.model.modelID}`
                  calls.push(model)
                  return submitSuccess(resumedHooks, request)
                },
              }}
              resumedHooks = await BiexceControlPlugin({ client: resumedClient })
              await resumedHooks.config({ default_agent: "bx-code", agent: {} })
              hooks = resumedHooks
            }

            const result = await hooks.tool.biexce_delegate.execute(
              { agent: "bx-explore", description: "explore", prompt: "fixture" },
              {
                agent: "bx-director",
                sessionID: "session-1",
                directory: process.env.PROJECT,
              },
            )
            const workflow = JSON.parse(fs.readFileSync(
              `${process.env.PROJECT}/.biexce/state/AUTOPILOT_WORKFLOW.json`,
              "utf8",
            ))
            const board = JSON.parse(fs.readFileSync(
              `${process.env.PROJECT}/.biexce/state/AUTOPILOT_JOBS.json`,
              "utf8",
            ))
            const registry = JSON.parse(fs.readFileSync(
              `${process.env.PROJECT}/.biexce/state/AUTOPILOT_SESSIONS.json`,
              "utf8",
            ))
            const job = Object.values(board.jobs)[0]
            const session = Object.values(registry.sessions)[0]
            console.log(JSON.stringify({
              calls,
              createCount,
              firstError,
              metadata: result.metadata,
              workflow,
              job,
              session,
            }))
            """
        )
        environment = os.environ.copy()
        environment["BIEXCE_CONFIG_HOME"] = str(config)
        environment["BIEXCE_RETRY_BACKOFF_MS"] = "0"
        environment["BIEXCE_TRANSPORT_RETRIES"] = (
            "0" if scenario == "resume" else "1"
        )
        environment["PROJECT"] = str(project)
        environment["PLUGIN_URL"] = runtime_plugin.resolve().as_uri()
        environment["SCENARIO"] = scenario
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

    def test_transport_retry_does_not_increment_fix_round(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            result = self.run_runtime_resilience_scenario(
                project, config, plugin, "retry"
            )
            self.assertEqual(result["workflow"]["phase"], "PLAN")
            self.assertEqual(result["workflow"]["fix_round"], 0)
            self.assertEqual(result["job"]["attempt"], 2)
            self.assertEqual(result["job"]["status"], "COMPLETED")
            self.assertEqual(result["createCount"], 1)
            self.assertEqual(len(result["calls"]), 2)

    def test_primary_runtime_failure_invokes_configured_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            fallback = "cloud-provider/backup-model"
            set_fallback(
                "bx-explore",
                fallback,
                actor="tester",
                confirm_cross_zone=False,
                config_home=config,
            )
            apply_routing(
                actor="tester",
                config_home=config,
                available_models={LOCAL_MODEL, CLOUD_MODEL, fallback},
            )
            result = self.run_runtime_resilience_scenario(
                project, config, plugin, "fallback"
            )
            self.assertEqual(result["calls"], [CLOUD_MODEL, fallback])
            self.assertEqual(result["metadata"]["actual_model"], fallback)
            self.assertTrue(result["metadata"]["fallback_used"])
            self.assertEqual(result["job"]["model"], fallback)

    def test_runtime_instance_restart_resumes_persisted_child_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config, plugin = self.prepare(Path(temporary))
            result = self.run_runtime_resilience_scenario(
                project, config, plugin, "resume"
            )
            self.assertIn("[TRANSPORT]", result["firstError"])
            self.assertEqual(result["createCount"], 1)
            self.assertTrue(result["metadata"]["session_resumed"])
            self.assertEqual(result["metadata"]["child_session_id"], "child-stable")
            self.assertEqual(result["session"]["status"], "COMPLETED")
            self.assertEqual(result["session"]["attempt"], 3)
            self.assertEqual(
                result["calls"],
                [CLOUD_MODEL, LOCAL_MODEL, LOCAL_MODEL],
            )
            self.assertEqual(result["workflow"]["phase"], "PLAN")
            self.assertEqual(result["workflow"]["fix_round"], 0)


if __name__ == "__main__":
    unittest.main()
