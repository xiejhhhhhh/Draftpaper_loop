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
from .project_state import load_project


class FigureRepairError(RuntimeError):
    """Raised when figure repair planning cannot proceed."""


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def _diagnosis_items(project_path: Path) -> list[dict[str, Any]]:
    payload = _read_json(project_path / "results" / "figure_execution_diagnosis.json", {})
    if not isinstance(payload, dict):
        return []
    return [item for item in payload.get("figures") or [] if isinstance(item, dict)]


def _contracts_by_id(project_path: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(project_path / "results" / "figure_contracts.json", {})
    indexed: dict[str, dict[str, Any]] = {}
    for item in payload.get("contracts") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("storyboard_id") or item.get("figure_id") or "")
        if key:
            indexed[key] = item
    return indexed


def _contract_for(item: dict[str, Any], contracts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    key = str(item.get("storyboard_id") or item.get("figure_id") or "")
    return contracts.get(key, {})


def _render_plan_markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# {title}",
        "",
        f"Status: {payload.get('status')}",
        "",
        "This repair plan keeps research-plan main figures intact. It does not create substitute or downgraded result figures.",
        "",
        "## Tasks",
        "",
    ]
    for task in payload.get("tasks") or []:
        lines.extend([
            f"### {task.get('task_id')}",
            "",
            f"- Figure: `{task.get('storyboard_id')}`",
            f"- Status: `{task.get('status')}`",
            f"- Missing: `{', '.join(task.get('missing') or [])}`",
            f"- Recommended command: `{task.get('recommended_command')}`",
            f"- Agent instruction: {task.get('agent_instruction')}",
            "",
        ])
    if not payload.get("tasks"):
        lines.append("- No matching repair task was found.")
    return "\n".join(lines) + "\n"


def repair_figure_data(project: str | Path) -> dict[str, Any]:
    """Write a data-repair plan for main figures blocked by missing data."""
    state = load_project(project)
    contracts = _contracts_by_id(state.path)
    tasks: list[dict[str, Any]] = []
    for item in _diagnosis_items(state.path):
        status = str(item.get("status") or "")
        if "missing_data" not in status and item.get("recommended_repair") != "repair-figure-data":
            continue
        contract = _contract_for(item, contracts)
        missing = list(item.get("missing_data") or contract.get("required_data") or [])
        storyboard_id = str(item.get("storyboard_id") or contract.get("storyboard_id") or item.get("figure_id") or "")
        tasks.append({
            "task_id": f"data_repair_{len(tasks) + 1}",
            "storyboard_id": storyboard_id,
            "figure_title": contract.get("title") or item.get("title") or storyboard_id,
            "status": "ready_for_agent_data_repair",
            "missing": missing,
            "repair_sources": [
                "existing project data acquisition connectors",
                "public database/API connectors already declared by the discipline module",
                "remote server/API workflows previously configured for the project",
                "user-provided processed tables or result artifacts when raw data cannot be downloaded",
            ],
            "recommended_command": "python -m draftpaper_cli.cli prepare-data-acquisition --project <project>",
            "followup_commands": [
                "python -m draftpaper_cli.cli inventory-data --project <project>",
                "python -m draftpaper_cli.cli assess-data-quality --project <project>",
                "python -m draftpaper_cli.cli assess-data-feasibility --project <project>",
                "python -m draftpaper_cli.cli generate-analysis-code --project <project>",
            ],
            "agent_instruction": (
                "Use the project data-acquisition flow to obtain or integrate the missing data required by this exact main figure. "
                "Do not replace the figure with a weaker visualization; rerun figure execution after data repair."
            ),
        })
    payload = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "policy": "repair_missing_data_before_core_evidence_review",
        "tasks": tasks,
        "next_command": tasks[0]["recommended_command"] if tasks else "python -m draftpaper_cli.cli diagnose-figure-execution --project <project>",
    }
    _write_json(state.path / "results" / "figure_data_repair_plan.json", payload)
    write_html_report(
        state.path / "results" / "figure_data_repair_plan.html",
        _render_plan_markdown("Figure Data Repair Plan", payload),
        title="Figure Data Repair Plan",
    )
    return payload


def repair_figure_method(project: str | Path) -> dict[str, Any]:
    """Write a method-repair plan for main figures blocked by missing method code."""
    state = load_project(project)
    contracts = _contracts_by_id(state.path)
    literature_items = _read_json(state.path / "references" / "literature_items.json", [])
    literature_titles = [
        str(item.get("title") or "")
        for item in literature_items
        if isinstance(item, dict) and item.get("title")
    ][:8]
    tasks: list[dict[str, Any]] = []
    for item in _diagnosis_items(state.path):
        status = str(item.get("status") or "")
        if "missing_method" not in status and item.get("recommended_repair") != "repair-figure-method":
            continue
        contract = _contract_for(item, contracts)
        missing = list(item.get("missing_method") or contract.get("required_method") or [])
        storyboard_id = str(item.get("storyboard_id") or contract.get("storyboard_id") or item.get("figure_id") or "")
        query_terms = " ".join(str(value) for value in missing + [contract.get("title") or "", state.metadata.get("field") or ""]).strip()
        tasks.append({
            "task_id": f"method_repair_{len(tasks) + 1}",
            "storyboard_id": storyboard_id,
            "figure_title": contract.get("title") or item.get("title") or storyboard_id,
            "status": "ready_for_agent_method_repair",
            "missing": missing,
            "github_search_queries": [
                f"{query_terms} research code",
                f"{query_terms} paper implementation",
                f"{query_terms} reproducible analysis",
            ],
            "literature_context_titles": literature_titles,
            "repair_sources": [
                "local discipline method plugins",
                "project-local methods/src and methods/scripts code",
                "public GitHub research-code repositories",
                "paper implementation repositories linked by retrieved literature",
                "Codex-generated project-specific method code when no reusable implementation is available",
            ],
            "recommended_command": "python -m draftpaper_cli.cli generate-analysis-code --project <project>",
            "agent_instruction": (
                "Search for reusable public method implementations or generate project-specific method code for this exact main figure. "
                "The repaired code must produce the contracted figure path and must not substitute a baseline or validation plot for the requested method."
            ),
        })
    payload = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "policy": "repair_missing_method_code_before_core_evidence_review",
        "tasks": tasks,
        "next_command": tasks[0]["recommended_command"] if tasks else "python -m draftpaper_cli.cli diagnose-figure-execution --project <project>",
    }
    _write_json(state.path / "methods" / "figure_method_repair_plan.json", payload)
    write_html_report(
        state.path / "methods" / "figure_method_repair_plan.html",
        _render_plan_markdown("Figure Method Repair Plan", payload),
        title="Figure Method Repair Plan",
    )
    return payload


def diagnose_figure_execution(project: str | Path) -> dict[str, Any]:
    """Return the current figure diagnosis or a minimal not-run report."""
    state = load_project(project)
    payload = _read_json(state.path / "results" / "figure_execution_diagnosis.json", {})
    if isinstance(payload, dict) and payload:
        return payload
    contracts = list(_contracts_by_id(state.path).values())
    payload = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "policy": "run_generate_analysis_code_before_core_evidence_review",
        "figures": [
            {
                "storyboard_id": item.get("storyboard_id"),
                "path": item.get("path"),
                "status": "not_executed",
                "recommended_repair": "generate-analysis-code",
            }
            for item in contracts
        ],
        "next_command": "python -m draftpaper_cli.cli generate-analysis-code --project <project>",
    }
    _write_json(state.path / "results" / "figure_execution_diagnosis.json", payload)
    write_html_report(
        state.path / "results" / "figure_execution_diagnosis.html",
        _render_plan_markdown("Figure Execution Diagnosis", {"status": "written", "tasks": payload["figures"]}),
        title="Figure Execution Diagnosis",
    )
    return payload
