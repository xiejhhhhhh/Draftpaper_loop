# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path


def run_template(*, input_csv: str | Path, output_dir: str | Path) -> dict[str, object]:
    """Summarize group means and log2 fold change for a small expression table."""
    input_path = Path(input_csv)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            values[row["feature_id"]][row["condition"]].append(float(row["measurement"]))
    table = out / "differential_table.csv"
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["feature_id", "control_mean", "case_mean", "log2_fold_change"])
        writer.writeheader()
        for feature_id, groups in sorted(values.items()):
            control = _mean(groups.get("control", []))
            case = _mean(groups.get("case", []))
            log2fc = math.log2((case + 1e-9) / (control + 1e-9)) if control is not None and case is not None else 0.0
            writer.writerow({"feature_id": feature_id, "control_mean": control or 0.0, "case_mean": case or 0.0, "log2_fold_change": log2fc})
    return {"status": "written", "differential_table": str(table), "feature_count": len(values)}


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None
