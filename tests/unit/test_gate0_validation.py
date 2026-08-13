import json
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
GLOBAL_ROOT = SOURCE_ROOT / "global"
sys.path.insert(0, str(SOURCE_ROOT))

from biexce_control import apply_action, load_state  # noqa: E402
from biexce_control.fixture import FIXTURE_ID, FixtureError, init_fixture, reset_fixture  # noqa: E402
from biexce_control.model_routing import LOCAL_MODEL, apply_routing, build_profile, save_routing  # noqa: E402
from biexce_control.validation import arm_validator, validate_project  # noqa: E402
from biexce_control.cli import main as cli_main  # noqa: E402
from biexce_control.workflow import load_workflow, workflow_path_for  # noqa: E402


class Gate0ValidationTests(unittest.TestCase):
    def prepare(self, root: Path):
        project = root / "project"
        config = root / "config"
        init_fixture(project)
        routing = build_profile("local-only", actor="tester")
        save_routing(routing, config)
        apply_routing(
            actor="tester",
            config_home=config,
            available_models={LOCAL_MODEL},
        )
        return project, config

    def test_clean_fixture_passes_and_arm_uses_real_validator(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config = self.prepare(Path(temporary))
            report = validate_project(
                project, config_home=config, opencode_root=GLOBAL_ROOT
            )
            self.assertTrue(report.ok, report.to_document())
            apply_action(project, "on", actor="tester", reason="enable")
            apply_action(
                project,
                "arm",
                actor="tester",
                reason="validated",
                arm_validator=arm_validator(
                    config_home=config, opencode_root=GLOBAL_ROOT
                ),
            )
            self.assertEqual(load_state(project).mode, "ARMED")

    def test_quick_auto_start_runs_validation_arm_and_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config = self.prepare(Path(temporary))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "auto",
                        "start",
                        "--project",
                        str(project),
                        "--config-home",
                        str(config),
                        "--opencode-config-dir",
                        str(GLOBAL_ROOT),
                        "--session",
                        "test-session",
                        "--json",
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["mode"], "RUNNING")
            self.assertEqual(
                payload["steps"],
                [
                    "ON_IDLE",
                    "RUNTIME_VALIDATED",
                    "ARMED",
                    "RUNNING",
                    "WORKFLOW:EXPLORE",
                ],
            )
            self.assertEqual(load_state(project).session_id, "test-session")
            self.assertEqual(payload["workflow"]["phase"], "EXPLORE")
            self.assertEqual(payload["workflow"]["expected_agent"], "bx-explore")

    def test_quick_auto_on_is_the_short_start_alias(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config = self.prepare(Path(temporary))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "auto",
                        "on",
                        "--project",
                        str(project),
                        "--config-home",
                        str(config),
                        "--opencode-config-dir",
                        str(GLOBAL_ROOT),
                        "--json",
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["mode"], "RUNNING")
            self.assertEqual(payload["workflow"]["phase"], "EXPLORE")
            self.assertEqual(payload["steps"][-1], "WORKFLOW:EXPLORE")

    def test_quick_auto_on_bootstraps_an_empty_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "empty-project"
            project.mkdir()
            config = root / "config"
            routing = build_profile("local-only", actor="tester")
            save_routing(routing, config)
            apply_routing(
                actor="tester",
                config_home=config,
                available_models={LOCAL_MODEL},
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "auto",
                        "on",
                        "--project",
                        str(project),
                        "--config-home",
                        str(config),
                        "--opencode-config-dir",
                        str(GLOBAL_ROOT),
                        "--json",
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["mode"], "RUNNING")
            self.assertEqual(payload["workflow"]["phase"], "EXPLORE")
            self.assertTrue(workflow_path_for(project).is_file())
            self.assertTrue((project / ".biexce" / "reports").is_dir())
            self.assertFalse((project / ".biexce" / "PROJECT_BRIEF.md").exists())

    def test_master_plan_markdown_table_task_dag_is_valid(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config = self.prepare(Path(temporary))
            plan_path = project / ".biexce" / "MASTER_PLAN.md"
            plan = plan_path.read_text(encoding="utf-8")
            plan = plan.replace(
                "- t-001 — implement addition and subtraction\n"
                "- t-002 — implement multiplication and guarded division; depends on t-001\n"
                "- t-003 — add deterministic unit coverage; depends on t-002",
                "| ID | Goal |\n"
                "| --- | --- |\n"
                "| t-001 | implement addition and subtraction |\n"
                "| t-002 | implement multiplication and guarded division |\n"
                "| t-003 | add deterministic unit coverage |",
            )
            plan_path.write_text(plan, encoding="utf-8")
            report = validate_project(
                project, config_home=config, opencode_root=GLOBAL_ROOT
            )
            self.assertTrue(report.ok, report.to_document())

    def test_self_test_cleans_its_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, config = self.prepare(Path(temporary))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "self-test",
                        "--config-home",
                        str(config),
                        "--opencode-config-dir",
                        str(GLOBAL_ROOT),
                        "--json",
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["fixture_removed"])
            self.assertEqual(
                payload["transitions"],
                ["OFF", "ON_IDLE", "ARMED", "RUNNING", "PAUSED", "OFF"],
            )
            self.assertEqual(
                payload["autopilot_workflow"],
                "PASS (EXPLORE -> bx-explore)",
            )

    def test_cli_cannot_approve_either_human_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config = self.prepare(Path(temporary))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    cli_main(
                        [
                            "auto",
                            "start",
                            "--project",
                            str(project),
                            "--config-home",
                            str(config),
                            "--opencode-config-dir",
                            str(GLOBAL_ROOT),
                        ]
                    ),
                    0,
                )
            workflow_path = workflow_path_for(project)
            document = json.loads(workflow_path.read_text(encoding="utf-8"))
            document["phase"] = "WAITING_GATE_1"
            workflow_path.write_text(
                json.dumps(document, indent=2) + "\n", encoding="utf-8"
            )
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    cli_main(
                        [
                            "autopilot",
                            "approve",
                            "--gate",
                            "1",
                            "--project",
                            str(project),
                            "--config-home",
                            str(config),
                            "--opencode-config-dir",
                            str(GLOBAL_ROOT),
                        ]
                    ),
                    2,
                )
            self.assertEqual(load_workflow(project).phase, "WAITING_GATE_1")

            document = json.loads(workflow_path.read_text(encoding="utf-8"))
            document["phase"] = "WAITING_GATE_2"
            document["gate_1"] = "APPROVED"
            document["gate_1_approved_by"] = "opencode-human:session-1"
            document["gate_1_approved_at_utc"] = "2026-08-05T00:00:00Z"
            workflow_path.write_text(
                json.dumps(document, indent=2) + "\n", encoding="utf-8"
            )
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    cli_main(
                        [
                            "autopilot",
                            "approve",
                            "--gate",
                            "2",
                            "--project",
                            str(project),
                        ]
                    ),
                    2,
                )
            self.assertEqual(load_workflow(project).phase, "WAITING_GATE_2")
            self.assertEqual(load_state(project).mode, "RUNNING")

    def test_state_drift_blocks_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config = self.prepare(Path(temporary))
            state_path = project / ".biexce" / "state" / "PROJECT_STATE.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["tasks"] = []
            state_path.write_text(json.dumps(state), encoding="utf-8")
            report = validate_project(
                project, config_home=config, opencode_root=GLOBAL_ROOT
            )
            self.assertFalse(report.ok)
            self.assertFalse(
                next(check for check in report.checks if check.name == "project_state").ok
            )

    def test_task_verify_na_is_rejected_before_gate_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config = self.prepare(Path(temporary))
            task_path = project / ".biexce" / "tasks" / "t-001.md"
            task = task_path.read_text(encoding="utf-8").replace(
                "Verify: `python -m unittest discover -s tests -v`",
                "Verify: `N/A — command omitted`",
            )
            task_path.write_text(task, encoding="utf-8")
            report = validate_project(
                project, config_home=config, opencode_root=GLOBAL_ROOT
            )
            task_check = next(
                check for check in report.checks if check.name == "task_contracts"
            )
            self.assertFalse(task_check.ok)
            self.assertIn("Verify must be an executable command", task_check.message)

    def test_bx_test_may_own_only_managed_report_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config = self.prepare(Path(temporary))
            task_path = project / ".biexce" / "tasks" / "t-001.md"
            original = task_path.read_text(encoding="utf-8")
            report_task = original.replace(
                "Owner role: bx-code", "Owner role: bx-test"
            ).replace(
                "Writable files: src/calculator.py",
                "Writable files: `.biexce/reports/integration-regression.md`",
            )
            task_path.write_text(report_task, encoding="utf-8")
            report = validate_project(
                project, config_home=config, opencode_root=GLOBAL_ROOT
            )
            task_check = next(
                check for check in report.checks if check.name == "task_contracts"
            )
            self.assertTrue(task_check.ok, task_check.message)

            task_path.write_text(
                report_task.replace(
                    "Writable files: `.biexce/reports/integration-regression.md`",
                    "Writable files: tests/test_regression.py",
                ),
                encoding="utf-8",
            )
            report = validate_project(
                project, config_home=config, opencode_root=GLOBAL_ROOT
            )
            task_check = next(
                check for check in report.checks if check.name == "task_contracts"
            )
            self.assertFalse(task_check.ok)
            self.assertIn("paths under .biexce/reports/", task_check.message)

    def test_plan_wip_limit_allows_bounded_parallel_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, config = self.prepare(Path(temporary))
            plan_path = project / ".biexce" / "MASTER_PLAN.md"
            plan = plan_path.read_text(encoding="utf-8").replace(
                "WIP limit: 1", "WIP limit: 2"
            )
            plan_path.write_text(plan, encoding="utf-8")
            state_path = project / ".biexce" / "state" / "PROJECT_STATE.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            for task in state["tasks"][:2]:
                task.update(status="coding", agent="bx-code")
            state_path.write_text(json.dumps(state), encoding="utf-8")
            report = validate_project(
                project, config_home=config, opencode_root=GLOBAL_ROOT
            )
            self.assertTrue(report.ok, report.to_document())
            state["tasks"][2].update(status="coding", agent="bx-code")
            state_path.write_text(json.dumps(state), encoding="utf-8")
            report = validate_project(
                project, config_home=config, opencode_root=GLOBAL_ROOT
            )
            self.assertFalse(
                next(check for check in report.checks if check.name == "project_state").ok
            )

    def test_reset_requires_marker_confirmation_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            init_fixture(project)
            (project / "temporary-output.txt").write_text("remove", encoding="utf-8")
            with self.assertRaises(FixtureError):
                reset_fixture(project, confirmation="wrong")
            reset_fixture(project, confirmation=FIXTURE_ID)
            self.assertFalse((project / "temporary-output.txt").exists())
            self.assertEqual(
                list(root.glob(".biexce-fixture-stage-*"))
                + list(root.glob(".biexce-fixture-backup-*")),
                [],
            )


if __name__ == "__main__":
    unittest.main()
