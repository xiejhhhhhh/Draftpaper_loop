# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import math
from pathlib import Path


def _float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def compute_embedding_health(*, embedding_csv: Path, output_csv: Path, embedding_prefix: str = "e") -> dict[str, float]:
    with embedding_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    columns = [col for col in (rows[0].keys() if rows else []) if col.startswith(embedding_prefix)]
    vectors = [[_float(row[col]) for col in columns] for row in rows]
    norms = [math.sqrt(sum(value * value for value in vector)) for vector in vectors]
    mean_norm = sum(norms) / len(norms) if norms else 0.0
    zero_norm_count = sum(1 for norm in norms if norm <= 1e-12)
    variances = []
    for index in range(len(columns)):
        values = [vector[index] for vector in vectors]
        mean = sum(values) / len(values) if values else 0.0
        variances.append(sum((value - mean) ** 2 for value in values) / len(values) if values else 0.0)
    active_dimensions = sum(1 for value in variances if value > 1e-8)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["sample_count", len(rows)])
        writer.writerow(["embedding_dim", len(columns)])
        writer.writerow(["mean_norm", round(mean_norm, 8)])
        writer.writerow(["zero_norm_count", zero_norm_count])
        writer.writerow(["active_dimensions", active_dimensions])
    return {"sample_count": float(len(rows)), "embedding_dim": float(len(columns)), "mean_norm": mean_norm, "active_dimensions": float(active_dimensions)}
