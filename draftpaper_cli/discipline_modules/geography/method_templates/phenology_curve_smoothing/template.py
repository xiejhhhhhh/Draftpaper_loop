# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean


def smooth_phenology_curve(
    *,
    input_csv: Path,
    output_csv: Path,
    time_column: str,
    value_column: str,
    window: int = 3,
) -> dict[str, float | str | int]:
    if window < 1:
        raise ValueError("window must be positive")
    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    series: list[tuple[str, float]] = []
    for row in rows:
        try:
            series.append((str(row.get(time_column, "")).strip(), float(str(row.get(value_column, "")).strip())))
        except ValueError:
            continue
    half = window // 2
    smoothed: list[tuple[str, float, float]] = []
    for index, (time_value, raw_value) in enumerate(series):
        left = max(0, index - half)
        right = min(len(series), index + half + 1)
        smoothed.append((time_value, raw_value, mean(value for _, value in series[left:right])))
    peak_time, peak_value = max(((time, value) for time, _, value in smoothed), key=lambda item: item[1], default=("", 0.0))
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([time_column, value_column, "smoothed_value"])
        for time_value, raw_value, smooth_value in smoothed:
            writer.writerow([time_value, raw_value, round(smooth_value, 6)])
    return {"point_count": len(smoothed), "peak_time": peak_time, "peak_value": round(peak_value, 6)}
