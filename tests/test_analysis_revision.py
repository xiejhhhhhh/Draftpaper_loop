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
from draftpaper_cli.project_state import update_stage_status
from tests.test_analysis_code_generation import write_passing_figure_contract_gate


def write_inventory(project_path: Path, columns: list[str]) -> None:
    (project_path / "data" / "data_inventory.json").write_text(
        json.dumps({
            "status": "written",
            "file_count": 1,
            "files": [
                {
                    "path": "data/processed/analysis_table.csv",
                    "kind": "processed",
                    "suffix": ".csv",
                    "readable": True,
                    "columns": columns,
                    "row_count": 120,
                    "column_count": len(columns),
                }
            ],
            "total_rows": 120,
            "tabular_file_count": 1,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_data_table(project_path: Path, rows: int = 12) -> None:
    data_path = project_path / "data" / "processed" / "analysis_table.csv"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["ndvi,yield,air_temperature,region,year,longitude,latitude"]
    for index in range(rows):
        lines.append(
            f"{0.30 + index * 0.02:.3f},{3.0 + index * 0.12:.3f},{18 + index % 4},R{index % 3},202{index % 3},{110 + index * 0.1:.3f},{35 + index * 0.1:.3f}"
        )
    data_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_method_requirements(project_path: Path) -> None:
    (project_path / "methods" / "method_requirements.json").write_text(
        json.dumps({
            "primary_metric": "r2",
            "minimum_primary_metric": 0.1,
            "method_families": ["remote_sensing_regression", "baseline_ablation"],
            "required_data_features": ["ndvi", "yield", "air_temperature", "region", "year"],
            "user_method": "Run agricultural remote-sensing feature rebuilding, baseline comparison, and spatial validation when data allow.",
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "methods" / "method_plan.md").write_text(
        "Use agricultural remote-sensing regression with NDVI, yield, climate proxies, region, and year.\n",
        encoding="utf-8",
    )
    update_stage_status(project_path, "method_plan", "approved")


def write_review_inputs(project_path: Path) -> None:
    (project_path / "review" / "statistical_rescue_plan.json").write_text(
        json.dumps({
            "status": "rescue_recommended",
            "recommended_routes": [
                {
                    "route_id": "agricultural_remote_sensing_feature_rebuild",
                    "title": "Rebuild crop and remote-sensing features before strengthening claims",
                    "target_stage": "methods",
                    "rationale": "Weak crop-yield evidence may improve after agronomic feature construction and blocked validation.",
                    "recommended_actions": [
                        "derive phenology-aware NDVI indicators",
                        "use spatial or temporal blocked validation",
                        "regenerate figure plans around agronomic evidence",
                    ],
                },
                {
                    "route_id": "spatial_ecological_validation",
                    "title": "Add spatial structure and ecological validation checks",
                    "target_stage": "methods",
                    "rationale": "Spatial projects need grouped or blocked validation.",
                    "recommended_actions": [
                        "prefer spatial block, regional holdout, or time-sliced validation",
                    ],
                },
            ],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "review" / "review_engineering_plan.json").write_text(
        json.dumps({
            "status": "review_engineering_plan_written",
            "discipline_profile": {"discipline": "geography", "engine": "geography"},
            "issues": [
                {
                    "code": "geography_remote_sensing_qc",
                    "source": "review_engineering",
                    "target_stage": "data",
                    "title": "Add remote-sensing quality control before interpreting weak effects",
                    "reason": "NDVI can be weakened by cloud contamination and phenology-window mismatch.",
                    "recommended_commands": ["plan-figures", "generate-analysis-code", "verify-methods"],
                },
                {
                    "code": "geography_spatial_autocorrelation",
                    "source": "review_engineering",
                    "target_stage": "methods",
                    "title": "Assess spatial autocorrelation and spatial validation risk",
                    "reason": "Geographic samples are often spatially clustered.",
                    "recommended_commands": ["plan-figures", "generate-analysis-code", "verify-methods"],
                },
            ],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class AnalysisRevisionTests(unittest.TestCase):
    def test_data_role_map_uses_token_roles_without_identifier_substring_collisions(self) -> None:
        from draftpaper_cli.analysis_revision import _data_role_map

        inventory = {
            "files": [
                {
                    "readable": True,
                    "columns": [
                        "adaptive_label",
                        "desi_row_index",
                        "population",
                        "COADD_EXPTIME",
                        "emb_0",
                        "color_gr",
                        "RA",
                        "DEC",
                        "euclid_region",
                    ],
                }
            ]
        }

        roles = _data_role_map(inventory)

        self.assertIn("adaptive_label", roles["target"])
        self.assertIn("emb_0", roles["predictors"])
        self.assertIn("color_gr", roles["predictors"])
        self.assertNotIn("desi_row_index", roles["predictors"])
        self.assertIn("RA", roles["spatial_group_or_coordinates"])
        self.assertIn("DEC", roles["spatial_group_or_coordinates"])
        self.assertNotIn("population", roles["spatial_group_or_coordinates"])
        self.assertNotIn("COADD_EXPTIME", roles.get("time", []))

    def test_prepare_analysis_revision_writes_executable_geography_tasks_when_data_roles_exist(self) -> None:
        from draftpaper_cli.analysis_revision import prepare_analysis_revision

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="NDVI wheat yield mapping with agricultural remote sensing.",
                field="geography remote sensing agriculture",
            )
            write_inventory(project.path, ["ndvi", "yield", "air_temperature", "region", "year", "longitude", "latitude"])
            write_review_inputs(project.path)

            result = prepare_analysis_revision(project.path)

            self.assertEqual(result["status"], "analysis_revision_prepared")
            self.assertGreaterEqual(result["task_count"], 3)
            by_family = {task["operation_family"]: task for task in result["tasks"]}
            self.assertEqual(by_family["spatial_block_validation"]["feasibility"]["status"], "executable")
            self.assertEqual(by_family["agricultural_remote_sensing_feature_rebuild"]["feasibility"]["status"], "executable")
            self.assertTrue((project.path / "review" / "actionable_analysis_tasks.json").exists())
            self.assertTrue((project.path / "review" / "analysis_revision_feasibility.html").exists())
            self.assertTrue((project.path / "methods" / "analysis_revision_requirements.json").exists())
            self.assertTrue((project.path / "results" / "revision_figure_plan_delta.json").exists())

    def test_prepare_analysis_revision_blocks_spatial_validation_when_spatial_roles_are_missing(self) -> None:
        from draftpaper_cli.analysis_revision import prepare_analysis_revision

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="NDVI wheat yield mapping with agricultural remote sensing.",
                field="geography remote sensing agriculture",
            )
            write_inventory(project.path, ["ndvi", "yield", "air_temperature", "year"])
            write_review_inputs(project.path)

            result = prepare_analysis_revision(project.path)

            by_family = {task["operation_family"]: task for task in result["tasks"]}
            spatial = by_family["spatial_block_validation"]
            self.assertEqual(spatial["feasibility"]["status"], "blocked_missing_data")
            self.assertIn("spatial_group_or_coordinates", spatial["feasibility"]["missing_required_roles"])
            self.assertGreaterEqual(result["blocked_task_count"], 1)

    def test_cli_prepare_analysis_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="NDVI wheat yield mapping with agricultural remote sensing.",
                field="geography remote sensing agriculture",
            )
            write_inventory(project.path, ["ndvi", "yield", "region", "year"])
            write_review_inputs(project.path)

            completed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "prepare-analysis-revision", "--project", str(project.path)],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "analysis_revision_prepared")
            self.assertIn("plan-figures", payload["next_command"])
            self.assertIn("--use-review-tasks", payload["next_command"])

    def test_plan_figures_uses_review_tasks_to_create_revision_figures(self) -> None:
        from draftpaper_cli.analysis_revision import prepare_analysis_revision
        from draftpaper_cli.figure_plan import plan_figures

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="NDVI wheat yield mapping with agricultural remote sensing.",
                field="geography remote sensing agriculture",
            )
            write_inventory(project.path, ["ndvi", "yield", "air_temperature", "region", "year", "longitude", "latitude"])
            write_data_table(project.path)
            write_method_requirements(project.path)
            write_review_inputs(project.path)
            prepare_analysis_revision(project.path)

            plan = plan_figures(project.path, use_review_tasks=True)
            payload = json.loads((project.path / "results" / "figure_plan.json").read_text(encoding="utf-8"))

            self.assertEqual(plan["status"], "written")
            self.assertTrue(payload["used_review_tasks"])
            review_figures = [item for item in payload["figures"] if item.get("source") == "review_task"]
            operations = {item["operation_family"] for item in review_figures}
            self.assertIn("agricultural_remote_sensing_feature_rebuild", operations)
            self.assertIn("baseline_ablation", operations)
            self.assertIn("spatial_block_validation", operations)
            self.assertTrue(all(item.get("review_task_id") for item in review_figures))
            self.assertTrue(all(item.get("figure_role") == "supporting" for item in review_figures))
            self.assertTrue(all(item.get("manuscript_role") == "appendix" for item in review_figures))
            self.assertTrue(all(item.get("counts_toward_main_figures") is False for item in review_figures))

    def test_generate_analysis_code_uses_review_tasks_and_declares_coverage_output(self) -> None:
        from draftpaper_cli.analysis_code import generate_analysis_code
        from draftpaper_cli.analysis_revision import prepare_analysis_revision
        from draftpaper_cli.figure_plan import plan_figures

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="NDVI wheat yield mapping with agricultural remote sensing.",
                field="geography remote sensing agriculture",
            )
            write_inventory(project.path, ["ndvi", "yield", "air_temperature", "region", "year", "longitude", "latitude"])
            write_data_table(project.path)
            write_method_requirements(project.path)
            write_review_inputs(project.path)
            prepare_analysis_revision(project.path)
            plan_figures(project.path, use_review_tasks=True)
            write_passing_figure_contract_gate(project.path)

            result = generate_analysis_code(project.path, use_review_tasks=True)
            manifest = json.loads((project.path / "methods" / "analysis_code_manifest.json").read_text(encoding="utf-8"))

            self.assertIn("review_task_coverage", manifest)
            self.assertIn("results/tables/review_task_coverage.csv", result["declared_outputs"])
            self.assertIn("results/tables/review_task_metrics.csv", result["declared_outputs"])
            self.assertGreaterEqual(len(manifest["review_task_coverage"]["covered_task_ids"]), 2)
            pipeline = (project.path / "code" / "src" / "generated_pipeline.py").read_text(encoding="utf-8")
            self.assertIn("write_review_task_coverage", pipeline)
            self.assertIn("write_review_task_metrics", pipeline)
            self.assertIn("cleaning_or_qc", pipeline)
            self.assertIn("feature_reconstruction", pipeline)
            self.assertIn("baseline_ablation", pipeline)

    def test_verify_methods_fails_when_review_task_coverage_is_missing(self) -> None:
        from draftpaper_cli.analysis_revision import prepare_analysis_revision
        from draftpaper_cli.methods import verify_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="NDVI wheat yield mapping with agricultural remote sensing.",
                field="geography remote sensing agriculture",
            )
            write_inventory(project.path, ["ndvi", "yield", "air_temperature", "region", "year"])
            write_data_table(project.path)
            write_method_requirements(project.path)
            write_review_inputs(project.path)
            prepare_analysis_revision(project.path)
            script = (
                "from pathlib import Path\n"
                "p=Path('results/tables'); p.mkdir(parents=True, exist_ok=True)\n"
                "(p/'metrics.csv').write_text('metric,value\\nr2,0.2\\n', encoding='utf-8')\n"
            )

            result = verify_methods(
                project.path,
                command=f'"{sys.executable}" -c "{script}"',
                output_files=["results/tables/metrics.csv"],
            )

            manifest = json.loads((project.path / "methods" / "run_manifest.yaml").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "failed")
            self.assertTrue(manifest["review_task_coverage_issues"])

    def test_assess_result_validity_fails_when_review_task_coverage_failed(self) -> None:
        from draftpaper_cli.result_validity import assess_result_validity

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="NDVI wheat yield mapping with agricultural remote sensing.",
                field="geography remote sensing agriculture",
            )
            write_method_requirements(project.path)
            (project.path / "data" / "data_feasibility_report.json").write_text(
                json.dumps({"decision": "pass"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "metrics": {"r2": "0.8"},
                    "output_files": ["results/tables/metrics.csv"],
                    "review_task_coverage_issues": ["Missing results/tables/review_task_coverage.csv for executable or partial review tasks."],
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (project.path / "results" / "tables").mkdir(parents=True, exist_ok=True)
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nr2,0.8\n", encoding="utf-8")

            result = assess_result_validity(project.path)
            report = json.loads((project.path / "results" / "result_validity_report.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "revise_required")
            self.assertTrue(report["review_task_coverage_issues"])


if __name__ == "__main__":
    unittest.main()
