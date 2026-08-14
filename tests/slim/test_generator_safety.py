from __future__ import annotations

import json
from pathlib import Path

from support import (
    GeneratorTestCase,
    content_map,
    file_digest,
    prototype,
    read_json,
    temporary_directory,
)


class GeneratorSafetyTests(GeneratorTestCase):
    def test_build_is_deterministic_and_does_not_mutate_source(self):
        before = file_digest(self.source_config)
        with temporary_directory() as root:
            first = self.build(root, "first")
            second = self.build(root, "second")
            self.assertEqual(content_map(first), content_map(second))
        self.assertEqual(before, file_digest(self.source_config))

    def test_invalid_routing_fails_without_output(self):
        with temporary_directory() as root:
            invalid = root / "routing.json"
            invalid.write_text(
                json.dumps({"schema_version": 1, "models": {"bx-code": "bad"}}),
                encoding="utf-8",
            )
            output = root / "output"
            with self.assertRaises(prototype.PrototypeError):
                prototype.build_prototype(invalid, output)
            self.assertFalse(output.exists())

    def test_custom_provider_model_must_exist_in_base_catalog(self):
        with temporary_directory() as root:
            routing = read_json(self.routing)
            routing["models"]["bx-code"] = (
                "biexce-local/vllm/DeepSeek-V4-Flash-0731"
            )
            routing_path = root / "routing.json"
            routing_path.write_text(json.dumps(routing), encoding="utf-8")
            output = root / "output"
            with self.assertRaisesRegex(prototype.PrototypeError, "missing from provider"):
                prototype.build_prototype(routing_path, output)
            self.assertFalse(output.exists())

    def test_alternate_read_only_base_config_supports_user_model_catalog(self):
        with temporary_directory() as root:
            routing = read_json(self.routing)
            deepseek = "biexce-local/vllm/DeepSeek-V4-Flash-0731"
            for role in ("bx-explore", "bx-code", "bx-fix", "bx-test"):
                routing["models"][role] = deepseek
            routing_path = root / "routing.json"
            routing_path.write_text(json.dumps(routing), encoding="utf-8")

            base = read_json(self.source_config)
            base["provider"]["biexce-local"]["models"][
                "vllm/DeepSeek-V4-Flash-0731"
            ] = {
                "name": "DeepSeek local",
                "limit": {"context": 524288, "output": 65536},
            }
            base["mcp"] = {
                "unrelated-server": {
                    "type": "remote",
                    "url": "http://127.0.0.1:8080/mcp",
                    "enabled": True,
                }
            }
            base_path = root / "base-opencode.json"
            base_path.write_text(json.dumps(base), encoding="utf-8")
            before = file_digest(base_path)

            output = root / "output"
            prototype.build_prototype(routing_path, output, base_path)
            self.assertEqual(before, file_digest(base_path))
            agents = read_json(output / "oh-my-opencode-slim.json")["agents"]
            self.assertEqual(deepseek, agents["bx-code"]["model"])
            generated = read_json(output / "opencode.json")
            self.assertIn(
                "vllm/DeepSeek-V4-Flash-0731",
                generated["provider"]["biexce-local"]["models"],
            )
            self.assertFalse(generated["mcp"]["unrelated-server"]["enabled"])

    def test_refuses_default_user_global_destination(self):
        forbidden = Path.home() / ".config" / "opencode"
        with self.assertRaises(prototype.PrototypeError):
            prototype.validate_output_path(forbidden)

    def test_live_fixture_seed_is_minimal_and_clean(self):
        fixture = Path(__file__).resolve().parent / "fixtures" / "live-smoke"
        files = {
            path.relative_to(fixture).as_posix()
            for path in fixture.rglob("*")
            if path.is_file()
        }
        self.assertEqual(
            {
                "README.md",
                "module-a/input.txt",
                "module-b/input.txt",
                "shared.txt",
            },
            files,
        )
        self.assertEqual(b"BASE\n", (fixture / "shared.txt").read_bytes())
        self.assertFalse((fixture / ".biexce").exists())
        self.assertFalse((fixture / "outputs").exists())
