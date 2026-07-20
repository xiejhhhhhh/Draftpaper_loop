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
from draftpaper_cli.result_rescue import ResultRescueError, prepare_result_rescue
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
    def _assess_metric_comparison(
        self,
        *,
        metric_name: str,
        baseline: float,
        proposed: float,
        optimization_direction: str = "",
    ) -> tuple[dict, dict]:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea=f"{metric_name} comparison", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "improvement",
                    "claim_text": "The proposed model improves over the baseline.",
                    "metric_dimension": metric_name,
                }]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current"}),
                encoding="utf-8",
            )
            direction = {"optimization_direction": optimization_direction} if optimization_direction else {}
            (project.path / "results" / "resolved_result_evidence.json").write_text(
                json.dumps({
                    "status": "resolved",
                    "run_id": "run-current",
                    "metrics": [
                        {
                            "run_id": "run-current",
                            "split": "test",
                            "model": "baseline",
                            "metric_name": metric_name,
                            "value": baseline,
                            **direction,
                        },
                        {
                            "run_id": "run-current",
                            "split": "test",
                            "model": "proposed",
                            "metric_name": metric_name,
                            "value": proposed,
                            **direction,
                        },
                    ],
                }),
                encoding="utf-8",
            )

            result = assess_result_support(project.path)
            report = json.loads(
                (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
            )
            assessment = next(item for item in report["claim_assessments"] if item["claim_id"] == "improvement")
            return result, assessment

    def test_rmse_improvement_uses_decreasing_direction(self) -> None:
        better_result, better_assessment = self._assess_metric_comparison(
            metric_name="rmse", baseline=0.40, proposed=0.30,
        )
        worse_result, worse_assessment = self._assess_metric_comparison(
            metric_name="rmse", baseline=0.30, proposed=0.40,
        )

        self.assertEqual(better_result["decision"], "pass")
        self.assertEqual(better_assessment["comparison"]["optimization_direction"], "lower_is_better")
        self.assertEqual(worse_result["decision"], "route_decision_required")
        self.assertEqual(worse_assessment["failure_type"], "claim_overreach")

    def test_higher_is_better_registry_accepts_only_increasing_values(self) -> None:
        for metric_name in ("accuracy", "f1", "auc", "precision", "recall", "r2"):
            with self.subTest(metric_name=metric_name, case="better"):
                result, assessment = self._assess_metric_comparison(
                    metric_name=metric_name, baseline=0.70, proposed=0.80,
                )
                self.assertEqual(result["decision"], "pass")
                self.assertEqual(assessment["comparison"]["optimization_direction"], "higher_is_better")
            with self.subTest(metric_name=metric_name, case="worse"):
                result, assessment = self._assess_metric_comparison(
                    metric_name=metric_name, baseline=0.80, proposed=0.70,
                )
                self.assertEqual(result["decision"], "route_decision_required")
                self.assertEqual(assessment["failure_type"], "claim_overreach")

    def test_unknown_metric_direction_does_not_support_improvement_without_contract(self) -> None:
        result, assessment = self._assess_metric_comparison(
            metric_name="custom_utility", baseline=0.20, proposed=0.90,
        )

        self.assertEqual(result["decision"], "route_decision_required")
        self.assertEqual(assessment["support_status"], "partially_supported")
        self.assertEqual(assessment["failure_type"], "unknown_metric_optimization_direction")
        self.assertEqual(assessment["comparison"]["status"], "unknown_optimization_direction")

    def test_explicit_optimization_direction_overrides_registry_and_supports_unknown_metric(self) -> None:
        overridden_result, overridden_assessment = self._assess_metric_comparison(
            metric_name="rmse",
            baseline=0.30,
            proposed=0.40,
            optimization_direction="higher_is_better",
        )
        unknown_result, unknown_assessment = self._assess_metric_comparison(
            metric_name="custom_utility",
            baseline=0.40,
            proposed=0.30,
            optimization_direction="lower_is_better",
        )

        self.assertEqual(overridden_result["decision"], "pass")
        self.assertEqual(overridden_assessment["comparison"]["optimization_direction"], "higher_is_better")
        self.assertEqual(unknown_result["decision"], "pass")
        self.assertEqual(unknown_assessment["comparison"]["optimization_direction"], "lower_is_better")

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
                json.dumps({"status": "success", "run_id": "run-current", "split": "test", "metrics": {"baseline_f1": 0.8205, "transformer_f1": 0.8053}}),
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
            report = json.loads((project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], "dpl.result_support_checkpoint.v3")
            self.assertEqual(len(report["checkpoint_sha256"]), 64)
            self.assertIsInstance(report["input_bindings"], dict)
            self.assertIsInstance(report["signals"], dict)
            self.assertIsNone(report["selected_route"])
            self.assertIsNone(report["route_receipt"])
            for route in report["route_options"]:
                self.assertIn(f"--checkpoint-hash {report['checkpoint_sha256']}", route["current_executable_command"])

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
                json.dumps({"status": "success", "run_id": "run-current", "split": "test", "metrics": {"baseline_f1": 0.8205, "transformer_f1": 0.8053}}),
                encoding="utf-8",
            )

            result = assess_result_support(project.path)

            self.assertEqual(result["decision"], "pass")
            self.assertEqual(result["support_level"], "supported")
            self.assertFalse(result["requires_user_decision"])

    def test_bounded_claim_passes_with_conditional_validity_when_no_claim_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Bounded model comparison", field="machine learning astronomy")
            _write_validity_inputs(project.path)
            (project.path / "results" / "result_validity_report.json").write_text(
                json.dumps({"decision": "conditional_pass", "evidence_strength": "no_threshold_configured"}),
                encoding="utf-8",
            )
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "bounded_comparison",
                    "claim_text": "The models are compared under the declared validation and evidence boundary.",
                    "strength": "moderate",
                }]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
            )

            result = assess_result_support(project.path)

            self.assertEqual(result["decision"], "pass")
            self.assertFalse(result["requires_user_decision"])

    def test_result_support_prefers_run_aware_model_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Resolved comparison", field="machine learning astronomy")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "claim_model_improvement",
                    "claim_text": "The proposed Transformer improves classification performance over baseline methods.",
                    "strength": "strong",
                }]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current", "metrics": {"f1": 0.5}}), encoding="utf-8"
            )
            (project.path / "results" / "resolved_result_evidence.json").write_text(
                json.dumps({"status": "resolved", "run_id": "run-current", "metrics": [
                    {"run_id": "run-current", "split": "test", "model": "logistic_baseline", "metric_name": "f1_macro", "value": 0.8667},
                    {"run_id": "run-current", "split": "test", "model": "transformer_full", "metric_name": "f1_macro", "value": 0.8053},
                ]}),
                encoding="utf-8",
            )

            result = assess_result_support(project.path)
            report = json.loads((project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "route_decision_required")
            self.assertEqual(report["metrics"]["logistic_baseline_f1_macro"], 0.8667)
            self.assertEqual(report["metrics"]["transformer_full_f1_macro"], 0.8053)

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

    def test_pass_checkpoint_blocks_manuscript_after_a_consumed_input_changes(self) -> None:
        from draftpaper_cli.result_support import ResultSupportError, validate_result_support_for_manuscript

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Changed support input", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "bounded",
                    "claim_text": "The current analysis is exploratory.",
                }]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
            )
            assess_result_support(project.path)
            (project.path / "results" / "result_validity_report.json").write_text(
                json.dumps({"decision": "conditional_pass", "evidence_strength": "changed"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ResultSupportError, "inputs changed.*result_validity_report.json"):
                validate_result_support_for_manuscript(project.path)

    def test_pass_checkpoint_blocks_manuscript_when_checkpoint_content_is_tampered(self) -> None:
        from draftpaper_cli.result_support import ResultSupportError, validate_result_support_for_manuscript

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Tampered support checkpoint", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "bounded",
                    "claim_text": "The current analysis is exploratory.",
                }]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
            )
            assess_result_support(project.path)
            checkpoint_path = project.path / "results" / "result_support_checkpoint.json"
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            checkpoint["assessment_support_level"] = "tampered"
            checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

            with self.assertRaisesRegex(ResultSupportError, "content does not match checkpoint_sha256"):
                validate_result_support_for_manuscript(project.path)

    def test_pass_checkpoint_blocks_manuscript_when_results_stage_projection_changes(self) -> None:
        from draftpaper_cli.project_state import update_stage_status
        from draftpaper_cli.result_support import ResultSupportError, validate_result_support_for_manuscript

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Changed Results stage", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "bounded",
                    "claim_text": "The current analysis is exploratory.",
                }]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
            )
            assess_result_support(project.path)
            update_stage_status(project.path, "results", "approved")

            with self.assertRaisesRegex(ResultSupportError, "inputs changed.*project.json"):
                validate_result_support_for_manuscript(project.path)

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
                json.dumps({"status": "success", "run_id": "run-current", "split": "test", "metrics": {"baseline_f1": 0.8205, "transformer_f1": 0.8053}}),
                encoding="utf-8",
            )
            assessed = assess_result_support(project.path)
            manifest_hash = _hash(project.path / "results" / "result_manifest.yaml")
            figure_hash = _hash(project.path / "results" / "figures" / "performance.png")

            handshake = apply_result_downgrade(project.path, reason="test downgrade")
            self.assertEqual(handshake["status"], "checkpoint_hash_required")
            self.assertEqual(handshake["checkpoint_sha256"], assessed["checkpoint_sha256"])
            self.assertIn(f"--checkpoint-hash {assessed['checkpoint_sha256']}", handshake["current_executable_command"])
            result = apply_result_downgrade(
                project.path, reason="test downgrade", checkpoint_hash=assessed["checkpoint_sha256"]
            )

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
            self.assertEqual(support["route_receipt"]["checkpoint_sha256"], assessed["checkpoint_sha256"])
            repeated = apply_result_downgrade(
                project.path, reason="test downgrade", checkpoint_hash=assessed["checkpoint_sha256"]
            )
            self.assertEqual(repeated["status"], "already_applied")
            mixed = prepare_result_rescue(project.path, checkpoint_hash=assessed["checkpoint_sha256"])
            self.assertEqual(mixed["status"], "mixed_route_not_supported")
            self.assertEqual(mixed["selected_route"], "downgrade_research_claim")
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
                json.dumps({"status": "success", "run_id": "run-current", "split": "test", "metrics": {"baseline_f1": 0.8205, "transformer_f1": 0.8053}}),
                encoding="utf-8",
            )
            assessed = assess_result_support(project.path)

            handshake = prepare_result_rescue(project.path)
            self.assertEqual(handshake["status"], "checkpoint_hash_required")
            self.assertIn(f"--checkpoint-hash {assessed['checkpoint_sha256']}", handshake["current_executable_command"])
            result = prepare_result_rescue(project.path, checkpoint_hash=assessed["checkpoint_sha256"])

            self.assertEqual(result["route"], "supplement_data_and_method")
            self.assertTrue((project.path / "review" / "result_rescue_plan.json").exists())
            plan = json.loads((project.path / "review" / "result_rescue_plan.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(plan["method_supplement_tasks"]), 1)
            self.assertGreaterEqual(len(plan["open_source_code_search_tasks"]), 1)
            self.assertEqual(plan["evidence_snapshot_policy"]["route"], "supplement_data_and_method")
            support = json.loads((project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(support["decision"], "supplement_prepared")
            self.assertEqual(support["selected_route"], "supplement_data_and_method")
            self.assertEqual(support["route_receipt"]["checkpoint_sha256"], assessed["checkpoint_sha256"])
            repeated = prepare_result_rescue(project.path, checkpoint_hash=assessed["checkpoint_sha256"])
            self.assertEqual(repeated["status"], "already_applied")
            state = load_project(project.path)
            for stage in ["data", "method_plan", "figure_plan", "code", "methods", "result_validity", "core_evidence", "results"]:
                self.assertTrue(state.metadata["stages"][stage].get("stale"), stage)

    def test_route_rejects_a_non_current_checkpoint_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Hash-bound route", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "claim_model_improvement",
                    "claim_text": "The proposed model improves performance over baseline methods.",
                    "strength": "strong",
                }]}), encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current", "split": "test", "metrics": {"baseline_f1": 0.8, "model_f1": 0.7}}),
                encoding="utf-8",
            )
            assess_result_support(project.path)

            with self.assertRaises(ResultRescueError):
                prepare_result_rescue(project.path, checkpoint_hash="0" * 64)

    def test_post_results_reopen_stays_requested_and_blocks_until_review_evidence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Post Results evidence reopen", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "bounded_claim",
                    "claim_text": "The analysis is descriptive within the current evidence boundary.",
                    "strength": "exploratory",
                }]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
            )
            results_path = project.path / "results" / "results.tex"
            results_path.write_text("Current Results.\n", encoding="utf-8")
            trace_path = project.path / "results" / "figure_plugin_trace_report.json"
            trace_path.write_text(json.dumps({"decision": "pass", "figure_checks": []}), encoding="utf-8")
            snapshot_path = project.path / "results" / "promoted_evidence_snapshot.json"
            snapshot_path.write_text(json.dumps({"snapshot_id": "snapshot-current"}), encoding="utf-8")
            manifest_path = project.path / "results" / "result_manifest.yaml"
            review_path = project.path / "review" / "result_discipline_review_report.json"
            review_path.write_text(json.dumps({
                "generated_at": "2026-01-01T00:00:00Z",
                "decision": "repair_required",
                "figure_publication_quality": {"decision": "repair_required"},
            }), encoding="utf-8")
            request_path = project.path / "review" / "result_support_reopen_request.json"
            request_path.write_text(json.dumps({
                "status": "requested",
                "generated_at": "2026-01-02T00:00:00Z",
                "evidence_failure_reasons": ["figure evidence failed"],
                "result_discipline_review": "review/result_discipline_review_report.json",
                "result_discipline_review_sha256": _hash(review_path),
            }), encoding="utf-8")

            first = assess_result_support(project.path)
            first_report = json.loads(
                (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
            )
            pending_request = json.loads(request_path.read_text(encoding="utf-8"))

            self.assertEqual(first["decision"], "route_decision_required")
            self.assertEqual(pending_request["status"], "requested")
            self.assertTrue(any(
                item["failure_type"] == "post_results_evidence_reopen_pending"
                for item in first_report["claim_assessments"]
            ))
            self.assertIn("review/result_support_reopen_request.json", first_report["input_bindings"])
            self.assertIn("review/result_discipline_review_report.json", first_report["input_bindings"])

            review_path.write_text(json.dumps({
                "generated_at": "2026-01-03T00:00:00Z",
                "decision": "pass",
                "figure_publication_quality": {"decision": "pass"},
                "review_rule_gate": {"decision": "pass"},
                "results_sha256": _hash(results_path),
                "evidence_snapshot_id": "snapshot-current",
                "promoted_evidence_snapshot_sha256": _hash(snapshot_path),
                "result_manifest_sha256": _hash(manifest_path),
                "figure_plugin_trace_sha256": _hash(trace_path),
                "evidence_bindings": {
                    "results/results.tex": _hash(results_path),
                    "results/promoted_evidence_snapshot.json": _hash(snapshot_path),
                    "results/result_manifest.yaml": _hash(manifest_path),
                    "results/figure_plugin_trace_report.json": _hash(trace_path),
                },
            }), encoding="utf-8")
            second = assess_result_support(project.path)
            resolved_request = json.loads(request_path.read_text(encoding="utf-8"))

            self.assertEqual(second["decision"], "pass")
            self.assertEqual(resolved_request["status"], "resolved")
            self.assertEqual(resolved_request["resolved_review_sha256"], _hash(review_path))

    def test_post_results_reopen_rejects_unchanged_passing_review_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Unchanged passing review", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{"claim_id": "bounded", "claim_text": "The analysis is exploratory."}]}),
                encoding="utf-8",
            )
            review_path = project.path / "review" / "result_discipline_review_report.json"
            review_path.write_text(json.dumps({
                "generated_at": "2026-01-03T00:00:00Z",
                "decision": "pass",
                "figure_publication_quality": {"decision": "pass"},
                "review_rule_gate": {"decision": "pass"},
            }), encoding="utf-8")
            request_path = project.path / "review" / "result_support_reopen_request.json"
            request_path.write_text(json.dumps({
                "status": "requested",
                "generated_at": "2026-01-02T00:00:00Z",
                "result_discipline_review_sha256": _hash(review_path),
            }), encoding="utf-8")

            result = assess_result_support(project.path)

            self.assertEqual(result["decision"], "route_decision_required")
            self.assertEqual(json.loads(request_path.read_text(encoding="utf-8"))["status"], "requested")

    def test_post_results_reopen_rejects_fresh_passing_review_without_current_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Unbound passing review", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{"claim_id": "bounded", "claim_text": "The analysis is exploratory."}]}),
                encoding="utf-8",
            )
            review_path = project.path / "review" / "result_discipline_review_report.json"
            request_path = project.path / "review" / "result_support_reopen_request.json"
            request_path.write_text(json.dumps({
                "status": "requested",
                "generated_at": "2026-01-02T00:00:00Z",
                "result_discipline_review_sha256": "0" * 64,
            }), encoding="utf-8")
            review_path.write_text(json.dumps({
                "generated_at": "2026-01-03T00:00:00Z",
                "decision": "pass",
                "figure_publication_quality": {"decision": "pass"},
                "review_rule_gate": {"decision": "pass"},
            }), encoding="utf-8")

            result = assess_result_support(project.path)

            self.assertEqual(result["decision"], "route_decision_required")
            self.assertEqual(json.loads(request_path.read_text(encoding="utf-8"))["status"], "requested")

    def test_preclosed_stale_unbound_reopen_request_is_rederived_as_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Preclosed stale reopen", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{"claim_id": "bounded", "claim_text": "The analysis is exploratory."}]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
            )
            review_path = project.path / "review" / "result_discipline_review_report.json"
            review_path.write_text(json.dumps({
                "generated_at": "2026-01-01T00:00:00Z",
                "decision": "pass",
                "figure_publication_quality": {"decision": "pass"},
                "review_rule_gate": {"decision": "pass"},
            }), encoding="utf-8")
            request_path = project.path / "review" / "result_support_reopen_request.json"
            request_path.write_text(json.dumps({
                "status": "resolved",
                "generated_at": "2026-01-02T00:00:00Z",
                "result_discipline_review_sha256": _hash(review_path),
                "resolved_review_sha256": _hash(review_path),
            }), encoding="utf-8")

            result = assess_result_support(project.path)
            report = json.loads(
                (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
            )
            request = json.loads(request_path.read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "route_decision_required")
            self.assertEqual(request["status"], "requested")
            assessment = next(
                item for item in report["claim_assessments"]
                if item["failure_type"] == "post_results_evidence_reopen_pending"
            )
            self.assertIn("review_hash_not_fresh", assessment["diagnosis"]["blocking_reasons"])
            self.assertIn("review_not_generated_after_request", assessment["diagnosis"]["blocking_reasons"])
            self.assertTrue(any(
                reason.startswith("current_binding_missing:")
                for reason in assessment["diagnosis"]["blocking_reasons"]
            ))

    def test_comparative_claim_without_same_dimension_pair_is_partial_never_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Incompatible comparison", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "claim_model_improvement",
                    "claim_text": "The proposed model performs better than the baseline.",
                    "strength": "strong",
                }]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "run_id": "run-current",
                    "metrics": {"baseline_accuracy": 0.60, "proposed_f1": 0.90},
                }),
                encoding="utf-8",
            )

            result = assess_result_support(project.path)
            report = json.loads(
                (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["decision"], "route_decision_required")
            self.assertEqual(result["support_level"], "partial")
            assessment = next(item for item in report["claim_assessments"] if item["claim_id"] == "claim_model_improvement")
            self.assertEqual(assessment["support_status"], "partially_supported")
            self.assertEqual(assessment["failure_type"], "missing_compatible_comparison_evidence")

    def test_missing_claim_contract_evidence_role_has_evidence_named_route_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Evidence-role Result Support gate", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(json.dumps({
                "claims": [{
                    "claim_id": "bounded",
                    "claim_text": "The analysis is exploratory.",
                    "required_evidence_roles": ["performance_metric"],
                }],
            }), encoding="utf-8")

            result = assess_result_support(project.path)
            report = json.loads(
                (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["decision"], "route_decision_required")
            assessment = next(
                item for item in report["claim_assessments"]
                if item["failure_type"] == "unbound_required_evidence_task"
            )
            self.assertEqual(assessment["claim_id"], "unbound_required_evidence_task:performance_metric")
            self.assertIn("Required evidence role performance_metric", assessment["planned_claim"])

    def test_explicit_metric_dimension_precedes_metric_name_inference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Explicit comparison dimension", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(json.dumps({
                "claims": [{"claim_id": "improvement", "claim_text": "The proposed model improves over baseline."}],
            }), encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
            )
            (project.path / "results" / "resolved_result_evidence.json").write_text(json.dumps({
                "status": "resolved",
                "run_id": "run-current",
                "metrics": [
                    {
                        "run_id": "run-current", "model": "baseline", "metric_name": "auc",
                        "metric_dimension": "f1", "split": "test", "value": 0.70,
                    },
                    {
                        "run_id": "run-current", "model": "proposed", "metric_name": "f1",
                        "metric_dimension": "f1", "split": "test", "value": 0.80,
                    },
                ],
            }), encoding="utf-8")

            result = assess_result_support(project.path)

            self.assertEqual(result["decision"], "pass")

    def test_runless_comparative_metrics_are_not_scientific_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Runless comparison", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(json.dumps({
                "claims": [{"claim_id": "improvement", "claim_text": "The proposed model improves over baseline."}],
            }), encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(json.dumps({
                "status": "success",
                "split": "test",
                "metrics": {"baseline_f1": 0.70, "proposed_f1": 0.90},
            }), encoding="utf-8")

            result = assess_result_support(project.path)
            report = json.loads(
                (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
            )

            assessment = next(item for item in report["claim_assessments"] if item["claim_id"] == "improvement")
            self.assertEqual(result["decision"], "route_decision_required")
            self.assertEqual(report["metrics"], {})
            self.assertEqual(assessment["failure_type"], "missing_compatible_comparison_evidence")
            self.assertTrue(any(
                item["failure_type"] == "selected_run_id_missing"
                for item in report["claim_assessments"]
            ))

    def test_noncomparative_claim_cannot_pass_without_a_selected_run(self) -> None:
        for manifest_payload in (None, {"status": "failed", "run_id": "run-failed"}):
            with self.subTest(manifest_payload=manifest_payload), tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea="Run required for bounded claim", field="machine learning")
                _write_validity_inputs(project.path)
                (project.path / "research_plan" / "claim_contract.json").write_text(json.dumps({
                    "claims": [{
                        "claim_id": "bounded",
                        "claim_text": "The current analysis is exploratory.",
                        "strength": "exploratory",
                    }],
                }), encoding="utf-8")
                manifest = project.path / "methods" / "run_manifest.yaml"
                if manifest_payload is None:
                    manifest.unlink(missing_ok=True)
                else:
                    manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")

                result = assess_result_support(project.path)
                report = json.loads(
                    (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
                )

                self.assertEqual(result["decision"], "route_decision_required")
                self.assertTrue(any(
                    item["failure_type"] == "selected_run_id_missing"
                    for item in report["claim_assessments"]
                ))

    def test_comparative_metrics_with_empty_scientific_context_do_not_form_a_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Contextless comparison", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(json.dumps({
                "claims": [{"claim_id": "improvement", "claim_text": "The proposed model improves over baseline."}],
            }), encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(json.dumps({
                "status": "success",
                "run_id": "run-current",
                "metrics": {"baseline_f1": 0.70, "proposed_f1": 0.90},
            }), encoding="utf-8")

            result = assess_result_support(project.path)
            report = json.loads(
                (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
            )

            assessment = next(item for item in report["claim_assessments"] if item["claim_id"] == "improvement")
            self.assertEqual(result["decision"], "route_decision_required")
            self.assertEqual(assessment["failure_type"], "missing_compatible_comparison_evidence")

    def test_comparative_metrics_must_match_declared_claim_context(self) -> None:
        context_cases = {
            "cohort": ("cohort-required", "cohort-other"),
            "split": ("test", "validation"),
            "sample_unit": ("patient", "visit"),
        }
        for field, (required_value, observed_value) in context_cases.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea=f"Claim context {field}", field="machine learning")
                _write_validity_inputs(project.path)
                (project.path / "research_plan" / "claim_contract.json").write_text(json.dumps({
                    "claims": [{
                        "claim_id": "improvement",
                        "claim_text": "The proposed model improves over baseline.",
                        "evidence_context": {field: required_value},
                    }],
                }), encoding="utf-8")
                common_context = {
                    "run_id": "run-current",
                    "cohort": "cohort-a",
                    "split": "test",
                    "sample_unit": "patient",
                    field: observed_value,
                }
                (project.path / "methods" / "run_manifest.yaml").write_text(
                    json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
                )
                (project.path / "results" / "resolved_result_evidence.json").write_text(json.dumps({
                    "status": "resolved",
                    "run_id": "run-current",
                    "metrics": [
                        {**common_context, "model": "baseline", "metric_name": "f1", "value": 0.70},
                        {**common_context, "model": "proposed", "metric_name": "f1", "value": 0.90},
                    ],
                }), encoding="utf-8")

                result = assess_result_support(project.path)
                report = json.loads(
                    (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
                )

                assessment = next(item for item in report["claim_assessments"] if item["claim_id"] == "improvement")
                self.assertEqual(result["decision"], "route_decision_required")
                self.assertEqual(assessment["failure_type"], "missing_compatible_comparison_evidence")

    def test_comparative_claim_requires_matching_metric_context(self) -> None:
        context_cases = {
            "cohort": ({"cohort": "cohort-a"}, {"cohort": "cohort-b"}),
            "split": ({"split": "validation"}, {"split": "test"}),
            "sample_unit": ({"sample_unit": "patient"}, {"sample_unit": "visit"}),
            "run_id": ({"run_id": "run-current"}, {"run_id": "run-old"}),
        }
        for field, (baseline_context, proposed_context) in context_cases.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea=f"Mismatched {field}", field="machine learning")
                _write_validity_inputs(project.path)
                (project.path / "research_plan" / "claim_contract.json").write_text(json.dumps({
                    "claims": [{"claim_id": "improvement", "claim_text": "The proposed model improves over baseline."}],
                }), encoding="utf-8")
                (project.path / "methods" / "run_manifest.yaml").write_text(
                    json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
                )
                baseline = {
                    "run_id": "run-current", "model": "baseline", "metric_name": "f1", "value": 0.70,
                    **baseline_context,
                }
                proposed = {
                    "run_id": "run-current", "model": "proposed", "metric_name": "f1", "value": 0.90,
                    **proposed_context,
                }
                (project.path / "results" / "resolved_result_evidence.json").write_text(json.dumps({
                    "status": "resolved", "run_id": "run-current", "metrics": [baseline, proposed],
                }), encoding="utf-8")

                result = assess_result_support(project.path)
                report = json.loads(
                    (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
                )

                assessment = next(item for item in report["claim_assessments"] if item["claim_id"] == "improvement")
                self.assertEqual(result["decision"], "route_decision_required")
                self.assertEqual(assessment["support_status"], "partially_supported")
                self.assertEqual(assessment["failure_type"], "missing_compatible_comparison_evidence")

    def test_current_evidence_review_failure_blocks_even_if_reopen_request_was_preclosed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Current review failure", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "bounded_claim",
                    "claim_text": "The current analysis is exploratory.",
                    "strength": "exploratory",
                }]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
            )
            review_path = project.path / "review" / "result_discipline_review_report.json"
            review_path.write_text(json.dumps({
                "decision": "repair_required",
                "figure_publication_quality": {"decision": "repair_required"},
                "result_support_reopen_request": "review/result_support_reopen_request.json",
            }), encoding="utf-8")
            (project.path / "review" / "result_support_reopen_request.json").write_text(
                json.dumps({
                    "status": "resolved",
                    "result_discipline_review_sha256": _hash(review_path),
                }),
                encoding="utf-8",
            )

            result = assess_result_support(project.path)
            report = json.loads(
                (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["decision"], "route_decision_required")
            assessment = next(
                item for item in report["claim_assessments"]
                if item["failure_type"] == "post_results_evidence_reopen_pending"
            )
            self.assertEqual(assessment["diagnosis"]["review_sha256"], _hash(review_path))

    def test_checkpoint_preserves_structured_skipped_tasks_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Visible skipped tasks", field="machine learning")
            _write_validity_inputs(project.path)
            (project.path / "research_plan" / "claim_contract.json").write_text(
                json.dumps({"claims": [{
                    "claim_id": "exploratory",
                    "claim_text": "The current analysis is exploratory.",
                }]}),
                encoding="utf-8",
            )
            run_manifest = project.path / "methods" / "run_manifest.yaml"
            run_manifest.write_text(json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8")
            (project.path / "review" / "actionable_analysis_tasks.json").write_text(
                json.dumps({"tasks": [{
                    "task_id": "optional-task",
                    "status": "pending",
                    "required": False,
                    "current": True,
                    "input_bindings": {"methods/run_manifest.yaml": _hash(run_manifest)},
                }]}),
                encoding="utf-8",
            )

            assess_result_support(project.path)
            report = json.loads(
                (project.path / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
            )

            self.assertEqual(report["skipped_tasks"][0]["task_id"], "optional-task")
            self.assertEqual(report["warnings"][0]["code"], "optional_task_skipped")


if __name__ == "__main__":
    unittest.main()
