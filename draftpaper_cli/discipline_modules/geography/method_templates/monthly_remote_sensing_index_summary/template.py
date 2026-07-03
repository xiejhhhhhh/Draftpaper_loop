# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev


def summarize_monthly_indices(
    *,
    input_csv: Path,
    output_csv: Path,
    month_column: str,
    value_columns: list[str],
) -> dict[str, int]:
    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        month = str(row.get(month_column, "")).strip()
        if not month:
            continue
        for column in value_columns:
            try:
                grouped[month][column].append(float(str(row.get(column, "")).strip()))
            except ValueError:
                continue
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [month_column, "row_count"]
    for column in value_columns:
        fieldnames.extend([f"{column}_mean", f"{column}_std"])
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for month in sorted(grouped, key=lambda value: int(value) if value.isdigit() else value):
            out = {month_column: month, "row_count": max(len(values) for values in grouped[month].values())}
            for column in value_columns:
                values = grouped[month].get(column, [])
                out[f"{column}_mean"] = round(mean(values), 6) if values else ""
                out[f"{column}_std"] = round(pstdev(values), 6) if len(values) > 1 else 0.0
            writer.writerow(out)
    return {"month_count": len(grouped), "value_column_count": len(value_columns)}
