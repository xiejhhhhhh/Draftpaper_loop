"""Decision-family policy for protected workflow operations.

`protected_action` protects a write boundary. It does not by itself mean that
an author must review a long scientific packet. This module gives every
historically human-gated command an explicit packet and receipt contract.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .artifact_identity import canonical_json

POLICY_SCHEMA = "dpl.protected_action_policy.v1"


def _policy(
    decision_family: str,
    packet_policy: str,
    risk_resolver: str,
    receipt_contract: str,
    delegation_policy: str,
    default_risk: str,
) -> dict[str, str]:
    return {
        "decision_family": decision_family,
        "packet_policy": packet_policy,
        "risk_resolver": risk_resolver,
        "receipt_contract": receipt_contract,
        "delegation_policy": delegation_policy,
        "default_risk": default_risk,
    }


# This table intentionally names every v0.41 human_checkpoint command. New
# protected commands fail closed through policy_for_command and are surfaced by
# audit_human_checkpoint_policy until a maintainer gives them an explicit row.
HUMAN_CHECKPOINT_POLICIES: dict[str, dict[str, str]] = {
    "accept-revision": _policy("content_change", "compact", "change_class", "revision_receipt", "C1_or_C2", "C1"),
    "apply-literature-sync": _policy("content_change", "compact", "literature_delta", "literature_receipt", "C1_or_C3", "C1"),
    "apply-manuscript-completion": _policy("content_change", "compact", "completion_change_class", "completion_receipt", "C1_or_C3", "C1"),
    "apply-manuscript-revision": _policy("content_change", "compact", "revision_change_class", "revision_receipt", "C1_or_C3", "C1"),
    "apply-orphan-adoption": _policy("operational_change", "compact", "adoption_scope", "operation_receipt", "C2_only", "C2"),
    "apply-result-downgrade": _policy("scientific_route", "full", "result_route", "user_decision_receipt", "human_only", "C3"),
    "begin-revision-cycle": _policy("notification", "notification", "user_intent", "user_intent_receipt", "C1", "C0"),
    "checkpoint": _policy("notification", "none", "packet_build", "none", "system", "C0"),
    "configure-review-policy": _policy("operational_change", "compact", "authority_scope", "user_decision_receipt", "human_only", "C3"),
    "confirm-final-manuscript": _policy("manuscript_release", "full", "release_identity", "user_decision_receipt", "human_only", "C3"),
    "confirm-literature-corpus": _policy("literature_corpus", "compact", "literature_corpus_identity", "literature_confirmation_receipt", "human_only", "C2"),
    "confirm-research-plan": _policy("scientific_plan", "full", "scientific_plan_identity", "user_decision_receipt", "human_only", "C3"),
    "fetch-research-code-archive": _policy("plugin_license", "compact", "external_archive_license", "user_decision_receipt", "human_only", "C3"),
    "grant-agent-review": _policy("operational_change", "compact", "delegation_scope", "user_decision_receipt", "human_only", "C3"),
    "job-cancel": _policy("operational_change", "compact", "job_ownership", "operation_receipt", "C1_or_C2", "C1"),
    "prepare-result-rescue": _policy("scientific_route", "full", "result_route", "user_decision_receipt", "human_only", "C3"),
    "promote-plugin-candidate": _policy("plugin_license", "full", "plugin_license_execution", "user_decision_receipt", "human_only", "C3"),
    "quarantine-orphan-literature": _policy("operational_change", "compact", "active_work_impact", "literature_receipt", "C1_or_C3", "C1"),
    "rebase-project-passport": _policy("operational_change", "compact", "baseline_adoption", "operation_receipt", "C2_or_C3", "C2"),
    "reconcile-project-drift": _policy("operational_change", "compact", "drift_route", "reconciliation_receipt", "C1_or_C3", "C2"),
    "reopen-core-evidence": _policy("scientific_evidence", "notification", "user_intent_or_scientific_route", "user_intent_receipt", "human_intent", "C3"),
    "reopen-research-plan": _policy("scientific_plan", "notification", "user_intent_or_scientific_route", "user_intent_receipt", "human_intent", "C3"),
    "resume": _policy("notification", "none", "receipt_consumer", "existing_receipt", "system_or_agent", "C0"),
    "revoke-agent-review": _policy("operational_change", "notification", "authority_reduction", "operation_receipt", "system_or_user", "C0"),
    "rollback-literature-migration": _policy("operational_change", "compact", "active_work_impact", "operation_receipt", "C2_or_C3", "C2"),
    "rollback-manuscript-completion": _policy("content_change", "compact", "completion_change_class", "operation_receipt", "C2_or_C3", "C2"),
    "rollback-manuscript-revision": _policy("content_change", "compact", "revision_change_class", "operation_receipt", "C1_or_C3", "C1"),
    "rollback-orphan-literature": _policy("operational_change", "compact", "active_work_impact", "operation_receipt", "C2_or_C3", "C2"),
}


def policy_for_command(name: str, *, protected: bool = False) -> dict[str, str]:
    """Return an explicit policy or a fail-closed policy for new operations."""

    if name in HUMAN_CHECKPOINT_POLICIES:
        return dict(HUMAN_CHECKPOINT_POLICIES[name])
    if protected:
        return _policy(
            "operational_change",
            "compact",
            "strict_unknown",
            "user_decision_receipt",
            "human_only",
            "C3",
        )
    return _policy("none", "none", "none", "none", "none", "C0")


def build_operation_effect_fingerprint(command: str, effect: Mapping[str, Any]) -> dict[str, Any]:
    """Create an auditable identity for a compact operational decision.

    This intentionally identifies declared operation effects, not a scientific
    claim.  It is the reusable counterpart to `ScientificPlanFingerprint` for
    rollback, rebase, quarantine, and other protected operational routes.
    """

    policy = policy_for_command(str(command), protected=True)
    subject = {
        "command": str(command),
        "decision_family": policy["decision_family"],
        "risk_resolver": policy["risk_resolver"],
        "effect": dict(effect),
    }
    digest = hashlib.sha256(canonical_json(subject).encode("utf-8")).hexdigest()
    return {
        "schema_version": "dpl.operation_effect_fingerprint.v1",
        "operation_subject": subject,
        "operation_effect_sha256": digest,
    }


def audit_human_checkpoint_policy(command_specs: Mapping[str, Any]) -> dict[str, Any]:
    """Verify that protected/human commands cannot silently inherit a policy."""

    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    for name, spec in sorted(command_specs.items()):
        protected = bool(getattr(spec, "protected_action", False))
        historical_human = str(getattr(spec, "risk_level", "")) == "human_checkpoint"
        if not protected and not historical_human:
            continue
        policy = policy_for_command(name, protected=protected)
        explicit = name in HUMAN_CHECKPOINT_POLICIES
        rows.append({"command": name, "explicit": explicit, **policy})
        if protected and not explicit:
            issues.append(f"{name}:protected_command_has_no_explicit_policy")
        for field in (
            "decision_family",
            "packet_policy",
            "risk_resolver",
            "receipt_contract",
            "delegation_policy",
        ):
            allows_none = (
                policy["decision_family"] == "notification"
                and field in {"packet_policy", "receipt_contract"}
            )
            if not policy.get(field) or (policy[field] == "none" and not allows_none):
                issues.append(f"{name}:missing_{field}")
    return {
        "schema_version": POLICY_SCHEMA,
        "status": "passed" if not issues else "failed",
        "historical_human_checkpoint_count": len(HUMAN_CHECKPOINT_POLICIES),
        "rows": rows,
        "issues": issues,
    }


def audit_registered_human_checkpoint_policy() -> dict[str, Any]:
    """CLI adapter that reads the completed registry after import initialization."""

    from .command_registry import COMMAND_SPECS

    return audit_human_checkpoint_policy(COMMAND_SPECS)


__all__ = [
    "HUMAN_CHECKPOINT_POLICIES",
    "POLICY_SCHEMA",
    "audit_human_checkpoint_policy",
    "audit_registered_human_checkpoint_policy",
    "build_operation_effect_fingerprint",
    "policy_for_command",
]
