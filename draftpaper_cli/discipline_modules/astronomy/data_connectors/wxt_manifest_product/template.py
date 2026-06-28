# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


PRODUCT_SUFFIXES = [
    ".cat",
    ".exp",
    ".img",
    "po_cl.evt",
    "po_clgti.fits",
    "sl_uf.evt",
]


def detnam_to_wxt(detnam: Any) -> str:
    text = str(detnam).strip().lower()
    if text.startswith("wxt"):
        return text
    if text.isdigit():
        return f"wxt{text}"
    return text or "wxt_unknown"


def version_to_level(version: Any) -> str:
    text = str(version).strip().lower()
    if text.startswith("lv"):
        return text
    if text in {"1", "l1"}:
        return "lv1"
    if text in {"2", "l2"}:
        return "lv2"
    return text or "lv_unknown"


def build_wxt_product_id(*, obs_id: int, detnam: Any, version: Any) -> dict[str, str]:
    detector = detnam_to_wxt(detnam)
    level = version_to_level(version)
    obs_prefix = f"ep{int(obs_id):011d}{detector}"
    return {
        "wxt_detnam": detector,
        "lv_version": level,
        "obs_prefix": obs_prefix,
        "obs_product_id": f"{obs_prefix}{level}",
    }


def build_manifest_rows(input_csv: Path, output_csv: Path, *, server_root: str = "/ep_data/wxt") -> dict[str, int]:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with input_csv.open("r", encoding="utf-8-sig", newline="") as src:
        rows = list(csv.DictReader(src))
    fieldnames = list(rows[0].keys()) if rows else ["obs_id", "detnam", "version", "source_in_det"]
    extra = ["wxt_detnam", "lv_version", "obs_prefix", "obs_product_id", "event_id", "server_product_dir", *[f"product_{i}" for i in range(len(PRODUCT_SUFFIXES))]]
    with output_csv.open("w", encoding="utf-8", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=[*fieldnames, *extra])
        writer.writeheader()
        for row in rows:
            ids = build_wxt_product_id(obs_id=int(float(row["obs_id"])), detnam=row.get("detnam"), version=row.get("version"))
            source_in_det = int(float(row.get("source_in_det", 0)))
            product_dir = f"{server_root}/{ids['lv_version']}/{ids['obs_product_id']}"
            enriched = dict(row)
            enriched.update(ids)
            enriched["event_id"] = f"{ids['obs_product_id']}s{source_in_det}"
            enriched["server_product_dir"] = product_dir
            for index, suffix in enumerate(PRODUCT_SUFFIXES):
                enriched[f"product_{index}"] = f"{product_dir}/{ids['obs_product_id']}{suffix}"
            writer.writerow(enriched)
    return {"row_count": len(rows)}
