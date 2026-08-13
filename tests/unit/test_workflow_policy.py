import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_MODULE = REPOSITORY_ROOT / "src" / "global" / "runtime" / "workflow-policy.js"


@unittest.skipUnless(shutil.which("node"), "Node.js is required for runtime tests")
class WorkflowPolicyTests(unittest.TestCase):
    def test_schema_is_strict_and_versioned(self):
        schema = json.loads(
            (
                REPOSITORY_ROOT
                / "src"
                / "biexce_control"
                / "schemas"
                / "workflow-policy-v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["properties"]["effective_profile"]["enum"]),
            {"fast", "standard", "critical", "advisory"},
        )

    def run_node(self, project: Path, script: str) -> dict[str, object]:
        environment = os.environ.copy()
        environment["PROJECT"] = str(project)
        environment["RUNTIME_URL"] = RUNTIME_MODULE.resolve().as_uri()
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
        return json.loads(result.stdout)

    def prepare_project(self, root: Path, text: str) -> Path:
        project = root / "project"
        (project / ".biexce" / "tasks").mkdir(parents=True)
        (project / ".biexce" / "state").mkdir(parents=True)
        (project / ".biexce" / "PROJECT_BRIEF.md").write_text(
            text, encoding="utf-8"
        )
        (project / ".biexce" / "MASTER_PLAN.md").write_text(
            "# Master Plan\n", encoding="utf-8"
        )
        return project

    def test_auto_profile_keeps_normal_application_security_work_standard(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.prepare_project(
                Path(temporary),
                "# Brief\nImplement authentication, permissions and database migration.\n",
            )
            payload = self.run_node(
                project,
                textwrap.dedent(
                    """
                    import fs from "node:fs"
                    const policy = await import(process.env.RUNTIME_URL)
                    const selected = policy.selectAndPersistWorkflowPolicy(
                      process.env.PROJECT,
                      {
                        requestedProfile: "auto",
                        allowCriticalDowngrade: false,
                        actor: "unit-test",
                      },
                    )
                    const stored = JSON.parse(fs.readFileSync(
                      process.env.PROJECT + "/.biexce/state/AUTOPILOT_POLICY.json",
                      "utf8",
                    ))
                    console.log(JSON.stringify({ selected, stored }))
                    """
                ),
            )
            self.assertEqual(payload["selected"]["effective_profile"], "standard")
            self.assertIn("authentication", payload["selected"]["risk_flags"])
            self.assertIn("database-migration", payload["selected"]["risk_flags"])
            self.assertEqual(payload["stored"], payload["selected"])
            self.assertEqual(payload["stored"]["driver_status"], "IDLE")

    def test_critical_downgrade_requires_an_explicit_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.prepare_project(
                Path(temporary),
                "# Brief\nDeploy to production with an irreversible destructive operation.\n",
            )
            payload = self.run_node(
                project,
                textwrap.dedent(
                    """
                    const policy = await import(process.env.RUNTIME_URL)
                    const protectedSelection = policy.selectWorkflowProfile(
                      process.env.PROJECT,
                      { requestedProfile: "fast", allowCriticalDowngrade: false },
                    )
                    const overriddenSelection = policy.selectWorkflowProfile(
                      process.env.PROJECT,
                      { requestedProfile: "fast", allowCriticalDowngrade: true },
                    )
                    const advisory = policy.profilePolicy("advisory")
                    console.log(JSON.stringify({
                      protectedSelection,
                      overriddenSelection,
                      advisory,
                    }))
                    """
                ),
            )
            self.assertEqual(
                payload["protectedSelection"]["effective_profile"], "critical"
            )
            self.assertEqual(
                payload["overriddenSelection"]["effective_profile"], "fast"
            )
            self.assertEqual(
                payload["overriddenSelection"]["source"], "explicit-override"
            )
            self.assertFalse(payload["advisory"]["execute_source"])
            self.assertEqual(payload["advisory"]["max_batch"], 0)

    def test_non_production_and_out_of_scope_language_stays_standard(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = self.prepare_project(
                Path(temporary),
                "\n".join(
                    [
                        "# Brief",
                        "Build a non-production social backend acceptance fixture.",
                        "Production deployment is out of scope.",
                        "Do not perform destructive operations or modify live data.",
                    ]
                ),
            )
            payload = self.run_node(
                project,
                textwrap.dedent(
                    """
                    const policy = await import(process.env.RUNTIME_URL)
                    const selected = policy.selectWorkflowProfile(
                      process.env.PROJECT,
                      { requestedProfile: "auto", allowCriticalDowngrade: false },
                    )
                    console.log(JSON.stringify(selected))
                    """
                ),
            )
            self.assertEqual(payload["effective_profile"], "standard")
            self.assertIn("production", payload["risk_flags"])
            self.assertIn("destructive-operation", payload["risk_flags"])


if __name__ == "__main__":
    unittest.main()
