# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


def run_majority_baseline(*, input_table: Path, target_column: str, output_table: Path) -> dict[str, float]:
    rows = list(csv.DictReader(input_table.open("r", encoding="utf-8-sig", newline="")))
    counts = Counter(str(row.get(target_column, "")).strip() for row in rows if str(row.get(target_column, "")).strip())
    majority = max(counts.values()) if counts else 0
    accuracy = majority / len(rows) if rows else 0.0
    output_table.parent.mkdir(parents=True, exist_ok=True)
    with output_table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["row_count", len(rows)])
        writer.writerow(["class_count", len(counts)])
        writer.writerow(["majority_baseline_accuracy", round(accuracy, 6)])
    return {"row_count": float(len(rows)), "class_count": float(len(counts)), "majority_baseline_accuracy": accuracy}
