# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def assess_group_holdout_feasibility(
    *,
    input_table: Path,
    target_column: str,
    group_column: str,
    output_table: Path,
    min_groups_per_class: int = 2,
) -> dict[str, Any]:
    with input_table.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    class_counts = Counter(str(row.get(target_column, "")).strip() for row in rows if str(row.get(target_column, "")).strip())
    groups_by_class: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        label = str(row.get(target_column, "")).strip()
        group = str(row.get(group_column, "")).strip()
        if label and group:
            groups_by_class[label].add(group)
    output_table.parent.mkdir(parents=True, exist_ok=True)
    with output_table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["class_label", "sample_count", "group_count", "group_holdout_feasible"])
        for label in sorted(class_counts):
            group_count = len(groups_by_class[label])
            writer.writerow([label, class_counts[label], group_count, group_count >= min_groups_per_class])
    feasible = bool(class_counts) and all(len(groups_by_class[label]) >= min_groups_per_class for label in class_counts)
    return {
        "row_count": len(rows),
        "class_count": len(class_counts),
        "group_count": len({group for groups in groups_by_class.values() for group in groups}),
        "group_holdout_feasible": feasible,
    }


def primary_metric_policy(summary: dict[str, Any]) -> str:
    return "group_holdout_primary" if summary.get("group_holdout_feasible") else "event_random_only_not_sufficient"
