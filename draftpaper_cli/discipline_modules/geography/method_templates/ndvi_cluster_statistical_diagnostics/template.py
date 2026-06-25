# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, pstdev


def write_cluster_diagnostics(
    *,
    input_csv: Path,
    output_json: Path,
    cluster_column: str,
    value_column: str,
) -> dict[str, int]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in csv.DictReader(input_csv.open("r", encoding="utf-8-sig", newline="")):
        try:
            grouped[str(row.get(cluster_column, "")).strip()].append(float(str(row.get(value_column, "")).strip()))
        except ValueError:
            continue
    diagnostics = {}
    for cluster_id, values in sorted(grouped.items()):
        diagnostics[cluster_id] = {
            "count": len(values),
            "mean": round(mean(values), 6),
            "median": round(median(values), 6),
            "std": round(pstdev(values), 6) if len(values) > 1 else 0.0,
            "min": min(values),
            "max": max(values),
        }
    payload = {
        "template_id": "ndvi_cluster_statistical_diagnostics",
        "cluster_column": cluster_column,
        "value_column": value_column,
        "cluster_count": len(diagnostics),
        "diagnostics": diagnostics,
        "formal_tests_require": ["scipy", "statsmodels"],
        "review_note": "Use formal tests only when their assumptions match the discipline and sample design.",
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"cluster_count": len(diagnostics)}
