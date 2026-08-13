import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "biexce_linux.py"
SPEC = importlib.util.spec_from_file_location("biexce_linux", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OpenCodeVersionTests(unittest.TestCase):
    def test_supported_range(self):
        self.assertFalse(MODULE.is_supported_opencode_version("1.18.3"))
        self.assertTrue(MODULE.is_supported_opencode_version("1.18.4"))
        self.assertTrue(MODULE.is_supported_opencode_version("1.18.7"))
        self.assertFalse(MODULE.is_supported_opencode_version("1.19.0"))

    def test_crlf_and_trailing_spaces(self):
        self.assertEqual(
            MODULE.parse_opencode_version("  1.18.7  \r\n\r\n"),
            "1.18.7",
        )

    def test_stderr_combined_output_shape(self):
        self.assertEqual(
            MODULE.parse_opencode_version("\n1.18.7\r\n"),
            "1.18.7",
        )

    def test_ansi_output(self):
        self.assertEqual(
            MODULE.parse_opencode_version("\x1b[32m1.18.7\x1b[0m\n"),
            "1.18.7",
        )

    def test_runtime_verification_isolates_external_skills(self):
        payload = (
            '[{"name":"first","content":"'
            + ("á" * 70000)
            + '"},{"name":"ci-config"}]\n'
        ).encode("utf-8")

        def complete_run(*_args, **kwargs):
            kwargs["stdout"].write(payload)
            kwargs["stdout"].flush()
            return mock.Mock(returncode=0)

        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            MODULE.subprocess,
            "run",
            side_effect=complete_run,
        ) as run:
            output = MODULE.run_opencode(
                ["opencode"],
                Path(temporary) / "opencode",
                ("debug", "skill", "--pure"),
            )

        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["OPENCODE_DISABLE_EXTERNAL_SKILLS"], "1")
        self.assertEqual(
            environment["OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"],
            "1",
        )
        self.assertIsNot(run.call_args.kwargs["stdout"], MODULE.subprocess.PIPE)
        self.assertIn('"name":"ci-config"', output)
        self.assertGreater(len(output.encode("utf-8")), 65536)


if __name__ == "__main__":
    unittest.main()
