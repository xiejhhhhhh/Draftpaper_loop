"""Unified human-checkpoint summaries and Chinese offline review pages."""

from __future__ import annotations

import hashlib
import json
import os
import re
from html import escape
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json, compute_artifact_identity
from .checkpoint_digest import STAGE_SCOPE_PREFIXES, build_stage_digest, discover_stage_paths
from .execution_policy import redact_sensitive
from .passport import collect_artifacts, load_project_passport, project_root, read_jsonl, utc_now
from .state_kernel import atomic_write_json, atomic_write_text


CHECKPOINT_SUMMARY_SCHEMA = "dpl.checkpoint_summary.v3"
CHECKPOINT_SUMMARY_V4_SCHEMA = "dpl.checkpoint_summary.v4"
LEGACY_CHECKPOINT_SUMMARY_SCHEMAS = frozenset({"dpl.checkpoint_summary.v1", "dpl.checkpoint_summary.v2"})
CHECKPOINT_REVIEW_STATES = frozenset({"confirmable", "stale", "blocked", "preview_only", "legacy_unqualified"})
ARTIFACT_MANIFEST_SCHEMA = "dpl.checkpoint_artifact_manifest.v2"
CONFIRMATION_REQUEST_SCHEMA = "dpl.confirmation_request.v1"
CHANGE_REPORT_SCHEMA = "dpl.checkpoint_change_report.v1"
UNRESOLVED_ISSUES_SCHEMA = "dpl.checkpoint_unresolved_issues.v1"
AGENT_PAYLOAD_SCHEMA = "dpl.checkpoint_agent_payload.v1"
CHECKPOINT_ROOT = "review/checkpoints"

_STAGE_TITLES = {
    "research_plan": "研究蓝图与可行性确认",
    "research_plan_feasibility": "研究蓝图可行性确认",
    "data": "数据来源与数据质量确认",
    "method_plan": "方法与统计合同确认",
    "methods": "方法运行与复现证据确认",
    "result_support": "结果支撑与论断路线确认",
    "core_evidence": "关键结果与论断支撑确认",
    "plugin": "科研插件候选与许可证确认",
    "quality_checks": "最终稿与发布确认",
    "writing": "论文内容补全确认",
}

_STAGE_PREFIXES = STAGE_SCOPE_PREFIXES

_PATH_KEY_TOKENS = (
    "path",
    "file",
    "report",
    "manifest",
    "artifact",
    "output",
    "html",
    "json",
    "packet",
)


class CheckpointSummaryError(RuntimeError):
    """Raised when a reviewable checkpoint summary cannot be committed."""


def _checkpoint_summary_contract_issues(summary: Any, *, allow_legacy: bool = False) -> list[str]:
    """Return deterministic structural issues for a checkpoint summary package.

    v1/v2 summaries remain readable for migration and audit, but they are never
    treated as current confirmation packages.  The v3 contract deliberately
    validates the fields that make a page reviewable without trying to infer
    scientific meaning from arbitrary project files.
    """

    if not isinstance(summary, dict):
        return ["Checkpoint summary is not a JSON object."]
    schema = str(summary.get("schema_version") or "")
    if schema in LEGACY_CHECKPOINT_SUMMARY_SCHEMAS:
        return [] if allow_legacy else [f"Legacy checkpoint summary is read-only: {schema}."]
    if schema not in {CHECKPOINT_SUMMARY_SCHEMA, CHECKPOINT_SUMMARY_V4_SCHEMA}:
        return [f"Unsupported checkpoint summary schema: {schema or 'missing'}."]

    required = (
        "schema_version",
        "checkpoint_id",
        "checkpoint_type",
        "completed_stage",
        "stage_status",
        "review_state",
        "stage_purpose_zh",
        "stage_narrative_zh",
        "stage_deliverables",
        "transaction_changes",
        "deliverable_groups",
        "deliverable_counts",
        "identity",
        "core_metrics",
        "sample_flow",
        "validation_summary",
        "consistency_checks",
        "decision_routes",
        "decision_route_state",
        "inspection_targets",
        "artifact_manifest",
        "artifact_manifest_sha256",
        "confirmation_contract",
        "confirmation_meaning_zh",
        "rejection_or_refinement_route_zh",
        "generated",
        "modified",
        "deployed",
        "validated",
        "failed",
        "unresolved",
        "scientific_summary_zh",
        "scientific_impact",
        "test_mode",
        "test_auto_confirmation",
        "stage_summary_path",
        "artifact_manifest_path",
        "stage_summary_sha256",
        "created_at",
    )
    if schema == CHECKPOINT_SUMMARY_V4_SCHEMA:
        required = (*required, "review_requirement", "decision_status", "decision_actor_type", "authority_source", "risk_class", "stage_activity_bundle", "activity_bundle_sha256", "baseline_refs", "revision_cycle_id")
    issues = [f"Missing required checkpoint summary field: {key}" for key in required if key not in summary]
    if issues:
        return issues
    string_fields = (
        "checkpoint_id",
        "checkpoint_type",
        "completed_stage",
        "stage_purpose_zh",
        "stage_narrative_zh",
        "artifact_manifest_sha256",
        "confirmation_meaning_zh",
        "rejection_or_refinement_route_zh",
        "stage_summary_path",
        "artifact_manifest_path",
        "stage_summary_sha256",
        "created_at",
    )
    issues.extend(f"Checkpoint summary field must be a non-empty string: {key}" for key in string_fields if not isinstance(summary.get(key), str) or not summary.get(key).strip())
    list_fields = (
        "stage_deliverables",
        "deliverable_groups",
        "sample_flow",
        "validation_summary",
        "consistency_checks",
        "decision_routes",
        "inspection_targets",
        "generated",
        "modified",
        "deployed",
        "validated",
        "failed",
        "unresolved",
        "scientific_summary_zh",
        "scientific_impact",
    )
    issues.extend(f"Checkpoint summary field must be an array: {key}" for key in list_fields if not isinstance(summary.get(key), list))
    dict_fields = ("transaction_changes", "deliverable_counts", "identity", "core_metrics", "decision_route_state", "artifact_manifest", "confirmation_contract")
    issues.extend(f"Checkpoint summary field must be an object: {key}" for key in dict_fields if not isinstance(summary.get(key), dict))
    if summary.get("stage_status") not in {"ready_for_human_review", "blocked", "auto_continued"}:
        issues.append("Checkpoint summary stage_status is not recognized.")
    if summary.get("review_state") not in CHECKPOINT_REVIEW_STATES:
        issues.append("Checkpoint summary review_state is not recognized.")
    if not isinstance(summary.get("test_mode"), bool) or not isinstance(summary.get("test_auto_confirmation"), bool):
        issues.append("Checkpoint summary test_mode and test_auto_confirmation must be booleans.")
    confirmation_contract = summary.get("confirmation_contract")
    if isinstance(confirmation_contract, dict):
        for key in ("requires_user_decision", "confirmation_command_allowed", "source_of_truth", "test_auto_confirmation"):
            if key not in confirmation_contract:
                issues.append(f"Confirmation contract is missing: {key}")
        if schema == CHECKPOINT_SUMMARY_SCHEMA and confirmation_contract.get("requires_user_decision") is not True:
            issues.append("Checkpoint confirmation must always require a user decision.")
        if schema == CHECKPOINT_SUMMARY_V4_SCHEMA and not isinstance(confirmation_contract.get("requires_user_decision"), bool):
            issues.append("v4 confirmation requires requires_user_decision to be boolean.")
        if confirmation_contract.get("source_of_truth") != "canonical_evidence":
            issues.append("Checkpoint confirmation source_of_truth must be canonical_evidence.")
        expected_command_allowed = summary.get("review_state") == "confirmable" and (
            schema == CHECKPOINT_SUMMARY_SCHEMA or summary.get("review_requirement") != "notify_only"
        )
        if confirmation_contract.get("confirmation_command_allowed") is not expected_command_allowed:
            issues.append("Confirmation command permission does not match review_state.")
        if confirmation_contract.get("test_auto_confirmation") is not summary.get("test_auto_confirmation"):
            issues.append("Confirmation contract test marker does not match summary.")
    if summary.get("test_auto_confirmation") and not summary.get("test_mode"):
        issues.append("test_auto_confirmation requires test_mode=true.")
    if summary.get("review_state") == "confirmable" and summary.get("stage_status") != "ready_for_human_review":
        if schema == CHECKPOINT_SUMMARY_SCHEMA:
            issues.append("A confirmable summary must have stage_status=ready_for_human_review.")
    if schema == CHECKPOINT_SUMMARY_V4_SCHEMA:
        if summary.get("review_requirement") not in {"notify_only", "agent_delegable", "human_required"}:
            issues.append("v4 review_requirement is not recognized.")
        if summary.get("decision_status") not in {"not_required", "pending", "system_acknowledged", "agent_approved", "user_confirmed", "rejected", "refinement_required"}:
            issues.append("v4 decision_status is not recognized.")
        if summary.get("decision_actor_type") not in {"none", "system", "agent", "user"}:
            issues.append("v4 decision_actor_type is not recognized.")
        if not isinstance(summary.get("stage_activity_bundle"), dict):
            issues.append("v4 stage_activity_bundle must be an object.")
        if not isinstance(summary.get("baseline_refs"), dict):
            issues.append("v4 baseline_refs must be an object.")
    if summary.get("review_state") != "confirmable" and summary.get("confirmation_contract", {}).get("confirmation_command_allowed"):
        issues.append("Non-confirmable summary cannot allow a confirmation command.")
    return issues


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload, volatile_fields=frozenset({"created_at", "generated_at"})).encode("utf-8")).hexdigest()


def _relative_project_path(root: Path, raw: str) -> str | None:
    candidate = Path(str(raw).strip().strip('"'))
    if not str(candidate) or "://" in str(candidate):
        return None
    try:
        root_resolved = root.resolve()
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        relative = resolved.relative_to(root_resolved).as_posix()
    except (OSError, ValueError):
        return None
    return relative if relative and relative != "." and (root_resolved / relative).exists() else None


def _payload_paths(root: Path, payload: Any) -> list[str]:
    found: set[str] = set()

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, str(child_key))
            return
        if isinstance(value, list):
            for child in value:
                visit(child, key)
            return
        if not isinstance(value, str) or not any(token in key.lower() for token in _PATH_KEY_TOKENS):
            return
        relative = _relative_project_path(root, value)
        if relative:
            found.add(relative)

    visit(payload)
    return sorted(found)


def _in_stage_scope(relative: str, stage: str) -> bool:
    prefixes = _STAGE_PREFIXES.get(stage, (f"{stage}/",))
    return relative.replace("\\", "/").startswith(prefixes)


def _stage_artifacts(root: Path, stage: str, explicit_paths: list[str], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item in artifacts:
        relative = str(item.get("path") or "").replace("\\", "/")
        if relative in explicit_paths or _in_stage_scope(relative, stage):
            selected.append(item)
    for relative in explicit_paths:
        if not any(str(item.get("path")) == relative for item in selected):
            selected.append({"path": relative, "missing": not (root / relative).is_file()})
    return sorted(selected, key=lambda item: str(item.get("path") or ""))


def _artifact_manifest(
    root: Path,
    stage: str,
    explicit_paths: list[str],
    before_artifacts: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    before = {str(item.get("path")): item for item in before_artifacts or [] if isinstance(item, dict)}
    current = collect_artifacts(root)
    rows: list[dict[str, Any]] = []
    for item in _stage_artifacts(root, stage, explicit_paths, current):
        relative = str(item.get("path") or "")
        if not item.get("missing") and not (item.get("byte_sha256") or item.get("sha256")):
            path = root / relative
            if path.is_file():
                item = {**item, **compute_artifact_identity(path, relative)}
        previous = before.get(relative)
        if item.get("missing"):
            operation = "failed"
            semantic_changed = None
        elif previous is None:
            operation = "generated"
            semantic_changed = True
        elif (previous.get("byte_sha256") or previous.get("sha256")) != (item.get("byte_sha256") or item.get("sha256")):
            operation = "modified"
            semantic_changed = previous.get("semantic_sha256") != item.get("semantic_sha256")
        else:
            operation = "unchanged"
            semantic_changed = False
        rows.append(
            {
                "artifact_id": item.get("artifact_id") or hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16],
                "project_relative_path": relative,
                "artifact_role": item.get("stage") or "unknown",
                "operation": operation,
                "before_byte_sha256": previous.get("byte_sha256") or previous.get("sha256") if previous else None,
                "after_byte_sha256": item.get("byte_sha256") or item.get("sha256"),
                "before_semantic_sha256": previous.get("semantic_sha256") if previous else None,
                "after_semantic_sha256": item.get("semantic_sha256"),
                "evidence_sha256": item.get("evidence_sha256"),
                "semantic_changed": semantic_changed,
                "user_attention": "required" if operation in {"generated", "modified", "failed"} else "informational",
            }
        )
    return {
        "schema_version": ARTIFACT_MANIFEST_SCHEMA,
        "checkpoint_stage": stage,
        "artifacts": rows,
    }


def _payload_items(payload: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
    values: list[Any] = []
    for key in keys:
        value = payload.get(key)
        if value in (None, "", [], {}):
            continue
        values.extend(value if isinstance(value, list) else [value])
    return values


def _short_item(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): redact_sensitive(item) for key, item in value.items() if key not in {"absolute_path", "project_path"}}
    return {"summary_zh": redact_sensitive(str(value))}


def _decision_status(payload: dict[str, Any]) -> str:
    return str(payload.get("decision") or payload.get("status") or "completed").lower()


def _scientific_summary(stage: str, command: str, payload: dict[str, Any]) -> list[str]:
    status = _decision_status(payload)
    title = _STAGE_TITLES.get(stage, stage)
    summary = [f"{title}阶段命令 `{command}` 已返回状态 `{status}`。"]
    for key in ("reason", "message", "summary", "scientific_summary"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            summary.append(redact_sensitive(value.strip()))
        elif isinstance(value, list):
            summary.extend(redact_sensitive(str(item)) for item in value[:3])
    next_action = payload.get("next_action")
    if isinstance(next_action, dict) and next_action.get("reason"):
        summary.append(f"下一步：{redact_sensitive(str(next_action['reason']))}")
    return summary[:8]


def _inspection_targets(manifest: dict[str, Any], explicit_paths: list[str], root: Path) -> list[dict[str, str]]:
    rows = manifest.get("artifacts") or []
    ordered = [*explicit_paths, *[str(item.get("project_relative_path")) for item in rows if item.get("operation") in {"generated", "modified", "failed"}]]
    seen: set[str] = set()
    targets: list[dict[str, str]] = []
    for relative in ordered:
        if not relative or relative in seen:
            continue
        seen.add(relative)
        targets.append(
            {
                "project_relative_path": relative,
                "purpose_zh": "本阶段生成或修改的重点产物，请优先检查。",
                "exists": str((root / relative).is_file()).lower(),
            }
        )
        if len(targets) >= 5:
            break
    return targets


def _html_link(output_dir: Path, root: Path, relative: str) -> str:
    target = Path(os.path.relpath(root / relative, output_dir)).as_posix()
    return escape(target)


def _render_html(root: Path, output_dir: Path, summary: dict[str, Any], request: dict[str, Any]) -> str:
    from .checkpoint_html import render_checkpoint_html

    return render_checkpoint_html(root, output_dir, summary, request)


def _publish_checkpoint_index(root: Path, report: dict[str, Any]) -> None:
    """Publish derived checkpoint pointers after the authoritative files exist."""

    stable_id = str(report.get("checkpoint_id") or "")
    if not stable_id:
        raise CheckpointSummaryError("Cannot publish a checkpoint index without checkpoint_id.")
    relative_dir = (Path(CHECKPOINT_ROOT) / stable_id).as_posix()
    index_path = root / CHECKPOINT_ROOT / "index.json"
    index_payload: dict[str, Any] = {"schema_version": "dpl.checkpoint_index.v1", "checkpoints": []}
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                index_payload = loaded
        except (OSError, ValueError):
            index_payload = {"schema_version": "dpl.checkpoint_index.v1", "checkpoints": []}
    records = [item for item in index_payload.get("checkpoints") or [] if str(item.get("checkpoint_id")) != stable_id]
    records.append(
        {
            "checkpoint_id": stable_id,
            "checkpoint_type": report.get("checkpoint_type"),
            "stage_summary_sha256": report.get("stage_summary_sha256"),
            "stage_summary_json": f"{relative_dir}/stage_summary.json",
            "stage_summary_zh_html": f"{relative_dir}/stage_summary.zh-CN.html",
            "created_at": report.get("created_at"),
        }
    )
    index_payload["checkpoints"] = records[-200:]
    atomic_write_json(index_path, index_payload)
    atomic_write_json(
        root / CHECKPOINT_ROOT / "latest_checkpoint.json",
        {"schema_version": "dpl.latest_checkpoint.v1", "checkpoint_id": stable_id, "stage_summary_json": f"{relative_dir}/stage_summary.json"},
    )


def _checkpoint_index_records(root: Path) -> list[dict[str, Any]]:
    """Read derived checkpoint records without treating them as scientific truth."""

    index_path = root / CHECKPOINT_ROOT / "index.json"
    if not index_path.is_file():
        return []
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    records = payload.get("checkpoints") if isinstance(payload, dict) else []
    return [item for item in records if isinstance(item, dict)]


def _latest_checkpoint_record(root: Path) -> dict[str, Any] | None:
    """Return the record named by the latest pointer, if it is still readable."""

    latest_path = root / CHECKPOINT_ROOT / "latest_checkpoint.json"
    if not latest_path.is_file():
        return None
    try:
        pointer = json.loads(latest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(pointer, dict):
        return None
    relative = str(pointer.get("stage_summary_json") or "")
    if not relative:
        return None
    normalized = _relative_project_path(root, relative)
    if not normalized:
        return None
    for record in reversed(_checkpoint_index_records(root)):
        if str(record.get("stage_summary_json") or "").replace("\\", "/") == normalized:
            return {**record, **pointer}
    return {**pointer, "stage_summary_json": normalized}


def _checkpoint_record_hash(root: Path, record: dict[str, Any] | None) -> str | None:
    """Resolve a source checkpoint hash from ledger, index, or stage evidence."""

    if not record:
        return None
    if str(record.get("checkpoint_type") or record.get("stage") or "") == "result_support":
        report_path = root / "results" / "result_support_checkpoint.json"
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                report = {}
            if isinstance(report, dict) and report.get("checkpoint_sha256"):
                return str(report["checkpoint_sha256"])
    for key in ("hash", "checkpoint_hash", "checkpoint_sha256"):
        value = record.get(key)
        if value:
            return str(value)
    relative = str(record.get("stage_summary_json") or "")
    summary_path = root / relative if relative else None
    if summary_path and summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            summary = {}
        identity = summary.get("identity") if isinstance(summary, dict) else {}
        if isinstance(identity, dict) and identity.get("checkpoint_hash"):
            return str(identity["checkpoint_hash"])
    return None


def _select_checkpoint_record(root: Path, checkpoint_hash: str | None = None) -> dict[str, Any] | None:
    """Select the current checkpoint, preferring the derived latest pointer."""

    events = [item for item in read_jsonl(root / "checkpoint_ledger.jsonl") if item.get("kind") == "checkpoint"]
    index_records = _checkpoint_index_records(root)
    latest = _latest_checkpoint_record(root)
    candidates = [*reversed(events), *reversed(index_records)]
    if checkpoint_hash:
        for record in candidates:
            if str(record.get("hash") or "") == checkpoint_hash or str(record.get("stage_summary_sha256") or "") == checkpoint_hash:
                return record
        if latest and _checkpoint_record_hash(root, latest) == checkpoint_hash:
            return latest
        for record in candidates:
            if _checkpoint_record_hash(root, record) == checkpoint_hash:
                return record
        return None
    if latest:
        return latest
    if index_records:
        return index_records[-1]
    return events[-1] if events else None


def write_stage_summary(
    project: str | Path,
    *,
    stage: str,
    command: str,
    payload: dict[str, Any] | None = None,
    before_artifacts: list[dict[str, Any]] | None = None,
    checkpoint_id: str | None = None,
    checkpoint_hash: str | None = None,
    publish_index: bool = True,
) -> dict[str, Any]:
    """Write the portable summary, artifact manifest, request and Chinese HTML."""

    root = project_root(project)
    data = dict(payload or {})
    test_auto_confirmation = bool(data.get("test_mode") is True and data.get("test_auto_confirmation") is True)
    explicit_paths = sorted(set(_payload_paths(root, data) + discover_stage_paths(root, stage)))
    current = collect_artifacts(root)
    identity_seed = {
        "stage": stage,
        "command": command,
        "artifacts": [(item.get("path"), item.get("semantic_sha256"), item.get("evidence_sha256")) for item in current if _in_stage_scope(str(item.get("path") or ""), stage)],
    }
    stable_id = checkpoint_id or f"{stage}-{_hash_payload(identity_seed)[:12]}"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", stable_id):
        raise CheckpointSummaryError("checkpoint_id contains unsafe path characters")
    output_dir = root / CHECKPOINT_ROOT / stable_id
    manifest = _artifact_manifest(root, stage, explicit_paths, before_artifacts)
    digest = build_stage_digest(
        root,
        stage=stage,
        command=command,
        payload=data,
        artifact_manifest=manifest,
        checkpoint_hash=checkpoint_hash,
        preview_only=bool(data.get("preview_only")),
    )
    manifest["artifacts"] = digest["stage_deliverables"]
    generated = digest["transaction_changes"].get("generated") or []
    modified = digest["transaction_changes"].get("modified") or []
    status = _decision_status(data)
    failed_values = _payload_items(data, ("errors", "error", "failure", "failure_reason"))
    if status in {"error", "failed", "blocked", "failure"} and not failed_values:
        failed_values = [f"命令返回状态：{status}"]
    unresolved_values = _payload_items(data, ("unresolved", "unresolved_issues", "pending", "pending_tasks", "missing", "warnings"))
    unresolved_values.extend(digest.get("unresolved") or [])
    review_state = str(digest.get("review_state") or "confirmable")
    stage_status = "ready_for_human_review" if review_state == "confirmable" and status not in {"error", "failed", "blocked"} else "blocked"
    summary: dict[str, Any] = {
        "schema_version": CHECKPOINT_SUMMARY_SCHEMA,
        "checkpoint_id": stable_id,
        "checkpoint_type": stage,
        "checkpoint_title_zh": _STAGE_TITLES.get(stage, f"{stage} 阶段人工确认"),
        "completed_stage": stage,
        "command": command,
        "stage_status": stage_status,
        "review_state": review_state,
        "stage_purpose_zh": digest.get("stage_purpose_zh"),
        "stage_narrative_zh": digest.get("stage_narrative_zh"),
        "stage_deliverables": digest.get("stage_deliverables") or [],
        "transaction_changes": digest.get("transaction_changes") or {},
        "deliverable_groups": digest.get("deliverable_groups") or [],
        "deliverable_counts": digest.get("deliverable_counts") or {},
        "key_findings": digest.get("key_findings") or [],
        "claim_boundaries": digest.get("claim_boundaries") or [],
        "decision_routes": digest.get("decision_routes") or [],
        "decision_route_state": digest.get("decision_route_state") or {},
        "validation_summary": digest.get("validation_summary") or [],
        "consistency_checks": digest.get("consistency_checks") or [],
        "identity": digest.get("identity") or {},
        "core_metrics": digest.get("core_metrics") or {},
        "sample_flow": (digest.get("core_metrics") or {}).get("sample_flow") or [],
        "generated": generated,
        "modified": modified,
        "deployed": [_short_item(item) for item in _payload_items(data, ("deployed", "deployment", "deployment_state"))],
        "validated": ([{"summary_zh": f"{command} 返回 `{status}`，请结合下方产物检查。"}] if status in {"pass", "passed", "success", "completed", "written", "review_required", "confirmation_required", "checkpoint_created"} else []),
        "failed": [_short_item(item) for item in failed_values],
        "unresolved": [_short_item(item) for item in unresolved_values],
        "scientific_summary_zh": [digest.get("stage_narrative_zh") or item for item in _scientific_summary(stage, command, data)[:1]],
        "scientific_impact": [
            "本摘要只描述当前阶段的产物和状态，不把候选、fixture 或 metadata 误写成论文证据。",
            f"下游影响由当前命令 `{command}` 的状态和确认决定。",
        ],
        "inspection_targets": digest.get("inspection_targets") or _inspection_targets(manifest, explicit_paths, root),
        "artifact_manifest": manifest,
        "upstream_bindings": data.get("upstream_bindings") or data.get("bindings") or {},
        "runtime_fingerprint": data.get("runtime_fingerprint"),
        "test_mode": bool(data.get("test_mode")),
        "test_auto_confirmation": test_auto_confirmation,
        "confirmation_contract": {
            "requires_user_decision": True,
            "confirmation_command_allowed": review_state == "confirmable",
            "source_of_truth": "canonical_evidence",
            "test_auto_confirmation": test_auto_confirmation,
        },
        "confirmation_meaning_zh": (
            f"确认后将冻结 `{stage}` 阶段当前产物及其证据身份，并允许状态机按照该阶段的下游路线继续。"
            if review_state == "confirmable"
            else f"当前 `{stage}` 阶段存在证据身份或完整性问题，只能审阅，不能确认；需先按恢复路线生成新的摘要。"
        ) + "确认不等于替用户判断科学结论正确。",
        "rejection_or_refinement_route_zh": "拒绝或要求修改后保留本次摘要和审计记录，先按下一步修复路线更新上游内容，再生成新的摘要和 hash；不直接覆盖本次确认版本。",
        "created_at": utc_now(),
    }
    manifest_hash = _hash_payload(manifest)
    relative_dir = (Path(CHECKPOINT_ROOT) / stable_id).as_posix()
    summary["stage_summary_path"] = f"{relative_dir}/stage_summary.json"
    summary["artifact_manifest_path"] = f"{relative_dir}/artifact_manifest.json"
    summary["artifact_manifest_sha256"] = manifest_hash
    summary_hash = _hash_payload(summary)
    summary["stage_summary_sha256"] = summary_hash
    contract_issues = _checkpoint_summary_contract_issues(summary)
    if contract_issues:
        raise CheckpointSummaryError("Checkpoint summary contract failed: " + "; ".join(contract_issues))
    next_action = data.get("next_action") if isinstance(data.get("next_action"), dict) else {}
    if checkpoint_hash:
        confirmation_command = f'python -m draftpaper_cli.cli resume --project "{root}" --checkpoint-hash {checkpoint_hash}'
    else:
        confirmation_command = data.get("confirmation_command") or next_action.get("cli")
    refinement_command = data.get("refinement_command") or next_action.get("cli")
    if review_state != "confirmable":
        confirmation_command = None
    request: dict[str, Any] = {
        "schema_version": CONFIRMATION_REQUEST_SCHEMA,
        "checkpoint_id": stable_id,
        "checkpoint_type": stage,
        "stage_summary_sha256": summary_hash,
        "summary_schema": CHECKPOINT_SUMMARY_SCHEMA,
        "checkpoint_hash": checkpoint_hash,
        "allowed_decisions": ["confirm", "refine", "reject"],
        "confirmation_command": confirmation_command,
        "refinement_command": refinement_command,
        "recovery_command": next_action.get("cli"),
        "review_state": review_state,
        "requires_user_decision": True,
        "test_auto_confirmation": test_auto_confirmation,
        "created_at": utc_now(),
    }
    if review_state == "confirmable" and not request.get("confirmation_command"):
        request["confirmation_command"] = f"python -m draftpaper_cli.cli resume --project <project> --checkpoint-hash {checkpoint_hash or summary_hash[:12]}"
    relative_dir = (Path(CHECKPOINT_ROOT) / stable_id).as_posix()
    change_report = {
        "schema_version": CHANGE_REPORT_SCHEMA,
        "checkpoint_id": stable_id,
        "checkpoint_type": stage,
        "generated": generated,
        "modified": modified,
        "deployed": summary["deployed"],
        "validated": summary["validated"],
        "failed": summary["failed"],
        "unresolved": summary["unresolved"],
        "stage_summary_sha256": summary_hash,
        "artifact_manifest_sha256": manifest_hash,
    }
    unresolved_report = {
        "schema_version": UNRESOLVED_ISSUES_SCHEMA,
        "checkpoint_id": stable_id,
        "status": "blocked" if summary["stage_status"] == "blocked" else "review_required" if summary["unresolved"] else "none",
        "issues": summary["unresolved"],
        "stage_summary_sha256": summary_hash,
    }
    agent_payload = {
        "schema_version": AGENT_PAYLOAD_SCHEMA,
        "summary_schema": summary["schema_version"],
        "checkpoint_id": stable_id,
        "stage": stage,
        "stage_status": summary["stage_status"],
        "review_state": summary["review_state"],
        "stage_purpose_zh": summary["stage_purpose_zh"],
        "stage_narrative_zh": summary["stage_narrative_zh"],
        "deliverable_counts": summary["deliverable_counts"],
        "sample_flow": summary["sample_flow"],
        "stage_summary_zh_html": {
            "project_relative_path": f"{relative_dir}/stage_summary.zh-CN.html",
            "absolute_path": str((output_dir / "stage_summary.zh-CN.html").resolve()),
        },
        "stage_summary_json": str((output_dir / "stage_summary.json").resolve()),
        "artifact_manifest": str((output_dir / "artifact_manifest.json").resolve()),
        "confirmation_request": str((output_dir / "confirmation_request.json").resolve()),
        "primary_artifacts": [
            {
                "project_relative_path": str(item.get("project_relative_path") or ""),
                "absolute_path": str((root / str(item.get("project_relative_path"))).resolve()),
            }
            for item in summary["inspection_targets"]
            if item.get("project_relative_path")
        ],
        "unresolved_issues": summary["unresolved"],
        "confirmation_command": request["confirmation_command"],
        "confirmation_meaning_zh": summary["confirmation_meaning_zh"],
        "confirmation_contract": summary["confirmation_contract"],
        "test_mode": summary["test_mode"],
        "test_auto_confirmation": test_auto_confirmation,
        "stage_summary_sha256": summary_hash,
    }
    atomic_write_json(output_dir / "artifact_manifest.json", manifest)
    atomic_write_json(output_dir / "stage_summary.json", summary)
    atomic_write_json(output_dir / "confirmation_request.json", request)
    atomic_write_json(output_dir / "change_report.json", change_report)
    atomic_write_json(output_dir / "unresolved_issues.json", unresolved_report)
    atomic_write_json(output_dir / "agent_payload.json", agent_payload)
    atomic_write_text(output_dir / "stage_summary.zh-CN.html", _render_html(root, output_dir, summary, request))
    required_files = (
        output_dir / "stage_summary.json",
        output_dir / "artifact_manifest.json",
        output_dir / "confirmation_request.json",
        output_dir / "change_report.json",
        output_dir / "unresolved_issues.json",
        output_dir / "agent_payload.json",
        output_dir / "stage_summary.zh-CN.html",
    )
    if not all(path.is_file() for path in required_files):
        missing = ", ".join(str(path.name) for path in required_files if not path.is_file())
        raise CheckpointSummaryError(f"Checkpoint summary is incomplete; missing: {missing}")
    if publish_index:
        _publish_checkpoint_index(root, {**summary, "checkpoint_type": stage})
    relative_dir = (Path(CHECKPOINT_ROOT) / stable_id).as_posix()
    return {
        "checkpoint_id": stable_id,
        "stage_summary_sha256": summary_hash,
        "artifact_manifest_sha256": manifest_hash,
        "project_relative_dir": relative_dir,
        "stage_summary_json": f"{relative_dir}/stage_summary.json",
        "stage_summary_zh_html": f"{relative_dir}/stage_summary.zh-CN.html",
        "artifact_manifest": f"{relative_dir}/artifact_manifest.json",
        "confirmation_request": f"{relative_dir}/confirmation_request.json",
        "change_report": f"{relative_dir}/change_report.json",
        "unresolved_issues_report": f"{relative_dir}/unresolved_issues.json",
        "agent_payload": f"{relative_dir}/agent_payload.json",
        "absolute_stage_summary_zh_html": str((output_dir / "stage_summary.zh-CN.html").resolve()),
        "absolute_stage_summary_json": str((output_dir / "stage_summary.json").resolve()),
        "absolute_artifact_manifest": str((output_dir / "artifact_manifest.json").resolve()),
        "absolute_confirmation_request": str((output_dir / "confirmation_request.json").resolve()),
        "absolute_change_report": str((output_dir / "change_report.json").resolve()),
        "absolute_unresolved_issues": str((output_dir / "unresolved_issues.json").resolve()),
        "absolute_agent_payload": str((output_dir / "agent_payload.json").resolve()),
        "unresolved_issues": summary["unresolved"],
        "inspection_targets": summary["inspection_targets"],
        "created_at": summary["created_at"],
        "checkpoint_type": stage,
    }


def write_stage_summary_v4(
    project: str | Path,
    *,
    stage: str,
    command: str,
    payload: dict[str, Any] | None = None,
    before_artifacts: list[dict[str, Any]] | None = None,
    checkpoint_id: str | None = None,
    checkpoint_hash: str | None = None,
    publish_index: bool = True,
) -> dict[str, Any]:
    """Write the current v4 review package while preserving v3 compatibility.

    The v3 writer remains available for read-only legacy fixtures.  Production
    checkpoint entry points call this adapter so JSON, HTML, and Agent output
    share one activity bundle and one semantic summary hash.
    """

    root = project_root(project)
    data = dict(payload or {})
    from .stage_activity import build_stage_activity_bundle
    from .review_policy import classify_checkpoint_risk, classify_review_requirement
    from .scientific_baseline import load_active_baseline
    from .revision_cycle import load_active_revision_cycle

    base = write_stage_summary(
        root,
        stage=stage,
        command=command,
        payload=data,
        before_artifacts=before_artifacts,
        checkpoint_id=checkpoint_id,
        checkpoint_hash=checkpoint_hash,
        publish_index=False,
    )
    output_dir = root / base["project_relative_dir"]
    summary_path = output_dir / "stage_summary.json"
    request_path = output_dir / "confirmation_request.json"
    agent_path = output_dir / "agent_payload.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    request = json.loads(request_path.read_text(encoding="utf-8-sig"))
    activity = build_stage_activity_bundle(
        root,
        stage=stage,
        command=command,
        before_artifacts=before_artifacts,
        activity_rows=data.get("activity_rows") if isinstance(data.get("activity_rows"), list) else None,
        stage_goal_zh=str(summary.get("stage_purpose_zh") or ""),
    )
    activity_path = output_dir / "stage_activity_bundle.json"
    atomic_write_json(activity_path, activity)
    baseline = load_active_baseline(root)
    cycle = load_active_revision_cycle(root)
    from .review_policy import decision_receipt_for_checkpoint

    receipt = decision_receipt_for_checkpoint(root, checkpoint_hash) if checkpoint_hash else None
    risk_class = classify_checkpoint_risk(summary)
    requirement = classify_review_requirement(summary)
    decision_status = str((receipt or {}).get("decision_status") or "pending")
    decision_actor_type = str((receipt or {}).get("actor_type") or "none")
    authority_source = (receipt or {}).get("authority_source") or {"policy": "review_policy", "policy_mode": "manual"}
    summary["schema_version"] = CHECKPOINT_SUMMARY_V4_SCHEMA
    summary["stage_narrative_zh"] = activity.get("narrative_zh") or summary.get("stage_narrative_zh")
    summary["scientific_summary_zh"] = [summary["stage_narrative_zh"]]
    summary["review_requirement"] = requirement
    summary["decision_status"] = decision_status
    summary["decision_actor_type"] = decision_actor_type
    summary["authority_source"] = authority_source
    summary["risk_class"] = risk_class
    summary["stage_activity_bundle"] = activity
    summary["activity_bundle_sha256"] = activity["bundle_sha256"]
    summary["baseline_refs"] = {
        "active_baseline_id": (baseline or {}).get("baseline_id"),
        "active_baseline_sha256": (baseline or {}).get("baseline_sha256"),
        "parent_baseline_id": (baseline or {}).get("parent_baseline_id"),
        "revision_cycle_id": (cycle or {}).get("revision_cycle_id"),
        "revision_cycle_sha256": (cycle or {}).get("revision_cycle_sha256"),
    }
    summary["revision_cycle_id"] = (cycle or {}).get("revision_cycle_id")
    summary["activity_summary_zh"] = activity.get("narrative_zh")
    summary["generated"] = activity.get("generated") or summary.get("generated") or []
    summary["modified"] = activity.get("modified") or summary.get("modified") or []
    summary["unresolved"] = sorted({json.dumps(item, ensure_ascii=False, sort_keys=True) for item in [*(summary.get("unresolved") or []), *(activity.get("unresolved") or [])]})
    summary["unresolved"] = [json.loads(item) for item in summary["unresolved"]]
    summary["confirmation_contract"] = {
        "requires_user_decision": requirement != "notify_only" and decision_status not in {"agent_approved", "user_confirmed", "system_acknowledged"},
        "confirmation_command_allowed": summary.get("review_state") == "confirmable" and requirement != "notify_only" and decision_status not in {"agent_approved", "user_confirmed"},
        "source_of_truth": "canonical_evidence",
        "test_auto_confirmation": bool(summary.get("test_auto_confirmation")),
    }
    summary["stage_status"] = "auto_continued" if requirement == "notify_only" else summary.get("stage_status")
    summary.pop("stage_summary_sha256", None)
    summary_hash = _hash_payload(summary)
    summary["stage_summary_sha256"] = summary_hash
    request["summary_schema"] = CHECKPOINT_SUMMARY_V4_SCHEMA
    request["stage_summary_sha256"] = summary_hash
    request["review_requirement"] = requirement
    request["decision_status"] = decision_status
    request["requires_user_decision"] = summary["confirmation_contract"]["requires_user_decision"]
    if not summary["confirmation_contract"]["confirmation_command_allowed"]:
        request["confirmation_command"] = None
    agent = json.loads(agent_path.read_text(encoding="utf-8-sig"))
    agent.update(
        {
            "summary_schema": CHECKPOINT_SUMMARY_V4_SCHEMA,
            "stage_narrative_zh": summary["stage_narrative_zh"],
            "review_requirement": requirement,
            "decision_status": decision_status,
            "decision_actor_type": decision_actor_type,
            "risk_class": risk_class,
            "authority_source": authority_source,
            "stage_activity_bundle": str(activity_path.resolve()),
            "activity_bundle_sha256": activity["bundle_sha256"],
            "baseline_refs": summary["baseline_refs"],
            "revision_cycle_id": summary.get("revision_cycle_id"),
            "stage_summary_sha256": summary_hash,
            "confirmation_contract": summary["confirmation_contract"],
        }
    )
    atomic_write_json(summary_path, summary)
    atomic_write_json(request_path, request)
    atomic_write_json(agent_path, agent)
    atomic_write_text(output_dir / "stage_summary.zh-CN.html", _render_html(root, output_dir, summary, request))
    if publish_index:
        _publish_checkpoint_index(root, {**summary, "checkpoint_type": stage})
    return {
        **base,
        "stage_summary_sha256": summary_hash,
        "absolute_stage_summary_zh_html": str((output_dir / "stage_summary.zh-CN.html").resolve()),
        "absolute_stage_summary_json": str(summary_path.resolve()),
        "absolute_agent_payload": str(agent_path.resolve()),
        "absolute_confirmation_request": str(request_path.resolve()),
        "stage_activity_bundle": str(activity_path.resolve()),
        "activity_bundle_sha256": activity["bundle_sha256"],
        "review_requirement": requirement,
        "decision_status": decision_status,
        "decision_actor_type": decision_actor_type,
        "risk_class": risk_class,
    }


def show_checkpoint_summary(project: str | Path, checkpoint_hash: str | None = None, language: str = "zh-CN") -> dict[str, Any]:
    """Read one checkpoint summary and expose exact local paths without writing state."""

    root = project_root(project)
    selected = _select_checkpoint_record(root, checkpoint_hash)
    relative = str((selected or {}).get("stage_summary_json") or "")
    relative = _relative_project_path(root, relative) if relative else None
    summary_path = root / relative if relative else None
    required = (
        summary_path,
        summary_path.parent / "stage_summary.zh-CN.html" if summary_path else None,
        summary_path.parent / "artifact_manifest.json" if summary_path else None,
        summary_path.parent / "confirmation_request.json" if summary_path else None,
        summary_path.parent / "change_report.json" if summary_path else None,
        summary_path.parent / "unresolved_issues.json" if summary_path else None,
        summary_path.parent / "agent_payload.json" if summary_path else None,
    )
    if not summary_path or not all(path is not None and path.is_file() for path in required):
        return {"status": "not_found", "project_path": str(root), "checkpoint_hash": checkpoint_hash, "language": language}
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    schema = str(summary.get("schema_version") or "")
    request_path = summary_path.parent / "confirmation_request.json"
    if schema == CHECKPOINT_SUMMARY_V4_SCHEMA and not (summary_path.parent / "stage_activity_bundle.json").is_file():
        return {
            "status": "invalid_summary",
            "project_path": str(root),
            "checkpoint_hash": _checkpoint_record_hash(root, selected) or checkpoint_hash,
            "language": language,
            "review_state": summary.get("review_state") or "unknown",
            "reasons": ["Missing v4 stage_activity_bundle.json companion."],
            "summary": summary,
        }
    legacy = schema in LEGACY_CHECKPOINT_SUMMARY_SCHEMAS
    contract_issues = _checkpoint_summary_contract_issues(summary)
    if not legacy and contract_issues:
        return {
            "status": "invalid_summary",
            "project_path": str(root),
            "checkpoint_hash": _checkpoint_record_hash(root, selected) or checkpoint_hash,
            "language": language,
            "review_state": summary.get("review_state") or "unknown",
            "reasons": contract_issues,
            "summary": summary,
        }
    return {
        "status": "legacy_summary" if legacy else "ready_for_human_review",
        "project_path": str(root),
        "checkpoint_hash": _checkpoint_record_hash(root, selected) or checkpoint_hash,
        "language": language,
        "review_state": summary.get("review_state") or ("legacy" if legacy else "unknown"),
        "requires_preview": legacy,
        "preview_command": (
            f'python -m draftpaper_cli.cli preview-checkpoint-summary --project "{root}"'
            if legacy
            else None
        ),
        "summary": summary,
        "summary_schema": schema,
        "contract_issues": [],
        "stage_summary_zh_html": {
            "project_relative_path": summary_path.parent.joinpath("stage_summary.zh-CN.html").relative_to(root).as_posix(),
            "absolute_path": str(summary_path.parent.joinpath("stage_summary.zh-CN.html").resolve()),
            "source_semantic_sha256": summary.get("stage_summary_sha256"),
        },
        "artifact_manifest": str(summary_path.parent.joinpath("artifact_manifest.json").resolve()),
        "confirmation_request": str(request_path.resolve()),
        "change_report": str(summary_path.parent.joinpath("change_report.json").resolve()),
        "unresolved_issues_report": str(summary_path.parent.joinpath("unresolved_issues.json").resolve()),
        "agent_payload": str(summary_path.parent.joinpath("agent_payload.json").resolve()),
        "stage_activity_bundle": (
            str(summary_path.parent.joinpath("stage_activity_bundle.json").resolve())
            if schema == CHECKPOINT_SUMMARY_V4_SCHEMA
            else None
        ),
        "review_decision_receipt": (
            str(summary_path.parent.joinpath("review_decision_receipt.json").resolve())
            if summary_path.parent.joinpath("review_decision_receipt.json").is_file()
            else None
        ),
        "decision_status": summary.get("decision_status") or "pending",
        "primary_artifacts": summary.get("inspection_targets") or [],
        "unresolved_issues": summary.get("unresolved") or [],
    }


def preview_checkpoint_summary(project: str | Path, checkpoint_hash: str | None = None) -> dict[str, Any]:
    """Render an enriched, non-consumable view without changing checkpoint state."""

    root = project_root(project)
    selected = _select_checkpoint_record(root, checkpoint_hash)
    if not selected:
        return {"status": "not_found", "project_path": str(root)}
    stage = str(selected.get("stage") or "")
    stage = stage or str(selected.get("checkpoint_type") or "")
    checkpoint_id = str(selected.get("checkpoint_id") or f"{stage}-preview") + "-preview"
    source_hash = _checkpoint_record_hash(root, selected) or checkpoint_hash
    preview = write_stage_summary(
        root,
        stage=stage,
        command="preview-checkpoint-summary",
        payload={
            "status": "preview_only",
            "preview_only": True,
            "next_action": selected.get("next_action") or {},
            "source_checkpoint_hash": source_hash,
        },
        before_artifacts=load_project_passport(root).get("artifacts") or [],
        checkpoint_id=checkpoint_id,
        publish_index=False,
    )
    return {
        "status": "preview_only",
        "project_path": str(root),
        "source_checkpoint_hash": source_hash,
        "review_state": "preview_only",
        "stage_summary_zh_html": {
            "project_relative_path": preview["stage_summary_zh_html"],
            "absolute_path": preview["absolute_stage_summary_zh_html"],
        },
        "stage_summary_json": preview["absolute_stage_summary_json"],
        "artifact_manifest": preview["absolute_artifact_manifest"],
        "confirmation_request": preview["absolute_confirmation_request"],
        "unresolved_issues": preview["unresolved_issues"],
    }


def agent_artifact_paths(project: str | Path, targets: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return an ASCII-safe path-only projection for CLI/Agent transport."""

    root = project_root(project)
    return [
        {
            "project_relative_path": str(item.get("project_relative_path") or ""),
            "absolute_path": str((root / str(item.get("project_relative_path"))).resolve()),
        }
        for item in targets
        if item.get("project_relative_path")
    ]


def checkpoint_path_payload(project: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    """Build an ASCII-safe path projection for status/next-action responses."""

    root = project_root(project)
    relative_html = str(event.get("stage_summary_zh_html") or "")
    relative_json = str(event.get("stage_summary_json") or "")
    if not relative_html and relative_json:
        relative_html = str(Path(relative_json).parent / "stage_summary.zh-CN.html").replace("\\", "/")
    result: dict[str, Any] = {}
    if relative_html:
        result["stage_summary_zh_html"] = {
            "project_relative_path": relative_html.replace("\\", "/"),
            "absolute_path": str((root / relative_html).resolve()),
            "source_semantic_sha256": event.get("stage_summary_sha256"),
        }
    if relative_json:
        result["stage_summary_json"] = str((root / relative_json).resolve())
    if event.get("checkpoint_id"):
        result["checkpoint_id"] = event["checkpoint_id"]
    return result


def validate_checkpoint_summary(project: str | Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Verify that the scientific artifacts bound by a checkpoint are unchanged."""

    root = project_root(project)
    relative = str(checkpoint.get("stage_summary_json") or "")
    if not relative:
        return {"status": "legacy_unbound", "valid": True, "reasons": []}
    path = root / relative
    if not path.is_file():
        return {"status": "invalid", "valid": False, "reasons": [f"Missing checkpoint summary: {relative}"]}
    companion_files = {
        "stage_summary.zh-CN.html": path.parent / "stage_summary.zh-CN.html",
        "artifact_manifest.json": path.parent / "artifact_manifest.json",
        "confirmation_request.json": path.parent / "confirmation_request.json",
        "change_report.json": path.parent / "change_report.json",
        "unresolved_issues.json": path.parent / "unresolved_issues.json",
        "agent_payload.json": path.parent / "agent_payload.json",
    }
    missing_companions = [name for name, companion in companion_files.items() if not companion.is_file()]
    if missing_companions:
        return {"status": "invalid", "valid": False, "reasons": ["Missing checkpoint companion files: " + ", ".join(missing_companions)]}
    try:
        summary = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {"status": "invalid", "valid": False, "reasons": [f"Invalid checkpoint summary: {exc}"]}
    reasons: list[str] = []
    schema = str(summary.get("schema_version") or "")
    if schema in LEGACY_CHECKPOINT_SUMMARY_SCHEMAS:
        return {
            "status": "legacy_unqualified",
            "valid": False,
            "reasons": [f"Legacy checkpoint summary {schema} is read-only; create a v3 summary before confirmation."],
        }
    reasons.extend(_checkpoint_summary_contract_issues(summary))
    if reasons:
        return {"status": "invalid", "valid": False, "reasons": reasons}
    expected_summary_hash = str(checkpoint.get("stage_summary_sha256") or summary.get("stage_summary_sha256") or "")
    if expected_summary_hash and expected_summary_hash != str(summary.get("stage_summary_sha256") or ""):
        reasons.append("Checkpoint summary hash changed.")
    recompute_payload = dict(summary)
    recompute_payload.pop("stage_summary_sha256", None)
    if str(summary.get("stage_summary_sha256") or "") != _hash_payload(recompute_payload):
        reasons.append("Checkpoint summary content does not match its semantic hash.")
    manifest = summary.get("artifact_manifest") if isinstance(summary.get("artifact_manifest"), dict) else {}
    if str(summary.get("artifact_manifest_sha256") or "") != _hash_payload(manifest):
        reasons.append("Checkpoint artifact manifest does not match its semantic hash.")
    try:
        stored_manifest = json.loads(companion_files["artifact_manifest.json"].read_text(encoding="utf-8-sig"))
        request = json.loads(companion_files["confirmation_request.json"].read_text(encoding="utf-8-sig"))
        agent = json.loads(companion_files["agent_payload.json"].read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        reasons.append(f"Checkpoint companion JSON is invalid: {exc}")
    else:
        if stored_manifest != manifest:
            reasons.append("Checkpoint artifact manifest file differs from stage summary.")
        if request.get("stage_summary_sha256") != summary.get("stage_summary_sha256"):
            reasons.append("Confirmation request is not bound to the stage summary hash.")
        if request.get("summary_schema") != summary.get("schema_version"):
            reasons.append("Confirmation request is not bound to the current summary schema.")
        expected_request_command = summary.get("review_state") == "confirmable" and (
            schema == CHECKPOINT_SUMMARY_SCHEMA or summary.get("review_requirement") != "notify_only"
        ) and summary.get("decision_status") not in {"agent_approved", "user_confirmed"}
        if (request.get("confirmation_command") is not None) != expected_request_command:
            reasons.append("Confirmation request command permission does not match review_state.")
        if agent.get("stage_summary_sha256") != summary.get("stage_summary_sha256"):
            reasons.append("Agent payload is not bound to the stage summary hash.")
        if agent.get("summary_schema") != summary.get("schema_version"):
            reasons.append("Agent payload is not bound to the current summary schema.")
        if agent.get("review_state") != summary.get("review_state"):
            reasons.append("Agent payload review_state differs from stage summary.")
        if agent.get("stage_narrative_zh") != summary.get("stage_narrative_zh"):
            reasons.append("Agent payload narrative differs from stage summary.")
        if schema == CHECKPOINT_SUMMARY_V4_SCHEMA:
            activity_path = path.parent / "stage_activity_bundle.json"
            if not activity_path.is_file():
                reasons.append("Missing v4 stage activity bundle companion.")
            else:
                try:
                    stored_activity = json.loads(activity_path.read_text(encoding="utf-8-sig"))
                except (OSError, ValueError) as exc:
                    reasons.append(f"Invalid v4 stage activity bundle: {exc}")
                else:
                    if stored_activity != summary.get("stage_activity_bundle"):
                        reasons.append("Stage activity bundle file differs from stage summary.")
                    if stored_activity.get("bundle_sha256") != summary.get("activity_bundle_sha256"):
                        reasons.append("Stage activity bundle hash differs from stage summary.")
                    if agent.get("activity_bundle_sha256") != summary.get("activity_bundle_sha256"):
                        reasons.append("Agent payload activity bundle hash differs from stage summary.")
    current = {str(item.get("path")): item for item in collect_artifacts(root) if isinstance(item, dict)}
    for item in (summary.get("artifact_manifest") or {}).get("artifacts") or []:
        relative_artifact = str(item.get("project_relative_path") or "")
        if not relative_artifact or item.get("operation") == "failed":
            continue
        current_item = current.get(relative_artifact)
        if current_item is None:
            candidate = root / relative_artifact
            if candidate.is_file():
                current_item = compute_artifact_identity(candidate, relative_artifact)
        if current_item is None:
            reasons.append(f"Bound artifact is missing: {relative_artifact}")
            continue
        expected_semantic = item.get("after_semantic_sha256")
        if expected_semantic and current_item.get("semantic_sha256") != expected_semantic:
            reasons.append(f"Bound artifact changed after assessment (semantic identity): {relative_artifact}")
        expected_evidence = item.get("evidence_sha256")
        if expected_evidence and current_item.get("evidence_sha256") != expected_evidence:
            reasons.append(f"Bound artifact changed after assessment (evidence identity): {relative_artifact}")
    return {"status": "valid" if not reasons else "invalid", "valid": not reasons, "reasons": reasons}


def attach_checkpoint_summary(
    payload: dict[str, Any],
    *,
    project: str | Path,
    stage: str,
    command: str,
    before_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach exact relative and absolute summary paths to an Agent payload."""

    if payload.get("stage_summary_zh_html"):
        return payload
    report = write_stage_summary_v4(
        project,
        stage=stage,
        command=command,
        payload=payload,
        before_artifacts=before_artifacts,
        checkpoint_id=str(payload.get("checkpoint_id") or "") or None,
        checkpoint_hash=str(payload.get("checkpoint_hash") or "") or None,
    )
    result = dict(payload)
    result["stage_summary_zh_html"] = {
        "project_relative_path": report["stage_summary_zh_html"],
        "absolute_path": report["absolute_stage_summary_zh_html"],
        "source_semantic_sha256": report["stage_summary_sha256"],
    }
    result["checkpoint_summary"] = {
        "checkpoint_id": report["checkpoint_id"],
        "project_relative_dir": report["project_relative_dir"],
        "absolute_path": report["absolute_stage_summary_zh_html"],
        "stage_summary_json": report["absolute_stage_summary_json"],
        "artifact_manifest": report["absolute_artifact_manifest"],
        "confirmation_request": report["confirmation_request"],
    }
    root = project_root(project)
    result["primary_artifacts"] = [
        {
            "project_relative_path": str(item.get("project_relative_path") or ""),
            "absolute_path": str((root / str(item.get("project_relative_path"))).resolve()),
        }
        for item in report["inspection_targets"]
        if item.get("project_relative_path")
    ]
    result["unresolved_issues"] = report["unresolved_issues"]
    result["stage_summary_sha256"] = report["stage_summary_sha256"]
    return result
