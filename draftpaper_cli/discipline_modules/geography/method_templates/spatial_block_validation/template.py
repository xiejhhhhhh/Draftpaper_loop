# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


def run_spatial_block_validation(
    *,
    input_table: Path,
    target_column: str,
    predictor_columns: list[str],
    group_column: str,
    output_table: Path,
) -> dict[str, float]:
    """Generic leave-group-out validation skeleton for geography workflows."""
    with input_table.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        group = str(row.get(group_column, "")).strip()
        if group:
            groups[group].append(row)
    group_count = len(groups)
    output_table.parent.mkdir(parents=True, exist_ok=True)
    with output_table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["row_count", len(rows)])
        writer.writerow(["group_count", group_count])
        writer.writerow(["predictor_count", len(predictor_columns)])
        writer.writerow(["spatial_validation_ready", int(group_count >= 3)])
    return {"row_count": float(len(rows)), "group_count": float(group_count), "spatial_validation_ready": float(group_count >= 3)}
