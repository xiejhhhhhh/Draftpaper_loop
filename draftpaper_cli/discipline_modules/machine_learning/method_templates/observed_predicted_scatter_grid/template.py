# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from pathlib import Path


def write_observed_predicted_metrics(
    *,
    input_csv: Path,
    observed_column: str,
    predicted_column: str,
    output_csv: Path,
) -> dict[str, float]:
    pairs: list[tuple[float, float]] = []
    for row in csv.DictReader(input_csv.open("r", encoding="utf-8-sig", newline="")):
        try:
            pairs.append((float(row[observed_column]), float(row[predicted_column])))
        except (KeyError, ValueError):
            continue
    if not pairs:
        raise ValueError("No valid observed-predicted pairs")
    y = [item[0] for item in pairs]
    yhat = [item[1] for item in pairs]
    mean_y = sum(y) / len(y)
    ss_res = sum((a - b) ** 2 for a, b in pairs)
    ss_tot = sum((a - mean_y) ** 2 for a in y)
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    mae = sum(abs(a - b) for a, b in pairs) / len(pairs)
    rmse = (ss_res / len(pairs)) ** 0.5
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["sample_count", len(pairs)])
        writer.writerow(["r2", round(r2, 6)])
        writer.writerow(["mae", round(mae, 6)])
        writer.writerow(["rmse", round(rmse, 6)])
    return {"sample_count": float(len(pairs)), "r2": r2, "mae": mae, "rmse": rmse}
