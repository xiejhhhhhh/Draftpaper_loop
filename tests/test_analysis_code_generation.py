# Copyright (c) 2026 xiejhhhhhh
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


class AnalysisCodeGenerationTests(unittest.TestCase):
    def test_generate_analysis_code_writes_manifest_and_runnable_code(self) -> None:
        from draftpaper_cli.analysis_code import generate_analysis_code
        from draftpaper_cli.project_state import load_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="X-ray flaring source classification", field="astronomy machine learning")
            prepare_codegen_project(project.path)
            figure_plan = plan_figures(project.path)

            result = generate_analysis_code(project.path)

            self.assertEqual(result["status"], "written")
            self.assertEqual(figure_plan["status"], "written")
            self.assertTrue((project.path / "results" / "figure_plan.json").exists())
            self.assertTrue((project.path / "results" / "figure_plan.html").exists())
            self.assertTrue((project.path / "code" / "scripts" / "run_analysis.py").exists())
            self.assertTrue((project.path / "code" / "src" / "generated_pipeline.py").exists())
            self.assertTrue((project.path / "code" / "requirements-publication.txt").exists())
            self.assertTrue((project.path / "code" / "tests" / "test_generated_pipeline.py").exists())
            self.assertIn(
                "Source-available for non-commercial use only",
                (project.path / "code" / "src" / "generated_pipeline.py").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Source-available for non-commercial use only",
                (project.path / "code" / "scripts" / "run_analysis.py").read_text(encoding="utf-8"),
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
            self.assertIn("time_series_deep_learning", manifest["method_families"])
            self.assertIn("multimodal_learning", manifest["method_families"])
            self.assertEqual(manifest["selected_input_data"], "data/raw/sources.csv")
            self.assertGreaterEqual(manifest["literature_method_count"], 1)
            requirements_text = (project.path / "code" / "requirements-publication.txt").read_text(encoding="utf-8")
            self.assertIn("matplotlib", requirements_text)
            self.assertIn("SciencePlots", requirements_text)
            self.assertIn("scikit-learn", requirements_text)
            self.assertIn("scikit-plot", requirements_text)
            self.assertIn("astropy", requirements_text)

            verify_result = verify_methods(
                project.path,
                command=result["verify_command"],
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

            generate_analysis_code(project.path)

            manifest = json.loads((project.path / "methods" / "analysis_code_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["selected_input_data"], "data/processed/wheat_ndvi_yield_proxy.csv")

            figure_plan = json.loads((project.path / "results" / "figure_plan.json").read_text(encoding="utf-8"))
            figure_specs = figure_plan["figures"]
            self.assertTrue(any(item.get("figure_type") == "scatter_regression" for item in figure_specs))
            self.assertTrue(all(item.get("path", "").endswith(".png") for item in figure_specs if item.get("generation_mode") == "generated_code"))
            for item in figure_specs:
                if item.get("generation_mode") == "generated_code":
                    self.assertEqual(item["required_inputs"], ["data/processed/wheat_ndvi_yield_proxy.csv"])
                    self.assertNotIn("cluster", " ".join(item.get("required_columns") or []).lower())
            self.assertTrue(all(item.get("no_flowchart_fallback") is True for item in figure_specs if item.get("generation_mode") == "generated_code"))

            codegen = generate_analysis_code(project.path)
            requirements_text = (project.path / "code" / "requirements-publication.txt").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
