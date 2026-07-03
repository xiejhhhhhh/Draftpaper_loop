# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def summarize_event_stream_inputs(
    *,
    event_table: Path,
    label_column: str,
    group_column: str,
    output_completeness_csv: Path,
) -> dict[str, Any]:
    with event_table.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    label_counts = Counter(str(row.get(label_column, "")).strip() for row in rows if str(row.get(label_column, "")).strip())
    groups_by_label: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        label = str(row.get(label_column, "")).strip()
        group = str(row.get(group_column, "")).strip()
        if label and group:
            groups_by_label[label].add(group)
    output_completeness_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_completeness_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["label", "event_count", "group_count", "group_holdout_feasible"])
        for label in sorted(label_counts):
            group_count = len(groups_by_label[label])
            writer.writerow([label, label_counts[label], group_count, group_count >= 2])
    return {
        "event_count": len(rows),
        "label_count": len(label_counts),
        "group_count": len({group for groups in groups_by_label.values() for group in groups}),
        "group_holdout_feasible": all(len(groups) >= 2 for groups in groups_by_label.values()) if label_counts else False,
    }


def recommended_validation_claim(summary: dict[str, Any]) -> str:
    if summary.get("group_holdout_feasible"):
        return "source_or_object_group_holdout_is_feasible"
    return "insufficient_independent_groups_for_group_holdout"
