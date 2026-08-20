from __future__ import annotations

import json
import unittest

from support import (
    temporary_directory,
    write_assessment,
    write_junit,
    write_session,
)

from biexce_control.evaluation import collect_evaluation, compare_evaluations


class EvaluationServiceTest(unittest.TestCase):
    def test_collect_writes_private_reproducible_summary(self):
        with temporary_directory() as root:
            project = root / "project"
            project.mkdir()
            result = collect_evaluation(
                project,
                session_exports=[write_session(root / "session.json")],
                junit_reports=[write_junit(root / "junit.xml")],
                assessment_path=write_assessment(root / "assessment.json"),
                output=root / "runs",
                label="backend pilot",
            )
            report = json.loads(
                (root / "runs" / result["run_id"] / "report.json").read_text()
            )

        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(report["project"]["name"], "project")
        self.assertNotIn("Implement fixture", json.dumps(report))
        self.assertEqual(report["workflow"]["models"], [
            "biexce-local/vllm/test-model"
        ])

    def test_compare_promotes_equal_clean_candidate(self):
        with temporary_directory() as root:
            project = root / "project"
            project.mkdir()
            common = {
                "project": project,
                "junit_reports": [write_junit(root / "junit.xml")],
                "assessment_path": write_assessment(root / "assessment.json"),
                "output": root / "runs",
            }
            baseline = collect_evaluation(
                session_exports=[write_session(root / "base.json")],
                label="baseline",
                **common,
            )
            candidate = collect_evaluation(
                session_exports=[write_session(root / "candidate.json")],
                label="candidate",
                **common,
            )
            result = compare_evaluations(
                baseline["run_dir"], candidate["run_dir"]
            )

        self.assertEqual(result["decision"], "PROMOTE")
        self.assertEqual(result["delta"]["score"], 0)


if __name__ == "__main__":
    unittest.main()
