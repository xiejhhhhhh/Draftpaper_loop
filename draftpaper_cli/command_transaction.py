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
    stage: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    actual_write_set: list[str] | tuple[str, ...] | None = None,
    created_paths: list[str] | tuple[str, ...] | None = None,
    modified_paths: list[str] | tuple[str, ...] | None = None,
    deleted_paths: list[str] | tuple[str, ...] | None = None,
    reused_paths: list[str] | tuple[str, ...] | None = None,
    skipped_paths: list[str] | tuple[str, ...] | None = None,
    input_artifact_refs: list[str] | tuple[str, ...] | None = None,
    validation_result_refs: list[str] | tuple[str, ...] | None = None,
    decision_refs: list[str] | tuple[str, ...] | None = None,
    baseline_changed: bool = False,
    reopen_required: bool = False,
) -> dict[str, Any]:
    payload = {
        "schema_version": "dpl.command_transaction.v3",
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
        "stage": stage,
        "actor_type": actor_type or "cli",
        "actor_id": actor_id or "draftpaper-cli",
        "actual_write_set": list(actual_write_set or []),
        "created_paths": list(created_paths or []),
        "modified_paths": list(modified_paths or []),
        "deleted_paths": list(deleted_paths or []),
        "reused_paths": list(reused_paths or []),
        "skipped_paths": list(skipped_paths or []),
        "input_artifact_refs": list(input_artifact_refs or []),
        "validation_result_refs": list(validation_result_refs or []),
        "decision_refs": list(decision_refs or []),
        "baseline_changed": bool(baseline_changed),
        "reopen_required": bool(reopen_required),
    }
    append_jsonl_locked(project_root(project) / TRANSACTION_LEDGER_PATH, payload)
    return payload
