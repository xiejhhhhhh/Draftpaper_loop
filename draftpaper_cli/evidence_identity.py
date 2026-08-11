"""Domain-neutral identity and comparability helpers for scientific evidence.

The workflow must never treat a metric or a count as a bare scalar.  This
module keeps identity construction separate from CSV compatibility readers so
that presentation files cannot silently become the scientific source of truth.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


METRIC_IDENTITY_FIELDS = (
    "metric_definition_id",
    "task_id",
    "cohort_id",
    "sample_unit",
    "model_id",
    "validation_design_id",
    "split_id",
    "aggregation_id",
    "uncertainty_definition_id",
)

COUNT_IDENTITY_FIELDS = (
    "count_definition_id",
    "entity_type",
    "count_mode",
    "cohort_id",
    "filter_contract_id",
)

_VALIDATION_ALIASES = (
    "validation_design_id",
    "validation_design",
    "evaluation_design",
    "holdout_scheme",
    "split_strategy",
    "validation",
)
_SPLIT_ALIASES = ("split_id", "split", "split_type", "evaluation_split")
_MODEL_ALIASES = ("model_id", "model", "model_name", "model_variant", "variant")
_TASK_ALIASES = ("task_id", "task", "target_id", "target", "label")
_COHORT_ALIASES = ("cohort_id", "cohort", "cohort_view_id", "analysis_view_id")
_SAMPLE_UNIT_ALIASES = ("sample_unit", "unit_of_analysis", "observation_unit")


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _pick(record: Mapping[str, Any], aliases: Iterable[str]) -> str:
    for key in aliases:
        value = _text(record.get(key))
        if value:
            return value
    return ""


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _normalize_aggregation(record: Mapping[str, Any]) -> tuple[str, bool]:
    raw = _text(record.get("aggregation_id") or record.get("aggregation") or record.get("reducer"))
    if raw:
        aliases = {
            "reported_scalar": "none",
            "reported_value": "none",
            "fold_value": "fold",
            "mean_across_folds": "fold_mean",
            "mean_across_primary_folds": "fold_mean",
            "arithmetic_mean": "mean",
        }
        return aliases.get(raw.lower(), raw), False
    return "", False


def _replicate(record: Mapping[str, Any]) -> tuple[str, list[str]]:
    axis = _text(record.get("replicate_axis") or record.get("replicate_dimension"))
    ids = _as_list(record.get("replicate_ids"))
    for candidate_axis, aliases in (
        ("seed", ("seed", "random_seed")),
        ("fold", ("fold", "fold_id")),
        ("repeated_split", ("repeat", "repetition", "repeated_split_id")),
        ("site", ("site", "site_id")),
    ):
        value = _pick(record, aliases)
        if value and not ids:
            ids = [value]
        if value and not axis:
            axis = candidate_axis
    return axis or "none", ids


def normalize_metric_evidence(
    record: Mapping[str, Any],
    *,
    context: Mapping[str, Any] | None = None,
    source_artifact: str = "",
    source_hash: str = "",
    row_index: int | None = None,
    evidence_role: str | None = None,
) -> dict[str, Any]:
    """Normalize one metric without inventing missing scientific semantics."""

    merged: dict[str, Any] = {}
    if context:
        merged.update(context)
    merged.update({key: value for key, value in dict(record).items() if value is not None and (not isinstance(value, str) or value.strip())})
    metric_name = _text(
        merged.get("metric_definition_id")
        or merged.get("metric_name")
        or merged.get("metric")
        or merged.get("primary_metric")
    )
    model_id = _pick(merged, (*_MODEL_ALIASES, "primary_model_id"))
    task_id = _pick(merged, (*_TASK_ALIASES, "primary_task_id"))
    cohort_id = _pick(merged, _COHORT_ALIASES)
    sample_unit = _pick(merged, _SAMPLE_UNIT_ALIASES)
    validation_design_id = _pick(merged, (*_VALIDATION_ALIASES, "primary_validation_design_id"))
    split_id = _pick(merged, (*_SPLIT_ALIASES, "primary_split_id"))
    aggregation_id, aggregation_inferred = _normalize_aggregation(merged)
    replicate_axis, replicate_ids = _replicate(merged)
    uncertainty = _text(
        merged.get("uncertainty_definition_id")
        or merged.get("uncertainty_definition")
        or ("none" if aggregation_id == "none" else "")
    )
    role = _text(evidence_role or merged.get("evidence_role") or merged.get("role")) or "primary"
    identity = {
        "metric_definition_id": metric_name,
        "task_id": task_id,
        "cohort_id": cohort_id,
        "sample_unit": sample_unit,
        "model_id": model_id,
        "validation_design_id": validation_design_id,
        "split_id": split_id,
        "aggregation_id": aggregation_id,
        "uncertainty_definition_id": uncertainty,
    }
    missing = [key for key, value in identity.items() if not value]
    if aggregation_id not in {"", "none"} and not _text(merged.get("aggregation_contract_id")):
        missing.append("aggregation_contract_id")
    if bool(merged.get("aggregation_inferred")) and "aggregation_contract_id" not in missing:
        missing.append("aggregation_contract_id")
    source = _text(source_artifact or merged.get("source_artifact"))
    source_digest = _text(source_hash or merged.get("source_sha256") or merged.get("source_hash"))
    record_id_seed = {
        "identity": identity,
        "source_artifact": source,
        "source_hash": source_digest,
        "row_index": row_index,
        "replicate_axis": replicate_axis,
        "replicate_ids": replicate_ids,
    }
    normalized = {
        "schema_version": "dpl.metric_evidence.v3",
        "metric_record_id": _text(merged.get("metric_record_id") or merged.get("evidence_id"))
        or _digest(record_id_seed)[:24],
        "identity": identity,
        **identity,
        "value": merged.get("value"),
        "direction": _text(merged.get("direction") or ""),
        "replicate_axis": replicate_axis,
        "replicate_ids": replicate_ids,
        "aggregation_contract_id": _text(merged.get("aggregation_contract_id") or merged.get("aggregation_id")),
        "aggregation_inferred": aggregation_inferred,
        "source_artifact": source,
        "source_sha256": source_digest,
        "producer_id": _text(merged.get("producer_id") or merged.get("producer")),
        "producer_version": _text(merged.get("producer_version")),
        "evidence_role": role,
        "parent_record_refs": _as_list(merged.get("parent_record_refs") or merged.get("aggregation_source_refs")),
        "row_index": row_index,
        "identity_hash": _digest(identity),
        "identity_complete": not missing,
        "missing_identity_fields": missing,
        "legacy_source": not bool(merged.get("schema_version") == "dpl.metric_evidence.v3"),
    }
    return normalized


def normalize_count_evidence(
    record: Mapping[str, Any],
    *,
    context: Mapping[str, Any] | None = None,
    source_artifact: str = "",
    source_hash: str = "",
    row_index: int | None = None,
    evidence_role: str | None = None,
) -> dict[str, Any]:
    """Normalize one count and retain its denominator identity."""

    merged: dict[str, Any] = {}
    if context:
        merged.update(context)
    merged.update({key: value for key, value in dict(record).items() if value is not None and (not isinstance(value, str) or value.strip())})
    count_definition = _text(
        merged.get("count_definition_id")
        or merged.get("count_definition")
        or merged.get("definition")
    )
    entity_type = _text(merged.get("entity_type") or merged.get("entity") or merged.get("unit"))
    count_mode = _text(merged.get("count_mode") or merged.get("mode"))
    cohort_id = _pick(merged, _COHORT_ALIASES)
    filter_contract = _text(merged.get("filter_contract_id") or merged.get("filter_contract") or merged.get("filter"))
    sample_unit = _pick(merged, _SAMPLE_UNIT_ALIASES)
    identity = {
        "count_definition_id": count_definition,
        "entity_type": entity_type,
        "count_mode": count_mode,
        "cohort_id": cohort_id,
        "filter_contract_id": filter_contract,
        "sample_unit": sample_unit,
    }
    missing = [key for key in COUNT_IDENTITY_FIELDS if not identity.get(key)]
    source = _text(source_artifact or merged.get("source_artifact"))
    source_digest = _text(source_hash or merged.get("source_sha256") or merged.get("source_hash"))
    record_id_seed = {"identity": identity, "source": source, "hash": source_digest, "row_index": row_index}
    return {
        "schema_version": "dpl.count_evidence.v1",
        "count_record_id": _text(merged.get("count_record_id") or merged.get("evidence_id"))
        or _digest(record_id_seed)[:24],
        "identity": identity,
        **identity,
        "value": merged.get("value") if "value" in merged else merged.get("count"),
        "parent_count_record_id": _text(merged.get("parent_count_record_id") or merged.get("parent_count_id")) or None,
        "exclusion_reason_table_ref": _text(merged.get("exclusion_reason_table_ref")),
        "source_artifact": source,
        "source_sha256": source_digest,
        "evidence_role": _text(evidence_role or merged.get("evidence_role") or merged.get("role")) or "sample_flow",
        "identity_hash": _digest(identity),
        "identity_complete": not missing,
        "missing_identity_fields": missing,
        "legacy_source": not bool(merged.get("schema_version") == "dpl.count_evidence.v1"),
        "row_index": row_index,
    }


def metric_identity_key(record: Mapping[str, Any]) -> tuple[str, ...]:
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else record
    return tuple(_text(identity.get(key)) for key in METRIC_IDENTITY_FIELDS)


def count_identity_key(record: Mapping[str, Any]) -> tuple[str, ...]:
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else record
    return tuple(_text(identity.get(key)) for key in COUNT_IDENTITY_FIELDS)


def _same_value(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) <= 1e-12
    except (TypeError, ValueError):
        return _stable(left) == _stable(right)


def compare_evidence(left: Mapping[str, Any], right: Mapping[str, Any], *, kind: str = "metric") -> dict[str, Any]:
    """Compare identity before value and return an explicit relation."""

    fields = METRIC_IDENTITY_FIELDS if kind == "metric" else COUNT_IDENTITY_FIELDS
    key_function = metric_identity_key if kind == "metric" else count_identity_key
    left_missing = [field for field in fields if not _text((left.get("identity") or left).get(field))]
    right_missing = [field for field in fields if not _text((right.get("identity") or right).get(field))]
    if left_missing or right_missing:
        return {
            "status": "missing_required_identity",
            "kind": kind,
            "left_id": left.get("metric_record_id") or left.get("count_record_id"),
            "right_id": right.get("metric_record_id") or right.get("count_record_id"),
            "missing": {"left": left_missing, "right": right_missing},
        }
    if key_function(left) != key_function(right):
        parent_refs = set(_as_list(left.get("parent_record_refs") or left.get("aggregation_source_refs")))
        parent_refs.update(_as_list(right.get("parent_record_refs") or right.get("aggregation_source_refs")))
        left_id = _text(left.get("metric_record_id") or left.get("count_record_id"))
        right_id = _text(right.get("metric_record_id") or right.get("count_record_id"))
        if left_id in parent_refs or right_id in parent_refs:
            status = "parent_aggregate_relation"
        else:
            status = "different_identity_non_comparable"
        return {"status": status, "kind": kind, "left_id": left_id, "right_id": right_id}
    left_value = left.get("value")
    right_value = right.get("value")
    return {
        "status": "same_identity_same_value" if _same_value(left_value, right_value) else "same_identity_value_conflict",
        "kind": kind,
        "identity_hash": _digest(key_function(left)),
        "left_id": left.get("metric_record_id") or left.get("count_record_id"),
        "right_id": right.get("metric_record_id") or right.get("count_record_id"),
        "left_value": left_value,
        "right_value": right_value,
    }


def _contract_from_payload(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    for key in ("primary_metric_contract", "primary_metric", "primary_metric_spec"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    if any(key in payload for key in ("metric_definition_id", "metric_name", "primary_metric", "model_id", "primary_model_id")):
        return dict(payload)
    return None


def load_primary_metric_contract(project: str | Path) -> dict[str, Any]:
    """Read an explicit contract; never infer a contract from metric values."""

    root = Path(project)
    candidates = (
        root / "methods" / "primary_metric_contract.json",
        root / "methods" / "method_requirements.json",
        root / "research_plan" / "primary_metric_contract.json",
        root / "research_plan" / "claim_contract.json",
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, Mapping):
            continue
        contract = _contract_from_payload(payload)
        if contract is None:
            continue
        normalized = normalize_metric_evidence(contract, evidence_role="primary_contract")
        normalized["contract_source"] = path.relative_to(root).as_posix()
        normalized["contract_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        normalized["contract_present"] = True
        normalized["contract_fields"] = {
            key: normalized.get(key) for key in METRIC_IDENTITY_FIELDS if normalized.get(key)
        }
        normalized["contract_missing_fields"] = [
            key for key in METRIC_IDENTITY_FIELDS if not normalized.get(key)
        ]
        return normalized
    return {
        "schema_version": "dpl.primary_metric_contract.v1",
        "contract_present": False,
        "contract_fields": {},
        "contract_missing_fields": list(METRIC_IDENTITY_FIELDS),
        "contract_source": None,
    }


def select_primary_metric(records: Iterable[Mapping[str, Any]], contract: Mapping[str, Any]) -> dict[str, Any]:
    """Select exactly one canonical record by explicit identity."""

    fields = {key: _text(contract.get(key)) for key in METRIC_IDENTITY_FIELDS if _text(contract.get(key))}
    required_missing = [key for key in METRIC_IDENTITY_FIELDS if not _text(contract.get(key))]
    if not contract.get("contract_present") or required_missing:
        return {
            "status": "blocked_missing_primary_metric_contract",
            "record": None,
            "candidate_count": 0,
            "missing_contract_fields": required_missing,
        }
    candidates = []
    for record in records:
        if str(record.get("evidence_role") or "") in {"presentation_only", "secondary", "legacy"}:
            continue
        if not record.get("identity_complete"):
            continue
        if all(_text(record.get(key)) == value for key, value in fields.items()):
            candidates.append(dict(record))
    if len(candidates) == 1:
        return {"status": "passed", "record": candidates[0], "candidate_count": 1, "missing_contract_fields": []}
    return {
        "status": "blocked_missing_primary_metric" if not candidates else "blocked_ambiguous_primary_metric",
        "record": None,
        "candidate_count": len(candidates),
        "missing_contract_fields": [],
        "candidate_ids": [item.get("metric_record_id") for item in candidates],
    }


def build_metric_identity_report(
    records: Iterable[Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = [dict(item) for item in records]
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in normalized:
        groups[metric_identity_key(item)].append(item)
    conflicts = []
    for key, items in groups.items():
        values = items if len(items) < 2 else items[1:]
        for item in values:
            relation = compare_evidence(items[0], item, kind="metric")
            if relation["status"] == "same_identity_value_conflict":
                conflicts.append(relation)
    primary = select_primary_metric(normalized, contract)
    missing = [item for item in normalized if not item.get("identity_complete") and item.get("evidence_role") != "presentation_only"]
    strict = bool(contract.get("contract_present"))
    blocking = list(conflicts)
    if strict and primary.get("status") != "passed":
        blocking.append({"status": primary.get("status"), "detail": "PrimaryMetricContract did not resolve exactly one record."})
    if strict:
        blocking.extend({"status": "missing_required_identity", "metric_record_id": item.get("metric_record_id"), "missing": item.get("missing_identity_fields")} for item in missing)
    status = "blocked" if blocking else ("passed" if strict else "legacy_unqualified")
    return {
        "schema_version": "dpl.metric_identity_report.v1",
        "status": status,
        "strict": strict,
        "record_count": len(normalized),
        "identity_group_count": len(groups),
        "records": normalized,
        "primary_metric": primary,
        "conflicts": conflicts,
        "missing_identity_records": [item.get("metric_record_id") for item in missing],
        "blocking_reasons": blocking,
        "policy": "Identity is checked before values. Legacy compatibility records remain visible but cannot be promoted without an explicit primary metric contract.",
    }


def build_count_identity_report(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [dict(item) for item in records]
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in normalized:
        groups[count_identity_key(item)].append(item)
    conflicts = []
    for items in groups.values():
        for item in items[1:]:
            relation = compare_evidence(items[0], item, kind="count")
            if relation["status"] == "same_identity_value_conflict":
                conflicts.append(relation)
    missing = [item for item in normalized if not item.get("identity_complete")]
    return {
        "schema_version": "dpl.count_identity_report.v1",
        "status": "blocked" if conflicts else "legacy_unqualified" if missing else "passed",
        "record_count": len(normalized),
        "identity_group_count": len(groups),
        "records": normalized,
        "conflicts": conflicts,
        "missing_identity_records": [item.get("count_record_id") for item in missing],
        "blocking_reasons": conflicts,
        "policy": "Different denominator identities form sample-flow relations and are not equality conflicts.",
    }
