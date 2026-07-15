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


def prepare_blueprint_project(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text(
        "# Research Plan\n\nAssess NDVI-yield relationships with spatial validation.\n",
        encoding="utf-8",
    )
    rows = "\n".join(f"{i},{2020 + i % 3},region_{i % 4},{0.2 + i / 1000:.3f},{3000 + i}" for i in range(1, 50))
    (project_path / "data" / "processed" / "wheat_ndvi.csv").write_text(
        "sample_id,year,region,ndvi,yield\n" + rows + "\n",
        encoding="utf-8",
    )
    inventory_data(project_path)
    assess_data_quality(project_path, required_columns=["ndvi", "yield"])
    assess_data_feasibility(project_path, min_rows=30)
    collect_method_plan(
        project_path,
        user_method="Use remote sensing feature reconstruction and spatial block validation for wheat yield response.",
        primary_metric="r2",
        minimum_primary_metric=0.05,
    )


class MethodBlueprintTests(unittest.TestCase):
    def test_prepare_method_blueprint_writes_discipline_contract(self) -> None:
        from draftpaper_cli.method_blueprint import prepare_method_blueprint

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="NDVI wheat spatial yield analysis", field="geography remote sensing")
            prepare_blueprint_project(project.path)

            result = prepare_method_blueprint(project.path)

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["discipline"], "geography")
            self.assertTrue((project.path / "methods" / "method_blueprint.json").exists())
            self.assertTrue((project.path / "methods" / "method_blueprint.html").exists())
            self.assertTrue((project.path / "methods" / "method_data_contract.json").exists())
            self.assertTrue((project.path / "methods" / "method_code_plan.json").exists())
            self.assertTrue((project.path / "methods" / "method_formula_plan.json").exists())
            blueprint = json.loads((project.path / "methods" / "method_blueprint.json").read_text(encoding="utf-8"))
            self.assertIn("spatial_block_validation", blueprint["method_code_plan"]["method_families"])
            self.assertIn("spatial_group_or_coordinates", blueprint["method_data_contract"]["available_roles"])
            self.assertIn("methods/scripts", blueprint["method_code_plan"]["stage_owned_code_locations"])

    def test_cli_prepare_method_blueprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="NDVI wheat CLI blueprint", field="geography remote sensing")
            prepare_blueprint_project(project.path)
            refresh_project_passport(project.path, event="test_cli_fixture_prepared")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "prepare-method-blueprint",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["method_blueprint"]).exists())

    def test_structured_scientific_image_contract_does_not_inherit_astronomy_time_series_templates(self) -> None:
        from draftpaper_cli.method_blueprint import prepare_method_blueprint
        from draftpaper_cli.project_state import update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Scientific-image representation analysis with group-aware validation",
                field="astronomy machine learning",
            )
            (project.path / "data" / "data_inventory.json").write_text(
                json.dumps({"files": [{"path": "external://source/embeddings.csv", "columns": ["TARGETID", "emb_0"]}]}),
                encoding="utf-8",
            )
            (project.path / "data" / "data_role_coverage_report.json").write_text(
                json.dumps(
                    {
                        "decision": "pass",
                        "available_roles": [
                            "source_catalog",
                            "image_or_raster_data",
                            "features",
                            "label_or_response",
                            "confounder_variables",
                            "sample_group",
                            "validation_design",
                            "missingness_reason",
                            "quality_flags",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (project.path / "research_plan" / "method_plan.json").write_text(
                json.dumps(
                    {
                        "method_tasks": [
                            {
                                "method_family": "representation_projection",
                                "method_components": ["target_confounder_diagnostic"],
                                "required_data": ["image_embedding", "independent_target", "confounder_variables"],
                                "validation_metric": "target_and_confounder_association",
                            },
                            {
                                "method_family": "group_aware_validation",
                                "method_components": ["transparent_baseline_comparison"],
                                "required_data": [
                                    "group_validation_split",
                                    "class_label",
                                    "prediction_score",
                                    "image_class_assignment",
                                    "physical_class_assignment",
                                    "assignment_stability",
                                ],
                                "validation_metric": "group_held_out_metric",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (project.path / "research_plan" / "figure_storyboard.json").write_text(
                json.dumps({"figures": [{"figure_id": "fig_repr", "suggested_plot_type": "embedding_diagnostic"}]}),
                encoding="utf-8",
            )
            (project.path / "methods" / "method_requirements.json").write_text(
                json.dumps(
                    {
                        "method_families": [
                            "representation_projection",
                            "target_confounder_diagnostic",
                            "group_aware_validation",
                            "transparent_baseline_comparison",
                        ],
                        "required_data_features": ["image_embedding", "independent_target"],
                        "method_data_fit": "proceed",
                    }
                ),
                encoding="utf-8",
            )
            (project.path / "methods" / "method_plan.md").write_text("Structured image method plan.\n", encoding="utf-8")
            update_stage_status(project.path, "method_plan", "draft")

            prepare_method_blueprint(project.path)

            blueprint = json.loads(
                (project.path / "methods" / "method_blueprint.json").read_text(encoding="utf-8")
            )
            code_plan = blueprint["method_code_plan"]
            contract = blueprint["method_data_contract"]
            self.assertEqual(code_plan["selected_method_templates"], [])
            self.assertNotIn("time_series_deep_learning_input", code_plan["method_families"])
            self.assertNotIn("event_level_transformer_input_builder", code_plan["method_families"])
            self.assertNotIn("light_curve_or_time_series", contract["required_roles"])
            self.assertNotIn("prediction_score", contract["required_roles"])
            self.assertNotIn("image_class_assignment", contract["required_roles"])
            self.assertNotIn("physical_class_assignment", contract["required_roles"])
            self.assertNotIn("assignment_stability", contract["required_roles"])
            self.assertEqual(contract["missing_roles"], [])
            self.assertIn("principal_component_projection", blueprint["method_formula_plan"]["formula_families"])
            self.assertIn("macro_f1", blueprint["method_formula_plan"]["formula_families"])


if __name__ == "__main__":
    unittest.main()
