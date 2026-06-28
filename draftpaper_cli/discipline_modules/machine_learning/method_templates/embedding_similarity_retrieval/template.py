# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import math
from pathlib import Path


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: list[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def _cosine(a: list[float], b: list[float]) -> float:
    denom = _norm(a) * _norm(b)
    return _dot(a, b) / denom if denom else 0.0


def retrieve_similar_embeddings(
    *,
    embedding_csv: Path,
    query_sample_id: str,
    output_csv: Path,
    sample_column: str = "sample_id",
    embedding_prefix: str = "e",
    top_k: int = 5,
) -> dict[str, int]:
    rows = list(csv.DictReader(embedding_csv.open("r", encoding="utf-8-sig", newline="")))
    columns = [col for col in (rows[0].keys() if rows else []) if col.startswith(embedding_prefix)]
    vectors = {row[sample_column]: [float(row[col]) for col in columns] for row in rows if row.get(sample_column)}
    query = vectors.get(query_sample_id)
    if query is None:
        raise ValueError(f"query_sample_id not found: {query_sample_id}")
    scored = []
    for sample_id, vector in vectors.items():
        if sample_id == query_sample_id:
            continue
        scored.append((sample_id, _cosine(query, vector)))
    scored.sort(key=lambda item: item[1], reverse=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "sample_id", "cosine_similarity"])
        for rank, (sample_id, score) in enumerate(scored[:top_k], start=1):
            writer.writerow([rank, sample_id, round(score, 8)])
    return {"candidate_count": len(scored), "written_count": min(top_k, len(scored))}
