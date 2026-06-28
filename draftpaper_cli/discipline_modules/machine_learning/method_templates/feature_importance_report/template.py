# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from pathlib import Path


def write_feature_importance_report(*, importances: dict[str, float], output_csv: Path) -> dict[str, int]:
    total = sum(abs(value) for value in importances.values()) or 1.0
    rows = sorted(((feature, value, abs(value) / total) for feature, value in importances.items()), key=lambda item: item[2], reverse=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["feature", "importance", "normalized_importance"])
        for feature, value, normalized in rows:
            writer.writerow([feature, round(value, 6), round(normalized, 6)])
    return {"feature_count": len(rows)}
