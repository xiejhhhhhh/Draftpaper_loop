# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def normalize_longitude(value: float) -> float:
    return ((float(value) + 180.0) % 360.0) - 180.0


def write_netcdf_geotiff_plan(
    *,
    variable_name: str,
    lon_values: Iterable[float],
    lat_values: Iterable[float],
    output_json: Path,
    crs: str = "EPSG:4326",
    nodata: float | None = None,
) -> dict[str, float | str | None]:
    lons = [normalize_longitude(value) for value in lon_values]
    lats = [float(value) for value in lat_values]
    if not lons or not lats:
        raise ValueError("lon_values and lat_values must not be empty")
    result = {
        "connector_id": "netcdf_to_geotiff_converter",
        "variable_name": variable_name,
        "crs": crs,
        "nodata": nodata,
        "normalized_lon_min": min(lons),
        "normalized_lon_max": max(lons),
        "lat_min": min(lats),
        "lat_max": max(lats),
        "required_packages": ["xarray", "rasterio", "netCDF4"],
        "status": "conversion_plan_ready",
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
