# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Publication-quality figure scoring tied to scientific contracts and runs."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from .project_scaffold import utc_now
from .project_state import load_project


REPORT = "results/scientific_figure_quality_report.json"
MINIMUM_SCORE = 0.95


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _png_dimensions(path: Path) -> tuple[int, int]:
    try:
        header = path.read_bytes()[:24]
    except OSError:
        return 0, 0
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return 0, 0
    return struct.unpack(">II", header[16:24])


def _values(value: object) -> set[str]:
    if isinstance(value, dict):
        raw = value.keys()
    elif isinstance(value, list):
        raw = value
    elif value:
        raw = [value]
    else:
        raw = []
    return {str(item).strip().lower() for item in raw if str(item).strip()}


def assess_scientific_figure_quality(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    contracts_payload = _read_json(state.path / "results" / "figure_contracts.json")
    contracts = contracts_payload.get("main_contracts") or contracts_payload.get("contracts") or []
    metadata = _read_json(state.path / "results" / "figure_metadata.json").get("figures") or []
    traces = _read_json(state.path / "results" / "figure_plugin_trace_report.json").get("figure_checks") or []
    metadata_by_id = {str(item.get("figure_id") or item.get("storyboard_id") or item.get("id") or ""): item for item in metadata if isinstance(item, dict)}
    metadata_by_path = {str(item.get("path") or "").replace("\\", "/"): item for item in metadata if isinstance(item, dict) and item.get("path")}
    trace_by_id = {str(item.get("figure_id") or ""): item for item in traces if isinstance(item, dict)}
    checks = []
    all_issues = []
    for index, contract in enumerate(contracts, start=1):
        if not isinstance(contract, dict) or str(contract.get("manuscript_role") or "main").lower() == "appendix":
            continue
        figure_id = str(contract.get("figure_id") or contract.get("storyboard_id") or contract.get("id") or f"figure_{index:02d}")
        contract_path = str(contract.get("path") or "").replace("\\", "/")
        item = metadata_by_id.get(figure_id) or metadata_by_path.get(contract_path) or {}
        trace = trace_by_id.get(figure_id) or {}
        path = state.path / str(item.get("path") or contract.get("path") or "")
        width, height = _png_dimensions(path)
        issues = []
        artifact_integrity = 1.0 if width and height else 0.0
        if not artifact_integrity:
            issues.append({"kind": "invalid_or_missing_png"})
        legibility = 1.0 if width >= 1200 and height >= 800 and item.get("axis_labels") and item.get("text_elements") else 0.0
        if width < 1200 or height < 800:
            issues.append({"kind": "insufficient_pixel_dimensions", "width": width, "height": height})
        if not item.get("axis_labels") or not item.get("text_elements"):
            issues.append({"kind": "missing_legibility_metadata"})

        required_roles = _values(contract.get("required_variable_roles"))
        observed_roles = _values(item.get("variable_roles")) | _values(item.get("variables"))
        required_outputs = _values(contract.get("required_method_outputs"))
        observed_outputs = _values(item.get("method_outputs")) | _values(item.get("statistics"))
        semantic_complete = bool(contract.get("scientific_question") or contract.get("research_question")) and required_roles <= observed_roles and required_outputs <= observed_outputs
        semantic_alignment = 1.0 if semantic_complete else 0.0
        if not semantic_complete:
            issues.append({
                "kind": "semantic_contract_incomplete",
                "missing_variable_roles": sorted(required_roles - observed_roles),
                "missing_method_outputs": sorted(required_outputs - observed_outputs),
            })

        evidence_reporting = 1.0 if item.get("statistics") and item.get("interpretation_summary") and item.get("publication_ready") else 0.0
        if not evidence_reporting:
            issues.append({"kind": "missing_statistical_or_interpretive_evidence"})
        plugin_trace = 1.0 if trace.get("data_plugin_ids") and trace.get("method_plugin_ids") and trace.get("run_output_event_id") else 0.0
        if not plugin_trace:
            issues.append({"kind": "missing_plugin_run_trace"})

        required_panels = _values(contract.get("required_panels"))
        observed_panels = _values(item.get("panels"))
        panel_completeness = 1.0 if not required_panels or required_panels <= observed_panels else 0.0
        if not panel_completeness:
            issues.append({"kind": "missing_required_panels", "panels": sorted(required_panels - observed_panels)})
        dimensions = {
            "artifact_integrity": artifact_integrity,
            "legibility": legibility,
            "semantic_alignment": semantic_alignment,
            "evidence_reporting": evidence_reporting,
            "plugin_run_trace": plugin_trace,
            "panel_completeness": panel_completeness,
        }
        weights = {"artifact_integrity": 0.15, "legibility": 0.15, "semantic_alignment": 0.25, "evidence_reporting": 0.15, "plugin_run_trace": 0.20, "panel_completeness": 0.10}
        score = round(sum(dimensions[key] * weights[key] for key in weights), 4)
        check = {"figure_id": figure_id, "score": score, "decision": "pass" if score >= MINIMUM_SCORE else "repair_required", "dimensions": dimensions, "issues": issues}
        checks.append(check)
        all_issues.extend({**issue, "figure_id": figure_id} for issue in issues)
    score = round(sum(item["score"] for item in checks) / max(1, len(checks)), 4)
    report = {
        "status": "written",
        "schema_version": "v0.21.0",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "score": score,
        "minimum_score": MINIMUM_SCORE,
        "decision": "pass" if checks and all(item["decision"] == "pass" for item in checks) else "repair_required",
        "figure_checks": checks,
        "issues": all_issues,
        "policy": "A valid PNG is necessary but insufficient; publication readiness requires semantic, plugin-run, panel, statistical, and legibility evidence.",
    }
    _write_json(state.path / REPORT, report)
    return report
