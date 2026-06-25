# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / "draftpaper_cli" / "discipline_modules" / "machine_learning"


def load_template(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem + "_ml_python_data_test_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import template: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MachineLearningPythonDataPluginTests(unittest.TestCase):
    def test_machine_learning_module_exposes_modeling_and_interpretation_plugins(self) -> None:
        from draftpaper_cli.discipline_modules import get_discipline_module

        hints = get_discipline_module({"discipline": "machine_learning"}).method_blueprint_hints({})
        connector_ids = {item["connector_id"] for item in hints["data_acquisition_hints"]}
        template_ids = {item["template_id"] for item in hints["method_template_hints"]}
        review_ids = {item["rule_group_id"] for item in hints["review_rule_hints"]}
        self.assertIn("tabular_environment_dataset", connector_ids)
        self.assertIn("saved_model_loader", connector_ids)
        self.assertIn("random_forest_regression_gridsearch", template_ids)
        self.assertIn("xgboost_optuna_regression", template_ids)
        self.assertIn("gradient_boosting_regression_pipeline", template_ids)
        self.assertIn("stacking_regression_ensemble", template_ids)
        self.assertIn("observed_predicted_scatter_grid", template_ids)
        self.assertIn("feature_importance_report", template_ids)
        self.assertIn("partial_dependence_ice_analysis", template_ids)
        self.assertIn("shap_tree_explainer_report", template_ids)
        self.assertIn("model_statistical_validity_gate", review_ids)

    def test_tabular_environment_dataset_connector_profiles_columns(self) -> None:
        module = load_template(ML / "data_connectors" / "tabular_environment_dataset" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "profile.json"
            result = module.profile_tabular_dataset(
                input_csv=ML / "data_connectors" / "tabular_environment_dataset" / "fixture_environment_table.csv",
                target_column="yield",
                output_json=output,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["row_count"], 5)
        self.assertIn("ndvi", payload["numeric_columns"])

    def test_saved_model_loader_writes_model_manifest(self) -> None:
        module = load_template(ML / "data_connectors" / "saved_model_loader" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "model_manifest.json"
            result = module.write_saved_model_manifest(
                model_family="random_forest",
                expected_feature_columns=["ndvi", "precipitation"],
                output_json=output,
                model_path="/private/project/model.pkl",
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["model_family"], "random_forest")
        self.assertIn("{{model_path}}", text)
        self.assertNotIn("/private", text)

    def test_random_forest_gridsearch_template_writes_dependency_light_plan(self) -> None:
        module = load_template(ML / "method_templates" / "random_forest_regression_gridsearch" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "rf_plan.json"
            result = module.build_random_forest_gridsearch_plan(
                target_column="yield",
                feature_columns=["ndvi", "precipitation"],
                output_json=output,
            )
            text = output.read_text(encoding="utf-8")
        self.assertIn("scikit-learn", result["requires_packages"])
        self.assertIn("n_estimators", text)

    def test_xgboost_optuna_template_writes_dependency_light_plan(self) -> None:
        module = load_template(ML / "method_templates" / "xgboost_optuna_regression" / "template.py")
        plan = module.build_xgboost_optuna_plan(target_column="yield", feature_columns=["ndvi"], trial_count=20)
        self.assertEqual(plan["trial_count"], 20)
        self.assertIn("xgboost", plan["requires_packages"])

    def test_gradient_boosting_pipeline_writes_config(self) -> None:
        module = load_template(ML / "method_templates" / "gradient_boosting_regression_pipeline" / "template.py")
        config = module.build_gradient_boosting_config(target_column="yield", feature_columns=["ndvi", "lai"])
        self.assertEqual(config["model_family"], "gradient_boosting_regression")
        self.assertIn("learning_rate", config["hyperparameter_grid"])

    def test_stacking_ensemble_template_requires_base_models(self) -> None:
        module = load_template(ML / "method_templates" / "stacking_regression_ensemble" / "template.py")
        plan = module.build_stacking_ensemble_plan(
            target_column="yield",
            feature_columns=["ndvi", "precipitation"],
            base_models=["random_forest", "gradient_boosting"],
        )
        self.assertEqual(plan["base_model_count"], 2)
        self.assertIn("out_of_fold_predictions", plan["required_artifacts"])

    def test_interpretation_templates_write_reviewable_artifacts(self) -> None:
        scatter = load_template(ML / "method_templates" / "observed_predicted_scatter_grid" / "template.py")
        importance = load_template(ML / "method_templates" / "feature_importance_report" / "template.py")
        pdp = load_template(ML / "method_templates" / "partial_dependence_ice_analysis" / "template.py")
        shap = load_template(ML / "method_templates" / "shap_tree_explainer_report" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            scatter_out = Path(tmp) / "scatter.csv"
            importance_out = Path(tmp) / "importance.csv"
            scatter_result = scatter.write_observed_predicted_metrics(
                input_csv=ML / "method_templates" / "observed_predicted_scatter_grid" / "fixture_predictions.csv",
                observed_column="observed",
                predicted_column="predicted",
                output_csv=scatter_out,
            )
            importance_result = importance.write_feature_importance_report(
                importances={"ndvi": 0.62, "precipitation": 0.38},
                output_csv=importance_out,
            )
            pdp_plan = pdp.build_pdp_ice_plan(features=["ndvi", "precipitation"], target_column="yield")
            shap_plan = shap.build_shap_explainer_plan(model_family="tree_ensemble", feature_columns=["ndvi"])
        self.assertGreater(scatter_result["r2"], 0.8)
        self.assertEqual(importance_result["feature_count"], 2)
        self.assertIn("partial_dependence", pdp_plan["required_artifacts"])
        self.assertIn("shap_values", shap_plan["required_artifacts"])

    def test_model_statistical_validity_gate_flags_weak_result(self) -> None:
        module = load_template(ML / "review_rules" / "model_statistical_validity_gate" / "template.py")
        report = module.assess_model_statistical_validity(
            metrics={"r2": 0.05, "p_value": 0.12, "sample_count": 80},
            thresholds={"minimum_r2": 0.2, "maximum_p_value": 0.05, "minimum_sample_count": 100},
        )
        self.assertFalse(report["passes_gate"])
        self.assertIn("effect_size_or_fit_is_weak", report["issues"])
        self.assertIn("statistical_confidence_is_weak", report["issues"])
        self.assertIn("sample_size_is_low", report["issues"])


if __name__ == "__main__":
    unittest.main()
