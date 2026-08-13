import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
GLOBAL_ROOT = SOURCE_ROOT / "global"
sys.path.insert(0, str(SOURCE_ROOT))

from biexce_control.fixture import init_fixture  # noqa: E402
from biexce_control.gate0 import (  # noqa: E402
    MatrixCheck,
    _http_failure_detail,
    _local_headers,
    run_gate0_matrix,
)
from biexce_control.model_routing import LOCAL_MODEL, apply_routing, build_profile, save_routing  # noqa: E402


class Gate0MatrixTests(unittest.TestCase):
    def test_http_failure_detail_distinguishes_auth_from_upstream_outage(self):
        self.assertIn("virtual key", _http_failure_detail(401))
        self.assertIn("upstream Bifrost/vLLM", _http_failure_detail(502))
        self.assertNotIn("credential", _http_failure_detail(502))

    def test_local_headers_use_virtual_key_without_logging_or_literals(self):
        with patch.dict(
            "os.environ",
            {"BIEXCE_LOCAL_VIRTUAL_KEY": "test-virtual-key"},
            clear=False,
        ):
            headers = _local_headers(include_content_type=True)
        self.assertEqual(headers["User-Agent"], "BIEXCE-Agent-Harness/0.4")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["x-bf-vk"], "test-virtual-key")

    def test_matrix_separates_local_pass_from_live_infra_blockers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            config = root / "config"
            init_fixture(project)
            routing = build_profile("local-only", actor="tester")
            save_routing(routing, config)
            apply_routing(
                actor="tester",
                config_home=config,
                available_models={LOCAL_MODEL},
            )
            with patch(
                "biexce_control.gate0._opencode_version",
                return_value=MatrixCheck("user-dev", "opencode_1_18", "PASS", "1.18.4"),
            ), patch(
                "biexce_control.gate0._gateway_checks",
                return_value=[MatrixCheck("server", "bifrost_tcp", "PASS", "reachable")],
            ), patch(
                "biexce_control.gate0._inference_check",
                return_value=MatrixCheck("e2e", "gateway_to_model", "PASS", "model ok"),
            ):
                result = run_gate0_matrix(
                    project, config_home=config, opencode_root=GLOBAL_ROOT
                )
            self.assertTrue(result["implementation_ok"])
            self.assertFalse(result["ok"])
            self.assertGreater(result["counts"]["BLOCKED"], 0)
            self.assertNotIn(
                "live_dashboard", {item["name"] for item in result["checks"]}
            )

    def test_live_server_evidence_contract_can_pass_four_server_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            config = root / "config"
            evidence = root / "server-evidence.json"
            init_fixture(project)
            routing = build_profile("local-only", actor="tester")
            save_routing(routing, config)
            apply_routing(actor="tester", config_home=config, available_models={LOCAL_MODEL})
            evidence.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "source": "LIVE",
                        "captured_at_utc": "2026-08-01T00:00:00Z",
                        "checks": {
                            name: {"ok": True, "detail": "verified"}
                            for name in ("vllm", "gpu", "quota", "concurrency")
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "biexce_control.gate0._opencode_version",
                return_value=MatrixCheck("user-dev", "opencode_1_18", "PASS", "1.18.4"),
            ), patch(
                "biexce_control.gate0._gateway_checks",
                return_value=[MatrixCheck("server", "bifrost_tcp", "PASS", "reachable")],
            ), patch(
                "biexce_control.gate0._inference_check",
                return_value=MatrixCheck("e2e", "gateway_to_model", "PASS", "model ok"),
            ):
                result = run_gate0_matrix(
                    project,
                    config_home=config,
                    opencode_root=GLOBAL_ROOT,
                    server_evidence=evidence,
                )
            server = [item for item in result["checks"] if item["layer"] == "server"]
            self.assertTrue(all(item["status"] == "PASS" for item in server))
            self.assertTrue(result["ok"])
            self.assertEqual(result["counts"], {"PASS": 9, "FAIL": 0, "BLOCKED": 0})


if __name__ == "__main__":
    unittest.main()
