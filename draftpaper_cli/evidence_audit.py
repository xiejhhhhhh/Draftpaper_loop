"""Read-only audits for evidence identity and migration routing.

The audit deliberately does not repair project files.  Its job is to tell the
workflow whether a legacy project can be deterministically rebuilt, must stay
presentation-only, or needs scientific input from the user before it can
reach a confirmable checkpoint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .code_ownership import assess_figure_code_trace
from .project_state import load_project
from .run_evidence_bundle import load_active_run_evidence_bundle


AUDIT_SCHEMA = "dpl.evidence_identity_audit.v1"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _records(report: Mapping[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = report.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _identity_findings(report: Mapping[str, Any], *, kind: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = _records(report, "records", f"{kind}_evidence_records")
    missing: list[dict[str, Any]] = []
    legacy: list[dict[str, Any]] = []
    for record in records:
        if record.get("identity_complete") is False or record.get("missing_identity_fields"):
            missing.append(
                {
                    "kind": kind,
                    "record_id": record.get("metric_record_id") or record.get("count_record_id"),
                    "source_artifact": record.get("source_artifact"),
                    "missing_fields": list(record.get("missing_identity_fields") or []),
                    "evidence_role": record.get("evidence_role"),
                }
            )
        if record.get("legacy_source") or record.get("evidence_role") in {"presentation_only", "legacy"}:
            legacy.append(
                {
                    "kind": kind,
                    "record_id": record.get("metric_record_id") or record.get("count_record_id"),
                    "source_artifact": record.get("source_artifact"),
                    "evidence_role": record.get("evidence_role"),
                    "schema_version": record.get("schema_version"),
                }
            )
    return missing, legacy


def audit_evidence_identity(project: str | Path) -> dict[str, Any]:
    """Inspect a project without writing any file or changing project state."""

    state = load_project(project)
    root = state.path
    resolved = _read_json(root / "results" / "resolved_result_evidence.json")
    metric_report = _read_json(root / "results" / "metric_identity_report.json")
    count_report = _read_json(root / "results" / "count_identity_report.json")
    active_bundle = load_active_run_evidence_bundle(root)
    figure_validation = assess_figure_code_trace(root)

    if not metric_report and isinstance(resolved.get("metric_identity_report"), Mapping):
        metric_report = dict(resolved["metric_identity_report"])
    if not count_report and isinstance(resolved.get("count_identity_report"), Mapping):
        count_report = dict(resolved["count_identity_report"])

    metric_missing, metric_legacy = _identity_findings(metric_report, kind="metric")
    count_missing, count_legacy = _identity_findings(count_report, kind="count")
    missing_identity = [*metric_missing, *count_missing]
    legacy_compatibility = [*metric_legacy, *count_legacy]

    stale_traces = [
        dict(item)
        for item in figure_validation.get("checks") or []
        if isinstance(item, Mapping) and item.get("status") != "current"
    ]
    metric_status = str(metric_report.get("status") or "missing")
    count_status = str(count_report.get("status") or "missing")
    active_status = str(active_bundle.get("status") or "missing")
    trace_status = str(figure_validation.get("status") or "missing")

    deterministic_migrations: list[dict[str, Any]] = []
    if legacy_compatibility:
        deterministic_migrations.append(
            {
                "route": "presentation_only",
                "reason": "Legacy or compatibility records can remain visible, but their scientific identity cannot be guessed.",
                "record_count": len(legacy_compatibility),
            }
        )
    if metric_report.get("schema_version") == "dpl.metric_identity_report.v1" and metric_report.get("report_fingerprint"):
        deterministic_migrations.append(
            {
                "route": "reuse_report_fingerprint",
                "reason": "The report has a stable fingerprint and can be referenced by a later derived rebuild.",
                "source": "results/metric_identity_report.json",
            }
        )

    derived_rebuild: list[dict[str, Any]] = []
    if stale_traces:
        derived_rebuild.append(
            {
                "route": "rebuild-derived",
                "artifacts": ["results/figure_code_trace.json", "results/figure_code_trace_validation.json"],
                "reason": "Figure, metadata, producer code, input, or transaction bindings are stale.",
            }
        )
    if legacy_compatibility:
        derived_rebuild.append(
            {
                "route": "rebuild-derived",
                "artifacts": ["results/metric_identity_report.json", "results/count_identity_report.json"],
                "reason": "Compatibility outputs must be regenerated from canonical typed records, never used as the source of truth.",
            }
        )

    scientific_rerun: list[dict[str, Any]] = []
    if missing_identity:
        scientific_rerun.append(
            {
                "route": "refinement_or_methods_rerun",
                "reason": "Missing model, task, cohort, validation, split, count, or filter semantics cannot be safely inferred.",
                "record_ids": [item.get("record_id") for item in missing_identity],
            }
        )
    if metric_status in {"blocked", "blocked_missing_primary_metric", "blocked_ambiguous_primary_metric"}:
        scientific_rerun.append(
            {
                "route": "primary_metric_contract_review",
                "reason": "The primary metric contract does not resolve exactly one canonical record.",
            }
        )
    if count_status == "blocked":
        scientific_rerun.append(
            {
                "route": "data_or_filter_review",
                "reason": "The same count identity has conflicting values and must be checked at its data/filter source.",
            }
        )

    checks = [
        {
            "name": "metric_identity",
            "status": metric_status,
            "source": "results/metric_identity_report.json" if metric_report else None,
        },
        {
            "name": "count_identity",
            "status": count_status,
            "source": "results/count_identity_report.json" if count_report else None,
        },
        {
            "name": "active_run_bundle",
            "status": active_status,
            "source": "results/active_run_evidence_bundle.json" if active_status != "missing" else None,
        },
        {
            "name": "figure_code_trace",
            "status": trace_status,
            "source": "results/figure_code_trace.json" if trace_status != "missing" else None,
        },
    ]

    evidence_present = bool(metric_report or count_report or resolved or active_status != "missing" or trace_status != "missing")
    blocking = bool(
        missing_identity
        or stale_traces
        or metric_status in {"blocked", "blocked_missing_primary_metric", "blocked_ambiguous_primary_metric"}
        or count_status == "blocked"
        or (evidence_present and active_status in {"missing", "stale"})
    )
    status = "blocked" if blocking else "needs_review" if legacy_compatibility or not evidence_present else "passed"

    return {
        "schema_version": AUDIT_SCHEMA,
        "status": status,
        "read_only": True,
        "writes_performed": [],
        "project_id": state.metadata.get("project_id"),
        "project_relative_root": ".",
        "checks": checks,
        "missing_identity": missing_identity,
        "legacy_compatibility": legacy_compatibility,
        "ambiguous_counts": [
            item
            for item in count_missing
            if item.get("missing_fields")
        ],
        "stale_traces": stale_traces,
        "deterministic_migrations": deterministic_migrations,
        "derived_rebuild": derived_rebuild,
        "requires_scientific_rerun": scientific_rerun,
        "policy": (
            "This audit is diagnostic only. It never guesses scientific identity, edits project state, "
            "promotes legacy evidence, or confirms a checkpoint."
        ),
    }


__all__ = ["AUDIT_SCHEMA", "audit_evidence_identity"]
