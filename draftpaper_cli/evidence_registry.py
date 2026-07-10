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
    return {
        "evidence_id": str(record.get("evidence_id") or ""),
        "entity_role": role,
        "value": value,
        "unit": str(record.get("unit") or "").strip(),
        "cohort": str(record.get("cohort") or "main").strip() or "main",
        "sample_unit": str(record.get("sample_unit") or "").strip(),
        "split": str(record.get("split") or "").strip(),
        "run_id": str(record.get("run_id") or "").strip(),
        "model": str(record.get("model") or "").strip(),
        "source_artifact": source_artifact,
        "source_hash": source_hash,
        "confidence": str(record.get("confidence") or "verified").strip(),
        "target_sections": list(record.get("target_sections") or []),
        "claim_boundary": str(record.get("claim_boundary") or "").strip(),
    }


def _record_key(record: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(record.get("entity_role") or ""),
        str(record.get("cohort") or ""),
        str(record.get("sample_unit") or ""),
        str(record.get("split") or ""),
        str(record.get("run_id") or ""),
        str(record.get("model") or ""),
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
    grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, Any]]] = {}
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
                },
                "values": [item.get("value") for item in items],
                "evidence_ids": [item.get("evidence_id") for item in items],
            })

    by_scope: dict[tuple[str, str, str, str], dict[str, list[dict[str, Any]]]] = {}
    for record in records:
        scope = (
            str(record.get("cohort") or ""),
            str(record.get("sample_unit") or ""),
            str(record.get("split") or ""),
            str(record.get("run_id") or ""),
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
        normalized.append(item)
    return normalized


def _records_from_result_manifest(path: Path, project_path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    relative = path.relative_to(project_path).as_posix()
    source_hash = _sha256(path)
    records: list[dict[str, Any]] = []
    figures = payload.get("figures") if isinstance(payload.get("figures"), list) else []
    for figure in figures:
        if not isinstance(figure, dict) or not isinstance(figure.get("metrics"), dict):
            continue
        figure_id = str(figure.get("storyboard_id") or figure.get("id") or figure.get("path") or "figure")
        for metric, value in figure["metrics"].items():
            numeric = _numeric(value)
            if numeric is None:
                continue
            metric_name = str(metric).strip().lower()
            unit = "count" if any(token in metric_name for token in ["count", "number", "row", "_n"]) else "score"
            record = _normalize_record(
                {
                    "entity_role": f"result_metric_{metric_name}",
                    "value": numeric,
                    "unit": unit,
                    "cohort": "main",
                    "sample_unit": "figure_evidence",
                    "model": figure_id,
                    "confidence": "figure_metadata",
                    "target_sections": ["results", "discussion"],
                },
                source_artifact=relative,
                source_hash=source_hash,
            )
            if record:
                record["evidence_id"] = hashlib.sha256(
                    f"{figure_id}|{metric_name}|{numeric}|{source_hash}".encode("utf-8")
                ).hexdigest()[:16]
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
    conflicts = _conflicts(records)
    registry = {
        "status": "blocked" if conflicts else "ready",
        "schema_version": "v0.17.3",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "record_count": len(records),
        "records": records,
        "blocking_conflict_count": len(conflicts),
        "conflicts": conflicts,
        "policy": "Only structured, scoped evidence may guide manuscript facts; free-text observations are context, not authoritative numeric evidence.",
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
