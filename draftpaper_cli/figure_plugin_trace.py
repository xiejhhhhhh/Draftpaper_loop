# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Trace main figure contracts through claims, plugins, runs, and review rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import utc_now
from .project_state import load_project
from .plugin_catalog import build_plugin_catalog_snapshot


TRACE_JSON = "results/figure_plugin_trace_report.json"
TRACE_HTML = "results/figure_plugin_trace_report.html"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _main_figures(contracts: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("main_contracts", "contracts", "figures"):
        values = contracts.get(key)
        if isinstance(values, list):
            return [item for item in values if isinstance(item, dict) and str(item.get("manuscript_role") or "main").lower() != "appendix"]
    return []


def _figure_id(item: dict[str, Any], index: int) -> str:
    return str(item.get("figure_id") or item.get("storyboard_id") or item.get("id") or f"figure_{index:02d}")


def _render(report: dict[str, Any]) -> str:
    lines = ["# Figure Plugin Trace Report", "", f"Decision: `{report.get('decision')}`", ""]
    for check in report.get("figure_checks") or []:
        lines.append(f"- `{check.get('figure_id')}`: **{check.get('decision')}**")
        for issue in check.get("issues") or []:
            lines.append(f"  - `{issue.get('kind')}`: {issue.get('detail')}")
    return "\n".join(lines)


def validate_figure_plugin_trace(project: str | Path) -> dict[str, Any]:
    """Validate planned and completed trace chains for every main figure.

    ``ready_for_codegen`` means executable data and method bindings exist and
    permits analysis-code generation. Claims remain auditable provenance and
    review rules are selected only after Results exist. ``pass`` additionally
    requires a real project method run output.
    """
    state = load_project(project)
    capabilities = _read_json(state.path / "research_plan" / "research_capability_contract.json")
    contracts = _read_json(state.path / "results" / "figure_contracts.json")
    binding_plan = _read_json(state.path / "research_plan" / "plugin_binding_plan.json")
    bindings = binding_plan.get("bindings") or []
    catalog_snapshot = build_plugin_catalog_snapshot()
    run_manifest = _read_json(state.path / "methods" / "run_manifest.yaml")
    events = _read_jsonl(state.path / "data" / "plugin_execution_ledger.jsonl") + _read_jsonl(state.path / "methods" / "plugin_execution_ledger.jsonl")
    figure_requirements = {
        str(item.get("figure_id")): item
        for item in capabilities.get("requirements") or []
        if isinstance(item, dict) and item.get("kind") == "figure" and item.get("core")
    }
    capability_requirements_by_figure: dict[str, list[dict[str, Any]]] = {}
    for item in capabilities.get("requirements") or []:
        if not isinstance(item, dict) or item.get("kind") not in {"data", "method"} or not item.get("core"):
            continue
        capability_requirements_by_figure.setdefault(str(item.get("figure_id") or ""), []).append(item)
    checks = []
    for index, contract in enumerate(_main_figures(contracts), start=1):
        figure_id = _figure_id(contract, index)
        requirement = figure_requirements.get(figure_id) or {}
        bound = [
            item for item in bindings
            if isinstance(item, dict)
            and item.get("figure_id") == figure_id
            and item.get("state") in {"covered", "covered_project_local"}
        ]
        data_ids = [str(item.get("plugin_id")) for item in bound if item.get("kind") == "data" and item.get("plugin_id")]
        method_ids = [str(item.get("plugin_id")) for item in bound if item.get("kind") == "method" and item.get("plugin_id")]
        review_ids = [str(item.get("plugin_id")) for item in bound if item.get("kind") == "review" and item.get("plugin_id")]
        bound_requirement_ids = {str(item.get("requirement_id")) for item in bound if item.get("requirement_id")}
        expected_capabilities = capability_requirements_by_figure.get(figure_id) or []
        issues = []
        claim_ids = [str(item) for item in requirement.get("claim_ids") or []]
        warnings = []
        if not claim_ids:
            warnings.append({"kind": "missing_research_plan_claim", "detail": "No main-figure claim is bound; repair provenance before final Results acceptance."})
        expected_data = [
            item
            for item in expected_capabilities
            if item.get("kind") == "data" and item.get("data_role_class") != "derived_method_output"
        ]
        expected_methods = [item for item in expected_capabilities if item.get("kind") == "method"]
        missing_data_requirements = [item for item in expected_data if str(item.get("requirement_id")) not in bound_requirement_ids]
        missing_method_requirements = [item for item in expected_methods if str(item.get("requirement_id")) not in bound_requirement_ids]
        for item in missing_data_requirements:
            issues.append({
                "kind": "missing_data_plugin_requirement",
                "requirement_id": str(item.get("requirement_id")),
                "detail": "A contracted data capability has no covered binding for this figure.",
            })
        for item in missing_method_requirements:
            issues.append({
                "kind": "missing_method_plugin_requirement",
                "requirement_id": str(item.get("requirement_id")),
                "detail": "A contracted method capability has no covered binding for this figure.",
            })
        has_only_derived_data = bool(
            [
                item
                for item in expected_capabilities
                if item.get("kind") == "data" and item.get("data_role_class") == "derived_method_output"
            ]
        )
        if not expected_data and not data_ids and not has_only_derived_data:
            issues.append({"kind": "missing_data_plugin_binding", "detail": "No covered data plugin is bound to this main figure."})
        if not expected_methods and not method_ids:
            issues.append({"kind": "missing_method_plugin_binding", "detail": "No covered method plugin is bound to this main figure."})
        method_events = [item for item in events if item.get("figure_id") == figure_id and item.get("plugin_id") in method_ids]
        real_event = next((
            item for item in reversed(method_events)
            if item.get("status") == "project_executed" and item.get("scientific_evidence_status") == "project_result"
        ), None)
        run_success = str(run_manifest.get("status") or "").lower() == "success"
        if not issues and not (real_event and run_success):
            decision = "ready_for_codegen"
        elif issues:
            decision = "capability_rescue_required"
        else:
            decision = "pass"
        checks.append({
            "figure_id": figure_id,
            "decision": decision,
            "claim_ids": claim_ids,
            "data_plugin_ids": data_ids,
            "method_plugin_ids": method_ids,
            "review_rule_ids": review_ids,
            "run_output_event_id": real_event.get("event_id") if real_event else None,
            "run_manifest_status": run_manifest.get("status"),
            "issues": issues,
            "warnings": warnings,
        })
    decision = "capability_rescue_required" if any(item["decision"] == "capability_rescue_required" for item in checks) else ("pass" if checks and all(item["decision"] == "pass" for item in checks) else "ready_for_codegen")
    if binding_plan.get("plugin_catalog_hash") and binding_plan.get("plugin_catalog_hash") != catalog_snapshot.get("catalog_hash"):
        decision = "capability_rescue_required"
        checks.append({"figure_id": "catalog", "decision": "capability_rescue_required", "issues": [{"kind": "plugin_catalog_drift", "detail": "The plugin catalog changed after capability binding."}]})
    report = {"status": "written", "generated_at": utc_now(), "project_id": state.metadata.get("project_id"), "decision": decision, "plugin_catalog_hash": catalog_snapshot.get("catalog_hash"), "binding_catalog_hash": binding_plan.get("plugin_catalog_hash"), "figure_checks": checks, "policy": "Data and method plugins gate code generation. Claim provenance and applicable review rules are repaired or assessed after Results; fixture events never count as scientific run output."}
    _write_json(state.path / TRACE_JSON, report)
    write_html_report(state.path / TRACE_HTML, _render(report), title="Figure Plugin Trace Report")
    return report
