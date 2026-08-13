import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from biexce_control.fixture import init_fixture  # noqa: E402
from biexce_control.workflow import (  # noqa: E402
    LEGACY_WORKFLOW_SCHEMA_ID,
    PHASES,
    TRANSITION_AUTHORITY,
    WORKFLOW_SCHEMA_ID,
    WORKFLOW_SCHEMA_VERSION,
    WorkflowStateError,
    approve_gate,
    command_path_for,
    initialize_workflow,
    load_workflow,
    resolve_blocked_workflow,
    workflow_path_for,
)


class AutopilotWorkflowTests(unittest.TestCase):
    def _set_phase(self, project: Path, phase: str) -> None:
        path = workflow_path_for(project)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["phase"] = phase
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def _set_fix_cap_blocked(self, project: Path) -> None:
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
            last_agent="bx-review",
            last_result="CHANGES REQUIRED",
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

    def test_initialize_is_idempotent_and_starts_with_explore(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            state, changed = initialize_workflow(project, actor="tester")
            self.assertTrue(changed)
            self.assertEqual(state.phase, "EXPLORE")
            self.assertEqual(state.expected_agent, "bx-explore")
            again, changed = initialize_workflow(project, actor="tester")
            self.assertFalse(changed)
            self.assertEqual(again.revision, 1)
            self.assertEqual(list(workflow_path_for(project).parent.glob("*.tmp")), [])

    def test_python_gate_api_cannot_bypass_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            init_fixture(project)
            initialize_workflow(project, actor="tester")
            self._set_phase(project, "WAITING_GATE_1")
            before = workflow_path_for(project).read_bytes()
            with self.assertRaisesRegex(WorkflowStateError, "runtime-owned"):
                approve_gate(
                    project,
                    1,
                    actor="human",
                    gate_1_validator=lambda _root: None,
                )
            self.assertEqual(workflow_path_for(project).read_bytes(), before)

    def test_v1_state_migrates_to_v2_without_changing_workflow_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            initialize_workflow(project, actor="tester")
            path = workflow_path_for(project)
            legacy = json.loads(path.read_text(encoding="utf-8"))
            legacy.pop("transition_authority")
            legacy["$schema"] = LEGACY_WORKFLOW_SCHEMA_ID
            legacy["schema_version"] = 1
            legacy["phase"] = "PLAN"
            legacy["revision"] = 4
            path.write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")

            migrated = load_workflow(project, required=True)
            document = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(migrated.phase, "PLAN")
            self.assertEqual(migrated.revision, 4)
            self.assertEqual(document["schema_version"], WORKFLOW_SCHEMA_VERSION)
            self.assertEqual(document["$schema"], WORKFLOW_SCHEMA_ID)
            self.assertEqual(document["transition_authority"], TRANSITION_AUTHORITY)

    def test_schema_contract_matches_runtime_phases(self):
        schema = json.loads(
            (
                SOURCE_ROOT
                / "biexce_control"
                / "schemas"
                / "autopilot-workflow-v2.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(schema["$id"], WORKFLOW_SCHEMA_ID)
        self.assertEqual(set(schema["properties"]["phase"]["enum"]), set(PHASES))

    def test_corrupt_workflow_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            initialize_workflow(project, actor="tester")
            path = workflow_path_for(project)
            path.write_text("{broken}\n", encoding="utf-8")
            with self.assertRaises(WorkflowStateError):
                load_workflow(project, required=True)

    def test_manual_fix_recovery_queues_runtime_command_without_transition(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            init_fixture(project)
            initialize_workflow(project, actor="tester")
            self._set_fix_cap_blocked(project)

            unchanged, command = resolve_blocked_workflow(
                project,
                action="manual-fix",
                actor="human",
                reason="Apply the approved authentication guard.",
            )

            self.assertEqual(unchanged.phase, "BLOCKED")
            self.assertEqual(unchanged.revision, 8)
            project_state = json.loads(
                (
                    project / ".biexce" / "state" / "PROJECT_STATE.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(project_state["tasks"][0]["status"], "escalated")
            self.assertIsNone(project_state["tasks"][0]["agent"])
            self.assertEqual(project_state["tasks"][0]["round"], 3)
            persisted = json.loads(command_path_for(project).read_text(encoding="utf-8"))
            self.assertEqual(persisted, command)
            self.assertEqual(command["command"], "RECOVER_MANUAL_FIX")
            self.assertEqual(command["workflow_revision"], 8)
            self.assertEqual(command["requested_by"], "human")

    def test_manual_fix_recovery_fails_closed_with_delegation_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            init_fixture(project)
            initialize_workflow(project, actor="tester")
            self._set_fix_cap_blocked(project)
            lock = (
                project
                / ".biexce"
                / "state"
                / "AUTOPILOT_DELEGATION.lock"
            )
            lock.write_text("{}\n", encoding="utf-8")
            before = workflow_path_for(project).read_bytes()

            with self.assertRaisesRegex(
                WorkflowStateError, "delegation lock exists"
            ):
                resolve_blocked_workflow(
                    project,
                    action="manual-fix",
                    actor="human",
                    reason="Approved targeted recovery.",
                )

            self.assertEqual(workflow_path_for(project).read_bytes(), before)
            self.assertFalse(command_path_for(project).exists())

    def test_manual_fix_recovery_rejects_non_fix_cap_blocker(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            init_fixture(project)
            initialize_workflow(project, actor="tester")
            self._set_fix_cap_blocked(project)
            path = workflow_path_for(project)
            workflow = json.loads(path.read_text(encoding="utf-8"))
            workflow["blocked_reason"] = "Integration test result: FAIL"
            path.write_text(
                json.dumps(workflow, indent=2) + "\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                WorkflowStateError, "only valid after the task fix cap"
            ):
                resolve_blocked_workflow(
                    project,
                    action="manual-fix",
                    actor="human",
                    reason="Do not reopen unrelated blockers.",
                )


if __name__ == "__main__":
    unittest.main()
