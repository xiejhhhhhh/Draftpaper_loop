# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


def build_event_level_transformer_inputs(
    *,
    event_manifest_csv: Path,
    source_feature_csv: Path,
    output_event_table: Path,
    output_completeness_csv: Path,
    source_key: str = "source_id",
    event_key: str = "event_id",
    class_column: str = "category",
) -> dict[str, int]:
    with event_manifest_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        events = list(csv.DictReader(handle))
    with source_feature_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        features = list(csv.DictReader(handle))
    feature_by_source = {str(row.get(source_key, "")).strip(): row for row in features}
    output_event_table.parent.mkdir(parents=True, exist_ok=True)
    output_completeness_csv.parent.mkdir(parents=True, exist_ok=True)
    merged_rows = []
    missing_feature = 0
    for row in events:
        source_id = str(row.get(source_key, "")).strip()
        feature = feature_by_source.get(source_id, {})
        if not feature:
            missing_feature += 1
        merged = dict(row)
        for key, value in feature.items():
            if key != source_key:
                merged[f"source_{key}"] = value
        merged_rows.append(merged)
    event_fields = sorted({key for row in merged_rows for key in row.keys()})
    with output_event_table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=event_fields)
        writer.writeheader()
        writer.writerows(merged_rows)
    class_counts = Counter(str(row.get(class_column, "")).strip() for row in events if str(row.get(class_column, "")).strip())
    with output_completeness_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["event_count", len(events)])
        writer.writerow(["source_feature_count", len(features)])
        writer.writerow(["events_missing_source_features", missing_feature])
        for label, count in sorted(class_counts.items()):
            writer.writerow([f"class_count_{label}", count])
    return {
        "event_count": len(events),
        "source_feature_count": len(features),
        "events_missing_source_features": missing_feature,
    }
