# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class CompositeDisciplineModuleTests(unittest.TestCase):
    def test_inference_returns_primary_and_secondary_disciplines(self) -> None:
        from draftpaper_cli.discipline import infer_discipline_from_text

        profile = infer_discipline_from_text(
            "Wheat NDVI remote sensing geography with random forest, XGBoost, "
            "feature importance, spatial validation, and observed-predicted R2."
        )
        self.assertEqual(profile["discipline"], "geography")
        self.assertEqual(profile["primary_discipline"], "geography")
        self.assertIn("machine_learning", profile["secondary_disciplines"])
        self.assertEqual(profile["discipline_modules"][0], "default")
        self.assertIn("geography", profile["discipline_modules"])
        self.assertIn("machine_learning", profile["discipline_modules"])

    def test_composite_module_merges_primary_and_secondary_plugins(self) -> None:
        from draftpaper_cli.discipline_modules import get_discipline_module

        module = get_discipline_module({
            "primary_discipline": "geography",
            "secondary_disciplines": ["machine_learning"],
            "discipline_modules": ["default", "geography", "machine_learning"],
        })
        hints = module.method_blueprint_hints({})
        connector_ids = {item["connector_id"] for item in hints["data_acquisition_hints"]}
        template_ids = {item["template_id"] for item in hints["method_template_hints"]}
        review_ids = {item["rule_group_id"] for item in hints["review_rule_hints"]}
        self.assertEqual(hints["module"]["module_id"], "composite:geography+machine_learning")
        self.assertIn("google_earth_engine_precip_export", connector_ids)
        self.assertIn("tabular_environment_dataset", connector_ids)
        self.assertIn("monthly_remote_sensing_index_summary", template_ids)
        self.assertIn("random_forest_regression_gridsearch", template_ids)
        self.assertIn("shap_tree_explainer_report", template_ids)
        self.assertIn("model_statistical_validity_gate", review_ids)
        self.assertEqual(len(template_ids), len(hints["method_template_hints"]))

    def test_method_blueprint_uses_composite_module_for_cross_discipline_project(self) -> None:
        from draftpaper_cli.method_blueprint import prepare_method_blueprint
        from draftpaper_cli.project_scaffold import create_project
        from draftpaper_cli.project_state import update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea=(
                    "Wheat NDVI geography study using remote sensing features, random forest, "
                    "XGBoost, SHAP, spatial validation, and observed-predicted model diagnostics."
                ),
                field="geography machine learning agriculture",
                target_journal="General Academic Journal",
            )
            project_path = project.path
            data_dir = project_path / "data"
            data_dir.mkdir(exist_ok=True)
            (data_dir / "data_inventory.json").write_text(json.dumps({
                "files": [{
                    "path": "data/processed/table.csv",
                    "suffix": ".csv",
                    "kind": "processed",
                    "readable": True,
                    "columns": ["ndvi", "precipitation", "yield", "region_id"],
                    "row_count": 120,
                    "column_count": 4,
                }]
            }), encoding="utf-8")
            methods_dir = project_path / "methods"
            methods_dir.mkdir(exist_ok=True)
            (methods_dir / "method_requirements.json").write_text(json.dumps({
                "status": "written",
                "user_method": "Use random forest and XGBoost with SHAP and spatial validation.",
                "method_families": ["supervised_learning"],
                "required_data_features": ["ndvi", "precipitation", "yield", "region_id"],
                "primary_metric": "r2",
            }), encoding="utf-8")
            (methods_dir / "method_plan.md").write_text(
                "Use remote sensing features, random forest, XGBoost, SHAP, and spatial validation.",
                encoding="utf-8",
            )
            update_stage_status(project_path, "method_plan", "draft")
            result = prepare_method_blueprint(project_path)
            blueprint = json.loads((project_path / "methods" / "method_blueprint.json").read_text(encoding="utf-8"))
        self.assertEqual(result["discipline"], "geography")
        self.assertIn("machine_learning", result["secondary_disciplines"])
        template_ids = {item["template_id"] for item in blueprint["method_template_hints"]}
        connector_ids = {item["connector_id"] for item in blueprint["data_acquisition_hints"]}
        self.assertIn("monthly_remote_sensing_index_summary", template_ids)
        self.assertIn("random_forest_regression_gridsearch", template_ids)
        self.assertIn("tabular_environment_dataset", connector_ids)


if __name__ == "__main__":
    unittest.main()
