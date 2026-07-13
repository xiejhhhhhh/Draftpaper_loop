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
) -> dict[str, Any]:
    payload = {
        "schema_version": "dpl.command_transaction.v1",
        "recorded_at": utc_now(),
        "command": command,
        "scientific_exit_code": int(scientific_exit_code),
        "scientific_decision": "pass" if scientific_exit_code == 0 else "non_passing_or_error",
        "transaction_status": transaction_status,
        "baseline_clean": bool(baseline_clean),
        "passport_event": passport_event,
        "message": message,
    }
    append_jsonl_locked(project_root(project) / TRANSACTION_LEDGER_PATH, payload)
    return payload
