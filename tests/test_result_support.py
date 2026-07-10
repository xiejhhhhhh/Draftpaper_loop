# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project
from draftpaper_cli.result_support import assess_result_support
from draftpaper_cli.results import ResultsGateError, write_results


def _write_validity_inputs(project_path) -> None:
    (project_path / "results" / "result_validity_report.json").write_text(
        json.dumps({"decision": "pass", "evidence_strength": "meets_threshold"}),
        encoding="utf-8",
    )
    (project_path / "results" / "result_manifest.yaml").write_text(
        json.dumps({
            "figures": [
                {
                    "id": "main-performance",
                    "path": "results/figures/performance.png",
                    "caption_draft": "Model performance panel.",
                    "result_claim": "The panel summarizes model performance.",
                }
            ],
            "tables": [],
        }),
        encoding="utf-8",
    )
    (project_path / "results" / "figures" / "performance.png").write_bytes(b"fake image")


class ResultSupportCheckpointTests(unittest.TestCase):
    def test_strong_improvement_claim_requires_route_choice_when_baseline_is_higher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Transformer comparison", field="machine learning astronomy")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({
                    "claims": [
                        {
                            "claim_id": "claim_model_improvement",
                            "claim_text": "The proposed Transformer improves classification performance over baseline methods.",
                            "strength": "strong",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "metrics": {"baseline_f1": 0.8205, "transformer_f1": 0.8053}}),
                encoding="utf-8",
            )

            result = assess_result_support(project.path)

            self.assertEqual(result["decision"], "route_decision_required")
            self.assertEqual(result["support_level"], "failed")
            self.assertTrue(result["requires_user_decision"])
            self.assertEqual({route["route"] for route in result["route_options"]}, {"downgrade_research_claim", "supplement_data_and_method"})
            report = json.loads((project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(report["failed_claims"][0]["failure_type"], "claim_overreach")
            state = load_project(project.path)
            self.assertEqual(state.metadata["stages"]["result_support"]["status"], "failed")

    def test_exploratory_claim_passes_when_validity_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Exploratory temporal context", field="machine learning astronomy")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({
                    "claims": [
                        {
                            "claim_id": "claim_exploratory_context",
                            "claim_text": "The current analysis provides exploratory evidence about temporal context under the declared validation setting.",
                            "strength": "exploratory",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "metrics": {"baseline_f1": 0.8205, "transformer_f1": 0.8053}}),
                encoding="utf-8",
            )

            result = assess_result_support(project.path)

            self.assertEqual(result["decision"], "pass")
            self.assertEqual(result["support_level"], "supported")
            self.assertFalse(result["requires_user_decision"])

    def test_write_results_blocks_when_existing_support_checkpoint_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Blocked results", field="machine learning astronomy")
            _write_validity_inputs(project.path)
            (project.path / "results" / "result_support_checkpoint.json").write_text(
                json.dumps({"decision": "route_decision_required", "support_level": "failed"}),
                encoding="utf-8",
            )

            with self.assertRaises(ResultsGateError):
                write_results(project.path)


if __name__ == "__main__":
    unittest.main()
