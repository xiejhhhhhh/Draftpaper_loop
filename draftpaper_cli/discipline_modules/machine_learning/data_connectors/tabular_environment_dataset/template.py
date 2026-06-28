# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
from pathlib import Path


def profile_tabular_dataset(*, input_csv: Path, target_column: str, output_json: Path) -> dict[str, object]:
    rows = list(csv.DictReader(input_csv.open("r", encoding="utf-8-sig", newline="")))
    fieldnames = list(rows[0].keys()) if rows else []
    numeric_columns: list[str] = []
    missing_by_column: dict[str, int] = {column: 0 for column in fieldnames}
    for column in fieldnames:
        numeric_count = 0
        for row in rows:
            value = str(row.get(column, "")).strip()
            if not value:
                missing_by_column[column] += 1
                continue
            try:
                float(value)
                numeric_count += 1
            except ValueError:
                pass
        if rows and numeric_count == len(rows) - missing_by_column[column]:
            numeric_columns.append(column)
    payload = {
        "connector_id": "tabular_environment_dataset",
        "row_count": len(rows),
        "column_count": len(fieldnames),
        "target_column": target_column,
        "numeric_columns": numeric_columns,
        "candidate_feature_columns": [column for column in numeric_columns if column != target_column],
        "missing_by_column": missing_by_column,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
