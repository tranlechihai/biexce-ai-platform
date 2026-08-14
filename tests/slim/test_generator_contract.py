from __future__ import annotations
from support import GeneratorTestCase, SLIM_SOURCE, read_json, temporary_directory


class GeneratorContractTests(GeneratorTestCase):
    def test_pin_and_source_baseline_are_explicit(self):
        compatibility = read_json(SLIM_SOURCE / "compatibility.json")
        self.assertEqual("2.2.13", compatibility["slim"]["version"])
        self.assertEqual(
            "781ca04fb83dbcd73a262c19ca70533ebbc117d2",
            compatibility["slim"]["git_head"],
        )
        self.assertEqual(
            "sha512-v5W4nUZs1/1P2YAQZQkyp1Mb1PJSLWi565kg6Rz4ua1pN/XY/"
            "eZ+U2ZdQvkxyB9PY6qjrx8s6JAnvvEWthslcQ==",
            compatibility["slim"]["integrity"],
        )
        self.assertEqual(
            "654acc424c56f65d9de841f5c040556252f0e114e7ce77966cb3bfef4ed25432",
            compatibility["slim"]["schema_sha256"],
        )
        self.assertEqual(
            "orchestratorWake", compatibility["slim"]["background_wake_key"]
        )
        self.assertEqual("1.18.13", compatibility["opencode"]["prototype_sdk"])
        self.assertEqual("1.18.13", compatibility["opencode"]["prototype_cli"])
        self.assertEqual("1.18.4", compatibility["opencode"]["baseline_cli"])

    def test_generated_opencode_and_package_are_exactly_pinned(self):
        with temporary_directory() as root:
            output = self.build(root)
            opencode = read_json(output / "opencode.json")
            package = read_json(output / "package.json")
            expected_plugins = [
                "./node_modules/oh-my-opencode-slim/dist/index.js",
                "./plugins/biexce-role-access.js",
                "./plugins/biexce-recovery.js",
            ]
            self.assertEqual(expected_plugins, opencode["plugin"])
            self.assertEqual("bx-director", opencode["default_agent"])
            self.assertFalse(opencode["autoupdate"])
            disabled = {"build", "plan", "general", "explore", "scout"}
            self.assertEqual(disabled, set(opencode["agent"]))
            self.assertTrue(all(item["disable"] for item in opencode["agent"].values()))
            self.assertEqual("ask", opencode["permission"]["external_directory"])
            self.assertEqual("ask", opencode["permission"]["edit"])
            self.assertEqual("ask", opencode["permission"]["task"])
            self.assertEqual("ask", opencode["permission"]["bash"]["git reset*"])
            self.assertEqual(
                "2.2.13", package["dependencies"]["oh-my-opencode-slim"]
            )
            self.assertEqual(
                "1.18.13", package["dependencies"]["@opencode-ai/plugin"]
            )
            self.assertEqual(
                "1.18.13", package["dependencies"]["@opencode-ai/sdk"]
            )
            self.assertEqual(
                "1.18.13", package["devDependencies"]["opencode-ai"]
            )
            self.assertEqual("4.4.3", package["dependencies"]["zod"])
            self.assertEqual(
                "OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true\n",
                (output / "runtime.env.example").read_text(encoding="utf-8"),
            )
            background = read_json(output / "oh-my-opencode-slim.json")[
                "backgroundJobs"
            ]
            self.assertNotIn("continueOnIdle", background)
            self.assertEqual(
                {"enabled": True, "intervalMs": 300000}, background["orchestratorWake"]
            )

    def test_seven_role_mapping_and_models(self):
        expected_routing = read_json(self.routing)["models"]
        with temporary_directory() as root:
            agents = read_json(self.build(root) / "oh-my-opencode-slim.json")["agents"]
            self.assertEqual(
                {
                    "orchestrator",
                    "bx-plan",
                    "bx-explore",
                    "bx-code",
                    "bx-fix",
                    "bx-test",
                    "bx-review",
                },
                set(agents),
            )
            self.assertEqual("bx-director", agents["orchestrator"]["displayName"])
            specialists = (
                definition for name, definition in agents.items() if name != "orchestrator"
            )
            self.assertTrue(all("displayName" not in item for item in specialists))
            from support import prototype

            for role, slim_id in prototype.SLIM_IDS.items():
                self.assertEqual(expected_routing[role], agents[slim_id]["model"])
            self.assertNotIn("bx-director", agents)

    def test_unused_builtins_are_disabled(self):
        with temporary_directory() as root:
            config = read_json(self.build(root) / "oh-my-opencode-slim.json")
            self.assertEqual(
                {
                    "explorer",
                    "librarian",
                    "oracle",
                    "designer",
                    "fixer",
                    "observer",
                    "council",
                },
                set(config["disabled_agents"]),
            )
            self.assertNotIn("orchestrator", config["disabled_agents"])

    def test_effective_role_permissions(self):
        with temporary_directory() as root:
            agents = read_json(self.build(root) / "oh-my-opencode-slim.json")["agents"]
            self.assertEqual("allow", agents["orchestrator"]["permission"]["task"])
            self.assertEqual(
                "allow", agents["orchestrator"]["permission"]["todowrite"]
            )
            for name, definition in agents.items():
                permission = definition["permission"]
                if name != "orchestrator":
                    self.assertEqual("deny", permission["task"])
                self.assertEqual("ask", permission["external_directory"])
            review = agents["bx-review"]["permission"]
            self.assertEqual("deny", review["edit"])
            self.assertEqual("deny", review["bash"]["*"])
            self.assertEqual("allow", review["bash"]["git diff*"])
            self.assertNotIn("rm *", review["bash"])
            for name in ("bx-code", "bx-fix", "bx-test"):
                self.assertEqual("allow", agents[name]["permission"]["edit"])
                self.assertNotEqual(
                    "allow", agents[name]["permission"]["bash"]["git reset*"]
                )
            self.assertIsInstance(agents["bx-plan"]["permission"]["edit"], dict)
            self.assertIsInstance(agents["bx-explore"]["permission"]["edit"], dict)

    def test_lazy_skills_are_explicit_and_copied(self):
        with temporary_directory() as root:
            output = self.build(root)
            agents = read_json(output / "oh-my-opencode-slim.json")["agents"]
            selected: set[str] = set()
            for definition in agents.values():
                skills = definition["skills"]
                self.assertGreaterEqual(len(skills), 2)
                self.assertLessEqual(len(skills), 5)
                self.assertNotIn("*", skills)
                selected.update(skills)
            copied = {
                path.parent.name for path in (output / "skills").rglob("SKILL.md")
            }
            self.assertEqual(selected, copied)

    def test_prompts_are_complete_and_do_not_reference_legacy_runtime(self):
        forbidden = (
            "biexce_drive",
            "biexce_delegate",
            "AUTOPILOT_WORKFLOW",
            "PROJECT_STATE",
            "AUTOPILOT_DELEGATION",
        )
        with temporary_directory() as root:
            prompt_root = self.build(root) / "oh-my-opencode-slim"
            prompts = sorted(prompt_root.glob("*.md"))
            self.assertEqual(7, len(prompts))
            combined = "\n".join(
                path.read_text(encoding="utf-8") for path in prompts
            )
            for token in forbidden:
                self.assertNotIn(token, combined)
            for role in (
                "bx-plan",
                "bx-explore",
                "bx-code",
                "bx-fix",
                "bx-test",
                "bx-review",
            ):
                self.assertIn(
                    "delegate to another agent",
                    (prompt_root / f"{role}.md").read_text(encoding="utf-8"),
                )
            orchestrator = (prompt_root / "orchestrator_append.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("dispatch exactly those roles", orchestrator)
            self.assertIn("do not collapse multiple named lanes", orchestrator)
            self.assertIn("Do not summarize away operational details", orchestrator)

    def test_recovery_bridge_uses_native_state_only(self):
        with temporary_directory() as root:
            plugin = self.build(root) / "plugins" / "biexce-recovery.js"
            core = plugin.parent.parent / "runtime" / "recovery-core.js"
            self.assertTrue(plugin.is_file())
            self.assertTrue(core.is_file())
            plugin_content = plugin.read_text(encoding="utf-8")
            self.assertEqual(1, plugin_content.count("export const"))
            content = plugin_content + core.read_text(encoding="utf-8")
            for api in (
                "sessionApi.list",
                "sessionApi.todo",
                "sessionApi.children",
                "sessionApi.status",
                "sessionApi.messages",
                "sessionApi.promptAsync",
            ):
                self.assertIn(api, content)
            for forbidden in (
                ".biexce",
                "PROJECT_STATE",
                "AUTOPILOT_WORKFLOW",
                "writeFile",
                "lockfile",
            ):
                self.assertNotIn(forbidden, content)
