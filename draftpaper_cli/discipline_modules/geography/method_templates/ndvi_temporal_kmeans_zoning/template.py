# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import math
from pathlib import Path


def _distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def cluster_temporal_profiles(
    *,
    input_csv: Path,
    output_csv: Path,
    id_column: str,
    feature_columns: list[str],
    cluster_count: int = 3,
    iterations: int = 20,
) -> dict[str, int]:
    rows = list(csv.DictReader(input_csv.open("r", encoding="utf-8-sig", newline="")))
    samples: list[tuple[str, list[float]]] = []
    for row in rows:
        try:
            samples.append((str(row.get(id_column, "")).strip(), [float(row[column]) for column in feature_columns]))
        except (KeyError, ValueError):
            continue
    if not samples:
        raise ValueError("No valid samples found")
    cluster_count = min(max(1, cluster_count), len(samples))
    centroids = [values[:] for _, values in samples[:cluster_count]]
    assignments = [0 for _ in samples]
    for _ in range(iterations):
        assignments = [min(range(cluster_count), key=lambda idx: _distance(values, centroids[idx])) for _, values in samples]
        for cluster_id in range(cluster_count):
            members = [values for assignment, (_, values) in zip(assignments, samples) if assignment == cluster_id]
            if members:
                centroids[cluster_id] = [sum(column) / len(column) for column in zip(*members)]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([id_column, "cluster_id", *feature_columns])
        for assignment, (sample_id, values) in zip(assignments, samples):
            writer.writerow([sample_id, assignment, *values])
    return {"sample_count": len(samples), "cluster_count": cluster_count}
