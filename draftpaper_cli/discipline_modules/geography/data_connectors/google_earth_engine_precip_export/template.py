# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_precip_export_plan(
    *,
    collection_id: str,
    region_asset: str,
    start_date: str,
    end_date: str,
    reducer: str,
    output_json: Path | None = None,
    scale_m: int | None = None,
    export_target: str = "drive_or_cloud_storage",
) -> dict[str, Any]:
    if not collection_id.strip():
        raise ValueError("collection_id is required")
    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required")
    plan = {
        "connector_id": "google_earth_engine_precip_export",
        "status": "requires_user_confirmed_cloud_export",
        "collection_id": collection_id,
        "region_asset_or_geometry": region_asset,
        "date_range": {"start": start_date, "end": end_date},
        "reducer": reducer,
        "scale_m": scale_m,
        "export_target": export_target,
        "expected_outputs": ["export_manifest.json", "raster_or_zonal_table"],
        "required_packages": ["earthengine-api", "geemap"],
        "credential_env_vars": ["GOOGLE_APPLICATION_CREDENTIALS"],
        "notes": [
            "This template records a cloud-processing plan only.",
            "Project-specific code must bind geometry, scale, and export destination after user confirmation."
        ],
    }
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return plan
