# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Fixed, hash-bound signal adapters for Result Support v3."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


SIGNAL_ADAPTERS = (
    "current_resolved_evidence_metrics",
    "selected_run_manifest_metrics",
    "run_bound_result_table_metrics",
    "current_bound_pending_tasks",
    "required_data_role_bindings",
    "required_evidence_role_bindings",
)
RESULT_SUPPORT_SIGNAL_ADAPTERS = SIGNAL_ADAPTERS
SIGNAL_ADAPTER_REGISTRY = {name: name for name in SIGNAL_ADAPTERS}

PROJECT_INPUT_BINDING_KEY = "project.json"
RESULT_SUPPORT_INPUTS = (
    PROJECT_INPUT_BINDING_KEY,
    "results/result_validity_report.json",
    "research_plan/claim_contract.json",
    "research_plan/figure_storyboard.json",
    "results/result_manifest.yaml",
    "methods/run_manifest.yaml",
    "results/resolved_result_evidence.json",
    "data/data_role_coverage_report.json",
    "research_plan/plugin_binding_plan.json",
    "review/actionable_analysis_tasks.json",
    "data/data_acquisition_tasks.json",
    "research_plan/pre_execution_rescue_tasks.json",
    "review/result_support_reopen_request.json",
    "review/result_discipline_review_report.json",
    "results/results.tex",
    "results/promoted_evidence_snapshot.json",
    "results/figure_plugin_trace_report.json",
)

_TASK_PATHS = (
    "review/actionable_analysis_tasks.json",
    "data/data_acquisition_tasks.json",
    "research_plan/pre_execution_rescue_tasks.json",
)

_PENDING_STATUSES = {
    "pending",
    "pending_user_confirmation",
    "requires_user_confirmation",
    "blocked_missing_data",
    "partial",
    "executable",
    "prepared",
    "pending_result_support",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        except (OSError, yaml.YAMLError):
            return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def result_support_project_binding(project: str | Path) -> str:
    """Hash only project state consumed by Result Support assessment."""
    root = Path(project).resolve()
    project_path = root / PROJECT_INPUT_BINDING_KEY
    if not project_path.is_file():
        return ""
    project_payload = _read_json(project_path)
    stages = project_payload.get("stages") if isinstance(project_payload.get("stages"), dict) else {}
    results_stage = stages.get("results") if isinstance(stages.get("results"), dict) else {}
    payload = {
        "project_id": project_payload.get("project_id"),
        "stages": {
            "results": {
                "status": results_stage.get("status"),
                "stale": bool(results_stage.get("stale")),
            },
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalise_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _numeric(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _metric_key(metric: Any, model: Any = "") -> str:
    metric_key = _normalise_key(metric)
    model_key = _normalise_key(model)
    return f"{model_key}_{metric_key}" if model_key and metric_key else metric_key


def _metric_dimension(metric_name: Any, explicit_dimension: Any = "") -> str:
    explicit = _normalise_key(explicit_dimension)
    if explicit:
        return explicit
    name = _normalise_key(metric_name)
    aliases = (
        (("macro_f1", "f1_macro"), "f1"),
        (("roc_auc",), "auc"),
        (("balanced_accuracy",), "accuracy"),
    )
    for names, dimension in aliases:
        if any(name == candidate or name.endswith("_" + candidate) for candidate in names):
            return dimension
    for dimension in ("f1", "accuracy", "auc", "r2", "rmse", "mae"):
        if name == dimension or name.endswith("_" + dimension):
            return dimension
    return name


def _comparison_role(model: Any, metric_name: Any, explicit_role: Any = "") -> str:
    explicit = _normalise_key(explicit_role)
    if explicit in {"baseline", "proposed"}:
        return explicit
    value = _normalise_key(f"{model}_{metric_name}")
    if (
        any(marker in value for marker in ("baseline", "control", "reference", "traditional", "random_forest", "logistic"))
        or "rf" in value.split("_")
    ):
        return "baseline"
    if any(marker in value for marker in ("proposed", "main", "transformer", "ours", "candidate", "time_aware", "model")):
        return "proposed"
    return ""


def _context_value(payload: dict[str, Any], defaults: dict[str, Any], *keys: str) -> str:
    for source in (payload, defaults):
        for key in keys:
            if source.get(key) not in {None, ""}:
                return str(source[key]).strip()
    return ""


def _metric_record(
    *,
    metric_name: Any,
    value: float,
    model: Any,
    payload: dict[str, Any],
    defaults: dict[str, Any],
    adapter: str,
    source: str,
) -> dict[str, Any]:
    key = _metric_key(metric_name, model)
    return {
        "key": key,
        "metric_name": _normalise_key(metric_name),
        "metric_dimension": _metric_dimension(metric_name, payload.get("metric_dimension")),
        "value": value,
        "model": _normalise_key(model),
        "comparison_role": _comparison_role(
            model,
            metric_name,
            payload.get("comparison_role") or payload.get("metric_role"),
        ),
        "context": {
            "run_id": _context_value(payload, defaults, "run_id", "execution_id"),
            "cohort": _context_value(payload, defaults, "cohort", "cohort_id"),
            "split": _context_value(payload, defaults, "split", "data_split", "evaluation_split"),
            "sample_unit": _context_value(payload, defaults, "sample_unit", "unit_of_analysis"),
        },
        "adapter": adapter,
        "source": source,
    }


def _selected_run_id(run_manifest: dict[str, Any]) -> str:
    if str(run_manifest.get("status") or "").lower() != "success":
        return ""
    return str(run_manifest.get("run_id") or run_manifest.get("execution_id") or "").strip()


def build_result_support_input_bindings(project: str | Path) -> dict[str, str]:
    """Hash the fixed Result Support inputs that currently exist."""
    root = Path(project).resolve()
    bindings: dict[str, str] = {}
    for relative in RESULT_SUPPORT_INPUTS:
        path = root / relative
        digest = result_support_project_binding(root) if relative == PROJECT_INPUT_BINDING_KEY else _sha256(path)
        if digest:
            bindings[relative] = digest
    run_manifest = _read_json(root / "methods/run_manifest.yaml")
    for relative in _declared_tables(run_manifest):
        path = _safe_path(root, relative)
        digest = _sha256(path) if path is not None and path.is_file() else ""
        if digest:
            bindings[relative] = digest
    coverage = _read_json(root / "data/data_role_coverage_report.json")
    binding_plan = _read_json(root / "research_plan/plugin_binding_plan.json")
    role_bindings: list[dict[str, Any]] = []
    for key in ("role_bindings", "available_role_bindings", "role_evidence", "data_bindings", "bindings"):
        value = coverage.get(key)
        if isinstance(value, dict):
            role_bindings.extend(item for item in value.values() if isinstance(item, dict))
    role_bindings.extend(item for item in binding_plan.get("bindings") or [] if isinstance(item, dict))
    for binding in role_bindings:
        evidence = binding.get("evidence") if isinstance(binding.get("evidence"), dict) else binding
        for key, raw in evidence.items():
            if key not in {"path", "evidence_path", "inventory_path", "source_path"} or not raw:
                continue
            relative = str(raw).replace("\\", "/").lstrip("./")
            path = _safe_path(root, relative)
            digest = _sha256(path) if path is not None and path.is_file() else ""
            if digest:
                bindings[relative] = digest
    return bindings


def _diagnostic(code: str, source: str, selected_run_id: str, observed_run_id: str = "", **extra: Any) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "error",
        "blocking": True,
        "source": source,
        "selected_run_id": selected_run_id,
        "observed_run_id": observed_run_id,
        **extra,
    }


def _resolved_metrics(
    root: Path,
    run_manifest: dict[str, Any],
) -> tuple[dict[str, float], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    selected_run_id = _selected_run_id(run_manifest)
    relative = "results/resolved_result_evidence.json"
    payload = _read_json(root / relative)
    status = str(payload.get("status") or "").lower()
    resolved_run_id = str(payload.get("run_id") or "").strip()
    current = bool(selected_run_id) and bool(payload) and status not in {"stale", "failed", "blocked", "invalid"}
    diagnostics: list[dict[str, Any]] = []
    run_bound = bool(selected_run_id)
    if payload and selected_run_id and not resolved_run_id:
        run_bound = False
        diagnostics.append(_diagnostic("resolved_evidence_run_unbound", relative, selected_run_id))
    elif payload and selected_run_id and resolved_run_id != selected_run_id:
        run_bound = False
        diagnostics.append(_diagnostic(
            "resolved_evidence_run_mismatch", relative, selected_run_id, resolved_run_id,
        ))
    current = current and run_bound
    metrics: dict[str, float] = {}
    records: list[dict[str, Any]] = []
    if selected_run_id and payload and status not in {"stale", "failed", "blocked", "invalid"}:
        for item in payload.get("metrics") or []:
            if not isinstance(item, dict):
                continue
            item_run_id = str(item.get("run_id") or "").strip()
            if selected_run_id and item_run_id and item_run_id != selected_run_id:
                diagnostics.append(_diagnostic(
                    "resolved_metric_run_mismatch",
                    relative,
                    selected_run_id,
                    item_run_id,
                    metric_name=str(item.get("metric_name") or item.get("name") or ""),
                ))
                continue
            if selected_run_id and not item_run_id:
                if resolved_run_id:
                    diagnostics.append(_diagnostic(
                        "resolved_metric_run_unbound",
                        relative,
                        selected_run_id,
                        metric_name=str(item.get("metric_name") or item.get("name") or ""),
                    ))
                continue
            if not current:
                continue
            value = _numeric(item.get("value"))
            key = _metric_key(item.get("metric_name") or item.get("name"), item.get("model") or item.get("model_id"))
            if key and value is not None:
                metrics[key] = value
                records.append(_metric_record(
                    metric_name=item.get("metric_name") or item.get("name"),
                    value=value,
                    model=item.get("model") or item.get("model_id"),
                    payload=item,
                    defaults={**run_manifest, **payload},
                    adapter="current_resolved_evidence_metrics",
                    source=relative,
                ))
        primary = (payload.get("primary_metric") or {}) if current else {}
        if isinstance(primary, dict):
            primary_run_id = str(primary.get("run_id") or "").strip()
            if selected_run_id and primary and primary_run_id != selected_run_id:
                diagnostics.append(_diagnostic(
                    "resolved_metric_run_unbound" if not primary_run_id else "resolved_metric_run_mismatch",
                    relative,
                    selected_run_id,
                    primary_run_id,
                    metric_name=str(primary.get("metric_name") or primary.get("name") or ""),
                ))
                primary = {}
            value = _numeric(primary.get("value"))
            key = _normalise_key(primary.get("metric_name") or primary.get("name"))
            if key and value is not None:
                metrics[f"primary_{key}"] = value
                records.append(_metric_record(
                    metric_name=primary.get("metric_name") or primary.get("name"),
                    value=value,
                    model=primary.get("model") or primary.get("model_id") or "primary",
                    payload=primary,
                    defaults={**run_manifest, **payload},
                    adapter="current_resolved_evidence_metrics",
                    source=relative,
                ))
    return metrics, records, {
        "adapter": "current_resolved_evidence_metrics",
        "current": current,
        "run_id": resolved_run_id,
        "source": relative if payload else None,
        "metric_count": len(metrics),
        "diagnostics": diagnostics,
    }, diagnostics


def _manifest_metrics(
    run_manifest: dict[str, Any],
) -> tuple[dict[str, float], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    selected_run_id = _selected_run_id(run_manifest)
    selected = bool(selected_run_id)
    metrics: dict[str, float] = {}
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    if selected:
        for name, raw in (run_manifest.get("metrics") or {}).items():
            payload = raw if isinstance(raw, dict) else {}
            observed_run_id = str(payload.get("run_id") or payload.get("execution_id") or "").strip()
            if observed_run_id and observed_run_id != selected_run_id:
                diagnostics.append(_diagnostic(
                    "manifest_metric_run_mismatch",
                    "methods/run_manifest.yaml",
                    selected_run_id,
                    observed_run_id,
                    metric_name=str(name),
                ))
                continue
            value = _numeric(payload.get("value") if payload else raw)
            model = payload.get("model") or payload.get("model_id") or ""
            key = _metric_key(name, model)
            if key and value is not None:
                metrics[key] = value
                records.append(_metric_record(
                    metric_name=name,
                    value=value,
                    model=model,
                    payload=payload,
                    defaults=run_manifest,
                    adapter="selected_run_manifest_metrics",
                    source="methods/run_manifest.yaml",
                ))
    return metrics, records, {
        "adapter": "selected_run_manifest_metrics",
        "current": selected,
        "run_id": selected_run_id,
        "source": "methods/run_manifest.yaml" if run_manifest else None,
        "metric_count": len(metrics),
        "diagnostics": diagnostics,
    }, diagnostics


def _declared_tables(run_manifest: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("tables_generated", "output_files", "declared_outputs"):
        raw_values = run_manifest.get(key) or []
        if isinstance(raw_values, str):
            raw_values = [raw_values]
        for raw in raw_values:
            relative = str(raw or "").strip().replace("\\", "/").lstrip("./")
            if relative.lower().endswith(".csv") and relative not in values:
                values.append(relative)
    return values


def _safe_path(root: Path, relative: str) -> Path | None:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _table_metrics(
    root: Path,
    run_manifest: dict[str, Any],
    selected_run_id: str,
) -> tuple[dict[str, float], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    metrics: dict[str, float] = {}
    sources: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    if str(run_manifest.get("status") or "").lower() == "success" and selected_run_id:
        for relative in _declared_tables(run_manifest):
            path = _safe_path(root, relative)
            if path is None or not path.is_file():
                continue
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
            except OSError:
                continue
            used = False
            for row in rows:
                lowered = {_normalise_key(key): value for key, value in row.items() if key}
                row_run_id = str(lowered.get("run_id") or lowered.get("execution_id") or "").strip()
                if selected_run_id and not row_run_id:
                    diagnostics.append(_diagnostic(
                        "table_metric_run_unbound",
                        relative,
                        selected_run_id,
                        metric_name=str(lowered.get("metric") or lowered.get("metric_name") or ""),
                    ))
                    continue
                if selected_run_id and row_run_id != selected_run_id:
                    diagnostics.append(_diagnostic(
                        "table_metric_run_mismatch",
                        relative,
                        selected_run_id,
                        row_run_id,
                        metric_name=str(lowered.get("metric") or lowered.get("metric_name") or ""),
                    ))
                    continue
                value = _numeric(lowered.get("value") or lowered.get("score") or lowered.get("metric_value"))
                key = _metric_key(
                    lowered.get("metric") or lowered.get("metric_name") or lowered.get("name") or lowered.get("key"),
                    lowered.get("model") or lowered.get("model_id"),
                )
                if key and value is not None:
                    metrics[key] = value
                    records.append(_metric_record(
                        metric_name=lowered.get("metric") or lowered.get("metric_name") or lowered.get("name") or lowered.get("key"),
                        value=value,
                        model=lowered.get("model") or lowered.get("model_id"),
                        payload=lowered,
                        defaults=run_manifest,
                        adapter="run_bound_result_table_metrics",
                        source=relative,
                    ))
                    used = True
            if used:
                sources.append(relative)
    return metrics, records, {
        "adapter": "run_bound_result_table_metrics",
        "current": bool(sources),
        "run_id": selected_run_id,
        "sources": sources,
        "metric_count": len(metrics),
        "diagnostics": diagnostics,
    }, diagnostics


def _binding_items(value: Any) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for path, expected in value.items():
            if isinstance(expected, dict):
                expected = expected.get("sha256") or expected.get("hash")
            if path and expected:
                items.append((str(path).replace("\\", "/").lstrip("./"), str(expected)))
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            path = item.get("path") or item.get("relative_path")
            expected = item.get("sha256") or item.get("hash")
            if path and expected:
                items.append((str(path).replace("\\", "/").lstrip("./"), str(expected)))
    return items


def _current_bound_pending_tasks(
    root: Path,
    current_bindings: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    active: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    inspected = 0
    for relative in _TASK_PATHS:
        payload = _read_json(root / relative)
        payload_bindings = payload.get("input_bindings")
        for task in payload.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            inspected += 1
            status = str(task.get("status") or (task.get("feasibility") or {}).get("status") or "").lower()
            task_id = str(task.get("task_id") or "")
            if status == "stale":
                skipped.append({**task, "source": relative, "skip_reason": "stale_task"})
                warnings.append({
                    "code": "stale_task_skipped",
                    "severity": "warning",
                    "task_id": task_id,
                    "source": relative,
                })
                continue
            if status not in _PENDING_STATUSES:
                continue
            bindings = _binding_items(task.get("input_bindings") or payload_bindings)
            if task.get("relevant") is False or task.get("related") is False:
                skipped.append({**task, "source": relative, "skip_reason": "unrelated_task"})
                warnings.append({
                    "code": "unrelated_task_skipped",
                    "severity": "warning",
                    "task_id": task_id,
                    "source": relative,
                })
                continue
            if task.get("required") is False or task.get("optional") is True:
                skipped.append({**task, "source": relative, "skip_reason": "optional_task"})
                warnings.append({
                    "code": "optional_task_skipped",
                    "severity": "warning",
                    "task_id": task_id,
                    "source": relative,
                })
                continue
            if not bindings and task.get("binding_match") is not True:
                skipped.append({**task, "source": relative, "skip_reason": "missing_input_binding"})
                warnings.append({
                    "code": "task_missing_input_binding",
                    "severity": "warning",
                    "task_id": task_id,
                    "source": relative,
                })
                continue
            binding_match = (
                bool(bindings)
                and all(current_bindings.get(path) == expected for path, expected in bindings)
            ) or (not bindings and task.get("binding_match") is True)
            current_marker = task.get("current", task.get("is_current", payload.get("current", binding_match)))
            if not binding_match:
                skipped.append({**task, "source": relative, "skip_reason": "input_binding_mismatch"})
                warnings.append({
                    "code": "task_input_binding_mismatch",
                    "severity": "warning",
                    "task_id": task_id,
                    "source": relative,
                })
                continue
            if not bool(current_marker):
                skipped.append({**task, "source": relative, "skip_reason": "not_current"})
                warnings.append({
                    "code": "task_not_current",
                    "severity": "warning",
                    "task_id": task_id,
                    "source": relative,
                })
                continue
            item = dict(task)
            item["source"] = item.get("source") or relative
            item["binding_match"] = True
            active.append(item)
    return active, skipped, warnings, {
        "adapter": "current_bound_pending_tasks",
        "current": bool(active),
        "inspected_task_count": inspected,
        "active_task_ids": [str(item.get("task_id") or "") for item in active],
        "skipped_task_ids": [str(item.get("task_id") or "") for item in skipped],
    }


def _roles(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(_normalise_key(value) for value in values if _normalise_key(value)))


_COVERED_BINDING_STATES = {"covered", "covered_project_local"}


def _role_binding_diagnostic(code: str, role: str, source: str, **extra: Any) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "error",
        "blocking": True,
        "required_role": role,
        "source": source,
        **extra,
    }


def _normalise_role_binding(binding: dict[str, Any]) -> tuple[dict[str, Any], str]:
    nested = binding.get("evidence")
    if isinstance(nested, dict):
        return dict(nested), "current_nested_evidence_v1"
    evidence = {
        "path": binding.get("evidence_path") or binding.get("path"),
        "sha256": binding.get("evidence_sha256") or binding.get("sha256") or binding.get("hash"),
        "run_id": binding.get("run_id"),
        "cohort_id": binding.get("cohort_id"),
        "snapshot_id": binding.get("snapshot_id") or binding.get("evidence_snapshot_id"),
    }
    return evidence, "legacy_flattened_evidence_v1"


def _declared_context_value(payload: dict[str, Any], *keys: str) -> str:
    contexts = [payload]
    for context_key in ("evidence_context", "claim_context", "context", "active_context"):
        context = payload.get(context_key)
        if isinstance(context, dict):
            contexts.insert(0, context)
    for context in contexts:
        for key in keys:
            value = context.get(key)
            if value not in {None, ""}:
                return str(value).strip()
    return ""


def _role_context(payload: dict[str, Any], *fallbacks: dict[str, Any]) -> dict[str, str]:
    contexts = (payload, *fallbacks)
    return {
        "cohort_id": next(
            (
                value
                for context in contexts
                if (value := _declared_context_value(context, "cohort_id", "cohort"))
            ),
            "",
        ),
        "snapshot_id": next(
            (
                value
                for context in contexts
                if (value := _declared_context_value(context, "snapshot_id", "evidence_snapshot_id"))
            ),
            "",
        ),
    }


def _role_obligation(
    requirement_kind: str,
    role: str,
    *,
    claim_id: str = "",
    context: dict[str, str] | None = None,
    source: str,
) -> dict[str, str]:
    required_context = context or {"cohort_id": "", "snapshot_id": ""}
    return {
        "requirement_kind": requirement_kind,
        "required_role": role,
        "claim_id": claim_id,
        "cohort_id": str(required_context.get("cohort_id") or ""),
        "snapshot_id": str(required_context.get("snapshot_id") or ""),
        "source": source,
    }


def _deduplicate_obligations(obligations: list[dict[str, str]]) -> list[dict[str, str]]:
    deduplicated: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for obligation in obligations:
        identity = (
            obligation["requirement_kind"],
            obligation["required_role"],
            obligation["claim_id"],
            obligation["cohort_id"],
            obligation["snapshot_id"],
        )
        if identity not in seen:
            seen.add(identity)
            deduplicated.append(obligation)
    return deduplicated


def _validate_role_binding(
    root: Path,
    role: str,
    binding: dict[str, Any],
    *,
    source: str,
    binding_kind: str,
    current_run_id: str,
    current_cohort_id: str,
    current_snapshot_id: str,
    obligation: dict[str, str],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    diagnostic_context = {
        "requirement_kind": obligation["requirement_kind"],
        "claim_id": obligation["claim_id"],
        "required_cohort_id": obligation["cohort_id"],
        "required_snapshot_id": obligation["snapshot_id"],
    }
    state = str(binding.get("state") or binding.get("status") or "").lower()
    if state not in _COVERED_BINDING_STATES:
        return None, [_role_binding_diagnostic(
            "role_binding_state_not_covered",
            role,
            source,
            observed_state=state or "missing",
            **diagnostic_context,
        )]
    if not current_run_id:
        return None, [_role_binding_diagnostic(
            "role_binding_selected_run_missing", role, source, **diagnostic_context,
        )]
    evidence, compatibility_mode = _normalise_role_binding(binding)
    relative = str(evidence.get("path") or "").replace("\\", "/").lstrip("./")
    path = _safe_path(root, relative) if relative else None
    if path is None or not path.is_file():
        return None, [_role_binding_diagnostic(
            "role_binding_evidence_missing",
            role,
            source,
            evidence_path=relative,
            **diagnostic_context,
        )]
    expected_hash = str(evidence.get("sha256") or evidence.get("hash") or "")
    current_hash = _sha256(path)
    if not expected_hash or expected_hash != current_hash:
        return None, [_role_binding_diagnostic(
            "role_binding_hash_mismatch",
            role,
            source,
            evidence_path=relative,
            expected_sha256=expected_hash,
            current_sha256=current_hash,
            **diagnostic_context,
        )]
    diagnostics: list[dict[str, Any]] = []
    for field, current, required, binding_code, current_code in (
        ("run_id", current_run_id, current_run_id, "role_binding_run_mismatch", ""),
        (
            "cohort_id",
            current_cohort_id,
            obligation["cohort_id"],
            "role_binding_cohort_mismatch",
            "role_current_cohort_mismatch",
        ),
        (
            "snapshot_id",
            current_snapshot_id,
            obligation["snapshot_id"],
            "role_binding_snapshot_mismatch",
            "role_current_snapshot_mismatch",
        ),
    ):
        observed = str(evidence.get(field) or "")
        if required and current != required and current_code:
            diagnostics.append(_role_binding_diagnostic(
                current_code if current else current_code.replace("mismatch", "unbound"),
                role,
                source,
                expected_value=required,
                observed_value=current,
                evidence_path=relative,
                **diagnostic_context,
            ))
        expected = required or current
        if expected and observed != expected:
            diagnostics.append(_role_binding_diagnostic(
                binding_code if observed else binding_code.replace("mismatch", "unbound"),
                role,
                source,
                expected_value=expected,
                observed_value=observed,
                evidence_path=relative,
                **diagnostic_context,
            ))
    if diagnostics:
        return None, diagnostics
    return {
        "required_role": role,
        "requirement_kind": obligation["requirement_kind"],
        "binding_kind": binding_kind or obligation["requirement_kind"],
        "claim_id": obligation["claim_id"],
        "required_cohort_id": obligation["cohort_id"],
        "required_snapshot_id": obligation["snapshot_id"],
        "state": state,
        "source": source,
        "evidence_path": relative,
        "evidence_sha256": current_hash,
        "run_id": str(evidence.get("run_id") or ""),
        "cohort_id": str(evidence.get("cohort_id") or ""),
        "snapshot_id": str(evidence.get("snapshot_id") or ""),
        "compatibility_mode": compatibility_mode,
    }, []


def _required_and_bound_roles(
    root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    coverage = _read_json(root / "data/data_role_coverage_report.json")
    generic_required = _roles(
        [
            *(coverage.get("required_roles") or []),
            *(coverage.get("blocking_missing_roles") or []),
        ]
    )
    validity = _read_json(root / "results/result_validity_report.json")
    generic_required.extend(_roles(validity.get("required_data_roles") or validity.get("required_roles") or []))
    run_manifest = _read_json(root / "methods/run_manifest.yaml")
    generic_required.extend(_roles(run_manifest.get("required_data_roles") or run_manifest.get("required_roles") or []))
    storyboard = _read_json(root / "research_plan/figure_storyboard.json")
    for figure in storyboard.get("figures") or []:
        if isinstance(figure, dict):
            generic_required.extend(_roles([
                *(figure.get("required_data_roles") or []),
                *(figure.get("required_data") or []),
                *(figure.get("data_roles") or []),
            ]))
    generic_required.extend(_roles(storyboard.get("required_data_roles") or []))
    contract = _read_json(root / "research_plan/claim_contract.json")
    resolved_evidence = _read_json(root / "results/resolved_result_evidence.json")
    fallback_context = _role_context({}, validity, coverage, resolved_evidence)
    obligations = [
        _role_obligation(
            "data",
            role,
            context=fallback_context,
            source="project_required_roles",
        )
        for role in dict.fromkeys(generic_required)
    ]
    for index, claim in enumerate(contract.get("claims") or [], start=1):
        if isinstance(claim, dict):
            claim_id = str(claim.get("claim_id") or f"claim_{index}")
            claim_context = _role_context(claim, validity, coverage, resolved_evidence)
            obligations.extend(
                _role_obligation(
                    "data",
                    role,
                    claim_id=claim_id,
                    context=claim_context,
                    source="research_plan/claim_contract.json",
                )
                for role in _roles(claim.get("required_data_roles") or [])
            )
            obligations.extend(
                _role_obligation(
                    "evidence",
                    role,
                    claim_id=claim_id,
                    context=claim_context,
                    source="research_plan/claim_contract.json",
                )
                for role in _roles(claim.get("required_evidence_roles") or [])
            )
    obligations = _deduplicate_obligations(obligations)

    current_run_id = _selected_run_id(run_manifest)
    run_cohort_id = str(run_manifest.get("cohort_id") or run_manifest.get("cohort") or "").strip()
    promoted_snapshot_id = str(
        _read_json(root / "results/promoted_evidence_snapshot.json").get("snapshot_id") or ""
    ).strip()
    candidates: list[tuple[str, str, dict[str, Any], str]] = []
    for key in ("role_bindings", "available_role_bindings", "role_evidence", "data_bindings", "bindings"):
        value = coverage.get(key)
        if isinstance(value, dict):
            for role, binding in value.items():
                binding_payload = dict(binding) if isinstance(binding, dict) else {"state": "legacy_unstructured"}
                candidates.append((
                    _normalise_key(role),
                    _normalise_key(binding_payload.get("kind") or binding_payload.get("requirement_kind")),
                    binding_payload,
                    "data/data_role_coverage_report.json",
                ))
    binding_plan = _read_json(root / "research_plan/plugin_binding_plan.json")
    for item in binding_plan.get("bindings") or []:
        if not isinstance(item, dict) or str(item.get("kind") or item.get("requirement_kind") or "").lower() not in {"data", "evidence", ""}:
            continue
        role = item.get("role") or item.get("required_role") or str(item.get("requirement_id") or "").split(":")[-1]
        if role:
            candidates.append((
                _normalise_key(role),
                _normalise_key(item.get("kind") or item.get("requirement_kind")),
                dict(item),
                "research_plan/plugin_binding_plan.json",
            ))
    bound_obligations: list[dict[str, str]] = []
    accepted: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for obligation in obligations:
        role = obligation["required_role"]
        obligation_diagnostics: list[dict[str, Any]] = []
        for candidate_role, binding_kind, binding, source in candidates:
            if candidate_role != role:
                continue
            if binding_kind and binding_kind != obligation["requirement_kind"]:
                obligation_diagnostics.append(_role_binding_diagnostic(
                    "role_binding_kind_mismatch",
                    role,
                    source,
                    requirement_kind=obligation["requirement_kind"],
                    binding_kind=binding_kind,
                    claim_id=obligation["claim_id"],
                ))
                continue
            accepted_binding, binding_diagnostics = _validate_role_binding(
                root,
                role,
                binding,
                source=source,
                binding_kind=binding_kind,
                current_run_id=current_run_id,
                current_cohort_id=run_cohort_id,
                current_snapshot_id=promoted_snapshot_id,
                obligation=obligation,
            )
            if accepted_binding:
                bound_obligations.append(obligation)
                accepted.append(accepted_binding)
                break
            obligation_diagnostics.extend(binding_diagnostics)
        else:
            diagnostics.extend(obligation_diagnostics)
    return obligations, bound_obligations, accepted, diagnostics


def _required_role_tasks(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    obligations, bound_obligations, accepted, diagnostics = _required_and_bound_roles(root)
    bound_ids = {
        (
            item["requirement_kind"], item["required_role"], item["claim_id"],
            item["cohort_id"], item["snapshot_id"],
        )
        for item in bound_obligations
    }
    unbound_obligations = [
        item for item in obligations
        if (
            item["requirement_kind"], item["required_role"], item["claim_id"],
            item["cohort_id"], item["snapshot_id"],
        ) not in bound_ids
    ]
    data_obligations = [item for item in obligations if item["requirement_kind"] == "data"]
    evidence_obligations = [item for item in obligations if item["requirement_kind"] == "evidence"]
    unbound_data_obligations = [item for item in unbound_obligations if item["requirement_kind"] == "data"]
    unbound_evidence_obligations = [item for item in unbound_obligations if item["requirement_kind"] == "evidence"]

    def tasks_for(items: list[dict[str, str]], kind: str) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for item in obligations:
            if item["requirement_kind"] == kind:
                counts[item["required_role"]] = counts.get(item["required_role"], 0) + 1
        tasks: list[dict[str, Any]] = []
        for item in items:
            role = item["required_role"]
            task_type = f"unbound_required_{kind}_task"
            task: dict[str, Any] = {
                "task_id": f"{task_type}:{role}",
                "task_type": task_type,
                "status": "pending",
                "required_role" if kind == "data" else "required_evidence_role": role,
                "selected_route": "supplement_data_and_method",
            }
            if counts[role] > 1:
                context_suffix = item["claim_id"] or f"{item['cohort_id']}:{item['snapshot_id']}"
                task["task_id"] += f":{context_suffix}"
                task.update({
                    "claim_id": item["claim_id"],
                    "cohort_id": item["cohort_id"],
                    "snapshot_id": item["snapshot_id"],
                })
            tasks.append(task)
        return tasks

    data_tasks = tasks_for(unbound_data_obligations, "data")
    evidence_tasks = tasks_for(unbound_evidence_obligations, "evidence")
    data_roles = list(dict.fromkeys(item["required_role"] for item in data_obligations))
    evidence_roles = list(dict.fromkeys(item["required_role"] for item in evidence_obligations))
    unbound_data_roles = list(dict.fromkeys(item["required_role"] for item in unbound_data_obligations))
    unbound_evidence_roles = list(dict.fromkeys(item["required_role"] for item in unbound_evidence_obligations))
    bound_data_roles = [role for role in data_roles if role not in set(unbound_data_roles)]
    bound_evidence_roles = [role for role in evidence_roles if role not in set(unbound_evidence_roles)]
    data_signal = {
        "adapter": "required_data_role_bindings",
        "current": True,
        "required_roles": data_roles,
        "bound_roles": bound_data_roles,
        "unbound_required_roles": unbound_data_roles,
        "required_obligations": data_obligations,
        "bound_obligations": [item for item in bound_obligations if item["requirement_kind"] == "data"],
        "unbound_required_obligations": unbound_data_obligations,
        "accepted_bindings": [item for item in accepted if item["requirement_kind"] == "data"],
        "binding_diagnostics": [item for item in diagnostics if item["requirement_kind"] == "data"],
    }
    evidence_signal = {
        "adapter": "required_evidence_role_bindings",
        "current": True,
        "required_evidence_roles": evidence_roles,
        "bound_evidence_roles": bound_evidence_roles,
        "unbound_required_evidence_roles": unbound_evidence_roles,
        "required_obligations": evidence_obligations,
        "bound_obligations": [item for item in bound_obligations if item["requirement_kind"] == "evidence"],
        "unbound_required_obligations": unbound_evidence_obligations,
        "accepted_bindings": [item for item in accepted if item["requirement_kind"] == "evidence"],
        "binding_diagnostics": [item for item in diagnostics if item["requirement_kind"] == "evidence"],
    }
    return data_tasks, evidence_tasks, data_signal, evidence_signal


def collect_result_support_signals(project: str | Path) -> dict[str, Any]:
    """Collect deterministic Result Support signals in the fixed adapter order."""
    root = Path(project).resolve()
    run_manifest = _read_json(root / "methods/run_manifest.yaml")
    selected_run_id = _selected_run_id(run_manifest)
    selection_diagnostics = []
    if not selected_run_id:
        selection_diagnostics.append(_diagnostic(
            "selected_run_id_missing",
            "methods/run_manifest.yaml",
            "",
        ))
    input_bindings = build_result_support_input_bindings(root)

    resolved_metrics, resolved_records, resolved_signal, resolved_diagnostics = _resolved_metrics(root, run_manifest)
    manifest_metrics, manifest_records, manifest_signal, manifest_diagnostics = _manifest_metrics(run_manifest)
    table_metrics, table_records, table_signal, table_diagnostics = _table_metrics(root, run_manifest, selected_run_id)
    pending_tasks, skipped_tasks, warnings, pending_signal = _current_bound_pending_tasks(root, input_bindings)
    unbound_tasks, unbound_evidence_tasks, role_signal, evidence_role_signal = _required_role_tasks(root)

    metrics: dict[str, float] = {}
    metric_sources: dict[str, str] = {}
    for adapter, values in (
        ("run_bound_result_table_metrics", table_metrics),
        ("selected_run_manifest_metrics", manifest_metrics),
        ("current_resolved_evidence_metrics", resolved_metrics),
    ):
        for key, value in values.items():
            metrics[key] = value
            metric_sources[key] = adapter
    metric_records_by_identity: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = {}
    for records in (table_records, manifest_records, resolved_records):
        for record in records:
            context = record.get("context") if isinstance(record.get("context"), dict) else {}
            identity = (
                str(record.get("key") or ""),
                str(record.get("metric_dimension") or ""),
                str(record.get("comparison_role") or ""),
                str(context.get("run_id") or ""),
                str(context.get("cohort") or ""),
                str(context.get("split") or ""),
                str(context.get("sample_unit") or ""),
            )
            metric_records_by_identity[identity] = record

    signals = {
        "current_resolved_evidence_metrics": resolved_signal,
        "selected_run_manifest_metrics": manifest_signal,
        "run_bound_result_table_metrics": table_signal,
        "current_bound_pending_tasks": pending_signal,
        "required_data_role_bindings": role_signal,
        "required_evidence_role_bindings": evidence_role_signal,
    }
    return {
        "adapter_order": list(SIGNAL_ADAPTERS),
        "selected_run_id": selected_run_id,
        "input_bindings": input_bindings,
        "signals": signals,
        "metrics": metrics,
        "metric_records": list(metric_records_by_identity.values()),
        "metric_sources": metric_sources,
        "blocking_diagnostics": [
            *selection_diagnostics,
            *resolved_diagnostics,
            *manifest_diagnostics,
            *table_diagnostics,
        ],
        "pending_tasks": pending_tasks,
        "skipped_tasks": skipped_tasks,
        "warnings": warnings,
        "unbound_required_data_tasks": unbound_tasks,
        "unbound_required_evidence_tasks": unbound_evidence_tasks,
        "route_required": bool(
            pending_tasks
            or unbound_tasks
            or unbound_evidence_tasks
            or selection_diagnostics
            or resolved_diagnostics
            or manifest_diagnostics
            or table_diagnostics
        ),
    }


extract_result_support_signals = collect_result_support_signals


__all__ = [
    "SIGNAL_ADAPTERS",
    "RESULT_SUPPORT_SIGNAL_ADAPTERS",
    "SIGNAL_ADAPTER_REGISTRY",
    "PROJECT_INPUT_BINDING_KEY",
    "RESULT_SUPPORT_INPUTS",
    "build_result_support_input_bindings",
    "collect_result_support_signals",
    "extract_result_support_signals",
    "result_support_project_binding",
]
