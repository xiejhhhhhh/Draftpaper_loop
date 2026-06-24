# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from pathlib import Path


def write_ablation_plan(*, feature_groups: dict[str, list[str]], output_table: Path) -> dict[str, float]:
    """Generic ablation plan writer; project code supplies actual model metrics."""
    output_table.parent.mkdir(parents=True, exist_ok=True)
    with output_table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["feature_group", "feature_count", "ablation_status"])
        for group, features in sorted(feature_groups.items()):
            writer.writerow([group, len(features), "planned"])
    return {"feature_group_count": float(len(feature_groups))}
