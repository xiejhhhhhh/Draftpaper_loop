"""Read-only migration planning for legacy checkpoint summaries.

Legacy checkpoint packages are evidence records.  This module never rewrites a
v1-v4 package or treats its old summary hash as a v5 scientific decision.  It
only explains whether an explicit v5 checkpoint is required and, when both
versions are already present, whether their scientific subjects can be
compared without copying a user confirmation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json
from .checkpoint_brief import build_human_decision_brief, validate_human_decision_brief
from .checkpoint_fingerprint import build_scientific_decision_fingerprint, compare_scientific_decisions
from .passport import project_root


MIGRATION_AUDIT_SCHEMA = "dpl.checkpoint_v4_v5_migration_audit.v1"
_LEGACY_SCHEMAS = frozenset({"dpl.checkpoint_summary.v1", "dpl.checkpoint_summary.v2", "dpl.checkpoint_summary.v3", "dpl.checkpoint_summary.v4"})


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _load_summary(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _records(root: Path) -> list[dict[str, Any]]:
    from .checkpoint_summary import _checkpoint_index_records

    return _checkpoint_index_records(root)


def _summary_path(root: Path, record: dict[str, Any]) -> Path | None:
    relative = str(record.get("stage_summary_json") or "").replace("\\", "/")
    if not relative or ".." in Path(relative).parts or Path(relative).is_absolute():
        return None
    path = root / relative
    return path if path.is_file() else None


def _select_record(root: Path, checkpoint_hash: str | None) -> dict[str, Any] | None:
    records = _records(root)
    if not records:
        return None
    if not checkpoint_hash:
        return records[-1]
    for record in reversed(records):
        if checkpoint_hash in {str(record.get("hash") or ""), str(record.get("stage_summary_sha256") or ""), str(record.get("checkpoint_id") or "")}:
            return record
        # v4 index rows pre-date the dedicated ``checkpoint_hash`` field.
        # Resolve the immutable summary only for selection, rather than
        # assuming that the derived index carries every legacy identifier.
        path = _summary_path(root, record)
        summary = _load_summary(path) if path else None
        if not summary:
            continue
        identity = summary.get("identity") if isinstance(summary.get("identity"), dict) else {}
        summary_hashes = {
            str(summary.get("checkpoint_hash") or ""),
            str(identity.get("checkpoint_hash") or ""),
        }
        request_path = path.parent / "confirmation_request.json"
        request = _load_summary(request_path)
        if isinstance(request, dict):
            summary_hashes.add(str(request.get("checkpoint_hash") or ""))
        if checkpoint_hash in summary_hashes:
            return record
    return None


def _matching_v5(root: Path, *, stage: str, fingerprint: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    for record in reversed(_records(root)):
        path = _summary_path(root, record)
        if not path:
            continue
        summary = _load_summary(path)
        if not summary or summary.get("schema_version") != "dpl.checkpoint_summary.v5":
            continue
        if str(summary.get("checkpoint_type") or summary.get("completed_stage") or "") != stage:
            continue
        current = summary.get("scientific_decision_fingerprint")
        if isinstance(current, dict) and current.get("scientific_decision_sha256") == fingerprint.get("scientific_decision_sha256"):
            return record, summary
    return None, None


def audit_checkpoint_v5_migration(project: str | Path, *, checkpoint_hash: str | None = None) -> dict[str, Any]:
    """Inspect legacy checkpoint readiness without touching project state."""

    root = project_root(project)
    record = _select_record(root, checkpoint_hash)
    if not record:
        return {"status": "not_found", "project_path": str(root), "checkpoint_hash": checkpoint_hash}
    path = _summary_path(root, record)
    summary = _load_summary(path) if path else None
    if not summary:
        return {
            "status": "invalid",
            "project_path": str(root),
            "checkpoint_id": record.get("checkpoint_id"),
            "reason_codes": ["summary_missing_or_invalid"],
        }
    schema = str(summary.get("schema_version") or "")
    base = {
        "schema_version": MIGRATION_AUDIT_SCHEMA,
        "project_path": str(root),
        "checkpoint_id": summary.get("checkpoint_id") or record.get("checkpoint_id"),
        "checkpoint_type": summary.get("checkpoint_type") or summary.get("completed_stage") or record.get("stage"),
        "source_summary_schema": schema,
        "source_summary_path": str(path.resolve()) if path else None,
        "source_summary_sha256": summary.get("stage_summary_sha256"),
        "source_files_mutated": False,
        "rollback": {"required": False, "reason": "This command is read-only and does not create or overwrite a checkpoint package."},
    }
    if schema == "dpl.checkpoint_summary.v5":
        return {
            **base,
            "status": "already_v5",
            "migration_action": "none",
            "reason_codes": [],
            "scientific_decision_sha256": (summary.get("scientific_decision_fingerprint") or {}).get("scientific_decision_sha256"),
        }
    if schema not in _LEGACY_SCHEMAS:
        return {**base, "status": "unsupported", "migration_action": "none", "reason_codes": ["unsupported_summary_schema"]}

    # v1-v3 do not carry enough structured material for a trustworthy v5
    # decision projection.  v4 can be rendered as a *preview* only.
    if schema != "dpl.checkpoint_summary.v4":
        return {
            **base,
            "status": "legacy_read_only",
            "migration_action": "create_new_v5_checkpoint_and_request_c3",
            "reason_codes": ["legacy_summary_requires_explicit_v5_checkpoint"],
        }
    brief = build_human_decision_brief(summary)
    issues = validate_human_decision_brief(brief)
    fingerprint = build_scientific_decision_fingerprint(summary, brief)
    stage = str(base["checkpoint_type"] or "")
    matching_record, matching_summary = _matching_v5(root, stage=stage, fingerprint=fingerprint)
    if issues or fingerprint.get("identity_complete") is not True:
        return {
            **base,
            "status": "legacy_read_only",
            "migration_action": "create_new_v5_checkpoint_and_request_c3",
            "reason_codes": ["legacy_scientific_identity_incomplete", *issues],
            "legacy_preview_scientific_fingerprint": fingerprint,
        }
    if matching_summary is None:
        return {
            **base,
            "status": "legacy_read_only",
            "migration_action": "create_new_v5_checkpoint_and_request_c3",
            "reason_codes": ["no_matching_v5_scientific_decision"],
            "legacy_preview_scientific_fingerprint": fingerprint,
        }
    comparison = compare_scientific_decisions(fingerprint, matching_summary["scientific_decision_fingerprint"])
    return {
        **base,
        "status": "comparison_ready",
        "migration_action": "explicit_owner_review_required",
        "reason_codes": ["legacy_receipt_is_not_silently_promoted"],
        "legacy_preview_scientific_fingerprint": fingerprint,
        "matching_v5_checkpoint_id": matching_summary.get("checkpoint_id") or matching_record.get("checkpoint_id"),
        "semantic_comparison": comparison,
    }


__all__ = ["MIGRATION_AUDIT_SCHEMA", "audit_checkpoint_v5_migration"]
