# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
from pathlib import Path


def run_template(*, input_csv: str | Path, output_dir: str | Path) -> dict[str, object]:
    """Build a simple cohort-flow table from de-identified patient rows."""
    input_path = Path(input_csv)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    included = 0
    excluded = 0
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            total += 1
            if row.get("eligible", "").strip().lower() in {"1", "true", "yes"}:
                included += 1
            else:
                excluded += 1
    table = out / "cohort_flow_table.csv"
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["stage", "count"])
        writer.writeheader()
        writer.writerow({"stage": "screened", "count": total})
        writer.writerow({"stage": "excluded", "count": excluded})
        writer.writerow({"stage": "included", "count": included})
    return {"status": "written", "cohort_flow_table": str(table), "screened_count": total, "included_count": included}
