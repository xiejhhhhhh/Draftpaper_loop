# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
from draftpaper_cli.discipline_modules.machine_learning import MODULE as MACHINE_LEARNING_MODULE
from draftpaper_cli.method_blueprint import prepare_method_blueprint
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.result_validity import assess_result_validity
from draftpaper_cli.review_rule_runtime import assess_review_rules
from draftpaper_cli.review_rule_runtime import build_review_rule_rescue_tasks
from draftpaper_cli.review_rule_runtime import collect_review_rule_evidence_roles
from draftpaper_cli.review_rule_runtime import review_rule_validation_checks


def _write_ml_project_inputs(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text(
        "# Research Plan\n\nTrain and validate a supervised machine-learning model with baseline checks.\n",
        encoding="utf-8",
    )
    rows = "\n".join(f"s{i},{i % 2},{0.1 * i:.3f},{0.2 * i:.3f}" for i in range(1, 60))
    (project_path / "data" / "processed" / "features.csv").write_text(
        "sample_id,label,feature_1,feature_2\n" + rows + "\n",
        encoding="utf-8",
    )
    inventory_data(project_path)
    assess_data_quality(project_path, required_columns=["label", "feature_1"])
    assess_data_feasibility(project_path, min_rows=30)
    collect_method_plan(
        project_path,
        user_method="Use supervised baseline and ablation comparisons with a held-out split.",
        primary_metric="f1",
        minimum_primary_metric=0.7,
    )


def _write_validity_project_inputs(project_path: Path) -> None:
    (project_path / "methods" / "method_requirements.json").write_text(
        json.dumps({"primary_metric": "f1", "minimum_primary_metric": 0.7}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_path / "methods" / "run_manifest.yaml").write_text(
        json.dumps({"status": "success", "metrics": {"f1": 0.82}, "output_files": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_path / "data" / "data_feasibility_report.json").write_text(
        json.dumps({"decision": "pass"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project_path / "result_validity" / "stage_manifest.json").write_text("{}", encoding="utf-8")


class ReviewRuleRuntimeTests(unittest.TestCase):
    def test_results_review_filters_rules_by_active_figure_plugins(self) -> None:
        matching = {
            "rule_id": "baseline_only_rule",
            "rule_family": "model_validity",
            "applicable_methods": ["baseline_model"],
            "pipeline_hooks": {"assess_result_validity": "required"},
        }
        unrelated = {
            "rule_id": "spatial_only_rule",
            "rule_family": "model_validity",
            "applicable_methods": ["spatial_block_validation"],
            "pipeline_hooks": {"assess_result_validity": "required"},
        }
        MACHINE_LEARNING_MODULE.spec.review_rule_groups.extend([matching, unrelated])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea="Baseline model", field="machine learning")
                report = assess_review_rules(
                    project.path,
                    stage="assess_result_validity",
                    evidence_context={"active_plugin_ids": ["baseline_model"]},
                )
                selected = {item["rule_id"] for item in report["rule_assessments"]}

                self.assertIn("baseline_only_rule", selected)
                self.assertNotIn("spatial_only_rule", selected)
        finally:
            MACHINE_LEARNING_MODULE.spec.review_rule_groups.remove(matching)
            MACHINE_LEARNING_MODULE.spec.review_rule_groups.remove(unrelated)

    def test_fixed_threshold_accepts_schema_authoritative_source_names(self) -> None:
        rule = {
            "rule_id": "discipline_convention_threshold_test",
            "rule_group_id": "discipline_convention_threshold_test",
            "rule_family": "model_validity",
            "evidence_binding": {
                "registry_record_types": ["metric"],
                "required_fields": ["performance_metric"],
                "forbidden_conflicts": [],
            },
            "blocking_level": "block_claim",
            "failure_route": "method_rescue",
            "pipeline_hooks": {"assess_result_validity": "required"},
            "threshold_policy": {"mode": "fixed", "value": 0.8, "comparator": ">="},
            "threshold_source": {"type": "discipline_convention", "citation_or_note": "fixture convention"},
            "maturity": "mature",
            "deployment_state": "promoted_review_rule",
        }
        MACHINE_LEARNING_MODULE.spec.review_rule_groups.append(rule)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea="Threshold source", field="machine learning")
                _write_validity_project_inputs(project.path)

                report = assess_review_rules(project.path, stage="assess_result_validity")
                assessment = next(item for item in report["rule_assessments"] if item["rule_id"] == rule["rule_id"])

                self.assertTrue(assessment["hard_threshold_enabled"])
                self.assertEqual(assessment["decision"], "satisfied")
        finally:
            MACHINE_LEARNING_MODULE.spec.review_rule_groups.remove(rule)

    def test_method_blueprint_includes_runtime_review_rule_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="ML baseline validation", field="machine learning")
            _write_ml_project_inputs(project.path)

            result = prepare_method_blueprint(project.path)

            self.assertEqual(result["status"], "written")
            gate_path = project.path / "methods" / "method_review_rule_gate.json"
            self.assertTrue(gate_path.exists())
            blueprint = json.loads((project.path / "methods" / "method_blueprint.json").read_text(encoding="utf-8"))
            self.assertEqual(blueprint["review_rule_gate_plan"]["stage"], "method_plan")
            self.assertGreaterEqual(blueprint["review_rule_gate_plan"]["selected_rule_count"], 1)
            checks = blueprint["method_code_plan"]["validation_checks"]
            self.assertIn("minimum_r2", checks)
            self.assertEqual(blueprint["method_code_plan"]["review_rule_gate_decision"], "pass")
            self.assertGreaterEqual(blueprint["review_rule_gate_plan"]["advisory_count"], 1)

    def test_result_validity_defers_review_rules_until_post_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="ML result validity", field="machine learning")
            _write_validity_project_inputs(project.path)

            result = assess_result_validity(project.path)

            self.assertIn(result["decision"], {"pass", "conditional_pass"})
            report = json.loads((project.path / "results" / "result_validity_report.json").read_text(encoding="utf-8"))
            self.assertNotIn("review_rule_gate", report)
            self.assertFalse((project.path / "results" / "review_rule_gate_report.json").exists())

    def test_promoted_blocking_review_rule_does_not_block_result_validity(self) -> None:
        rule = {
            "rule_group_id": "external_validation_required_for_strong_claims_test",
            "rule_id": "external_validation_required_for_strong_claims_test",
            "display_name": "External validation required for strong claims",
            "rule_family": "model_validity",
            "checks": ["external_validation_check"],
            "evidence_roles": ["external_validation"],
            "minimum_evidence_required": ["external_validation"],
            "blocking_level": "block_claim",
            "failure_route": "supplement_data_and_method",
            "pipeline_hooks": {"assess_result_validity": "assess-result-validity"},
            "threshold_policy": {"mode": "contextual"},
            "threshold_source": {"type": "discipline_consensus"},
            "maturity": "mature",
            "deployment_state": "promoted_review_rule",
            "human_confirmation_required": False,
        }
        MACHINE_LEARNING_MODULE.spec.review_rule_groups.append(rule)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea="ML strong claim", field="machine learning")
                _write_validity_project_inputs(project.path)

                result = assess_result_validity(project.path)

                self.assertIn(result["decision"], {"pass", "conditional_pass"})
                report = json.loads((project.path / "results" / "result_validity_report.json").read_text(encoding="utf-8"))
                self.assertNotIn("review_rules", report.get("failure_causes") or [])
        finally:
            MACHINE_LEARNING_MODULE.spec.review_rule_groups.remove(rule)

    def test_cli_assess_review_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="ML CLI rule gate", field="machine learning")
            _write_validity_project_inputs(project.path)
            refresh_project_passport(project.path, event="test_fixture_ready")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "assess-review-rules",
                    "--project",
                    str(project.path),
                    "--stage",
                    "assess_result_validity",
                    "--no-write",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["stage"], "assess_result_validity")
            self.assertGreaterEqual(payload["selected_rule_count"], 1)

    def test_review_rule_runtime_reads_simple_yaml_run_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="ML YAML metrics", field="machine learning")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                "status: success\nmetrics:\n  f1: 0.82\n  baseline_f1: 0.71\noutput_files: []\n",
                encoding="utf-8",
            )

            roles = collect_review_rule_evidence_roles(project.path)

            self.assertIn("successful_method_run", roles)
            self.assertIn("performance_metric", roles)
            self.assertIn("baseline_metric", roles)

    def test_evidence_binding_required_fields_are_runtime_evidence_requirements(self) -> None:
        rule = {
            "rule_group_id": "bound_external_validation_gate_test",
            "rule_id": "bound_external_validation_gate_test",
            "display_name": "Bound external validation gate",
            "rule_family": "model_validity",
            "checks": ["external_validation_check"],
            "evidence_roles": [],
            "evidence_binding": {
                "registry_record_types": ["method_output", "metric"],
                "required_fields": ["external_validation"],
                "forbidden_conflicts": [],
            },
            "blocking_level": "block_claim",
            "failure_route": "supplement_data_and_method",
            "pipeline_hooks": {"assess_result_validity": "assess-result-validity"},
            "threshold_policy": {"mode": "contextual"},
            "threshold_source": {"type": "discipline_consensus"},
            "maturity": "mature",
            "deployment_state": "promoted_review_rule",
            "human_confirmation_required": False,
        }
        MACHINE_LEARNING_MODULE.spec.review_rule_groups.append(rule)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea="ML bound rule", field="machine learning")
                _write_validity_project_inputs(project.path)

                report = assess_review_rules(project.path, stage="assess_result_validity")

                assessment = next(item for item in report["rule_assessments"] if item["rule_id"] == "bound_external_validation_gate_test")
                self.assertEqual(assessment["decision"], "blocked_missing_evidence")
                self.assertIn("external_validation", assessment["schema_required_evidence_roles"])
                self.assertIn("external_validation", assessment["missing_evidence_roles"])
                tasks = build_review_rule_rescue_tasks(project.path, report)
                task = next(item for item in tasks if item["rule_id"] == "bound_external_validation_gate_test")
                self.assertEqual(task["task_id"], "review_rule:bound_external_validation_gate_test:missing_evidence")
                self.assertEqual(task["recommended_command"], "prepare-result-rescue")
                self.assertIn("python -m draftpaper_cli.cli prepare-result-rescue", task["recommended_cli"])
        finally:
            MACHINE_LEARNING_MODULE.spec.review_rule_groups.remove(rule)

    def test_forbidden_conflicts_from_evidence_binding_can_block_promoted_rules(self) -> None:
        rule = {
            "rule_group_id": "leakage_conflict_gate_test",
            "rule_id": "leakage_conflict_gate_test",
            "display_name": "Leakage conflict gate",
            "rule_family": "model_validity",
            "checks": ["leakage_check"],
            "evidence_roles": ["performance_metric"],
            "evidence_binding": {
                "registry_record_types": ["method_output", "metric"],
                "required_fields": ["performance_metric"],
                "forbidden_conflicts": ["train_test_leakage"],
            },
            "blocking_level": "block_claim",
            "failure_route": "method_rescue",
            "pipeline_hooks": {"assess_result_validity": "assess-result-validity"},
            "threshold_policy": {"mode": "contextual"},
            "threshold_source": {"type": "discipline_consensus"},
            "maturity": "mature",
            "deployment_state": "promoted_review_rule",
            "human_confirmation_required": False,
        }
        MACHINE_LEARNING_MODULE.spec.review_rule_groups.append(rule)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea="ML leakage conflict", field="machine learning")
                _write_validity_project_inputs(project.path)

                report = assess_review_rules(
                    project.path,
                    stage="assess_result_validity",
                    evidence_context={"observed_conflicts": ["train_test_leakage"]},
                )

                assessment = next(item for item in report["rule_assessments"] if item["rule_id"] == "leakage_conflict_gate_test")
                self.assertEqual(assessment["decision"], "blocked_evidence_conflict")
                self.assertIn("train_test_leakage", assessment["observed_forbidden_conflicts"])
                self.assertIn("review_rule:leakage_conflict_gate_test:resolve train_test_leakage", review_rule_validation_checks(report))
                task = next(item for item in report["rescue_tasks"] if item["rule_id"] == "leakage_conflict_gate_test")
                self.assertEqual(task["task_id"], "review_rule:leakage_conflict_gate_test:forbidden_conflict")
                self.assertEqual(task["recommended_command"], "prepare-method-blueprint")
        finally:
            MACHINE_LEARNING_MODULE.spec.review_rule_groups.remove(rule)

    def test_real_threshold_failure_routes_to_local_results_semantic_repair(self) -> None:
        rule = {
            "rule_id": "minimum_f1_runtime_test", "rule_group_id": "minimum_f1_runtime_test",
            "rule_family": "model_validity", "metric_name": "f1",
            "evidence_binding": {"required_fields": ["performance_metric"], "forbidden_conflicts": []},
            "blocking_level": "block_claim", "failure_route": "method_rescue",
            "pipeline_hooks": {"post_results": "required"},
            "threshold_policy": {"mode": "fixed", "value": 0.8, "comparator": ">="},
            "threshold_source": {"type": "discipline_convention", "citation_or_note": "test convention"},
            "maturity": "mature", "deployment_state": "promoted_review_rule", "human_confirmation_required": False,
        }
        MACHINE_LEARNING_MODULE.spec.review_rule_groups.append(rule)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea="Threshold anomaly", field="machine learning")
                _write_validity_project_inputs(project.path)
                (project.path / "methods" / "run_manifest.yaml").write_text(
                    json.dumps({"status": "success", "run_id": "run-low", "metrics": {"f1": 0.72}}), encoding="utf-8"
                )
                report = assess_review_rules(project.path, stage="post_results")
                assessment = next(item for item in report["rule_assessments"] if item["rule_id"] == rule["rule_id"])
                task = next(item for item in report["rescue_tasks"] if item["rule_id"] == rule["rule_id"])
                self.assertEqual(assessment["decision"], "threshold_failed")
                self.assertEqual(assessment["threshold_evaluation"]["observed"], 0.72)
                self.assertEqual(task["recommended_command"], "prepare-results-semantic-repair")
        finally:
            MACHINE_LEARNING_MODULE.spec.review_rule_groups.remove(rule)

    def test_mixed_metric_dimensions_are_detected_from_evidence_bundle(self) -> None:
        rule = {
            "rule_id": "dimension_consistency_runtime_test", "rule_group_id": "dimension_consistency_runtime_test",
            "rule_family": "model_validity", "evidence_roles": ["performance_metric"],
            "evidence_binding": {"required_fields": ["performance_metric"], "forbidden_conflicts": []},
            "blocking_level": "block_claim", "failure_route": "manuscript_repair",
            "pipeline_hooks": {"post_results": "required"}, "threshold_policy": {"mode": "contextual"},
            "maturity": "mature", "deployment_state": "promoted_review_rule", "human_confirmation_required": False,
        }
        MACHINE_LEARNING_MODULE.spec.review_rule_groups.append(rule)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea="Dimension anomaly", field="machine learning")
                _write_validity_project_inputs(project.path)
                records = []
                for evidence_id, dimension, value in (("f1-score", "score", 0.8), ("f1-count", "count", 8)):
                    records.append({
                        "evidence_id": evidence_id, "entity_role": "result_metric_f1", "metric_name": "f1", "value": value,
                        "metric_dimension": dimension, "run_id": "run-1", "cohort_id": "main", "sample_unit": "source",
                        "split": "held_out", "model_id": "model-1",
                    })
                (project.path / "results" / "resolved_result_evidence.json").write_text(
                    json.dumps({"evidence_records": records}), encoding="utf-8"
                )
                report = assess_review_rules(project.path, stage="post_results")
                assessment = next(item for item in report["rule_assessments"] if item["rule_id"] == rule["rule_id"])
                self.assertEqual(assessment["decision"], "scientific_anomaly")
                self.assertIn("mixed_metric_dimension", {item["code"] for item in assessment["scientific_findings"]})
        finally:
            MACHINE_LEARNING_MODULE.spec.review_rule_groups.remove(rule)


if __name__ == "__main__":
    unittest.main()
