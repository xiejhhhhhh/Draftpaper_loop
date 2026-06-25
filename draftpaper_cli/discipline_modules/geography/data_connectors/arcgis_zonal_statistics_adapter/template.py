# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path


def build_zonal_statistics_plan(
    *,
    raster_variable: str,
    zone_id_field: str,
    statistics: list[str],
    output_json: Path,
    backend: str = "arcgis_or_project_bound_gis_runtime",
) -> dict[str, object]:
    if not statistics:
        raise ValueError("statistics must not be empty")
    plan = {
        "connector_id": "arcgis_zonal_statistics_adapter",
        "execution_backend": backend,
        "raster_variable": raster_variable,
        "zone_id_field": zone_id_field,
        "statistics": statistics,
        "required_packages": ["arcpy"],
        "status": "requires_project_bound_gis_runtime",
        "expected_outputs": ["zonal_statistics.csv", "zonal_statistics_manifest.json"],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return plan
