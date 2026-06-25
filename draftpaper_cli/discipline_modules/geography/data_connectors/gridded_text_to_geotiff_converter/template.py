# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def reshape_grid_values(values: Iterable[float], *, rows: int, cols: int) -> list[list[float]]:
    numbers = [float(value) for value in values]
    expected = rows * cols
    if len(numbers) != expected:
        raise ValueError(f"Expected {expected} values for a {rows}x{cols} grid, got {len(numbers)}")
    return [numbers[index:index + cols] for index in range(0, expected, cols)]


def build_grid_geotiff_plan(
    *,
    rows: int,
    cols: int,
    crs: str,
    transform: list[float],
    output_json: Path,
    nodata: float | None = None,
) -> dict[str, object]:
    if len(transform) not in {6, 9}:
        raise ValueError("transform must contain 6 affine or 9 matrix values")
    plan = {
        "connector_id": "gridded_text_to_geotiff_converter",
        "rows": rows,
        "cols": cols,
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
        "required_packages": ["numpy", "rasterio"],
        "status": "grid_export_plan_ready",
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return plan
