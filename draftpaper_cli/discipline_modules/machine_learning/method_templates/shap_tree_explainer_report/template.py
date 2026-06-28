# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations


def build_shap_explainer_plan(*, model_family: str, feature_columns: list[str]) -> dict[str, object]:
    return {
        "template_id": "shap_tree_explainer_report",
        "model_family": model_family,
        "feature_columns": list(feature_columns),
        "requires_packages": ["shap", "matplotlib"],
        "required_artifacts": ["shap_values", "shap_summary_table", "shap_summary_figure"],
        "fallback": "use permutation or model-native feature importance when SHAP is not feasible",
    }
