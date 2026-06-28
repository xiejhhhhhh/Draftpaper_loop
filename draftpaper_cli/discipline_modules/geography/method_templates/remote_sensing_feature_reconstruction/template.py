# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence


def run_remote_sensing_feature_reconstruction(
    *,
    input_table: Path,
    index_column: str,
    target_column: str,
    output_table: Path,
    quality_column: str | None = None,
    group_column: str | None = None,
) -> dict[str, float]:
    """Generic tabular remote-sensing index summary.

    This template intentionally does not hard-code a region, date range, sensor,
    or dataset id. Project-specific code should bind those values outside this
    reusable template.
    """
    rows = list(csv.DictReader(input_table.open("r", encoding="utf-8-sig", newline="")))
    pairs: list[tuple[float, float]] = []
    for row in rows:
        if quality_column and str(row.get(quality_column, "")).strip().lower() in {"bad", "invalid", "0"}:
            continue
        try:
            x = float(str(row.get(index_column, "")).strip())
            y = float(str(row.get(target_column, "")).strip())
        except ValueError:
            continue
        pairs.append((x, y))
    n = len(pairs)
    mean_index = sum(x for x, _ in pairs) / n if n else 0.0
    mean_target = sum(y for _, y in pairs) / n if n else 0.0
    output_table.parent.mkdir(parents=True, exist_ok=True)
    with output_table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["row_count", n])
        writer.writerow(["mean_index", round(mean_index, 6)])
        writer.writerow(["mean_target", round(mean_target, 6)])
    return {"row_count": float(n), "mean_index": mean_index, "mean_target": mean_target}


def required_columns(index_column: str, target_column: str, optional_columns: Sequence[str] = ()) -> list[str]:
    return [index_column, target_column, *optional_columns]
