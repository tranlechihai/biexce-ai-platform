from __future__ import annotations

from pathlib import Path

from support import GeneratorTestCase, read_json, temporary_directory
from biexce_control.slim_config.service import (
    build_from_user_routing,
    inspect_generated_config,
)
from biexce_control.slim_config.doctor import run_generated_doctor
from biexce_control.model_routing import apply_routing, save_routing


class SlimServiceTests(GeneratorTestCase):
    def test_build_from_explicit_routing_is_structurally_ready(self):
        with temporary_directory() as root:
            output = build_from_user_routing(
                root / "config",
                routing_file=self.routing,
                opencode_root=self.source_config.parent,
            )
            status = inspect_generated_config(output)
            self.assertTrue(status["ok"])
            self.assertFalse(status["ready_to_run"])
            checks = {item["name"]: item for item in status["checks"]}
            self.assertTrue(checks["roles"]["ok"])
            self.assertTrue(checks["command"]["ok"])
            self.assertTrue(checks["templates"]["ok"])
            self.assertTrue(checks["recovery"]["ok"])
            self.assertTrue(checks["role_access"]["ok"])
            self.assertFalse(checks["dependencies"]["ok"])

    def test_inspection_fails_when_workflow_command_is_missing(self):
        with temporary_directory() as root:
            output = self.build(root)
            (output / "commands" / "bx-auto.md").unlink()
            status = inspect_generated_config(output)
            self.assertFalse(status["ok"])
            checks = {item["name"]: item for item in status["checks"]}
            self.assertFalse(checks["command"]["ok"])

    def test_generated_models_match_explicit_routing(self):
        with temporary_directory() as root:
            output = build_from_user_routing(
                root / "config",
                routing_file=self.routing,
                opencode_root=self.source_config.parent,
            )
            routing = read_json(self.routing)["models"]
            agents = read_json(output / "oh-my-opencode-slim.json")["agents"]
            from support import prototype

            for role, slim_id in prototype.SLIM_IDS.items():
                self.assertEqual(routing[role], agents[slim_id]["model"])

    def test_default_build_reads_applied_user_routing(self):
        with temporary_directory() as root:
            config_home = root / "biexce-config"
            routing = read_json(self.routing)["models"]
            document = {
                "$schema": (
                    "https://schemas.biexce.local/control-plane/"
                    "model-routing-v1.schema.json"
                ),
                "schema_version": 1,
                "inherit_parent_model": False,
                "unconfigured_policy": "block",
                "active_profile": None,
                "revision": 1,
                "updated_at_utc": "2026-08-13T00:00:00Z",
                "updated_by": "test",
                "agents": {
                    role: {
                        "primary": model,
                        "fallbacks": [],
                        "source": "manual",
                        "confirmed_cross_zone_fallbacks": [],
                    }
                    for role, model in routing.items()
                },
            }
            save_routing(document, config_home)
            apply_routing(actor="test", config_home=config_home)
            output = build_from_user_routing(
                root / "config",
                config_home=config_home,
                opencode_root=self.source_config.parent,
            )
            agents = read_json(output / "oh-my-opencode-slim.json")["agents"]
            self.assertEqual(routing["bx-code"], agents["bx-code"]["model"])

    def test_runtime_doctor_stays_fail_closed_before_local_install(self):
        with temporary_directory() as root:
            output = self.build(root)
            doctor = run_generated_doctor(output)
            self.assertFalse(doctor["ok"])
            self.assertTrue(doctor["structural_ok"])
            self.assertFalse(doctor["ready_to_run"])
            self.assertEqual([], doctor["runtime_checks"])


if __name__ == "__main__":
    import unittest

    unittest.main()
