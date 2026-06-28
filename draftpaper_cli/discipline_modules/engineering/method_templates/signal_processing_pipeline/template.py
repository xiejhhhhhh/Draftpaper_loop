# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import math
from pathlib import Path


def run_template(*, input_csv: str | Path, output_dir: str | Path) -> dict[str, object]:
    """Compute simple signal features from a time-measurement table."""
    input_path = Path(input_csv)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    values = []
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            values.append(float(row["measurement"]))
    mean = sum(values) / len(values) if values else 0.0
    rms = math.sqrt(sum(value * value for value in values) / len(values)) if values else 0.0
    peak_to_peak = (max(values) - min(values)) if values else 0.0
    table = out / "signal_feature_table.csv"
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["feature", "value"])
        writer.writeheader()
        writer.writerow({"feature": "mean", "value": mean})
        writer.writerow({"feature": "rms", "value": rms})
        writer.writerow({"feature": "peak_to_peak", "value": peak_to_peak})
    return {"status": "written", "signal_feature_table": str(table), "sample_count": len(values), "rms": rms}
