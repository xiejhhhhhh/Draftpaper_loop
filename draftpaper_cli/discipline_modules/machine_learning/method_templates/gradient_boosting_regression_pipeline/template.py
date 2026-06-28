# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations


def build_gradient_boosting_config(*, target_column: str, feature_columns: list[str]) -> dict[str, object]:
    return {
        "template_id": "gradient_boosting_regression_pipeline",
        "model_family": "gradient_boosting_regression",
        "target_column": target_column,
        "feature_columns": list(feature_columns),
        "hyperparameter_grid": {
            "n_estimators": [100, 300],
            "learning_rate": [0.03, 0.05, 0.1],
            "max_depth": [2, 3, 5],
        },
        "requires_packages": ["scikit-learn"],
        "required_artifacts": ["metrics.csv", "observed_predicted.csv"],
    }
