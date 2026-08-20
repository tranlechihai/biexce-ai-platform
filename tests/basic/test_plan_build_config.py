from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from biexce_control.basic_config import BasicConfigError, build_config, inspect_config
from biexce_control.basic_config.launchers import POSIX, WINDOWS


PLAN_MODEL = "openai/gpt-5.6-sol"
BUILD_MODEL = "biexce-local/vllm/Qwen/Qwen3.8-27B-FP8"


@contextmanager
def temporary_directory():
    root = Path(tempfile.gettempdir()) / f"biexce-basic-test-{uuid.uuid4().hex}"
    root.mkdir(mode=0o755)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def write_source_config(root: Path) -> Path:
    source = root / "source"
    source.mkdir()
    (source / "opencode.json").write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "plugin": ["legacy-plugin"],
                "agent": {"bx-director": {"model": "old/model"}},
                "provider": {
                    "biexce-local": {
                        "models": {
                            "vllm/Qwen/Qwen3.8-27B-FP8": {
                                "name": "Qwen 3.8"
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return source


class PlanBuildConfigTest(unittest.TestCase):
    def test_build_is_clean_and_deterministic(self):
        with temporary_directory() as root:
            source = write_source_config(root)
            first = build_config(
                root / "first",
                plan_model=PLAN_MODEL,
                build_model=BUILD_MODEL,
                source_config_dir=source,
            )
            second = build_config(
                root / "second",
                plan_model=PLAN_MODEL,
                build_model=BUILD_MODEL,
                source_config_dir=source,
            )

            first_config = (first / "opencode.json").read_bytes()
            second_config = (second / "opencode.json").read_bytes()
            self.assertEqual(first_config, second_config)

            document = json.loads(first_config)
            self.assertEqual(set(document["agent"]), {"plan", "build"})
            self.assertNotIn("plugin", document)
            self.assertNotIn("bx-director", document["agent"])
            self.assertEqual(document["default_agent"], "plan")

    def test_build_copies_rules_skills_prompts_and_launchers(self):
        with temporary_directory() as root:
            output = build_config(
                root / "output",
                plan_model=PLAN_MODEL,
                build_model=BUILD_MODEL,
                source_config_dir=write_source_config(root),
            )
            report = inspect_config(output)

            self.assertTrue(report["ok"], report)
            self.assertGreaterEqual(len(list((output / "skills").rglob("SKILL.md"))), 40)
            self.assertTrue((output / "AGENTS.md").is_file())
            self.assertTrue((output / "prompts" / "plan.md").is_file())
            self.assertTrue((output / "prompts" / "build.md").is_file())
            self.assertTrue((output / "bin" / "biexce-opencode").is_file())
            self.assertTrue((output / "bin" / "biexce-opencode.cmd").is_file())

    def test_launchers_isolate_global_config_and_ignore_nested_launcher(self):
        for launcher in (POSIX, WINDOWS):
            self.assertIn("XDG_CONFIG_HOME", launcher)
            self.assertIn("BIEXCE_SLIM_CONFIG_DIR", launcher)
            self.assertIn("OPENCODE_CONFIG", launcher)
        self.assertIn('case "${OPENCODE_BINARY##*/}"', POSIX)
        self.assertIn("OPENCODE_BINARY_NAME", WINDOWS)

    def test_rejects_invalid_or_missing_catalog_model(self):
        with temporary_directory() as root:
            source = write_source_config(root)
            with self.assertRaises(BasicConfigError):
                build_config(
                    root / "invalid",
                    plan_model="not-a-model",
                    build_model=BUILD_MODEL,
                    source_config_dir=source,
                )
            with self.assertRaises(BasicConfigError):
                build_config(
                    root / "missing",
                    plan_model=PLAN_MODEL,
                    build_model="biexce-local/vllm/missing",
                    source_config_dir=source,
                )

    def test_refuses_existing_output(self):
        with temporary_directory() as root:
            source = write_source_config(root)
            output = root / "existing"
            output.mkdir()
            with self.assertRaises(BasicConfigError):
                build_config(
                    output,
                    plan_model=PLAN_MODEL,
                    build_model=BUILD_MODEL,
                    source_config_dir=source,
                )


if __name__ == "__main__":
    unittest.main()
