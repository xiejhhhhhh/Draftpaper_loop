# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path


def build_random_forest_gridsearch_plan(
    *,
    target_column: str,
    feature_columns: list[str],
    output_json: Path | None = None,
    cv_folds: int = 5,
) -> dict[str, object]:
    plan = {
        "template_id": "random_forest_regression_gridsearch",
        "model_family": "random_forest_regression",
        "target_column": target_column,
        "feature_columns": list(feature_columns),
        "cv_folds": cv_folds,
        "hyperparameter_grid": {
            "n_estimators": [100, 300, 500],
            "max_depth": [None, 5, 10],
            "min_samples_leaf": [1, 2, 5],
        },
        "requires_packages": ["scikit-learn"],
        "required_artifacts": ["metrics.csv", "feature_importance.csv", "observed_predicted.csv"],
    }
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return plan
