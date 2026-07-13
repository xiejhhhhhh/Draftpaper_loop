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
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import write_reference_outputs
from draftpaper_cli.result_validity import assess_result_validity


LITERATURE = [
    {
        "title": "X-ray Sources Classification Using Machine Learning",
        "authors": ["A. Zuo"],
        "year": "2024",
        "abstract": "Machine learning classification uses light curve and spectral features for X-ray sources with validation.",
        "publication": "arXiv",
        "citation_count": 10,
        "source": "arxiv",
    }
]


def prepare_project(project_path: Path) -> None:
    write_reference_outputs(project_path, LITERATURE, query="X-ray source classification")
    (project_path / "research_plan" / "research_plan.md").write_text(
        "# Plan\n\nUse supervised X-ray source classification with light curve and spectral features.\n",
        encoding="utf-8",
    )
    rows = "\n".join(f"{i},{i % 2},0.{i % 9}" for i in range(1, 41))
    (project_path / "data" / "raw" / "sample.csv").write_text("id,target,hardness\n" + rows + "\n", encoding="utf-8")
    inventory_data(project_path)
    assess_data_quality(project_path, required_columns=["id", "target", "hardness"])
    assess_data_feasibility(project_path, min_rows=30)


class MethodPlanAndResultValidityTests(unittest.TestCase):
    def test_collect_method_plan_writes_user_and_literature_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="X-ray transient classification", field="machine learning astronomy")
            prepare_project(project.path)

            result = collect_method_plan(
                project.path,
                user_method="Use a multimodal Transformer with light-curve and spectral branches.",
                primary_metric="f1",
                minimum_primary_metric=0.8,
            )

            self.assertEqual(result["status"], "written")
            requirements = json.loads((project.path / "methods" / "method_requirements.json").read_text(encoding="utf-8"))
            self.assertEqual(requirements["method_data_fit"], "proceed")
            self.assertEqual(requirements["primary_metric"], "f1")
            self.assertEqual(requirements["minimum_primary_metric"], 0.8)
            self.assertIn("light_curve", requirements["required_data_features"])
            self.assertGreaterEqual(requirements["literature_method_count"], 1)
            plan = (project.path / "methods" / "method_plan.md").read_text(encoding="utf-8")
            self.assertIn("Literature-Informed Method Synthesis", plan)
            self.assertIn("multimodal Transformer", plan)

    def test_collect_method_plan_prefers_structured_blueprint_over_broad_literature_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Test scientific-image representations with group-aware validation",
                field="astronomy machine learning",
            )
            prepare_project(project.path)
            (project.path / "research_plan" / "method_plan.json").write_text(
                json.dumps(
                    {
                        "method_tasks": [
                            {
                                "method_family": "representation_projection",
                                "method_components": ["target_confounder_diagnostic"],
                                "required_data": ["image_embedding", "independent_target", "confounder_variables"],
                            },
                            {
                                "method_family": "group_aware_validation",
                                "method_components": ["transparent_baseline_comparison"],
                                "required_data": ["group_validation_split", "class_label"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            collect_method_plan(project.path)

            requirements = json.loads(
                (project.path / "methods" / "method_requirements.json").read_text(encoding="utf-8")
            )
            self.assertEqual(requirements["requirement_source"], "research_blueprint")
            self.assertIn("representation_projection", requirements["method_families"])
            self.assertIn("group_aware_validation", requirements["method_families"])
            self.assertIn("image_embedding", requirements["required_data_features"])
            self.assertNotIn("time_series_deep_learning", requirements["method_families"])
            self.assertNotIn("light_curve", requirements["required_data_features"])

    def test_result_validity_blocks_weak_results_and_identifies_backtracking_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Weak result classification", field="machine learning astronomy")
            prepare_project(project.path)
            collect_method_plan(project.path, primary_metric="f1", minimum_primary_metric=0.8)
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.55\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "output_files": ["results/tables/metrics.csv"],
                    "metrics": {"f1": 0.55},
                }),
                encoding="utf-8",
            )

            result = assess_result_validity(project.path)

            self.assertEqual(result["decision"], "revise_required")
            self.assertIn("method", result["failure_causes"])
            report = json.loads((project.path / "results" / "result_validity_report.json").read_text(encoding="utf-8"))
            self.assertIn("Inspect model design", " ".join(report["recommended_actions"]))

    def test_result_validity_does_not_treat_r2_point_05_as_significance_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Weak regression evidence", field="remote sensing agronomy")
            prepare_project(project.path)
            collect_method_plan(project.path, primary_metric="r2", minimum_primary_metric=0.05)
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nr2,0.053129\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "output_files": ["results/tables/metrics.csv"],
                    "metrics": {"r2": 0.053129},
                }),
                encoding="utf-8",
            )

            result = assess_result_validity(project.path)

            self.assertEqual(result["decision"], "revise_required")
            report = json.loads((project.path / "results" / "result_validity_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["metric_semantics"], "goodness_of_fit")
            self.assertEqual(report["evidence_strength"], "very_weak_fit")
            self.assertTrue(any("not a p-value" in issue for issue in report["issues"]))
            self.assertTrue(any("data quality" in action.lower() for action in report["recommended_actions"]))

    def test_result_validity_uses_point_05_as_default_p_value_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Significance test", field="environmental statistics")
            prepare_project(project.path)
            collect_method_plan(project.path, primary_metric="p_value")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\np_value,0.031\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "output_files": ["results/tables/metrics.csv"],
                    "metrics": {"p_value": 0.031},
                }),
                encoding="utf-8",
            )

            result = assess_result_validity(project.path)

            self.assertEqual(result["decision"], "pass")
            report = json.loads((project.path / "results" / "result_validity_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["metric_semantics"], "statistical_significance")
            self.assertEqual(report["minimum_value"], 0.05)
            self.assertEqual(report["evidence_strength"], "statistically_significant")

    def test_result_validity_blocks_failed_figure_contract_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Contracted figure evidence", field="machine learning astronomy")
            prepare_project(project.path)
            collect_method_plan(project.path, primary_metric="f1", minimum_primary_metric=0.8)
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.91\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "output_files": ["results/tables/metrics.csv"], "metrics": {"f1": 0.91}}),
                encoding="utf-8",
            )
            (project.path / "results" / "figure_contracts.json").write_text(
                json.dumps({"status": "written", "contracts": [{
                    "figure_id": "fig_main_1",
                    "figure_role": "main_result",
                    "required_data": ["independent_holdout_cohort"],
                    "expected_finding": "Class-aware performance evidence",
                }]}),
                encoding="utf-8",
            )
            (project.path / "results" / "figure_contract_gate_report.json").write_text(
                json.dumps(
                    {
                        "status": "written",
                        "decision": "blocked",
                        "recommended_next_action": {"command": "repair-figure-data", "reason": "label data missing"},
                    }
                ),
                encoding="utf-8",
            )

            result = assess_result_validity(project.path)

            self.assertEqual(result["decision"], "revise_required")
            report = json.loads((project.path / "results" / "result_validity_report.json").read_text(encoding="utf-8"))
            self.assertIn("figure_contracts", report["failure_causes"])
            self.assertTrue(any("Figure contract gate is blocked" in issue for issue in report["figure_contract_issues"]))
            self.assertTrue(any("repair-figure-data" in action for action in report["recommended_actions"]))

    def test_result_validity_rechecks_rendered_figure_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Semantic figure validity", field="astronomy")
            prepare_project(project.path)
            collect_method_plan(project.path, primary_metric="f1", minimum_primary_metric=0.7)
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            (project.path / "results" / "figures" / "fig_bad_ids.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 256)
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "output_files": ["results/tables/metrics.csv", "results/figures/fig_bad_ids.png"],
                    "figures_generated": ["results/figures/fig_bad_ids.png"],
                    "metrics": {"f1": 0.88},
                }),
                encoding="utf-8",
            )
            (project.path / "results" / "figure_contracts.json").write_text(
                json.dumps({"contracts": [{
                    "figure_id": "fig_bad_ids",
                    "path": "results/figures/fig_bad_ids.png",
                    "scientific_question": "Do temporal features distinguish classes?",
                    "required_variable_roles": ["temporal_feature", "class_label"],
                    "forbidden_variable_roles": ["identifier"],
                    "plot_grammar": "grouped_distribution",
                }]}),
                encoding="utf-8",
            )
            (project.path / "results" / "figure_plan.json").write_text(json.dumps({"figures": []}), encoding="utf-8")
            (project.path / "results" / "storyboard_alignment_report.json").write_text(
                json.dumps({"decision": "pass", "all_storyboard_figures_planned": True}), encoding="utf-8"
            )
            (project.path / "methods" / "method_feasibility_report.json").write_text(json.dumps({"decision": "pass"}), encoding="utf-8")
            (project.path / "data" / "data_role_coverage_report.json").write_text(json.dumps({"available_roles": ["local_data"]}), encoding="utf-8")
            (project.path / "results" / "figure_metadata.json").write_text(
                json.dumps({"figures": [{
                    "figure_id": "fig_bad_ids",
                    "path": "results/figures/fig_bad_ids.png",
                    "x_role": "source_id",
                    "y_role": "obs_id",
                    "plot_grammar": "scatter",
                }]}),
                encoding="utf-8",
            )

            result = assess_result_validity(project.path)

            self.assertEqual(result["decision"], "revise_required")
            report = json.loads((project.path / "results" / "figure_semantic_validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["decision"], "blocked")

    def test_result_validity_uses_run_bound_model_metric_instead_of_manifest_scalar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Run-aware classification", field="machine learning astronomy")
            prepare_project(project.path)
            collect_method_plan(project.path, primary_metric="f1_macro", minimum_primary_metric=0.8)
            (project.path / "results" / "tables" / "metrics.csv").write_text(
                "metric,value\nf1,0.5\n",
                encoding="utf-8",
            )
            (project.path / "results" / "tables" / "verified_models.csv").write_text(
                "model,split,f1_macro\nlogistic_event_static,source_held_out,0.8667\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "run_id": "run-aware-validity",
                        "output_files": [
                            "results/tables/metrics.csv",
                            "results/tables/verified_models.csv",
                        ],
                        "metrics": {"f1": 0.5},
                    }
                ),
                encoding="utf-8",
            )

            result = assess_result_validity(project.path)

            self.assertEqual(result["decision"], "pass")
            report = json.loads((project.path / "results" / "result_validity_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["observed_value"], 0.8667)
            self.assertEqual(report["resolved_run_id"], "run-aware-validity")
            self.assertEqual(report["resolved_metric_source"], "results/tables/verified_models.csv")

    def test_result_validity_treats_f1_and_f1_macro_as_same_metric_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Macro F1 validity", field="machine learning")
            prepare_project(project.path)
            collect_method_plan(project.path, primary_metric="f1")
            (project.path / "results" / "tables" / "verified_models.csv").write_text(
                "run_id,model_id,split,metric,value\nrun-1,proposed_full,test,f1_macro,0.8053\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "run_id": "run-1",
                    "output_files": ["results/tables/verified_models.csv"],
                }),
                encoding="utf-8",
            )

            result = assess_result_validity(project.path)
            report = json.loads((project.path / "results" / "result_validity_report.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "conditional_pass")
            self.assertEqual(report["observed_value"], 0.8053)
            self.assertEqual(report["resolved_run_id"], "run-1")

    def test_cli_collect_method_plan_and_assess_result_validity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI validity", field="workflow engineering")
            prepare_project(project.path)
            refresh_project_passport(project.path, event="test_cli_fixture_prepared")
            collect_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "collect-method-plan",
                    "--project",
                    str(project.path),
                    "--method-note",
                    "Use supervised classification.",
                    "--primary-metric",
                    "f1",
                    "--minimum-primary-metric",
                    "0.7",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(collect_completed.stdout)["status"], "written")

            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "output_files": ["results/tables/metrics.csv"], "metrics": {"f1": 0.88}}),
                encoding="utf-8",
            )
            validity_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "assess-result-validity",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(validity_completed.stdout)["decision"], "pass")


if __name__ == "__main__":
    unittest.main()
