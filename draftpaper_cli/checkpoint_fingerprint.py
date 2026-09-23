"""Semantic fingerprints for checkpoint decisions, audits, and presentation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .artifact_identity import canonical_json
from .checkpoint_brief import brief_semantic_payload
from .figure_claim_map import scientific_figure_claim_subject

SCIENTIFIC_DECISION_FINGERPRINT_SCHEMA = "dpl.scientific_decision_fingerprint.v1"
AUDIT_FINGERPRINT_SCHEMA = "dpl.checkpoint_audit_fingerprint.v1"
PRESENTATION_FINGERPRINT_SCHEMA = "dpl.checkpoint_presentation_fingerprint.v1"

_VOLATILE_KEYS = frozenset({"created_at", "updated_at", "generated_at", "recorded_at", "absolute_path", "project_path", "bundle_sha256"})

_DECISION_FIELD_LABELS = {
    "decision_brief.semantic_subject.facts": ("核心证据事实", "core evidence facts"),
    "figure_claim_map": ("图表与论断的对应关系", "figure-to-claim bindings"),
    "scientific_identity.plan_hash": ("研究蓝图身份", "research blueprint identity"),
    "scientific_identity.method_analysis_contract_sha256": ("方法分析合同身份", "method-analysis contract identity"),
    "scientific_identity.run_id": ("分析运行批次", "analysis run"),
    "scientific_identity.cohort_id": ("研究样本范围", "study cohort"),
    "scientific_identity.sample_unit": ("分析单位", "unit of analysis"),
    "scientific_identity.validation_design": ("验证设计", "validation design"),
    "scientific_identity.metric_definition_id": ("主指标定义", "primary metric definition"),
    "scientific_identity.split_id": ("数据划分", "data split"),
    "scientific_identity.model_id": ("模型身份", "model identity"),
    "scientific_identity.aggregation_id": ("指标汇总方式", "metric aggregation"),
    "decision_brief.semantic_subject.confirming": ("本次确认范围", "confirmation scope"),
    "decision_brief.semantic_subject.not_confirming": ("本次不确认的内容", "items outside this confirmation"),
    "decision_brief.semantic_subject.claim_boundaries": ("论断边界", "claim boundaries"),
    "decision_brief.semantic_subject.figure_claims": ("图表支持的结论", "figure-supported claims"),
    "decision_brief.semantic_subject.reopen_conditions": ("重新确认条件", "reconfirmation conditions"),
}


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _stable(value: Any, *, volatile_keys: frozenset[str] = _VOLATILE_KEYS) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(item, volatile_keys=volatile_keys) for key, item in value.items() if str(key) not in volatile_keys}
    if isinstance(value, list):
        return [_stable(item, volatile_keys=volatile_keys) for item in value]
    return value


def _normalize_scientific_payload(payload: Any) -> Any:
    """Remove audit locators that must not manufacture a scientific delta.

    Checkpoint packages deliberately retain fact IDs, evidence-snapshot IDs,
    and claim-to-fact links for auditability.  Those identifiers can be
    regenerated when the same scientific record is re-indexed.  They should
    not force an author to reapprove an otherwise unchanged question, method,
    cohort, metric, figure meaning, or claim boundary.
    """

    normalized = _stable(payload)
    if not isinstance(normalized, Mapping):
        return normalized
    normalized = dict(normalized)

    identity = normalized.get("scientific_identity")
    if isinstance(identity, Mapping):
        identity = dict(identity)
        # Snapshot identity remains in the immutable audit/baseline records.
        # It is a versioned container, not a scientific estimand by itself.
        identity.pop("evidence_snapshot_id", None)
        normalized["scientific_identity"] = identity

    decision_brief = normalized.get("decision_brief")
    if isinstance(decision_brief, Mapping):
        decision_brief = dict(decision_brief)
        subject = decision_brief.get("semantic_subject")
        if isinstance(subject, Mapping):
            subject = dict(subject)
            facts = subject.get("facts")
            if isinstance(facts, list):
                subject["facts"] = sorted(
                    [
                        {
                            "fact_type": item.get("fact_type"),
                            "semantic_value": item.get("semantic_value"),
                        }
                        if isinstance(item, Mapping)
                        else item
                        for item in facts
                    ],
                    key=canonical_json,
                )
            decision_brief["semantic_subject"] = subject
        normalized["decision_brief"] = decision_brief

    figure_claim_map = normalized.get("figure_claim_map")
    if isinstance(figure_claim_map, list):
        normalized["figure_claim_map"] = sorted(
            [
                {str(key): value for key, value in item.items() if str(key) != "claim_fact_refs"}
                if isinstance(item, Mapping)
                else item
                for item in figure_claim_map
            ],
            key=canonical_json,
        )
    return normalized


def scientific_fingerprints_equivalent(previous: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    """Compare scientific content while tolerating regenerated audit locators."""

    previous_payload = previous.get("canonical_payload") if isinstance(previous, Mapping) else None
    current_payload = current.get("canonical_payload") if isinstance(current, Mapping) else None
    if not isinstance(previous_payload, Mapping) or not isinstance(current_payload, Mapping):
        return False
    return _normalize_scientific_payload(previous_payload) == _normalize_scientific_payload(current_payload)


def _identity(summary: dict[str, Any]) -> dict[str, Any]:
    identity = summary.get("identity") if isinstance(summary.get("identity"), dict) else {}
    metrics = summary.get("core_metrics") if isinstance(summary.get("core_metrics"), dict) else {}
    analysis_spec_ids = identity.get("analysis_spec_ids") or metrics.get("analysis_spec_id") or []
    if isinstance(analysis_spec_ids, str):
        analysis_spec_ids = [analysis_spec_ids]
    if not isinstance(analysis_spec_ids, list):
        analysis_spec_ids = []
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
        "analysis_spec_ids": sorted({str(value).strip() for value in analysis_spec_ids if str(value).strip()}),
        "method_analysis_contract_sha256": identity.get("method_analysis_contract_sha256"),
    }


def fingerprint_has_method_analysis_identity(fingerprint: Mapping[str, Any]) -> bool:
    """Return whether a core-decision fingerprint binds method semantics."""

    payload = fingerprint.get("canonical_payload") if isinstance(fingerprint, Mapping) else None
    identity = payload.get("scientific_identity") if isinstance(payload, Mapping) else None
    analysis_spec_ids = identity.get("analysis_spec_ids") if isinstance(identity, Mapping) else None
    return bool(
        isinstance(analysis_spec_ids, list)
        and any(str(value).strip() for value in analysis_spec_ids)
        and str(identity.get("method_analysis_contract_sha256") or "").strip()
    )


def build_scientific_decision_fingerprint(
    summary: dict[str, Any],
    brief: dict[str, Any],
    *,
    figure_claim_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hash only the scientific subject of a decision, never derived layout."""

    payload = {
        "checkpoint_type": summary.get("checkpoint_type") or summary.get("completed_stage"),
        "scientific_identity": _identity(summary),
        "decision_brief": brief_semantic_payload(brief),
        "figure_claim_map": scientific_figure_claim_subject(figure_claim_map or {}),
    }
    payload = _normalize_scientific_payload(payload)
    scientific_identity = payload["scientific_identity"]
    semantic_facts = ((brief.get("semantic_subject") or {}).get("facts") or [])
    has_scientific_fact = any(
        isinstance(item, Mapping) and item.get("fact_type") in {"metric", "count", "figure"}
        for item in semantic_facts
    )
    requires_identity = payload["checkpoint_type"] == "core_evidence" or has_scientific_fact or any(
        value not in (None, "", [], {}) for value in scientific_identity.values()
    )
    required_identity_fields = {"sample_unit", "validation_design"}
    if payload["checkpoint_type"] == "core_evidence":
        required_identity_fields.update({"analysis_spec_ids", "method_analysis_contract_sha256"})
    identity_complete = (
        all(value not in (None, "", [], {}) for key, value in scientific_identity.items() if key in required_identity_fields)
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


def scientific_delta_field_label(field: str, *, locale: str = "zh-CN") -> str:
    """Map an internal fingerprint path to an author-facing decision topic."""

    known = _DECISION_FIELD_LABELS.get(field)
    if known:
        return known[1] if locale == "en" else known[0]
    if field.endswith(".facts"):
        return "core evidence facts" if locale == "en" else "核心证据事实"
    if field.startswith("scientific_identity."):
        return "scientific study identity" if locale == "en" else "研究设计与分析身份"
    return "scientific decision content" if locale == "en" else "科学决定内容"


def human_scientific_delta_summary(delta: Mapping[str, Any], *, locale: str = "zh-CN") -> str:
    """Return an author-facing summary without exposing internal payload paths."""

    if delta.get("classification") != "scientific_change" or not delta.get("changes"):
        key = "summary_en" if locale == "en" else "summary_zh"
        return str(delta.get(key) or delta.get("summary_zh") or "")
    labels = []
    for item in delta.get("changes") or []:
        if not isinstance(item, Mapping):
            continue
        label = scientific_delta_field_label(str(item.get("field") or ""), locale=locale)
        if label not in labels:
            labels.append(label)
    if not labels:
        labels = ["scientific decision content" if locale == "en" else "科学决定内容"]
    joined = ", ".join(labels) if locale == "en" else "、".join(labels)
    if locale == "en":
        return (
            f"Compared with the latest valid confirmation, {joined} changed. "
            "The itemized differences below show what was added, removed, or revised; a new author confirmation is required."
        )
    return f"相对最近一次有效确认，{joined}发生变化。下方列出具体新增、移除或修改内容，因此本次需要新的作者确认。"


def compare_scientific_decisions(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Explain whether a new user decision is scientifically required."""

    current_hash = str(current.get("scientific_decision_sha256") or "")
    if not previous:
        return {
            "classification": "first_scientific_decision",
            "requires_reconfirmation": True,
            "changes": [],
            "summary_zh": "这是该 checkpoint family 的首次有效科学确认，需要作者审阅并确认。",
            "summary_en": "This is the first valid scientific confirmation for this checkpoint family and requires author review.",
        }
    previous_hash = str(previous.get("scientific_decision_sha256") or "")
    if not previous_hash or not current_hash:
        return {
            "classification": "unknown",
            "requires_reconfirmation": True,
            "changes": [],
            "summary_zh": "缺少可比较的科学决定指纹，不能自动沿用先前确认。",
            "summary_en": "A comparable scientific-decision fingerprint is missing, so the prior confirmation cannot be reused automatically.",
        }
    if previous_hash == current_hash or scientific_fingerprints_equivalent(previous, current):
        return {
            "classification": "no_scientific_change",
            "requires_reconfirmation": False,
            "changes": [],
            "summary_zh": "与最近一次有效确认相比，数据、方法、验证身份、主图语义和论断边界均未发生科学变化；本次仅更新技术审计或呈现内容。",
            "summary_en": "Compared with the latest valid confirmation, the data, method, validation identity, main-figure semantics, and claim boundary are unchanged; only technical-audit or presentation material changed.",
        }
    before = _normalize_scientific_payload(previous.get("canonical_payload") if isinstance(previous.get("canonical_payload"), dict) else {})
    after = _normalize_scientific_payload(current.get("canonical_payload") if isinstance(current.get("canonical_payload"), dict) else {})
    changes = _diff(before, after)
    result = {
        "classification": "scientific_change",
        "requires_reconfirmation": True,
        "changes": changes[:50],
    }
    result["summary_zh"] = human_scientific_delta_summary(result, locale="zh-CN")
    result["summary_en"] = human_scientific_delta_summary(result, locale="en")
    return result


__all__ = [
    "AUDIT_FINGERPRINT_SCHEMA",
    "PRESENTATION_FINGERPRINT_SCHEMA",
    "SCIENTIFIC_DECISION_FINGERPRINT_SCHEMA",
    "build_audit_fingerprint",
    "build_presentation_fingerprint",
    "build_scientific_decision_fingerprint",
    "compare_scientific_decisions",
    "human_scientific_delta_summary",
    "scientific_delta_field_label",
    "fingerprint_has_method_analysis_identity",
    "scientific_fingerprints_equivalent",
]
