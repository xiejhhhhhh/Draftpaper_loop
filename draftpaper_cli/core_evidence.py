# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .passport import utc_now
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


CORE_EVIDENCE_JSON = "core_evidence/core_evidence_report.json"
CORE_EVIDENCE_HTML = "core_evidence/core_evidence_report.html"
FIGURE_CONTRACTS_JSON = "results/figure_contracts.json"
FIGURE_EXECUTION_DIAGNOSIS_JSON = "results/figure_execution_diagnosis.json"


class CoreEvidenceError(RuntimeError):
    """Raised when core empirical evidence cannot be assessed."""


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def _normalise_path(value: Any) -> str:
    return str(value or "").replace("\\", "/")


def _figure_items(figure_plan: dict[str, Any], figure_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    plan_by_path = {
        _normalise_path(item.get("path")): item
        for item in figure_plan.get("figures") or []
        if item.get("path")
    }
    items: list[dict[str, Any]] = []
    for metadata in figure_metadata.get("figures") or []:
        path = _normalise_path(metadata.get("path"))
        if not path:
            continue
        plan = plan_by_path.get(path, {})
        items.append({
            "figure_id": metadata.get("figure_id") or plan.get("figure_id") or path,
            "storyboard_id": metadata.get("storyboard_id") or plan.get("storyboard_id") or plan.get("id") or "",
            "figure_role": plan.get("figure_role") or metadata.get("figure_role") or "main_result",
            "path": path,
            "title": metadata.get("title") or plan.get("title") or "",
            "caption": metadata.get("caption") or plan.get("caption_draft") or "",
            "scientific_question": plan.get("scientific_question") or "",
            "interpretation_summary": metadata.get("interpretation_summary") or "",
            "has_axes": bool(metadata.get("has_axes")),
            "axis_labels": metadata.get("axis_labels") or {},
            "publication_ready": bool(metadata.get("publication_ready")),
        })
    if not items:
        for plan in figure_plan.get("figures") or []:
            path = _normalise_path(plan.get("path"))
            if not path:
                continue
            items.append({
                "figure_id": plan.get("figure_id") or path,
                "path": path,
                "title": plan.get("title") or "",
                "caption": plan.get("caption_draft") or "",
                "scientific_question": plan.get("scientific_question") or "",
                "interpretation_summary": plan.get("result_claim_template") or "",
                "has_axes": False,
                "axis_labels": {},
                "publication_ready": False,
            })
    return items


def _reviewable_figure_issues(project_path: Path, figures: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    main_figures = [item for item in figures if item.get("figure_role") != "supporting"]
    if len(main_figures) < 5:
        issues.append("Fewer than five main reviewable figures are available for the draft evidence package.")
    for item in main_figures:
        path_text = _normalise_path(item.get("path"))
        if not path_text:
            issues.append("A figure metadata entry is missing its path.")
            continue
        if not (project_path / path_text).exists():
            issues.append(f"{path_text} does not exist.")
        if not item.get("title") and not item.get("caption"):
            issues.append(f"{path_text} lacks a title or caption.")
        if not item.get("interpretation_summary"):
            issues.append(f"{path_text} lacks an interpretation summary.")
        if not item.get("has_axes"):
            issues.append(f"{path_text} does not confirm axes or a scientific scale.")
        if not item.get("axis_labels"):
            issues.append(f"{path_text} does not declare axis labels.")
        if not item.get("publication_ready"):
            issues.append(f"{path_text} is not marked publication_ready in figure metadata.")
    return issues


def _diagnosis_by_storyboard(diagnosis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in diagnosis.get("figures") or []:
        if not isinstance(item, dict):
            continue
        key = _normalise_path(item.get("storyboard_id") or item.get("figure_id") or item.get("path"))
        if key:
            indexed[key] = item
    return indexed


def _figure_contract_coverage(
    project_path: Path,
    *,
    contracts_payload: dict[str, Any],
    figure_plan: dict[str, Any],
    figure_metadata: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    contracts = [item for item in contracts_payload.get("contracts") or [] if isinstance(item, dict)]
    metadata_paths = {_normalise_path(item.get("path")) for item in figure_metadata.get("figures") or [] if item.get("path")}
    metadata_storyboard_ids = {
        _normalise_path(item.get("storyboard_id") or item.get("figure_id"))
        for item in figure_metadata.get("figures") or []
        if item.get("storyboard_id") or item.get("figure_id")
    }
    plan_supporting_paths = {
        _normalise_path(item.get("path"))
        for item in figure_plan.get("figures") or []
        if item.get("figure_role") == "supporting" and item.get("path")
    }
    diagnosis_index = _diagnosis_by_storyboard(diagnosis)
    missing: list[dict[str, Any]] = []
    satisfied: list[dict[str, Any]] = []
    substituted: list[dict[str, Any]] = []
    for contract in contracts:
        path = _normalise_path(contract.get("path"))
        storyboard_id = _normalise_path(contract.get("storyboard_id") or contract.get("figure_id"))
        path_exists = bool(path and (project_path / path).exists())
        metadata_exists = path in metadata_paths or storyboard_id in metadata_storyboard_ids
        if path in plan_supporting_paths:
            substituted.append({"storyboard_id": storyboard_id, "path": path, "reason": "main_contract_path_marked_supporting"})
        if path_exists and metadata_exists and path not in plan_supporting_paths:
            satisfied.append({"storyboard_id": storyboard_id, "path": path})
            continue
        diagnostic = diagnosis_index.get(storyboard_id) or diagnosis_index.get(path) or {}
        missing.append({
            "storyboard_id": storyboard_id,
            "title": contract.get("title"),
            "path": path,
            "required_data": contract.get("required_data") or [],
            "required_method": contract.get("required_method") or [],
            "diagnosis_status": diagnostic.get("status") or "not_executed",
            "recommended_repair": diagnostic.get("recommended_repair") or (
                "repair-figure-method"
                if "missing_method" in str(diagnostic.get("status") or "")
                else "repair-figure-data"
                if "missing_data" in str(diagnostic.get("status") or "") or contract.get("required_data")
                else "repair-figure-method"
            ),
        })
    return {
        "contract_count": len(contracts),
        "satisfied_count": len(satisfied),
        "missing_count": len(missing),
        "substituted_count": len(substituted),
        "all_main_contracts_satisfied": bool(contracts) and not missing and not substituted,
        "satisfied_contracts": satisfied,
        "missing_contracts": missing,
        "substituted_contracts": substituted,
    }


def _decision_from_report(payload: dict[str, Any]) -> str:
    return str(payload.get("decision") or payload.get("status") or "").strip().lower()


def _workflow_coverage(project_path: Path, run_manifest: dict[str, Any], validity: dict[str, Any]) -> dict[str, bool]:
    acquisition_plan = _read_json(project_path / "data" / "data_acquisition_plan.json", {})
    acquisition_tasks = _read_json(project_path / "data" / "data_acquisition_tasks.json", {})
    inventory = _read_json(project_path / "data" / "data_inventory.json", {})
    quality = _read_json(project_path / "data" / "data_quality_report.json", {})
    feasibility = _read_json(project_path / "data" / "data_feasibility_report.json", {})
    support = _read_json(project_path / "results" / "result_support_checkpoint.json", {})
    output_files = [_normalise_path(item) for item in run_manifest.get("output_files") or []]
    generated_figures = [_normalise_path(item) for item in run_manifest.get("figures_generated") or []]
    return {
        "data_supplementation": bool(acquisition_plan or acquisition_tasks),
        "data_integration": bool((inventory.get("files") or []) or quality or feasibility),
        "method_analysis": run_manifest.get("status") == "success",
        "figure_production": bool(generated_figures or any(item.startswith("results/figures/") for item in output_files)),
        "result_validity": _decision_from_report(validity) in {"pass", "passed", "conditional_pass"},
        "result_support": _decision_from_report(support) in {"pass", "passed"},
    }


def _recommended_next_action(
    decision: str,
    issues: list[str],
    coverage: dict[str, bool],
    contract_coverage: dict[str, Any] | None = None,
) -> dict[str, str]:
    if decision == "pass":
        return {
            "command": "checkpoint",
            "reason": "Core figures and result evidence are ready for user review before manuscript writing continues.",
        }
    if not coverage.get("data_supplementation") or not coverage.get("data_integration"):
        return {
            "command": "prepare-data-acquisition",
            "reason": "Data supplementation or integration evidence is incomplete.",
        }
    contract_coverage = contract_coverage or {}
    missing_contracts = contract_coverage.get("missing_contracts") or []
    if missing_contracts:
        statuses = " ".join(str(item.get("diagnosis_status") or "") for item in missing_contracts)
        if "missing_data" in statuses or any(item.get("recommended_repair") == "repair-figure-data" for item in missing_contracts):
            return {
                "command": "repair-figure-data",
                "reason": "At least one research-plan main figure is blocked by missing data; run the data acquisition/integration repair loop before changing the figure claim.",
            }
        if "missing_method" in statuses or any(item.get("recommended_repair") == "repair-figure-method" for item in missing_contracts):
            return {
                "command": "repair-figure-method",
                "reason": "At least one research-plan main figure is blocked by missing method code; search/reuse/generate method code before changing the figure claim.",
            }
        return {
            "command": "diagnose-figure-execution",
            "reason": "Research-plan main figure contracts are not satisfied; diagnose whether data or method repair is required.",
        }
    if not coverage.get("method_analysis"):
        return {
            "command": "verify-methods",
            "reason": "Method code has not produced a successful run manifest.",
        }
    if not coverage.get("figure_production"):
        return {
            "command": "generate-analysis-code",
            "reason": "The pipeline has not produced reviewable result figures.",
        }
    if not coverage.get("result_validity"):
        return {
            "command": "assess-result-validity",
            "reason": "Result validity has not passed or conditionally passed.",
        }
    if not coverage.get("result_support"):
        return {
            "command": "assess-result-support",
            "reason": "Result support has not passed; decide whether to downgrade claims or supplement data/method evidence before manuscript writing.",
        }
    return {
        "command": "plan-figures",
        "reason": issues[0] if issues else "Core evidence needs revision before user confirmation.",
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Core Evidence Report",
        "",
        f"Decision: {report.get('decision')}",
        "",
        "## Workflow Coverage",
        "",
    ]
    for key, value in (report.get("workflow_coverage") or {}).items():
        lines.append(f"- {key}: {'yes' if value else 'no'}")
    lines.extend(["", "## Reviewable Figures", ""])
    for item in report.get("reviewable_figures") or []:
        title = item.get("title") or item.get("caption") or item.get("path")
        lines.append(f"- {title}: {item.get('path')}")
        if item.get("interpretation_summary"):
            lines.append(f"  - Interpretation: {item.get('interpretation_summary')}")
    lines.extend(["", "## Issues", ""])
    if report.get("issues"):
        lines.extend(f"- {issue}" for issue in report["issues"])
    else:
        lines.append("- No blocking evidence issue was detected. Human figure review is still required.")
    next_action = report.get("recommended_next_action") or {}
    lines.extend(["", "## Recommended Next Action", "", f"{next_action.get('command')}: {next_action.get('reason')}"])
    coverage = report.get("figure_contract_coverage") or {}
    if coverage:
        lines.extend([
            "",
            "## Figure Contract Coverage",
            "",
            f"- Contracts: {coverage.get('contract_count')}",
            f"- Satisfied: {coverage.get('satisfied_count')}",
            f"- Missing: {coverage.get('missing_count')}",
            f"- Substituted: {coverage.get('substituted_count')}",
        ])
        for item in coverage.get("missing_contracts") or []:
            lines.append(f"- Missing contract `{item.get('storyboard_id')}`: {item.get('diagnosis_status')} -> {item.get('recommended_repair')}")
    return "\n".join(lines) + "\n"


def _set_manifest(project_path: Path) -> None:
    manifest_path = project_path / "core_evidence" / "stage_manifest.json"
    manifest = _read_json(manifest_path, {})
    if not isinstance(manifest, dict):
        return
    manifest["input_files"] = [
        "data/data_acquisition_plan.json",
        "data/data_inventory.json",
        "data/data_quality_report.json",
        "data/data_feasibility_report.json",
        "results/figure_plan.json",
        FIGURE_CONTRACTS_JSON,
        FIGURE_EXECUTION_DIAGNOSIS_JSON,
        "results/figure_metadata.json",
        "results/figure_semantic_validation_report.json",
        "methods/run_manifest.yaml",
        "results/result_validity_report.json",
        "results/result_support_checkpoint.json",
    ]
    manifest["output_files"] = [CORE_EVIDENCE_JSON, CORE_EVIDENCE_HTML]
    _write_json(manifest_path, manifest)


def assess_core_evidence(project: str | Path) -> dict[str, Any]:
    """Assess whether data, method execution, figures, and validity are ready for human evidence review."""
    state = load_project(project)
    figure_plan = _read_json(state.path / "results" / "figure_plan.json", {})
    figure_metadata = _read_json(state.path / "results" / "figure_metadata.json", {})
    contracts_payload = _read_json(state.path / FIGURE_CONTRACTS_JSON, {})
    diagnosis = _read_json(state.path / FIGURE_EXECUTION_DIAGNOSIS_JSON, {})
    semantic_report = _read_json(state.path / "results" / "figure_semantic_validation_report.json", {})
    run_manifest = _read_json(state.path / "methods" / "run_manifest.yaml", {})
    validity = _read_json(state.path / "results" / "result_validity_report.json", {})
    figures = _figure_items(figure_plan if isinstance(figure_plan, dict) else {}, figure_metadata if isinstance(figure_metadata, dict) else {})
    issues = _reviewable_figure_issues(state.path, figures)
    coverage = _workflow_coverage(state.path, run_manifest if isinstance(run_manifest, dict) else {}, validity if isinstance(validity, dict) else {})
    contract_coverage = _figure_contract_coverage(
        state.path,
        contracts_payload=contracts_payload if isinstance(contracts_payload, dict) else {},
        figure_plan=figure_plan if isinstance(figure_plan, dict) else {},
        figure_metadata=figure_metadata if isinstance(figure_metadata, dict) else {},
        diagnosis=diagnosis if isinstance(diagnosis, dict) else {},
    )
    for item in contract_coverage.get("missing_contracts") or []:
        issues.append(
            f"Research-plan main figure contract is not satisfied: {item.get('storyboard_id')} ({item.get('diagnosis_status')})."
        )
    for item in contract_coverage.get("substituted_contracts") or []:
        issues.append(
            f"Research-plan main figure contract appears substituted by a supporting figure: {item.get('storyboard_id')}."
        )
    if str((semantic_report or {}).get("decision") or "").lower() == "blocked":
        issues.append("At least one rendered figure fails its semantic scientific contract.")
    for label, covered in coverage.items():
        if not covered:
            issues.append(f"Workflow coverage missing: {label}.")
    decision = "pass" if not issues else "revise_required"
    report = {
        "status": "written",
        "project_id": state.metadata.get("project_id"),
        "generated_at": utc_now(),
        "decision": decision,
        "evidence_ready_for_manuscript": decision == "pass",
        "requires_user_confirmation": True,
        "figure_count": len(figures),
        "reviewable_figures": figures,
        "workflow_coverage": coverage,
        "figure_contract_coverage": contract_coverage,
        "figure_semantic_validation": semantic_report,
        "issues": issues,
        "recommended_next_action": _recommended_next_action(decision, issues, coverage, contract_coverage),
    }
    output_path = state.path / CORE_EVIDENCE_JSON
    _write_json(output_path, report)
    write_html_report(state.path / CORE_EVIDENCE_HTML, _render_markdown(report), title="Core Evidence Report")
    update_stage_status(state.path, "core_evidence", "draft" if decision == "pass" else "failed")
    _set_manifest(state.path)
    return report
