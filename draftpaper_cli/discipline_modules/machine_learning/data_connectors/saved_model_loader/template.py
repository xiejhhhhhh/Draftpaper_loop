# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path


def write_saved_model_manifest(
    *,
    model_family: str,
    expected_feature_columns: list[str],
    output_json: Path,
    model_path: str | None = None,
    target_column: str | None = None,
) -> dict[str, object]:
    payload = {
        "connector_id": "saved_model_loader",
        "model_family": model_family,
        "model_path": "{{model_path}}" if model_path else None,
        "target_column": target_column,
        "expected_feature_columns": list(expected_feature_columns),
        "required_validation": ["feature_order_check", "metric_manifest_check", "data_leakage_check"],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
