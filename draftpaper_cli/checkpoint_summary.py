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
CHECKPOINT_SUMMARY_V5_SCHEMA = "dpl.checkpoint_summary.v5"
CHECKPOINT_SUMMARY_V6_SCHEMA = "dpl.checkpoint_summary.v6"
LEGACY_CHECKPOINT_SUMMARY_SCHEMAS = frozenset({"dpl.checkpoint_summary.v1", "dpl.checkpoint_summary.v2"})
CURRENT_DECISION_CHECKPOINT_SCHEMAS = frozenset({CHECKPOINT_SUMMARY_V5_SCHEMA, CHECKPOINT_SUMMARY_V6_SCHEMA})
CHECKPOINT_REVIEW_STATES = frozenset({"confirmable", "stale", "blocked", "preview_only", "legacy_unqualified"})
ARTIFACT_MANIFEST_SCHEMA = "dpl.checkpoint_artifact_manifest.v2"
CONFIRMATION_REQUEST_SCHEMA = "dpl.confirmation_request.v1"
CONFIRMATION_REQUEST_V2_SCHEMA = "dpl.confirmation_request.v2"
CHANGE_REPORT_SCHEMA = "dpl.checkpoint_change_report.v1"
UNRESOLVED_ISSUES_SCHEMA = "dpl.checkpoint_unresolved_issues.v1"
AGENT_PAYLOAD_SCHEMA = "dpl.checkpoint_agent_payload.v1"
AGENT_PAYLOAD_V2_SCHEMA = "dpl.checkpoint_agent_payload.v2"
AGENT_PAYLOAD_V3_SCHEMA = "dpl.checkpoint_agent_payload.v3"
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


def _confirmation_meaning_en(summary: dict[str, Any], *, continuity_eligible: bool) -> str:
    explicit = str(summary.get("confirmation_meaning_en") or "").strip()
    if explicit:
        return explicit
    if continuity_eligible:
        return (
            "The current scientific decision is identical to the prior author-approved decision. "
            "The workflow may continue while preserving that approval; only the technical audit was refreshed."
        )
    if str(summary.get("review_state") or "") != "confirmable":
        return (
            "This checkpoint is readable but cannot be confirmed until its blocking or stale evidence is repaired "
            "and a new checkpoint package is created."
        )
    return (
        "After confirmation, the workflow may continue only through this checkpoint's allowed downstream route. "
        "Confirmation does not replace the author's scientific judgment."
    )


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
    if schema not in {CHECKPOINT_SUMMARY_SCHEMA, CHECKPOINT_SUMMARY_V4_SCHEMA, *CURRENT_DECISION_CHECKPOINT_SCHEMAS}:
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
    if schema in {CHECKPOINT_SUMMARY_V4_SCHEMA, *CURRENT_DECISION_CHECKPOINT_SCHEMAS}:
        required = (*required, "review_requirement", "decision_status", "decision_actor_type", "authority_source", "risk_class", "stage_activity_bundle", "activity_bundle_sha256", "baseline_refs", "revision_cycle_id")
    if schema in CURRENT_DECISION_CHECKPOINT_SCHEMAS:
        required = (
            *required,
            "decision_brief",
            "scientific_decision_fingerprint",
            "human_brief_semantic_sha256",
            "confirmation_meaning_en",
            "audit_bundle_ref",
            "audit_bundle_sha256",
            "presentation_sha256",
            "activity_window",
            "semantic_delta_from_last_confirmed",
            "confirmation_basis",
            "readability_report_ref",
            "reviewer_visibility_scope",
            "confirmation_continuity",
            "figure_claim_map_sha256",
            "scientific_figure_claim_sha256",
        )
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
        if schema in {CHECKPOINT_SUMMARY_V4_SCHEMA, *CURRENT_DECISION_CHECKPOINT_SCHEMAS} and not isinstance(confirmation_contract.get("requires_user_decision"), bool):
            issues.append("v4/v5/v6 confirmation requires requires_user_decision to be boolean.")
        if confirmation_contract.get("source_of_truth") != "canonical_evidence":
            issues.append("Checkpoint confirmation source_of_truth must be canonical_evidence.")
        expected_command_allowed = summary.get("review_state") == "confirmable" and (
            schema == CHECKPOINT_SUMMARY_SCHEMA or summary.get("review_requirement") != "notify_only"
        ) and (
            schema not in CURRENT_DECISION_CHECKPOINT_SCHEMAS or bool(confirmation_contract.get("requires_user_decision"))
        )
        if confirmation_contract.get("confirmation_command_allowed") is not expected_command_allowed:
            issues.append("Confirmation command permission does not match review_state.")
        if confirmation_contract.get("test_auto_confirmation") is not summary.get("test_auto_confirmation"):
            issues.append("Confirmation contract test marker does not match summary.")
    if summary.get("test_auto_confirmation") and not summary.get("test_mode"):
        issues.append("test_auto_confirmation requires test_mode=true.")
    if (
        summary.get("review_state") == "confirmable"
        and summary.get("stage_status") != "ready_for_human_review"
        and schema == CHECKPOINT_SUMMARY_SCHEMA
    ):
        issues.append("A confirmable summary must have stage_status=ready_for_human_review.")
    if schema in {CHECKPOINT_SUMMARY_V4_SCHEMA, *CURRENT_DECISION_CHECKPOINT_SCHEMAS}:
        if summary.get("review_requirement") not in {"notify_only", "agent_delegable", "human_required"}:
            issues.append("v4 review_requirement is not recognized.")
        if summary.get("decision_status") not in {"not_required", "pending", "system_acknowledged", "continuity_preserved", "agent_approved", "user_confirmed", "rejected", "refinement_required"}:
            issues.append("v4 decision_status is not recognized.")
        if summary.get("decision_actor_type") not in {"none", "system", "agent", "user"}:
            issues.append("v4 decision_actor_type is not recognized.")
        if not isinstance(summary.get("stage_activity_bundle"), dict):
            issues.append("v4 stage_activity_bundle must be an object.")
        if not isinstance(summary.get("baseline_refs"), dict):
            issues.append("v4 baseline_refs must be an object.")
    if schema in CURRENT_DECISION_CHECKPOINT_SCHEMAS:
        if not isinstance(summary.get("decision_brief"), dict):
            issues.append("v5/v6 decision_brief must be an object.")
        if not isinstance(summary.get("scientific_decision_fingerprint"), dict):
            issues.append("v5/v6 scientific_decision_fingerprint must be an object.")
        if not isinstance(summary.get("activity_window"), dict):
            issues.append("v5/v6 activity_window must be an object.")
        if not isinstance(summary.get("semantic_delta_from_last_confirmed"), dict):
            issues.append("v5/v6 semantic_delta_from_last_confirmed must be an object.")
        if not isinstance(summary.get("confirmation_basis"), dict):
            issues.append("v5/v6 confirmation_basis must be an object.")
        if not isinstance(summary.get("confirmation_continuity"), dict):
            issues.append("v5/v6 confirmation_continuity must be an object.")
        if not isinstance(summary.get("confirmation_meaning_en"), str) or not summary.get("confirmation_meaning_en").strip():
            issues.append("v5/v6 confirmation_meaning_en must be a non-empty string.")
        if summary.get("reviewer_visibility_scope") not in {"author_decision", "internal_audit", "reviewer_visible", "release_public"}:
            issues.append("v5/v6 reviewer_visibility_scope is not recognized.")
        if not isinstance(summary.get("figure_claim_map_sha256"), str) or not summary.get("figure_claim_map_sha256").strip():
            issues.append("v5/v6 figure_claim_map_sha256 must be a non-empty string.")
        if not isinstance(summary.get("scientific_figure_claim_sha256"), str) or not summary.get("scientific_figure_claim_sha256").strip():
            issues.append("v5/v6 scientific_figure_claim_sha256 must be a non-empty string.")
        if schema == CHECKPOINT_SUMMARY_V6_SCHEMA and not str(summary.get("audit_bundle_ref") or "").endswith(".json"):
            issues.append("v6 audit_bundle_ref must point to JSON.")
        if schema == CHECKPOINT_SUMMARY_V6_SCHEMA and summary.get("audit_render_policy") != "on_demand_cache_only":
            issues.append("v6 audit_render_policy must be on_demand_cache_only.")
    if summary.get("review_state") != "confirmable" and summary.get("confirmation_contract", {}).get("confirmation_command_allowed"):
        issues.append("Non-confirmable summary cannot allow a confirmation command.")
    return issues


def _pre_figure_claim_v5_contract(summary: dict[str, Any]) -> bool:
    """Identify a historical v5 package before FigureClaimMap bound C3 semantics.

    It remains readable evidence but cannot be resumed or silently upgraded
    under the current scientific-decision contract.
    """

    fingerprint = summary.get("scientific_decision_fingerprint")
    payload = fingerprint.get("canonical_payload") if isinstance(fingerprint, dict) else None
    return not (
        isinstance(payload, dict)
        and isinstance(payload.get("figure_claim_map"), list)
        and isinstance(summary.get("scientific_figure_claim_sha256"), str)
        and bool(str(summary.get("scientific_figure_claim_sha256") or "").strip())
    )


def _pre_method_analysis_v5_contract(summary: dict[str, Any]) -> bool:
    """Keep old core-evidence v5 packages read-only under the complete contract."""

    if str(summary.get("checkpoint_type") or summary.get("completed_stage") or "") != "core_evidence":
        return False
    from .checkpoint_fingerprint import fingerprint_has_method_analysis_identity

    fingerprint = summary.get("scientific_decision_fingerprint")
    return not fingerprint_has_method_analysis_identity(fingerprint if isinstance(fingerprint, dict) else {})


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
        # The explicit list is prepared by the bounded, manifest-first scope
        # builder.  Do not re-expand it using historical stage prefixes here.
        if relative in explicit_paths:
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


def _render_html(
    root: Path,
    output_dir: Path,
    summary: dict[str, Any],
    request: dict[str, Any],
    *,
    locale: str = "zh-CN",
) -> str:
    from .checkpoint_html import render_checkpoint_html

    return render_checkpoint_html(root, output_dir, summary, request, locale=locale)


def _previous_repair_layers(root: Path, stage: str) -> list[str]:
    """Read prior repair classes without treating old audit files as evidence."""

    layers: list[str] = []
    for record in reversed(_checkpoint_index_records(root)):
        if str(record.get("checkpoint_type") or record.get("stage") or "") != stage:
            continue
        relative = _relative_project_path(root, str(record.get("stage_summary_json") or ""))
        if not relative:
            continue
        receipt_path = root / Path(relative).parent / "evidence_binding_failure_receipt.json"
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        for item in receipt.get("failures") or []:
            if isinstance(item, dict) and item.get("repair_layer"):
                layers.append(str(item["repair_layer"]))
        if layers:
            break
    # A single producer defect can surface on several paired artifacts (for
    # example, PDF and PNG renderings of one figure).  The loop guard tracks
    # repair *classes* across attempts, not the number of artifacts emitted by
    # one attempt, so collapse duplicate layers before handing them to it.
    return sorted(set(layers))


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
            "scientific_decision_sha256": report.get("scientific_decision_sha256"),
            "stage_summary_json": f"{relative_dir}/stage_summary.json",
            "stage_summary_zh_html": f"{relative_dir}/stage_summary.zh-CN.html",
            "stage_summary_en_html": f"{relative_dir}/stage_summary.en.html" if report.get("schema_version") in CURRENT_DECISION_CHECKPOINT_SCHEMAS else None,
            "stage_audit_zh_html": f"{relative_dir}/stage_audit.zh-CN.html" if report.get("schema_version") == CHECKPOINT_SUMMARY_V5_SCHEMA else None,
            "stage_audit_json": f"{relative_dir}/stage_audit.json" if report.get("schema_version") == CHECKPOINT_SUMMARY_V6_SCHEMA else None,
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
    from .review_policy import classify_checkpoint_risk, classify_review_requirement
    from .revision_cycle import load_active_revision_cycle
    from .scientific_baseline import load_active_baseline
    from .stage_activity import build_stage_activity_bundle

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


def write_stage_summary_v5(
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
    """Write the v5 decision/audit package without mutating older packages.

    v5 deliberately builds on the mature v4 evidence adapters, then changes
    only the package contract consumed by new checkpoints.  The main HTML is a
    short decision page; the former all-details page is retained as a sibling
    audit view so no evidence is discarded.
    """

    from .checkpoint_brief import build_human_decision_brief, validate_human_decision_brief
    from .checkpoint_fingerprint import (
        build_audit_fingerprint,
        build_presentation_fingerprint,
        build_scientific_decision_fingerprint,
        compare_scientific_decisions,
    )
    from .checkpoint_html import render_checkpoint_audit_html
    from .checkpoint_readability import build_checkpoint_readability_report
    from .confirmation_continuity import (
        evaluate_confirmation_continuity,
        latest_valid_user_receipt,
        write_confirmation_continuity_receipt,
    )
    from .evidence_repair_router import route_evidence_failures
    from .figure_claim_map import build_figure_claim_map, validate_figure_claim_map
    from .review_policy import classify_checkpoint_risk, classify_review_requirement

    root = project_root(project)
    data = dict(payload or {})
    base = write_stage_summary_v4(
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
    activity_path = output_dir / "stage_activity_bundle.json"
    manifest_path = output_dir / "artifact_manifest.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    request = json.loads(request_path.read_text(encoding="utf-8-sig"))
    agent = json.loads(agent_path.read_text(encoding="utf-8-sig"))
    activity = json.loads(activity_path.read_text(encoding="utf-8-sig"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))

    brief = build_human_decision_brief(summary)
    brief_issues = validate_human_decision_brief(brief)
    figure_map = build_figure_claim_map(summary, brief)
    fingerprint = build_scientific_decision_fingerprint(summary, brief, figure_claim_map=figure_map)
    previous_receipt = latest_valid_user_receipt(root, checkpoint_type=stage)
    previous_fingerprint = (previous_receipt or {}).get("scientific_decision_fingerprint") if isinstance((previous_receipt or {}).get("scientific_decision_fingerprint"), dict) else None
    delta = compare_scientific_decisions(previous_fingerprint, fingerprint)
    brief["semantic_delta"] = delta
    figure_issues = validate_figure_claim_map(figure_map)
    repair_failures = [*figure_issues]
    repair_failures.extend({"code": "decision_brief_contract", "detail_zh": issue} for issue in brief_issues)
    repair = route_evidence_failures(repair_failures, failure_history=_previous_repair_layers(root, stage))
    blocking_codes = [str(item.get("code") or "") for item in figure_issues] + (["decision_brief_contract"] if brief_issues else [])
    if (repair.get("loop_guard") or {}).get("stop_and_report"):
        blocking_codes.append("repeated_failure_class_requires_root_cause")
    if blocking_codes:
        summary["review_state"] = "blocked"
        summary["stage_status"] = "blocked"
        unresolved = list(summary.get("unresolved") or [])
        unresolved.extend(
            {
                "summary_zh": str(item.get("detail_zh") or item.get("code") or "确认合同存在问题。"),
                "blocking": True,
                "source": "figure_claim_map_v1.json" if item in figure_issues else "human_decision_brief_v1.json",
            }
            for item in figure_issues
        )
        unresolved.extend({"summary_zh": issue, "blocking": True, "source": "human_decision_brief_v1.json"} for issue in brief_issues)
        if (repair.get("loop_guard") or {}).get("stop_and_report"):
            unresolved.append(
                {
                    "summary_zh": "同一证据失败类型重复出现；必须先完成根因报告，不能继续进行局部循环修复。",
                    "blocking": True,
                    "source": "evidence_binding_failure_receipt.json",
                }
            )
        summary["unresolved"] = unresolved

    audit_fingerprint = build_audit_fingerprint(summary, activity, manifest)
    presentation_fingerprint = build_presentation_fingerprint(brief)
    continuity = evaluate_confirmation_continuity(
        root,
        checkpoint_type=stage,
        scientific_fingerprint=fingerprint,
        brief_semantic_sha256=str(brief.get("brief_semantic_sha256") or ""),
        review_state=str(summary.get("review_state") or "blocked"),
        blocked_reason_codes=blocking_codes,
        semantic_delta_class=str(delta.get("classification") or ""),
        unresolved_issues=list(summary.get("unresolved") or []),
    )
    risk_class = classify_checkpoint_risk(summary)
    normal_requirement = classify_review_requirement(summary)
    continuity_path: str | None = None
    if continuity.get("eligible"):
        continuity_result = write_confirmation_continuity_receipt(
            output_dir,
            checkpoint_type=stage,
            checkpoint_package_id=str(summary.get("checkpoint_id") or base["checkpoint_id"]),
            scientific_decision_sha256=str(fingerprint["scientific_decision_sha256"]),
            human_brief_semantic_sha256=str(brief["brief_semantic_sha256"]),
            audit_bundle_sha256=str(audit_fingerprint["audit_bundle_sha256"]),
            previous_receipt=dict(continuity["previous_receipt"]),
            classified_changes=list(delta.get("changes") or []),
        )
        continuity_path = Path(continuity_result["path"]).relative_to(root).as_posix()
        requirement = "notify_only"
        decision_status = "continuity_preserved"
        decision_actor_type = "system"
        authority_source = {"policy": "semantic_confirmation_continuity", "previous_receipt_id": continuity["previous_receipt"].get("receipt_id")}
        summary["stage_status"] = "auto_continued"
    else:
        requirement = normal_requirement
        decision_status = str(summary.get("decision_status") or "pending")
        decision_actor_type = str(summary.get("decision_actor_type") or "none")
        authority_source = summary.get("authority_source") or {"policy": "review_policy"}

    relative_dir = str(base["project_relative_dir"])
    summary["schema_version"] = CHECKPOINT_SUMMARY_V5_SCHEMA
    summary["review_requirement"] = requirement
    summary["decision_status"] = decision_status
    summary["decision_actor_type"] = decision_actor_type
    summary["authority_source"] = authority_source
    summary["risk_class"] = risk_class
    summary["decision_brief"] = brief
    summary["scientific_decision_fingerprint"] = fingerprint
    summary["human_brief_semantic_sha256"] = brief["brief_semantic_sha256"]
    summary["confirmation_meaning_en"] = _confirmation_meaning_en(summary, continuity_eligible=bool(continuity.get("eligible")))
    summary["audit_bundle_ref"] = f"{relative_dir}/stage_audit.zh-CN.html"
    summary["audit_bundle_sha256"] = audit_fingerprint["audit_bundle_sha256"]
    summary["presentation_sha256"] = presentation_fingerprint["presentation_sha256"]
    summary["activity_window"] = activity.get("activity_window") or {}
    summary["semantic_delta_from_last_confirmed"] = delta
    summary["confirmation_basis"] = {
        "source_of_truth": "scientific_decision_fingerprint",
        "scientific_decision_sha256": fingerprint["scientific_decision_sha256"],
        "human_brief_semantic_sha256": brief["brief_semantic_sha256"],
        "package_summary_sha256": None,
    }
    summary["readability_report_ref"] = f"{relative_dir}/checkpoint_readability_report.json"
    summary["readability_reports"] = {
        "zh-CN": f"{relative_dir}/checkpoint_readability_report.json",
        "en": f"{relative_dir}/checkpoint_readability_report.en.json",
    }
    summary["reviewer_visibility_scope"] = str(data.get("reviewer_visibility_scope") or "author_decision")
    summary["confirmation_continuity"] = {
        "eligible": bool(continuity.get("eligible")),
        "classification": continuity.get("classification"),
        "previous_receipt_id": (continuity.get("previous_receipt") or {}).get("receipt_id"),
        "receipt_path": continuity_path,
        "reason_codes": continuity.get("reason_codes") or [],
    }
    summary["figure_claim_map_ref"] = f"{relative_dir}/figure_claim_map_v1.json"
    summary["figure_claim_map_sha256"] = figure_map["figure_claim_map_sha256"]
    summary["scientific_figure_claim_sha256"] = figure_map["scientific_figure_claim_sha256"]
    summary["evidence_repair_route_ref"] = f"{relative_dir}/evidence_binding_failure_receipt.json"
    summary["confirmation_contract"] = {
        "requires_user_decision": requirement != "notify_only" and decision_status not in {"agent_approved", "user_confirmed", "system_acknowledged", "continuity_preserved"},
        "confirmation_command_allowed": str(summary.get("review_state")) == "confirmable" and requirement != "notify_only",
        "source_of_truth": "canonical_evidence",
        "test_auto_confirmation": bool(summary.get("test_auto_confirmation")),
    }
    if summary["review_state"] != "confirmable":
        summary["confirmation_contract"]["confirmation_command_allowed"] = False
        summary["confirmation_contract"]["requires_user_decision"] = False
    summary.pop("stage_summary_sha256", None)
    summary_hash = _hash_payload(summary)
    summary["stage_summary_sha256"] = summary_hash
    # The package hash is diagnostic only.  It stays in the request rather
    # than in the summary's semantic payload, avoiding a self-referential hash.

    request = {
        "schema_version": CONFIRMATION_REQUEST_V2_SCHEMA,
        "checkpoint_id": summary["checkpoint_id"],
        "checkpoint_type": stage,
        "checkpoint_hash": checkpoint_hash,
        "checkpoint_package_id": summary["checkpoint_id"],
        "checkpoint_package_summary_sha256": summary_hash,
        "scientific_decision_sha256": fingerprint["scientific_decision_sha256"],
        "human_brief_semantic_sha256": brief["brief_semantic_sha256"],
        "semantic_delta_class": delta.get("classification"),
        "continuity_eligible": bool(continuity.get("eligible")),
        "previous_decision_receipt_id": (continuity.get("previous_receipt") or {}).get("receipt_id"),
        "summary_schema": CHECKPOINT_SUMMARY_V5_SCHEMA,
        "review_state": summary.get("review_state"),
        "review_requirement": requirement,
        "decision_status": decision_status,
        "requires_user_decision": summary["confirmation_contract"]["requires_user_decision"],
        "allowed_decisions": ["confirm", "refine", "reject"] if summary["confirmation_contract"]["requires_user_decision"] else [],
        "confirmation_command": request.get("confirmation_command") if summary["confirmation_contract"]["confirmation_command_allowed"] else None,
        "refinement_command": request.get("refinement_command"),
        "recovery_command": request.get("recovery_command"),
        "created_at": utc_now(),
    }
    decision_path = {
        "project_relative_path": f"{relative_dir}/stage_summary.zh-CN.html",
        "absolute_path": str((output_dir / "stage_summary.zh-CN.html").resolve()),
    }
    decision_path_en = {
        "project_relative_path": f"{relative_dir}/stage_summary.en.html",
        "absolute_path": str((output_dir / "stage_summary.en.html").resolve()),
    }
    audit_path = {
        "project_relative_path": f"{relative_dir}/stage_audit.zh-CN.html",
        "absolute_path": str((output_dir / "stage_audit.zh-CN.html").resolve()),
    }
    review_points: list[str] = []
    for group in ("confirming", "claim_boundaries", "not_confirming", "reopen_conditions"):
        for item in brief.get(group) or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text_zh") or "").strip()
            if text and text not in review_points:
                review_points.append(text)
            if len(review_points) >= 5:
                break
        if len(review_points) >= 5:
            break
    decision_question = brief.get("decision_question") if isinstance(brief.get("decision_question"), dict) else {}
    decision_summary = next(
        (
            str(item.get("text_zh") or "").strip()
            for item in brief.get("confirming") or []
            if isinstance(item, dict) and str(item.get("text_zh") or "").strip()
        ),
        str(summary.get("stage_purpose_zh") or ""),
    )
    authority_reason = (
        "本次科学决定与最近一次有效作者确认相同，系统只沿用原确认。"
        if continuity.get("eligible")
        else f"当前审查主体由 {(authority_source or {}).get('policy') or 'review_policy'!s} 决定。"
    )
    ordered_agent_keys = {
        "primary_human_review_html",
        "human_decision_html",
        "human_decision_html_en",
        "stage_summary_zh_html",
        "stage_completion_summary_zh",
        "decision_question_zh",
        "decision_summary_zh",
        "semantic_delta_summary_zh",
        "semantic_delta_summary_en",
        "review_points_zh",
        "decision_actor_type",
        "decision_authority_reason_zh",
        "confirmation_meaning_zh",
        "confirmation_meaning_en",
        "scientific_decision_sha256",
        "human_brief_semantic_sha256",
        "continuity_status",
        "reconfirmation_reason_codes",
        "latest_user_visible_deliverables",
        "confirmation_command",
        "confirmation_contract",
        "decision_brief",
        "stage_summary_sha256",
        "schema_version",
        "summary_schema",
        "technical_audit_html",
    }
    agent_remainder = {key: value for key, value in agent.items() if key not in ordered_agent_keys}
    # Preserve insertion order so the first fields are the text and paths an
    # Agent must present to an author, while the technical audit remains last.
    agent = {
        "primary_human_review_html": decision_path,
        "human_decision_html": decision_path,
        "human_decision_html_en": decision_path_en,
        "stage_summary_zh_html": decision_path,
        "stage_completion_summary_zh": summary["stage_narrative_zh"],
        "decision_question_zh": str(decision_question.get("text_zh") or summary["stage_purpose_zh"]),
        "decision_summary_zh": decision_summary,
        "semantic_delta_summary_zh": str(delta.get("summary_zh") or ""),
        "semantic_delta_summary_en": str(delta.get("summary_en") or ""),
        "review_points_zh": review_points,
        "decision_actor_type": decision_actor_type,
        "decision_authority_reason_zh": authority_reason,
        "confirmation_meaning_zh": summary["confirmation_meaning_zh"],
        "confirmation_meaning_en": summary["confirmation_meaning_en"],
        "scientific_decision_sha256": fingerprint["scientific_decision_sha256"],
        "human_brief_semantic_sha256": brief["brief_semantic_sha256"],
        "continuity_status": continuity.get("classification"),
        "reconfirmation_reason_codes": continuity.get("reason_codes") or [],
        "latest_user_visible_deliverables": brief.get("latest_user_visible_deliverables") or [],
        "confirmation_command": request["confirmation_command"],
        "confirmation_contract": summary["confirmation_contract"],
        "decision_brief": str((output_dir / "human_decision_brief_v1.json").resolve()),
        "stage_summary_sha256": summary_hash,
        "schema_version": AGENT_PAYLOAD_V2_SCHEMA,
        "summary_schema": CHECKPOINT_SUMMARY_V5_SCHEMA,
        **agent_remainder,
        "technical_audit_html": audit_path,
    }
    contract_issues = _checkpoint_summary_contract_issues(summary)
    if contract_issues:
        raise CheckpointSummaryError("Checkpoint v5 summary contract failed: " + "; ".join(contract_issues))

    atomic_write_json(summary_path, summary)
    atomic_write_json(request_path, request)
    atomic_write_json(agent_path, agent)
    atomic_write_json(output_dir / "human_decision_brief_v1.json", brief)
    atomic_write_json(output_dir / "scientific_decision_fingerprint_v1.json", fingerprint)
    atomic_write_json(output_dir / "checkpoint_audit_fingerprint_v1.json", audit_fingerprint)
    atomic_write_json(output_dir / "checkpoint_presentation_fingerprint_v1.json", presentation_fingerprint)
    atomic_write_json(output_dir / "figure_claim_map_v1.json", figure_map)
    atomic_write_json(output_dir / "evidence_binding_failure_receipt.json", repair)
    atomic_write_text(output_dir / "stage_audit.zh-CN.html", render_checkpoint_audit_html(root, output_dir, summary, request))
    decision_html = _render_html(root, output_dir, summary, request)
    decision_html_en = _render_html(root, output_dir, summary, request, locale="en")
    atomic_write_text(output_dir / "stage_summary.zh-CN.html", decision_html)
    atomic_write_text(output_dir / "stage_summary.en.html", decision_html_en)
    readability = build_checkpoint_readability_report(html=decision_html, brief=brief)
    readability_en = build_checkpoint_readability_report(html=decision_html_en, brief=brief, locale="en")
    atomic_write_json(output_dir / "checkpoint_readability_report.json", readability)
    atomic_write_json(output_dir / "checkpoint_readability_report.en.json", readability_en)
    if readability.get("status") != "passed" or readability_en.get("status") != "passed":
        failures = [*list(readability.get("failure_codes") or []), *[f"en:{code}" for code in readability_en.get("failure_codes") or []]]
        raise CheckpointSummaryError("Checkpoint decision page failed readability gate: " + ", ".join(failures))
    required_files = (
        output_dir / "stage_summary.json",
        output_dir / "stage_summary.zh-CN.html",
        output_dir / "stage_summary.en.html",
        output_dir / "stage_audit.zh-CN.html",
        output_dir / "confirmation_request.json",
        output_dir / "agent_payload.json",
        output_dir / "human_decision_brief_v1.json",
        output_dir / "scientific_decision_fingerprint_v1.json",
        output_dir / "checkpoint_readability_report.json",
        output_dir / "checkpoint_readability_report.en.json",
        output_dir / "figure_claim_map_v1.json",
    )
    if not all(path.is_file() for path in required_files):
        missing = ", ".join(path.name for path in required_files if not path.is_file())
        raise CheckpointSummaryError("Checkpoint v5 package is incomplete; missing: " + missing)
    if publish_index:
        _publish_checkpoint_index(root, {**summary, "checkpoint_type": stage})
    return {
        **base,
        "summary_schema": CHECKPOINT_SUMMARY_V5_SCHEMA,
        "stage_summary_sha256": summary_hash,
        "stage_summary_zh_html": f"{relative_dir}/stage_summary.zh-CN.html",
        "absolute_stage_summary_zh_html": str((output_dir / "stage_summary.zh-CN.html").resolve()),
        "stage_audit_zh_html": f"{relative_dir}/stage_audit.zh-CN.html",
        "absolute_stage_audit_zh_html": str((output_dir / "stage_audit.zh-CN.html").resolve()),
        "stage_summary_en_html": f"{relative_dir}/stage_summary.en.html",
        "absolute_stage_summary_en_html": str((output_dir / "stage_summary.en.html").resolve()),
        "human_decision_brief": f"{relative_dir}/human_decision_brief_v1.json",
        "scientific_decision_fingerprint": f"{relative_dir}/scientific_decision_fingerprint_v1.json",
        "scientific_decision_sha256": fingerprint["scientific_decision_sha256"],
        "human_brief_semantic_sha256": brief["brief_semantic_sha256"],
        "audit_bundle_sha256": audit_fingerprint["audit_bundle_sha256"],
        "presentation_sha256": presentation_fingerprint["presentation_sha256"],
        "semantic_delta_summary_zh": str(delta.get("summary_zh") or ""),
        "semantic_delta_summary_en": str(delta.get("summary_en") or ""),
        "stage_completion_summary_zh": summary["stage_narrative_zh"],
        "decision_question_zh": str(decision_question.get("text_zh") or summary["stage_purpose_zh"]),
        "decision_summary_zh": decision_summary,
        "review_points_zh": review_points,
        "confirmation_meaning_zh": summary["confirmation_meaning_zh"],
        "confirmation_meaning_en": summary["confirmation_meaning_en"],
        "decision_actor_type": decision_actor_type,
        "decision_authority_reason_zh": authority_reason,
        "primary_human_review_html": decision_path,
        "technical_audit_html": audit_path,
        "confirmation_command": request["confirmation_command"],
        "latest_user_visible_deliverables": brief.get("latest_user_visible_deliverables") or [],
        "confirmation_continuity": summary["confirmation_continuity"],
        "readability_report": f"{relative_dir}/checkpoint_readability_report.json",
    }


def write_stage_summary_v6(
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
    """Write a v6 decision package with JSON-first technical audit.

    v6 deliberately reuses v5's evidence assembly and continuity gates.  It
    changes only the persistent presentation contract: `stage_audit.json` is
    the complete technical record and audit HTML is rendered only into the
    disposable `.draftpaper/render_cache/` on demand.  v5 packages remain
    untouched and readable.
    """

    from .checkpoint_fingerprint import build_presentation_fingerprint
    from .checkpoint_html import render_checkpoint_html
    from .checkpoint_readability import build_checkpoint_readability_report

    root = project_root(project)
    base = write_stage_summary_v5(
        root,
        stage=stage,
        command=command,
        payload=payload,
        before_artifacts=before_artifacts,
        checkpoint_id=checkpoint_id,
        checkpoint_hash=checkpoint_hash,
        publish_index=False,
    )
    output_dir = root / str(base["project_relative_dir"])
    summary_path = output_dir / "stage_summary.json"
    request_path = output_dir / "confirmation_request.json"
    agent_path = output_dir / "agent_payload.json"
    audit_path = output_dir / "stage_audit.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    request = json.loads(request_path.read_text(encoding="utf-8-sig"))
    brief = summary.get("decision_brief") if isinstance(summary.get("decision_brief"), dict) else {}
    audit_fingerprint = json.loads((output_dir / "checkpoint_audit_fingerprint_v1.json").read_text(encoding="utf-8-sig"))
    manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8-sig"))
    activity = json.loads((output_dir / "stage_activity_bundle.json").read_text(encoding="utf-8-sig"))
    relative_dir = str(base["project_relative_dir"])

    # The renderer version is presentation identity, not scientific identity.
    presentation_fingerprint = build_presentation_fingerprint(brief, renderer_version="v6")
    summary["schema_version"] = CHECKPOINT_SUMMARY_V6_SCHEMA
    summary["audit_bundle_ref"] = f"{relative_dir}/stage_audit.json"
    summary["audit_render_policy"] = "on_demand_cache_only"
    summary["presentation_sha256"] = presentation_fingerprint["presentation_sha256"]
    summary.pop("stage_summary_sha256", None)
    summary_hash = _hash_payload(summary)
    summary["stage_summary_sha256"] = summary_hash

    request["summary_schema"] = CHECKPOINT_SUMMARY_V6_SCHEMA
    request["checkpoint_package_summary_sha256"] = summary_hash

    decision_path = {
        "project_relative_path": f"{relative_dir}/stage_summary.zh-CN.html",
        "absolute_path": str((output_dir / "stage_summary.zh-CN.html").resolve()),
    }
    decision_path_en = {
        "project_relative_path": f"{relative_dir}/stage_summary.en.html",
        "absolute_path": str((output_dir / "stage_summary.en.html").resolve()),
    }
    technical_audit_json = {
        "project_relative_path": f"{relative_dir}/stage_audit.json",
        "absolute_path": str(audit_path.resolve()),
    }
    decision_question = brief.get("decision_question") if isinstance(brief.get("decision_question"), dict) else {}
    decision_summary = next(
        (
            str(item.get("text_zh") or "").strip()
            for item in brief.get("confirming") or []
            if isinstance(item, dict) and str(item.get("text_zh") or "").strip()
        ),
        str(summary.get("stage_purpose_zh") or ""),
    )
    review_points: list[str] = []
    for group in ("confirming", "claim_boundaries", "not_confirming", "reopen_conditions"):
        for item in brief.get(group) or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text_zh") or "").strip()
            if text and text not in review_points:
                review_points.append(text)
            if len(review_points) >= 5:
                break
        if len(review_points) >= 5:
            break
    continuity = summary.get("confirmation_continuity") if isinstance(summary.get("confirmation_continuity"), dict) else {}
    authority_source = summary.get("authority_source") if isinstance(summary.get("authority_source"), dict) else {}
    authority_reason = (
        "本次科学决定与最近一次有效作者确认相同，系统只沿用原确认。"
        if continuity.get("eligible")
        else f"当前审查主体由 {authority_source.get('policy') or 'review_policy'} 决定。"
    )
    agent = {
        "schema_version": AGENT_PAYLOAD_V3_SCHEMA,
        "summary_schema": CHECKPOINT_SUMMARY_V6_SCHEMA,
        "checkpoint_id": summary["checkpoint_id"],
        "stage": stage,
        "review_state": summary.get("review_state"),
        "stage_narrative_zh": summary.get("stage_narrative_zh"),
        "activity_bundle_sha256": summary.get("activity_bundle_sha256"),
        "primary_human_review_html": decision_path,
        "human_decision_html": decision_path,
        "human_decision_html_en": decision_path_en,
        "stage_summary_zh_html": decision_path,
        "stage_completion_summary_zh": summary.get("stage_narrative_zh"),
        "decision_question_zh": str(decision_question.get("text_zh") or summary.get("stage_purpose_zh") or ""),
        "decision_summary_zh": decision_summary,
        "semantic_delta_summary_zh": str((summary.get("semantic_delta_from_last_confirmed") or {}).get("summary_zh") or ""),
        "semantic_delta_summary_en": str((summary.get("semantic_delta_from_last_confirmed") or {}).get("summary_en") or ""),
        "review_points_zh": review_points,
        "decision_actor_type": summary.get("decision_actor_type"),
        "decision_authority_reason_zh": authority_reason,
        "confirmation_meaning_zh": summary.get("confirmation_meaning_zh"),
        "confirmation_meaning_en": summary.get("confirmation_meaning_en"),
        "scientific_decision_sha256": (summary.get("scientific_decision_fingerprint") or {}).get("scientific_decision_sha256"),
        "human_brief_semantic_sha256": summary.get("human_brief_semantic_sha256"),
        "continuity_status": continuity.get("classification"),
        "reconfirmation_reason_codes": continuity.get("reason_codes") or [],
        "latest_user_visible_deliverables": list(brief.get("latest_user_visible_deliverables") or [])[:8],
        "confirmation_command": request.get("confirmation_command"),
        "confirmation_contract": summary.get("confirmation_contract") or {},
        "decision_brief": {
            "project_relative_path": f"{relative_dir}/human_decision_brief_v1.json",
            "absolute_path": str((output_dir / "human_decision_brief_v1.json").resolve()),
        },
        "technical_audit_json": technical_audit_json,
        "audit_access_policy": "evidence_on_demand",
        "context_budget_bytes": 12 * 1024,
        "stage_summary_sha256": summary_hash,
    }
    if len(json.dumps(agent, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 12 * 1024:
        raise CheckpointSummaryError("Checkpoint v6 Agent payload exceeds the 12 KB decision-context budget.")

    audit_document = {
        "schema_version": "dpl.checkpoint_stage_audit.v1",
        "checkpoint_id": summary["checkpoint_id"],
        "checkpoint_type": summary.get("checkpoint_type"),
        "summary_schema": CHECKPOINT_SUMMARY_V6_SCHEMA,
        "stage_summary_sha256": summary_hash,
        "audit_bundle_sha256": summary.get("audit_bundle_sha256"),
        "audit_fingerprint": audit_fingerprint,
        "artifact_manifest": manifest,
        "stage_activity_bundle": activity,
        "unresolved_issues": summary.get("unresolved") or [],
        "confirmation_request": request,
    }
    audit_document["stage_audit_sha256"] = _hash_payload(audit_document)

    contract_issues = _checkpoint_summary_contract_issues(summary)
    if contract_issues:
        raise CheckpointSummaryError("Checkpoint v6 summary contract failed: " + "; ".join(contract_issues))
    atomic_write_json(summary_path, summary)
    atomic_write_json(request_path, request)
    atomic_write_json(agent_path, agent)
    atomic_write_json(audit_path, audit_document)
    atomic_write_json(output_dir / "checkpoint_presentation_fingerprint_v1.json", presentation_fingerprint)

    # This package was created in the current call, so removing the v5 audit
    # projection cannot remove a user-facing historical record.
    (output_dir / "stage_audit.zh-CN.html").unlink(missing_ok=True)
    decision_html = render_checkpoint_html(root, output_dir, summary, request)
    decision_html_en = render_checkpoint_html(root, output_dir, summary, request, locale="en")
    atomic_write_text(output_dir / "stage_summary.zh-CN.html", decision_html)
    atomic_write_text(output_dir / "stage_summary.en.html", decision_html_en)
    readability = build_checkpoint_readability_report(html=decision_html, brief=brief)
    readability_en = build_checkpoint_readability_report(html=decision_html_en, brief=brief, locale="en")
    atomic_write_json(output_dir / "checkpoint_readability_report.json", readability)
    atomic_write_json(output_dir / "checkpoint_readability_report.en.json", readability_en)
    if readability.get("status") != "passed" or readability_en.get("status") != "passed":
        failures = [
            *list(readability.get("failure_codes") or []),
            *[f"en:{code}" for code in readability_en.get("failure_codes") or []],
        ]
        raise CheckpointSummaryError("Checkpoint v6 decision page failed readability gate: " + ", ".join(failures))
    required_files = (
        output_dir / "stage_summary.json",
        output_dir / "stage_summary.zh-CN.html",
        output_dir / "stage_summary.en.html",
        audit_path,
        output_dir / "confirmation_request.json",
        output_dir / "agent_payload.json",
        output_dir / "human_decision_brief_v1.json",
        output_dir / "scientific_decision_fingerprint_v1.json",
        output_dir / "checkpoint_readability_report.json",
        output_dir / "checkpoint_readability_report.en.json",
        output_dir / "figure_claim_map_v1.json",
    )
    if not all(path.is_file() for path in required_files):
        missing = ", ".join(path.name for path in required_files if not path.is_file())
        raise CheckpointSummaryError("Checkpoint v6 package is incomplete; missing: " + missing)
    if publish_index:
        _publish_checkpoint_index(root, {**summary, "checkpoint_type": stage})
    return {
        **base,
        "schema_version": CHECKPOINT_SUMMARY_V6_SCHEMA,
        "summary_schema": CHECKPOINT_SUMMARY_V6_SCHEMA,
        "stage_summary_sha256": summary_hash,
        "stage_summary_zh_html": f"{relative_dir}/stage_summary.zh-CN.html",
        "absolute_stage_summary_zh_html": str((output_dir / "stage_summary.zh-CN.html").resolve()),
        "stage_summary_en_html": f"{relative_dir}/stage_summary.en.html",
        "absolute_stage_summary_en_html": str((output_dir / "stage_summary.en.html").resolve()),
        "stage_audit_json": f"{relative_dir}/stage_audit.json",
        "absolute_stage_audit_json": str(audit_path.resolve()),
        "technical_audit_json": technical_audit_json,
        "audit_bundle_sha256": summary["audit_bundle_sha256"],
        "presentation_sha256": summary["presentation_sha256"],
        "primary_human_review_html": decision_path,
        "confirmation_command": request.get("confirmation_command"),
    }


def show_checkpoint_summary(
    project: str | Path,
    checkpoint_hash: str | None = None,
    language: str = "zh-CN",
    view: str = "decision",
) -> dict[str, Any]:
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
    pre_figure_claim_v5 = schema == CHECKPOINT_SUMMARY_V5_SCHEMA and _pre_figure_claim_v5_contract(summary)
    pre_method_analysis_v5 = schema == CHECKPOINT_SUMMARY_V5_SCHEMA and _pre_method_analysis_v5_contract(summary)
    legacy_v5_reason_codes = [
        *(["legacy_v5_pre_figure_claim_fingerprint"] if pre_figure_claim_v5 else []),
        *(["legacy_v5_pre_method_analysis_fingerprint"] if pre_method_analysis_v5 else []),
    ]
    request_path = summary_path.parent / "confirmation_request.json"
    if schema in {CHECKPOINT_SUMMARY_V4_SCHEMA, *CURRENT_DECISION_CHECKPOINT_SCHEMAS} and not (summary_path.parent / "stage_activity_bundle.json").is_file():
        return {
            "status": "invalid_summary",
            "project_path": str(root),
            "checkpoint_hash": _checkpoint_record_hash(root, selected) or checkpoint_hash,
            "language": language,
            "review_state": summary.get("review_state") or "unknown",
            "reasons": ["Missing v4 stage_activity_bundle.json companion."],
            "summary": summary,
        }
    if schema == CHECKPOINT_SUMMARY_V5_SCHEMA and not legacy_v5_reason_codes:
        v5_required = (
            "stage_audit.zh-CN.html",
            "stage_summary.en.html",
            "human_decision_brief_v1.json",
            "scientific_decision_fingerprint_v1.json",
            "checkpoint_readability_report.json",
            "checkpoint_readability_report.en.json",
            "figure_claim_map_v1.json",
            "evidence_binding_failure_receipt.json",
        )
        missing_v5 = [name for name in v5_required if not (summary_path.parent / name).is_file()]
        if missing_v5:
            return {
                "status": "invalid_summary",
                "project_path": str(root),
                "checkpoint_hash": _checkpoint_record_hash(root, selected) or checkpoint_hash,
                "language": language,
                "review_state": summary.get("review_state") or "unknown",
                "reasons": ["Missing v5 checkpoint companions: " + ", ".join(missing_v5)],
                "summary": summary,
            }
    if schema == CHECKPOINT_SUMMARY_V6_SCHEMA:
        v6_required = (
            "stage_audit.json",
            "stage_summary.en.html",
            "human_decision_brief_v1.json",
            "scientific_decision_fingerprint_v1.json",
            "checkpoint_readability_report.json",
            "checkpoint_readability_report.en.json",
            "figure_claim_map_v1.json",
            "evidence_binding_failure_receipt.json",
        )
        missing_v6 = [name for name in v6_required if not (summary_path.parent / name).is_file()]
        if missing_v6:
            return {
                "status": "invalid_summary",
                "project_path": str(root),
                "checkpoint_hash": _checkpoint_record_hash(root, selected) or checkpoint_hash,
                "language": language,
                "review_state": summary.get("review_state") or "unknown",
                "reasons": ["Missing v6 checkpoint companions: " + ", ".join(missing_v6)],
                "summary": summary,
            }
    legacy = schema in LEGACY_CHECKPOINT_SUMMARY_SCHEMAS or bool(legacy_v5_reason_codes)
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
    preferred_html_name = "stage_summary.en.html" if language == "en" and schema in CURRENT_DECISION_CHECKPOINT_SCHEMAS else "stage_summary.zh-CN.html"
    return {
        "status": "legacy_summary" if legacy else "ready_for_human_review",
        "project_path": str(root),
        "checkpoint_hash": _checkpoint_record_hash(root, selected) or checkpoint_hash,
        "language": language,
        "view": view,
        "review_state": summary.get("review_state") or ("legacy" if legacy else "unknown"),
        "requires_preview": legacy,
        "preview_command": (
            f'python -m draftpaper_cli.cli audit-checkpoint-v5-migration --project "{root}" --checkpoint-hash "{_checkpoint_record_hash(root, selected) or checkpoint_hash or ""}"'
            if legacy_v5_reason_codes
            else f'python -m draftpaper_cli.cli preview-checkpoint-summary --project "{root}"'
            if legacy
            else None
        ),
        "migration_action": "create_new_v5_checkpoint_and_request_c3" if legacy_v5_reason_codes else None,
        "legacy_reason_codes": legacy_v5_reason_codes,
        "summary": summary,
        "summary_schema": schema,
        "contract_issues": [],
        "stage_summary_zh_html": {
            "project_relative_path": summary_path.parent.joinpath("stage_summary.zh-CN.html").relative_to(root).as_posix(),
            "absolute_path": str(summary_path.parent.joinpath("stage_summary.zh-CN.html").resolve()),
            "source_semantic_sha256": summary.get("stage_summary_sha256"),
        },
        "stage_summary_en_html": (
            {
                "project_relative_path": summary_path.parent.joinpath("stage_summary.en.html").relative_to(root).as_posix(),
                "absolute_path": str(summary_path.parent.joinpath("stage_summary.en.html").resolve()),
            }
            if schema in CURRENT_DECISION_CHECKPOINT_SCHEMAS
            else None
        ),
        "author_decision_html": {
            "project_relative_path": summary_path.parent.joinpath(preferred_html_name).relative_to(root).as_posix(),
            "absolute_path": str(summary_path.parent.joinpath(preferred_html_name).resolve()),
            "locale": "en" if preferred_html_name.endswith(".en.html") else "zh-CN",
        },
        "stage_audit_zh_html": (
            {
                "project_relative_path": summary_path.parent.joinpath("stage_audit.zh-CN.html").relative_to(root).as_posix(),
                "absolute_path": str(summary_path.parent.joinpath("stage_audit.zh-CN.html").resolve()),
            }
            if schema == CHECKPOINT_SUMMARY_V5_SCHEMA
            else None
        ),
        "stage_audit_json": (
            {
                "project_relative_path": summary_path.parent.joinpath("stage_audit.json").relative_to(root).as_posix(),
                "absolute_path": str(summary_path.parent.joinpath("stage_audit.json").resolve()),
            }
            if schema == CHECKPOINT_SUMMARY_V6_SCHEMA
            else None
        ),
        "artifact_manifest": str(summary_path.parent.joinpath("artifact_manifest.json").resolve()),
        "confirmation_request": str(request_path.resolve()),
        "change_report": str(summary_path.parent.joinpath("change_report.json").resolve()),
        "unresolved_issues_report": str(summary_path.parent.joinpath("unresolved_issues.json").resolve()),
        "agent_payload": str(summary_path.parent.joinpath("agent_payload.json").resolve()),
        "stage_activity_bundle": (
            str(summary_path.parent.joinpath("stage_activity_bundle.json").resolve())
            if schema in {CHECKPOINT_SUMMARY_V4_SCHEMA, *CURRENT_DECISION_CHECKPOINT_SCHEMAS}
            else None
        ),
        "human_decision_brief": (
            str(summary_path.parent.joinpath("human_decision_brief_v1.json").resolve())
            if schema in CURRENT_DECISION_CHECKPOINT_SCHEMAS
            else None
        ),
        "scientific_decision_fingerprint": (
            str(summary_path.parent.joinpath("scientific_decision_fingerprint_v1.json").resolve())
            if schema in CURRENT_DECISION_CHECKPOINT_SCHEMAS
            else None
        ),
        "checkpoint_readability_report": (
            str(summary_path.parent.joinpath("checkpoint_readability_report.json").resolve())
            if schema in CURRENT_DECISION_CHECKPOINT_SCHEMAS
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


def _checkpoint_record_by_package_id(root: Path, checkpoint_package_id: str) -> dict[str, Any] | None:
    for record in reversed(_checkpoint_index_records(root)):
        if str(record.get("checkpoint_id") or "") == checkpoint_package_id:
            return record
    candidate = root / CHECKPOINT_ROOT / checkpoint_package_id / "stage_summary.json"
    if candidate.is_file():
        return {"checkpoint_id": checkpoint_package_id, "stage_summary_json": candidate.relative_to(root).as_posix()}
    return None


def show_checkpoint_audit(
    project: str | Path,
    *,
    checkpoint_package_id: str | None = None,
    checkpoint_hash: str | None = None,
) -> dict[str, Any]:
    """Expose the technical audit path without making it the default view."""

    root = project_root(project)
    record = _checkpoint_record_by_package_id(root, checkpoint_package_id) if checkpoint_package_id else _select_checkpoint_record(root, checkpoint_hash)
    if not record:
        return {"status": "not_found", "project_path": str(root)}
    selected_hash = _checkpoint_record_hash(root, record)
    shown = show_checkpoint_summary(root, selected_hash, view="audit") if selected_hash else show_checkpoint_summary(root, None, view="audit")
    schema = shown.get("summary_schema")
    if schema not in CURRENT_DECISION_CHECKPOINT_SCHEMAS:
        return {"status": "unsupported_legacy_audit", "project_path": str(root), "checkpoint_id": record.get("checkpoint_id")}
    if schema == CHECKPOINT_SUMMARY_V6_SCHEMA:
        audit = shown.get("stage_audit_json")
        return {
            "status": "passed",
            "project_path": str(root),
            "checkpoint_id": shown.get("summary", {}).get("checkpoint_id"),
            "technical_audit_json": audit,
            "decision_html": shown.get("stage_summary_zh_html"),
            "artifact_manifest": shown.get("artifact_manifest"),
            "render_command": f'draftpaper render-checkpoint-audit --project "{root}" --checkpoint-package-id "{shown.get("summary", {}).get("checkpoint_id") or ""}"',
        }
    return {
        "status": "passed",
        "project_path": str(root),
        "checkpoint_id": shown.get("summary", {}).get("checkpoint_id"),
        "technical_audit_html": shown.get("stage_audit_zh_html"),
        "decision_html": shown.get("stage_summary_zh_html"),
        "artifact_manifest": shown.get("artifact_manifest"),
    }


def render_checkpoint_audit(
    project: str | Path,
    *,
    checkpoint_package_id: str,
) -> dict[str, Any]:
    """Render a disposable v6 technical-audit HTML cache on explicit request."""

    from .checkpoint_html import render_checkpoint_audit_html

    root = project_root(project)
    record = _checkpoint_record_by_package_id(root, checkpoint_package_id)
    if not record:
        return {"status": "not_found", "project_path": str(root)}
    relative = _relative_project_path(root, str(record.get("stage_summary_json") or ""))
    if not relative:
        return {"status": "not_found", "project_path": str(root)}
    summary_path = root / relative
    output_dir = summary_path.parent
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
        request = json.loads((output_dir / "confirmation_request.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {"status": "invalid", "project_path": str(root), "reason": str(exc)}
    if summary.get("schema_version") != CHECKPOINT_SUMMARY_V6_SCHEMA:
        return {"status": "unsupported_non_v6_summary", "project_path": str(root), "checkpoint_id": checkpoint_package_id}
    audit_json = output_dir / "stage_audit.json"
    if not audit_json.is_file():
        return {"status": "invalid", "project_path": str(root), "reason": "stage_audit_json_missing"}
    cache_dir = root / ".draftpaper" / "render_cache" / "audit"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{checkpoint_package_id}.zh-CN.html"
    atomic_write_text(cache, render_checkpoint_audit_html(root, cache_dir, summary, request))
    return {
        "status": "passed",
        "project_path": str(root),
        "checkpoint_id": checkpoint_package_id,
        "technical_audit_json": {
            "project_relative_path": audit_json.relative_to(root).as_posix(),
            "absolute_path": str(audit_json.resolve()),
        },
        "rendered_audit_html": {
            "project_relative_path": cache.relative_to(root).as_posix(),
            "absolute_path": str(cache.resolve()),
        },
        "cache_only": True,
    }


def compare_checkpoint_decision(
    project: str | Path,
    *,
    checkpoint_hash: str | None = None,
    against: str = "latest-confirmed",
) -> dict[str, Any]:
    """Return the stored semantic comparison; it never changes project state."""

    shown = show_checkpoint_summary(project, checkpoint_hash)
    summary = shown.get("summary") if isinstance(shown.get("summary"), dict) else {}
    if shown.get("summary_schema") not in CURRENT_DECISION_CHECKPOINT_SCHEMAS:
        return {"status": "unsupported_legacy_summary", "project_path": shown.get("project_path"), "against": against}
    return {
        "status": "passed",
        "project_path": shown.get("project_path"),
        "checkpoint_id": summary.get("checkpoint_id"),
        "against": against,
        "scientific_decision_sha256": (summary.get("scientific_decision_fingerprint") or {}).get("scientific_decision_sha256"),
        "semantic_delta": summary.get("semantic_delta_from_last_confirmed") or {},
        "confirmation_continuity": summary.get("confirmation_continuity") or {},
    }


def explain_reconfirmation(project: str | Path, *, checkpoint_package_id: str | None = None) -> dict[str, Any]:
    root = project_root(project)
    record = _checkpoint_record_by_package_id(root, checkpoint_package_id) if checkpoint_package_id else _latest_checkpoint_record(root)
    if not record:
        return {"status": "not_found", "project_path": str(root)}
    checkpoint_hash = _checkpoint_record_hash(root, record)
    comparison = compare_checkpoint_decision(root, checkpoint_hash=checkpoint_hash)
    return {
        **comparison,
        "explanation_zh": (comparison.get("semantic_delta") or {}).get("summary_zh"),
        "reason_codes": (comparison.get("confirmation_continuity") or {}).get("reason_codes") or [],
    }


def validate_checkpoint_readability(
    project: str | Path,
    *,
    checkpoint_package_id: str | None = None,
    language: str = "zh-CN",
) -> dict[str, Any]:
    root = project_root(project)
    record = _checkpoint_record_by_package_id(root, checkpoint_package_id) if checkpoint_package_id else _latest_checkpoint_record(root)
    if not record:
        return {"status": "not_found", "project_path": str(root)}
    relative = _relative_project_path(root, str(record.get("stage_summary_json") or ""))
    path = root / relative if relative else None
    report_name = "checkpoint_readability_report.en.json" if language == "en" else "checkpoint_readability_report.json"
    report_path = path.parent / report_name if path else None
    if not report_path or not report_path.is_file():
        return {"status": "not_found", "project_path": str(root), "reason": "checkpoint_readability_report_missing"}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {"status": "invalid", "project_path": str(root), "reason": str(exc)}
    return {
        "status": report.get("status") or "invalid",
        "project_path": str(root),
        "language": "en" if language == "en" else "zh-CN",
        "report": report,
        "report_path": str(report_path.resolve()),
    }


def show_confirmation_continuity(project: str | Path, *, checkpoint_type: str = "core_evidence") -> dict[str, Any]:
    from .confirmation_continuity import latest_valid_user_receipt

    root = project_root(project)
    record = _latest_checkpoint_record(root)
    current = {}
    if record:
        relative = _relative_project_path(root, str(record.get("stage_summary_json") or ""))
        if relative:
            try:
                current = json.loads((root / relative).read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                current = {}
    return {
        "status": "passed",
        "project_path": str(root),
        "checkpoint_type": checkpoint_type,
        "latest_valid_user_receipt": latest_valid_user_receipt(root, checkpoint_type=checkpoint_type),
        "current_continuity": current.get("confirmation_continuity") if current.get("checkpoint_type") == checkpoint_type else None,
    }


def rebuild_checkpoint_presentation(project: str | Path, *, checkpoint_package_id: str) -> dict[str, Any]:
    """Regenerate decision HTML from immutable v5/v6 facts only."""

    from .checkpoint_html import render_checkpoint_audit_html
    from .checkpoint_readability import build_checkpoint_readability_report

    root = project_root(project)
    record = _checkpoint_record_by_package_id(root, checkpoint_package_id)
    if not record:
        return {"status": "not_found", "project_path": str(root)}
    relative = _relative_project_path(root, str(record.get("stage_summary_json") or ""))
    if not relative:
        return {"status": "not_found", "project_path": str(root)}
    summary_path = root / relative
    output_dir = summary_path.parent
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
        request = json.loads((output_dir / "confirmation_request.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {"status": "invalid", "project_path": str(root), "reason": str(exc)}
    schema = str(summary.get("schema_version") or "")
    if schema not in CURRENT_DECISION_CHECKPOINT_SCHEMAS:
        return {"status": "unsupported_legacy_summary", "project_path": str(root)}
    audit_html = render_checkpoint_audit_html(root, output_dir, summary, request) if schema == CHECKPOINT_SUMMARY_V5_SCHEMA else None
    decision_html = _render_html(root, output_dir, summary, request)
    decision_html_en = _render_html(root, output_dir, summary, request, locale="en")
    report = build_checkpoint_readability_report(html=decision_html, brief=summary.get("decision_brief") or {})
    report_en = build_checkpoint_readability_report(html=decision_html_en, brief=summary.get("decision_brief") or {}, locale="en")
    if audit_html is not None:
        atomic_write_text(output_dir / "stage_audit.zh-CN.html", audit_html)
    atomic_write_text(output_dir / "stage_summary.zh-CN.html", decision_html)
    atomic_write_text(output_dir / "stage_summary.en.html", decision_html_en)
    atomic_write_json(output_dir / "checkpoint_readability_report.json", report)
    atomic_write_json(output_dir / "checkpoint_readability_report.en.json", report_en)
    return {
        "status": "passed" if report.get("status") == "passed" and report_en.get("status") == "passed" else "blocked",
        "project_path": str(root),
        "checkpoint_id": checkpoint_package_id,
        "presentation_sha256": summary.get("presentation_sha256"),
        "decision_html": str((output_dir / "stage_summary.zh-CN.html").resolve()),
        "decision_html_en": str((output_dir / "stage_summary.en.html").resolve()),
        "audit_html": str((output_dir / "stage_audit.zh-CN.html").resolve()) if audit_html is not None else None,
        "technical_audit_json": str((output_dir / "stage_audit.json").resolve()) if schema == CHECKPOINT_SUMMARY_V6_SCHEMA else None,
        "readability_report": str((output_dir / "checkpoint_readability_report.json").resolve()),
        "readability_report_en": str((output_dir / "checkpoint_readability_report.en.json").resolve()),
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
        audit_json_relative = str(Path(relative_json).parent / "stage_audit.json").replace("\\", "/")
        audit_relative = str(Path(relative_json).parent / "stage_audit.zh-CN.html").replace("\\", "/")
        if (root / audit_json_relative).is_file():
            result["stage_audit_json"] = {
                "project_relative_path": audit_json_relative,
                "absolute_path": str((root / audit_json_relative).resolve()),
            }
        elif (root / audit_relative).is_file():
            result["stage_audit_zh_html"] = {
                "project_relative_path": audit_relative,
                "absolute_path": str((root / audit_relative).resolve()),
            }
    if relative_json:
        result["stage_summary_json"] = str((root / relative_json).resolve())
    if event.get("checkpoint_id"):
        result["checkpoint_id"] = event["checkpoint_id"]
    if event.get("scientific_decision_sha256"):
        result["scientific_decision_sha256"] = event["scientific_decision_sha256"]
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
        if schema in CURRENT_DECISION_CHECKPOINT_SCHEMAS:
            fingerprint = summary.get("scientific_decision_fingerprint") if isinstance(summary.get("scientific_decision_fingerprint"), dict) else {}
            if request.get("scientific_decision_sha256") != fingerprint.get("scientific_decision_sha256"):
                reasons.append("v5/v6 confirmation request is not bound to the scientific decision hash.")
            if request.get("human_brief_semantic_sha256") != summary.get("human_brief_semantic_sha256"):
                reasons.append("v5/v6 confirmation request is not bound to the decision brief semantic hash.")
            if request.get("checkpoint_package_summary_sha256") != summary.get("stage_summary_sha256"):
                reasons.append("v5/v6 confirmation request package hash differs from the summary.")
        elif request.get("stage_summary_sha256") != summary.get("stage_summary_sha256"):
            reasons.append("Confirmation request is not bound to the stage summary hash.")
        if request.get("summary_schema") != summary.get("schema_version"):
            reasons.append("Confirmation request is not bound to the current summary schema.")
        expected_request_command = summary.get("review_state") == "confirmable" and (
            schema == CHECKPOINT_SUMMARY_SCHEMA or summary.get("review_requirement") != "notify_only"
        ) and summary.get("decision_status") not in {"agent_approved", "user_confirmed", "continuity_preserved"}
        if schema in CURRENT_DECISION_CHECKPOINT_SCHEMAS:
            expected_request_command = expected_request_command and bool((summary.get("confirmation_contract") or {}).get("requires_user_decision"))
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
        if schema in {CHECKPOINT_SUMMARY_V4_SCHEMA, *CURRENT_DECISION_CHECKPOINT_SCHEMAS}:
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
        if schema in CURRENT_DECISION_CHECKPOINT_SCHEMAS:
            v5_paths = {
                "stage_summary.en.html": path.parent / "stage_summary.en.html",
                "human_decision_brief_v1.json": path.parent / "human_decision_brief_v1.json",
                "scientific_decision_fingerprint_v1.json": path.parent / "scientific_decision_fingerprint_v1.json",
                "checkpoint_readability_report.json": path.parent / "checkpoint_readability_report.json",
                "checkpoint_readability_report.en.json": path.parent / "checkpoint_readability_report.en.json",
                "figure_claim_map_v1.json": path.parent / "figure_claim_map_v1.json",
                "checkpoint_audit_fingerprint_v1.json": path.parent / "checkpoint_audit_fingerprint_v1.json",
            }
            if schema == CHECKPOINT_SUMMARY_V6_SCHEMA:
                v5_paths["stage_audit.json"] = path.parent / "stage_audit.json"
            for name, companion in v5_paths.items():
                if not companion.is_file():
                    reasons.append(f"Missing v5/v6 companion: {name}")
            if not reasons or all(not reason.startswith("Missing v5/v6 companion") for reason in reasons):
                try:
                    brief = json.loads(v5_paths["human_decision_brief_v1.json"].read_text(encoding="utf-8-sig"))
                    fingerprint = json.loads(v5_paths["scientific_decision_fingerprint_v1.json"].read_text(encoding="utf-8-sig"))
                    readability = json.loads(v5_paths["checkpoint_readability_report.json"].read_text(encoding="utf-8-sig"))
                    readability_en = json.loads(v5_paths["checkpoint_readability_report.en.json"].read_text(encoding="utf-8-sig"))
                    figure_map = json.loads(v5_paths["figure_claim_map_v1.json"].read_text(encoding="utf-8-sig"))
                    audit_fingerprint = json.loads(v5_paths["checkpoint_audit_fingerprint_v1.json"].read_text(encoding="utf-8-sig"))
                except (OSError, ValueError) as exc:
                    reasons.append(f"Invalid v5/v6 companion JSON: {exc}")
                else:
                    from .checkpoint_fingerprint import build_scientific_decision_fingerprint
                    from .figure_claim_map import build_figure_claim_map, validate_figure_claim_map

                    if brief != summary.get("decision_brief"):
                        reasons.append("Human decision brief file differs from the v5/v6 summary.")
                    if fingerprint != summary.get("scientific_decision_fingerprint"):
                        reasons.append("Scientific decision fingerprint file differs from the v5/v6 summary.")
                    recomputed_figure_map = build_figure_claim_map(summary, brief)
                    if figure_map != recomputed_figure_map:
                        reasons.append("FigureClaimMap file differs from the v5/v6 summary projection.")
                    figure_issues = validate_figure_claim_map(figure_map)
                    if figure_issues:
                        reasons.append("FigureClaimMap contains unresolved alignment issues.")
                    recomputed_fingerprint = build_scientific_decision_fingerprint(
                        summary,
                        brief,
                        figure_claim_map=figure_map,
                    )
                    if fingerprint != recomputed_fingerprint:
                        reasons.append("Scientific fingerprint no longer matches the current FigureClaimMap projection.")
                    if readability.get("status") != "passed":
                        reasons.append("Checkpoint decision page did not pass readability validation.")
                    if readability_en.get("status") != "passed":
                        reasons.append("English checkpoint decision page did not pass readability validation.")
                    if figure_map.get("figure_claim_map_sha256") != summary.get("figure_claim_map_sha256"):
                        reasons.append("FigureClaimMap hash differs from the v5/v6 summary.")
                    if figure_map.get("scientific_figure_claim_sha256") != summary.get("scientific_figure_claim_sha256"):
                        reasons.append("Scientific FigureClaimMap hash differs from the v5/v6 summary.")
                    if audit_fingerprint.get("audit_bundle_sha256") != summary.get("audit_bundle_sha256"):
                        reasons.append("Audit fingerprint differs from the v5/v6 summary.")
                    if schema == CHECKPOINT_SUMMARY_V6_SCHEMA:
                        try:
                            audit_document = json.loads(v5_paths["stage_audit.json"].read_text(encoding="utf-8-sig"))
                        except (OSError, ValueError) as exc:
                            reasons.append(f"Invalid v6 stage audit JSON: {exc}")
                        else:
                            audit_hash = audit_document.get("stage_audit_sha256")
                            audit_subject = dict(audit_document)
                            audit_subject.pop("stage_audit_sha256", None)
                            if audit_hash != _hash_payload(audit_subject):
                                reasons.append("v6 stage audit JSON does not match its hash.")
                            if audit_document.get("stage_summary_sha256") != summary.get("stage_summary_sha256"):
                                reasons.append("v6 stage audit JSON is not bound to the stage summary hash.")
                            if audit_document.get("audit_bundle_sha256") != summary.get("audit_bundle_sha256"):
                                reasons.append("v6 stage audit JSON is not bound to the audit fingerprint.")
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
    report = write_stage_summary_v6(
        project,
        stage=stage,
        command=command,
        payload=payload,
        before_artifacts=before_artifacts,
        checkpoint_id=str(payload.get("checkpoint_id") or "") or None,
        checkpoint_hash=str(payload.get("checkpoint_hash") or "") or None,
    )
    decision_path = {
        "project_relative_path": report["stage_summary_zh_html"],
        "absolute_path": report["absolute_stage_summary_zh_html"],
        "source_semantic_sha256": report["stage_summary_sha256"],
    }
    audit_path = report["technical_audit_json"]
    review_keys = {
        "stage_completion_summary_zh",
        "primary_human_review_html",
        "human_decision_html",
        "semantic_delta_summary_zh",
        "semantic_delta_summary_en",
        "review_points_zh",
        "decision_actor_type",
        "decision_authority_reason_zh",
        "confirmation_meaning_zh",
        "confirmation_meaning_en",
        "confirmation_command",
        "technical_audit_html",
        "technical_audit_json",
        "stage_summary_zh_html",
        "checkpoint_summary",
        "primary_artifacts",
        "unresolved_issues",
        "stage_summary_sha256",
        "scientific_decision_sha256",
    }
    result = {
        "stage_completion_summary_zh": report["stage_completion_summary_zh"],
        "primary_human_review_html": decision_path,
        "human_decision_html": decision_path,
        "semantic_delta_summary_zh": report["semantic_delta_summary_zh"],
        "semantic_delta_summary_en": report["semantic_delta_summary_en"],
        "review_points_zh": report["review_points_zh"],
        "decision_actor_type": report["decision_actor_type"],
        "decision_authority_reason_zh": report["decision_authority_reason_zh"],
        "confirmation_meaning_zh": report["confirmation_meaning_zh"],
        "confirmation_meaning_en": report["confirmation_meaning_en"],
        "confirmation_command": report["confirmation_command"],
        "technical_audit_json": audit_path,
        **{key: value for key, value in payload.items() if key not in review_keys},
        "stage_summary_zh_html": decision_path,
    }
    result["checkpoint_summary"] = {
        "checkpoint_id": report["checkpoint_id"],
        "project_relative_dir": report["project_relative_dir"],
        "absolute_path": report["absolute_stage_summary_zh_html"],
        "stage_summary_json": report["absolute_stage_summary_json"],
        "artifact_manifest": report["absolute_artifact_manifest"],
        "confirmation_request": report["confirmation_request"],
        "stage_audit": report["absolute_stage_audit_json"],
        "human_decision_brief": str((project_root(project) / report["human_decision_brief"]).resolve()),
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
    result["scientific_decision_sha256"] = report["scientific_decision_sha256"]
    return result
