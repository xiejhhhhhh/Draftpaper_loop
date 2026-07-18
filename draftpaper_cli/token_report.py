"""Read-only token and recorded-cost reporting from the project token ledger."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .doctor import MANUSCRIPT_TOKEN_BUDGET, MANUSCRIPT_WRITING_STAGES
from .passport import read_jsonl
from .project_state import load_project


def _token_value(row: dict[str, Any], kind: str) -> tuple[int, str]:
    actual_key = f"actual_{kind}_tokens"
    estimated_key = f"estimated_{kind}_tokens"
    if row.get(actual_key) is not None:
        return int(row.get(actual_key) or 0), "actual"
    return int(row.get(estimated_key) or 0), "estimated"


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    input_tokens = 0
    output_tokens = 0
    actual_input_receipts = 0
    actual_output_receipts = 0
    for row in rows:
        input_value, input_source = _token_value(row, "input")
        output_value, output_source = _token_value(row, "output")
        input_tokens += input_value
        output_tokens += output_value
        actual_input_receipts += input_source == "actual"
        actual_output_receipts += output_source == "actual"
    return {
        "receipt_count": len(rows),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "actual_input_receipt_count": actual_input_receipts,
        "actual_output_receipt_count": actual_output_receipts,
    }


def _grouped(rows: list[dict[str, Any]], key: str, *, fallback: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        name = str(row.get(key) or fallback)
        groups.setdefault(name, []).append(row)
    return {name: _aggregate(items) for name, items in sorted(groups.items())}


def _active_manuscript_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, tuple[str, int, dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        task_id = str(row.get("task_id") or "")
        stage = str(row.get("stage") or "")
        if stage not in MANUSCRIPT_WRITING_STAGES or not task_id.startswith("prepare-section-writing:"):
            continue
        marker = (str(row.get("recorded_at") or ""), index)
        current = latest.get(task_id)
        if current is None or marker >= current[:2]:
            latest[task_id] = (marker[0], marker[1], row)
    return [item[2] for _, item in sorted(latest.items())]


def build_token_cost_report(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    rows = [item for item in read_jsonl(state.path / "token_ledger.jsonl") if isinstance(item, dict)]
    active_rows = _active_manuscript_rows(rows)
    active = _aggregate(active_rows)
    cost_rows = [row for row in rows if row.get("recorded_cost_usd") is not None]
    recorded_cost = round(sum(float(row.get("recorded_cost_usd") or 0.0) for row in cost_rows), 8)
    if not cost_rows:
        monetary_status = "not_available_without_recorded_price_contract"
    elif len(cost_rows) == len(rows):
        monetary_status = "complete_recorded_values"
    else:
        monetary_status = "partial_recorded_values"
    return {
        "schema_version": "dpl.token_cost_report.v1",
        "status": "passed",
        "project_id": state.metadata.get("project_id"),
        "project_path": str(state.path),
        "totals": _aggregate(rows),
        "active_manuscript": {
            **active,
            "budget": MANUSCRIPT_TOKEN_BUDGET,
            "within_budget": active["input_tokens"] <= MANUSCRIPT_TOKEN_BUDGET,
        },
        "by_stage": _grouped(rows, "stage", fallback="unassigned"),
        "by_model": _grouped(rows, "model", fallback="unrecorded"),
        "monetary_cost": {
            "status": monetary_status,
            "recorded_usd": recorded_cost,
            "receipt_count_with_recorded_cost": len(cost_rows),
            "policy": "Currency cost is reported only when the producing runtime records it; Draftpaper-loop does not infer provider prices from token counts.",
        },
    }
