# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import re
from pathlib import Path


OBJECT_ID_PATTERN = re.compile(r"^(-?\d+)[_-]")


def parse_object_id_from_name(name: str) -> int | None:
    match = OBJECT_ID_PATTERN.match(Path(name).name)
    return int(match.group(1)) if match else None


def build_catalog_image_manifest(
    *,
    catalog_csv: Path,
    image_files: list[str],
    output_csv: Path,
    object_id_column: str = "OBJECT_ID",
    label_column: str = "morphology_label",
    ignore_labels: set[str] | None = None,
) -> dict[str, int]:
    ignore = ignore_labels or set()
    with catalog_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    catalog = {str(row.get(object_id_column, "")).strip(): row for row in rows}
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    matched = []
    missing_catalog = 0
    ignored = 0
    for file_path in image_files:
        object_id = parse_object_id_from_name(file_path)
        row = catalog.get(str(object_id)) if object_id is not None else None
        if row is None:
            missing_catalog += 1
            continue
        label = str(row.get(label_column, "")).strip()
        if label in ignore or not label:
            ignored += 1
            continue
        matched.append({"object_id": object_id, "file_path": file_path, "label": label})
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["object_id", "file_path", "label"])
        writer.writeheader()
        writer.writerows(matched)
    return {"matched_count": len(matched), "missing_catalog": missing_catalog, "ignored_label_count": ignored}
