# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


def run_split_integrity_check(*, input_table: Path, split_column: str, target_column: str, output_table: Path) -> dict[str, float]:
    rows = list(csv.DictReader(input_table.open("r", encoding="utf-8-sig", newline="")))
    split_counts: dict[str, int] = Counter(str(row.get(split_column, "")).strip() for row in rows)
    class_by_split: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        split = str(row.get(split_column, "")).strip()
        label = str(row.get(target_column, "")).strip()
        if split and label:
            class_by_split[split][label] += 1
    output_table.parent.mkdir(parents=True, exist_ok=True)
    with output_table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["split", "row_count", "class_count"])
        for split, count in sorted(split_counts.items()):
            writer.writerow([split, count, len(class_by_split.get(split, {}))])
    return {"row_count": float(len(rows)), "split_count": float(len(split_counts))}
