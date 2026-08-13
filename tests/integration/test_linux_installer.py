import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY_ROOT / "scripts" / "biexce_linux.py"
MANIFEST = json.loads(
    (REPOSITORY_ROOT / "src" / "harness-manifest.json").read_text(
        encoding="utf-8"
    )
)


class LinuxInstallerIntegrationTests(unittest.TestCase):
    def run_installer(self, target, *, fail_after_mutation=False):
        environment = os.environ.copy()
        environment["PATH"] = ""
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        if fail_after_mutation:
            environment["BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION"] = "1"
        else:
            environment.pop("BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION", None)

        return subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "install",
                "--root",
                str(REPOSITORY_ROOT),
                "--target",
                str(target),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )

    def assert_static_install(self, target):
        config = json.loads((target / "opencode.json").read_text(encoding="utf-8"))
        provider_id = MANIFEST["provider"]["id"]
        model_id = MANIFEST["provider"]["model"]["id"]
        provider = config["provider"][provider_id]
        self.assertIn(model_id, provider["models"])
        self.assertEqual(
            provider["options"]["headers"],
            {"x-bf-vk": "{env:BIEXCE_LOCAL_VIRTUAL_KEY}"},
        )
        for agent in MANIFEST["agents"]:
            self.assertTrue((target / agent["path"]).is_file())
        for skill in MANIFEST["skills"]:
            self.assertTrue((target / skill["path"]).is_file())
        for runtime in MANIFEST["runtime_files"]:
            self.assertTrue((target / runtime["path"]).is_file())
        for relative in (
            "biexce-bin/biexce",
            "biexce-cli/scripts/biexce.py",
            "biexce-cli/src/biexce_control/cli.py",
            "biexce-cli/src/global/opencode.json",
            "biexce-cli/src/biexce_control/resources/self-test-project/.biexce/FIXTURE.json",
        ):
            self.assertTrue((target / relative).is_file(), relative)
        self.assertTrue(os.access(target / "biexce-bin" / "biexce", os.X_OK))
        package = json.loads((target / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(
            package["dependencies"]["@opencode-ai/plugin"],
            "1.18.4",
        )

    def test_fresh_install_and_reinstall_are_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "opencode"
            first = self.run_installer(target)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assert_static_install(target)

            second = self.run_installer(target)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("Backup: none", second.stdout)

    def test_existing_config_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "opencode"
            target.mkdir()
            existing = {
                "plugin": ["keep-plugin"],
                "mcp": {"keep": {"type": "local", "command": ["keep"]}},
                "agent": {"custom-agent": {"mode": "subagent"}},
                "provider": {
                    "custom-provider": {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": "Keep",
                        "options": {"baseURL": "http://127.0.0.1:9999/v1"},
                        "models": {"keep-model": {"name": "Keep"}},
                    }
                },
            }
            (target / "opencode.json").write_text(
                json.dumps(existing),
                encoding="utf-8",
            )
            existing_package = {
                "private": True,
                "dependencies": {"keep-plugin": "2.0.0"},
            }
            (target / "package.json").write_text(
                json.dumps(existing_package),
                encoding="utf-8",
            )

            result = self.run_installer(target)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            installed = json.loads(
                (target / "opencode.json").read_text(encoding="utf-8")
            )
            for name in ("plugin", "mcp"):
                self.assertEqual(installed[name], existing[name])
            self.assertEqual(
                installed["agent"]["custom-agent"],
                existing["agent"]["custom-agent"],
            )
            self.assertEqual(
                installed["provider"]["custom-provider"],
                existing["provider"]["custom-provider"],
            )
            installed_package = json.loads(
                (target / "package.json").read_text(encoding="utf-8")
            )
            self.assertTrue(installed_package["private"])
            self.assertEqual(
                installed_package["dependencies"]["keep-plugin"], "2.0.0"
            )
            self.assertEqual(
                installed_package["dependencies"]["@opencode-ai/plugin"],
                "1.18.4",
            )

    def test_strict_jsonc_migrates_and_preserves_backup_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "opencode"
            target.mkdir()
            original = b'{\r\n  "plugin": ["keep-plugin"]\r\n}\r\n'
            jsonc_path = target / "opencode.jsonc"
            jsonc_path.write_bytes(original)

            result = self.run_installer(target)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(jsonc_path.exists())
            self.assert_static_install(target)

            backups = list(Path(temporary).glob("opencode.biexce-backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(
                (backups[0] / "opencode.jsonc").read_bytes(),
                original,
            )

    def test_jsonc_and_conflicting_configs_fail_without_mutation(self):
        cases = {
            "real-jsonc": {
                "opencode.jsonc": b'{\n  // keep\n  "plugin": []\n}\n',
            },
            "both-configs": {
                "opencode.json": b"{}\n",
                "opencode.jsonc": b"{}\n",
            },
            "malformed-json": {
                "opencode.json": b'{"plugin": [}\n',
            },
        }
        for label, files in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / "opencode"
                target.mkdir()
                for name, content in files.items():
                    (target / name).write_bytes(content)

                result = self.run_installer(target)
                self.assertNotEqual(result.returncode, 0)
                for name, content in files.items():
                    self.assertEqual((target / name).read_bytes(), content)
                self.assertEqual(
                    list(Path(temporary).glob("opencode.biexce-backup-*")),
                    [],
                )

    def test_failure_after_mutation_rolls_back_jsonc_and_managed_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "opencode"
            target.mkdir()
            original_jsonc = b'{"plugin":["keep"]}\n'
            original_agent = b"existing user agent\n"
            (target / "opencode.jsonc").write_bytes(original_jsonc)
            agent_path = target / "agents" / "bx-code.md"
            agent_path.parent.mkdir()
            agent_path.write_bytes(original_agent)

            result = self.run_installer(target, fail_after_mutation=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((target / "opencode.json").exists())
            self.assertEqual(
                (target / "opencode.jsonc").read_bytes(),
                original_jsonc,
            )
            self.assertEqual(agent_path.read_bytes(), original_agent)


if __name__ == "__main__":
    unittest.main()
