"""Append-only receipts that separate command writes from scientific decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .passport import project_root, utc_now
from .state_kernel import append_jsonl_locked


TRANSACTION_LEDGER_PATH = "transaction_ledger.jsonl"


def record_command_transaction(
    project: str | Path,
    *,
    command: str,
    scientific_exit_code: int,
    transaction_status: str,
    baseline_clean: bool,
    passport_event: str | None = None,
    message: str | None = None,
    run_id: str | None = None,
    command_id: str | None = None,
    parent_command_id: str | None = None,
    attempt: int = 1,
    started_at: str | None = None,
    completed_at: str | None = None,
    duration_seconds: float | None = None,
    process_status: str | None = None,
    failure_class: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "dpl.command_transaction.v2",
        "recorded_at": utc_now(),
        "command": command,
        "scientific_exit_code": int(scientific_exit_code),
        "scientific_decision": "pass" if scientific_exit_code == 0 else "non_passing_or_error",
        "transaction_status": transaction_status,
        "baseline_clean": bool(baseline_clean),
        "passport_event": passport_event,
        "message": message,
        "run_id": run_id,
        "command_id": command_id,
        "parent_command_id": parent_command_id,
        "attempt": int(attempt),
        "started_at": started_at,
        "completed_at": completed_at or utc_now(),
        "duration_seconds": duration_seconds,
        "process_status": process_status or ("completed" if transaction_status == "committed" else "failed_or_blocked"),
        "failure_class": failure_class,
    }
    append_jsonl_locked(project_root(project) / TRANSACTION_LEDGER_PATH, payload)
    return payload
