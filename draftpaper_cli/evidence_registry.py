# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project


EVIDENCE_REGISTRY_JSON = "writing/scientific_evidence_registry.json"
REQUIRED_BINDING_FIELDS = (
    "evidence_id", "run_id", "cohort_id", "sample_unit", "split", "model_id", "metric_dimension",
)


class EvidenceConflictError(RuntimeError):
    """Raised when manuscript evidence contains unresolved scientific conflicts."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_record(
    record: dict[str, Any],
    *,
    source_artifact: str,
    source_hash: str,
) -> dict[str, Any] | None:
    role = str(record.get("entity_role") or record.get("role") or "").strip()
    value = record.get("value")
    if not role or value is None or value == "":
        return None
    is_result_metric = role.startswith("result_metric_")
    cohort_id = str(record.get("cohort_id") or record.get("cohort") or "main").strip() or "main"
    run_id = str(record.get("run_id") or ("" if is_result_metric else "not_applicable")).strip()
    split = str(record.get("split") or ("" if is_result_metric else "not_applicable")).strip()
    model_id = str(record.get("model_id") or record.get("model") or ("" if is_result_metric else "not_applicable")).strip()
    metric_dimension = str(record.get("metric_dimension") or record.get("unit") or "").strip()
    normalized = {
        "evidence_id": str(record.get("evidence_id") or ""),
        "entity_role": role,
        "value": value,
        "unit": str(record.get("unit") or "").strip(),
        "cohort_id": cohort_id,
        "cohort": cohort_id,
        "sample_unit": str(record.get("sample_unit") or "").strip(),
        "split": split,
        "run_id": run_id,
        "model_id": model_id,
        "model": model_id,
        "metric_dimension": metric_dimension,
        "aggregation": str(record.get("aggregation") or "not_applicable").strip(),
        "analysis_variant": str(record.get("analysis_variant") or "primary").strip(),
        "source_artifact": source_artifact,
        "source_hash": source_hash,
        "confidence": str(record.get("confidence") or "verified").strip(),
        "target_sections": list(record.get("target_sections") or []),
        "claim_boundary": str(record.get("claim_boundary") or "").strip(),
        "figure_ids": [
            str(item) for item in record.get("figure_ids") or record.get("figure_groups") or [] if str(item)
        ],
        "formula_ids": [str(item) for item in record.get("formula_ids") or [] if str(item)],
        "citation_key": str(record.get("citation_key") or "").strip(),
        "citation_role": str(record.get("citation_role") or "").strip(),
        "allowed_interpretation": str(record.get("allowed_interpretation") or "").strip(),
    }
    missing = [field for field in REQUIRED_BINDING_FIELDS if not str(normalized.get(field) or "").strip()]
    normalized["binding_complete"] = not missing
    normalized["missing_binding_fields"] = missing
    return normalized


def _finalize_binding(record: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_BINDING_FIELDS if not str(record.get(field) or "").strip()]
    record["binding_complete"] = not missing
    record["missing_binding_fields"] = missing


def _record_key(record: dict[str, Any]) -> tuple[str, str, str, str, str, str, str, str, str]:
    return (
        str(record.get("entity_role") or ""),
        str(record.get("cohort_id") or record.get("cohort") or ""),
        str(record.get("sample_unit") or ""),
        str(record.get("split") or ""),
        str(record.get("run_id") or ""),
        str(record.get("model_id") or record.get("model") or ""),
        str(record.get("metric_dimension") or ""),
        str(record.get("aggregation") or ""),
        str(record.get("analysis_variant") or ""),
    )


def _value_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _class_balance_total(value: Any) -> float | None:
    if isinstance(value, dict):
        try:
            return float(sum(float(item) for item in value.values()))
        except (TypeError, ValueError):
            return None
    if isinstance(value, str) and ":" in value:
        try:
            return float(sum(float(item) for item in value.split(":")))
        except ValueError:
            return None
    return None


def _numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _conflicts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str, str, str, str, str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(_record_key(record), []).append(record)
    for key, items in grouped.items():
        values = {_value_key(item.get("value")) for item in items}
        if len(values) > 1:
            conflicts.append({
                "code": "conflicting_values_same_scope",
                "severity": "blocking",
                "scope": {
                    "entity_role": key[0],
                    "cohort": key[1],
                    "sample_unit": key[2],
                    "split": key[3],
                    "run_id": key[4],
                    "model": key[5],
                    "metric_dimension": key[6],
                    "aggregation": key[7],
                    "analysis_variant": key[8],
                },
                "values": [item.get("value") for item in items],
                "evidence_ids": [item.get("evidence_id") for item in items],
            })

    by_scope: dict[tuple[str, str, str, str, str], dict[str, list[dict[str, Any]]]] = {}
    for record in records:
        scope = (
            str(record.get("cohort_id") or record.get("cohort") or ""),
            str(record.get("sample_unit") or ""),
            str(record.get("split") or ""),
            str(record.get("run_id") or ""),
            str(record.get("analysis_variant") or "primary"),
        )
        by_scope.setdefault(scope, {}).setdefault(str(record.get("entity_role") or ""), []).append(record)
    for scope, roles in by_scope.items():
        for source_record in roles.get("source_count", []):
            source_count = _numeric(source_record.get("value"))
            if source_count is None:
                continue
            for balance_record in roles.get("class_balance", []):
                balance_total = _class_balance_total(balance_record.get("value"))
                if balance_total is not None and abs(source_count - balance_total) > 1e-9:
                    conflicts.append({
                        "code": "source_count_class_balance_mismatch",
                        "severity": "blocking",
                        "scope": {
                            "cohort": scope[0],
                            "sample_unit": scope[1],
                            "split": scope[2],
                            "run_id": scope[3],
                            "analysis_variant": scope[4],
                        },
                        "source_count": source_count,
                        "class_balance_total": balance_total,
                        "evidence_ids": [
                            source_record.get("evidence_id"),
                            balance_record.get("evidence_id"),
                        ],
                    })
    return conflicts


def _records_from_payload(path: Path, project_path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    records = payload.get("evidence_records") if isinstance(payload.get("evidence_records"), list) else []
    relative = path.relative_to(project_path).as_posix()
    source_hash = _sha256(path)
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        item = _normalize_record(record, source_artifact=relative, source_hash=source_hash)
        if item is None:
            continue
        if not item["evidence_id"]:
            scope = f"{item['entity_role']}|{item['cohort']}|{item['sample_unit']}|{item['split']}|{item['run_id']}|{item['model']}|{index}"
            item["evidence_id"] = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:16]
        _finalize_binding(item)
        normalized.append(item)
    return normalized


def _flatten_numeric_metrics(value: Any, prefix: str = "") -> list[tuple[str, float]]:
    if isinstance(value, dict):
        rows: list[tuple[str, float]] = []
        for key, child in value.items():
            name = f"{prefix}_{key}".strip("_")
            rows.extend(_flatten_numeric_metrics(child, name))
        return rows
    numeric = _numeric(value)
    return [(prefix, numeric)] if prefix and numeric is not None else []


def _records_from_result_manifest(path: Path, project_path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    relative = path.relative_to(project_path).as_posix()
    source_hash = _sha256(path)
    run_manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    resolved = _read_json(project_path / "results" / "resolved_result_evidence.json")
    primary = resolved.get("primary_metric") if isinstance(resolved.get("primary_metric"), dict) else {}
    current_run_id = str(run_manifest.get("run_id") or primary.get("run_id") or "")
    current_split = str(primary.get("split") or run_manifest.get("split") or "current_run")
    records: list[dict[str, Any]] = []
    figures = payload.get("figures") if isinstance(payload.get("figures"), list) else []
    for figure in figures:
        if not isinstance(figure, dict) or not isinstance(figure.get("metrics"), dict):
            continue
        figure_id = str(figure.get("storyboard_id") or figure.get("id") or figure.get("path") or "figure")
        figure_text = " ".join(
            str(figure.get(key) or "")
            for key in ("scientific_question", "caption_draft", "figure_group", "result_claim")
        ).lower()
        for metric, numeric in _flatten_numeric_metrics(figure["metrics"]):
            metric_name = str(metric).strip().lower()
            count_tokens = (
                "count", "number", "row", "sample", "cohort", "event", "source", "available",
                "valid", "excluded", "support", "dimension", "fold", "group",
            )
            unit = "count" if any(token in metric_name for token in count_tokens) or "_as_" in metric_name else "score"
            cohort_figure = any(token in figure_text for token in ("sample", "cohort", "coverage", "missingness", "availability"))
            data_count_tokens = (
                "sample", "cohort", "row", "event", "source", "available", "valid", "excluded",
                "support", "inventory", "dimension", "group",
            )
            data_sections = (
                ["results", "data", "discussion"]
                if unit == "count" and (cohort_figure or any(token in metric_name for token in data_count_tokens))
                else ["results", "discussion"]
            )
            record = _normalize_record(
                {
                    "entity_role": f"result_metric_{metric_name}",
                    "value": numeric,
                    "unit": unit,
                    "cohort": "main",
                    "sample_unit": "figure_evidence",
                    "run_id": str(figure.get("run_id") or current_run_id),
                    "split": str(figure.get("split") or figure.get("split_unit") or current_split),
                    "model_id": str(figure.get("model_id") or primary.get("model_id") or "not_applicable"),
                    "metric_dimension": unit,
                    "confidence": "figure_metadata_bound",
                    "target_sections": data_sections,
                    "figure_ids": [figure_id],
                    "allowed_interpretation": figure.get("result_claim") or figure.get("claim_boundary") or "",
                },
                source_artifact=relative,
                source_hash=source_hash,
            )
            if record:
                record["evidence_id"] = hashlib.sha256(
                    f"{figure_id}|{metric_name}|{numeric}|{source_hash}".encode("utf-8")
                ).hexdigest()[:16]
                _finalize_binding(record)
                records.append(record)
    return records


def build_scientific_evidence_registry(project: str | Path) -> dict[str, Any]:
    """Build a domain-neutral registry from explicitly structured evidence only."""
    state = load_project(project)
    records: list[dict[str, Any]] = []
    for relative in [
        "data/data_key_facts.json",
        "results/resolved_result_evidence.json",
        "methods/run_manifest.yaml",
    ]:
        path = state.path / relative
        if path.exists():
            records.extend(_records_from_payload(path, state.path))
    result_manifest = state.path / "results" / "result_manifest.yaml"
    if result_manifest.exists():
        records.extend(_records_from_result_manifest(result_manifest, state.path))
    resolved = _read_json(state.path / "results" / "resolved_result_evidence.json")
    primary = resolved.get("primary_metric") if isinstance(resolved.get("primary_metric"), dict) else {}
    conflicts = _conflicts(records)
    incomplete = [record for record in records if not record.get("binding_complete")]
    registry = {
        "status": "blocked" if conflicts else "ready",
        "schema_version": "v0.22.3",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "record_count": len(records),
        "records": records,
        "preferred_run_id": str(primary.get("run_id") or ""),
        "blocking_conflict_count": len(conflicts),
        "incomplete_binding_count": len(incomplete),
        "incomplete_binding_evidence_ids": [record.get("evidence_id") for record in incomplete],
        "conflicts": conflicts,
        "required_binding_fields": list(REQUIRED_BINDING_FIELDS),
        "policy": "Only structured evidence bound to evidence/run/cohort/unit/split/model/dimension may guide quantitative manuscript claims; free text is non-authoritative context.",
    }
    output = state.path / EVIDENCE_REGISTRY_JSON
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, registry)
    return registry


def ensure_registry_consistent(project: str | Path) -> dict[str, Any]:
    registry = build_scientific_evidence_registry(project)
    if registry.get("blocking_conflict_count"):
        codes = ", ".join(str(item.get("code") or "conflict") for item in registry.get("conflicts") or [])
        raise EvidenceConflictError(f"Scientific evidence conflicts must be resolved before manuscript writing: {codes}")
    return registry
