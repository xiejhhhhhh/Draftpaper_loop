# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


def aggregate_probe_results(*, raw_results_csv: Path, output_csv: Path, metric: str = "macro_f1") -> dict[str, int]:
    rows = list(csv.DictReader(raw_results_csv.open("r", encoding="utf-8-sig", newline="")))
    groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in rows:
        key = (str(row.get("method", "")), str(row.get("probe_head", "")), str(row.get("fraction", "")))
        try:
            groups[key].append(float(row.get(metric, "nan")))
        except ValueError:
            continue
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["method", "probe_head", "fraction", f"{metric}_mean", "n_runs"])
        for (method, probe_head, fraction), values in sorted(groups.items()):
            mean = sum(values) / len(values) if values else 0.0
            writer.writerow([method, probe_head, fraction, round(mean, 8), len(values)])
    return {"group_count": len(groups), "row_count": len(rows)}
