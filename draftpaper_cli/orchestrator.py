# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .evidence_snapshot import (
    EvidenceSnapshotMismatch,
    create_evidence_snapshot,
    evidence_confirmation_subject,
)
from .passport import (
    PASSPORT_FILES,
    PassportError,
    append_checkpoint_event,
    load_project_passport,
    project_root,
    read_jsonl,
    refresh_project_passport,
    utc_now,
)
from .project_scaffold import STAGE_ORDER
from .project_state import ProjectStateError, load_project
from .stale_sync import detect_artifact_drift
from .artifact_repository import ArtifactRepository
from .writing_coordinator import (
    SECTION_STAGE_MAP as COORDINATED_SECTION_STAGE_MAP,
    formal_writing_release_action as coordinated_formal_release_action,
    section_lifecycle_action as coordinated_section_lifecycle_action,
)


COMPLETE_STATUSES = {"draft", "approved", "completed"}
BACKFILL_COMPATIBLE_STAGES = {"research_feasibility", "research_plan_feasibility", "method_feasibility", "figure_contracts"}

STAGE_COMMANDS = {
    "references": "search-literature",
    "journal_profile": "resolve-journal-template",
    "research_feasibility": "preflight-research-feasibility",
    "research_plan": "generate-plan",
    "research_plan_feasibility": "assess-research-plan-feasibility",
    "data": "inventory-data",
    "method_plan": "collect-method-plan",
    "method_feasibility": "assess-method-feasibility",
    "figure_plan": "plan-figures",
    "figure_contracts": "assess-figure-contracts",
    "code": "generate-analysis-code",
    "methods": "verify-methods",
    "result_validity": "assess-result-validity",
    "result_support": "assess-result-support",
    "core_evidence": "assess-core-evidence",
    "results": "inventory-results",
    "introduction": "write-introduction",
    "data_writing": "build-data-context",
    "methods_writing": "build-method-context",
    "discussion": "write-discussion",
    "latex": "assemble-latex",
    "quality_checks": "quality-check",
}

MINIMUM_STAGE_OUTPUTS = {
    "research_feasibility": [
        "research_plan/research_preflight_feasibility.json",
        "research_plan/research_preflight_feasibility.html",
    ],
    "research_plan_feasibility": [
        "research_plan/research_plan_feasibility_report.json",
        "research_plan/research_plan_feasibility_report.html",
        "research_plan/research_degradation_options.json",
        "research_plan/research_plan_revision_suggestions.json",
        "research_plan/research_plan_revision_suggestions.md",
        "research_plan/research_scope_decision.json",
    ],
    "method_feasibility": [
        "methods/method_feasibility_report.json",
        "methods/method_feasibility_report.html",
        "methods/method_repair_plan.json",
        "methods/method_degradation_options.json",
    ],
    "figure_contracts": [
        "results/figure_contract_gate_report.json",
        "results/figure_contract_gate_report.html",
    ],
    "data": [
        "data/data_acquisition_plan.json",
        "data/data_inventory.json",
        "data/data_quality_report.json",
        "data/data_feasibility_report.json",
    ],
    "data_writing": [
        "data/data_writing_context.json",
        "data/data.tex",
    ],
    "methods": [
        "methods/run_manifest.yaml",
    ],
    "methods_writing": [
        "methods/method_writing_context.json",
        "methods/methods.tex",
    ],
    "core_evidence": [
        "core_evidence/core_evidence_report.json",
        "core_evidence/core_evidence_report.html",
    ],
    "result_support": [
        "results/result_support_checkpoint.json",
        "results/result_support_checkpoint.md",
        "results/result_support_checkpoint.html",
    ],
    "results": [
        "results/result_manifest.yaml",
        "results/results.tex",
        "results/results_summary_zh.md",
    ],
}


class OrchestratorError(RuntimeError):
    """Raised when the pipeline orchestrator cannot resolve a legal next action."""


def _stage_declared_outputs_current(project_path: Path, stage: str) -> bool:
    manifest_path = project_path / stage / "stage_manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return False
    output_files = list(manifest.get("output_files") or [])
    for relative in MINIMUM_STAGE_OUTPUTS.get(stage, []):
        if relative not in output_files:
            output_files.append(relative)
    for relative in output_files:
        if not (project_path / str(relative)).exists():
            return False
    return True


def _stage_is_current(project_path: Path, stage: str, stage_meta: dict[str, Any]) -> bool:
    return (
        stage_meta.get("status") in COMPLETE_STATUSES
        and not stage_meta.get("stale")
        and _stage_declared_outputs_current(project_path, stage)
    )


def _quote(path: Path) -> str:
    text = str(path)
    return f'"{text}"' if " " in text else text


def _cli_for(project_path: Path, command: str) -> str:
    return f"python -m draftpaper_cli.cli {command} --project {_quote(project_path)}"


def _review_execution_action(project_path: Path, prefix: str) -> dict[str, Any] | None:
    if not (project_path / "review" / "actionable_analysis_tasks.json").exists():
        return None
    if not (project_path / "data" / "data_acquisition_tasks.json").exists():
        return {
            "stage": "data",
            "command": "prepare-data-acquisition",
            "cli": _cli_for(project_path, "prepare-data-acquisition"),
            "reason": f"{prefix}; reviewer/rescue analysis tasks exist and missing-data requests need connector-aware acquisition tasks.",
        }
    if not (project_path / "methods" / "method_blueprint.json").exists():
        return {
            "stage": "method_plan",
            "command": "prepare-method-blueprint",
            "cli": _cli_for(project_path, "prepare-method-blueprint"),
            "reason": f"{prefix}; reviewer/rescue tasks need a method blueprint before revised figure contracts are executed.",
        }
    if not (project_path / "methods" / "method_feasibility_report.json").exists():
        return {
            "stage": "method_feasibility",
            "command": "assess-method-feasibility",
            "cli": _cli_for(project_path, "assess-method-feasibility"),
            "reason": f"{prefix}; reviewer/rescue method support must be checked before revised figure contracts are executed.",
        }
    figure_plan = _read_report(project_path, "results/figure_plan.json")
    if not figure_plan.get("used_review_tasks"):
        return {
            "stage": "figure_plan",
            "command": "plan-figures",
            "cli": _cli_for(project_path, "plan-figures") + " --use-review-tasks",
            "reason": f"{prefix}; reviewer/rescue tasks exist and need a revised figure plan.",
        }
    if not (project_path / "results" / "figure_contract_gate_report.json").exists():
        return {
            "stage": "figure_contracts",
            "command": "assess-figure-contracts",
            "cli": _cli_for(project_path, "assess-figure-contracts"),
            "reason": f"{prefix}; revised main figures need a passing or conditional figure-contract gate before code generation.",
        }
    analysis_manifest = _read_report(project_path, "methods/method_code_manifest.json") or _read_report(project_path, "methods/analysis_code_manifest.json")
    coverage = analysis_manifest.get("review_task_coverage") or {}
    if not coverage.get("enabled"):
        return {
            "stage": "code",
            "command": "generate-analysis-code",
            "cli": _cli_for(project_path, "generate-analysis-code") + " --use-review-tasks",
            "reason": f"{prefix}; the revised figure plan needs review-task-aware analysis code.",
        }
    run_manifest = _read_report(project_path, "methods/run_manifest.yaml")
    if "review_task_coverage_issues" not in run_manifest:
        outputs = " ".join(f"--output {relative}" for relative in analysis_manifest.get("declared_outputs") or [])
        cli = (
            _cli_for(project_path, "verify-methods")
            + ' --command "python code/scripts/run_analysis.py"'
            + (f" {outputs}" if outputs else "")
        )
        return {
            "stage": "methods",
            "command": "verify-methods",
            "cli": cli,
            "reason": f"{prefix}; generated reviewer-rescue analysis code must be run and checked for task coverage.",
        }
    validity = _read_report(project_path, "results/result_validity_report.json")
    if "review_task_coverage_issues" not in validity:
        return {
            "stage": "result_validity",
            "command": "assess-result-validity",
            "cli": _cli_for(project_path, "assess-result-validity"),
            "reason": f"{prefix}; verified review-task-aware outputs need result-validity assessment.",
        }
    return None


def _integrity_is_current(project_path: Path) -> bool:
    report_path = project_path / "integrity" / "integrity_report.json"
    if not report_path.exists():
        return False
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return False
    return isinstance(report, dict) and report.get("status") == "passed"


def _read_report(project_path: Path, relative: str) -> dict[str, Any]:
    return ArtifactRepository(project_path).read_mapping(relative)


def _plugin_execution_failures(project_path: Path) -> list[dict[str, Any]]:
    failures = []
    for relative in ["data/plugin_execution_ledger.jsonl", "methods/plugin_execution_ledger.jsonl"]:
        for event in read_jsonl(project_path / relative):
            if str(event.get("status") or "") == "execution_failed":
                failures.append(event)
    return failures


def _result_support_action(project_path: Path, result_support: dict[str, Any]) -> dict[str, Any] | None:
    decision = str(result_support.get("decision") or "")
    if decision == "pass":
        return None
    selected_route = str(result_support.get("selected_route") or "")
    if decision == "supplement_prepared" or selected_route == "supplement_data_and_method":
        rescue = _read_report(project_path, "review/result_rescue_plan.json")
        next_commands = list(rescue.get("recommended_next_commands") or [])
        return {
            "stage": "result_support",
            "command": "continue-result-rescue",
            "cli": next_commands[0] if next_commands else _cli_for(project_path, "prepare-data-acquisition"),
            "reason": "Supplement route is selected; reopen data/method/figure evidence and rerun result support after the rescue tasks are executed.",
            "selected_route": "supplement_data_and_method",
            "result_rescue_plan": "review/result_rescue_plan.json" if rescue else result_support.get("result_rescue_plan"),
            "recommended_next_commands": next_commands,
        }
    route_options = result_support.get("route_options") or []
    if not route_options:
        route_options = [
            {
                "route": "downgrade_research_claim",
                "current_executable_command": _cli_for(project_path, "apply-result-downgrade"),
                "stale_policy": "stale manuscript and claim boundary only; keep current result artifacts frozen",
            },
            {
                "route": "supplement_data_and_method",
                "current_executable_command": _cli_for(project_path, "prepare-result-rescue"),
                "stale_policy": "stale data, method, figure, evidence, and manuscript chain before rerunning results",
            },
        ]
    return {
        "stage": "result_support",
        "command": "choose-result-route",
        "cli": None,
        "reason": "Current figures and metrics do not fully support the research-plan claims; choose claim downgrade or data/method supplementation before manuscript writing continues.",
        "requires_user_decision": True,
        "route_options": route_options,
    }


def _gate_failure_action(project_path: Path) -> dict[str, Any] | None:
    research_plan = project_path / "research_plan" / "research_plan.md"
    discipline_contract = project_path / "research_plan" / "discipline_contract.json"
    sufficiency_report = _read_report(project_path, "research_plan/plugin_sufficiency_report.json")
    capability_contract_path = project_path / "research_plan" / "research_capability_contract.json"
    if capability_contract_path.exists():
        current_capability_hash = hashlib.sha256(capability_contract_path.read_bytes()).hexdigest()
        if sufficiency_report.get("research_capability_contract_sha256") != current_capability_hash:
            sufficiency_report = {}
    capability_inputs_present = (project_path / "research_plan" / "claim_contract.json").exists() or (project_path / "research_plan" / "figure_storyboard.json").exists()
    stage_state = (load_project(project_path).metadata.get("stages") or {})
    data_meta = stage_state.get("data") or {}
    method_plan_meta = stage_state.get("method_plan") or {}
    capability_assessment_ready = (
        data_meta.get("status") in COMPLETE_STATUSES
        and not data_meta.get("stale")
        and method_plan_meta.get("status") in COMPLETE_STATUSES
        and not method_plan_meta.get("stale")
    )
    if research_plan.exists() and capability_inputs_present and not discipline_contract.exists():
        return {
            "stage": "research_plan",
            "command": "resolve-research-capabilities",
            "cli": _cli_for(project_path, "resolve-research-capabilities"),
            "reason": "The final research plan needs an explicit discipline and capability contract before data/method execution.",
        }
    if discipline_contract.exists() and capability_inputs_present and not sufficiency_report and capability_assessment_ready:
        return {
            "stage": "research_plan",
            "command": "assess-plugin-sufficiency",
            "cli": _cli_for(project_path, "assess-plugin-sufficiency"),
            "reason": "Planned core figures need structured data/method/runtime plugin sufficiency assessment before execution.",
        }
    if sufficiency_report.get("decision") == "project_implementation_required":
        audit_report = _read_report(project_path, "research_plan/project_capability_audit.json")
        if not audit_report or (
            audit_report.get("research_capability_contract_sha256")
            != sufficiency_report.get("research_capability_contract_sha256")
            or audit_report.get("source_sufficiency_generated_at") != sufficiency_report.get("generated_at")
        ):
            return {
                "stage": "research_plan",
                "command": "audit-project-capabilities",
                "cli": _cli_for(project_path, "audit-project-capabilities"),
                "reason": "Before generating new code, audit the apparent gap against current stage-owned project data and method assets.",
            }
        method_ids = list(audit_report.get("project_method_implementation_required") or [])
        data_ids = list(audit_report.get("project_data_implementation_required") or [])
        task_path = project_path / "methods" / "project_method_implementation_tasks.json"
        if method_ids and not task_path.exists():
            return {
                "stage": "methods",
                "command": "prepare-project-method-implementation",
                "cli": _cli_for(project_path, "prepare-project-method-implementation"),
                "reason": "Reusable plugins do not yet cover the planned method. Prepare a project-local Agent implementation contract instead of blocking code generation or substituting another method.",
                "requirement_ids": method_ids,
            }
        if method_ids:
            return {
                "stage": "methods",
                "command": "agent_action_required",
                "cli": None,
                "reason": "Implement the scoped project method tasks, preserve project-local ownership, then rerun audit-project-capabilities and verify-methods with real outputs.",
                "task_artifact": "methods/project_method_implementation_tasks.json",
                "resume_command": _cli_for(project_path, "audit-project-capabilities"),
                "requirement_ids": method_ids,
            }
        if data_ids:
            return {
                "stage": "data",
                "command": "prepare-data-acquisition",
                "cli": _cli_for(project_path, "prepare-data-acquisition"),
                "reason": "The planned evidence needs project data roles that are not yet bound. Prepare acquisition or local data integration before method execution.",
                "requirement_ids": data_ids,
            }
    if sufficiency_report.get("decision") == "execution_required":
        pending = [
            item for item in sufficiency_report.get("requirement_assessments") or []
            if isinstance(item, dict) and item.get("core") and item.get("state") == "execution_required"
        ]
        pending_kinds = {str(item.get("kind") or "") for item in pending}
        existing_events = [
            event for relative in ("data/plugin_execution_ledger.jsonl", "methods/plugin_execution_ledger.jsonl")
            for event in read_jsonl(project_path / relative)
        ]
        pending_ids = {str(item.get("matched_plugin_id") or "") for item in pending}
        attempted = any(str(event.get("plugin_id") or "") in pending_ids for event in existing_events)
        if attempted:
            return {
                "stage": "research_plan",
                "command": "prepare-plugin-rescue",
                "cli": _cli_for(project_path, "prepare-plugin-rescue"),
                "reason": "Selected templates were only fixture/code-generator level after execution preparation; bind and verify real project outputs before claiming sufficiency.",
                "plugin_gap_plan": "research_plan/plugin_gap_plan.json",
            }
        command = "execute-data-plugins" if "data" in pending_kinds else "execute-method-plugins"
        return {
            "stage": "research_plan",
            "command": command,
            "cli": _cli_for(project_path, command),
            "reason": "Core capability templates exist but must execute and produce auditable project outputs before they can satisfy plugin sufficiency.",
            "runtime_level_required": "project_validated",
        }
    if sufficiency_report.get("decision") in {"rescue_required", "blocked", "blocked_unavailable"}:
        audit_report = _read_report(project_path, "research_plan/project_capability_audit.json")
        if capability_contract_path.exists() and audit_report:
            if (
                audit_report.get("research_capability_contract_sha256") != sufficiency_report.get("research_capability_contract_sha256")
                or audit_report.get("source_sufficiency_generated_at") != sufficiency_report.get("generated_at")
            ):
                audit_report = {}
        if not audit_report:
            return {
                "stage": "research_plan",
                "command": "audit-project-capabilities",
                "cli": _cli_for(project_path, "audit-project-capabilities"),
                "reason": "Apparent plugin gaps must first be audited against stage-owned project-local data and method assets before external rescue or a figure block.",
            }
        if sufficiency_report.get("decision") == "blocked_unavailable":
            return {
                "stage": "research_plan",
                "command": "checkpoint",
                "cli": _cli_for(project_path, "checkpoint"),
                "reason": "A required data or method plugin remained unavailable after documented local, AcademicForge, and GitHub rescue attempts; the planned figure cannot be generated without user input.",
                "plugin_gap_plan": "research_plan/plugin_gap_plan.json",
            }
        return {
            "stage": "research_plan",
            "command": "prepare-plugin-rescue",
            "cli": _cli_for(project_path, "prepare-plugin-rescue"),
            "reason": "At least one core figure lacks an executable data or method plugin; prepare a scoped capability rescue instead of generating a substitute figure.",
            "plugin_gap_plan": "research_plan/plugin_gap_plan.json",
        }
    execution_failures = _plugin_execution_failures(project_path)
    if execution_failures:
        failed = execution_failures[-1]
        return {
            "stage": str(failed.get("stage") or "methods"),
            "command": "prepare-plugin-rescue",
            "cli": _cli_for(project_path, "prepare-plugin-rescue"),
            "reason": f"Plugin execution failed for {failed.get('plugin_id') or 'a selected plugin'}; repair the scoped capability or runtime contract before figure generation.",
            "plugin_execution_failure": failed,
        }
    results_path = project_path / "results" / "results.tex"
    result_discipline_review = _read_report(project_path, "review/result_discipline_review_report.json")
    results_stage_meta = ((load_project(project_path).metadata.get("stages") or {}).get("results") or {})
    results_stage_current = bool(
        results_stage_meta.get("status") in COMPLETE_STATUSES
        and not results_stage_meta.get("stale")
    )
    current_results_hash = hashlib.sha256(results_path.read_bytes()).hexdigest() if results_path.exists() else ""
    core_evidence_report = _read_report(project_path, "core_evidence/core_evidence_report.json")
    promoted_snapshot_id = str(core_evidence_report.get("promoted_evidence_snapshot_id") or "")
    result_manifest_path = project_path / "results" / "result_manifest.yaml"
    trace_path = project_path / "results" / "figure_plugin_trace_report.json"
    current_result_manifest_hash = hashlib.sha256(result_manifest_path.read_bytes()).hexdigest() if result_manifest_path.exists() else ""
    current_trace_hash = hashlib.sha256(trace_path.read_bytes()).hexdigest() if trace_path.exists() else ""
    review_matches_results = bool(
        result_discipline_review
        and result_discipline_review.get("results_sha256") == current_results_hash
    )
    if promoted_snapshot_id:
        review_matches_results = bool(
            review_matches_results
            and result_discipline_review.get("evidence_snapshot_id") == promoted_snapshot_id
            and result_discipline_review.get("result_manifest_sha256") == current_result_manifest_hash
            and result_discipline_review.get("figure_plugin_trace_sha256") == current_trace_hash
        )
    if (
        results_stage_current
        and (project_path / "research_plan" / "research_capability_contract.json").exists()
        and results_path.exists()
    ):
        lifecycle_action = coordinated_section_lifecycle_action(project_path, "results")
        if lifecycle_action:
            return lifecycle_action
    if (
        results_stage_current
        and (project_path / "research_plan" / "research_capability_contract.json").exists()
        and results_path.exists()
        and not review_matches_results
    ):
        return {
            "stage": "results",
            "command": "review-results-with-discipline-rules",
            "cli": _cli_for(project_path, "review-results-with-discipline-rules"),
            "reason": "Results prose must be checked against the complete main-figure plugin trace and composite discipline review rules before downstream manuscript sections.",
        }
    if (
        (project_path / "research_plan" / "research_capability_contract.json").exists()
        and results_stage_current
        and review_matches_results
        and result_discipline_review.get("decision") in {"repair_required", "revise_required"}
    ):
        action = result_discipline_review.get("recommended_next_action") or {}
        command = str(action.get("command") or "prepare-result-rescue")
        return {
            "stage": "results",
            "command": command,
            "cli": _cli_for(project_path, command),
            "reason": str(action.get("reason") or "Results discipline review requires evidence repair before manuscript writing continues."),
        }
    plan_feasibility = _read_report(project_path, "research_plan/research_plan_feasibility_report.json")
    if plan_feasibility and plan_feasibility.get("decision") == "blocked":
        command = str(plan_feasibility.get("recommended_next_action") or "revise-research-plan")
        if command not in {"prepare-data-acquisition", "assess-method-feasibility", "revise-research-plan"}:
            command = "revise-research-plan"
        return {
            "stage": "research_plan_feasibility",
            "command": command,
            "cli": _cli_for(project_path, command),
            "reason": "Research-plan feasibility is blocked; repair data/method support or revise the research scope before execution.",
        }
    method_feasibility = _read_report(project_path, "methods/method_feasibility_report.json")
    if method_feasibility and method_feasibility.get("decision") == "blocked":
        command = str(method_feasibility.get("recommended_next_action") or "prepare-method-blueprint")
        if command not in {"prepare-data-acquisition", "collect-method-plan", "prepare-method-blueprint"}:
            command = "prepare-method-blueprint"
        return {
            "stage": "method_feasibility",
            "command": command,
            "cli": _cli_for(project_path, command),
            "reason": "Method feasibility is blocked; repair missing data roles or method templates before figure planning/code generation.",
        }
    figure_contracts = _read_report(project_path, "results/figure_contract_gate_report.json")
    if figure_contracts and figure_contracts.get("decision") == "blocked":
        action = figure_contracts.get("recommended_next_action") or {}
        command = str(action.get("command") or "revise-research-plan")
        if command not in {
            "repair-figure-data",
            "repair-figure-method",
            "revise-research-plan",
            "assess-figure-contracts",
            "prepare-data-acquisition",
            "prepare-method-blueprint",
            "prepare-result-rescue",
            "apply-result-downgrade",
            "checkpoint",
        }:
            command = "revise-research-plan"
        return {
            "stage": "figure_contracts",
            "command": command,
            "cli": _cli_for(project_path, command),
            "reason": "Figure contract gate is blocked; contracted main results need data/method repair before code generation.",
        }
    result_support = _read_report(project_path, "results/result_support_checkpoint.json")
    if result_support:
        action = _result_support_action(project_path, result_support)
        if action:
            return action
    core_evidence = _read_report(project_path, "core_evidence/core_evidence_report.json")
    if core_evidence and core_evidence.get("decision") not in {"pass", "passed"}:
        action = (core_evidence.get("recommended_next_action") or {}).get("command")
        if action in {"repair-figure-data", "repair-figure-method", "diagnose-figure-execution"}:
            return {
                "stage": "core_evidence",
                "command": action,
                "cli": _cli_for(project_path, action),
                "reason": "Core evidence failed because research-plan main figure contracts are not satisfied; repair data or method code before manuscript writing continues.",
            }
        return {
            "stage": "core_evidence",
            "command": "assess-core-evidence",
            "cli": _cli_for(project_path, "assess-core-evidence"),
            "reason": "Core evidence has not passed; refresh the evidence report before manuscript writing continues.",
        }
    project_stages = load_project(project_path).metadata.get("stages") or {}
    latex_stage = project_stages.get("latex") or {}
    quality_stage = project_stages.get("quality_checks") or {}
    latex_stage_current = latex_stage.get("status") in COMPLETE_STATUSES and not latex_stage.get("stale")
    quality_stage_current = quality_stage.get("status") in COMPLETE_STATUSES and not quality_stage.get("stale")
    quality_stage_failed = quality_stage.get("status") == "failed" and not quality_stage.get("stale")
    integrity = _read_report(project_path, "integrity/integrity_report.json")
    if latex_stage_current and integrity and integrity.get("status") not in {"passed", "pass"}:
        return _review_sequence_action(project_path, "The integrity gate failed")
    quality = _read_report(project_path, "quality_checks/quality_report.json")
    if (quality_stage_current or quality_stage_failed) and quality and quality.get("status") not in {"passed", "pass"}:
        return _review_sequence_action(project_path, "The final quality gate failed")
    return None


def _citation_audit_passed(project_path: Path) -> bool:
    report = _read_report(project_path, "citation_audit/final_citation_audit_report.json")
    return report.get("status") == "passed"


def _citation_audit_action(project_path: Path) -> dict[str, Any] | None:
    if _citation_audit_passed(project_path):
        return None
    latest = _read_report(project_path, "citation_audit/citation_audit_report.json")
    if not latest:
        return {
            "stage": "quality_checks",
            "command": "audit-citations",
            "cli": _cli_for(project_path, "audit-citations") + " --final",
            "reason": "Final quality check is blocked until claim-level citation support has a passing audit report.",
        }
    if latest.get("status") == "passed":
        return {
            "stage": "quality_checks",
            "command": "re-audit-citations",
            "cli": _cli_for(project_path, "re-audit-citations"),
            "reason": "A passing citation audit exists, but the final citation audit report has not been written.",
        }
    if not (project_path / "citation_audit" / "citation_repair_plan.json").exists():
        return {
            "stage": "citation_audit",
            "command": "generate-citation-repair-plan",
            "cli": _cli_for(project_path, "generate-citation-repair-plan"),
            "reason": "Claim-level citation audit failed; generate a repair plan before final quality check.",
        }
    if not (project_path / "citation_audit" / "citation_repair_ledger.json").exists():
        plan = _read_report(project_path, "citation_audit/citation_repair_plan.json")
        agent_tasks = [item for item in plan.get("issues") or [] if isinstance(item, dict) and item.get("action") == "agent_paragraph_rewrite"]
        if agent_tasks:
            return {
                "stage": "citation_audit",
                "command": "revise-citation-paragraphs-with-agent",
                "cli": None,
                "reason": "Citation semantics require paragraph-local Agent repair; references must be preserved and evidence summaries must not replace the manuscript argument.",
                "tasks": agent_tasks,
            }
        return {
            "stage": "citation_audit",
            "command": "apply-citation-repair",
            "cli": _cli_for(project_path, "apply-citation-repair"),
            "reason": "Citation repair plan exists and must be applied before re-audit.",
        }
    return {
        "stage": "citation_audit",
        "command": "re-audit-citations",
        "cli": _cli_for(project_path, "re-audit-citations"),
        "reason": "Citation repairs were applied; rerun the audit and write the final pass report before quality check.",
    }


def _review_sequence_action(project_path: Path, prefix: str) -> dict[str, Any]:
    sequence = [
        ("review/gate_failure_diagnosis.json", "diagnose-gate-failures", "map failed gates to revision stages"),
        ("review/reviewer_issues.json", "review-draft", "run a reviewer-style draft pass"),
        ("review/publication_readiness_report.json", "assess-publication-readiness", "estimate target-journal submission risk"),
        ("review/review_workflow_gap_report.json", "discover-review-workflow-gaps", "discover discipline-specific review workflow gaps"),
        ("review/review_engineering_plan.json", "propose-review-engineering-plan", "propose discipline-specific review-engineering actions"),
        ("review/statistical_rescue_plan.json", "recommend-statistical-revision", "recommend statistical rescue or claim reframing routes"),
        ("review/actionable_analysis_tasks.json", "prepare-analysis-revision", "convert review/rescue advice into executable analysis tasks and data-feasibility checks"),
    ]
    for relative, command, reason in sequence:
        if not (project_path / relative).exists():
            return {
                "stage": "review",
                "command": command,
                "cli": _cli_for(project_path, command),
                "reason": f"{prefix}; {reason}.",
            }
    execution_action = _review_execution_action(project_path, prefix)
    if execution_action:
        return execution_action
    if not (project_path / "review" / "revision_plan.json").exists():
        return {
            "stage": "review",
            "command": "generate-revision-plan",
            "cli": _cli_for(project_path, "generate-revision-plan"),
            "reason": f"{prefix}; merge review issues into a staged revision plan.",
        }
    return {
        "stage": "review",
        "command": "generate-revision-plan",
        "cli": _cli_for(project_path, "generate-revision-plan"),
        "reason": f"{prefix}; review artifacts already exist, refresh the unified revision plan before applying revisions.",
    }


def _has_downstream_progress(stages: dict[str, Any], stage: str) -> bool:
    if stage not in STAGE_ORDER:
        return False
    for later_stage in STAGE_ORDER[STAGE_ORDER.index(stage) + 1:]:
        later_meta = stages.get(later_stage) or {}
        if later_meta.get("status") in COMPLETE_STATUSES and not later_meta.get("stale"):
            return True
    return False


def _next_stage(project_path: Path, metadata: dict[str, Any]) -> str | None:
    stages = metadata.get("stages") or {}
    for stage in STAGE_ORDER:
        if stage == "idea":
            continue
        stage_meta = stages.get(stage) or {}
        if not _stage_is_current(project_path, stage, stage_meta):
            if stage in BACKFILL_COMPATIBLE_STAGES and _has_downstream_progress(stages, stage):
                continue
            return stage
    return None


def _data_stage_command(project_path: Path) -> str:
    checks = [
        ("data/data_acquisition_plan.json", "prepare-data-acquisition"),
        ("data/data_inventory.json", "inventory-data"),
        ("data/data_quality_report.json", "assess-data-quality"),
        ("data/data_feasibility_report.json", "assess-data-feasibility"),
    ]
    for relative, command in checks:
        if not (project_path / relative).exists():
            return command
    return "assess-data-feasibility"


def _data_writing_stage_command(project_path: Path) -> str:
    checks = [
        ("data/data_writing_context.json", "build-data-context"),
        ("data/data.tex", "write-data"),
    ]
    for relative, command in checks:
        if not (project_path / relative).exists():
            return command
    return "write-data"


def _methods_stage_command(project_path: Path) -> str:
    manifest = _read_report(project_path, "methods/run_manifest.yaml")
    if manifest.get("status") != "success":
        return "verify-methods"
    return "verify-methods"


def _methods_writing_stage_command(project_path: Path) -> str:
    manifest = _read_report(project_path, "methods/run_manifest.yaml")
    if manifest.get("status") != "success":
        return "verify-methods"
    if not (project_path / "methods" / "method_writing_context.json").exists():
        return "build-method-context"
    if not (project_path / "methods" / "methods.tex").exists():
        return "write-methods"
    return "write-methods"



def _method_feasibility_stage_command(project_path: Path) -> str:
    method_plan_manifest = _read_report(project_path, "method_plan/stage_manifest.json")
    declared_outputs = {str(item).replace("\\", "/") for item in method_plan_manifest.get("output_files") or []}
    if (
        "methods/method_blueprint.json" not in declared_outputs
        or not (project_path / "methods" / "method_blueprint.json").exists()
    ):
        return "prepare-method-blueprint"
    return "assess-method-feasibility"


def _figure_contract_stage_command(project_path: Path) -> str:
    if not (project_path / "results" / "figure_contracts.json").exists():
        return "plan-figures"
    if not (project_path / "methods" / "method_feasibility_report.json").exists():
        return "assess-method-feasibility"
    return "assess-figure-contracts"
def _figure_plan_stage_command(project_path: Path) -> str:
    if not (project_path / "methods" / "method_blueprint.json").exists():
        return "prepare-method-blueprint"
    return "plan-figures"


def _results_stage_command(project_path: Path) -> str:
    if not (project_path / "results" / "result_manifest.yaml").exists():
        return "inventory-results"
    if not (project_path / "results" / "results.tex").exists():
        return "write-results"
    if not (project_path / "results" / "results_summary_zh.md").exists():
        return "write-results"
    return "write-results"


def _core_evidence_stage_command(project_path: Path) -> str:
    report = _read_report(project_path, "core_evidence/core_evidence_report.json")
    if report and report.get("decision") != "pass":
        command = ((report.get("recommended_next_action") or {}).get("command") or "").strip()
        if command in {"repair-figure-data", "repair-figure-method", "diagnose-figure-execution"}:
            return command
    return "assess-core-evidence"


def _stage_command(project_path: Path, stage: str) -> str | None:
    if stage == "data":
        return _data_stage_command(project_path)
    if stage == "data_writing":
        return _data_writing_stage_command(project_path)
    if stage == "method_feasibility":
        return _method_feasibility_stage_command(project_path)
    if stage == "figure_plan":
        return _figure_plan_stage_command(project_path)
    if stage == "figure_contracts":
        return _figure_contract_stage_command(project_path)
    if stage == "methods":
        return _methods_stage_command(project_path)
    if stage == "methods_writing":
        return _methods_writing_stage_command(project_path)
    if stage == "core_evidence":
        return _core_evidence_stage_command(project_path)
    if stage == "result_support":
        return "assess-result-support"
    if stage == "results":
        return _results_stage_command(project_path)
    return STAGE_COMMANDS.get(stage)


def _next_action(project_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    stage = _next_stage(project_path, metadata)
    promoted_snapshot = project_path / "results" / "promoted_evidence_snapshot.json"
    evidence_changing_stages = {
        "research_plan",
        "research_plan_feasibility",
        "data",
        "method_plan",
        "method_feasibility",
        "figure_plan",
        "figure_contracts",
        "code",
        "methods",
        "result_validity",
        "result_support",
    }
    if promoted_snapshot.exists() and stage in evidence_changing_stages:
        return {
            "stage": "core_evidence",
            "command": "reopen-core-evidence",
            "cli": _cli_for(project_path, "reopen-core-evidence") + ' --reason "Upstream scientific evidence requires regeneration."',
            "reason": f"Stage {stage} requires scientific regeneration, so the previously promoted core-evidence snapshot must be explicitly reopened first.",
        }
    failure_action = _gate_failure_action(project_path)
    if failure_action:
        return failure_action
    if stage is None:
        return {
            "stage": None,
            "command": None,
            "cli": None,
            "reason": "All declared stages are current.",
        }
    section = COORDINATED_SECTION_STAGE_MAP.get(stage)
    if section:
        lifecycle_action = coordinated_section_lifecycle_action(project_path, section)
        if lifecycle_action:
            return lifecycle_action
    if stage in {"latex", "quality_checks"}:
        release_action = coordinated_formal_release_action(project_path)
        if release_action:
            return release_action
    command = _stage_command(project_path, stage)
    if stage == "quality_checks" and not _integrity_is_current(project_path):
        command = "run-integrity-gate"
    elif stage == "quality_checks":
        citation_action = _citation_audit_action(project_path)
        if citation_action:
            return citation_action
    if not command:
        raise OrchestratorError(f"No orchestrator command mapping exists for stage: {stage}")
    return {
        "stage": stage,
        "command": command,
        "cli": _cli_for(project_path, command),
        "reason": f"Stage {stage} is pending, stale, or not yet completed.",
    }


def status_project(project: str | Path) -> dict[str, Any]:
    """Return pipeline status, passport state, and the next CLI action."""
    state = load_project(project)
    result_support = _read_report(state.path, "results/result_support_checkpoint.json")
    result_support_action = _result_support_action(state.path, result_support) if result_support else None
    if result_support_action and result_support_action.get("command") == "choose-result-route":
        passport = load_project_passport(state.path)
        return {
            "status": "reported",
            "project_path": str(state.path),
            "pipeline_state": "awaiting_result_route",
            "current_stage": state.metadata.get("current_stage"),
            "awaiting_checkpoint": None,
            "passport": str(state.path / PASSPORT_FILES["passport"]),
            "result_support_checkpoint": "results/result_support_checkpoint.json",
            "next_action": result_support_action,
        }
    drift = detect_artifact_drift(state.path)
    if drift.get("status") == "drift_detected":
        return {
            "status": "reported",
            "project_path": str(state.path),
            "pipeline_state": "drift_detected",
            "current_stage": state.metadata.get("current_stage"),
            "awaiting_checkpoint": None,
            "passport": str(state.path / PASSPORT_FILES["passport"]),
            "drift": drift,
            "next_action": {
                "stage": None,
                "command": "sync-artifact-stale",
                "cli": f"python -m draftpaper_cli.cli sync-artifact-stale --project {_quote(state.path)}",
                "reason": "Artifact hashes changed since the last passport snapshot.",
            },
        }
    passport = load_project_passport(state.path)
    awaiting = passport.get("awaiting_checkpoint")
    if awaiting:
        return {
            "status": "reported",
            "project_path": str(state.path),
            "pipeline_state": "awaiting_confirmation",
            "current_stage": state.metadata.get("current_stage"),
            "awaiting_checkpoint": awaiting,
            "passport": str(state.path / PASSPORT_FILES["passport"]),
            "next_action": {
                "stage": awaiting.get("stage"),
                "command": "resume",
                "cli": f"python -m draftpaper_cli.cli resume --project {_quote(state.path)} --checkpoint-hash {awaiting.get('hash')}",
                "reason": "A checkpoint is waiting for explicit resume confirmation.",
            },
        }
    core_report = _read_report(state.path, "core_evidence/core_evidence_report.json")
    core_stage = (state.metadata.get("stages") or {}).get("core_evidence") or {}
    core_stage_current = bool(
        core_stage.get("status") in COMPLETE_STATUSES
        and not core_stage.get("stale")
    )
    if (
        core_stage_current
        and
        str(core_report.get("decision") or "").lower() in {"pass", "passed"}
        and bool(core_report.get("requires_user_confirmation"))
    ):
        confirmation_error = ""
        try:
            subject = evidence_confirmation_subject(state.path)
        except EvidenceSnapshotMismatch as exc:
            subject = {}
            confirmation_error = str(exc)
        if not subject:
            return {
                "status": "reported",
                "project_path": str(state.path),
                "pipeline_state": "core_evidence_refresh_required",
                "current_stage": state.metadata.get("current_stage"),
                "awaiting_checkpoint": None,
                "passport": str(state.path / PASSPORT_FILES["passport"]),
                "next_action": {
                    "stage": "core_evidence",
                    "command": "assess-core-evidence",
                    "cli": f"python -m draftpaper_cli.cli assess-core-evidence --project {_quote(state.path)}",
                    "reason": confirmation_error or "Core evidence must be reassessed before human confirmation.",
                },
            }
        promoted = _read_report(state.path, "results/promoted_evidence_snapshot.json")
        confirmation_current = bool(
            subject
            and core_report.get("human_confirmation_status") == "approved"
            and core_report.get("human_confirmation_subject_id") == subject.get("confirmation_subject_id")
            and core_report.get("promoted_evidence_snapshot_id") == subject.get("evidence_snapshot_id")
            and promoted.get("snapshot_id") == subject.get("evidence_snapshot_id")
        )
        if not confirmation_current:
            return {
                "status": "reported",
                "project_path": str(state.path),
                "pipeline_state": "confirmation_required",
                "current_stage": state.metadata.get("current_stage"),
                "awaiting_checkpoint": None,
                "passport": str(state.path / PASSPORT_FILES["passport"]),
                "next_action": {
                    "stage": "core_evidence",
                    "command": "checkpoint",
                    "cli": f"python -m draftpaper_cli.cli checkpoint --project {_quote(state.path)} --stage core_evidence",
                    "reason": "The current core-evidence version has passed automated checks but has not been explicitly confirmed.",
                    "confirmation_subject_id": subject.get("confirmation_subject_id"),
                    "evidence_snapshot_id": subject.get("evidence_snapshot_id"),
                },
            }
    next_action = _next_action(state.path, state.metadata)
    command = str(next_action.get("command") or "")
    pipeline_state = {
        "choose-result-route": "awaiting_result_route",
        "resolve-research-capabilities": "plugin_sufficiency_required",
        "assess-plugin-sufficiency": "plugin_sufficiency_required",
        "audit-project-capabilities": "capability_audit_required",
        "prepare-plugin-rescue": "plugin_gap_detected",
        "compose-section-with-agent": "agent_composition_required",
        "revise-section-with-agent": "editor_revision_required",
        "accept-section-draft": "section_acceptance_required",
        "assess-functional-quality-release": "quality_release_required",
        "execute-data-plugins": "plugin_execution_required",
        "execute-method-plugins": "plugin_execution_required",
        "revise-citation-paragraphs-with-agent": "citation_agent_repair_required",
    }.get(command, "ready")
    if next_action.get("plugin_execution_failure"):
        pipeline_state = "plugin_execution_failed"
    elif command == "prepare-plugin-rescue":
        sufficiency = _read_report(state.path, "research_plan/plugin_sufficiency_report.json")
        if any(str(item.get("state") or "") == "blocked_external" for item in sufficiency.get("requirement_assessments") or [] if isinstance(item, dict)):
            pipeline_state = "awaiting_external_access"
    return {
        "status": "reported",
        "project_path": str(state.path),
        "pipeline_state": pipeline_state,
        "current_stage": state.metadata.get("current_stage"),
        "awaiting_checkpoint": None,
        "passport": str(state.path / PASSPORT_FILES["passport"]),
        "next_action": next_action,
    }


def _checkpoint_hash(entry: dict[str, Any]) -> str:
    payload = dict(entry)
    payload["hash"] = "000000000000"
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def checkpoint_project(project: str | Path, *, stage: str, note: str = "") -> dict[str, Any]:
    """Append a checkpoint ledger entry and wait for explicit resume."""
    state = load_project(project)
    if stage not in (state.metadata.get("stages") or {}):
        raise OrchestratorError(f"Unknown checkpoint stage: {stage}")
    passport = load_project_passport(state.path)
    if passport.get("awaiting_checkpoint"):
        raise OrchestratorError("A checkpoint is already awaiting resume.")
    base = {
        "kind": "checkpoint",
        "stage": stage,
        "note": note,
        "created_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "next_action": _next_action(state.path, state.metadata),
    }
    if stage == "core_evidence":
        try:
            subject = evidence_confirmation_subject(state.path)
        except EvidenceSnapshotMismatch as exc:
            raise OrchestratorError(str(exc)) from exc
        base.update(subject)
    base["hash"] = _checkpoint_hash(base)
    append_checkpoint_event(state.path, base)
    return {
        "status": "checkpoint_created",
        "project_path": str(state.path),
        "checkpoint_hash": base["hash"],
        "checkpoint_ledger": str(state.path / PASSPORT_FILES["checkpoint_ledger"]),
        "next_action": base["next_action"],
    }


def resume_project(project: str | Path, *, checkpoint_hash: str, note: str = "") -> dict[str, Any]:
    """Consume a checkpoint by appending a resume ledger entry."""
    state = load_project(project)
    events = read_jsonl(state.path / PASSPORT_FILES["checkpoint_ledger"])
    checkpoints = [event for event in events if event.get("kind") == "checkpoint" and event.get("hash") == checkpoint_hash]
    if not checkpoints:
        raise OrchestratorError(f"Checkpoint hash not found: {checkpoint_hash}")
    if any(event.get("kind") == "resume" and event.get("consumes_hash") == checkpoint_hash for event in events):
        raise OrchestratorError(f"Checkpoint hash has already been consumed: {checkpoint_hash}")
    checkpoint = checkpoints[-1]
    if str(checkpoint.get("stage") or "") == "core_evidence":
        try:
            current_subject = evidence_confirmation_subject(state.path)
        except EvidenceSnapshotMismatch as exc:
            raise OrchestratorError(str(exc)) from exc
        if not checkpoint.get("confirmation_subject_id"):
            raise OrchestratorError(
                "This legacy core-evidence checkpoint is not bound to a scientific evidence version; create a new checkpoint."
            )
        if checkpoint.get("confirmation_subject_id") != current_subject.get("confirmation_subject_id"):
            raise OrchestratorError(
                "Core evidence changed after the checkpoint was created; create and review a new checkpoint."
            )
    resume_event = {
        "kind": "resume",
        "consumes_hash": checkpoint_hash,
        "stage": checkpoints[-1].get("stage"),
        "note": note,
        "created_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
    }
    append_checkpoint_event(state.path, resume_event)
    promoted_snapshot = None
    if str(resume_event.get("stage") or "") == "core_evidence":
        promoted_snapshot = create_evidence_snapshot(state.path)
        if promoted_snapshot.get("snapshot_id") != checkpoint.get("evidence_snapshot_id"):
            raise OrchestratorError("The promoted evidence snapshot does not match the confirmed checkpoint subject.")
        core_report_path = state.path / "core_evidence" / "core_evidence_report.json"
        if core_report_path.exists():
            core_report = json.loads(core_report_path.read_text(encoding="utf-8-sig"))
            core_report["promoted_evidence_snapshot_id"] = promoted_snapshot.get("snapshot_id")
            core_report["human_confirmation_status"] = "approved"
            core_report["human_confirmation_checkpoint_hash"] = checkpoint_hash
            core_report["human_confirmation_subject_id"] = checkpoint.get("confirmation_subject_id")
            core_report_path.write_text(json.dumps(core_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        refresh_project_passport(state.path, event="core_evidence_resume")
    status = status_project(state.path)
    return {
        "status": "resumed",
        "project_path": str(state.path),
        "consumed_checkpoint_hash": checkpoint_hash,
        "evidence_snapshot_id": (promoted_snapshot or {}).get("snapshot_id"),
        "next_action": status["next_action"],
    }


def run_pipeline(project: str | Path) -> dict[str, Any]:
    """Plan the next pipeline action from current project state."""
    status = status_project(project)
    if status["pipeline_state"] == "awaiting_confirmation":
        return {
            "status": "awaiting_confirmation",
            "project_path": status["project_path"],
            "awaiting_checkpoint": status["awaiting_checkpoint"],
            "next_action": status["next_action"],
        }
    if status["pipeline_state"] == "drift_detected":
        return {
            "status": "drift_detected",
            "project_path": status["project_path"],
            "drift": status["drift"],
            "next_action": status["next_action"],
        }
    if status["pipeline_state"] == "awaiting_result_route":
        return {
            "status": "awaiting_result_route",
            "project_path": status["project_path"],
            "next_action": status["next_action"],
        }
    return {
        "status": "planned",
        "project_path": status["project_path"],
        "pipeline_state": status["pipeline_state"],
        "next_action": status["next_action"],
    }


def handle_orchestrator_error(exc: Exception) -> dict[str, str]:
    if isinstance(exc, (OrchestratorError, PassportError, ProjectStateError)):
        return {"status": "error", "message": str(exc)}
    return {"status": "error", "message": str(exc)}
