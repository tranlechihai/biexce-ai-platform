from __future__ import annotations

import os

from support import GeneratorTestCase, temporary_directory
from biexce_control.slim_config.service import inspect_generated_config


class LauncherIsolationTests(GeneratorTestCase):
    def test_generated_launchers_isolate_legacy_config(self):
        with temporary_directory() as root:
            output = self.build(root)
            posix = output / "bin" / "biexce-opencode"
            windows = output / "bin" / "biexce-opencode.cmd"
            self.assertTrue(posix.is_file())
            self.assertTrue(windows.is_file())
            self.assertTrue(os.access(posix, os.X_OK))
            self.assertTrue((output / ".xdg-config" / "opencode").is_dir())
            combined = posix.read_text() + windows.read_text()
            for variable in (
                "OPENCODE_CONFIG_DIR",
                "XDG_CONFIG_HOME",
                "OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS",
                "OPENCODE_DISABLE_PROJECT_CONFIG",
                "OPENCODE_DISABLE_EXTERNAL_SKILLS",
            ):
                self.assertIn(variable, combined)
            self.assertNotIn("biexce-control.js", combined)
            self.assertNotIn(".config/opencode", combined)

    def test_status_requires_isolated_launcher(self):
        with temporary_directory() as root:
            output = self.build(root)
            status = inspect_generated_config(output)
            checks = {item["name"]: item for item in status["checks"]}
            self.assertTrue(checks["launcher"]["ok"])
            (output / "bin" / "biexce-opencode").unlink()
            status = inspect_generated_config(output)
            checks = {item["name"]: item for item in status["checks"]}
            self.assertFalse(status["ok"])
            self.assertFalse(checks["launcher"]["ok"])


if __name__ == "__main__":
    import unittest

    unittest.main()
