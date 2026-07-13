"""Append-only stage token and execution receipts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .passport import project_root, utc_now
from .state_kernel import append_jsonl_locked


TOKEN_LEDGER_PATH = "token_ledger.jsonl"


def record_stage_receipt(
    project: str | Path,
    *,
    stage: str,
    task_id: str,
    input_artifacts: list[str] | None = None,
    estimated_input_tokens: int = 0,
    actual_input_tokens: int | None = None,
    actual_output_tokens: int | None = None,
    model: str | None = None,
    status: str = "recorded",
) -> dict[str, Any]:
    root = project_root(project)
    hashes = {}
    for relative in input_artifacts or []:
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if path.is_file():
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = {
        "schema_version": "dpl.stage_receipt.v1",
        "recorded_at": utc_now(),
        "stage": stage,
        "task_id": task_id,
        "status": status,
        "input_artifact_hashes": hashes,
        "estimated_input_tokens": int(estimated_input_tokens),
        "actual_input_tokens": int(actual_input_tokens) if actual_input_tokens is not None else None,
        "actual_output_tokens": int(actual_output_tokens) if actual_output_tokens is not None else None,
        "model": model,
    }
    append_jsonl_locked(root / TOKEN_LEDGER_PATH, payload)
    return payload
