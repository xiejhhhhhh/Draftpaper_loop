"""Semantic and audit identities for research-plan decisions.

Research plans used to be confirmed with one digest over a group of files.
That made wording, projection, timestamp, and manifest changes look like new
scientific decisions.  This module keeps the exact artifact inventory for
audit while hashing a conservative, structured scientific subject separately.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .artifact_identity import canonical_json, sha256_file


SCIENTIFIC_PLAN_FINGERPRINT_SCHEMA = "dpl.scientific_plan_fingerprint.v1"
PLAN_AUDIT_FINGERPRINT_SCHEMA = "dpl.research_plan_audit_fingerprint.v1"
PLAN_PRESENTATION_FINGERPRINT_SCHEMA = "dpl.research_plan_presentation_fingerprint.v1"

STRUCTURED_PLAN_ARTIFACTS = (
    "research_plan/research_blueprint.json",
    "research_plan/claim_contract.json",
    "research_plan/figure_storyboard.json",
    "research_plan/method_plan.json",
    "research_plan/discipline_contract.json",
    "research_plan/research_capability_contract.json",
    "research_plan/statistical_validation_contract.json",
)

VOLATILE_KEYS = frozenset(
    {
        "created_at",
        "generated_at",
        "updated_at",
        "rendered_at",
        "retrieved_at",
        "reviewed_at",
        "timestamp",
        "timestamps",
        "sha256",
        "hash",
        "fingerprint",
        "path",
        "absolute_path",
        "project_path",
        "relative_path",
        "size_bytes",
        "byte_sha256",
        "semantic_sha256",
        "evidence_sha256",
        "status",
        "stage_status",
        "output_path",
        "report_path",
        "html",
        "markdown",
        "generated_files",
    }
)

PRESENTATION_SUFFIXES = (
    "_zh_cn",
    "_zh",
    "_en",
    "_en_us",
    "_en_gb",
    "_html",
    "_markdown",
)

SET_LIST_FIELDS = frozenset(
    {
        "required_data",
        "required_data_roles",
        "required_method",
        "required_methods",
        "data_roles",
        "roles",
        "method_ids",
        "claim_ids",
        "figure_ids",
        "table_ids",
        "plugin_ids",
        "capability_ids",
        "missing_rule_families",
        "secondary_disciplines",
        "allowed_claim_strengths",
    }
)

IDENTITY_KEYS = (
    "claim_id",
    "figure_id",
    "panel_id",
    "table_id",
    "task_id",
    "requirement_id",
    "method_id",
    "role_id",
    "id",
    "name",
)


class ResearchPlanFingerprintError(RuntimeError):
    """Raised when a plan cannot be reduced to a safe semantic subject."""


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def plan_artifact_records(root: str | Path, *, artifacts: tuple[str, ...] = STRUCTURED_PLAN_ARTIFACTS) -> tuple[list[dict[str, Any]], list[str]]:
    project_root = Path(root)
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative in artifacts:
        path = project_root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        records.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "kind": "structured_plan_contract",
            }
        )
    return records, missing


def _localization_base(key: str) -> str | None:
    lowered = key.lower()
    for suffix in PRESENTATION_SUFFIXES:
        if lowered.endswith(suffix):
            return key[: -len(suffix)]
    return None


def _is_volatile_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in VOLATILE_KEYS
        or lowered.startswith("_")
        or lowered.endswith("_sha256")
        or lowered.endswith("_hash")
        or lowered.endswith("_path")
        or lowered.startswith("display_")
    )


def _normalise(value: Any, *, parent_key: str = "") -> Any:
    """Keep unknown scientific fields while removing declared presentation noise.

    Unknown fields deliberately remain in the subject.  That is fail-closed:
    a future adapter field causes a new confirmation rather than accidental
    continuity.  Localized fields are only folded into their canonical field
    when no non-localized counterpart exists.
    """

    if isinstance(value, Mapping):
        source = {str(key): item for key, item in value.items()}
        result: dict[str, Any] = {}
        for key in sorted(source):
            if _is_volatile_key(key):
                continue
            base = _localization_base(key)
            if base is not None:
                if base in source and source.get(base) not in (None, "", [], {}):
                    continue
                normalized_key = base
            else:
                normalized_key = key
            item = _normalise(source[key], parent_key=normalized_key)
            if item in (None, "", [], {}):
                continue
            existing = result.get(normalized_key)
            if existing is None or key == normalized_key:
                result[normalized_key] = item
        return result
    if isinstance(value, (list, tuple)):
        items = [_normalise(item, parent_key=parent_key) for item in value]
        items = [item for item in items if item not in (None, "", [], {})]
        if parent_key in SET_LIST_FIELDS:
            return sorted(items, key=canonical_json)
        if items and all(isinstance(item, Mapping) for item in items):
            identity_key = next(
                (
                    key
                    for key in IDENTITY_KEYS
                    if all(str(dict(item).get(key) or "").strip() for item in items)
                ),
                None,
            )
            if identity_key:
                return sorted(items, key=lambda item: str(dict(item).get(identity_key)))
        return items
    return value


def _structured_contracts(root: Path) -> tuple[dict[str, Any], list[str]]:
    contracts: dict[str, Any] = {}
    missing: list[str] = []
    for relative in STRUCTURED_PLAN_ARTIFACTS:
        path = root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        payload = read_json_object(path)
        if not payload:
            missing.append(relative)
            continue
        contracts[Path(relative).stem] = _normalise(payload)
    return contracts, missing


def build_scientific_plan_fingerprint(
    root: str | Path,
    *,
    feasibility: Mapping[str, Any] | None = None,
    review_rule_coverage: Mapping[str, Any] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Build the semantic subject a research-plan author actually approves."""

    project_root = Path(root)
    contracts, missing = _structured_contracts(project_root)
    feasibility_subject = _normalise(
        {
            "pre_execution_decision": (feasibility or {}).get("decision"),
            "supported_claim_level": (feasibility or {}).get("supported_claim_level"),
            "review_rule_decision": (review_rule_coverage or {}).get("decision"),
            "missing_rule_families": (review_rule_coverage or {}).get("missing_rule_families") or [],
            "accepted_or_pending_limitations": sorted({str(item) for item in limitations or [] if str(item).strip()}),
        }
    )
    subject = {
        "contracts": contracts,
        "feasibility_boundary": feasibility_subject,
    }
    identity_complete = not missing and bool(contracts)
    result = {
        "schema_version": SCIENTIFIC_PLAN_FINGERPRINT_SCHEMA,
        "identity_complete": identity_complete,
        "missing_artifacts": sorted(set(missing)),
        "scientific_plan_subject": subject,
    }
    result["scientific_plan_sha256"] = _hash(subject)
    # Generic confirmation infrastructure uses this spelling.
    result["scientific_decision_sha256"] = result["scientific_plan_sha256"]
    return result


def build_plan_audit_fingerprint(
    root: str | Path,
    *,
    extra_artifacts: list[dict[str, Any]] | None = None,
    validation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    project_root = Path(root)
    records, missing = plan_artifact_records(project_root)
    for record in extra_artifacts or []:
        if isinstance(record, Mapping):
            records.append(dict(record))
    subject = {
        "artifact_records": sorted(records, key=lambda item: str(item.get("path") or "")),
        "missing_artifacts": sorted(set(missing)),
        "validation": _normalise(dict(validation or {})),
    }
    return {
        "schema_version": PLAN_AUDIT_FINGERPRINT_SCHEMA,
        "audit_subject": subject,
        "audit_bundle_sha256": _hash(subject),
    }


def build_plan_presentation_fingerprint(brief: Mapping[str, Any]) -> dict[str, Any]:
    subject = {
        "brief_semantic_sha256": str(brief.get("brief_semantic_sha256") or ""),
        "renderer_contract": "research_plan_decision_html.v1",
        "locales": ["zh-CN", "en"],
    }
    return {
        "schema_version": PLAN_PRESENTATION_FINGERPRINT_SCHEMA,
        "presentation_subject": subject,
        "presentation_sha256": _hash(subject),
    }


def legacy_plan_file_hash(root: str | Path) -> str:
    """Return the v1 exact-file identity for compatibility diagnostics."""

    records, missing = plan_artifact_records(root)
    if missing:
        raise ResearchPlanFingerprintError("Research blueprint is incomplete: " + ", ".join(missing))
    payload = [{"path": item["path"], "sha256": item["sha256"], "size_bytes": item["size_bytes"]} for item in records]
    return _hash(payload)


def _diff_paths(before: Any, after: Any, *, prefix: str = "", limit: int = 40) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []

    def walk(left: Any, right: Any, path: str) -> None:
        if len(changes) >= limit:
            return
        if type(left) is not type(right):
            changes.append({"path": path or "$", "before": left, "after": right})
            return
        if isinstance(left, Mapping):
            keys = sorted({*left.keys(), *right.keys()}, key=str)
            for key in keys:
                if len(changes) >= limit:
                    return
                if key not in left or key not in right:
                    changes.append({"path": f"{path}.{key}" if path else str(key), "before": left.get(key), "after": right.get(key)})
                else:
                    walk(left[key], right[key], f"{path}.{key}" if path else str(key))
            return
        if isinstance(left, list):
            if left != right:
                changes.append({"path": path or "$", "before": left, "after": right})
            return
        if left != right:
            changes.append({"path": path or "$", "before": left, "after": right})

    walk(before, after, prefix)
    return changes


def compare_scientific_plan_fingerprints(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a readable, conservative plan-decision delta."""

    if not current.get("identity_complete"):
        return {
            "classification": "blocked",
            "summary_zh": "当前研究计划缺少结构化合同，不能判断是否可沿用确认。",
            "summary_en": "The current research plan lacks required structured contracts.",
            "changes": [{"path": "missing_artifacts", "after": current.get("missing_artifacts") or []}],
        }
    if not previous:
        return {
            "classification": "first_scientific_decision",
            "summary_zh": "这是首次形成完整研究计划，需要作者确认。",
            "summary_en": "This is the first complete research-plan decision.",
            "changes": [],
        }
    prior_subject = previous.get("scientific_plan_subject") or previous.get("scientific_subject")
    current_subject = current.get("scientific_plan_subject")
    if not isinstance(prior_subject, Mapping):
        return {
            "classification": "unknown",
            "summary_zh": "上一确认缺少可迁移的语义主体，不能自动沿用。",
            "summary_en": "The prior decision lacks a migratable semantic subject.",
            "changes": [],
        }
    if previous.get("scientific_plan_sha256") == current.get("scientific_plan_sha256") or _hash(prior_subject) == _hash(current_subject):
        return {
            "classification": "no_scientific_change",
            "summary_zh": "研究问题、claim、数据角色、方法、统计和图表合同没有科学变化。",
            "summary_en": "The research question, claims, data roles, methods, statistics, and figure contracts are unchanged.",
            "changes": [],
        }
    changes = _diff_paths(prior_subject, current_subject)
    return {
        "classification": "scientific_change",
        "summary_zh": "研究计划的结构化科学合同发生变化，必须重新确认。",
        "summary_en": "The structured scientific plan changed and requires a new confirmation.",
        "changes": changes,
    }


__all__ = [
    "PLAN_AUDIT_FINGERPRINT_SCHEMA",
    "PLAN_PRESENTATION_FINGERPRINT_SCHEMA",
    "SCIENTIFIC_PLAN_FINGERPRINT_SCHEMA",
    "STRUCTURED_PLAN_ARTIFACTS",
    "ResearchPlanFingerprintError",
    "build_plan_audit_fingerprint",
    "build_plan_presentation_fingerprint",
    "build_scientific_plan_fingerprint",
    "compare_scientific_plan_fingerprints",
    "legacy_plan_file_hash",
    "plan_artifact_records",
    "read_json_object",
]
