"""Transport-neutral implementation of the small Draftpaper MCP surface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..command_registry import COMMAND_SPECS, command_spec
from ..doctor import doctor_project, verify_next_action
from ..execution_policy import ExecutionPolicy, command_allowed_via_mcp, redact_sensitive, sanitized_environment
from ..jobs import job_status, submit_job
from ..orchestrator import status_project
from ..workflow_trace import audit_workflow_runtime
from ..write_set_guard import BoundaryViolation, resolve_confined_path


MAX_ARTIFACT_BYTES = 128 * 1024
READABLE_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml", ".md", ".txt", ".csv", ".tex", ".bib", ".html"}


def _safe(payload: Any) -> Any:
    return redact_sensitive(payload)


def _parser_schema(command: str) -> tuple[dict[str, Any], bool]:
    from ..cli import build_parser

    parser = build_parser()
    subparsers = next(action for action in parser._actions if hasattr(action, "choices") and action.choices)
    selected = subparsers.choices.get(command)
    if selected is None:
        return {"type": "object", "properties": {}, "additionalProperties": False}, False
    properties: dict[str, Any] = {}
    required = []
    for action in selected._actions:
        if action.dest == "help":
            continue
        value_type = "boolean" if action.const in {True, False} else "integer" if action.type is int else "number" if action.type is float else "array" if action.nargs in {"+", "*"} else "string"
        properties[action.dest] = {"type": value_type}
        if action.required:
            required.append(action.dest)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}, "project" in properties


def project_status(project: str) -> dict[str, Any]:
    return _safe(status_project(project))


def doctor(project: str | None = None) -> dict[str, Any]:
    return _safe(doctor_project(project))


def next_action(project: str) -> dict[str, Any]:
    return _safe(verify_next_action(project))


def plan_command(command: str) -> dict[str, Any]:
    spec = command_spec(command)
    if spec is None:
        return {"status": "not_found", "command": command}
    allowed, reason = command_allowed_via_mcp(spec)
    parser_schema, project_scoped = _parser_schema(command)
    return {
        "status": "planned" if allowed else "protected",
        "command": command,
        "mcp_allowed": allowed,
        "denial_reason": reason,
        "policy": ExecutionPolicy.from_spec(spec).as_dict(),
        "input_schema": parser_schema,
        "output_schema": spec.output_schema,
        "project_scoped": project_scoped,
    }


def _arguments(value: str | None) -> dict[str, Any]:
    payload = json.loads(value or "{}")
    if not isinstance(payload, dict):
        raise ValueError("arguments_json must contain one JSON object.")
    return payload


def _argv(command: str, arguments: dict[str, Any]) -> list[str]:
    result = [command]
    for key, value in arguments.items():
        option = "--" + str(key).replace("_", "-")
        if isinstance(value, bool):
            if value:
                result.append(option)
        elif isinstance(value, list):
            for item in value:
                result.extend([option, str(item)])
        elif value is not None:
            result.extend([option, str(value)])
    return result


def execute_command(project: str, command: str, arguments_json: str | None = None, *, confirm_science_execution: bool = False) -> dict[str, Any]:
    spec = command_spec(command)
    if spec is None:
        return {"status": "not_found", "command": command}
    allowed, reason = command_allowed_via_mcp(spec)
    if not allowed:
        return {"status": "protected", "command": command, "reason": reason, "requires_human_action": True}
    policy = ExecutionPolicy.from_spec(spec)
    if policy.risk_level in {"execute_science", "network_external"} and not confirm_science_execution:
        return {"status": "confirmation_required", "command": command, "risk_level": policy.risk_level, "requires_human_action": False, "next_step": "Call again with confirm_science_execution=true after reviewing the command plan."}
    root = Path(project).resolve(strict=True)
    _, project_scoped = _parser_schema(command)
    if not project_scoped:
        return {"status": "not_project_scoped", "command": command, "reason": "Use the dedicated MCP diagnostic tool or the local CLI for environment-level commands."}
    arguments = _arguments(arguments_json)
    if arguments.get("project") and Path(str(arguments["project"])).resolve() != root:
        return {"status": "boundary_violation", "reason": "project_argument_mismatch"}
    arguments["project"] = str(root)
    completed = subprocess.run(
        [sys.executable, "-m", "draftpaper_cli.cli", *_argv(command, arguments)],
        cwd=root,
        env=sanitized_environment(),
        capture_output=True,
        text=True,
        timeout=policy.timeout_seconds,
    )
    payload = None
    for line in reversed(completed.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            payload = candidate
            break
    return _safe({
        "status": "completed" if completed.returncode == 0 else "non_passing",
        "command": command,
        "exit_code": completed.returncode,
        "scientific_result": payload,
        "stderr": completed.stderr[-4096:],
    })


def job_submit(project: str, command: str, arguments_json: str | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
    return _safe(submit_job(project, command, arguments_json, idempotency_key))


def job_get(project: str, job_id: str) -> dict[str, Any]:
    return _safe(job_status(project, job_id))


def _select(payload: Any, selector: str | None) -> Any:
    current = payload
    for part in (selector or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def artifact_get(project: str, path: str, selector: str | None = None, max_items: int = 50, max_bytes: int = MAX_ARTIFACT_BYTES) -> dict[str, Any]:
    root = Path(project).resolve(strict=True)
    try:
        artifact = resolve_confined_path(root, path, must_exist=True)
    except BoundaryViolation as exc:
        return {"status": "boundary_violation", "message": str(exc)}
    if artifact.suffix.lower() not in READABLE_SUFFIXES or artifact.name.lower() in {".env", "jobs.sqlite3"}:
        return {"status": "forbidden_artifact_type", "suffix": artifact.suffix.lower()}
    limit = min(max(1, int(max_bytes)), MAX_ARTIFACT_BYTES)
    raw = artifact.read_bytes()
    truncated = len(raw) > limit
    text = raw[:limit].decode("utf-8", errors="replace")
    payload: Any = text
    if artifact.suffix.lower() == ".json":
        try:
            payload = _select(json.loads(text), selector)
        except json.JSONDecodeError:
            payload = text
    if isinstance(payload, list) and len(payload) > max_items:
        payload = payload[:max_items]
        truncated = True
    return _safe({"status": "read", "path": Path(path).as_posix(), "selector": selector, "content": payload, "truncated": truncated, "max_bytes": limit})


def review_summary(project: str) -> dict[str, Any]:
    root = Path(project).resolve(strict=True)
    paths = [
        "review/result_discipline_review_report.json",
        "quality_checks/manuscript_quality_release.json",
        "quality_checks/independent_review_report.json",
        "citation_audit/final_citation_audit_report.json",
    ]
    reports = {}
    for relative in paths:
        path = root / relative
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                continue
            reports[relative] = {key: value.get(key) for key in ("status", "decision", "critical_count", "major_count", "minor_count", "blocking_count") if key in value}
    return _safe({"status": "available" if reports else "not_available", "reports": reports})


def runtime_audit(project: str) -> dict[str, Any]:
    return _safe(audit_workflow_runtime(project))


def public_tool_names() -> list[str]:
    return [
        "draftpaper_project_status", "draftpaper_doctor", "draftpaper_next_action",
        "draftpaper_plan_command", "draftpaper_execute_command", "draftpaper_job_submit",
        "draftpaper_job_status", "draftpaper_artifact_get", "draftpaper_review_summary",
        "draftpaper_runtime_audit",
    ]
