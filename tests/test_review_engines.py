from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


def write_geography_project_artifacts(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text(
        "Study wheat yield response using NDVI time-series indicators, temperature proxies, and spatial zoning.\n",
        encoding="utf-8",
    )
    (project_path / "references" / "literature_review_notes.html").write_text(
        "<p>Remote sensing crop-yield studies commonly check spatial autocorrelation, phenology windows, and spatial validation.</p>",
        encoding="utf-8",
    )
    (project_path / "data" / "data_writing_context.json").write_text(
        json.dumps({
            "narrative_summary": "The project uses NDVI, wheat yield, air temperature proxy, and regional zoning variables.",
            "candidate_variables": ["ndvi", "yield", "air_temperature_proxy", "region", "year"],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "methods" / "method_requirements.json").write_text(
        json.dumps({
            "primary_metric": "r2",
            "method_families": ["correlation_analysis", "regression_model"],
            "user_method": "Use remote-sensing regression and spatial stratification.",
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "results" / "result_validity_report.json").write_text(
        json.dumps({
            "decision": "revise_required",
            "primary_metric": "r2",
            "metric_semantics": "goodness_of_fit",
            "observed_value": 0.085081,
            "evidence_strength": "very_weak_fit",
            "failure_causes": ["data", "method"],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "results" / "figure_metadata.json").write_text(
        json.dumps({
            "figures": [
                {
                    "figure_id": "environmental_driver_response",
                    "title": "Environmental driver response",
                    "figure_type": "scatter_regression",
                    "variables": {"x": "air_temperature_proxy", "y": "yield"},
                    "statistics": {"pearson_r": -0.2304975730964553, "r2": 0.05312913120335572},
                    "interpretation_summary": "Weak negative environmental response.",
                }
            ]
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "results" / "results.tex").write_text(
        "\\section{Results}\nThe environmental driver response had r=-0.230 and R2=0.0531.\n",
        encoding="utf-8",
    )
    (project_path / "journal_profile" / "journal_profile.json").write_text(
        json.dumps({"target_journal": "Remote Sensing", "field": "remote sensing geography"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_astronomy_project_artifacts(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text(
        "Classify X-ray flaring sources using light curve variability, catalog labels, spectral hardness, and multiwavelength features.\n",
        encoding="utf-8",
    )
    (project_path / "data" / "data_writing_context.json").write_text(
        json.dumps({
            "narrative_summary": "The project uses X-ray light curves, source catalogs, spectral hardness, and photometric cross-match metadata.",
            "candidate_variables": ["source_id", "ra", "dec", "flare_rate", "hardness_ratio", "source_class"],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "methods" / "method_requirements.json").write_text(
        json.dumps({
            "method_families": ["source_classification", "time_series_features", "machine_learning"],
            "user_method": "Use a classifier for astronomical source classification with light-curve and catalog features.",
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_machine_learning_project_artifacts(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text(
        "Develop a machine learning classification model with random forest and transformer baselines for tabular prediction.\n",
        encoding="utf-8",
    )
    (project_path / "methods" / "method_requirements.json").write_text(
        json.dumps({
            "method_families": ["classification", "random_forest", "transformer"],
            "primary_metric": "macro_f1",
            "user_method": "Compare deep learning and random forest classifiers with ablation and robust validation.",
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "results" / "result_validity_report.json").write_text(
        json.dumps({"decision": "conditional_pass", "primary_metric": "macro_f1"}, ensure_ascii=False),
        encoding="utf-8",
    )


class ReviewEngineTests(unittest.TestCase):
    def test_geography_engine_discovers_spatial_remote_sensing_review_gaps(self) -> None:
        from draftpaper_cli.review_engines import discover_review_workflow_gaps, propose_review_engineering_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Exploratory analysis of NDVI time-series indicators and wheat yield zoning.",
                field="geography remote sensing agricultural geography",
                target_journal="Remote Sensing",
            )
            write_geography_project_artifacts(project.path)

            gaps = discover_review_workflow_gaps(project.path)
            plan = propose_review_engineering_plan(project.path)

            self.assertEqual(gaps["discipline_profile"]["discipline"], "geography")
            self.assertEqual(gaps["engine"], "geography")
            codes = {gap["code"] for gap in gaps["missing_review_workflows"]}
            self.assertIn("geography_spatial_scale_alignment", codes)
            self.assertIn("geography_remote_sensing_qc", codes)
            self.assertIn("geography_spatial_autocorrelation", codes)
            self.assertIn("geography_weak_fit_qc", codes)
            self.assertTrue(any(gap["requires_user_confirmation"] for gap in gaps["missing_review_workflows"]))
            self.assertTrue((project.path / "review" / "review_discipline_profile.json").exists())
            self.assertTrue((project.path / "review" / "review_workflow_gap_report.html").exists())

            issue_codes = {issue["code"] for issue in plan["issues"]}
            self.assertIn("geography_remote_sensing_qc", issue_codes)
            self.assertIn("geography_spatial_scale_alignment", issue_codes)
            self.assertGreaterEqual(len(plan["user_confirmation_requests"]), 3)
            self.assertTrue((project.path / "review" / "review_engineering_plan.json").exists())
            self.assertTrue((project.path / "review" / "user_confirmation_requests.json").exists())
            self.assertIn("codex_enhancement_context", plan)

    def test_default_engine_is_used_when_no_discipline_matches(self) -> None:
        from draftpaper_cli.review_engines import discover_review_workflow_gaps

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="A conceptual theory note", field="general social theory")
            (project.path / "results" / "result_validity_report.json").write_text(
                json.dumps({"decision": "conditional_pass"}, ensure_ascii=False),
                encoding="utf-8",
            )

            gaps = discover_review_workflow_gaps(project.path)

            self.assertEqual(gaps["discipline_profile"]["discipline"], "default")
            self.assertEqual(gaps["engine"], "default")
            self.assertTrue({gap["code"] for gap in gaps["missing_review_workflows"]})

    def test_cli_review_engineering_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="NDVI wheat yield mapping with environmental proxies.",
                field="remote sensing geography",
                target_journal="Remote Sensing",
            )
            write_geography_project_artifacts(project.path)

            gap_completed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "discover-review-workflow-gaps", "--project", str(project.path)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(gap_completed.stdout)["discipline_profile"]["discipline"], "geography")

            plan_completed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "propose-review-engineering-plan", "--project", str(project.path)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(plan_completed.stdout)["status"], "review_engineering_plan_written")

    def test_astronomy_engine_is_reserved_and_discovers_domain_gaps(self) -> None:
        from draftpaper_cli.review_engines import discover_review_workflow_gaps

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="X-ray flaring source classification with light curve and catalog data.",
                field="astronomy machine learning astrophysics",
                target_journal="APJS",
            )
            write_astronomy_project_artifacts(project.path)

            gaps = discover_review_workflow_gaps(project.path)

            self.assertEqual(gaps["discipline_profile"]["discipline"], "astronomy")
            self.assertEqual(gaps["engine"], "astronomy")
            self.assertIn("astronomy_machine_learning", gaps["discipline_profile"]["subdisciplines"])
            codes = {gap["code"] for gap in gaps["missing_review_workflows"]}
            self.assertIn("astronomy_catalog_crossmatch_qc", codes)
            self.assertIn("astronomy_time_series_sampling_qc", codes)
            self.assertIn("astronomy_class_imbalance_validation", codes)

    def test_machine_learning_engine_is_reserved_and_discovers_domain_gaps(self) -> None:
        from draftpaper_cli.review_engines import discover_review_workflow_gaps

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Machine learning classification with random forest, transformer, and ablation.",
                field="machine learning",
            )
            write_machine_learning_project_artifacts(project.path)

            gaps = discover_review_workflow_gaps(project.path)

            self.assertEqual(gaps["discipline_profile"]["discipline"], "machine_learning")
            self.assertEqual(gaps["engine"], "machine_learning")
            codes = {gap["code"] for gap in gaps["missing_review_workflows"]}
            self.assertIn("machine_learning_data_leakage_audit", codes)
            self.assertIn("machine_learning_baseline_ablation", codes)
            self.assertIn("machine_learning_validation_split_robustness", codes)


if __name__ == "__main__":
    unittest.main()
