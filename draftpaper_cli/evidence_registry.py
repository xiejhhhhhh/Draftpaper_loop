# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .io_utils import read_json_object
from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .loop_contract import stable_evidence_id


EVIDENCE_REGISTRY_JSON = "writing/scientific_evidence_registry.json"
REQUIRED_BINDING_FIELDS = (
    "evidence_id", "estimand_id", "cohort_view_id", "analysis_spec_id", "run_id",
    "sample_unit", "split_id", "model_id", "metric_dimension", "aggregation",
)


class EvidenceConflictError(RuntimeError):
    """Raised when manuscript evidence contains unresolved scientific conflicts."""


def _read_json(path: Path) -> dict[str, Any]:
    return read_json_object(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity_value(value: Any, fallback: str = "") -> str:
    """Treat generated placeholder identities as missing when a real value exists."""
    text = str(value or "").strip()
    if text.lower() in {"not_yet_assigned", "unknown", "null", "none"}:
        return fallback
    return text


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
    split = _identity_value(record.get("split"), "" if is_result_metric else "not_applicable")
    model_id = str(record.get("model_id") or record.get("model") or ("" if is_result_metric else "not_applicable")).strip()
    metric_dimension = str(record.get("metric_dimension") or record.get("unit") or "").strip()
    normalized = {
        "evidence_id": str(record.get("evidence_id") or ""),
        "entity_role": role,
        "value": value,
        "evidence_role": str(record.get("evidence_role") or "primary").strip() or "primary",
        "unit": str(record.get("unit") or "").strip(),
        "cohort_id": cohort_id,
        "cohort": cohort_id,
        "cohort_view_id": str(record.get("cohort_view_id") or record.get("analysis_view_id") or ("" if is_result_metric else "not_applicable")).strip(),
        "estimand_id": str(record.get("estimand_id") or ("" if is_result_metric else "not_applicable")).strip(),
        "analysis_spec_id": str(record.get("analysis_spec_id") or ("" if is_result_metric else "not_applicable")).strip(),
        "sample_unit": str(record.get("sample_unit") or "").strip(),
        "split": split,
        "split_id": _identity_value(record.get("split_id"), split) or split,
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


def _record_key(record: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(record.get("entity_role") or ""),
        str(record.get("estimand_id") or ""),
        str(record.get("cohort_view_id") or ""),
        str(record.get("cohort_id") or record.get("cohort") or ""),
        str(record.get("analysis_spec_id") or record.get("analysis_variant") or ""),
        str(record.get("run_id") or ""),
        str(record.get("model_id") or record.get("model") or ""),
        str(record.get("split_id") or record.get("split") or ""),
        str(record.get("sample_unit") or ""),
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
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _conflicts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    # Presentation-only/secondary/legacy diagnostics remain visible in the
    # registry but cannot compete with identity-bound scientific evidence.
    scientific_records = [
        record for record in records
        if str(record.get("evidence_role") or "primary").strip().lower()
        not in {"presentation_only", "secondary", "legacy"}
    ]
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for record in scientific_records:
        grouped.setdefault(_record_key(record), []).append(record)
    for key, items in grouped.items():
        values = {_value_key(item.get("value")) for item in items}
        if len(values) > 1:
            conflicts.append({
                "code": "conflicting_values_same_scope",
                "severity": "blocking",
                "scope": {
                    "entity_role": key[0],
                    "estimand_id": key[1],
                    "cohort_view_id": key[2],
                    "cohort_id": key[3],
                    "analysis_spec_id": key[4],
                    "run_id": key[5],
                    "model": key[6],
                    "split_id": key[7],
                    "sample_unit": key[8],
                    "metric_dimension": key[9],
                    "aggregation": key[10],
                    "analysis_variant": key[11],
                },
                "values": [item.get("value") for item in items],
                "evidence_ids": [item.get("evidence_id") for item in items],
            })

    by_scope: dict[tuple[str, str, str, str, str], dict[str, list[dict[str, Any]]]] = {}
    for record in scientific_records:
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
            item["evidence_id"] = stable_evidence_id("structured_evidence", title=scope, sequence=index)
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
    if isinstance(value, list):
        rows: list[tuple[str, float]] = []
        for index, child in enumerate(value):
            name = f"{prefix}_{index}".strip("_")
            rows.extend(_flatten_numeric_metrics(child, name))
        return rows
    numeric = _numeric(value)
    return [(prefix, numeric)] if prefix and numeric is not None else []


def _figure_metric_unit(metric_name: str, numeric: float, *, cohort_figure: bool) -> str:
    """Classify flattened figure values without treating scope words as counts."""

    name = metric_name.lower().replace("/", "_")
    score_hints = (
        "macro_f1", "balanced_accuracy", "recall", "precision", "brier",
        "roc_auc", "average_precision", "p_value", "probability", "delta",
        "ci_lower", "ci_upper", "global_max", "global_min", "display_xlim",
        "display_ylim",
    )
    if any(hint in name for hint in score_hints):
        return "score"
    if any(hint in name for hint in ("fraction", "proportion", "percentage", "percent", "prevalence")):
        return "fraction"
    tokens = {token for token in name.split("_") if token}
    explicit_count = (
        "confusion_matrix" in name
        or name.endswith(("_count", "_counts", "_rows", "_draws"))
        or "_count_" in name
        or "_counts_" in name
        or bool(tokens.intersection({"count", "counts", "number", "rows", "draws", "folds"}))
    )
    if explicit_count:
        return "count"
    cohort_count_hint = bool(tokens.intersection({
        "sample", "cohort", "source", "event", "catalog", "image", "embedding",
        "available", "valid", "excluded", "inventory", "dimension",
    }))
    if cohort_figure and cohort_count_hint and float(numeric).is_integer():
        return "count"
    return "score"


def _figure_metric_target_sections(
    metric_name: str,
    numeric: float,
    *,
    unit: str,
    cohort_figure: bool,
) -> list[str]:
    """Route only sample, coverage, and denominator evidence into Data."""

    name = metric_name.lower().replace("/", "_")
    if cohort_figure and unit in {"count", "fraction"}:
        return ["results", "data", "discussion"]
    if float(numeric) <= 0 or any(token in name for token in ("confusion", "bootstrap", "outlier", "metric_row_count")):
        return ["results", "discussion"]
    denominator_hints = (
        "sample_count", "cohort_count", "source_count", "event_count",
        "event_counts_by_split", "split_counts", "physical_fit_event_count",
        "available_count", "availability_count", "available_fraction",
        "availability_fraction", "coverage", "inventory_count", "valid_count",
        "excluded_count", "support_count",
    )
    return (
        ["results", "data", "discussion"]
        if any(hint in name for hint in denominator_hints)
        else ["results", "discussion"]
    )


def _records_from_result_manifest(path: Path, project_path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    relative = path.relative_to(project_path).as_posix()
    source_hash = _sha256(path)
    run_manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    resolved = _read_json(project_path / "results" / "resolved_result_evidence.json")
    primary = resolved.get("primary_metric") if isinstance(resolved.get("primary_metric"), dict) else {}
    current_run_id = str(run_manifest.get("run_id") or primary.get("run_id") or "")
    current_split = str(primary.get("split") or run_manifest.get("split") or "current_run")
    analysis_payload = _read_json(project_path / "methods" / "executable_analysis_spec.json")
    analysis_specs = [item for item in analysis_payload.get("analysis_specs") or [] if isinstance(item, dict)]
    specs_by_figure = {
        str(figure_id): spec
        for spec in analysis_specs
        for figure_id in spec.get("figure_ids") or []
        if figure_id
    }
    default_spec = analysis_specs[0] if len(analysis_specs) == 1 else {}
    figure_contract_payload = _read_json(project_path / "results" / "figure_contracts.json")
    figure_contracts = [item for item in figure_contract_payload.get("contracts") or [] if isinstance(item, dict)]
    contracts_by_figure = {
        str(item.get("storyboard_id") or item.get("figure_id") or ""): item
        for item in figure_contracts
        if item.get("storyboard_id") or item.get("figure_id")
    }
    records: list[dict[str, Any]] = []
    figures = payload.get("figures") if isinstance(payload.get("figures"), list) else []
    for figure in figures:
        if not isinstance(figure, dict) or not isinstance(figure.get("metrics"), dict):
            continue
        figure_id = str(figure.get("storyboard_id") or figure.get("id") or figure.get("path") or "figure")
        analysis_spec = specs_by_figure.get(figure_id) or default_spec
        contract = contracts_by_figure.get(figure_id) or {}
        binding = {**contract, **analysis_spec}
        figure_text = " ".join(
            str(figure.get(key) or "")
            for key in ("scientific_question", "caption_draft", "figure_group", "result_claim")
        ).lower()
        for metric, numeric in _flatten_numeric_metrics(figure["metrics"]):
            metric_name = str(metric).strip().lower()
            analysis_variant = "primary"
            if "tile_grouped" in metric_name:
                analysis_variant = "tile_grouped_validation"
            elif "multi_seed" in metric_name:
                analysis_variant = "multi_seed_summary"
            elif "baseline" in metric_name:
                analysis_variant = "transparent_baseline_comparison"
            elif "calibration" in metric_name:
                analysis_variant = "calibration_audit"
            elif "external" in metric_name:
                analysis_variant = "external_transfer"
            elif "adjusted_association" in metric_name:
                analysis_variant = "adjusted_association"
            cohort_figure = any(token in figure_text for token in ("sample", "cohort", "coverage", "missingness", "availability"))
            unit = _figure_metric_unit(metric_name, numeric, cohort_figure=cohort_figure)
            data_sections = _figure_metric_target_sections(
                metric_name,
                numeric,
                unit=unit,
                cohort_figure=cohort_figure,
            )
            record = _normalize_record(
                {
                    "entity_role": f"result_metric_{metric_name}",
                    "value": numeric,
                    "unit": unit,
                    "cohort": "main",
                    "cohort_view_id": figure.get("cohort_view_id") or binding.get("cohort_view_id"),
                    "estimand_id": figure.get("estimand_id") or binding.get("estimand_id"),
                    "analysis_spec_id": figure.get("analysis_spec_id") or binding.get("analysis_spec_id"),
                    "sample_unit": "figure_evidence",
                    "run_id": str(figure.get("run_id") or current_run_id),
                    "split": str(figure.get("split") or figure.get("split_unit") or current_split),
                    "split_id": str(figure.get("split_id") or binding.get("split_id") or current_split),
                    "model_id": str(figure.get("model_id") or primary.get("model_id") or "not_applicable"),
                    "metric_dimension": unit,
                    "confidence": "figure_metadata_bound",
                    "analysis_variant": analysis_variant,
                    "target_sections": data_sections,
                    "figure_ids": [figure_id],
                    "allowed_interpretation": figure.get("result_claim") or figure.get("claim_boundary") or "",
                },
                source_artifact=relative,
                source_hash=source_hash,
            )
            if record:
                record["evidence_id"] = stable_evidence_id(
                    "result_metric",
                    title=f"{figure_id}|{metric_name}|{numeric}|{source_hash}",
                    sequence=len(records) + 1,
                )
                _finalize_binding(record)
                records.append(record)
    return records


def _figure_table_path(project_path: Path, reference: Any) -> Path | None:
    """Resolve a figure-declared compact table without leaving results/tables."""
    relative = str(reference or "").strip().replace("\\", "/").removeprefix("./")
    if not relative:
        return None
    if not relative.startswith("results/tables/"):
        if "/" in relative:
            return None
        relative = f"results/tables/{relative}"
    table_path = (project_path / relative).resolve()
    tables_root = (project_path / "results" / "tables").resolve()
    try:
        table_path.relative_to(tables_root)
    except ValueError:
        return None
    if table_path.suffix.lower() not in {".csv", ".tsv"} or not table_path.is_file():
        return None
    return table_path


def _records_from_figure_bound_tables(project_path: Path) -> list[dict[str, Any]]:
    """Register compact tables explicitly declared by generated figure metadata.

    The registry stores the table hash with each cell. A content-addressed
    ``table:<path>:<hash-prefix>`` evidence identifier is verified when present;
    plain ``source_tables`` references remain supported for existing projects.
    """
    metadata = _read_json(project_path / "results" / "figure_metadata.json")
    figures = [item for item in metadata.get("figures") or [] if isinstance(item, dict)]
    if not figures:
        return []

    run_manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    resolved = _read_json(project_path / "results" / "resolved_result_evidence.json")
    primary = resolved.get("primary_metric") if isinstance(resolved.get("primary_metric"), dict) else {}
    current_run_id = str(run_manifest.get("run_id") or primary.get("run_id") or "")
    current_split = str(primary.get("split") or run_manifest.get("split") or "current_run")
    analysis_payload = _read_json(project_path / "methods" / "executable_analysis_spec.json")
    analysis_specs = [item for item in analysis_payload.get("analysis_specs") or [] if isinstance(item, dict)]
    specs_by_figure = {
        str(figure_id): spec
        for spec in analysis_specs
        for figure_id in spec.get("figure_ids") or []
        if figure_id
    }
    default_spec = analysis_specs[0] if len(analysis_specs) == 1 else {}
    figure_contract_payload = _read_json(project_path / "results" / "figure_contracts.json")
    figure_contracts = [item for item in figure_contract_payload.get("contracts") or [] if isinstance(item, dict)]
    contracts_by_figure = {
        str(item.get("storyboard_id") or item.get("figure_id") or ""): item
        for item in figure_contracts
        if item.get("storyboard_id") or item.get("figure_id")
    }

    records: list[dict[str, Any]] = []
    count_terms = {"count", "iterations", "pair_count", "source_count", "fold_seed_count", "epoch_count"}
    aggregation_names = (
        "mean", "median", "sd", "q025", "q975", "ci_low", "ci_high",
        "observed", "fraction", "threshold",
    )
    for figure in figures:
        figure_id = str(figure.get("figure_id") or figure.get("storyboard_id") or figure.get("id") or "figure")
        analysis_spec = specs_by_figure.get(figure_id) or default_spec
        contract = contracts_by_figure.get(figure_id) or {}
        binding = {**contract, **analysis_spec}
        table_references: dict[Path, str] = {}
        source_table_hashes = figure.get("source_table_hashes")
        source_table_hashes = source_table_hashes if isinstance(source_table_hashes, dict) else {}

        for source_table in figure.get("source_tables") or []:
            table_path = _figure_table_path(project_path, source_table)
            if table_path is None:
                continue
            relative = table_path.relative_to(project_path).as_posix()
            expected_hash = str(
                source_table_hashes.get(str(source_table))
                or source_table_hashes.get(relative)
                or ""
            ).removeprefix("sha256:")
            table_references.setdefault(table_path, expected_hash)

        for evidence_id in figure.get("evidence_ids") or []:
            match = re.fullmatch(r"table:(.+):([0-9a-fA-F]{8,64})", str(evidence_id).strip())
            if not match:
                continue
            table_path = _figure_table_path(project_path, match.group(1))
            if table_path is not None:
                table_references[table_path] = match.group(2).lower()

        figure_text = " ".join(
            str(figure.get(key) or "")
            for key in ("scientific_question", "caption_draft", "figure_group", "result_claim", "interpretation")
        ).lower()
        cohort_figure = any(token in figure_text for token in ("sample", "cohort", "coverage", "missingness", "availability"))
        for table_path, expected_hash_prefix in table_references.items():
            source_hash = _sha256(table_path)
            if expected_hash_prefix and not source_hash.startswith(expected_hash_prefix):
                continue
            try:
                with table_path.open("r", encoding="utf-8-sig", newline="") as handle:
                    delimiter = "\t" if table_path.suffix.lower() == ".tsv" else ","
                    rows = list(csv.DictReader(handle, delimiter=delimiter))
            except (OSError, UnicodeDecodeError, csv.Error):
                continue
            # Per-object tables can contain millions of values and are not
            # manuscript scalar evidence. Aggregate tables stay small enough to
            # register cell-by-cell for traceability.
            if len(rows) > 500 or (rows and "source_id" in rows[0]):
                continue
            relative = table_path.relative_to(project_path).as_posix()
            figure_analysis_spec = str(
                figure.get("analysis_spec_id") or binding.get("analysis_spec_id") or ""
            ).strip()
            if figure_analysis_spec:
                figure_analysis_spec = f"{figure_analysis_spec}|table:{relative}"
            for row_index, row in enumerate(rows, start=1):
                identity_columns = (
                    "model", "time_encoding", "metric", "finding", "comparison", "coverage_variable",
                    "quality_tier", "category", "comparison_model", "baseline_model",
                )
                identity_parts = [
                    str(row.get(column) or "").strip()
                    for column in identity_columns
                    if str(row.get(column) or "").strip()
                ]
                model_id = " | ".join(dict.fromkeys(identity_parts)) or str(
                    figure.get("model_id") or primary.get("model_id") or "not_applicable"
                )
                cohort_id = str(
                    row.get("cohort_id") or row.get("cohort") or figure.get("cohort_id")
                    or figure.get("cohort") or binding.get("cohort_id") or binding.get("cohort") or "main"
                ).strip() or "main"
                for column, raw_value in row.items():
                    numeric = _numeric(raw_value)
                    if numeric is None:
                        continue
                    normalized_column = re.sub(r"[^a-z0-9]+", "_", str(column).lower()).strip("_")
                    if not normalized_column:
                        continue
                    unit = "count" if any(term in normalized_column for term in count_terms) else "score"
                    aggregation = next(
                        (name for name in aggregation_names if name in normalized_column),
                        "reported_scalar",
                    )
                    record = _normalize_record(
                        {
                            "entity_role": f"result_metric_{normalized_column}",
                            "value": numeric,
                            "unit": unit,
                            "cohort": cohort_id,
                            "cohort_view_id": figure.get("cohort_view_id") or binding.get("cohort_view_id"),
                            "estimand_id": figure.get("estimand_id") or binding.get("estimand_id"),
                            "analysis_spec_id": figure_analysis_spec,
                            "sample_unit": figure.get("sample_unit") or "figure_evidence",
                            "run_id": str(figure.get("run_id") or current_run_id),
                            "split": str(figure.get("split") or figure.get("split_unit") or current_split),
                            "split_id": str(figure.get("split_id") or binding.get("split_id") or current_split),
                            "model_id": model_id,
                            "metric_dimension": unit,
                            "aggregation": aggregation,
                            "analysis_variant": "figure_bound_table",
                            "confidence": "figure_metadata_bound",
                            "target_sections": _figure_metric_target_sections(
                                normalized_column,
                                numeric,
                                unit=unit,
                                cohort_figure=cohort_figure,
                            ),
                            "figure_ids": [figure_id],
                            "allowed_interpretation": figure.get("result_claim") or figure.get("claim_boundary") or "",
                        },
                        source_artifact=relative,
                        source_hash=source_hash,
                    )
                    if record:
                        record["evidence_id"] = stable_evidence_id(
                            "figure_table_cell",
                            title=f"{figure_id}|{relative}|{row_index}|{normalized_column}|{raw_value}|{source_hash}",
                            sequence=len(records) + 1,
                        )
                        _finalize_binding(record)
                        # The registry is canonical scientific evidence, not
                        # a generic table index. A figure may declare a
                        # supporting table before its estimand/cohort/split
                        # binding exists; keep that table in the audit surface
                        # but do not promote its numeric cells into the
                        # scientific registry yet.
                        if record["binding_complete"]:
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
    records.extend(_records_from_figure_bound_tables(state.path))
    resolved = _read_json(state.path / "results" / "resolved_result_evidence.json")
    primary = resolved.get("primary_metric") if isinstance(resolved.get("primary_metric"), dict) else {}
    typed_metric_report = _read_json(state.path / "results" / "metric_identity_report.json")
    typed_count_report = _read_json(state.path / "results" / "count_identity_report.json")
    active_bundle = _read_json(state.path / "results" / "active_run_evidence_bundle.json")
    if not typed_metric_report and isinstance(resolved.get("metric_identity_report"), dict):
        typed_metric_report = dict(resolved["metric_identity_report"])
    if not typed_count_report and isinstance(resolved.get("count_identity_report"), dict):
        typed_count_report = dict(resolved["count_identity_report"])
    conflicts = _conflicts(records)
    incomplete = [record for record in records if not record.get("binding_complete")]
    typed_metric_records = [
        item for item in typed_metric_report.get("records") or []
        if isinstance(item, dict)
    ]
    typed_count_records = [
        item for item in typed_count_report.get("records") or []
        if isinstance(item, dict)
    ]
    typed_statuses = [
        str(typed_metric_report.get("status") or "missing"),
        str(typed_count_report.get("status") or "missing"),
    ]
    typed_blocking = [
        status for status in typed_statuses
        if status in {"blocked", "blocked_missing_primary_metric", "blocked_ambiguous_primary_metric"}
    ]
    registry = {
        "status": "blocked" if conflicts or typed_blocking else "ready",
        "schema_version": "dpl.scientific_evidence_registry.v2",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "record_count": len(records),
        "figure_table_binding_count": sum(
            1 for record in records if record.get("analysis_variant") == "figure_bound_table"
        ),
        "records": records,
        "preferred_run_id": str(primary.get("run_id") or ""),
        "preferred_model_id": str(primary.get("model_id") or primary.get("model") or ""),
        "blocking_conflict_count": len(conflicts),
        "incomplete_binding_count": len(incomplete),
        "incomplete_binding_evidence_ids": [record.get("evidence_id") for record in incomplete],
        "conflicts": conflicts,
        "typed_evidence": {
            "metric_identity_report": typed_metric_report,
            "count_identity_report": typed_count_report,
            "active_run_bundle_pointer": active_bundle,
            "metric_record_count": len(typed_metric_records),
            "count_record_count": len(typed_count_records),
            "metric_status": str(typed_metric_report.get("status") or "missing"),
            "count_status": str(typed_count_report.get("status") or "missing"),
            "active_bundle_status": "active" if active_bundle.get("status") == "active" else "missing_or_stale",
            "policy": "Typed identity reports are the canonical quantitative bridge; legacy records remain visible for manuscript coverage but cannot override them.",
        },
        "typed_blocking_statuses": typed_blocking,
        "required_binding_fields": list(REQUIRED_BINDING_FIELDS),
        "semantic_key": ["estimand_id", "cohort_view_id", "cohort_id", "analysis_spec_id", "run_id", "model_id", "split_id", "aggregation", "metric_dimension"],
        "policy": "Only structured evidence bound to estimand/cohort-view/cohort/analysis-spec/run/model/split/aggregation/dimension may guide quantitative manuscript claims; numeric value and free text are not identity keys.",
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
