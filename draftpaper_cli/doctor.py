"""Native Draftpaper-loop doctor and deterministic next-action verification."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from .command_registry import command_spec
from .orchestrator import status_project
from .passport import read_jsonl
from .project_state import load_project
from .project_system_of_record import inspect_project_system_of_record
from .skill_sync import skill_doctor


MANUSCRIPT_TOKEN_BUDGET = 73_343
MANUSCRIPT_WRITING_STAGES = {"results", "introduction", "data", "methods", "discussion"}


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _finding(
    category: str,
    severity: str,
    cause: str,
    impact: str,
    *,
    artifacts: list[str] | None = None,
    automatic_or_manual: str = "automatic",
    next_command: str | None = None,
    precondition_check: dict[str, Any] | None = None,
    stale_scope: list[str] | None = None,
    confidence: str = "high",
) -> dict[str, Any]:
    seed = json.dumps([category, cause, sorted(artifacts or [])], ensure_ascii=False, sort_keys=True)
    return {
        "finding_id": f"doctor:{category}:{hashlib.sha256(seed.encode()).hexdigest()[:12]}",
        "category": category,
        "severity": severity,
        "cause": cause,
        "impact": impact,
        "confidence": confidence,
        "affected_artifacts": sorted(artifacts or []),
        "automatic_or_manual": automatic_or_manual,
        "next_command": next_command,
        "precondition_check": precondition_check or {"status": "not_applicable"},
        "estimated_stale_scope": sorted(stale_scope or []),
    }


def _token_ledger_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lifetime_input_tokens = sum(
        int(item.get("actual_input_tokens") or item.get("estimated_input_tokens") or 0)
        for item in rows
    )
    latest_by_task: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(rows):
        stage = str(item.get("stage") or "")
        task_id = str(item.get("task_id") or "")
        if stage not in MANUSCRIPT_WRITING_STAGES or not task_id.startswith("prepare-section-writing:"):
            continue
        recorded_at = str(item.get("recorded_at") or "")
        current = latest_by_task.get(task_id)
        if current is None or (recorded_at, index) >= (str(current.get("recorded_at") or ""), int(current.get("_index") or 0)):
            latest_by_task[task_id] = {**item, "_index": index}
    active_input_tokens = sum(
        int(item.get("actual_input_tokens") or item.get("estimated_input_tokens") or 0)
        for item in latest_by_task.values()
    )
    return {
        "receipt_count": len(rows),
        "latest_manuscript_receipt_count": len(latest_by_task),
        "active_manuscript_input_tokens": active_input_tokens,
        "lifetime_input_tokens": lifetime_input_tokens,
        "budget": MANUSCRIPT_TOKEN_BUDGET,
    }


def _required_options(command: str) -> list[str]:
    from .command_contracts import required_options

    return required_options(command)


def verify_next_action(project: str | Path) -> dict[str, Any]:
    status = status_project(project)
    action = status.get("next_action") or {}
    command = str(action.get("command") or "")
    cli = str(action.get("cli") or "")
    if command in {"agent_action_required", "human_action_required"}:
        return {
            "status": "passed",
            "action_mode": "manual_or_agent",
            "command": command,
            "registered": True,
            "cli_present": False,
            "missing_required_options": [],
            "reason": action.get("reason"),
        }
    spec = command_spec(command) if command else None
    required = _required_options(command) if spec else []
    missing = [option for option in required if option not in cli]
    return {
        "status": "passed" if command and spec and cli and not missing else "failed",
        "command": command or None,
        "registered": spec is not None,
        "mutates_project": spec.mutates_project if spec else None,
        "protected_action": spec.protected_action if spec else None,
        "manual_only": spec.manual_only if spec else None,
        "cli_present": bool(cli),
        "missing_required_options": missing,
        "cli": cli or None,
        "reason": action.get("reason"),
    }


def _environment() -> dict[str, Any]:
    runtime_source = _runtime_source_diagnostics()
    return {
        "python": sys.version.split()[0],
        "runtime_source": runtime_source,
        "executables": {
            "latex": shutil.which("xelatex") or shutil.which("pdflatex"),
            "bibtex": shutil.which("bibtex"),
            "git": shutil.which("git"),
            "gh": shutil.which("gh"),
        },
        "optional_modules": {
            name: importlib.util.find_spec(name) is not None
            for name in ("bibtexparser", "matplotlib", "numpy", "pandas", "yaml")
        },
    }


def _draftpaper_checkout_root(start: Path) -> Path | None:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        pyproject = candidate / "pyproject.toml"
        package = candidate / "draftpaper_cli"
        if pyproject.is_file() and package.is_dir():
            text = pyproject.read_text(encoding="utf-8-sig", errors="replace")
            if re.search(r'(?m)^name\s*=\s*["\']draftpaper-cli["\']', text):
                return candidate
    return None


def _runtime_source_diagnostics(
    *,
    imported_module_file: str | Path | None = None,
    working_directory: str | Path | None = None,
) -> dict[str, Any]:
    imported = Path(imported_module_file or __file__).resolve()
    imported_root = _draftpaper_checkout_root(imported)
    cwd_checkout = _draftpaper_checkout_root(Path(working_directory or Path.cwd()))
    try:
        distribution_version = importlib.metadata.version("draftpaper-cli")
    except importlib.metadata.PackageNotFoundError:
        distribution_version = None
    mismatch = bool(cwd_checkout and imported_root != cwd_checkout)
    return {
        "imported_module": str(imported),
        "imported_checkout_root": str(imported_root) if imported_root else None,
        "working_checkout_root": str(cwd_checkout) if cwd_checkout else None,
        "source_kind": "source_checkout" if imported_root else "installed_package",
        "distribution_version": distribution_version,
        "source_checkout_mismatch": mismatch,
    }


def doctor_project(project: str | Path | None = None, *, explain: bool = False) -> dict[str, Any]:
    environment = _environment()
    environment["workflow_skill"] = skill_doctor()
    findings: list[dict[str, Any]] = []
    runtime_source = environment["runtime_source"]
    if runtime_source.get("source_checkout_mismatch"):
        checkout = str(runtime_source.get("working_checkout_root") or "").strip()
        findings.append(_finding(
            "runtime_source_mismatch",
            "error",
            "The current working tree is a Draftpaper-loop source checkout, but Python imported draftpaper_cli from another installation.",
            "Commands may run stale code and produce artifacts that do not match the checked-out implementation.",
            artifacts=[str(runtime_source.get("imported_module") or "")],
            next_command=f'python -m pip install -e "{checkout}"' if checkout else "python -m pip install -e .",
        ))
    if environment["optional_modules"].get("bibtexparser") is False:
        findings.append(_finding("environment", "error", "bibtexparser is unavailable", "Structured bibliography validation cannot run.", next_command="python -m pip install bibtexparser>=1.4"))
    if environment["workflow_skill"].get("status") != "passed":
        findings.append(_finding(
            "workflow_skill_mismatch",
            "info",
            "The installed Draftpaper workflow skill does not match the canonical package resource.",
            "Codex may recommend a stale stage order even when the current CLI is correct.",
            artifacts=[str(environment["workflow_skill"].get("installed_path") or "")],
            next_command=str(environment["workflow_skill"].get("next_command") or "draftpaper install-skill --force"),
        ))
    if project is None:
        return {
            "schema_version": "dpl.doctor.v1",
            "status": "passed" if not [item for item in findings if item["severity"] == "error"] else "failed",
            "scope": "environment",
            "environment": environment,
            "findings": findings,
        }

    state = load_project(project)
    root = state.path
    status = status_project(root)
    next_check = verify_next_action(root)
    system = inspect_project_system_of_record(root)
    if system.get("status") != "current" or system.get("violation_count"):
        findings.append(_finding("project_system_of_record", "error", "Project system-of-record is missing, invalid, or violates lineage isolation.", "Derived or baseline artifacts may enter the active graph.", artifacts=["project_system_of_record.json"], next_command=f'python -m draftpaper_cli.cli migrate-project --project "{root}"'))
    if status.get("pipeline_state") == "drift_detected":
        findings.append(_finding("stage_stale", "error", "Artifacts differ from the managed passport baseline.", "A mutating command would otherwise mix external changes with its own transaction.", artifacts=[item.get("path") for item in (status.get("drift") or {}).get("changed_artifacts") or [] if item.get("path")], next_command=f'python -m draftpaper_cli.cli sync-artifact-stale --project "{root}"', stale_scope=list((status.get("drift") or {}).get("affected_stages") or [])))
    if next_check.get("status") == "failed":
        findings.append(_finding("next_action", "error", "The current status recommendation is not immediately executable.", "Following status would fail before scientific work begins.", next_command=next_check.get("cli"), precondition_check=next_check))

    stale = sorted(stage for stage, meta in (state.metadata.get("stages") or {}).items() if meta.get("stale"))
    snapshot = _read(root / "results" / "promoted_evidence_snapshot.json")
    sufficiency = _read(root / "research_plan" / "plugin_sufficiency_report.json")
    capability = _read(root / "research_plan" / "research_capability_contract.json")
    routing_ambiguity = [item for item in capability.get("capability_pack_routing") or [] if isinstance(item, dict) and item.get("status") == "ambiguous"]
    if routing_ambiguity:
        findings.append(_finding("plugin_routing_ambiguity", "warning", "Multiple capability packs have equal routing support.", "An unintended discipline method could be selected.", artifacts=["research_plan/research_capability_contract.json"], automatic_or_manual="manual", next_command=f'python -m draftpaper_cli.cli assess-plugin-sufficiency --project "{root}"'))
    if sufficiency.get("decision") in {"rescue_required", "blocked_unavailable", "project_implementation_required"}:
        command = "prepare-project-method-implementation" if sufficiency.get("decision") == "project_implementation_required" else "prepare-plugin-rescue"
        findings.append(_finding("plugin_sufficiency", "warning" if sufficiency.get("decision") != "blocked_unavailable" else "error", f"Plugin sufficiency decision is {sufficiency.get('decision')}.", "Core evidence cannot be completed until the scoped capability route is resolved.", artifacts=["research_plan/plugin_sufficiency_report.json"], automatic_or_manual="manual" if sufficiency.get("decision") == "blocked_unavailable" else "automatic", next_command=f'python -m draftpaper_cli.cli {command} --project "{root}"'))
    external = [
        item for item in sufficiency.get("requirement_assessments") or []
        if isinstance(item, dict) and item.get("state") == "blocked_external"
    ]
    if external:
        findings.append(_finding("external_runtime", "warning", "One or more API/server/GPU contracts lack live project evidence.", "Mock or contract-only capability cannot support a scientific claim.", artifacts=["research_plan/plugin_sufficiency_report.json"], automatic_or_manual="manual", next_command=f'python -m draftpaper_cli.cli prepare-plugin-rescue --project "{root}"'))

    figure_evidence = _read(root / "results" / "figure_evidence_resolution.json")
    if figure_evidence.get("status") == "blocked":
        findings.append(_finding("figure_run_binding", "error", "Figure semantic evidence resolution is blocked.", "A figure may use identifiers, the wrong run/model/cohort, or incomplete semantic metadata.", artifacts=["results/figure_evidence_resolution.json"], next_command=f'python -m draftpaper_cli.cli resolve-figure-evidence --project "{root}"'))
    bibliography = _read(root / "quality_checks" / "bibliography_quality_report.json")
    duplicate = _read(root / "references" / "reference_duplicate_report.json")
    if duplicate.get("status") == "confirmation_required":
        findings.append(_finding("reference_metadata", "warning", "Related reference versions require a preferred citable version decision.", "The bibliography may render one work as multiple year-suffixed citations.", artifacts=["references/reference_duplicate_report.json"], automatic_or_manual="manual", next_command=f'python -m draftpaper_cli.cli inspect-reference-duplicates --project "{root}"'))
    if bibliography and bibliography.get("status") == "failed":
        findings.append(_finding("bibliography_format", "error", "Bibliography metadata or journal style validation failed.", "Citation support may be valid while the rendered References remain publication-incompatible.", artifacts=["quality_checks/bibliography_quality_report.json"], next_command=f'python -m draftpaper_cli.cli validate-bibliography --project "{root}"'))

    final_audit = _read(root / "citation_audit" / "final_citation_audit_report.json")
    if final_audit and final_audit.get("status") != "passed":
        findings.append(_finding("citation_support", "error", "Final citation support audit is not passing.", "The final manuscript contains weak or mismatched citation use.", artifacts=["citation_audit/final_citation_audit_report.json"], next_command=f'python -m draftpaper_cli.cli generate-citation-repair-plan --project "{root}"'))
    blind = _read(root / "quality_checks" / "blind_reviews" / "aggregate.json")
    if (state.metadata.get("stages") or {}).get("quality_checks", {}).get("status") in {"approved", "completed"} and not blind:
        findings.append(_finding("blind_review", "warning", "No two-reviewer independent single-manuscript audit is recorded.", "Automated gates may have missed scientific or narrative defects.", artifacts=["quality_checks"], automatic_or_manual="manual", next_command=f'python -m draftpaper_cli.cli prepare-independent-manuscript-review --project "{root}"'))
    token_rows = read_jsonl(root / "token_ledger.jsonl")
    token_summary = _token_ledger_summary(token_rows)
    active_input_tokens = int(token_summary["active_manuscript_input_tokens"])
    if active_input_tokens > MANUSCRIPT_TOKEN_BUDGET:
        findings.append(_finding("token_budget", "warning", f"The latest manuscript writing packets require {active_input_tokens} input tokens, above {MANUSCRIPT_TOKEN_BUDGET:,}.", "Current writers are receiving oversized repeated context; historical retries are reported separately and do not keep a repaired project permanently in warning state.", artifacts=["token_ledger.jsonl"], next_command=f'python -m draftpaper_cli.cli resolve-paragraph-evidence --project "{root}" --section results'))
    revision = _read(root / "writing" / "revision_workspace.json")
    if revision.get("pending_requests"):
        findings.append(_finding("revision_state", "info", "Author revision requests are pending preview or acceptance.", "The current PDF may not include the latest author intent.", artifacts=["writing/revision_workspace.json"], automatic_or_manual="manual", next_command=f'python -m draftpaper_cli.cli build-manuscript-source-map --project "{root}"'))

    findings.sort(key=lambda item: (item["severity"], item["category"], item["finding_id"]))
    report = {
        "schema_version": "dpl.doctor.v1",
        "status": (
            "failed"
            if any(item["severity"] == "error" for item in findings)
            else "attention"
            if any(item["severity"] == "warning" for item in findings)
            else "passed"
        ),
        "scope": "project",
        "project_path": str(root),
        "project_id": state.metadata.get("project_id"),
        "pipeline_state": status.get("pipeline_state"),
        "stale_stages": stale,
        "evidence_snapshot_id": snapshot.get("snapshot_id"),
        "environment": environment,
        "next_action_verification": next_check,
        "system_of_record": {key: system.get(key) for key in ("status", "category_count", "artifact_count", "violation_count")},
        "token_ledger": token_summary,
        "finding_count": len(findings),
        "findings": findings,
    }
    if explain:
        from .artifact_dag import build_artifact_dag

        report["artifact_dependency_dag"] = build_artifact_dag(root, write=False)
        report["failure_routes"] = [
            {
                "finding_id": item.get("finding_id"),
                "category": item.get("category"),
                "affected_artifacts": item.get("affected_artifacts") or [],
                "next_command": item.get("next_command"),
                "stale_scope": item.get("stale_scope") or [],
            }
            for item in findings
        ]
    return report


def rebuild_derived(project: str | Path, *, dry_run: bool = True) -> dict[str, Any]:
    report = inspect_project_system_of_record(project)
    tasks = []
    for artifact in report.get("artifacts") or []:
        if artifact.get("category") == "derived_rebuildable" and artifact.get("rebuild_command"):
            tasks.append({"artifact": artifact.get("path"), "command": artifact.get("rebuild_command"), "input_sha256": artifact.get("input_sha256") or {}})
    return {
        "status": "planned",
        "dry_run": bool(dry_run),
        "task_count": len(tasks),
        "tasks": tasks,
        "policy": "This command never overwrites canonical decisions, scientific sources, approved evidence or lineage baselines.",
    }
