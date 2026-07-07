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
from draftpaper_cli.figure_plan import plan_figures
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.methods import verify_methods
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import write_reference_outputs


def prepare_codegen_project(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text(
        "# Research Plan\n\n"
        "Build an exploratory classifier for X-ray flaring sources using light curves, "
        "spectral hardness, and multiwavelength features.\n",
        encoding="utf-8",
    )
    write_reference_outputs(
        project_path,
        [
            {
                "title": "Transformer classification of variable X-ray sources",
                "authors": ["Smith", "Wang"],
                "year": 2024,
                "publication": "Astrophysical Journal Supplement Series",
                "doi": "10.0000/apjs.2024.001",
                "url": "https://example.org/apjs-transformer",
                "abstract": (
                    "The paper evaluates transformer and temporal convolutional networks "
                    "for light curve classification of variable X-ray sources."
                ),
                "deep_summary": {
                    "methods": (
                        "A supervised multimodal classifier combines light-curve embeddings, "
                        "spectral hardness ratios, and cross-validation metrics."
                    )
                },
                "citation_weight": 0.98,
            }
        ],
    )
    rows = "\n".join(f"{i},{i % 2},{0.1 * i:.2f},{10 + i}" for i in range(1, 41))
    (project_path / "data" / "raw" / "sources.csv").write_text(
        "source_id,target,hardness,flux\n" + rows + "\n",
        encoding="utf-8",
    )
    inventory_data(project_path)
    assess_data_quality(project_path, required_columns=["source_id", "target", "hardness"])
    assess_data_feasibility(project_path, min_rows=30)
    collect_method_plan(
        project_path,
        user_method=(
            "Use 1D CNN, transformer, temporal convolutional network, multimodal fusion, "
            "and contrastive pretraining for source classification."
        ),
        primary_metric="f1",
        minimum_primary_metric=0.6,
    )


def write_storyboard_contract(project_path: Path) -> None:
    storyboard = {
        "status": "written",
        "source": "research_blueprint",
        "figures": [
            {
                "figure_id": "fig_1_workflow",
                "proposed_title": "Time-aware flaring-source classification workflow",
                "research_question": "How does the study connect long-term light curves, current observation tokens, and spectral features?",
                "expected_finding": "The workflow should expose every data-to-model step required for source classification.",
                "scientific_claim_boundary": "Workflow evidence is descriptive and does not itself prove classification performance.",
                "required_data": ["light_curve", "current_observation_tokens", "spectral_features"],
                "required_method": ["data_alignment", "time_aware_transformer"],
                "suggested_plot_type": "data_overview",
                "validation_metric": "pipeline_completeness",
                "supporting_literature_keys": ["Smith2024Transformer1"],
                "downstream_stage_dependency": ["method_plan", "figure_plan", "code"],
                "fallback_if_data_missing": "Use available tabular feature coverage and mark missing modalities.",
            },
            {
                "figure_id": "fig_2_class_support",
                "proposed_title": "Class support and label balance for flaring-source categories",
                "research_question": "Are the available labels sufficient for a supervised classification claim?",
                "expected_finding": "The label distribution should define which classes can support reliable evaluation.",
                "scientific_claim_boundary": "Minority-class claims must remain limited when sample support is low.",
                "required_data": ["class_label"],
                "required_method": ["class_balance_check"],
                "suggested_plot_type": "class_balance",
                "validation_metric": "imbalance_ratio",
                "supporting_literature_keys": ["Smith2024Transformer1"],
                "downstream_stage_dependency": ["figure_plan", "code", "results"],
                "fallback_if_data_missing": "Report unlabeled sample support only.",
            },
            {
                "figure_id": "fig_3_feature_space",
                "proposed_title": "Hardness-flux feature space before sequence modeling",
                "research_question": "Do spectral hardness and flux contain separable source-class structure?",
                "expected_finding": "Feature-space structure should indicate whether tabular spectral information adds useful signal.",
                "scientific_claim_boundary": "Feature separation is exploratory and must be confirmed by validation metrics.",
                "required_data": ["hardness", "flux", "class_label"],
                "required_method": ["feature_space_diagnostic"],
                "suggested_plot_type": "scatter_regression",
                "validation_metric": "class_separation_summary",
                "supporting_literature_keys": ["Smith2024Transformer1"],
                "downstream_stage_dependency": ["figure_plan", "code", "results"],
                "fallback_if_data_missing": "Use the strongest two numeric features available.",
            },
            {
                "figure_id": "fig_4_model_performance",
                "proposed_title": "Baseline versus time-aware model performance",
                "research_question": "Does the time-aware model improve over transparent baselines?",
                "expected_finding": "The proposed model should be interpreted only against baseline and ablation metrics.",
                "scientific_claim_boundary": "Performance claims require verified metrics from local code execution.",
                "required_data": ["features", "class_label"],
                "required_method": ["baseline_model", "time_aware_transformer", "ablation_study"],
                "suggested_plot_type": "metric_summary",
                "validation_metric": "f1",
                "supporting_literature_keys": ["Smith2024Transformer1"],
                "downstream_stage_dependency": ["code", "verify_methods", "result_validity"],
                "fallback_if_data_missing": "Report baseline-only feasibility.",
            },
            {
                "figure_id": "fig_5_error_analysis",
                "proposed_title": "Error structure across confused flaring-source classes",
                "research_question": "Which source classes remain ambiguous after multimodal fusion?",
                "expected_finding": "Residual errors should identify classes requiring additional data or weaker claims.",
                "scientific_claim_boundary": "Error interpretation is conditional on label quality and sample support.",
                "required_data": ["predicted_label", "class_label"],
                "required_method": ["confusion_or_error_analysis"],
                "suggested_plot_type": "metric_summary",
                "validation_metric": "confusion_summary",
                "supporting_literature_keys": ["Smith2024Transformer1"],
                "downstream_stage_dependency": ["code", "results", "discussion"],
                "fallback_if_data_missing": "Use per-class support and metric summary.",
            },
            {
                "figure_id": "fig_6_validation_stability",
                "proposed_title": "Validation stability across held-out flaring-source splits",
                "research_question": "Are model-performance claims stable across the planned validation design?",
                "expected_finding": "The validation view should show whether the main performance pattern is stable enough to support the manuscript claim.",
                "scientific_claim_boundary": "Stability claims remain limited to the available held-out split design and sample support.",
                "required_data": ["features", "class_label"],
                "required_method": ["validation_design", "metric_uncertainty"],
                "suggested_plot_type": "metric_summary",
                "validation_metric": "f1_interval",
                "supporting_literature_keys": ["Smith2024Transformer1"],
                "downstream_stage_dependency": ["code", "verify_methods", "result_validity", "discussion"],
                "fallback_if_data_missing": "Report split-level metric availability and keep claims conditional.",
            },
        ],
        "tables": [
            {
                "table_id": "table_1_dataset",
                "proposed_title": "Dataset, modality, and validation split summary",
                "required_data": ["source_id", "class_label"],
                "required_method": ["data_inventory"],
            }
        ],
    }
    method_plan = {
        "status": "written",
        "source": "research_blueprint",
        "method_tasks": [
            {"task_id": "method_1", "figure_id": "fig_2_class_support", "method_family": "class_balance_check"},
            {"task_id": "method_2", "figure_id": "fig_3_feature_space", "method_family": "feature_space_diagnostic"},
            {"task_id": "method_3", "figure_id": "fig_4_model_performance", "method_family": "baseline_model"},
            {"task_id": "method_4", "figure_id": "fig_5_error_analysis", "method_family": "error_analysis"},
            {"task_id": "method_5", "figure_id": "fig_6_validation_stability", "method_family": "validation_stability"},
        ],
    }
    (project_path / "research_plan").mkdir(parents=True, exist_ok=True)
    (project_path / "research_plan" / "figure_storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")
    (project_path / "research_plan" / "method_plan.json").write_text(json.dumps(method_plan), encoding="utf-8")


def write_passing_figure_contract_gate(project_path: Path) -> None:
    from draftpaper_cli.figure_contract_gate import assess_figure_contracts

    contracts_path = project_path / "results" / "figure_contracts.json"
    contracts = json.loads(contracts_path.read_text(encoding="utf-8")) if contracts_path.exists() else {"contracts": []}
    required_roles: list[str] = []
    for contract in contracts.get("contracts") or []:
        if not isinstance(contract, dict):
            continue
        required_roles.extend(str(role) for role in contract.get("required_data") or [])
        required_roles.extend(str(role) for role in contract.get("required_data_roles") or [])
    available_roles = list(dict.fromkeys(required_roles + [
        "local_data",
        "tabular_data",
        "sample_records",
        "processed_dataset",
        "label_or_response",
        "spectral_or_remote_sensing_features",
        "time_series",
        "validation_design",
    ]))
    (project_path / "data" / "data_role_coverage_report.json").write_text(
        json.dumps({
            "status": "written",
            "decision": "pass",
            "required_roles": required_roles,
            "available_roles": available_roles,
            "missing_roles": [],
            "blocking_missing_roles": [],
            "partial_missing_roles": [],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "methods" / "method_feasibility_report.json").write_text(
        json.dumps({"status": "written", "decision": "pass", "issues": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assess_figure_contracts(project_path)


class AnalysisCodeGenerationTests(unittest.TestCase):
    def test_generate_analysis_code_writes_manifest_and_runnable_code(self) -> None:
        from draftpaper_cli.analysis_code import generate_analysis_code
        from draftpaper_cli.project_state import load_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="X-ray flaring source classification", field="astronomy machine learning")
            prepare_codegen_project(project.path)
            figure_plan = plan_figures(project.path)
            write_passing_figure_contract_gate(project.path)

            result = generate_analysis_code(project.path)

            self.assertEqual(result["status"], "written")
            self.assertEqual(figure_plan["status"], "written")
            self.assertTrue((project.path / "results" / "figure_plan.json").exists())
            self.assertTrue((project.path / "results" / "figure_plan.html").exists())
            self.assertTrue((project.path / "methods" / "scripts" / "run_analysis.py").exists())
            self.assertTrue((project.path / "methods" / "src" / "generated_pipeline.py").exists())
            self.assertTrue((project.path / "methods" / "requirements-publication.txt").exists())
            self.assertTrue((project.path / "methods" / "method_code_manifest.json").exists())
            self.assertTrue((project.path / "code" / "scripts" / "run_analysis.py").exists())
            self.assertTrue((project.path / "code" / "src" / "generated_pipeline.py").exists())
            self.assertTrue((project.path / "code" / "requirements-publication.txt").exists())
            self.assertTrue((project.path / "code" / "tests" / "test_generated_pipeline.py").exists())
            self.assertIn(
                "Source-available for non-commercial use only",
                (project.path / "methods" / "src" / "generated_pipeline.py").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Source-available for non-commercial use only",
                (project.path / "methods" / "scripts" / "run_analysis.py").read_text(encoding="utf-8"),
            )
            self.assertIn("results/tables/metrics.csv", result["declared_outputs"])
            self.assertIn("results/tables/analysis_summary.csv", result["declared_outputs"])
            self.assertIn("results/figure_metadata.json", result["declared_outputs"])
            self.assertIn("results/figure_quality_report.json", result["declared_outputs"])
            self.assertTrue(any(path.startswith("results/figures/") for path in result["declared_outputs"]))
            generated_figures = [path for path in result["declared_outputs"] if path.startswith("results/figures/")]
            self.assertTrue(generated_figures)
            self.assertTrue(all(path.endswith(".png") for path in generated_figures))
            state = load_project(project.path)
            self.assertEqual(state.metadata["stages"]["code"]["status"], "draft")
            self.assertTrue(state.metadata["stages"]["methods"]["stale"])

            manifest = json.loads((project.path / "methods" / "analysis_code_manifest.json").read_text(encoding="utf-8"))
            method_manifest = json.loads((project.path / "methods" / "method_code_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(method_manifest["code_layout"], "stage_owned_methods_code_with_code_compatibility_launchers")
            self.assertEqual(method_manifest["verify_command_argv"], ["{python}", "methods/scripts/run_analysis.py"])
            self.assertEqual(manifest["verify_command_argv"], result["verify_command_argv"])
            self.assertEqual(method_manifest["verify_command"], result["verify_command"])
            self.assertEqual(manifest["verify_command"], result["verify_command"])
            self.assertNotIn(sys.executable, method_manifest["verify_command"])
            self.assertTrue(all(path.startswith("methods/") for path in manifest["canonical_code_outputs"]))
            self.assertTrue(all(path.startswith("code/") for path in manifest["compatibility_code_outputs"]))
            self.assertTrue(all("/methods/" in path.replace("\\", "/") for path in result["generated_files"]))
            self.assertTrue(all("/code/" in path.replace("\\", "/") for path in result["compatibility_files"]))
            self.assertNotIn("--command", result["next_command"])
            self.assertNotIn("--output", result["next_command"])
            self.assertIn("time_series_deep_learning", manifest["method_families"])
            self.assertIn("multimodal_learning", manifest["method_families"])
            self.assertEqual(manifest["selected_input_data"], "data/raw/sources.csv")
            self.assertGreaterEqual(manifest["literature_method_count"], 1)
            requirements_text = (project.path / "methods" / "requirements-publication.txt").read_text(encoding="utf-8")
            self.assertIn("matplotlib", requirements_text)
            self.assertIn("SciencePlots", requirements_text)
            self.assertIn("scikit-learn", requirements_text)
            self.assertIn("scikit-plot", requirements_text)
            self.assertIn("astropy", requirements_text)

            verify_result = verify_methods(
                project.path,
                output_files=result["declared_outputs"],
                input_data=[manifest["selected_input_data"]],
            )
            self.assertEqual(verify_result["status"], "success")
            metrics = json.loads((project.path / "methods" / "run_manifest.yaml").read_text(encoding="utf-8"))["metrics"]
            self.assertIn("f1", metrics)
            self.assertIn("row_count", metrics)
            self.assertTrue((project.path / "methods" / "method_formula_manifest.json").exists())
            self.assertTrue((project.path / "methods" / "method_formulas.tex").exists())
            for output in result["declared_outputs"]:
                self.assertTrue((project.path / output).exists())
            metadata = json.loads((project.path / "results" / "figure_metadata.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(metadata["figures"]), 1)
            generated_plan = [
                item for item in json.loads((project.path / "results" / "figure_plan.json").read_text(encoding="utf-8"))["figures"]
                if item.get("generation_mode") == "generated_code"
            ]
            self.assertEqual(len(metadata["figures"]), len(generated_plan))
            self.assertFalse(metadata["figures"][0]["is_placeholder"])
            self.assertEqual(metadata["figures"][0]["file_format"], "png")
            self.assertIn("statistics", metadata["figures"][0])
            self.assertTrue(metadata["figures"][0]["statistics"])
            self.assertIn(metadata["figures"][0]["backend"], {"matplotlib_scienceplots", "matplotlib_publication", "png_stdlib_fallback"})
            self.assertTrue(metadata["figures"][0]["publication_ready"])
            self.assertTrue(metadata["figures"][0]["axis_labels"])
            self.assertTrue(metadata["figures"][0]["text_elements"])
            self.assertIn("figure_size_inches", metadata["figures"][0])
            self.assertTrue(metadata["figures"][0]["interpretation_summary"])
            for figure in metadata["figures"]:
                figure_path = project.path / figure["path"]
                self.assertEqual(figure_path.suffix.lower(), ".png")
                self.assertEqual(figure_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            quality = json.loads((project.path / "results" / "figure_quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["status"], "passed")

    def test_cli_generate_analysis_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI codegen", field="astronomy machine learning")
            prepare_codegen_project(project.path)
            plan_figures(project.path)
            write_passing_figure_contract_gate(project.path)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "generate-analysis-code",
                    "--project",
                    str(project.path),
                    "--auto-plan-figures",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertIn("verify_command", payload)
            self.assertTrue((project.path / "results" / "figure_plan.json").exists())
            self.assertTrue(Path(payload["analysis_code_manifest"]).exists())

    def test_generate_analysis_code_prefers_user_named_processed_table(self) -> None:
        from draftpaper_cli.analysis_code import generate_analysis_code

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Wheat NDVI proxy analysis", field="remote sensing agronomy")
            (project.path / "research_plan" / "research_plan.md").write_text("# Plan\n\nExploratory wheat NDVI analysis.\n", encoding="utf-8")
            raw_rows = "\n".join(f"{i},{i % 3}" for i in range(1, 101))
            processed_rows = "\n".join(f"{i},{0.2 + i / 1000:.3f},{i % 8}" for i in range(1, 41))
            (project.path / "data" / "raw" / "large_cluster_table.csv").write_text("id,cluster\n" + raw_rows + "\n", encoding="utf-8")
            (project.path / "data" / "processed" / "wheat_ndvi_yield_proxy.csv").write_text("sample_id,ndvi,yield\n" + processed_rows + "\n", encoding="utf-8")
            inventory_data(project.path)
            assess_data_quality(project.path, required_columns=["ndvi", "yield"])
            assess_data_feasibility(project.path, min_rows=30)
            collect_method_plan(
                project.path,
                user_method="Use data/processed/wheat_ndvi_yield_proxy.csv as the main analysis table for NDVI and yield association.",
                primary_metric="r2",
                minimum_primary_metric=0.05,
            )
            plan_figures(project.path)
            write_passing_figure_contract_gate(project.path)

            generate_analysis_code(project.path)

            manifest = json.loads((project.path / "methods" / "analysis_code_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["selected_input_data"], "data/processed/wheat_ndvi_yield_proxy.csv")

            figure_plan = json.loads((project.path / "results" / "figure_plan.json").read_text(encoding="utf-8"))
            figure_specs = figure_plan["figures"]
            generated_specs = [item for item in figure_specs if item.get("generation_mode") == "generated_code"]
            self.assertGreaterEqual(len(generated_specs), 5)
            self.assertEqual(figure_plan["figure_policy"]["discipline"], "geography")
            self.assertGreaterEqual(figure_plan["figure_policy"]["minimum_main_figures"], 5)
            groups = {item.get("figure_group") for item in generated_specs}
            self.assertIn("remote_sensing_index_distribution", groups)
            self.assertIn("environmental_driver_response", groups)
            self.assertIn("predictor_correlation_structure", groups)
            self.assertTrue(any(item.get("figure_type") == "scatter_regression" for item in figure_specs))
            self.assertTrue(all(item.get("path", "").endswith(".png") for item in figure_specs if item.get("generation_mode") == "generated_code"))
            for item in figure_specs:
                if item.get("generation_mode") == "generated_code":
                    self.assertEqual(item["required_inputs"], ["data/processed/wheat_ndvi_yield_proxy.csv"])
                    self.assertNotIn("cluster", " ".join(item.get("required_columns") or []).lower())
            self.assertTrue(all(item.get("no_flowchart_fallback") is True for item in figure_specs if item.get("generation_mode") == "generated_code"))
            write_passing_figure_contract_gate(project.path)

            codegen = generate_analysis_code(project.path)
            requirements_text = (project.path / "methods" / "requirements-publication.txt").read_text(encoding="utf-8")
            self.assertIn("geopandas", requirements_text)
            self.assertIn("rasterio", requirements_text)
            self.assertIn("cartopy", requirements_text)
            codegen_manifest = json.loads((project.path / "methods" / "analysis_code_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("plotting_requirements", codegen_manifest)
            self.assertIn("geospatial_remote_sensing", codegen_manifest["plotting_requirements"]["matched_rules"])
            verify_methods(
                project.path,
                command=codegen["verify_command"],
                output_files=codegen["declared_outputs"],
                input_data=[codegen["selected_input_data"]],
            )
            run_manifest = json.loads((project.path / "methods" / "run_manifest.yaml").read_text(encoding="utf-8"))
            self.assertIn("r2", run_manifest["metrics"])
            self.assertGreaterEqual(float(run_manifest["metrics"]["r2"]), 0.0)
            formulas = (project.path / "methods" / "method_formulas.tex").read_text(encoding="utf-8")
            self.assertIn("R^2", formulas)

    def test_figure_plan_and_codegen_follow_research_storyboard(self) -> None:
        from draftpaper_cli.analysis_code import generate_analysis_code

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Storyboard source classification", field="astronomy machine learning")
            prepare_codegen_project(project.path)
            write_storyboard_contract(project.path)

            plan_figures(project.path)
            write_passing_figure_contract_gate(project.path)
            figure_plan = json.loads((project.path / "results" / "figure_plan.json").read_text(encoding="utf-8"))
            storyboard_figures = [item for item in figure_plan["figures"] if item.get("source") == "research_storyboard"]
            self.assertGreaterEqual(len(storyboard_figures), 5)
            self.assertEqual(storyboard_figures[0]["id"], "fig_1_workflow")
            self.assertEqual(storyboard_figures[0]["title"], "Time-aware flaring-source classification workflow")
            self.assertEqual(storyboard_figures[0]["storyboard_trace"]["validation_metric"], "pipeline_completeness")
            self.assertIn("research_storyboard", figure_plan["loop_decision"])

            result = generate_analysis_code(project.path)
            self.assertEqual(result["status"], "written")
            manifest = json.loads((project.path / "methods" / "analysis_code_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["research_storyboard"]["source"], "research_blueprint")
            self.assertGreaterEqual(len(manifest["research_storyboard"]["figures"]), 5)
            self.assertIn("method_tasks", manifest["research_method_plan"])


if __name__ == "__main__":
    unittest.main()
