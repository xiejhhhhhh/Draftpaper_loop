# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import math
from pathlib import Path


def _to_float(value: object) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        number = float(str(value).strip())
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def extract_light_curve_features(
    *,
    light_curve_csv: Path,
    output_features_csv: Path,
    source_id: str = "source",
    time_column: str = "time",
    flux_column: str = "flux",
    exposure_column: str = "exposure",
) -> dict[str, float]:
    with light_curve_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fluxes = [value for value in (_to_float(row.get(flux_column)) for row in rows) if value is not None]
    times = [value for value in (_to_float(row.get(time_column)) for row in rows) if value is not None]
    exposures = [value for value in (_to_float(row.get(exposure_column)) for row in rows) if value is not None]
    n = len(fluxes)
    mean_flux = sum(fluxes) / n if n else 0.0
    variance = sum((value - mean_flux) ** 2 for value in fluxes) / (n - 1) if n > 1 else 0.0
    max_flux = max(fluxes) if fluxes else 0.0
    min_flux = min(fluxes) if fluxes else 0.0
    duration = max(times) - min(times) if len(times) > 1 else 0.0
    total_exposure = sum(exposures) if exposures else 0.0
    active_threshold = mean_flux + math.sqrt(variance) if n > 1 else mean_flux
    active_fraction = sum(1 for value in fluxes if value >= active_threshold) / n if n else 0.0
    feature = {
        "n_bins": float(n),
        "mean_flux": mean_flux,
        "std_flux": math.sqrt(variance),
        "amplitude": max_flux - min_flux,
        "duration": duration,
        "total_exposure": total_exposure,
        "active_fraction": active_fraction,
    }
    output_features_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_features_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source_id", *feature.keys()])
        writer.writerow([source_id, *[round(value, 8) for value in feature.values()]])
    return feature
