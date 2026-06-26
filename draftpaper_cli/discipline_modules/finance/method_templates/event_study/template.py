# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from pathlib import Path


def run_template(*, input_csv: str | Path, output_dir: str | Path) -> dict[str, object]:
    """Compute abnormal returns and cumulative abnormal return from a small event-study table."""
    input_path = Path(input_csv)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            asset_return = float(row["asset_return"])
            benchmark_return = float(row["benchmark_return"])
            abnormal = asset_return - benchmark_return
            rows.append({
                "date": row["date"],
                "event_id": row.get("event_id", "event"),
                "abnormal_return": abnormal,
            })
    car = 0.0
    table = out / "event_window_table.csv"
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "event_id", "abnormal_return", "cumulative_abnormal_return"])
        writer.writeheader()
        for row in rows:
            car += float(row["abnormal_return"])
            writer.writerow({**row, "cumulative_abnormal_return": car})
    return {"status": "written", "event_window_table": str(table), "row_count": len(rows), "cumulative_abnormal_return": car}
