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
    if len(figures) < 5:
        issues.append("Fewer than five main reviewable figures are available for the draft evidence package.")
    for item in figures:
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


def _decision_from_report(payload: dict[str, Any]) -> str:
    return str(payload.get("decision") or payload.get("status") or "").strip().lower()


def _workflow_coverage(project_path: Path, run_manifest: dict[str, Any], validity: dict[str, Any]) -> dict[str, bool]:
    acquisition_plan = _read_json(project_path / "data" / "data_acquisition_plan.json", {})
    acquisition_tasks = _read_json(project_path / "data" / "data_acquisition_tasks.json", {})
    inventory = _read_json(project_path / "data" / "data_inventory.json", {})
    quality = _read_json(project_path / "data" / "data_quality_report.json", {})
    feasibility = _read_json(project_path / "data" / "data_feasibility_report.json", {})
    output_files = [_normalise_path(item) for item in run_manifest.get("output_files") or []]
    generated_figures = [_normalise_path(item) for item in run_manifest.get("figures_generated") or []]
    return {
        "data_supplementation": bool(acquisition_plan or acquisition_tasks),
        "data_integration": bool((inventory.get("files") or []) or quality or feasibility),
        "method_analysis": run_manifest.get("status") == "success",
        "figure_production": bool(generated_figures or any(item.startswith("results/figures/") for item in output_files)),
        "result_validity": _decision_from_report(validity) in {"pass", "passed", "conditional_pass"},
    }


def _recommended_next_action(decision: str, issues: list[str], coverage: dict[str, bool]) -> dict[str, str]:
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
        "results/figure_metadata.json",
        "methods/run_manifest.yaml",
        "results/result_validity_report.json",
    ]
    manifest["output_files"] = [CORE_EVIDENCE_JSON, CORE_EVIDENCE_HTML]
    _write_json(manifest_path, manifest)


def assess_core_evidence(project: str | Path) -> dict[str, Any]:
    """Assess whether data, method execution, figures, and validity are ready for human evidence review."""
    state = load_project(project)
    figure_plan = _read_json(state.path / "results" / "figure_plan.json", {})
    figure_metadata = _read_json(state.path / "results" / "figure_metadata.json", {})
    run_manifest = _read_json(state.path / "methods" / "run_manifest.yaml", {})
    validity = _read_json(state.path / "results" / "result_validity_report.json", {})
    figures = _figure_items(figure_plan if isinstance(figure_plan, dict) else {}, figure_metadata if isinstance(figure_metadata, dict) else {})
    issues = _reviewable_figure_issues(state.path, figures)
    coverage = _workflow_coverage(state.path, run_manifest if isinstance(run_manifest, dict) else {}, validity if isinstance(validity, dict) else {})
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
        "issues": issues,
        "recommended_next_action": _recommended_next_action(decision, issues, coverage),
    }
    output_path = state.path / CORE_EVIDENCE_JSON
    _write_json(output_path, report)
    write_html_report(state.path / CORE_EVIDENCE_HTML, _render_markdown(report), title="Core Evidence Report")
    update_stage_status(state.path, "core_evidence", "draft" if decision == "pass" else "failed")
    _set_manifest(state.path)
    return report
