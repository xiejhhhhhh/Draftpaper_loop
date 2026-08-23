"""Carry a valid author confirmation forward when science has not changed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .artifact_identity import canonical_json
from .passport import project_root, read_jsonl, utc_now
from .review_policy import DECISION_LEDGER
from .state_kernel import atomic_write_json


CONTINUITY_RECEIPT_SCHEMA = "dpl.confirmation_continuity_receipt.v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def latest_valid_user_receipt(project: str | Path, *, checkpoint_type: str) -> dict[str, Any] | None:
    """Read only immutable user receipts which already bind a v5 decision."""

    root = project_root(project)
    for row in reversed(read_jsonl(root / DECISION_LEDGER)):
        if not isinstance(row, dict):
            continue
        if row.get("decision_status") != "user_confirmed" or row.get("stage") != checkpoint_type:
            continue
        if not row.get("scientific_decision_sha256") or not row.get("human_brief_semantic_sha256"):
            continue
        expected = _hash({key: value for key, value in row.items() if key not in {"receipt_sha256", "created_at"}})
        if row.get("receipt_sha256") == expected:
            return row
    return None


def continuity_blocking_reason_codes(
    *,
    scientific_fingerprint: dict[str, Any],
    brief_semantic_sha256: str,
    review_state: str,
    semantic_delta_class: str | None = None,
    unresolved_issues: Iterable[Any] = (),
    reason_codes: Iterable[str] = (),
) -> list[str]:
    """Return conservative reasons why a prior confirmation cannot carry forward.

    Continuity is not a convenience override.  It is available only when the
    current package has complete scientific identity, no unresolved blocking
    evidence, and a classified no-op decision.  This keeps missing, stale,
    conflicting, and unclassified changes from becoming an accidental C3
    bypass.
    """

    reasons = {str(item).strip() for item in reason_codes if str(item).strip()}
    if review_state != "confirmable":
        reasons.add("checkpoint_not_confirmable")
    if not str(scientific_fingerprint.get("scientific_decision_sha256") or "") or not str(brief_semantic_sha256 or ""):
        reasons.add("missing_current_scientific_identity")
    if scientific_fingerprint.get("identity_complete") is not True:
        reasons.add("incomplete_scientific_identity")
    if semantic_delta_class in {"unknown", "unclassified", "blocked"}:
        reasons.add(f"semantic_delta_{semantic_delta_class}")
    for item in unresolved_issues:
        if isinstance(item, dict) and item.get("blocking"):
            reasons.add("unresolved_blocking_evidence")
        elif isinstance(item, str) and item.strip():
            reasons.add("unresolved_evidence")
    for code in tuple(reasons):
        lowered = code.lower()
        if any(token in lowered for token in ("unknown", "unclassified", "missing", "stale", "conflict", "incomplete")):
            reasons.add(code)
    return sorted(reasons)


def evaluate_confirmation_continuity(
    project: str | Path,
    *,
    checkpoint_type: str,
    scientific_fingerprint: dict[str, Any],
    brief_semantic_sha256: str,
    review_state: str,
    blocked_reason_codes: list[str] | None = None,
    semantic_delta_class: str | None = None,
    unresolved_issues: Iterable[Any] = (),
) -> dict[str, Any]:
    """Make a fail-closed continuity decision before a checkpoint is published."""

    previous = latest_valid_user_receipt(project, checkpoint_type=checkpoint_type)
    current_hash = str(scientific_fingerprint.get("scientific_decision_sha256") or "")
    reasons = continuity_blocking_reason_codes(
        scientific_fingerprint=scientific_fingerprint,
        brief_semantic_sha256=brief_semantic_sha256,
        review_state=review_state,
        semantic_delta_class=semantic_delta_class,
        unresolved_issues=unresolved_issues,
        reason_codes=blocked_reason_codes or (),
    )
    if reasons:
        return {
            "eligible": False,
            "classification": "blocked",
            "previous_receipt": previous,
            "reason_codes": reasons,
        }
    if not previous:
        return {
            "eligible": False,
            "classification": "first_scientific_decision",
            "previous_receipt": None,
            "reason_codes": [],
        }
    if previous.get("scientific_decision_sha256") != current_hash:
        return {
            "eligible": False,
            "classification": "scientific_change",
            "previous_receipt": previous,
            "reason_codes": ["scientific_fingerprint_changed"],
        }
    if previous.get("human_brief_semantic_sha256") != brief_semantic_sha256:
        return {
            "eligible": False,
            "classification": "blocked",
            "previous_receipt": previous,
            "reason_codes": ["brief_semantic_subject_changed"],
        }
    return {
        "eligible": True,
        "classification": "no_scientific_change",
        "previous_receipt": previous,
        "reason_codes": [],
    }


def write_confirmation_continuity_receipt(
    output_dir: str | Path,
    *,
    checkpoint_type: str,
    checkpoint_package_id: str,
    scientific_decision_sha256: str,
    human_brief_semantic_sha256: str,
    audit_bundle_sha256: str,
    previous_receipt: dict[str, Any],
    classified_changes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write an immutable local receipt; never mutate the original approval."""

    receipt = {
        "schema_version": CONTINUITY_RECEIPT_SCHEMA,
        "receipt_id": f"continuity-{_hash({'package': checkpoint_package_id, 'science': scientific_decision_sha256, 'previous': previous_receipt.get('receipt_id')})[:20]}",
        "checkpoint_type": checkpoint_type,
        "checkpoint_package_id": checkpoint_package_id,
        "previous_decision_receipt_id": previous_receipt.get("receipt_id"),
        "previous_scientific_decision_sha256": previous_receipt.get("scientific_decision_sha256"),
        "current_scientific_decision_sha256": scientific_decision_sha256,
        "human_brief_semantic_sha256": human_brief_semantic_sha256,
        "current_audit_bundle_sha256": audit_bundle_sha256,
        "semantic_delta_class": "no_scientific_change",
        "classified_changes": classified_changes or [],
        "eligibility_checks": [
            {"name": "prior_user_receipt", "passed": True},
            {"name": "scientific_fingerprint_equal", "passed": True},
            {"name": "brief_semantic_subject_equal", "passed": True},
        ],
        "actor_type": "system",
        "actor_id": "draftpaper-cli",
        "decision_effect": "preserve_previous_user_confirmation",
        "created_at": utc_now(),
    }
    receipt["receipt_sha256"] = _hash({key: value for key, value in receipt.items() if key not in {"receipt_sha256", "created_at"}})
    path = Path(output_dir) / "confirmation_continuity_receipt.json"
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8-sig"))
        if existing.get("receipt_sha256") != receipt["receipt_sha256"]:
            raise RuntimeError("Confirmation continuity receipt collision; checkpoint packages are immutable.")
    else:
        atomic_write_json(path, receipt)
    return {"receipt": receipt, "path": str(path.resolve())}


__all__ = [
    "CONTINUITY_RECEIPT_SCHEMA",
    "continuity_blocking_reason_codes",
    "evaluate_confirmation_continuity",
    "latest_valid_user_receipt",
    "write_confirmation_continuity_receipt",
]
