# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations


def build_stacking_ensemble_plan(
    *,
    target_column: str,
    feature_columns: list[str],
    base_models: list[str],
    meta_model: str = "ridge_regression",
) -> dict[str, object]:
    if len(base_models) < 2:
        raise ValueError("At least two base models are required for a stacking ensemble")
    return {
        "template_id": "stacking_regression_ensemble",
        "model_family": "stacking_regression",
        "target_column": target_column,
        "feature_columns": list(feature_columns),
        "base_models": list(base_models),
        "base_model_count": len(base_models),
        "meta_model": meta_model,
        "requires_packages": ["scikit-learn"],
        "required_artifacts": ["out_of_fold_predictions", "base_model_metrics.csv", "ensemble_metrics.csv"],
    }
