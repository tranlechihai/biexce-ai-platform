import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from biexce_control import (  # noqa: E402
    ArmValidationRequiredError,
    InvalidTransitionError,
    StateValidationError,
    apply_action,
    load_state,
    state_path_for,
)
from biexce_control.autopilot import SCHEMA_ID  # noqa: E402
from biexce_control.cli import main as cli_main  # noqa: E402
from biexce_control.fixture import init_fixture  # noqa: E402
from biexce_control.workflow import (  # noqa: E402
    initialize_workflow,
    load_workflow,
    workflow_path_for,
)


class AutopilotControlTests(unittest.TestCase):
    def test_missing_state_is_off_without_creating_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            state = load_state(project)
            self.assertEqual(state.mode, "OFF")
            self.assertEqual(state.revision, 0)
            self.assertFalse(state.persisted)
            self.assertFalse((project / ".biexce").exists())

    def test_on_and_off_persist_auditable_state_atomically(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            on_state, changed = apply_action(
                project,
                "on",
                actor="test-user",
                reason="prepare fixture",
            )
            self.assertTrue(changed)
            self.assertEqual(on_state.mode, "ON_IDLE")
            self.assertEqual(on_state.revision, 1)

            state_path = state_path_for(project)
            document = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(document["$schema"], SCHEMA_ID)
            self.assertEqual(document["updated_by"], "test-user")
            self.assertEqual(document["reason"], "prepare fixture")
            self.assertEqual(list(state_path.parent.glob("*.tmp")), [])

            off_state, changed = apply_action(
                project,
                "off",
                actor="test-user",
                reason="stop fixture",
            )
            self.assertTrue(changed)
            self.assertEqual(off_state.mode, "OFF")
            self.assertEqual(off_state.revision, 2)

    def test_transitions_are_strict_and_start_resumes_paused(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            with self.assertRaises(InvalidTransitionError):
                apply_action(project, "start", actor="user", reason="invalid")

            apply_action(project, "on", actor="user", reason="enable")
            armed, _ = apply_action(
                project,
                "arm",
                actor="user",
                reason="validated",
                arm_validator=lambda _project, _state: None,
            )
            self.assertEqual(armed.mode, "ARMED")
            running, _ = apply_action(
                project, "start", actor="user", reason="start"
            )
            self.assertEqual(running.mode, "RUNNING")
            paused, _ = apply_action(
                project, "pause", actor="user", reason="pause"
            )
            self.assertEqual(paused.mode, "PAUSED")
            resumed, _ = apply_action(
                project, "start", actor="user", reason="resume"
            )
            self.assertEqual(resumed.mode, "RUNNING")

    def test_arm_is_blocked_without_gate_zero_validator(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            apply_action(project, "on", actor="user", reason="enable")
            with self.assertRaises(ArmValidationRequiredError):
                apply_action(project, "arm", actor="user", reason="try arm")
            self.assertEqual(load_state(project).mode, "ON_IDLE")

    def test_corrupt_state_fails_closed_and_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            state_path = project / ".biexce" / "state" / "AUTOPILOT_CONTROL.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text("{not-json}\n", encoding="utf-8")
            original = state_path.read_bytes()

            with self.assertRaises(StateValidationError):
                load_state(project)
            with self.assertRaises(StateValidationError):
                apply_action(project, "off", actor="user", reason="recover")
            self.assertEqual(state_path.read_bytes(), original)

    def test_cli_arm_checks_runtime_then_full_validation_blocks_missing_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli_main(
                    ["autopilot", "status", "--project", temporary, "--json"]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["mode"], "OFF")

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    cli_main(["autopilot", "on", "--project", temporary]),
                    0,
                )
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    ["autopilot", "arm", "--project", temporary]
                )
            self.assertEqual(exit_code, 0)
            self.assertEqual(load_state(temporary).mode, "ARMED")

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    ["autopilot", "validate", "--project", temporary]
                )
            self.assertEqual(exit_code, 2)

    def test_schema_contract_matches_runtime_constants(self):
        schema_path = (
            SOURCE_ROOT
            / "biexce_control"
            / "schemas"
            / "autopilot-state-v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], SCHEMA_ID)
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(
            set(schema["properties"]["mode"]["enum"]),
            {"OFF", "ON_IDLE", "ARMED", "RUNNING", "PAUSED"},
        )

    def test_cli_status_reports_workflow_profile_and_driver(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            init_fixture(project)
            apply_action(project, "on", actor="user", reason="enable")
            policy_path = (
                project / ".biexce" / "state" / "AUTOPILOT_POLICY.json"
            )
            policy_path.write_text(
                json.dumps(
                    {
                        "$schema": "https://schemas.biexce.local/runtime/workflow-policy-v1.schema.json",
                        "schema_version": 1,
                        "project_root": str(project.resolve()),
                        "requested_profile": "standard",
                        "effective_profile": "standard",
                        "source": "explicit",
                        "risk_flags": [],
                        "policy": {
                            "execute_source": True,
                            "max_batch": 3,
                            "require_gate_1": True,
                            "require_gate_2": True,
                            "stop_on_task_blocker": False,
                        },
                        "driver_status": "RUNNING",
                        "last_terminal_reason": None,
                        "updated_at_utc": "2026-08-06T00:00:00Z",
                        "updated_by": "test",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli_main(
                    ["autopilot", "status", "--project", str(project), "--json"]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(
                payload["workflow_policy"]["effective_profile"], "standard"
            )
            self.assertEqual(payload["workflow_policy"]["driver_status"], "RUNNING")

    def test_cli_resolve_queues_runtime_command_without_changing_workflow(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            init_fixture(project)
            apply_action(project, "on", actor="user", reason="enable")
            apply_action(
                project,
                "arm",
                actor="user",
                reason="validated",
                arm_validator=lambda _project, _state: None,
            )
            apply_action(project, "start", actor="user", reason="run")
            initialize_workflow(project, actor="user")

            workflow_path = workflow_path_for(project)
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            workflow.update(
                phase="BLOCKED",
                revision=8,
                current_task_id="t-001",
                fix_round=3,
                gate_1="APPROVED",
                gate_1_approved_by="human",
                gate_1_approved_at_utc="2026-08-04T00:00:00Z",
                blocked_reason="Fix cap reached for t-001",
            )
            workflow_path.write_text(
                json.dumps(workflow, indent=2) + "\n", encoding="utf-8"
            )
            project_state_path = (
                project / ".biexce" / "state" / "PROJECT_STATE.json"
            )
            project_state = json.loads(
                project_state_path.read_text(encoding="utf-8")
            )
            project_state["tasks"][0].update(
                status="escalated", round=3, agent=None
            )
            project_state_path.write_text(
                json.dumps(project_state, indent=2) + "\n", encoding="utf-8"
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "autopilot",
                        "resolve",
                        "--project",
                        str(project),
                        "--action",
                        "manual-fix",
                        "--reason",
                        "Human approved one targeted authentication fix.",
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["recovery"]["command"], "RECOVER_MANUAL_FIX")
            self.assertEqual(payload["workflow"]["phase"], "BLOCKED")
            self.assertEqual(load_workflow(project).phase, "BLOCKED")
            self.assertTrue(
                (project / ".biexce" / "state" / "AUTOPILOT_COMMAND.json").is_file()
            )

    def test_cli_cannot_bypass_human_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            init_fixture(project)
            initialize_workflow(project, actor="user")
            workflow_path = workflow_path_for(project)
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            workflow["phase"] = "WAITING_GATE_1"
            workflow_path.write_text(
                json.dumps(workflow, indent=2) + "\n", encoding="utf-8"
            )
            before = workflow_path.read_bytes()
            error = io.StringIO()

            with contextlib.redirect_stderr(error):
                exit_code = cli_main(
                    [
                        "autopilot",
                        "approve",
                        "--project",
                        str(project),
                        "--gate",
                        "1",
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("only inside OpenCode", error.getvalue())
            self.assertEqual(workflow_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
