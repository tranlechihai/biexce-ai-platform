from __future__ import annotations

from support import GeneratorTestCase, SLIM_SOURCE, temporary_directory


class WorkflowPackTests(GeneratorTestCase):
    def test_source_pack_is_complete_and_has_no_legacy_authority(self):
        command = (SLIM_SOURCE / "commands" / "bx-auto.md").read_text(
            encoding="utf-8"
        )
        prompts = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((SLIM_SOURCE / "prompts").glob("*.md"))
        )
        templates = {
            path.name
            for path in (SLIM_SOURCE / "templates").glob("*.md")
        }
        self.assertEqual(
            {
                "PROJECT_BRIEF.md",
                "CODEBASE_BRIEF.md",
                "MASTER_PLAN.md",
                "TASK.md",
                "CHECKPOINT.md",
                "FINAL_REPORT.md",
            },
            templates,
        )
        self.assertIn("agent: orchestrator", command)
        self.assertIn("$ARGUMENTS", command)
        self.assertIn("highest workflow authority", command)
        self.assertIn("Run independent, non-overlapping writers concurrently", command)
        self.assertIn("obsolete test", command)
        self.assertIn("Load only the project instructions", command)
        self.assertIn("never relabel failed or unrun evidence as PASS", command)
        combined = command + prompts
        for forbidden in (
            "biexce_drive",
            "biexce_delegate",
            "PROJECT_STATE",
            "AUTOPILOT_WORKFLOW",
            "WIP=1",
            "clear lock",
        ):
            self.assertNotIn(forbidden, combined)

    def test_generated_pack_contains_command_templates_and_source_assets(self):
        with temporary_directory() as root:
            output = self.build(root)
            self.assertEqual(
                (SLIM_SOURCE / "commands" / "bx-auto.md").read_bytes(),
                (output / "commands" / "bx-auto.md").read_bytes(),
            )
            source_templates = {
                path.name: path.read_bytes()
                for path in (SLIM_SOURCE / "templates").glob("*.md")
            }
            output_templates = {
                path.name: path.read_bytes()
                for path in (output / "biexce" / "templates").glob("*.md")
            }
            self.assertEqual(source_templates, output_templates)
            self.assertEqual(
                (SLIM_SOURCE / "plugins" / "biexce-recovery.js").read_bytes(),
                (output / "plugins" / "biexce-recovery.js").read_bytes(),
            )


if __name__ == "__main__":
    import unittest

    unittest.main()
