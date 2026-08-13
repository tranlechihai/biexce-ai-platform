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
    save_routing,
)


CLOUD_MODEL = "cloud-provider/strong-model"


@unittest.skipUnless(shutil.which("node"), "Node.js is required for plugin tests")
class RuntimeGuardTests(unittest.TestCase):
    def test_plugin_keeps_task_deny_and_guards_custom_delegate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
                    const chain = {
                      min() { return this },
                      max() { return this },
                    }
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
                reason="test",
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
            script = textwrap.dedent(
                """
                import fs from "node:fs"
                const { BiexceControlPlugin } = await import(process.env.PLUGIN_URL)
                let creates = 0
                let hooks = null
                const client = { session: {
                  create: async () => ({ data: { id: "child-1" } }),
                  prompt: async (input) => {
                    creates += 1
                    if (input.body.model.providerID !== "cloud-provider") throw new Error("model")
                    const contract = input.body.parts[0].text
                    if (!contract.includes("`.biexce/CODEBASE_BRIEF.md`")) {
                      throw new Error("missing EXPLORE artifact contract")
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
                        agent: input.body.agent,
                        status: "SUCCEEDED",
                        summary: "Codebase Brief created",
                        changed_files: [".biexce/CODEBASE_BRIEF.md"],
                        checks: [],
                        artifacts: [".biexce/CODEBASE_BRIEF.md"],
                      }) },
                      {
                        agent: input.body.agent,
                        sessionID: input.path.id,
                        directory: process.env.PROJECT,
                      },
                    )
                    return { data: { parts: [{ type: "text", text: "ok" }] } }
                  },
                }}
                hooks = await BiexceControlPlugin({ client })
                const config = { default_agent: "bx-code", agent: {
                  "bx-director": { permission: { task: "deny" } },
                }}
                await hooks.config(config)
                if (config.agent['bx-director'].permission.biexce_delegate !== 'allow') {
                  throw new Error('custom delegate remains denied')
                }
                for (const name of [
                  "biexce_drive",
                  "biexce_run_next",
                  "biexce_start_job",
                  "biexce_job_status",
                  "biexce_cancel_job",
                  "biexce_resume_job",
                ]) {
                  if (config.agent["bx-director"].permission[name] !== "allow") {
                    throw new Error("scheduler tool remains denied: " + name)
                  }
                }
                if (config.agent["bx-director"].permission.task !== "deny") throw new Error("task changed")
                if (config.agent["bx-code"].model !== "cloud-provider/strong-model") {
                  throw new Error("source agent did not receive user-selected cloud model")
                }
                if (config.agent["bx-code"].permission.biexce_run_command !== "allow") {
                  throw new Error("managed command tool is not enabled for child agents")
                }
                await hooks["chat.message"]({
                  agent: "bx-code",
                  model: { providerID: "cloud-provider", modelID: "strong-model" },
                })
                let denied = false
                try {
                  await hooks.tool.biexce_delegate.execute(
                    { agent: "bx-code", description: "x", prompt: "x" },
                    { agent: "bx-code", sessionID: "session-1", directory: process.env.PROJECT },
                  )
                } catch (error) { denied = error.message.includes("only bx-director") }
                if (!denied) throw new Error("child delegate allowed")
                denied = false
                try {
                  await hooks.tool.biexce_delegate.execute(
                    { agent: "bx-code", description: "wrong order", prompt: "x" },
                    { agent: "bx-director", sessionID: "session-1", directory: process.env.PROJECT },
                  )
                } catch (error) { denied = error.message.includes("requires bx-explore") }
                if (!denied) throw new Error("wrong workflow agent allowed")
                const result = await hooks.tool.biexce_delegate.execute(
                  { agent: "bx-explore", description: "x", prompt: "x" },
                  { agent: "bx-director", sessionID: "session-1", directory: process.env.PROJECT },
                )
                if (result.output !== "ok" || creates !== 1) throw new Error("director delegate failed")
                if (result.metadata.next_phase !== "PLAN" || result.metadata.next_agent !== "bx-plan") {
                  throw new Error("workflow did not advance to plan")
                }
                console.log(JSON.stringify({ ok: true }))
                """
            )
            environment = os.environ.copy()
            environment["BIEXCE_CONFIG_HOME"] = str(config)
            environment["PROJECT"] = str(project)
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
            self.assertTrue(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
