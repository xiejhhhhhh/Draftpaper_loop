"""Hard separation between reviewer-visible material and internal audit state."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Iterable


REVIEWER_VISIBLE_SCOPE = "reviewer_visible"
INTERNAL_AUDIT_PREFIXES = (
    ".draftpaper/",
    "review/checkpoints/",
    "review/consistency/",
    "review/drift/",
    "review/independent_review/",
    "core_evidence/",
    "results/evidence_snapshots/",
    "results/archive/",
    "results/historical/",
    "results/promoted_evidence_snapshot.json",
)
_ANONYMOUS_BUILD_PREFIX = "quality_checks/blind_reviews/anonymous_build/"
_INTERNAL_FILENAMES = {
    "artifact_manifest.json",
    "checkpoint_ledger.jsonl",
    "confirmation_continuity_receipt.json",
    "evidence_binding_failure_receipt.json",
    "project_passport.yaml",
    "review_decision_receipt.json",
    "workflow_trace.jsonl",
}


def reviewer_visibility_issues(paths: Iterable[str]) -> list[dict[str, str]]:
    """Reject audit-only paths before an anonymous reviewer bundle is frozen."""

    issues: list[dict[str, str]] = []
    for raw in sorted({str(item).replace("\\", "/") for item in paths if str(item).strip()}):
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or raw != path.as_posix():
            issues.append({"path": raw, "code": "noncanonical_reviewer_path"})
            continue
        if raw.startswith(_ANONYMOUS_BUILD_PREFIX):
            # This directory is an intentionally sanitized projection, not an
            # internal report.  Other quality-check paths remain private.
            continue
        if any(raw.startswith(prefix) for prefix in INTERNAL_AUDIT_PREFIXES):
            issues.append({"path": raw, "code": "internal_audit_path_in_reviewer_bundle"})
            continue
        if path.name.lower() in _INTERNAL_FILENAMES:
            issues.append({"path": raw, "code": "internal_audit_filename_in_reviewer_bundle"})
    return issues


def validate_reviewer_visible_frozen(frozen: dict[str, list[dict[str, Any]]]) -> list[dict[str, str]]:
    paths = [str(item.get("path") or "") for group in frozen.values() for item in group if isinstance(item, dict)]
    return reviewer_visibility_issues(paths)


__all__ = ["INTERNAL_AUDIT_PREFIXES", "REVIEWER_VISIBLE_SCOPE", "reviewer_visibility_issues", "validate_reviewer_visible_frozen"]
