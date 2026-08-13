import copy
import importlib.util
import json
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "biexce_linux.py"
CONFIG_PATH = REPOSITORY_ROOT / "src" / "global" / "opencode.json"
MANIFEST_PATH = REPOSITORY_ROOT / "src" / "harness-manifest.json"
SPEC = importlib.util.spec_from_file_location("biexce_linux_upgrade", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

OLD_MODEL_ID = "vllm/Qwen/Qwen3.6-35B-A3B-FP8"


class ModelUpgradeTests(unittest.TestCase):
    def test_replaces_managed_model_and_preserves_user_config(self):
        canonical = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        new_model_id = manifest["provider"]["model"]["id"]
        provider_base_url = manifest["provider"]["base_url"]
        existing = {
            "model": f"biexce-local/{OLD_MODEL_ID}",
            "plugin": ["keep-plugin"],
            "mcp": {"keep-mcp": {"type": "local", "command": ["keep"]}},
            "custom_setting": {"keep": True},
            "agent": {
                "custom-agent": {
                    "description": "keep",
                    "mode": "subagent",
                }
            },
            "provider": {
                "biexce-local": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Biexce Local",
                    "options": {
                        "baseURL": provider_base_url,
                    },
                    "models": {
                        OLD_MODEL_ID: {
                            "name": "Biexce Qwen3.6 35B Local",
                        }
                    },
                },
                "keep-provider": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Keep",
                    "options": {"baseURL": "http://127.0.0.1:9999/v1"},
                    "models": {"keep-model": {"name": "Keep Model"}},
                },
            },
            "permission": {"custom-tool": "allow"},
        }
        preserved = copy.deepcopy(existing)

        merged = MODULE.merge_config(existing, canonical)
        managed_models = merged["provider"]["biexce-local"]["models"]

        self.assertEqual(list(managed_models), [new_model_id])
        self.assertNotIn(OLD_MODEL_ID, managed_models)
        self.assertEqual(
            merged["provider"]["keep-provider"],
            preserved["provider"]["keep-provider"],
        )
        self.assertEqual(merged["model"], preserved["model"])
        self.assertEqual(merged["plugin"], preserved["plugin"])
        self.assertEqual(merged["mcp"], preserved["mcp"])
        self.assertEqual(
            merged["custom_setting"],
            preserved["custom_setting"],
        )
        self.assertEqual(
            merged["agent"]["custom-agent"],
            preserved["agent"]["custom-agent"],
        )
        self.assertEqual(merged["permission"]["custom-tool"], "allow")


if __name__ == "__main__":
    unittest.main()
