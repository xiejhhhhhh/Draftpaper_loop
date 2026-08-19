# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .run_evidence_bundle import build_run_evidence_bundle, publish_run_evidence_bundle
from .evidence_identity import (
    build_count_identity_report,
    build_metric_identity_report,
    load_primary_metric_contract,
    normalize_count_evidence,
    normalize_metric_evidence,
)


RESOLVED_RESULT_EVIDENCE_JSON = "results/resolved_result_evidence.json"
METRIC_PREFERENCE = ["f1_macro", "macro_f1", "f1", "roc_auc", "auc", "balanced_accuracy", "accuracy"]
NON_METRIC_COLUMNS = {
    "model",
    "model_name",
    "model_id",
    "split",
    "split_type",
    "fold",
    "fold_id",
    "note",
    "feature_group",
    "variant",
    "class",
    "label",
    "n",
    "n_train",
    "n_test",
    "row_count",
    "sample_size",
    "sample_count",
    "run_id",
    "metric_dimension",
    "cohort",
    "cohort_id",
    "sample_unit",
    "targetid",
    "target_id",
    "source_id",
    "object_id",
    "group_id",
    "candidate_rank",
    "count",
    "predicted_label",
    "true_label",
    "is_candidate",
}

METRIC_COLUMN_MARKERS = (
    "f1",
    "auc",
    "accuracy",
    "precision",
    "recall",
    "specificity",
    "sensitivity",
    "r2",
    "rmse",
    "mae",
    "mse",
    "loss",
    "p_value",
    "correlation",
    "effect_size",
    "balanced_accuracy",
    "stability",
)


class ResultEvidenceError(RuntimeError):
    """Raised when verified method outputs cannot provide result evidence."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_project_path(project_path: Path, relative: str) -> Path | None:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError:
        return None
    return candidate


def _numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _analysis_variant(relative: str) -> str:
    """Infer a conservative analysis layer from an auditable result filename."""
    stem = Path(relative).stem.lower()
    if "multi_seed" in stem or "multiseed" in stem:
        return "multi_seed_summary"
    if "tile_grouped" in stem or "tile-grouped" in stem:
        return "tile_grouped_validation"
    if "transparent" in stem and "baseline" in stem:
        return "transparent_baseline_comparison"
    if "external_transfer" in stem or "external-transfer" in stem:
        return "external_transfer"
    if "calibration" in stem:
        return "calibration_audit"
    if "quality_filtered" in stem or "quality-filtered" in stem:
        return "quality_filtered_sensitivity"
    if "repeated_group_partition" in stem or "repeated-group-partition" in stem:
        return "repeated_partition_sensitivity"
    if any(token in stem for token in ("sensitivity", "robustness", "stress_test", "stress-test")):
        return "sensitivity_analysis"
    if "ablation" in stem:
        return "ablation"
    if "model_metrics_by_fold" in stem or "pooled_out_of_fold" in stem:
        return "primary_fixed_partition"
    return "primary"


def _aggregation_scope(relative: str, *, value_count: int, fallback: str) -> str:
    """Identify the estimand represented by a metric table, independent of its values."""
    stem = Path(relative).stem.lower()
    if "repeated_group_partition" in stem or "repeated-group-partition" in stem:
        return "mean_across_repeated_group_partitions"
    if "pooled_out_of_fold" in stem or "pooled-out-of-fold" in stem:
        return "pooled_out_of_fold"
    if "model_metrics_by_fold" in stem or "model-metrics-by-fold" in stem:
        return "mean_across_primary_folds"
    return "mean_across_folds" if value_count > 1 else fallback


def _metric_rows_from_csv(path: Path, relative: str, run_id: str) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return []
    columns = [str(column or "").strip() for column in rows[0].keys()]
    source_hash = _source_hash(path)
    analysis_variant = _analysis_variant(relative)
    model_column = next((item for item in ["model_id", "model", "model_name", "model_variant", "variant"] if item in columns), "")
    split_column = next((item for item in ["split_id", "split", "split_type"] if item in columns), "")
    validation_column = next(
        (item for item in ["validation_design_id", "validation_design", "evaluation_design", "holdout_scheme", "split_strategy"] if item in columns),
        "",
    )
    fold_column = next((item for item in ["fold", "fold_id"] if item in columns), "")
    seed_column = next((item for item in ["seed", "random_seed"] if item in columns), "")
    repeat_column = next((item for item in ["repeat", "repetition", "repeated_split_id"] if item in columns), "")
    cohort_column = next((item for item in ["cohort_id", "cohort"] if item in columns), "")
    cohort_view_column = next((item for item in ["cohort_view_id", "analysis_view_id"] if item in columns), "")
    estimand_column = "estimand_id" if "estimand_id" in columns else ""
    analysis_spec_column = "analysis_spec_id" if "analysis_spec_id" in columns else ""
    sample_unit_column = "sample_unit" if "sample_unit" in columns else ""
    task_column = next((item for item in ["task_id", "task", "target_id", "target"] if item in columns), "")
    aggregation_contract_column = next((item for item in ["aggregation_contract_id", "aggregation_id"] if item in columns), "")
    aggregation_id_column = next((item for item in ["aggregation_id", "aggregation", "reducer", "aggregation_method"] if item in columns), "")
    uncertainty_column = next((item for item in ["uncertainty_definition_id", "uncertainty_definition"] if item in columns), "")
    evidence_role_column = "evidence_role" if "evidence_role" in columns else ""
    reducer_column = next((item for item in ["reducer", "aggregation", "aggregation_method"] if item in columns), "")
    records: list[dict[str, Any]] = []
    metric_value_column = next(
        (item for item in ["value", "mean", "score", "metric_value"] if item in columns),
        "",
    )
    if "metric" in columns and metric_value_column:
        for row in rows:
            value = _numeric(row.get(metric_value_column))
            metric_name = str(row.get("metric") or "").strip().lower()
            if metric_name and value is not None:
                records.append({
                    "metric_name": metric_name,
                    "value": value,
                    "model": str(row.get(model_column) or "").strip() if model_column else "",
                    "split": str(row.get(split_column) or "").strip() if split_column else "",
                    "validation_design": str(row.get(validation_column) or "").strip() if validation_column else "",
                    "fold": str(row.get(fold_column) or "").strip() if fold_column else "",
                    "seed": str(row.get(seed_column) or "").strip() if seed_column else "",
                    "repetition": str(row.get(repeat_column) or "").strip() if repeat_column else "",
                    "aggregation": str(row.get(aggregation_id_column) or "").strip() if aggregation_id_column else "",
                    "aggregation_contract_id": str(row.get(aggregation_contract_column) or "").strip() if aggregation_contract_column else "",
                    "uncertainty_definition_id": str(row.get(uncertainty_column) or "").strip() if uncertainty_column else "",
                    "evidence_role": str(row.get(evidence_role_column) or "").strip() if evidence_role_column else "",
                    "reducer": str(row.get(reducer_column) or "").strip() if reducer_column else "",
                    "analysis_variant": analysis_variant,
                    "run_id": str(row.get("run_id") or run_id).strip(),
                    "cohort_id": str(row.get(cohort_column) or "").strip() if cohort_column else "",
                    "cohort_view_id": str(row.get(cohort_view_column) or "").strip() if cohort_view_column else "",
                    "estimand_id": str(row.get(estimand_column) or "").strip() if estimand_column else "",
                    "analysis_spec_id": str(row.get(analysis_spec_column) or "").strip() if analysis_spec_column else "",
                    "sample_unit": str(row.get(sample_unit_column) or "").strip() if sample_unit_column else "",
                    "task_id": str(row.get(task_column) or "").strip() if task_column else "",
                    "sample_count": _numeric(row.get("sample_count")),
                    "metric_dimension": str(row.get("metric_dimension") or "score").strip(),
                    "source_artifact": relative,
                    "source_hash": source_hash,
                    "priority": 100 if model_column else 10,
                })
        return records
    for row in rows:
        for column in columns:
            metric_name = column.strip().lower()
            if metric_name in NON_METRIC_COLUMNS:
                continue
            if not any(marker in metric_name for marker in METRIC_COLUMN_MARKERS):
                continue
            value = _numeric(row.get(column))
            if value is None:
                continue
            records.append({
                "metric_name": metric_name,
                "value": value,
                "model": str(row.get(model_column) or "").strip() if model_column else "",
                "split": str(row.get(split_column) or "").strip() if split_column else "",
                "validation_design": str(row.get(validation_column) or "").strip() if validation_column else "",
                "fold": str(row.get(fold_column) or "").strip() if fold_column else "",
                "seed": str(row.get(seed_column) or "").strip() if seed_column else "",
                "repetition": str(row.get(repeat_column) or "").strip() if repeat_column else "",
                "aggregation": str(row.get(aggregation_id_column) or "").strip() if aggregation_id_column else "",
                "aggregation_contract_id": str(row.get(aggregation_contract_column) or "").strip() if aggregation_contract_column else "",
                "uncertainty_definition_id": str(row.get(uncertainty_column) or "").strip() if uncertainty_column else "",
                "evidence_role": str(row.get(evidence_role_column) or "").strip() if evidence_role_column else "",
                "reducer": str(row.get(reducer_column) or "").strip() if reducer_column else "",
                "analysis_variant": analysis_variant,
                "run_id": run_id,
                "cohort_id": str(row.get(cohort_column) or "").strip() if cohort_column else "",
                "cohort_view_id": str(row.get(cohort_view_column) or "").strip() if cohort_view_column else "",
                "estimand_id": str(row.get(estimand_column) or "").strip() if estimand_column else "",
                "analysis_spec_id": str(row.get(analysis_spec_column) or "").strip() if analysis_spec_column else "",
                "sample_unit": str(row.get(sample_unit_column) or "").strip() if sample_unit_column else "",
                "task_id": str(row.get(task_column) or "").strip() if task_column else "",
                "source_artifact": relative,
                "source_hash": source_hash,
                "priority": 100 if model_column else 40,
            })
    return records


def _aggregate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(
            str(record.get("metric_name") or ""),
            str(record.get("model") or ""),
            str(record.get("split") or ""),
            str(record.get("run_id") or ""),
            str(record.get("source_artifact") or ""),
            str(record.get("cohort_id") or ""),
            str(record.get("sample_unit") or ""),
        )].append(record)
    aggregated: list[dict[str, Any]] = []
    for (metric_name, model, split, run_id, source_artifact, cohort_id, sample_unit), items in grouped.items():
        values = [float(item["value"]) for item in items]
        item = dict(items[0])
        item["value"] = mean(values)
        explicit_aggregation = str(item.get("aggregation") or "").strip()
        item["aggregation"] = explicit_aggregation or _aggregation_scope(
            source_artifact,
            value_count=len(values),
            fallback="reported_value",
        )
        item["fold_count"] = len(values)
        item["metric_name"] = metric_name
        item["model"] = model
        item["split"] = split
        item["run_id"] = run_id
        item["source_artifact"] = source_artifact
        item["cohort_id"] = cohort_id
        item["sample_unit"] = sample_unit
        item["replicate_axis"] = "fold" if any(str(value.get("fold") or "").strip() for value in items) else "none"
        item["replicate_ids"] = [
            str(value.get("fold") or value.get("seed") or value.get("repetition") or "")
            for value in items
            if str(value.get("fold") or value.get("seed") or value.get("repetition") or "").strip()
        ]
        item["aggregation_contract_id"] = str(item.get("aggregation_contract_id") or "")
        item["uncertainty_definition_id"] = str(item.get("uncertainty_definition_id") or "")
        item["evidence_role"] = str(item.get("evidence_role") or "")
        item["aggregation_inferred"] = len(values) > 1 and not item["aggregation_contract_id"]
        item.pop("fold", None)
        aggregated.append(item)
    return aggregated


def _metric_rank(record: dict[str, Any]) -> tuple[int, int, int, float]:
    name = str(record.get("metric_name") or "")
    try:
        preference = len(METRIC_PREFERENCE) - METRIC_PREFERENCE.index(name)
    except ValueError:
        preference = 0
    primary_variant = 1 if str(record.get("analysis_variant") or "primary") in {
        "primary", "primary_fixed_partition",
    } else 0
    return int(record.get("priority") or 0), primary_variant, preference, float(record.get("value") or 0.0)


def _metric_family(value: Any) -> str:
    name = str(value or "").strip().lower()
    if name in {"f1", "f1_macro", "macro_f1"}:
        return "f1"
    if name in {"auc", "roc_auc"}:
        return "auc"
    return name


def _select_primary_metric(
    records: list[dict[str, Any]],
    *,
    configured_metric: str,
    configured_model: str,
    bound_sources: list[str],
) -> tuple[dict[str, Any], str]:
    metric_candidates = [
        item for item in records
        if not configured_metric or _metric_family(item.get("metric_name")) == _metric_family(configured_metric)
    ]
    if configured_model:
        exact = [item for item in metric_candidates if str(item.get("model") or "") == configured_model]
        if exact:
            return max(exact, key=_metric_rank), "configured_model_id"
    directly_bound_models = [
        item for item in metric_candidates
        if str(item.get("model") or "").strip() and item.get("source_artifact") in bound_sources
    ]
    non_ablation_models = []
    for item in directly_bound_models:
        model = str(item.get("model") or "").lower()
        tokens = {token for token in model.replace("-", "_").split("_") if token}
        if not tokens & {"ablation", "without", "no", "sensitivity"}:
            non_ablation_models.append(item)
    proposed = []
    for item in non_ablation_models or directly_bound_models or metric_candidates:
        model = str(item.get("model") or "").lower()
        tokens = {token for token in model.replace("-", "_").split("_") if token}
        if tokens & {"full", "main", "primary", "proposed"} and not tokens & {"baseline", "without", "no"}:
            proposed.append(item)
    if proposed:
        return max(proposed, key=_metric_rank), "inferred_full_or_proposed_model"
    if non_ablation_models:
        return max(non_ablation_models, key=_metric_rank), "highest_ranked_non_ablation_run_bound_model"
    if directly_bound_models:
        return max(directly_bound_models, key=_metric_rank), "highest_ranked_run_bound_model"
    summaries = [
        item for item in metric_candidates
        if not str(item.get("model") or "").strip() and item.get("source_artifact") in bound_sources
    ]
    if summaries:
        return max(summaries, key=_metric_rank), "run_bound_summary"
    if metric_candidates:
        return max(metric_candidates, key=_metric_rank), "highest_ranked_verified_model"
    return {}, "no_primary_metric"


def _matches_anchor(value: float, anchors: list[float]) -> bool:
    return any(abs(value - anchor) <= max(1e-8, abs(anchor) * 5e-4) for anchor in anchors)


def _legacy_primary_metric_record(record: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    """Expose the strict contract-selected metric through the legacy report shape."""

    identity = record.get("identity") if isinstance(record.get("identity"), dict) else record
    return {
        "metric_name": record.get("metric_definition_id") or identity.get("metric_definition_id"),
        "value": record.get("value"),
        "model": record.get("model_id") or identity.get("model_id"),
        "split": record.get("split_id") or identity.get("split_id"),
        "validation_design": record.get("validation_design_id") or identity.get("validation_design_id"),
        "fold": "",
        "seed": "",
        "repetition": "",
        "aggregation": record.get("aggregation_id") or identity.get("aggregation_id") or "none",
        "aggregation_contract_id": record.get("aggregation_contract_id") or "",
        "uncertainty_definition_id": record.get("uncertainty_definition_id") or identity.get("uncertainty_definition_id") or "none",
        "evidence_role": record.get("evidence_role") or "primary",
        "reducer": "",
        "analysis_variant": "primary",
        "run_id": run_id,
        "cohort_id": record.get("cohort_id") or identity.get("cohort_id"),
        "sample_unit": record.get("sample_unit") or identity.get("sample_unit"),
        "task_id": record.get("task_id") or identity.get("task_id"),
        "metric_dimension": "score",
        "source_artifact": record.get("source_artifact") or "",
        "source_hash": record.get("source_sha256") or "",
        "priority": 200,
        "replicate_axis": record.get("replicate_axis") or "none",
        "replicate_ids": record.get("replicate_ids") or [],
        "aggregation_inferred": bool(record.get("aggregation_inferred")),
    }


def _anchor_verified_metric_tables(
    project_path: Path,
    *,
    run_id: str,
    bound_sources: list[str],
    bound_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Bind legacy detailed tables only when they reproduce a run-bound summary value."""
    anchors = [float(item["value"]) for item in bound_records if _numeric(item.get("value")) is not None]
    if not anchors:
        return [], []
    tables_root = project_path / "results" / "tables"
    verified_records: list[dict[str, Any]] = []
    verified_sources: list[str] = []
    already_bound = set(bound_sources)
    for path in sorted(tables_root.rglob("*.csv")) if tables_root.exists() else []:
        relative = path.relative_to(project_path).as_posix()
        # Reviewer-only sensitivity tables can use a different cohort and
        # validation identity from the active scientific run.  They remain
        # available as supplementary evidence, but must not be promoted to
        # legacy anchors for the primary run merely because their filenames
        # contain "metric".
        if relative.startswith("results/tables/reviewer_revision/"):
            continue
        if relative in already_bound or "metric" not in path.stem.lower():
            continue
        candidate = _aggregate(_metric_rows_from_csv(path, relative, run_id))
        model_records = [item for item in candidate if str(item.get("model") or "").strip()]
        if not model_records:
            continue
        if not any(_matches_anchor(float(item["value"]), anchors) for item in model_records):
            continue
        for item in candidate:
            item["binding"] = "summary_anchor_verified"
            item["priority"] = max(80, int(item.get("priority") or 0))
        verified_records.extend(candidate)
        verified_sources.append(relative)
    return verified_records, verified_sources


def _count_records_from_payload(
    payload: dict[str, Any],
    *,
    source_artifact: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Read explicitly typed counts and retain legacy scalar counts as unqualified."""

    records: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    for key in ("count_evidence", "count_records", "sample_flow", "counts"):
        value = payload.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            for name, child in value.items():
                if isinstance(child, dict):
                    entries.append({"count_definition_id": name, **child})
                else:
                    entries.append({"count_definition_id": name, "value": child})
    legacy_map = {
        "source_rows": ("catalog_row_count", "row", "rows"),
        "train_sources": ("train_entity_count", "entity", "split_members"),
        "test_sources": ("test_entity_count", "entity", "split_members"),
        "sample_count": ("model_sample_count", "entity", "rows"),
    }
    for key, (definition, entity_type, count_mode) in legacy_map.items():
        if key in payload and not any(str(item.get("count_definition_id") or item.get("count_definition") or "") == definition for item in entries):
            entries.append({
                "count_definition_id": definition,
                "entity_type": entity_type,
                "count_mode": count_mode,
                "value": payload.get(key),
                "evidence_role": "presentation_only",
            })
    for index, entry in enumerate(entries, start=1):
        value = entry.get("value") if "value" in entry else entry.get("count")
        if value is None or value == "":
            continue
        records.append(
            normalize_count_evidence(
                entry,
                context=context,
                source_artifact=source_artifact,
                row_index=index,
            )
        )
    return records


def resolve_result_evidence(project: str | Path) -> dict[str, Any]:
    """Resolve quantitative evidence only from outputs bound to a successful run."""
    state = load_project(project)
    run_manifest = _read_json(state.path / "methods" / "run_manifest.yaml")
    if str(run_manifest.get("status") or "").lower() != "success":
        raise ResultEvidenceError("A successful methods/run_manifest.yaml is required to resolve result evidence.")
    run_id = str(run_manifest.get("run_id") or run_manifest.get("execution_id") or "").strip()
    if not run_id:
        seed = json.dumps(
            {
                "command": run_manifest.get("command_argv") or run_manifest.get("command"),
                "outputs": run_manifest.get("output_files") or run_manifest.get("declared_outputs"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        run_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    outputs = list(
        dict.fromkeys(
            str(item).replace("\\", "/")
            for key in ["output_files", "declared_outputs", "tables_generated"]
            for item in (run_manifest.get(key) or [])
            if str(item).strip()
        )
    )
    raw_records: list[dict[str, Any]] = []
    bound_sources: list[str] = []
    for relative in outputs:
        path = _safe_project_path(state.path, relative)
        if path is None or not path.is_file() or path.suffix.lower() != ".csv":
            continue
        bound_sources.append(relative)
        raw_records.extend(_metric_rows_from_csv(path, relative, run_id))
    records = _aggregate(raw_records)
    anchor_records, anchor_verified_sources = _anchor_verified_metric_tables(
        state.path,
        run_id=run_id,
        bound_sources=bound_sources,
        bound_records=records,
    )
    records.extend(anchor_records)
    requirements = _read_json(state.path / "methods" / "method_requirements.json")
    configured_primary = str(requirements.get("primary_metric") or "").strip().lower()
    configured_model = str(
        requirements.get("primary_model_id") or run_manifest.get("primary_model_id") or run_manifest.get("model_id") or ""
    ).strip()
    primary_metric, primary_selection = _select_primary_metric(
        records,
        configured_metric=configured_primary,
        configured_model=configured_model,
        bound_sources=bound_sources,
    )
    analysis_payload = _read_json(state.path / "methods" / "executable_analysis_spec.json")
    analysis_specs = [item for item in analysis_payload.get("analysis_specs") or [] if isinstance(item, dict)]
    specs_by_id = {str(item.get("analysis_spec_id")): item for item in analysis_specs if item.get("analysis_spec_id")}
    run_spec = specs_by_id.get(str(run_manifest.get("analysis_spec_id") or ""))
    default_spec = run_spec or (analysis_specs[0] if len(analysis_specs) == 1 else {})
    evidence_records = []
    for item in records:
        item_spec = specs_by_id.get(str(item.get("analysis_spec_id") or "")) or default_spec
        evidence_records.append({
            "evidence_id": hashlib.sha256(
                (
                    f"{item.get('run_id')}|{item.get('model')}|{item.get('split')}|{item.get('metric_name')}|"
                    f"{item.get('aggregation')}|{item.get('analysis_variant')}|{item.get('source_artifact')}"
                ).encode("utf-8")
            ).hexdigest()[:16],
            "entity_role": f"result_metric_{item.get('metric_name')}",
            "value": item.get("value"),
            "unit": "score",
            "metric_dimension": item.get("metric_dimension") or "score",
            "aggregation": item.get("aggregation") or "reported_value",
            "analysis_variant": item.get("analysis_variant") or "primary",
            "cohort_id": item.get("cohort_id") or run_manifest.get("cohort_id") or "main",
            "cohort_view_id": item.get("cohort_view_id") or run_manifest.get("cohort_view_id") or item_spec.get("cohort_view_id"),
            "estimand_id": item.get("estimand_id") or run_manifest.get("estimand_id") or item_spec.get("estimand_id"),
            "analysis_spec_id": item.get("analysis_spec_id") or run_manifest.get("analysis_spec_id") or item_spec.get("analysis_spec_id"),
            "sample_unit": item.get("sample_unit") or run_manifest.get("sample_unit") or "model_evaluation",
            "split": item.get("split") or run_manifest.get("evaluation_split") or "run_summary",
            "split_id": item.get("split_id") or run_manifest.get("split_id") or item_spec.get("split_id") or item.get("split") or run_manifest.get("evaluation_split") or "run_summary",
            "run_id": item.get("run_id") or run_id,
            "source_artifact": item.get("source_artifact"),
            "source_hash": item.get("source_hash"),
            "evidence_role": item.get("evidence_role") or "primary",
            "confidence": "verified_run_output",
            "target_sections": ["results", "methods", "discussion"],
            "model_id": item.get("model") or run_manifest.get("model_id") or "run_summary",
            "sample_count": item.get("sample_count"),
        })
    identity_context = {
        "project_id": state.metadata.get("project_id"),
        "run_id": run_id,
        "cohort_id": run_manifest.get("cohort_id") or run_manifest.get("cohort"),
        "task_id": run_manifest.get("task_id") or run_manifest.get("target_id") or requirements.get("task_id"),
        "sample_unit": run_manifest.get("sample_unit"),
        "validation_design_id": run_manifest.get("validation_design_id") or run_manifest.get("validation_design"),
        "split_id": run_manifest.get("split_id") or run_manifest.get("evaluation_split"),
    }
    metric_evidence_records = []
    for index, item in enumerate(records, start=1):
        source_artifact = str(item.get("source_artifact") or "")
        is_generic_compatibility = Path(source_artifact).name.lower() in {"metrics.csv", "analysis_summary.csv"}
        metric_evidence_records.append(
            normalize_metric_evidence(
                item,
                context=identity_context,
                source_artifact=source_artifact,
                source_hash=str(item.get("source_hash") or ""),
                row_index=index,
                evidence_role="presentation_only" if is_generic_compatibility else str(item.get("evidence_role") or "primary"),
            )
        )
    primary_contract = load_primary_metric_contract(state.path)
    metric_identity_report = build_metric_identity_report(metric_evidence_records, primary_contract)
    strict_primary = metric_identity_report.get("primary_metric", {}).get("record")
    if metric_identity_report.get("status") == "passed" and isinstance(strict_primary, dict):
        primary_metric = _legacy_primary_metric_record(strict_primary, run_id=run_id)
        primary_selection = "strict_primary_metric_contract"
    identity_report_path = state.path / "results" / "metric_identity_report.json"
    identity_report_payload = {
        **metric_identity_report,
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "run_id": run_id,
        "primary_metric_contract": {
            key: primary_contract.get(key)
            for key in ("contract_source", "contract_sha256", "contract_present", "contract_fields", "contract_missing_fields")
        },
    }
    identity_fingerprint = hashlib.sha256(
        json.dumps({key: value for key, value in identity_report_payload.items() if key != "generated_at"}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    identity_report_payload["report_fingerprint"] = identity_fingerprint
    existing_identity = _read_json(identity_report_path)
    if existing_identity.get("report_fingerprint") != identity_fingerprint:
        _write_json(identity_report_path, identity_report_payload)
    binding_payload = _read_json(state.path / "data" / "formal_data_run_binding.json")
    count_evidence_records = _count_records_from_payload(
        binding_payload,
        source_artifact="data/formal_data_run_binding.json",
        context=identity_context,
    )
    count_evidence_records.extend(
        _count_records_from_payload(
            run_manifest,
            source_artifact="methods/run_manifest.yaml",
            context=identity_context,
        )
    )
    result_manifest_payload = _read_json(state.path / "results" / "result_manifest.yaml")
    if result_manifest_payload:
        count_evidence_records.extend(
            _count_records_from_payload(
                result_manifest_payload,
                source_artifact="results/result_manifest.yaml",
                context=identity_context,
            )
        )
    count_identity_report = build_count_identity_report(count_evidence_records) if count_evidence_records else {
        "schema_version": "dpl.count_identity_report.v1",
        "status": "not_registered",
        "record_count": 0,
        "identity_group_count": 0,
        "records": [],
        "conflicts": [],
        "missing_identity_records": [],
        "blocking_reasons": [],
    }
    count_report_path = state.path / "results" / "count_identity_report.json"
    count_report_payload = {**count_identity_report, "generated_at": utc_now(), "project_id": state.metadata.get("project_id"), "run_id": run_id}
    count_fingerprint = hashlib.sha256(
        json.dumps({key: value for key, value in count_report_payload.items() if key != "generated_at"}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    count_report_payload["report_fingerprint"] = count_fingerprint
    existing_count = _read_json(count_report_path)
    if existing_count.get("report_fingerprint") != count_fingerprint:
        _write_json(count_report_path, count_report_payload)
    figure_trace_payload = _read_json(state.path / "results" / "figure_code_trace.json")
    run_bundle = build_run_evidence_bundle(
        state.path,
        metric_identity=metric_identity_report,
        count_identity=count_identity_report,
        figure_trace=figure_trace_payload,
        generated_at="",
    )
    published_bundle = publish_run_evidence_bundle(state.path, run_bundle)
    report = {
        "status": "resolved" if primary_metric else "no_primary_metric",
        "schema_version": "dpl.resolved_result_evidence.v2",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "run_id": run_id,
        "bound_sources": bound_sources,
        "anchor_verified_sources": anchor_verified_sources,
        "metric_count": len(records),
        "metrics": sorted(records, key=_metric_rank, reverse=True),
        "primary_metric": primary_metric,
        "primary_metric_selection": primary_selection,
        "evidence_records": evidence_records,
        "metric_evidence_records": metric_evidence_records,
        "metric_identity_report": metric_identity_report,
        "metric_identity_report_path": "results/metric_identity_report.json",
        "count_evidence_records": count_evidence_records,
        "count_identity_report": count_identity_report,
        "count_identity_report_path": "results/count_identity_report.json",
        "run_evidence_bundle": published_bundle,
        "run_evidence_bundle_path": published_bundle.get("bundle_path"),
        "primary_metric_contract": {
            key: primary_contract.get(key)
            for key in ("contract_source", "contract_sha256", "contract_present", "contract_fields", "contract_missing_fields")
        },
        "scientific_primary_metric": metric_identity_report.get("primary_metric", {}).get("record"),
        "strict_status": metric_identity_report.get("status"),
        "analysis_spec_resolution": {
            "candidate_count": len(analysis_specs),
            "selected_analysis_spec_id": default_spec.get("analysis_spec_id"),
            "ambiguous": len(analysis_specs) > 1 and not run_spec,
        },
        "policy": "Model- and split-specific verified run outputs outrank generic scalar metric files. Formal evidence also requires an explicit executable analysis spec; multiple candidate specs are never resolved by numeric value or prose wording.",
    }
    fingerprint_payload = {key: value for key, value in report.items() if key != "generated_at"}
    report["evidence_fingerprint"] = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    output_path = state.path / RESOLVED_RESULT_EVIDENCE_JSON
    existing = _read_json(output_path)
    if existing:
        if existing.get("evidence_fingerprint") == report.get("evidence_fingerprint"):
            return existing
        stable_existing = {key: value for key, value in existing.items() if key != "generated_at"}
        stable_report = {key: value for key, value in report.items() if key != "generated_at"}
        if json.dumps(stable_existing, sort_keys=True, ensure_ascii=False) == json.dumps(
            stable_report,
            sort_keys=True,
            ensure_ascii=False,
        ):
            return existing
    _write_json(output_path, report)
    return report
