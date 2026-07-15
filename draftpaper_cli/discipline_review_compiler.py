"""Compile post-Results discipline rules from the current semantic evidence graph."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def compile_discipline_review_inputs(project: str | Path) -> dict[str, Any]:
    root = Path(project)
    claim_map = _read(root / "writing" / "claim_maps" / "results.json") or _read(root / "writing" / "claim_bindings" / "results.json")
    figure_gate = _read(root / "results" / "figure_contract_gate_report.json")
    trace = _read(root / "results" / "figure_plugin_trace_report.json")
    registry = _read(root / "writing" / "scientific_evidence_registry.json")
    analysis = _read(root / "methods" / "executable_analysis_spec.json")
    results_path = root / "results" / "results.tex"
    results_hash = hashlib.sha256(results_path.read_bytes()).hexdigest() if results_path.exists() else ""
    evidence_index = {str(item.get("evidence_id")): item for item in registry.get("records") or [] if isinstance(item, dict) and item.get("evidence_id")}
    figure_index = {str(item.get("figure_id")): item for item in figure_gate.get("contract_checks") or [] if isinstance(item, dict) and item.get("figure_id")}
    trace_index = {str(item.get("figure_id")): item for item in trace.get("figure_checks") or [] if isinstance(item, dict) and item.get("figure_id")}
    spec_index = {str(item.get("analysis_spec_id")): item for item in analysis.get("analysis_specs") or [] if isinstance(item, dict) and item.get("analysis_spec_id")}
    rows = []
    for claim in claim_map.get("section_claims") or []:
        if not isinstance(claim, dict):
            continue
        evidence_ids = [str(item) for item in claim.get("evidence_ids") or []]
        evidence = [evidence_index[item] for item in evidence_ids if item in evidence_index]
        figure_ids = sorted({str(figure_id) for item in evidence for figure_id in item.get("figure_ids") or [] if figure_id})
        for figure_id in figure_ids or [""]:
            figure = figure_index.get(figure_id, {})
            plugin_trace = trace_index.get(figure_id, {})
            analysis_spec_id = str(figure.get("analysis_spec_id") or next((item.get("analysis_spec_id") for item in evidence if item.get("analysis_spec_id")), ""))
            spec = spec_index.get(analysis_spec_id, {})
            rows.append({
                "claim_id": claim.get("section_claim_id"),
                "results_sentence_hash": claim.get("sentence_hash"),
                "figure_id": figure_id or None,
                "panel_ids": list(figure.get("panel_ids") or []),
                "cohort_view_id": figure.get("cohort_view_id") or spec.get("cohort_view_id"),
                "estimand_id": figure.get("estimand_id") or spec.get("estimand_id"),
                "analysis_spec_id": analysis_spec_id or None,
                "run_ids": sorted({str(item.get("run_id")) for item in evidence if item.get("run_id")}),
                "data_plugin_ids": list(plugin_trace.get("data_plugin_ids") or []),
                "method_plugin_ids": list(plugin_trace.get("method_plugin_ids") or []),
                "evidence_ids": evidence_ids,
                "threshold_source": spec.get("threshold_selection") or "analysis_spec",
            })
    issues = []
    for row in rows:
        for field in ("claim_id", "results_sentence_hash", "cohort_view_id", "estimand_id", "analysis_spec_id"):
            if not row.get(field):
                issues.append({"code": f"missing_{field}", "claim_id": row.get("claim_id"), "figure_id": row.get("figure_id")})
    return {
        "schema_version": "dpl.discipline_review_compiler.v1",
        "results_sha256": results_hash,
        "decision": "repair_required" if issues else "pass",
        "claim_inputs": rows,
        "issues": issues,
        "policy": "Discipline rules consume claim-level IDs compiled from the current Results, figure contract, capability trace, analysis spec, run and evidence registry. They are not rerun later with inferred role aliases.",
    }
