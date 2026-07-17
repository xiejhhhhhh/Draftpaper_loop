"""Transport-neutral implementation of the small Draftpaper MCP surface."""

from __future__ import annotations

import json
import hashlib
import hmac
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..command_registry import COMMAND_SPECS, command_spec
from ..command_contracts import command_input_schema
from ..doctor import doctor_project, verify_next_action
from ..execution_policy import ExecutionPolicy, command_allowed_via_mcp, redact_sensitive, sanitized_environment
from ..jobs import job_status, submit_job
from ..orchestrator import status_project
from ..workflow_trace import audit_workflow_runtime
from ..write_set_guard import BoundaryViolation, resolve_confined_path


MAX_ARTIFACT_BYTES = 128 * 1024
READABLE_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml", ".md", ".txt", ".csv", ".tex", ".bib", ".html"}
_CAPABILITY_SECRET = secrets.token_bytes(32)
_PATH_ARGUMENT_TOKENS = {"path", "input", "output", "report", "source", "destination", "baseline", "package", "before", "after"}
_PRIVATE_ARTIFACT_NAMES = {"external_data_locators.private.json"}
_PRIVATE_ARTIFACT_SUFFIXES = (".private.json",)
_PRIVATE_ARTIFACT_TOKENS = ("credential", "secret", "password", "token", "api_key")


def _safe(payload: Any) -> Any:
    return redact_sensitive(payload)


def _parser_schema(command: str) -> tuple[dict[str, Any], bool]:
    return command_input_schema(command)


def project_status(project: str) -> dict[str, Any]:
    return _safe(status_project(project))


def doctor(project: str | None = None) -> dict[str, Any]:
    return _safe(doctor_project(project))


def next_action(project: str) -> dict[str, Any]:
    return _safe(verify_next_action(project))


def _capability_material(project: Path, command: str, arguments: dict[str, Any], bucket: int) -> bytes:
    normalized = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{project}|{command}|{normalized}|{bucket}".encode("utf-8")


def _capability_token(project: Path, command: str, arguments: dict[str, Any], bucket: int | None = None) -> str:
    value = int(time.time() // 300) if bucket is None else bucket
    digest = hmac.new(_CAPABILITY_SECRET, _capability_material(project, command, arguments, value), hashlib.sha256).hexdigest()
    return f"{value}.{digest}"


def _valid_capability_token(token: str | None, project: Path, command: str, arguments: dict[str, Any]) -> bool:
    if not token or "." not in token:
        return False
    raw_bucket, _separator, _digest = token.partition(".")
    try:
        bucket = int(raw_bucket)
    except ValueError:
        return False
    current = int(time.time() // 300)
    if bucket not in {current, current - 1}:
        return False
    return hmac.compare_digest(token, _capability_token(project, command, arguments, bucket))


def _path_argument_violation(root: Path, arguments: dict[str, Any]) -> str | None:
    for key, raw in arguments.items():
        lowered = str(key).lower()
        if not any(token in lowered for token in _PATH_ARGUMENT_TOKENS):
            continue
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if not isinstance(value, str) or "://" in value:
                continue
            try:
                resolve_confined_path(root, value, must_exist=False)
            except BoundaryViolation:
                return str(key)
    return None


def plan_command(command: str, project: str | None = None, arguments_json: str | None = None) -> dict[str, Any]:
    spec = command_spec(command)
    if spec is None:
        return {"status": "not_found", "command": command}
    allowed, reason = command_allowed_via_mcp(spec)
    parser_schema, project_scoped = _parser_schema(command)
    policy = ExecutionPolicy.from_spec(spec)
    result = {
        "status": "planned" if allowed else "protected",
        "command": command,
        "mcp_allowed": allowed,
        "denial_reason": reason,
        "policy": policy.as_dict(),
        "input_schema": parser_schema,
        "output_schema": spec.output_schema,
        "project_scoped": project_scoped,
    }
    if project and policy.risk_level in {"execute_science", "network_external"}:
        root = Path(project).resolve(strict=True)
        arguments = _arguments(arguments_json)
        arguments["project"] = str(root)
        result["confirmation_token"] = _capability_token(root, command, arguments)
        result["confirmation_scope"] = {"project": str(root), "command": command, "arguments": arguments}
        result["confirmation_expires_within_seconds"] = 600
    return result


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


def execute_command(
    project: str,
    command: str,
    arguments_json: str | None = None,
    *,
    confirm_science_execution: bool = False,
    capability_token: str | None = None,
) -> dict[str, Any]:
    _ = confirm_science_execution  # Retained in the transport signature for compatibility; tokens are authoritative.
    spec = command_spec(command)
    if spec is None:
        return {"status": "not_found", "command": command}
    allowed, reason = command_allowed_via_mcp(spec)
    if not allowed:
        return {"status": "protected", "command": command, "reason": reason, "requires_human_action": True}
    policy = ExecutionPolicy.from_spec(spec)
    root = Path(project).resolve(strict=True)
    _, project_scoped = _parser_schema(command)
    if not project_scoped:
        return {"status": "not_project_scoped", "command": command, "reason": "Use the dedicated MCP diagnostic tool or the local CLI for environment-level commands."}
    arguments = _arguments(arguments_json)
    if arguments.get("project") and Path(str(arguments["project"])).resolve() != root:
        return {"status": "boundary_violation", "reason": "project_argument_mismatch"}
    arguments["project"] = str(root)
    path_violation = _path_argument_violation(root, arguments)
    if path_violation:
        return {"status": "boundary_violation", "reason": "path_argument_outside_project", "argument": path_violation}
    if policy.risk_level in {"execute_science", "network_external"} and not _valid_capability_token(
        capability_token, root, command, arguments
    ):
        return {
            "status": "confirmation_required",
            "command": command,
            "risk_level": policy.risk_level,
            "requires_human_action": False,
            "legacy_boolean_accepted": False,
            "next_step": "Call draftpaper_plan_command with the same project and arguments, then provide its short-lived confirmation_token.",
        }
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


def job_submit(
    project: str,
    command: str,
    arguments_json: str | None = None,
    idempotency_key: str | None = None,
    capability_token: str | None = None,
) -> dict[str, Any]:
    root = Path(project).resolve(strict=True)
    spec = command_spec(command)
    if spec is None:
        return {"status": "not_found", "command": command}
    arguments = _arguments(arguments_json)
    arguments["project"] = str(root)
    path_violation = _path_argument_violation(root, arguments)
    if path_violation:
        return {"status": "boundary_violation", "reason": "path_argument_outside_project", "argument": path_violation}
    policy = ExecutionPolicy.from_spec(spec)
    if policy.risk_level in {"execute_science", "network_external"} and not _valid_capability_token(
        capability_token, root, command, arguments
    ):
        return {"status": "confirmation_required", "command": command, "risk_level": policy.risk_level}
    return _safe(submit_job(root, command, json.dumps(arguments, ensure_ascii=False), idempotency_key))


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
    relative = artifact.relative_to(root).as_posix()
    lowered_name = artifact.name.lower()
    if lowered_name in _PRIVATE_ARTIFACT_NAMES or lowered_name.endswith(_PRIVATE_ARTIFACT_SUFFIXES) or any(token in lowered_name for token in _PRIVATE_ARTIFACT_TOKENS):
        return {"status": "forbidden_artifact", "reason_code": "private_locator" if "locator" in lowered_name else "sensitive_artifact"}
    if artifact.suffix.lower() not in READABLE_SUFFIXES or lowered_name in {".env", "jobs.sqlite3"}:
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
    return _safe({"status": "read", "path": relative, "selector": selector, "content": payload, "truncated": truncated, "max_bytes": limit})


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
