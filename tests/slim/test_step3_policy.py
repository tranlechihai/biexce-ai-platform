from __future__ import annotations

import os

from support import GeneratorTestCase, SLIM_SOURCE, read_json, temporary_directory


ROOT = SLIM_SOURCE.parents[2]
RESILIENCE_FIXTURE = ROOT / "tests" / "slim" / "fixtures" / "resilience-python"
NODE_FIXTURE = ROOT / "tests" / "slim" / "fixtures" / "resilience-node"


class Step3PolicyTests(GeneratorTestCase):
    def source_text(self, relative: str) -> str:
        return (SLIM_SOURCE / relative).read_text(encoding="utf-8")

    def test_orchestrator_recovers_incidents_without_new_runtime(self):
        prompt = self.source_text("prompts/orchestrator_append.md")
        command = self.source_text("commands/bx-auto.md")
        combined = prompt + command
        for required in (
            "transient provider",
            "stopped or missing child",
            "accepted behavior that invalidates an old test",
            "A child failure is not a project failure",
            "Never loop on an identical failure",
        ):
            self.assertIn(required, combined)
        for forbidden in (
            "fix cap",
            "set a terminal workflow state",
            "manual recovery command",
            "PROJECT_STATE",
            "AUTOPILOT_WORKFLOW",
        ):
            self.assertNotIn(forbidden, combined)

    def test_review_blockers_are_material_and_proportional(self):
        plan = self.source_text("prompts/bx-plan.md")
        review = self.source_text("prompts/bx-review.md")
        test = self.source_text("prompts/bx-test.md")
        self.assertIn("do not require external baseline seals", plan)
        self.assertIn("A blocker requires a reproducible acceptance failure", review)
        self.assertIn("hypothetical assurance", review)
        self.assertIn("Missing optional tooling is N/A", test)
        self.assertIn("infrastructure incident", test)

    def test_small_work_is_not_expanded_into_process_only_tasks(self):
        plan = self.source_text("prompts/bx-plan.md")
        orchestrator = self.source_text("prompts/orchestrator_append.md")
        command = self.source_text("commands/bx-auto.md")
        self.assertIn("smallest task graph", plan)
        self.assertIn("not automatically a separate task contract", " ".join(plan.split()))
        self.assertIn("do not need separate task contracts", " ".join(orchestrator.split()))
        self.assertIn("not a terminal runtime error or an automatic full-plan revision", command)

    def test_safe_checks_are_allowed_but_dangerous_commands_still_ask(self):
        with temporary_directory() as root:
            agents = read_json(self.build(root) / "oh-my-opencode-slim.json")[
                "agents"
            ]
            for role in ("bx-code", "bx-fix", "bx-test"):
                shell = agents[role]["permission"]["bash"]
                for pattern in (
                    "ls*",
                    "python -m unittest*",
                    "python3 -m unittest*",
                    "python -m pytest*",
                    "npm run test*",
                    "dotnet test*",
                    "go test*",
                    "cargo test*",
                ):
                    self.assertEqual("allow", shell[pattern])
                for pattern in (
                    "git reset*",
                    "git clean*",
                    "git push*",
                    "rm *",
                    "Remove-Item *",
                    "terraform apply*",
                ):
                    self.assertEqual("ask", shell[pattern])
            review = agents["bx-review"]["permission"]["bash"]
            self.assertEqual("deny", review["*"])
            self.assertNotIn("python -m unittest*", review)

    def test_policy_is_project_agnostic(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for folder in ("commands", "prompts", "templates")
            for path in sorted((SLIM_SOURCE / folder).glob("*.md"))
        )
        for fixture_token in (
            "calculator",
            "social network",
            "module-a",
            "module-b",
            "normalize_status",
            "normalizeOutcome",
            "resilience-python",
            "resilience-node",
        ):
            self.assertNotIn(fixture_token, combined)

    def test_resilience_fixture_starts_green_without_external_dependencies(self):
        import subprocess
        import sys

        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=RESILIENCE_FIXTURE,
            capture_output=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=30,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("Ran 4 tests", completed.stderr)

    def test_second_language_fixture_starts_green_without_install(self):
        import subprocess

        completed = subprocess.run(
            ["node", "test/run.mjs"],
            cwd=NODE_FIXTURE,
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("pass 4", completed.stdout)


if __name__ == "__main__":
    import unittest

    unittest.main()
