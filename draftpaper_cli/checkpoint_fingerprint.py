"""Semantic fingerprints for checkpoint decisions, audits, and presentation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .artifact_identity import canonical_json
from .checkpoint_brief import brief_semantic_payload


SCIENTIFIC_DECISION_FINGERPRINT_SCHEMA = "dpl.scientific_decision_fingerprint.v1"
AUDIT_FINGERPRINT_SCHEMA = "dpl.checkpoint_audit_fingerprint.v1"
PRESENTATION_FINGERPRINT_SCHEMA = "dpl.checkpoint_presentation_fingerprint.v1"

_VOLATILE_KEYS = frozenset({"created_at", "updated_at", "generated_at", "recorded_at", "absolute_path", "project_path", "bundle_sha256"})


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _stable(value: Any, *, volatile_keys: frozenset[str] = _VOLATILE_KEYS) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(item, volatile_keys=volatile_keys) for key, item in value.items() if str(key) not in volatile_keys}
    if isinstance(value, list):
        return [_stable(item, volatile_keys=volatile_keys) for item in value]
    return value


def _identity(summary: dict[str, Any]) -> dict[str, Any]:
    identity = summary.get("identity") if isinstance(summary.get("identity"), dict) else {}
    metrics = summary.get("core_metrics") if isinstance(summary.get("core_metrics"), dict) else {}
    return {
        "plan_hash": identity.get("plan_hash"),
        "run_id": identity.get("run_id") or metrics.get("run_id"),
        "cohort_id": identity.get("cohort_id") or metrics.get("cohort_id"),
        "sample_unit": identity.get("sample_unit") or metrics.get("sample_unit"),
        "validation_design": identity.get("cohort_label") or metrics.get("validation_design"),
        "evidence_snapshot_id": identity.get("evidence_snapshot_id"),
        "metric_definition_id": metrics.get("metric_definition_id") or metrics.get("metric"),
        "split_id": metrics.get("split_id"),
        "model_id": metrics.get("model_id"),
        "aggregation_id": metrics.get("aggregation_id"),
    }


def build_scientific_decision_fingerprint(summary: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    """Hash only the scientific subject of a decision, never derived layout."""

    payload = {
        "checkpoint_type": summary.get("checkpoint_type") or summary.get("completed_stage"),
        "scientific_identity": _identity(summary),
        "decision_brief": brief_semantic_payload(brief),
    }
    payload = _stable(payload)
    scientific_identity = payload["scientific_identity"]
    semantic_facts = ((brief.get("semantic_subject") or {}).get("facts") or [])
    has_scientific_fact = any(
        isinstance(item, Mapping) and item.get("fact_type") in {"metric", "count", "figure"}
        for item in semantic_facts
    )
    requires_identity = payload["checkpoint_type"] == "core_evidence" or has_scientific_fact or any(
        value not in (None, "", [], {}) for value in scientific_identity.values()
    )
    identity_complete = (
        all(value not in (None, "", [], {}) for key, value in scientific_identity.items() if key in {"sample_unit", "validation_design"})
        if requires_identity
        else True
    )
    return {
        "schema_version": SCIENTIFIC_DECISION_FINGERPRINT_SCHEMA,
        "checkpoint_type": payload["checkpoint_type"],
        "canonical_payload": payload,
        "scientific_decision_sha256": _hash(payload),
        "identity_complete": identity_complete,
        "identity_requirement": "scientific" if requires_identity else "non_scientific_stage",
    }


def build_audit_fingerprint(summary: dict[str, Any], activity: dict[str, Any], artifact_manifest: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "checkpoint_type": summary.get("checkpoint_type") or summary.get("completed_stage"),
        "activity": _stable(activity),
        "artifact_manifest": _stable(artifact_manifest),
        "validation_summary": _stable(summary.get("validation_summary") or []),
        "consistency_checks": _stable(summary.get("consistency_checks") or []),
    }
    return {
        "schema_version": AUDIT_FINGERPRINT_SCHEMA,
        "canonical_payload": payload,
        "audit_bundle_sha256": _hash(payload),
    }


def build_presentation_fingerprint(brief: dict[str, Any], *, locale: str = "zh-CN", renderer_version: str = "v5") -> dict[str, Any]:
    payload = {
        "renderer_version": renderer_version,
        "locale": locale,
        "brief_semantic_sha256": brief.get("brief_semantic_sha256"),
        "sections": [
            "decision_question",
            "semantic_delta",
            "confirming",
            "scientific_context",
            "figure_claims",
            "claim_boundaries",
            "not_confirming",
            "reopen_conditions",
            "deliverables",
        ],
    }
    return {
        "schema_version": PRESENTATION_FINGERPRINT_SCHEMA,
        "canonical_payload": payload,
        "presentation_sha256": _hash(payload),
    }


def _diff(previous: Any, current: Any, prefix: str = "") -> list[dict[str, Any]]:
    if isinstance(previous, Mapping) and isinstance(current, Mapping):
        rows: list[dict[str, Any]] = []
        for key in sorted(set(previous) | set(current), key=str):
            child = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_diff(previous.get(key), current.get(key), child))
        return rows
    if previous == current:
        return []
    return [{"field": prefix or "root", "before": previous, "after": current}]


def compare_scientific_decisions(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Explain whether a new user decision is scientifically required."""

    current_hash = str(current.get("scientific_decision_sha256") or "")
    if not previous:
        return {
            "classification": "first_scientific_decision",
            "requires_reconfirmation": True,
            "changes": [],
            "summary_zh": "这是该 checkpoint family 的首次有效科学确认，需要作者审阅并确认。",
        }
    previous_hash = str(previous.get("scientific_decision_sha256") or "")
    if not previous_hash or not current_hash:
        return {
            "classification": "unknown",
            "requires_reconfirmation": True,
            "changes": [],
            "summary_zh": "缺少可比较的科学决定指纹，不能自动沿用先前确认。",
        }
    if previous_hash == current_hash:
        return {
            "classification": "no_scientific_change",
            "requires_reconfirmation": False,
            "changes": [],
            "summary_zh": "与最近一次有效确认相比，数据、方法、验证身份、主图语义和论断边界均未发生科学变化；本次仅更新技术审计或呈现内容。",
        }
    before = previous.get("canonical_payload") if isinstance(previous.get("canonical_payload"), dict) else {}
    after = current.get("canonical_payload") if isinstance(current.get("canonical_payload"), dict) else {}
    changes = _diff(before, after)
    names = "、".join(str(item.get("field")) for item in changes[:5]) or "科学决定内容"
    return {
        "classification": "scientific_change",
        "requires_reconfirmation": True,
        "changes": changes[:50],
        "summary_zh": f"相对最近一次有效确认，以下科学决定字段发生变化：{names}；需要新的作者确认。",
    }


__all__ = [
    "AUDIT_FINGERPRINT_SCHEMA",
    "PRESENTATION_FINGERPRINT_SCHEMA",
    "SCIENTIFIC_DECISION_FINGERPRINT_SCHEMA",
    "build_audit_fingerprint",
    "build_presentation_fingerprint",
    "build_scientific_decision_fingerprint",
    "compare_scientific_decisions",
]
