"""Privacy-preserving workflow traces and repeat/loop runtime diagnostics."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from .execution_policy import redact_sensitive
from .passport import read_jsonl, utc_now
from .project_state import load_project
from .state_kernel import append_jsonl_locked


TRACE_PATH = "workflow_trace.jsonl"


def begin_workflow_trace(
    project: str | Path,
    command: str,
    arguments: dict[str, Any],
    *,
    parent_command_id: str | None = None,
    attempt: int = 1,
    actor_type: str | None = None,
    actor_id: str | None = None,
    stage: str | None = None,
    intent_id: str | None = None,
    action_kind: str = "command",
) -> dict[str, Any]:
    safe = redact_sensitive(arguments)
    canonical = json.dumps(safe, sort_keys=True, ensure_ascii=True, default=str)
    now = utc_now()
    return {
        "schema_version": "dpl.workflow_trace.v2",
        "run_id": str(arguments.get("run_id") or uuid.uuid4().hex),
        "command_id": uuid.uuid4().hex,
        "parent_command_id": parent_command_id,
        "command": command,
        "attempt": int(attempt),
        "started_at": now,
        "started_monotonic": time.monotonic(),
        "input_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "argument_keys": sorted(str(key) for key in arguments if key not in {"password", "token", "api_key", "secret"}),
        "actor_type": actor_type or str(arguments.get("actor_type") or "cli"),
        "actor_id": actor_id or str(arguments.get("actor_id") or "draftpaper-cli"),
        "agent_session_id": arguments.get("agent_session_id"),
        "stage": stage,
        "intent_id": intent_id,
        "parent_intent_id": arguments.get("parent_intent_id"),
        "action_kind": action_kind,
        "input_artifact_refs": list(arguments.get("input_artifact_refs") or []),
        "output_artifact_refs": [],
        "artifact_change_summary": {},
        "validation_result_refs": [],
        "decision_refs": [],
        "reason_codes": [],
        "user_visible_summary_fragment_zh": "",
        "retry_of": arguments.get("retry_of"),
    }


def finish_workflow_trace(
    project: str | Path,
    trace: dict[str, Any],
    *,
    process_status: str,
    command_exit_code: int,
    transaction_status: str,
    scientific_decision: str,
    next_action_before: str | None = None,
    next_action_after: str | None = None,
    failure_class: str | None = None,
    output_hash: str | None = None,
    action_kind: str | None = None,
    changed_paths: list[str] | tuple[str, ...] | None = None,
    input_artifact_refs: list[str] | tuple[str, ...] | None = None,
    output_artifact_refs: list[str] | tuple[str, ...] | None = None,
    validation_result_refs: list[str] | tuple[str, ...] | None = None,
    decision_refs: list[str] | tuple[str, ...] | None = None,
    reason_codes: list[str] | tuple[str, ...] | None = None,
    user_visible_summary_fragment_zh: str | None = None,
) -> dict[str, Any]:
    payload = {key: value for key, value in trace.items() if key != "started_monotonic"}
    payload.update({
        "completed_at": utc_now(),
        "duration_seconds": round(max(0.0, time.monotonic() - float(trace.get("started_monotonic") or time.monotonic())), 6),
        "process_status": process_status,
        "command_exit_code": int(command_exit_code),
        "transaction_status": transaction_status,
        "scientific_decision": scientific_decision,
        "next_action_before": next_action_before,
        "next_action_after": next_action_after,
        "failure_class": failure_class,
        "output_hash": output_hash,
        "action_kind": action_kind or trace.get("action_kind") or "command",
        "input_artifact_refs": list(input_artifact_refs or trace.get("input_artifact_refs") or []),
        "output_artifact_refs": list(output_artifact_refs or [f"artifact:{item}" for item in (changed_paths or [])]),
        "artifact_change_summary": {
            **(trace.get("artifact_change_summary") or {}),
            "changed_paths": list(changed_paths or []),
        },
        "validation_result_refs": list(validation_result_refs or []),
        "decision_refs": list(decision_refs or []),
        "reason_codes": list(reason_codes or ([failure_class] if failure_class else [])),
        "user_visible_summary_fragment_zh": user_visible_summary_fragment_zh or trace.get("user_visible_summary_fragment_zh") or "",
    })
    append_jsonl_locked(load_project(project).path / TRACE_PATH, payload)
    return payload


def _token_rows(project_path: Path) -> list[dict[str, Any]]:
    return read_jsonl(project_path / "token_ledger.jsonl")


def audit_workflow_runtime(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    rows = read_jsonl(state.path / TRACE_PATH)
    findings: list[dict[str, Any]] = []
    commands = [str(item.get("command") or "") for item in rows]
    for index in range(2, len(commands)):
        if commands[index] == commands[index - 2] and commands[index] != commands[index - 1]:
            findings.append({"kind": "next_action_cycle", "severity": "warning", "command_ids": [rows[index - 2].get("command_id"), rows[index - 1].get("command_id"), rows[index].get("command_id")], "pattern": commands[index - 2:index + 1]})
    by_input: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        by_input.setdefault((str(row.get("command") or ""), str(row.get("input_hash") or "")), []).append(row)
    for (command, input_hash), matches in by_input.items():
        costly = sum(float(item.get("duration_seconds") or 0) for item in matches)
        if input_hash and len(matches) > 1 and costly > 1.0:
            findings.append({"kind": "duplicate_expensive_run", "severity": "warning", "command": command, "input_hash": input_hash, "attempts": len(matches), "duration_seconds": round(costly, 3)})
    failures = [row for row in rows if row.get("process_status") != "completed" or row.get("transaction_status") not in {"committed", "read_only"}]
    tokens = _token_rows(state.path)
    oversized = [item for item in tokens if int(item.get("estimated_input_tokens") or item.get("actual_input_tokens") or 0) > 18_000]
    if oversized:
        findings.append({"kind": "oversized_packet", "severity": "warning", "count": len(oversized), "task_ids": sorted({str(item.get("task_id") or "") for item in oversized})})
    return {
        "schema_version": "dpl.workflow_runtime_audit.v1",
        "status": "attention" if findings else "passed",
        "run_count": len({str(item.get("run_id") or "") for item in rows if item.get("run_id")}),
        "command_count": len(rows),
        "failure_count": len(failures),
        "findings": findings,
        "failure_classes": sorted({str(item.get("failure_class") or "unspecified") for item in failures}),
        "policy": "Trace records contain hashes, status and metering only; manuscript text and private scientific data are not copied.",
    }
