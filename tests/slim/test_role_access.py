from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock

from biexce_control.slim_config import doctor


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "src" / "global" / "slim" / "runtime" / "role-access.js"
PLUGIN = ROOT / "src" / "global" / "slim" / "plugins" / "biexce-role-access.js"


def expose(agent_document: dict) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for role-access tests")
    script = r"""
import { pathToFileURL } from "node:url"
const module = await import(pathToFileURL(process.env.BX_MODULE).href)
const config = JSON.parse(process.env.BX_AGENTS)
const result = module.exposeUserFacingRoles(config)
console.log(JSON.stringify({ config, result }))
"""
    completed = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True,
        check=True,
        encoding="utf-8",
        env=os.environ
        | {"BX_MODULE": str(MODULE), "BX_AGENTS": json.dumps(agent_document)},
    )
    return json.loads(completed.stdout)


def apply_plugin(agent_document: dict) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for role-access tests")
    script = r"""
import { pathToFileURL } from "node:url"
const module = await import(pathToFileURL(process.env.BX_PLUGIN).href)
const config = JSON.parse(process.env.BX_AGENTS)
const plugin = await module.BiexceRoleAccessPlugin({
  client: { app: { log: async () => {} } },
})
await plugin.config(config)
console.log(JSON.stringify(config))
"""
    completed = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        capture_output=True,
        check=True,
        encoding="utf-8",
        env=os.environ
        | {"BX_PLUGIN": str(PLUGIN), "BX_AGENTS": json.dumps(agent_document)},
    )
    return json.loads(completed.stdout)


class RoleAccessTests(unittest.TestCase):
    def test_exposes_alias_and_hides_internal_orchestrator(self):
        ids = (
            "orchestrator",
            "bx-plan",
            "bx-explore",
            "bx-code",
            "bx-fix",
            "bx-test",
            "bx-review",
        )
        source = {
            name: {"mode": "subagent", "hidden": True}
            for name in ids
        }
        source["BX-Director"] = {
            "mode": "primary",
            "displayName": "BX-Director",
        }
        source["BX-Code"] = dict(source["bx-code"])
        result = expose({"agent": source})
        self.assertTrue(result["result"]["ok"])
        agents = result["config"]["agent"]
        self.assertEqual({*ids, "bx-director"}, set(agents))
        self.assertEqual("bx-director", result["config"]["default_agent"])
        self.assertEqual("primary", agents["bx-director"]["mode"])
        self.assertNotIn("hidden", agents["bx-director"])
        self.assertEqual("subagent", agents["orchestrator"]["mode"])
        self.assertTrue(agents["orchestrator"]["hidden"])
        for name in ids[1:]:
            self.assertEqual("all", agents[name]["mode"])
            self.assertNotIn("hidden", agents[name])

    def test_reports_missing_registration_without_creating_fake_agents(self):
        result = expose({"agent": {"orchestrator": {"mode": "primary"}}})
        self.assertFalse(result["result"]["ok"])
        self.assertEqual({"orchestrator"}, set(result["config"]["agent"]))
        self.assertEqual(
            {
                "bx-director",
                "bx-plan",
                "bx-explore",
                "bx-code",
                "bx-fix",
                "bx-test",
                "bx-review",
            },
            set(result["result"]["missing"]),
        )

    def test_runtime_probe_requires_real_visible_registry(self):
        def fake_debug(_root, agent_id):
            if agent_id == "orchestrator":
                return {
                    "name": agent_id,
                    "mode": "subagent",
                    "hidden": True,
                }, ""
            return {
                "name": agent_id,
                "mode": doctor.EXPECTED_AGENT_MODES[agent_id],
            }, ""

        with mock.patch.object(doctor, "_debug_agent", side_effect=fake_debug):
            result = doctor.probe_role_access(ROOT)
        self.assertTrue(result["ok"], result["detail"])

    def test_plugin_hook_applies_the_registry_transform(self):
        ids = ("orchestrator", *doctor.EXPECTED_AGENT_MODES.keys())
        agents = {
            name: {"mode": "subagent", "hidden": True}
            for name in set(ids)
        }
        result = apply_plugin({"agent": agents})["agent"]
        self.assertEqual("primary", result["bx-director"]["mode"])
        self.assertTrue(result["orchestrator"]["hidden"])
        for name in doctor.EXPECTED_AGENT_MODES:
            self.assertNotIn("hidden", result[name])


if __name__ == "__main__":
    unittest.main()
