import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from biexce_control.model_routing import (  # noqa: E402
    AGENTS,
    LOCAL_MODEL,
    ModelPolicyError,
    ModelRoutingError,
    apply_routing,
    authenticated_providers,
    build_profile,
    discover_models,
    load_applied_routing,
    provider_health,
    provider_readiness,
    readiness_warnings,
    resolve_config_reference,
    routing_status,
    save_routing,
    set_fallback,
    set_primary,
    validate_routing_document,
)


class ModelRoutingTests(unittest.TestCase):
    def test_provider_readiness_distinguishes_catalog_auth_and_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "opencode.json").write_text(
                json.dumps({"provider": {}}), encoding="utf-8"
            )
            auth_file = root / "auth.json"
            auth_file.write_text(
                json.dumps(
                    {"openai": {"type": "oauth", "access": "secret-value"}}
                ),
                encoding="utf-8",
            )

            authenticated, auth_warnings = authenticated_providers(auth_file)
            readiness, warnings = provider_readiness(
                {"openai", "opencode"}, root, auth_file=auth_file
            )
            by_provider = {item["provider"]: item for item in readiness}

            self.assertEqual(authenticated, {"openai"})
            self.assertEqual(auth_warnings, [])
            self.assertEqual(warnings, [])
            self.assertEqual(by_provider["openai"]["status"], "AUTHENTICATED")
            self.assertEqual(
                by_provider["opencode"]["status"], "NOT AUTHENTICATED"
            )
            self.assertTrue(
                all(
                    item["inference_status"] == "NOT VERIFIED"
                    for item in readiness
                )
            )
            self.assertNotIn("secret-value", json.dumps(readiness))
            self.assertIn("routing remains allowed", readiness_warnings(readiness)[0])

    def test_local_endpoint_environment_reference_is_resolved_per_machine(self):
        reference = '{env:BIEXCE_LOCAL_BASE_URL}'
        with patch.dict(
            os.environ,
            {'BIEXCE_LOCAL_BASE_URL': 'http://127.0.0.1:8087/v1'},
            clear=False,
        ):
            self.assertEqual(
                resolve_config_reference(reference),
                'http://127.0.0.1:8087/v1',
            )
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(resolve_config_reference(reference))

    def test_provider_health_warns_when_local_endpoint_is_not_configured(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'opencode.json').write_text(
                json.dumps(
                    {
                        'provider': {
                            'biexce-local': {
                                'options': {
                                    'baseURL': '{env:BIEXCE_LOCAL_BASE_URL}'
                                }
                            }
                        }
                    }
                ),
                encoding='utf-8',
            )
            with patch.dict(os.environ, {}, clear=True):
                result = provider_health(root)
            self.assertEqual(result[0]['status'], 'WARN')
            self.assertIn('BIEXCE_LOCAL_BASE_URL', result[0]['detail'])

    def test_local_readiness_reports_virtual_key_without_exposing_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "opencode.json").write_text(
                json.dumps(
                    {
                        "provider": {
                            "biexce-local": {
                                "options": {
                                    "baseURL": "{env:BIEXCE_LOCAL_BASE_URL}",
                                    "headers": {
                                        "x-bf-vk": (
                                            "{env:BIEXCE_LOCAL_VIRTUAL_KEY}"
                                        )
                                    },
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "BIEXCE_LOCAL_BASE_URL": "https://gateway.example/v1",
                    "BIEXCE_LOCAL_VIRTUAL_KEY": "private-test-value",
                },
                clear=False,
            ), patch(
                "biexce_control.model_routing.provider_health",
                return_value=[
                    {
                        "provider": "biexce-local",
                        "status": "PASS",
                        "detail": "TCP reachable",
                    }
                ],
            ):
                readiness, warnings = provider_readiness(
                    {"biexce-local"}, root, auth_file=root / "missing-auth.json"
                )
        self.assertEqual(warnings, [])
        self.assertEqual(readiness[0]["credential_status"], "CONFIGURED")
        self.assertIn("BIEXCE_LOCAL_VIRTUAL_KEY is configured", readiness[0]["detail"])
        self.assertNotIn("private-test-value", json.dumps(readiness))

    def test_provider_health_rejects_a_relative_local_endpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'opencode.json').write_text(
                json.dumps(
                    {
                        'provider': {
                            'biexce-local': {
                                'options': {'baseURL': 'not-an-absolute-url'}
                            }
                        }
                    }
                ),
                encoding='utf-8',
            )
            result = provider_health(root)
            self.assertEqual(result[0]['status'], 'WARN')
            self.assertIn('absolute HTTP(S)', result[0]['detail'])

    def test_static_inventory_includes_native_agent_model_bindings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cloud_model = "openai/gpt-5.6-sol-fast"
            (root / "opencode.json").write_text(
                json.dumps(
                    {
                        "agent": {
                            "bx-code": {"model": cloud_model},
                        }
                    }
                ),
                encoding="utf-8",
            )

            models, warnings = discover_models(root, include_runtime=False)

            self.assertEqual(models, [cloud_model])
            self.assertEqual(warnings, [])

    def test_local_profile_expands_applies_and_detects_manual_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_home = Path(temporary)
            document = build_profile("local-only", actor="tester")
            self.assertEqual(set(document["agents"]), set(AGENTS))
            self.assertTrue(
                all(
                    binding["primary"] == LOCAL_MODEL
                    for binding in document["agents"].values()
                )
            )
            save_routing(document, config_home)
            apply_routing(
                actor="tester",
                config_home=config_home,
                available_models={LOCAL_MODEL},
            )
            self.assertEqual(
                load_applied_routing(config_home)["routing"], document
            )
            self.assertTrue(routing_status(config_home)["applied"])

            source = config_home / "model-routing.json"
            changed = json.loads(source.read_text(encoding="utf-8"))
            changed["updated_by"] = "manual-edit"
            source.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ModelRoutingError):
                load_applied_routing(config_home)

    def test_every_agent_accepts_a_user_selected_cloud_primary(self):
        with tempfile.TemporaryDirectory() as temporary:
            document = build_profile("local-only", actor="tester")
            save_routing(document, temporary)
            cloud_model = "cloud-provider/strong-model"
            for agent in AGENTS:
                document = set_primary(
                    agent,
                    cloud_model,
                    actor="tester",
                    config_home=temporary,
                )
            self.assertEqual(
                validate_routing_document(
                    document,
                    available_models={LOCAL_MODEL, cloud_model},
                ),
                [],
            )

    def test_cross_zone_fallback_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as temporary:
            document = build_profile("local-only", actor="tester")
            save_routing(document, temporary)
            with self.assertRaises(ModelPolicyError):
                set_fallback(
                    "bx-plan",
                    "cloud-provider/strong-model",
                    actor="tester",
                    confirm_cross_zone=False,
                    config_home=temporary,
                )
            changed = set_fallback(
                "bx-plan",
                "cloud-provider/strong-model",
                actor="tester",
                confirm_cross_zone=True,
                config_home=temporary,
            )
            self.assertEqual(
                validate_routing_document(
                    changed,
                    available_models={LOCAL_MODEL, "cloud-provider/strong-model"},
                ),
                [],
            )

    def test_cloud_profiles_require_an_explicit_approved_model(self):
        with self.assertRaises(ModelRoutingError):
            build_profile("hybrid", actor="tester")
        with self.assertRaises(ModelRoutingError):
            build_profile("cloud-strong", actor="tester")


    def test_cloud_strong_profile_assigns_cloud_to_every_agent(self):
        cloud_model = "cloud-provider/strong-model"
        document = build_profile(
            "cloud-strong", actor="tester", cloud_model=cloud_model
        )
        for binding in document["agents"].values():
            self.assertEqual(binding["primary"], cloud_model)
            self.assertEqual(binding["fallbacks"], [LOCAL_MODEL])

    def test_hybrid_profile_uses_cloud_for_coordination_only(self):
        cloud_model = "cloud-provider/strong-model"
        document = build_profile(
            "hybrid", actor="tester", cloud_model=cloud_model
        )
        for agent, binding in document["agents"].items():
            if agent in {"bx-director", "bx-plan"}:
                self.assertEqual(binding["primary"], cloud_model)
                self.assertEqual(binding["fallbacks"], [LOCAL_MODEL])
            else:
                self.assertEqual(binding["primary"], LOCAL_MODEL)
                self.assertEqual(binding["fallbacks"], [])

    def test_cli_applies_a_cloud_binding_for_bx_code(self):
        cloud_model = "cloud-provider/strong-model"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_home = root / "biexce"
            opencode_root = root / "opencode"
            opencode_root.mkdir()
            (opencode_root / "opencode.json").write_text(
                json.dumps(
                    {
                        "provider": {
                            "biexce-local": {
                                "models": {
                                    LOCAL_MODEL.split("/", 1)[1]: {},
                                }
                            },
                            "cloud-provider": {
                                "models": {"strong-model": {}},
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            cli = REPOSITORY_ROOT / "scripts" / "biexce.py"
            common = [sys.executable, "-B", str(cli), "model"]
            environment = os.environ.copy()
            environment["PATH"] = ""
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["USERNAME"] = "tester"

            def run(*arguments):
                return subprocess.run(
                    [
                        *common,
                        *arguments,
                        "--config-home",
                        str(config_home),
                        "--opencode-config-dir",
                        str(opencode_root),
                        "--json",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env=environment,
                    check=False,
                )

            setup = run("setup", "--profile", "local-only", "--yes")
            self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
            set_cloud = run("set", "bx-code", cloud_model)
            self.assertEqual(set_cloud.returncode, 0, set_cloud.stdout + set_cloud.stderr)
            validate = run("validate")
            self.assertEqual(validate.returncode, 0, validate.stdout + validate.stderr)
            apply = run("apply")
            self.assertEqual(apply.returncode, 0, apply.stdout + apply.stderr)
            status = run("status", "--all")
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            status_payload = json.loads(status.stdout)
            self.assertEqual(
                status_payload["agents"]["bx-code"]["primary"],
                cloud_model,
            )
            native_config = json.loads(
                (opencode_root / "opencode.json").read_text(encoding="utf-8")
            )
            for agent in AGENTS:
                self.assertIn(agent, native_config["agent"])
                self.assertEqual(
                    native_config["agent"][agent]["model"],
                    status_payload["agents"][agent]["primary"],
                )

    def test_quick_setup_applies_default_and_per_agent_override(self):
        default_model = "cloud-provider/strong-model"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_home = root / "biexce"
            opencode_root = root / "opencode"
            opencode_root.mkdir()
            (opencode_root / "opencode.json").write_text(
                json.dumps(
                    {
                        "provider": {
                            "biexce-local": {
                                "models": {LOCAL_MODEL.split("/", 1)[1]: {}},
                            },
                            "cloud-provider": {"models": {"strong-model": {}}},
                        }
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(REPOSITORY_ROOT / "scripts" / "biexce.py"),
                    "setup",
                    "--model",
                    default_model,
                    "--agent",
                    f"bx-code={LOCAL_MODEL}",
                    "--yes",
                    "--config-home",
                    str(config_home),
                    "--opencode-config-dir",
                    str(opencode_root),
                    "--json",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**os.environ, "PATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            bindings = {item["agent"]: item["primary"] for item in payload["bindings"]}
            self.assertEqual(bindings["bx-code"], LOCAL_MODEL)
            self.assertTrue(
                all(
                    model == default_model
                    for agent, model in bindings.items()
                    if agent != "bx-code"
                )
            )

    def test_unauthenticated_catalog_model_warns_without_blocking_cli(self):
        cloud_model = "opencode/free-model"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_home = root / "biexce"
            opencode_root = root / "opencode"
            (opencode_root / "plugins").mkdir(parents=True)
            (opencode_root / "plugins" / "biexce-control.js").write_text(
                "export default {};\n", encoding="utf-8"
            )
            (opencode_root / "opencode.json").write_text(
                json.dumps(
                    {
                        "provider": {
                            "opencode": {"models": {"free-model": {}}},
                        }
                    }
                ),
                encoding="utf-8",
            )
            environment = {
                **os.environ,
                "PATH": "",
                "PYTHONDONTWRITEBYTECODE": "1",
                "BIEXCE_OPENCODE_AUTH_FILE": str(root / "missing-auth.json"),
            }
            cli = REPOSITORY_ROOT / "scripts" / "biexce.py"

            def run(*arguments):
                return subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(cli),
                        *arguments,
                        "--config-home",
                        str(config_home),
                        "--opencode-config-dir",
                        str(opencode_root),
                        "--json",
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env=environment,
                    check=False,
                )

            setup = run("setup", "--model", cloud_model, "--yes")
            self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
            self.assertIn("NOT AUTHENTICATED", setup.stdout)

            model_list = run("model", "list")
            self.assertEqual(
                model_list.returncode, 0, model_list.stdout + model_list.stderr
            )
            model_list_payload = json.loads(model_list.stdout)
            self.assertEqual(
                model_list_payload["model_readiness"][0],
                {
                    "id": cloud_model,
                    "provider": "opencode",
                    "catalog_status": "DISCOVERED",
                    "credential_status": "NOT AUTHENTICATED",
                    "inference_status": "NOT VERIFIED",
                },
            )

            validate = run("model", "validate")
            self.assertEqual(validate.returncode, 0, validate.stdout + validate.stderr)
            validate_payload = json.loads(validate.stdout)
            self.assertTrue(validate_payload["ok"])
            self.assertEqual(
                validate_payload["providers"][0]["status"],
                "NOT AUTHENTICATED",
            )

            status = run("status", "--project", str(root))
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertEqual(
                json.loads(status.stdout)["providers"][0]["status"],
                "NOT AUTHENTICATED",
            )

            doctor = run("doctor")
            self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
            self.assertEqual(
                json.loads(doctor.stdout)["providers"][0]["status"],
                "NOT AUTHENTICATED",
            )

if __name__ == "__main__":
    unittest.main()
