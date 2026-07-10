# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import hashlib
import tempfile
import unittest

from draftpaper_cli.claim_contract import apply_result_downgrade
from draftpaper_cli.orchestrator import run_pipeline, status_project
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project
from draftpaper_cli.result_rescue import prepare_result_rescue
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


def _hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

            status = status_project(project.path)
            self.assertEqual(status["pipeline_state"], "awaiting_result_route")
            self.assertEqual(status["next_action"]["command"], "choose-result-route")
            self.assertEqual(run_pipeline(project.path)["status"], "awaiting_result_route")

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

    def test_apply_result_downgrade_freezes_results_and_only_reopens_manuscript_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Transformer comparison", field="machine learning astronomy")
            _write_validity_inputs(project.path)
            contract_path = project.path / "research_plan" / "claim_contract.json"
            contract_path.write_text(
                json.dumps({
                    "claims": [
                        {
                            "claim_id": "claim_model_improvement",
                            "planned_claim": "The proposed Transformer improves classification performance over baseline methods.",
                            "active_claim": "The proposed Transformer improves classification performance over baseline methods.",
                            "active_strength": "strong",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "metrics": {"baseline_f1": 0.8205, "transformer_f1": 0.8053}}),
                encoding="utf-8",
            )
            assess_result_support(project.path)
            manifest_hash = _hash(project.path / "results" / "result_manifest.yaml")
            figure_hash = _hash(project.path / "results" / "figures" / "performance.png")

            result = apply_result_downgrade(project.path, reason="test downgrade")

            self.assertEqual(result["route"], "downgrade_research_claim")
            self.assertEqual(_hash(project.path / "results" / "result_manifest.yaml"), manifest_hash)
            self.assertEqual(_hash(project.path / "results" / "figures" / "performance.png"), figure_hash)
            freeze = json.loads((project.path / "results" / "result_evidence_freeze.json").read_text(encoding="utf-8"))
            self.assertEqual(freeze["status"], "frozen")
            self.assertTrue((project.path / freeze["versioned_snapshot"]).exists())
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["claims"][0]["active_strength"], "exploratory")
            support = json.loads((project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(support["decision"], "pass")
            self.assertEqual(support["selected_route"], "downgrade_research_claim")
            state = load_project(project.path)
            self.assertFalse(state.metadata["stages"]["data"].get("stale"))
            self.assertFalse(state.metadata["stages"]["methods"].get("stale"))
            self.assertFalse(state.metadata["stages"]["result_validity"].get("stale"))
            self.assertTrue(state.metadata["stages"]["results"].get("stale"))
            self.assertTrue(state.metadata["stages"]["discussion"].get("stale"))

    def test_prepare_result_rescue_generates_supplement_tasks_and_reopens_evidence_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Transformer comparison", field="machine learning astronomy")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({
                    "claims": [
                        {
                            "claim_id": "claim_model_improvement",
                            "planned_claim": "The proposed Transformer improves classification performance over baseline methods.",
                            "active_claim": "The proposed Transformer improves classification performance over baseline methods.",
                            "active_strength": "strong",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "metrics": {"baseline_f1": 0.8205, "transformer_f1": 0.8053}}),
                encoding="utf-8",
            )
            assess_result_support(project.path)

            result = prepare_result_rescue(project.path)

            self.assertEqual(result["route"], "supplement_data_and_method")
            self.assertTrue((project.path / "review" / "result_rescue_plan.json").exists())
            plan = json.loads((project.path / "review" / "result_rescue_plan.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(plan["method_supplement_tasks"]), 1)
            self.assertGreaterEqual(len(plan["open_source_code_search_tasks"]), 1)
            self.assertEqual(plan["evidence_snapshot_policy"]["route"], "supplement_data_and_method")
            support = json.loads((project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(support["decision"], "supplement_prepared")
            self.assertEqual(support["selected_route"], "supplement_data_and_method")
            state = load_project(project.path)
            for stage in ["data", "method_plan", "figure_plan", "code", "methods", "result_validity", "core_evidence", "results"]:
                self.assertTrue(state.metadata["stages"][stage].get("stale"), stage)


if __name__ == "__main__":
    unittest.main()
