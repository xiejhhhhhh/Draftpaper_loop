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

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project, update_stage_status


def prepare_passing_result_validity(project_path: Path) -> None:
    from draftpaper_cli.result_validity import assess_result_validity

    (project_path / "methods" / "method_requirements.json").write_text(
        json.dumps({"primary_metric": "f1", "minimum_primary_metric": 0.7, "method_data_fit": "proceed"}),
        encoding="utf-8",
    )
    (project_path / "data" / "data_feasibility_report.json").write_text(
        json.dumps({"decision": "pass"}),
        encoding="utf-8",
    )
    (project_path / "methods" / "run_manifest.yaml").write_text(
        json.dumps({
            "status": "success",
            "output_files": ["results/tables/metrics.csv"],
            "metrics": {"f1": 0.88},
        }),
        encoding="utf-8",
    )
    assess_result_validity(project_path)


class ResultsManifestWriterTests(unittest.TestCase):
    def test_inventory_excludes_historical_artifacts_when_current_run_declares_outputs(self) -> None:
        from draftpaper_cli.results import inventory_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Current run inventory", field="astronomy")
            figures = project.path / "results" / "figures"
            tables = project.path / "results" / "tables"
            methods = project.path / "methods"
            figures.mkdir(parents=True, exist_ok=True)
            tables.mkdir(parents=True, exist_ok=True)
            methods.mkdir(parents=True, exist_ok=True)
            (figures / "current.png").write_bytes(b"current")
            (figures / "historical.png").write_bytes(b"historical")
            (tables / "current.csv").write_text("metric,value\nf1,0.8\n", encoding="utf-8")
            (tables / "historical.csv").write_text("metric,value\nf1,0.5\n", encoding="utf-8")
            (project.path / "results" / "figure_metadata.json").write_text(
                json.dumps({"figures": [{"path": "results/figures/current.png"}]}),
                encoding="utf-8",
            )
            (methods / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "figures_generated": ["results/figures/current.png"],
                    "tables_generated": ["results/tables/current.csv"],
                }),
                encoding="utf-8",
            )

            result = inventory_results(project.path)
            manifest = json.loads((project.path / "results" / "result_manifest.yaml").read_text(encoding="utf-8"))

            self.assertEqual(result["figure_count"], 1)
            self.assertEqual(result["table_count"], 1)
            self.assertEqual(manifest["inventory_scope"], "current_successful_run")
            self.assertEqual([item["path"] for item in manifest["figures"]], ["results/figures/current.png"])
            self.assertEqual([item["path"] for item in manifest["tables"]], ["results/tables/current.csv"])

    def test_inventory_results_writes_manifest_for_existing_figures_and_tables(self) -> None:
        from draftpaper_cli.results import inventory_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Result manifest test", field="workflow engineering")
            (project.path / "results" / "figures" / "fig1.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\naccuracy,0.91\n", encoding="utf-8")

            result = inventory_results(project.path)

            self.assertEqual(result["status"], "written")
            manifest_path = project.path / "results" / "result_manifest.yaml"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["figures"][0]["path"], "results/figures/fig1.png")
            self.assertEqual(manifest["tables"][0]["path"], "results/tables/metrics.csv")
            self.assertEqual(manifest["schema_version"], "dpl.result_manifest.v2")
            self.assertIn("main_figures", manifest)
            self.assertIn("appendix_figures", manifest)
            self.assertIn("supporting_links", manifest)
            self.assertIn("claim_boundaries", manifest)
            self.assertIn("result_claim", manifest["figures"][0])

    def test_write_results_requires_manifest_and_existing_files(self) -> None:
        from draftpaper_cli.results import ResultsGateError, write_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Missing result test", field="workflow engineering")

            with self.assertRaises(ResultsGateError):
                write_results(project.path)

            (project.path / "results" / "result_manifest.yaml").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "fig1",
                            "path": "results/figures/missing.png",
                            "caption_draft": "Missing figure",
                            "result_claim": "A missing result cannot support text.",
                        }
                    ],
                    "tables": [],
                }),
                encoding="utf-8",
            )
            with self.assertRaises(ResultsGateError):
                write_results(project.path)

    def test_write_results_creates_latex_without_citations_and_writes_chinese_review_summary(self) -> None:
        from draftpaper_cli.results import inventory_results, write_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN prediction results", field="machine learning astronomy")
            (project.path / "results" / "figures" / "risk_curve.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            prepare_passing_result_validity(project.path)
            inventory_results(project.path)

            result = write_results(project.path)

            self.assertEqual(result["status"], "written")
            tex_path = project.path / "results" / "results.tex"
            tex = tex_path.read_text(encoding="utf-8")
            self.assertTrue(tex.startswith("\\section{Results}"))
            self.assertIn("\\includegraphics", tex)
            self.assertIn("results/figures/risk_curve.png", tex)
            self.assertNotIn("results/tables/metrics.csv", tex)
            self.assertNotIn("\\texttt", tex)
            self.assertNotIn("\\cite", tex)
            self.assertNotIn("\\subsection", tex)
            self.assertRegex(tex, r"Figure~\\ref\{fig:[^{}]+\}")
            self.assertLess(tex.index("The figure provides visual evidence"), tex.index("\\includegraphics"))
            self.assertLess(tex.index("risk_curve.png"), tex.index("\\end{figure}"))
            self.assertTrue(tex.rstrip().endswith("\\end{table}"))
            self.assertIn("\\begin{minipage}{0.86\\linewidth}", tex)
            self.assertNotIn("p{0.86\\linewidth}", tex)
            self.assertNotIn("This section does not use literature citations", tex)
            self.assertNotIn("local filenames", tex)
            self.assertNotIn("storage paths", tex)
            self.assertNotIn("Draftpaper", tex)
            self.assertNotIn("result validity gate", tex)
            self.assertNotIn("project workflow", tex)
            self.assertNotIn("verified workflow", tex)
            summary = project.path / "results" / "results_summary_zh.md"
            self.assertTrue(summary.exists())
            self.assertIn("结果部分中文审阅摘要", summary.read_text(encoding="utf-8"))

            manifest = json.loads((project.path / "results" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertIn("results/result_validity_report.json", manifest["input_files"])
            self.assertIn("results/result_manifest.yaml", manifest["input_files"])
            self.assertIn("results/results.tex", manifest["output_files"])
            self.assertIn("results/results_summary_zh.md", manifest["output_files"])

    def test_write_results_can_cite_appendix_diagnostic_figures(self) -> None:
        from draftpaper_cli.results import write_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Appendix diagnostics", field="machine learning astronomy")
            (project.path / "results" / "figures" / "main_panel.png").write_bytes(b"fake main image")
            (project.path / "results" / "figures" / "diagnostic_panel.png").write_bytes(b"fake appendix image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            prepare_passing_result_validity(project.path)
            (project.path / "results" / "result_manifest.yaml").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "main_panel",
                            "path": "results/figures/main_panel.png",
                            "caption_draft": "Main result panel",
                            "result_claim": "The main panel reports the central empirical pattern for the planned result.",
                            "manuscript_role": "main",
                            "figure_role": "main_result",
                        },
                        {
                            "id": "diagnostic_panel",
                            "path": "results/figures/diagnostic_panel.png",
                            "caption_draft": "Appendix diagnostic panel",
                            "result_claim": "The diagnostic panel evaluates whether the main pattern remains stable under a complementary reliability check.",
                            "manuscript_role": "appendix",
                            "figure_role": "supporting_diagnostic",
                            "supporting_reason": "reliability check",
                        },
                    ],
                    "tables": [],
                }),
                encoding="utf-8",
            )

            result = write_results(project.path)

            self.assertEqual(result["status"], "written")
            tex = (project.path / "results" / "results.tex").read_text(encoding="utf-8")
            self.assertIn("Figure~\\ref{fig:main-panel}", tex)
            self.assertIn("Appendix Figure~\\ref{fig:diagnostic-panel}", tex)
            self.assertIn("Diagnostic or supporting evidence", tex)
            self.assertNotIn("first establishes the main empirical pattern", tex)

    def test_write_results_humanizes_internal_identifier_statistics(self) -> None:
        from draftpaper_cli.results import write_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Identifier statistic cleanup", field="astronomy machine learning")
            (project.path / "results" / "figures" / "coverage.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            prepare_passing_result_validity(project.path)
            (project.path / "results" / "result_manifest.yaml").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "coverage-panel",
                            "path": "results/figures/coverage.png",
                            "caption_draft": "Coverage panel. The plotted evidence uses n=5980 usable observations.",
                            "scientific_question": "What data coverage and label support are available?",
                            "result_claim": "source_id has 5980 usable observations with mean 4.03e+04 and range 3.74e+04 to 1.97e+05.",
                        }
                    ],
                    "tables": [
                        {
                            "id": "metrics-table",
                            "path": "results/tables/metrics.csv",
                            "caption_draft": "Metrics summary.",
                            "result_claim": "The metric summary reports row_count=5.98e+03 with 5 numeric metrics available.",
                        }
                    ],
                }),
                encoding="utf-8",
            )

            write_results(project.path)
            tex = (project.path / "results" / "results.tex").read_text(encoding="utf-8")

            self.assertIn("source-level coverage across 5980 usable observations", tex)
            self.assertIn("the data coverage and label support", tex)
            self.assertNotIn("source_id has", tex)
            self.assertNotIn("row_count", tex)
            self.assertNotIn("results/tables/metrics.csv", tex)

    def test_write_results_blocks_when_verified_metric_file_conflicts_with_manifest_scalar(self) -> None:
        from draftpaper_cli.results import ResultsGateError, write_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Weak classifier evidence", field="astronomy machine learning")
            (project.path / "results" / "figures" / "performance.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.50\n", encoding="utf-8")
            prepare_passing_result_validity(project.path)
            (project.path / "results" / "result_manifest.yaml").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "performance-panel",
                            "path": "results/figures/performance.png",
                            "caption_draft": "Baseline versus model performance. The plotted evidence uses n=5 usable observations.",
                            "scientific_question": "Which data modality or method component contributes most to the result?",
                            "result_claim": "The metric summary reports row_count=5.98e+03 and feature_column_count=11 with 5 numeric metrics available.",
                            "metrics": {"row_count": 5980.0, "feature_column_count": 11, "class_count": 2, "f1": 0.500167, "counts": {"AGN": 2989, "XRB": 2991}},
                        }
                    ],
                    "tables": [],
                }),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ResultsGateError, "revise_required"):
                write_results(project.path)

    def test_write_results_is_idempotent_after_downstream_writing_when_inputs_are_unchanged(self) -> None:
        from draftpaper_cli.results import inventory_results, write_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Confirmed result text", field="workflow engineering")
            (project.path / "results" / "figures" / "risk_curve.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            prepare_passing_result_validity(project.path)
            inventory_results(project.path)
            first = write_results(project.path)
            self.assertEqual(first["status"], "written")
            results_tex = project.path / "results" / "results.tex"
            first_text = results_tex.read_text(encoding="utf-8")

            for stage in ["introduction", "data_writing", "methods_writing", "discussion"]:
                update_stage_status(project.path, stage, "draft")
            state_before = load_project(project.path)
            for stage in ["introduction", "data_writing", "methods_writing", "discussion"]:
                self.assertFalse(state_before.metadata["stages"][stage]["stale"], stage)

            second = write_results(project.path)

            self.assertEqual(second["status"], "unchanged")
            self.assertEqual(results_tex.read_text(encoding="utf-8"), first_text)
            state_after = load_project(project.path)
            self.assertFalse(state_after.metadata["stages"]["results"]["stale"])
            for stage in ["introduction", "data_writing", "methods_writing", "discussion"]:
                self.assertFalse(state_after.metadata["stages"][stage]["stale"], stage)


    def test_inventory_results_excludes_stale_unrendered_planned_figures(self) -> None:
        from draftpaper_cli.results import inventory_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Stale supporting figure", field="astronomy machine learning")
            figures_dir = project.path / "results" / "figures"
            figures_dir.mkdir(parents=True, exist_ok=True)
            (figures_dir / "main.png").write_bytes(b"fresh main image")
            (figures_dir / "stale_supporting.png").write_bytes(b"old supporting image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            (project.path / "results" / "figure_plan.json").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "main",
                            "path": "results/figures/main.png",
                            "generation_mode": "generated_code",
                            "figure_role": "main_result",
                            "manuscript_role": "main",
                            "counts_toward_main_figures": True,
                            "caption_draft": "Main empirical panel.",
                            "result_claim_template": "The main panel supports the planned result.",
                        },
                        {
                            "id": "stale_supporting",
                            "path": "results/figures/stale_supporting.png",
                            "generation_mode": "generated_code",
                            "figure_role": "supporting",
                            "manuscript_role": "appendix",
                            "counts_toward_main_figures": False,
                            "caption_draft": "Supporting diagnostic panel.",
                            "result_claim_template": "This panel should only be used if it was rendered in the current run.",
                        },
                    ]
                }),
                encoding="utf-8",
            )
            (project.path / "results" / "figure_metadata.json").write_text(
                json.dumps({
                    "figures": [
                        {
                            "path": "results/figures/main.png",
                            "n": 10,
                            "statistics": {"f1": 0.88},
                            "interpretation_summary": "The main panel reports F1=0.88.",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            (project.path / "results" / "figure_execution_diagnosis.json").write_text(
                json.dumps({
                    "figures": [
                        {
                            "figure_id": "main",
                            "path": "results/figures/main.png",
                            "status": "generated",
                            "rendered_path": "results/figures/main.png",
                        },
                        {
                            "figure_id": "stale_supporting",
                            "path": "results/figures/stale_supporting.png",
                            "status": "missing_data_repairing",
                            "missing_data": ["history_detnam"],
                        },
                    ]
                }),
                encoding="utf-8",
            )

            result = inventory_results(project.path)

            self.assertEqual(result["figure_count"], 1)
            self.assertEqual(result["excluded_unrendered_figure_count"], 1)
            manifest = json.loads((project.path / "results" / "result_manifest.yaml").read_text(encoding="utf-8"))
            self.assertEqual([item["path"] for item in manifest["figures"]], ["results/figures/main.png"])
            self.assertEqual(manifest["excluded_unrendered_figures"][0]["path"], "results/figures/stale_supporting.png")
            self.assertEqual(manifest["main_figures"][0]["path"], "results/figures/main.png")
            self.assertEqual(manifest["appendix_figures"], [])

    def test_write_results_rejects_citation_in_manifest_claim(self) -> None:
        from draftpaper_cli.results import ResultsGateError, write_results

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Citation rejection", field="workflow engineering")
            (project.path / "results" / "figures" / "fig1.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            prepare_passing_result_validity(project.path)
            (project.path / "results" / "result_manifest.yaml").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "fig1",
                            "path": "results/figures/fig1.png",
                            "caption_draft": "A result figure",
                            "result_claim": "This result confirms prior work \\citep{Smith2024}.",
                        }
                    ],
                    "tables": [],
                }),
                encoding="utf-8",
            )

            with self.assertRaises(ResultsGateError):
                write_results(project.path)

    def test_cli_inventory_and_write_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI results", field="workflow engineering")
            (project.path / "results" / "figures" / "fig1.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            (project.path / "methods" / "method_requirements.json").write_text(
                json.dumps({"primary_metric": "f1", "minimum_primary_metric": 0.7, "method_data_fit": "proceed"}),
                encoding="utf-8",
            )
            (project.path / "data" / "data_feasibility_report.json").write_text(json.dumps({"decision": "pass"}), encoding="utf-8")
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

            inventory_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "inventory-results",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(inventory_completed.stdout)["status"], "written")

            write_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "write-results",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(write_completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["results"]).exists())


if __name__ == "__main__":
    unittest.main()
