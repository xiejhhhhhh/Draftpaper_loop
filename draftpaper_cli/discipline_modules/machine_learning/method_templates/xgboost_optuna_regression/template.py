# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations


def build_xgboost_optuna_plan(*, target_column: str, feature_columns: list[str], trial_count: int = 50) -> dict[str, object]:
    return {
        "template_id": "xgboost_optuna_regression",
        "model_family": "xgboost_regression",
        "target_column": target_column,
        "feature_columns": list(feature_columns),
        "trial_count": trial_count,
        "search_space": {
            "max_depth": [2, 12],
            "learning_rate": [0.01, 0.3],
            "subsample": [0.5, 1.0],
            "colsample_bytree": [0.5, 1.0],
        },
        "requires_packages": ["xgboost", "optuna", "scikit-learn"],
        "required_artifacts": ["best_params.json", "metrics.csv", "observed_predicted.csv"],
    }
