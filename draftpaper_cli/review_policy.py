"""Review authority policy and scoped Agent delegation.

This module owns the policy boundary for checkpoint review.  A delegation is
an auditable capability grant; it never changes the identity of the decision
actor and it never authorizes a C3 scientific or release decision.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .artifact_identity import canonical_json
from .passport import project_root, read_jsonl, utc_now
from .state_kernel import append_jsonl_locked, atomic_write_json, atomic_write_text


POLICY_SCHEMA = "dpl.review_policy.v1"
DELEGATION_SCHEMA = "dpl.review_delegation.v1"
DECISION_RECEIPT_SCHEMA = "dpl.review_decision_receipt.v2"
POLICY_PATH = ".draftpaper/review_policy.json"
DELEGATION_DIR = ".draftpaper/review_delegations"
DECISION_LEDGER = ".draftpaper/review_decision_ledger.jsonl"
REVOCATION_LEDGER = ".draftpaper/review_delegation_revocations.jsonl"

REVIEW_MODES = frozenset({"manual", "balanced", "delegated"})
REVIEW_REQUIREMENTS = frozenset({"notify_only", "agent_delegable", "human_required"})
DECISION_STATUSES = frozenset(
    {
        "not_required",
        "pending",
        "system_acknowledged",
        "continuity_preserved",
        "agent_approved",
        "user_confirmed",
        "rejected",
        "refinement_required",
    }
)
RISK_ORDER = {"C0": 0, "C1": 1, "C2": 2, "C3": 3}

_C3_STAGES = frozenset(
    {
        "research_plan",
        "research_plan_feasibility",
        "result_support",
        "core_evidence",
        "quality_checks",
        "final_manuscript",
        "release",
    }
)
_C2_STAGES = frozenset({"methods", "method_plan", "plugin", "results", "writing"})
_C1_STAGES = frozenset(
    {
        "references",
        "data",
        "data_writing",
        "methods_writing",
        "introduction",
        "discussion",
        "latex",
        "citation_audit",
    }
)


class ReviewPolicyError(RuntimeError):
    """Raised when a review policy or delegation is invalid."""


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value).strip("-") or uuid.uuid4().hex[:12]


def default_review_policy(*, mode: str = "balanced") -> dict[str, Any]:
    if mode not in REVIEW_MODES:
        raise ReviewPolicyError(f"Unsupported review mode: {mode}")
    payload = {
        "schema_version": POLICY_SCHEMA,
        "mode": mode,
        "default_new_project_mode": "balanced",
        "existing_project_mode": "manual",
        "agent_delegation_enabled": False,
        "delegations": [],
        "human_required_risk_classes": ["C3"],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    payload["policy_sha256"] = _policy_hash(payload)
    return payload


def _policy_hash(policy: dict[str, Any]) -> str:
    # Timestamps document when a policy file was touched; they do not change
    # the authority it grants. Keeping them out of the capability hash means
    # a second delegation does not silently invalidate an earlier one.
    ignored = {"policy_sha256", "created_at", "updated_at", "revoked_at", "revoke_reason"}
    return _hash_payload({key: value for key, value in policy.items() if key not in ignored})


def _runtime_fingerprint(project: str | Path) -> str | None:
    path = project_root(project) / ".draftpaper" / "runtime_lock.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("runtime_fingerprint", "source_commit", "runtime_lock_sha256"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _delegation_hash_is_valid(payload: dict[str, Any]) -> bool:
    stored = str(payload.get("delegation_sha256") or "")
    if not stored:
        return False
    return stored == _hash_payload({key: value for key, value in payload.items() if key != "delegation_sha256"})


def _revoked_delegation_ids(project: str | Path) -> set[str]:
    rows = read_jsonl(project_root(project) / REVOCATION_LEDGER)
    return {
        str(row.get("delegation_id"))
        for row in rows
        if isinstance(row, dict) and row.get("schema_version") == "dpl.review_delegation_revocation.v1" and row.get("delegation_id")
    }


def _delegation_effective_status(project: str | Path, payload: dict[str, Any]) -> str:
    if not _delegation_hash_is_valid(payload):
        return "tampered"
    if str(payload.get("status") or "active") != "active":
        return str(payload.get("status") or "revoked")
    if str(payload.get("delegation_id") or "") in _revoked_delegation_ids(project):
        return "revoked"
    expires_at = payload.get("expires_at")
    if expires_at:
        parsed = _parse_timestamp(expires_at)
        if parsed is None or parsed <= datetime.now(timezone.utc):
            return "expired"
    return "active"


def _delegation_used_count(project: str | Path, delegation_id: str) -> int:
    return sum(
        1
        for row in read_jsonl(project_root(project) / DECISION_LEDGER)
        if isinstance(row, dict)
        and str((row.get("authority_source") or {}).get("delegation_id") or "") == delegation_id
        and row.get("decision_status") == "agent_approved"
    )


def _policy_path(project: str | Path) -> Path:
    return project_root(project) / POLICY_PATH


def initialize_review_policy(project: str | Path, *, mode: str = "balanced") -> dict[str, Any]:
    path = _policy_path(project)
    if path.is_file():
        return load_review_policy(project)
    policy = default_review_policy(mode=mode)
    atomic_write_json(path, policy)
    return policy


def load_review_policy(project: str | Path) -> dict[str, Any]:
    path = _policy_path(project)
    if not path.is_file():
        # Existing projects keep the pre-v0.38 manual behavior until the user
        # explicitly opts into delegation.
        policy = default_review_policy(mode="manual")
        policy["legacy_project_default"] = True
        return policy
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ReviewPolicyError(f"Cannot read review policy: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != POLICY_SCHEMA:
        raise ReviewPolicyError(f"Unsupported review policy: {path}")
    if payload.get("mode") not in REVIEW_MODES:
        raise ReviewPolicyError("Review policy mode must be manual, balanced, or delegated.")
    stored_hash = payload.get("policy_sha256")
    if stored_hash and stored_hash != _policy_hash(payload):
        raise ReviewPolicyError("Review policy hash does not match its stored policy document.")
    if not stored_hash:
        # A legacy project may remain manual, but it cannot grant new authority
        # until the first explicit configuration writes a signed policy.
        payload["legacy_policy_unhashed"] = True
    return payload


def configure_review_policy(project: str | Path, *, mode: str) -> dict[str, Any]:
    if mode not in REVIEW_MODES:
        raise ReviewPolicyError(f"Unsupported review mode: {mode}")
    policy = load_review_policy(project)
    policy["mode"] = mode
    policy.pop("legacy_policy_unhashed", None)
    policy["updated_at"] = utc_now()
    policy["policy_sha256"] = _policy_hash(policy)
    atomic_write_json(_policy_path(project), policy)
    return {"status": "updated", "project_path": str(project_root(project)), "policy": policy}


def _delegation_path(project: str | Path, delegation_id: str) -> Path:
    return project_root(project) / DELEGATION_DIR / f"{_safe_id(delegation_id)}.json"


def _normalize_scope(scope: str | Iterable[str] | None) -> list[str]:
    if isinstance(scope, str):
        values = scope.split(",")
    else:
        values = list(scope or [])
    normalized = sorted({str(item).strip() for item in values if str(item).strip()})
    return normalized or ["*"]


def grant_agent_review(
    project: str | Path,
    *,
    scope: str | Iterable[str],
    max_risk: str = "C1",
    actor_id: str = "agent",
    require_independent_agent: bool = False,
    revision_cycle_id: str | None = None,
    expires_at: str | None = None,
    allowed_change_classes: Iterable[str] = (),
    allow_scientific_freeze: bool = False,
    forbid_external_side_effects: bool = True,
    forbid_unresolved_items: bool = True,
    max_checkpoint_count: int | None = None,
    producer_actor_id: str | None = None,
) -> dict[str, Any]:
    if max_risk not in RISK_ORDER:
        raise ReviewPolicyError("max_risk must be C0, C1, C2, or C3.")
    root = project_root(project)
    policy = load_review_policy(root)
    if policy.get("legacy_policy_unhashed"):
        raise ReviewPolicyError("Configure the review policy explicitly before granting Agent review on an existing project.")
    if expires_at and _parse_timestamp(expires_at) is None:
        raise ReviewPolicyError("expires_at must be an ISO-8601 timestamp with timezone information.")
    if max_checkpoint_count is not None and int(max_checkpoint_count) <= 0:
        raise ReviewPolicyError("max_checkpoint_count must be a positive integer when provided.")
    # The policy is part of the capability grant. Enable it once, then keep
    # its capability hash stable while additional scoped delegations are made.
    if not policy.get("agent_delegation_enabled"):
        policy["agent_delegation_enabled"] = True
        policy["updated_at"] = utc_now()
        policy["policy_sha256"] = _policy_hash(policy)
        atomic_write_json(_policy_path(root), policy)
    delegation_id = uuid.uuid4().hex
    payload = {
        "schema_version": DELEGATION_SCHEMA,
        "delegation_id": delegation_id,
        "project_id": _project_id(project),
        "scope": _normalize_scope(scope),
        "max_risk": max_risk,
        "actor_id": actor_id,
        "producer_actor_id": producer_actor_id,
        "require_independent_agent": bool(require_independent_agent),
        "revision_cycle_id": revision_cycle_id,
        "expires_at": expires_at,
        "max_checkpoint_count": int(max_checkpoint_count) if max_checkpoint_count is not None else None,
        "allowed_change_classes": sorted({str(item) for item in allowed_change_classes if str(item).strip()}),
        "allow_scientific_freeze": bool(allow_scientific_freeze),
        "forbid_external_side_effects": bool(forbid_external_side_effects),
        "forbid_unresolved_items": bool(forbid_unresolved_items),
        "policy_sha256": policy["policy_sha256"],
        "runtime_fingerprint": _runtime_fingerprint(root),
        "status": "active",
        "created_at": utc_now(),
    }
    payload["delegation_sha256"] = _hash_payload(payload)
    path = _delegation_path(root, delegation_id)
    atomic_write_json(path, payload)
    return {"status": "granted", "project_path": str(root), "delegation": payload, "delegation_path": str(path.resolve())}


def _project_id(project: str | Path) -> str | None:
    path = project_root(project) / "project.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return str(payload.get("project_id") or "") or None


def list_delegations(project: str | Path, *, active_only: bool = False) -> list[dict[str, Any]]:
    directory = project_root(project) / DELEGATION_DIR
    rows: list[dict[str, Any]] = []
    if not directory.is_dir():
        return rows
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        effective_status = _delegation_effective_status(project, payload)
        payload = {**payload, "effective_status": effective_status}
        if active_only and effective_status != "active":
            continue
        rows.append(payload)
    return rows


def revoke_agent_review(project: str | Path, *, reason: str) -> dict[str, Any]:
    policy = load_review_policy(project)
    revoked: list[str] = []
    for delegation in list_delegations(project, active_only=True):
        revocation = {
            "schema_version": "dpl.review_delegation_revocation.v1",
            "delegation_id": str(delegation.get("delegation_id")),
            "delegation_sha256": str(delegation.get("delegation_sha256")),
            "reason": reason,
            "revoked_at": utc_now(),
        }
        revocation["revocation_sha256"] = _hash_payload(revocation)
        append_jsonl_locked(project_root(project) / REVOCATION_LEDGER, revocation)
        revoked.append(revocation["delegation_id"])
    policy["agent_delegation_enabled"] = False
    policy["updated_at"] = utc_now()
    policy["revoked_at"] = utc_now()
    policy["revoke_reason"] = reason
    policy["policy_sha256"] = _policy_hash(policy)
    atomic_write_json(_policy_path(project), policy)
    return {"status": "revoked", "project_path": str(project_root(project)), "revoked_delegations": revoked, "reason": reason}


def review_policy_status(project: str | Path) -> dict[str, Any]:
    policy = load_review_policy(project)
    return {
        "status": "passed",
        "project_path": str(project_root(project)),
        "policy": policy,
        "active_delegations": list_delegations(project, active_only=True),
    }


def build_review_authority_shadow(project: str | Path) -> dict[str, Any]:
    """Compare current checkpoints with the new authority policy without acting."""

    root = project_root(project)
    from .checkpoint_summary import show_checkpoint_summary

    events = [item for item in read_jsonl(root / "checkpoint_ledger.jsonl") if item.get("kind") == "checkpoint"]
    rows: list[dict[str, Any]] = []
    for event in events[-200:]:
        checkpoint_hash = str(event.get("hash") or "")
        if not checkpoint_hash:
            continue
        shown = show_checkpoint_summary(root, checkpoint_hash)
        if isinstance(shown.get("summary"), dict):
            evaluation = evaluate_checkpoint_authority(root, checkpoint_hash=checkpoint_hash)
            rows.append(
                {
                    "checkpoint_hash": checkpoint_hash,
                    "checkpoint_id": event.get("checkpoint_id"),
                    "stage": evaluation.get("stage"),
                    "risk_class": evaluation.get("risk_class"),
                    "review_requirement": evaluation.get("review_requirement"),
                    "would_auto_continue": evaluation.get("status") == "notify_only",
                    "would_be_agent_eligible": evaluation.get("can_agent_review"),
                    "would_change_current_behavior": evaluation.get("status") in {"notify_only", "eligible"},
                }
            )
    summary = {
        "schema_version": "dpl.review_authority_shadow.v1",
        "project_path": str(root),
        "policy_mode": load_review_policy(root).get("mode"),
        "shadow_only": True,
        "decision_effect": "none",
        "checkpoint_count": len(rows),
        "rows": rows,
        "counts": {
            "notify_only": sum(item.get("review_requirement") == "notify_only" for item in rows),
            "agent_delegable": sum(item.get("review_requirement") == "agent_delegable" for item in rows),
            "human_required": sum(item.get("review_requirement") == "human_required" for item in rows),
        },
        "created_at": utc_now(),
    }
    summary["shadow_sha256"] = _hash_payload(summary)
    path = root / "review" / "review_authority_shadow.json"
    atomic_write_json(path, summary)
    return {"status": "shadow_reported", "project_path": str(root), "report": summary, "report_path": str(path.resolve())}


def _stage_from_summary(summary: dict[str, Any]) -> str:
    return str(summary.get("completed_stage") or summary.get("checkpoint_type") or "")


def classify_checkpoint_risk(summary: dict[str, Any]) -> str:
    explicit = str(summary.get("risk_class") or summary.get("risk_level") or "").upper()
    if explicit in RISK_ORDER:
        return explicit
    stage = _stage_from_summary(summary)
    if stage in _C3_STAGES:
        return "C3"
    if stage in _C2_STAGES:
        return "C2"
    if stage in _C1_STAGES:
        return "C1"
    return "C0"


def classify_review_requirement(summary: dict[str, Any]) -> str:
    state = str(summary.get("review_state") or "")
    if state != "confirmable":
        return "human_required"
    if summary.get("review_requirement") in REVIEW_REQUIREMENTS:
        return str(summary["review_requirement"])
    risk = classify_checkpoint_risk(summary)
    if risk == "C0":
        return "notify_only"
    if risk == "C3":
        return "human_required"
    return "agent_delegable"


def _summary_change_classes(summary: dict[str, Any]) -> set[str]:
    values: list[Any] = []
    values.extend(summary.get("change_classes") or [])
    transaction = summary.get("transaction_changes")
    if isinstance(transaction, dict):
        values.extend(transaction.get("change_classes") or [])
        values.extend(item.get("change_class") for item in transaction.get("changes") or [] if isinstance(item, dict))
    return {str(item).strip() for item in values if str(item).strip()}


def _has_external_side_effect(summary: dict[str, Any]) -> bool:
    explicit = summary.get("external_side_effects") or summary.get("outside_project_effects") or []
    if isinstance(explicit, bool):
        return explicit
    if isinstance(explicit, (list, tuple, set)):
        return bool(explicit)
    return bool(explicit)


def _has_blocking_unresolved(summary: dict[str, Any]) -> bool:
    for item in summary.get("unresolved") or []:
        if isinstance(item, dict):
            severity = str(item.get("severity") or item.get("status") or "").lower()
            if severity in {"blocked", "blocking", "error", "failed", "missing", "stale"}:
                return True
            if item.get("requires_human_confirmation") or item.get("requires_agent_review"):
                return True
        elif any(token in str(item).lower() for token in ("阻断", "blocked", "stale", "missing", "failed")):
            return True
    return False


def _checkpoint_validation(project: str | Path, checkpoint_hash: str) -> tuple[bool, list[str]]:
    from .checkpoint_summary import _select_checkpoint_record, validate_checkpoint_summary

    record = _select_checkpoint_record(project_root(project), checkpoint_hash)
    if not record:
        return False, ["checkpoint_record_not_found"]
    validation = validate_checkpoint_summary(project, record)
    return bool(validation.get("valid")), [str(item) for item in validation.get("reasons") or []]


def _summary_from_checkpoint(project: str | Path, checkpoint_hash: str) -> tuple[dict[str, Any], str]:
    from .checkpoint_summary import show_checkpoint_summary

    shown = show_checkpoint_summary(project, checkpoint_hash)
    if shown.get("status") not in {"ready_for_human_review", "legacy_summary"}:
        raise ReviewPolicyError("Checkpoint summary is not reviewable: " + "; ".join(map(str, shown.get("reasons") or [])))
    summary = shown.get("summary")
    if not isinstance(summary, dict):
        raise ReviewPolicyError("Checkpoint has no structured summary.")
    return summary, str(shown.get("checkpoint_hash") or checkpoint_hash)


def evaluate_checkpoint_authority(project: str | Path, *, checkpoint_hash: str) -> dict[str, Any]:
    summary, resolved_hash = _summary_from_checkpoint(project, checkpoint_hash)
    policy = load_review_policy(project)
    risk = classify_checkpoint_risk(summary)
    requirement = classify_review_requirement(summary)
    valid_summary, validation_reasons = _checkpoint_validation(project, resolved_hash)
    stage = _stage_from_summary(summary)
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    is_current_summary = summary.get("schema_version") in {
        "dpl.checkpoint_summary.v4",
        "dpl.checkpoint_summary.v5",
        "dpl.checkpoint_summary.v6",
    }
    continuity_preserved = bool((summary.get("confirmation_continuity") or {}).get("eligible")) and summary.get("decision_status") == "continuity_preserved"
    check("current_checkpoint_summary", is_current_summary, "Agent delegation never consumes a legacy or v3 package.")
    check("summary_validation", valid_summary, "; ".join(validation_reasons))
    check("review_state_confirmable", summary.get("review_state") == "confirmable")
    check("no_blocking_unresolved", not _has_blocking_unresolved(summary))
    check("no_external_side_effect", not _has_external_side_effect(summary))
    check("not_c3_or_preserved_continuity", risk != "C3" or continuity_preserved, "C3 routes are human-only unless the exact prior user scientific decision is preserved.")

    delegations = list_delegations(project, active_only=False)
    eligible: list[dict[str, Any]] = []
    rejection_reasons: list[str] = []
    policy_hash = _policy_hash(policy)
    runtime = _runtime_fingerprint(project)
    change_classes = _summary_change_classes(summary)
    for delegation in delegations:
        reasons: list[str] = []
        if delegation.get("effective_status") != "active":
            reasons.append(f"delegation_{delegation.get('effective_status')}")
        scope = set(delegation.get("scope") or [])
        if "*" not in scope and stage not in scope and str(summary.get("checkpoint_type")) not in scope:
            reasons.append("scope_mismatch")
        if RISK_ORDER.get(str(delegation.get("max_risk")), -1) < RISK_ORDER[risk]:
            reasons.append("risk_exceeds_delegation")
        if delegation.get("revision_cycle_id") and delegation.get("revision_cycle_id") != summary.get("revision_cycle_id"):
            reasons.append("revision_cycle_mismatch")
        if delegation.get("policy_sha256") and delegation.get("policy_sha256") != policy_hash:
            reasons.append("policy_hash_mismatch")
        if delegation.get("runtime_fingerprint") and delegation.get("runtime_fingerprint") != runtime:
            reasons.append("runtime_fingerprint_mismatch")
        if delegation.get("max_checkpoint_count") is not None and _delegation_used_count(project, str(delegation.get("delegation_id") or "")) >= int(delegation["max_checkpoint_count"]):
            reasons.append("delegation_checkpoint_limit_reached")
        allowed_change_classes = set(delegation.get("allowed_change_classes") or [])
        if allowed_change_classes and change_classes and not change_classes <= allowed_change_classes:
            reasons.append("change_class_outside_delegation")
        if delegation.get("forbid_external_side_effects", True) and _has_external_side_effect(summary):
            reasons.append("external_side_effect_forbidden")
        if delegation.get("forbid_unresolved_items", True) and _has_blocking_unresolved(summary):
            reasons.append("unresolved_items_forbidden")
        if risk == "C2" and not delegation.get("allow_scientific_freeze", False):
            reasons.append("scientific_freeze_not_granted")
        if risk == "C2" and not delegation.get("require_independent_agent", False):
            reasons.append("independent_reviewer_required")
        candidate = {**delegation, "eligibility_reasons": reasons}
        if not reasons:
            eligible.append(candidate)
        else:
            rejection_reasons.extend(reasons)

    policy_allows = policy.get("mode") in {"balanced", "delegated"} and bool(policy.get("agent_delegation_enabled"))
    hard_checks_pass = all(item["passed"] for item in checks)
    can_agent_review = bool(policy_allows and hard_checks_pass and eligible and requirement == "agent_delegable")
    if requirement == "notify_only" and hard_checks_pass:
        status = "notify_only"
    elif requirement == "human_required" or risk == "C3" or not hard_checks_pass:
        status = "human_required"
    elif can_agent_review:
        status = "eligible"
    else:
        status = "awaiting_delegation"
    return {
        "status": status,
        "project_path": str(project_root(project)),
        "checkpoint_hash": resolved_hash,
        "checkpoint_id": summary.get("checkpoint_id"),
        "stage": _stage_from_summary(summary),
        "risk_class": risk,
        "review_state": summary.get("review_state"),
        "review_requirement": requirement,
        "decision_status": summary.get("decision_status") or ("pending" if requirement != "notify_only" else "not_required"),
        "policy_mode": policy.get("mode"),
        "policy_sha256": policy_hash,
        "runtime_fingerprint": runtime,
        "summary_change_classes": sorted(change_classes),
        "eligibility_checks": checks,
        "eligible_delegations": eligible,
        "can_agent_review": can_agent_review,
        "human_required_reason": "C3, stale/blocked evidence, or an unresolved protected boundary" if status == "human_required" else None,
        "delegation_rejection_reasons": sorted(set(rejection_reasons)),
    }


def _decision_hash(payload: dict[str, Any]) -> str:
    return _hash_payload({key: value for key, value in payload.items() if key not in {"receipt_sha256", "created_at"}})


def review_checkpoint(
    project: str | Path,
    *,
    checkpoint_hash: str,
    actor: str = "agent",
    actor_id: str = "agent",
    delegation_hash: str | None = None,
    reviewer_agent_id: str | None = None,
    decision: str = "approve",
) -> dict[str, Any]:
    authority = evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint_hash)
    if actor != "agent":
        raise ReviewPolicyError("review-checkpoint is the Agent review route; user confirmation remains resume/confirm-*.")
    if decision not in {"approve", "reject", "refine"}:
        raise ReviewPolicyError("decision must be approve, reject, or refine.")
    if not authority.get("can_agent_review"):
        raise ReviewPolicyError("Agent review is not authorized for this checkpoint.")
    delegation = None
    for candidate in authority.get("eligible_delegations") or []:
        if delegation_hash and candidate.get("delegation_sha256") == delegation_hash:
            delegation = candidate
            break
        if not delegation_hash:
            delegation = candidate
            break
    if delegation is None:
        raise ReviewPolicyError("No matching active delegation was found.")
    producer_actor_id = reviewer_agent_id or delegation.get("producer_actor_id") or delegation.get("actor_id")
    if delegation.get("require_independent_agent") and (not producer_actor_id or actor_id == producer_actor_id):
        raise ReviewPolicyError("Independent reviewer Agent must differ from the recorded producing Agent.")
    status = {"approve": "agent_approved", "reject": "rejected", "refine": "refinement_required"}[decision]
    receipt = {
        "schema_version": DECISION_RECEIPT_SCHEMA,
        "receipt_id": uuid.uuid4().hex,
        "project_id": _project_id(project),
        "checkpoint_hash": checkpoint_hash,
        "summary_sha256": _summary_hash(project, checkpoint_hash),
        "decision": decision,
        "decision_status": status,
        "actor_type": "agent",
        "actor_id": actor_id,
        "producer_actor_id": producer_actor_id,
        "authority_source": {
            "delegation_id": delegation.get("delegation_id"),
            "delegation_sha256": delegation.get("delegation_sha256"),
            "policy_sha256": authority.get("policy_sha256"),
        },
        "risk_class": authority.get("risk_class"),
        "stage": authority.get("stage"),
        "revision_cycle_id": (delegation.get("revision_cycle_id") or _summary_revision_cycle(project, checkpoint_hash)),
        "runtime_fingerprint": authority.get("runtime_fingerprint"),
        "evidence_snapshot_id": _summary_evidence_snapshot(project, checkpoint_hash),
        "baseline_id": _summary_baseline_id(project, checkpoint_hash),
        "scientific_decision_fingerprint": _summary_scientific_fingerprint(project, checkpoint_hash),
        "scientific_decision_sha256": (_summary_scientific_fingerprint(project, checkpoint_hash) or {}).get("scientific_decision_sha256"),
        "human_brief_semantic_sha256": _summary_brief_semantic_sha(project, checkpoint_hash),
        "eligibility_checks": authority.get("eligibility_checks") or [],
        "created_at": utc_now(),
    }
    receipt["receipt_sha256"] = _decision_hash(receipt)
    summary_path = _persist_decision_receipt(project, checkpoint_hash, receipt)
    from .scientific_baseline import create_scientific_baseline

    baseline_result = create_scientific_baseline(
        project,
        decision_receipt_id=receipt["receipt_id"],
        revision_cycle_id=delegation.get("revision_cycle_id"),
        reason="agent_review_approved" if decision == "approve" else "agent_review_recorded",
    ) if decision == "approve" else None
    if baseline_result and delegation.get("revision_cycle_id"):
        from .revision_cycle import close_revision_cycle, load_active_revision_cycle

        active_cycle = load_active_revision_cycle(project)
        if active_cycle and active_cycle.get("revision_cycle_id") == delegation.get("revision_cycle_id") and active_cycle.get("status") == "open":
            close_revision_cycle(
                project,
                decision_receipt_id=receipt["receipt_id"],
                candidate_baseline_id=baseline_result["baseline"].get("baseline_id"),
            )
    return {
        "status": "agent_approved" if decision == "approve" else status,
        "project_path": str(project_root(project)),
        "decision_receipt": str((summary_path.parent / "review_decision_receipt.json").resolve()),
        "receipt": receipt,
        "baseline": baseline_result,
        "checkpoint_hash": checkpoint_hash,
        "user_confirmation_preserved": True,
        "next_action": "continue downstream workflow; C3/user confirmation remains unchanged",
    }


def record_user_checkpoint_confirmation(
    project: str | Path,
    *,
    checkpoint_hash: str,
    note: str = "",
    actor_id: str = "user",
) -> dict[str, Any]:
    """Write a receipt for an actual user confirmation without mutating its summary."""

    authority = evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint_hash)
    if authority.get("review_state") != "confirmable":
        raise ReviewPolicyError("A stale or blocked checkpoint cannot be confirmed by the user.")
    # Explicit user confirmation remains valid for a notification checkpoint.
    # It is stronger than the default system acknowledgement and preserves the
    # pre-v0.38 manual workflow for users who intentionally inspect every step.
    receipt = {
        "schema_version": DECISION_RECEIPT_SCHEMA,
        "receipt_id": uuid.uuid4().hex,
        "project_id": _project_id(project),
        "checkpoint_hash": checkpoint_hash,
        "summary_sha256": _summary_hash(project, checkpoint_hash),
        "decision": "approve",
        "decision_status": "user_confirmed",
        "actor_type": "user",
        "actor_id": actor_id,
        "producer_actor_id": None,
        "authority_source": {"policy": "explicit_user_command", "policy_sha256": authority.get("policy_sha256")},
        "risk_class": authority.get("risk_class"),
        "stage": authority.get("stage"),
        "revision_cycle_id": _summary_revision_cycle(project, checkpoint_hash),
        "runtime_fingerprint": authority.get("runtime_fingerprint"),
        "evidence_snapshot_id": _summary_evidence_snapshot(project, checkpoint_hash),
        "baseline_id": _summary_baseline_id(project, checkpoint_hash),
        "scientific_decision_fingerprint": _summary_scientific_fingerprint(project, checkpoint_hash),
        "scientific_decision_sha256": (_summary_scientific_fingerprint(project, checkpoint_hash) or {}).get("scientific_decision_sha256"),
        "human_brief_semantic_sha256": _summary_brief_semantic_sha(project, checkpoint_hash),
        "eligibility_checks": authority.get("eligibility_checks") or [],
        "note": note,
        "created_at": utc_now(),
    }
    receipt["receipt_sha256"] = _decision_hash(receipt)
    _persist_decision_receipt(project, checkpoint_hash, receipt)
    return {"status": "user_confirmed", "project_path": str(project_root(project)), "receipt": receipt}


def acknowledge_notification_checkpoint(
    project: str | Path,
    *,
    checkpoint_hash: str,
) -> dict[str, Any]:
    """Record a non-scientific system acknowledgement for C0 notification stages."""

    authority = evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint_hash)
    if authority.get("status") != "notify_only":
        raise ReviewPolicyError("Only a confirmable notify-only checkpoint can be system-acknowledged.")
    receipt = {
        "schema_version": DECISION_RECEIPT_SCHEMA,
        "receipt_id": uuid.uuid4().hex,
        "project_id": _project_id(project),
        "checkpoint_hash": checkpoint_hash,
        "summary_sha256": _summary_hash(project, checkpoint_hash),
        "decision": "acknowledge",
        "decision_status": "system_acknowledged",
        "actor_type": "system",
        "actor_id": "draftpaper-cli",
        "producer_actor_id": None,
        "authority_source": {"policy": "notify_only", "policy_sha256": authority.get("policy_sha256")},
        "risk_class": authority.get("risk_class"),
        "stage": authority.get("stage"),
        "revision_cycle_id": _summary_revision_cycle(project, checkpoint_hash),
        "runtime_fingerprint": authority.get("runtime_fingerprint"),
        "evidence_snapshot_id": _summary_evidence_snapshot(project, checkpoint_hash),
        "baseline_id": _summary_baseline_id(project, checkpoint_hash),
        "scientific_decision_fingerprint": _summary_scientific_fingerprint(project, checkpoint_hash),
        "scientific_decision_sha256": (_summary_scientific_fingerprint(project, checkpoint_hash) or {}).get("scientific_decision_sha256"),
        "human_brief_semantic_sha256": _summary_brief_semantic_sha(project, checkpoint_hash),
        "eligibility_checks": authority.get("eligibility_checks") or [],
        "created_at": utc_now(),
    }
    receipt["receipt_sha256"] = _decision_hash(receipt)
    _persist_decision_receipt(project, checkpoint_hash, receipt)
    return {"status": "system_acknowledged", "project_path": str(project_root(project)), "receipt": receipt}


def _persist_decision_receipt(project: str | Path, checkpoint_hash: str, receipt: dict[str, Any]) -> Path:
    summary_path = _checkpoint_summary_path(project, checkpoint_hash)
    receipt_dir = summary_path.parent / "review_decision_receipts"
    atomic_write_json(receipt_dir / f"{receipt['receipt_id']}.json", receipt)
    # This is a convenience pointer for the HTML.  The immutable receipt file
    # and append-only ledger remain the source of historical truth.
    atomic_write_json(summary_path.parent / "review_decision_receipt.json", receipt)
    append_jsonl_locked(project_root(project) / DECISION_LEDGER, receipt)
    from .checkpoint_html import render_checkpoint_html

    try:
        summary_payload = json.loads(summary_path.read_text(encoding="utf-8-sig"))
        request_payload = json.loads((summary_path.parent / "confirmation_request.json").read_text(encoding="utf-8-sig"))
        atomic_write_text(
            summary_path.parent / "stage_summary.zh-CN.html",
            render_checkpoint_html(project_root(project), summary_path.parent, summary_payload, request_payload),
        )
    except (OSError, ValueError):
        pass
    return summary_path


def _summary_payload(project: str | Path, checkpoint_hash: str) -> dict[str, Any]:
    try:
        payload = json.loads(_checkpoint_summary_path(project, checkpoint_hash).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, ReviewPolicyError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _summary_revision_cycle(project: str | Path, checkpoint_hash: str) -> str | None:
    value = _summary_payload(project, checkpoint_hash).get("revision_cycle_id")
    return str(value) if value else None


def _summary_evidence_snapshot(project: str | Path, checkpoint_hash: str) -> str | None:
    summary = _summary_payload(project, checkpoint_hash)
    identity = summary.get("identity") if isinstance(summary.get("identity"), dict) else {}
    value = identity.get("evidence_snapshot_id") or summary.get("evidence_snapshot_id")
    return str(value) if value else None


def _summary_baseline_id(project: str | Path, checkpoint_hash: str) -> str | None:
    summary = _summary_payload(project, checkpoint_hash)
    refs = summary.get("baseline_refs") if isinstance(summary.get("baseline_refs"), dict) else {}
    value = refs.get("active_baseline_id")
    return str(value) if value else None


def _summary_scientific_fingerprint(project: str | Path, checkpoint_hash: str) -> dict[str, Any] | None:
    summary = _summary_payload(project, checkpoint_hash)
    payload = summary.get("scientific_decision_fingerprint")
    return payload if isinstance(payload, dict) else None


def _summary_brief_semantic_sha(project: str | Path, checkpoint_hash: str) -> str | None:
    value = _summary_payload(project, checkpoint_hash).get("human_brief_semantic_sha256")
    return str(value) if value else None


def _checkpoint_summary_path(project: str | Path, checkpoint_hash: str) -> Path:
    from .checkpoint_summary import _select_checkpoint_record, _relative_project_path

    root = project_root(project)
    record = _select_checkpoint_record(root, checkpoint_hash)
    relative = _relative_project_path(root, str((record or {}).get("stage_summary_json") or ""))
    if not relative:
        raise ReviewPolicyError("Checkpoint summary path cannot be resolved safely.")
    return root / relative


def _summary_hash(project: str | Path, checkpoint_hash: str) -> str | None:
    payload = _summary_payload(project, checkpoint_hash)
    return str(payload.get("stage_summary_sha256") or "") or None


def decision_receipt_for_checkpoint(project: str | Path, checkpoint_hash: str) -> dict[str, Any] | None:
    try:
        path = _checkpoint_summary_path(project, checkpoint_hash).parent / "review_decision_receipt.json"
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, ReviewPolicyError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != DECISION_RECEIPT_SCHEMA:
        return None
    if payload.get("checkpoint_hash") != checkpoint_hash:
        return None
    if payload.get("receipt_sha256") != _decision_hash(payload):
        return None
    if payload.get("summary_sha256") != _summary_hash(project, checkpoint_hash):
        return None
    return payload


__all__ = [
    "DECISION_RECEIPT_SCHEMA",
    "DELEGATION_SCHEMA",
    "POLICY_SCHEMA",
    "ReviewPolicyError",
    "acknowledge_notification_checkpoint",
    "classify_checkpoint_risk",
    "classify_review_requirement",
    "configure_review_policy",
    "decision_receipt_for_checkpoint",
    "default_review_policy",
    "evaluate_checkpoint_authority",
    "grant_agent_review",
    "build_review_authority_shadow",
    "initialize_review_policy",
    "list_delegations",
    "load_review_policy",
    "review_checkpoint",
    "record_user_checkpoint_confirmation",
    "review_policy_status",
    "revoke_agent_review",
]
