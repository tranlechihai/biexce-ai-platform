import importlib.util
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_PATH = REPOSITORY_ROOT / "scripts" / "biexce_linux.py"
SPEC = importlib.util.spec_from_file_location("biexce_installer", INSTALLER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the BIEXCE installer module.")
INSTALLER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = INSTALLER
SPEC.loader.exec_module(INSTALLER)


class InstallerProviderMergeTest(unittest.TestCase):
    def test_preserves_user_models_and_environment_header(self):
        managed = json.loads(
            (REPOSITORY_ROOT / "src" / "global" / "opencode.json").read_text(
                encoding="utf-8"
            )
        )["provider"]
        existing = {
            "biexce-local": {
                "npm": "old-package",
                "name": "Old name",
                "options": {
                    "baseURL": "https://old.invalid/v1",
                    "headers": {
                        "x-bf-vk": "{env:BIEXCE_LOCAL_VIRTUAL_KEY}",
                    },
                },
                "models": {
                    "vllm/Qwen/Qwen3.8-27B-FP8": {
                        "name": "Biexce Qwen3.8 27B Local",
                        "limit": {"context": 262144, "output": 65536},
                    },
                },
            },
            "openai": {"models": {"gpt-5.6-sol": {}}},
        }

        result = INSTALLER.merge_providers(existing, managed)
        local = result["biexce-local"]

        self.assertEqual(local["npm"], managed["biexce-local"]["npm"])
        self.assertEqual(
            local["options"]["baseURL"],
            managed["biexce-local"]["options"]["baseURL"],
        )
        self.assertEqual(
            local["options"]["headers"]["x-bf-vk"],
            "{env:BIEXCE_LOCAL_VIRTUAL_KEY}",
        )
        self.assertIn("vllm/Qwen/Qwen3.8-27B-FP8", local["models"])
        self.assertIn(INSTALLER.MODEL_ID, local["models"])
        self.assertIn("openai", result)
        INSTALLER.validate_local_provider({"provider": result})


if __name__ == "__main__":
    unittest.main()
