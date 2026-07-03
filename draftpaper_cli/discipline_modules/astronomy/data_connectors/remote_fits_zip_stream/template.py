# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import math
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PRODUCT_SUFFIXES = [
    ".cat",
    ".img",
    ".exp",
    ".lc",
    ".pha",
    ".arf",
    ".rmf",
    ".evt",
]


def build_event_product_manifest(
    *,
    input_csv: Path,
    output_csv: Path,
    remote_root: str,
    column_map: dict[str, str],
    product_suffixes: list[str] | None = None,
) -> dict[str, int]:
    """Create a generic event-to-remote-product manifest.

    The caller supplies every project-specific column name. The template writes
    normalized identifiers and remote product paths without storing credentials.
    """

    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    suffixes = product_suffixes or DEFAULT_PRODUCT_SUFFIXES
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    input_fields = list(rows[0].keys()) if rows else list(column_map.values())
    extra_fields = [
        "event_id",
        "object_id",
        "class_label",
        "detector_id",
        "product_level",
        "product_id",
        "remote_product_dir",
        "remote_product_zip_path",
        "remote_product_members_json",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_unique([*input_fields, *extra_fields]))
        writer.writeheader()
        for raw in rows:
            normalized = _normalize_row(raw, column_map)
            product_id = _product_id(
                obs_id=normalized["obs_id"],
                detector=normalized["detector"],
                product_level=normalized["product_level"],
            )
            event_id = f"{product_id}o{normalized['object_index']}"
            remote_dir = f"{remote_root.rstrip('/')}/{normalized['product_level']}/{product_id}"
            members = {suffix.strip(".").replace(".", "_") or "product": f"{remote_dir}/{product_id}{suffix}" for suffix in suffixes}
            row = dict(raw)
            row.update({
                "event_id": event_id,
                "object_id": normalized["object_id"],
                "class_label": normalized["class_label"],
                "detector_id": normalized["detector"],
                "product_level": normalized["product_level"],
                "product_id": product_id,
                "remote_product_dir": remote_dir,
                "remote_product_zip_path": f"{remote_dir}.zip",
                "remote_product_members_json": json.dumps(members, sort_keys=True),
            })
            writer.writerow(row)
    return {"row_count": len(rows)}


def inspect_zip_member_availability(
    *,
    manifest_csv: Path,
    output_csv: Path,
    zip_path_column: str = "remote_product_zip_path",
    required_suffixes: list[str] | None = None,
) -> dict[str, int]:
    """Inspect local or mounted ZIP paths without extracting full products."""

    suffixes = required_suffixes or [".cat", ".img", ".exp", ".lc", ".evt"]
    with manifest_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    output_rows: list[dict[str, Any]] = []
    for row in rows:
        zip_path = Path(str(row.get(zip_path_column) or ""))
        record = {
            "event_id": row.get("event_id", ""),
            "zip_path": str(zip_path),
            "zip_exists": zip_path.is_file(),
            "can_open_zip": False,
            "missing_members": "",
        }
        found: set[str] = set()
        if zip_path.is_file():
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    names = [Path(name).name.lower() for name in zf.namelist()]
                record["can_open_zip"] = True
                found = {suffix for suffix in suffixes if any(name.endswith(suffix.lower()) for name in names)}
            except zipfile.BadZipFile:
                record["can_open_zip"] = False
        for suffix in suffixes:
            record[f"has_{suffix.strip('.').replace('.', '_')}"] = suffix in found
        record["missing_members"] = ";".join(suffix for suffix in suffixes if suffix not in found)
        output_rows.append(record)
    _write_csv(output_csv, output_rows)
    return {"row_count": len(output_rows), "openable_zip_count": sum(1 for row in output_rows if row["can_open_zip"])}


def select_dense_event_windows(
    *,
    header_report_csv: Path,
    output_csv: Path,
    group_columns: list[str],
    time_column: str,
    max_per_group: int,
) -> dict[str, int]:
    """Select the shortest time-span window per source/object group."""

    with header_report_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(str(row.get(column, "")) for column in group_columns)].append(row)
    selected: list[dict[str, Any]] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda item: _to_float(item.get(time_column)) if _to_float(item.get(time_column)) is not None else math.inf)
        valid = [row for row in ordered if _to_float(row.get(time_column)) is not None]
        if len(valid) <= max_per_group:
            chosen = valid or ordered[:max_per_group]
        else:
            start = _shortest_window_start(valid, time_column, max_per_group)
            chosen = valid[start:start + max_per_group]
            span = _to_float(chosen[-1][time_column]) - _to_float(chosen[0][time_column])
            for row in chosen:
                row["dense_window_span"] = span
        selected.extend(chosen)
    _write_csv(output_csv, selected)
    return {"input_row_count": len(rows), "selected_row_count": len(selected)}


def write_streaming_data_contract(output_json: Path) -> dict[str, Any]:
    """Write the small-table contract expected by Draftpaper-loop data stages."""

    payload = {
        "status": "written",
        "raw_data_policy": "remote_raw_products_remain_external",
        "processed_outputs": [
            "event_level_samples.csv",
            "current_observation_tokens.csv or current_observation_tokens.parquet",
            "history_sequence_tokens.csv or history_sequence_tokens.parquet",
            "spectral_file_inventory.csv",
            "spectral_quick_features.csv",
            "file_inventory_and_quality.csv",
            "stream_parse_status.csv",
        ],
        "required_quality_checks": [
            "product_availability_rate",
            "zip_open_success_rate",
            "event_parse_success_rate",
            "current_observation_coverage",
            "history_sequence_coverage",
            "spectral_inventory_coverage",
            "class_or_label_balance",
            "group_holdout_feasibility",
        ],
        "privacy_rules": [
            "Do not store credentials in project files.",
            "Do not commit private remote paths or raw product manifests.",
            "Publish only generic templates and synthetic fixtures.",
        ],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _normalize_row(row: dict[str, str], column_map: dict[str, str]) -> dict[str, str]:
    mapped = {key: str(row.get(column, "")).strip() for key, column in column_map.items()}
    return {
        "object_id": mapped.get("object_id", ""),
        "class_label": mapped.get("class_label", ""),
        "obs_id": str(int(float(mapped.get("obs_id", "0") or 0))),
        "detector": _normalize_detector(mapped.get("detector", "")),
        "product_level": _normalize_level(mapped.get("product_level", "")),
        "object_index": str(int(float(mapped.get("object_index", "0") or 0))),
    }


def _product_id(*, obs_id: str, detector: str, product_level: str) -> str:
    return f"obs{int(obs_id):011d}{detector}{product_level}"


def _normalize_detector(value: str) -> str:
    text = value.strip().lower()
    if text.startswith("det"):
        return text
    digits = "".join(ch for ch in text if ch.isdigit())
    return f"det{int(digits)}" if digits else "det_unknown"


def _normalize_level(value: str) -> str:
    text = value.strip().lower()
    if text.startswith("lv"):
        return text
    digits = "".join(ch for ch in text if ch.isdigit())
    return f"lv{int(digits)}" if digits else "lv_unknown"


def _shortest_window_start(rows: list[dict[str, Any]], time_column: str, width: int) -> int:
    best_start = 0
    best_span = math.inf
    for start in range(0, len(rows) - width + 1):
        lo = _to_float(rows[start].get(time_column))
        hi = _to_float(rows[start + width - 1].get(time_column))
        if lo is None or hi is None:
            continue
        span = hi - lo
        if span < best_span:
            best_span = span
            best_start = start
    return best_start


def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = _unique(key for row in rows for key in row)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _unique(values: Any) -> list[str]:
    output: list[str] = []
    for value in values:
        text = str(value)
        if text not in output:
            output.append(text)
    return output


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
