# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

from .change_impact import CANONICAL_CHANGE_CLASSES
from .command_registry import (
    COMMAND_SPECS,
    command_spec,
    dispatch_extensions_nonblocking,
    dispatch_registered_command,
)
from .command_transaction import record_command_transaction
from .write_set_guard import BoundaryViolation, WriteSetGuard
from .workflow_trace import begin_workflow_trace, finish_workflow_trace
from .passport import PassportError, refresh_project_passport
from .project_state import (
    ProjectStateError,
)
from .stale_sync import ArtifactDriftError, detect_artifact_drift


_LEGACY_NAME_MODULES = {
    "ClaimContractError": ".claim_contract",
    "CodeOwnershipError": ".code_ownership",
    "CoreEvidenceError": ".core_evidence",
    "EvidenceSnapshotMismatch": ".evidence_snapshot",
    "FigureContractGateError": ".figure_contract_gate",
    "FigurePlanError": ".figure_plan",
    "FigureRepairError": ".figure_repair",
    "JournalProfileError": ".journal_profile",
    "MethodFeasibilityError": ".method_feasibility",
    "MethodPlanError": ".method_plan",
    "NoveltyOverlapError": ".research_plan",
    "ObservationError": ".observations",
    "PluginExecutionError": ".plugin_execution",
    "PluginRescueError": ".plugin_rescue",
    "ResearchCodeMiningError": ".research_code_mining",
    "ResearchFeasibilityError": ".research_feasibility",
    "ResultDisciplineReviewError": ".result_discipline_review",
    "ResultRescueError": ".result_rescue",
    "ResultSupportError": ".result_support",
    "ResultValidityError": ".result_validity",
    "ZoteroAdapterError": ".zotero_adapter",
    "apply_result_downgrade": ".claim_contract",
    "assess_core_evidence": ".core_evidence",
    "assess_figure_contracts": ".figure_contract_gate",
    "assess_method_feasibility": ".method_feasibility",
    "assess_plugin_sufficiency": ".research_capabilities",
    "assess_research_plan_feasibility": ".research_feasibility",
    "assess_result_support": ".result_support",
    "assess_result_validity": ".result_validity",
    "audit_project_capabilities": ".project_capability_audit",
    "bootstrap_discipline_foundation": ".research_code_mining",
    "build_code_provenance": ".code_ownership",
    "build_data_writing_context": ".data_feasibility",
    "build_method_writing_context": ".methods",
    "capture_discipline_learning": ".research_code_mining",
    "classify_code_ownership": ".code_ownership",
    "classify_plugin_reusability": ".research_code_mining",
    "collect_method_plan": ".method_plan",
    "diagnose_figure_execution": ".figure_repair",
    "discover_research_repos": ".research_code_mining",
    "execute_data_plugins": ".plugin_execution",
    "execute_method_plugins": ".plugin_execution",
    "extract_method_formulas": ".code_ownership",
    "extract_plugin_candidates": ".research_code_mining",
    "inspect_research_repo": ".research_code_mining",
    "list_zotero_collections": ".zotero_adapter",
    "map_repository_workflow": ".research_code_mining",
    "plan_figures": ".figure_plan",
    "preflight_plugin_contribution_package": ".plugin_candidates",
    "preflight_research_feasibility": ".research_feasibility",
    "prepare_discussion_comparison": ".discussion",
    "prepare_plugin_rescue": ".plugin_rescue",
    "prepare_result_rescue": ".result_rescue",
    "record_observation": ".observations",
    "record_plugin_rescue_outcome": ".plugin_rescue",
    "render_third_party_notices": ".third_party_provenance",
    "repair_figure_data": ".figure_repair",
    "repair_figure_method": ".figure_repair",
    "resolve_journal_template": ".journal_profile",
    "resolve_research_capabilities": ".research_capabilities",
    "review_results_with_discipline_rules": ".result_discipline_review",
    "revise_research_plan": ".research_feasibility",
    "route_stage_code": ".code_ownership",
    "score_research_repos": ".research_code_mining",
    "search_literature_for_project": ".literature_search",
    "trace_figures_to_code": ".code_ownership",
    "validate_figure_plugin_trace": ".figure_plugin_trace",
    "validate_template_registry": ".template_registry",
    "write_data": ".data_feasibility",
}


def __getattr__(name: str) -> Any:
    """Resolve old cli-namespace imports lazily for ``cli_compat``."""

    package = import_module(__package__)
    if hasattr(package, name):
        value = getattr(package, name)
        globals()[name] = value
        return value
    module_name = _LEGACY_NAME_MODULES.get(name)
    if module_name:
        module = import_module(module_name, package=__package__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _read_cli_json(path: str | None) -> dict:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _skill_source_root_from_args(args: argparse.Namespace) -> str | None:
    direct = getattr(args, "source_root", None) or getattr(args, "path", None)
    if direct:
        return direct
    for attr in ["snapshot", "inspection", "index"]:
        report = _read_cli_json(getattr(args, attr, None))
        source_root = report.get("source_root")
        if source_root:
            return str(source_root)
    return None


def _single_skill_source_file_from_args(args: argparse.Namespace) -> str | None:
    direct = getattr(args, "source_file", None) or getattr(args, "path", None)
    if direct:
        return str(direct)
    snapshot = _read_cli_json(getattr(args, "snapshot", None))
    if not snapshot:
        return None
    records = snapshot.get("records") or []
    source_root = snapshot.get("source_root")
    if len(records) != 1 or not source_root:
        return None
    relative_path = records[0].get("relative_path")
    if not relative_path:
        return None
    return str(Path(str(source_root)) / str(relative_path))


def _skill_source_label(args: argparse.Namespace) -> str:
    return str(getattr(args, "adapter", None) or getattr(args, "source", None) or "local_skill")


def _skill_source_url(args: argparse.Namespace) -> str | None:
    explicit = getattr(args, "source_url", None)
    if explicit:
        return str(explicit)
    repo = getattr(args, "repo", None)
    if repo:
        repo_text = str(repo)
        if repo_text.startswith("http://") or repo_text.startswith("https://"):
            return repo_text
        return f"https://github.com/{repo_text}"
    return None
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="draftpaper",
        description="Local-first staged workflow for research paper projects.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-project", help="Create a single-paper project directory model.")
    create.add_argument("--root", "--projects-root", dest="root", default=None, help="Directory that will contain paper projects; defaults to configured projects root.")
    create.add_argument("--allow-external-project-root", action="store_true", help="Explicitly allow a project root different from the configured central projects root.")
    create.add_argument("--idea", required=True, help="Research idea or working title.")
    create.add_argument("--field", required=True, help="Research field or aim.")
    create.add_argument("--target-journal", default="General Academic Journal", help="Target journal or template family.")
    create.add_argument("--overwrite", action="store_true", help="Allow regenerating an existing project scaffold.")

    load = subparsers.add_parser("load-project", help="Load project metadata as JSON.")
    load.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    validate = subparsers.add_parser("validate-project", help="Validate project metadata and stage manifests.")
    validate.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    subparsers.add_parser("validate-command-contracts", help="Validate the normalized CLI, handler, MCP, and execution-policy contracts.")

    path_budget = subparsers.add_parser("path-budget-check", help="Validate Windows-safe project and artifact path budgets.")
    path_budget.add_argument("--project", required=True)
    layout_doctor = subparsers.add_parser("doctor-project-layout", help="Find path-budget issues and adjacent orphan artifacts without mutating them.")
    layout_doctor.add_argument("--project", required=True)
    adopt_orphans = subparsers.add_parser("adopt-orphan-artifacts", help="Read-only plan for verified adjacent artifacts and stage-owned destinations.")
    adopt_orphans.add_argument("--project", required=True)
    apply_orphans = subparsers.add_parser("apply-orphan-adoption", help="Human-approved copy of identity-verified adjacent artifacts into the project.")
    apply_orphans.add_argument("--project", required=True)

    statistical_contract = subparsers.add_parser("build-statistical-validation-contract", help="Build task-aware statistical validation requirements for the research blueprint.")
    statistical_contract.add_argument("--project", required=True)
    rule_coverage = subparsers.add_parser("assess-review-rule-coverage", help="Report missing task- and discipline-specific statistical review-rule families.")
    rule_coverage.add_argument("--project", required=True)
    pre_execution = subparsers.add_parser("assess-pre-execution-support", help="Assess data, method, plugin, and statistical support before key-figure code generation.")
    pre_execution.add_argument("--project", required=True)
    pre_execution_rescue = subparsers.add_parser("prepare-pre-execution-rescue", help="Prepare scoped data, method, plugin, and review-rule rescue tasks.")
    pre_execution_rescue.add_argument("--project", required=True)
    review_plan = subparsers.add_parser("review-research-plan", help="Render the Chinese-first research blueprint and feasibility packet for human confirmation.")
    review_plan.add_argument("--project", required=True)
    revise_objective = subparsers.add_parser(
        "revise-research-objective",
        help="Apply a science-first objective contract and stale the research chain before plan confirmation.",
    )
    revise_objective.add_argument("--project", required=True)
    revise_objective.add_argument("--objective-file", required=True)
    confirm_plan = subparsers.add_parser("confirm-research-plan", help="Human-confirm the exact research blueprint hash used by key-figure execution.")
    confirm_plan.add_argument("--project", required=True)
    confirm_plan.add_argument("--plan-hash", default=None)
    confirm_plan.add_argument("--decision-hash", default=None, help="v0.42 scientific decision hash; --plan-hash remains a compatibility alias.")
    confirm_plan.add_argument("--accept-limitations", action="store_true")
    reopen_plan = subparsers.add_parser("reopen-research-plan", help="Explicitly reopen a confirmed scientific contract before changing claims, data, methods, statistics, or figures.")
    reopen_plan.add_argument("--project", required=True)
    reopen_plan.add_argument("--reason", required=True)
    validate_plan_review = subparsers.add_parser("validate-research-plan-review", help="Read-only readiness check before rendering a research-plan confirmation packet.")
    validate_plan_review.add_argument("--project", required=True)
    compare_plan_review = subparsers.add_parser("compare-research-plan-decision", help="Compare the active research-plan decision with the latest confirmed decision.")
    compare_plan_review.add_argument("--project", required=True)
    compare_plan_review.add_argument("--against", default="latest-confirmed")
    explain_plan_review = subparsers.add_parser("explain-research-plan-reconfirmation", help="Explain why the active research plan does or does not require a new confirmation.")
    explain_plan_review.add_argument("--project", required=True)
    audit_plan_migration = subparsers.add_parser("audit-research-plan-migration", help="Read-only audit of a historical research-plan snapshot under the v0.42 semantic contract.")
    audit_plan_migration.add_argument("--project", required=True)
    show_plan_packet = subparsers.add_parser("show-human-review-packet", help="Show the readable research-plan review packet paths.")
    show_plan_packet.add_argument("--project", required=True)
    show_plan_packet.add_argument("--decision-family", default="scientific_plan")
    inspect_review_evidence = subparsers.add_parser("inspect-review-evidence", help="Read one explicit, project-bound evidence reference without loading the full audit.")
    inspect_review_evidence.add_argument("--project", required=True)
    inspect_review_evidence.add_argument("--ref", required=True)
    subparsers.add_parser("audit-human-checkpoint-policy", help="Verify explicit decision, packet, risk, and receipt policies for protected commands.")
    confirmed_alignment = subparsers.add_parser("validate-confirmed-figure-alignment", help="Reject any executable main figure that diverges from the human-confirmed blueprint.")
    confirmed_alignment.add_argument("--project", required=True)
    caption_validation = subparsers.add_parser("validate-figure-captions", help="Validate group-level headline, ordered panel descriptions, statistics, and claim boundaries.")
    caption_validation.add_argument("--project", required=True)
    final_review = subparsers.add_parser("review-final-manuscript", help="Render one release packet containing the final PDF, citation audit, and two independent reviews.")
    final_review.add_argument("--project", required=True)
    final_confirm = subparsers.add_parser("confirm-final-manuscript", help="Human-confirm the exact final manuscript release hash.")
    final_confirm.add_argument("--project", required=True)
    final_confirm.add_argument("--release-hash", required=True)

    inspect_migration = subparsers.add_parser("inspect-project-migration", help="Read-only report of schema updates required by an older project.")
    inspect_migration.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    migrate = subparsers.add_parser("migrate-project", help="Explicitly apply current project directories, stages, dependencies, and manifests.")
    migrate.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    plan_version = subparsers.add_parser("plan-project-version", help="Read-only plan for creating a clean _vN project and selectively importing parent assets.")
    plan_version.add_argument("--project", required=True, help="Path to the read-only parent project.")
    plan_version.add_argument("--version", default="v1", help="Version label such as v1 or v2.")
    plan_version.add_argument("--destination-root", default=None, help="Optional parent directory for the new project.")
    plan_version.add_argument("--change-request", default=None, help="Optional change-request file; only its filename and hash enter the plan.")
    plan_version.add_argument("--output", default=None, help="Optional path outside the parent project where the JSON plan is saved.")

    create_version = subparsers.add_parser("create-project-version", help="Create a clean child project from a saved project-version plan.")
    create_version.add_argument("--plan", required=True, help="Path to asset_import_plan.json produced by plan-project-version.")

    import_version = subparsers.add_parser("import-version-assets", help="Import allowlisted parent assets into lineage-owned child locations.")
    import_version.add_argument("--project", required=True, help="Path to the newly created child project.")
    import_version.add_argument("--plan", required=True, help="Path to the same project-version plan used to create the child.")

    validate_version = subparsers.add_parser("validate-project-version", help="Validate child identity, lineage isolation, and imported asset hashes.")
    validate_version.add_argument("--project", required=True, help="Path to the child project.")

    inspect_sor = subparsers.add_parser("inspect-system-of-record", help="Read-only summary of project artifact categories and invariants.")
    inspect_sor.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    prepare_project_method = subparsers.add_parser(
        "prepare-project-method-implementation",
        help="Prepare auditable Agent tasks when the research plan needs a method absent from reusable plugins.",
    )
    prepare_project_method.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    subparsers.add_parser("list-capability-packs", help="List validated research capability packs.")
    subparsers.add_parser("evaluate-capability-routing", help="Run bundled held-out capability-pack routing cases.")

    figure_evidence = subparsers.add_parser("resolve-figure-evidence", help="Resolve each semantic figure contract to run/model/cohort-qualified evidence.")
    figure_evidence.add_argument("--project", required=True)

    paragraph_evidence = subparsers.add_parser("resolve-paragraph-evidence", help="Build hard-budget paragraph evidence slices for one manuscript section.")
    paragraph_evidence.add_argument("--project", required=True)
    paragraph_evidence.add_argument("--section", required=True, choices=["results", "introduction", "data", "methods", "discussion"])

    stage_receipt = subparsers.add_parser("record-stage-receipt", help="Append a stage execution and token receipt.")
    stage_receipt.add_argument("--project", required=True)
    stage_receipt.add_argument("--stage", required=True)
    stage_receipt.add_argument("--task-id", required=True)
    stage_receipt.add_argument("--input-artifact", action="append", default=[])
    stage_receipt.add_argument("--estimated-input-tokens", type=int, default=0)
    stage_receipt.add_argument("--actual-input-tokens", type=int, default=None)
    stage_receipt.add_argument("--actual-output-tokens", type=int, default=None)
    stage_receipt.add_argument("--model", default=None)
    stage_receipt.add_argument("--receipt-status", default="recorded")

    build_registry = subparsers.add_parser("build-reference-registry", help="Normalize library.bib into the canonical reference registry and journal bibliography contract.")
    build_registry.add_argument("--project", required=True)
    inspect_duplicates = subparsers.add_parser("inspect-reference-duplicates", help="Inspect duplicate works and related publication versions without deleting references.")
    inspect_duplicates.add_argument("--project", required=True)
    resolve_version = subparsers.add_parser("resolve-reference-version", help="Confirm the preferred citable version of one canonical work before manuscript writing.")
    resolve_version.add_argument("--project", required=True)
    resolve_version.add_argument("--work", required=True)
    resolve_version.add_argument("--preferred-key", required=True)
    validate_bib = subparsers.add_parser("validate-bibliography", help="Audit structured metadata, duplicate decisions, journal style and compiled bibliography artifacts.")
    validate_bib.add_argument("--project", required=True)
    proof = subparsers.add_parser("render-reference-proof", help="Render an HTML proof with DOI/URL hyperlinks and bibliography audit status.")
    proof.add_argument("--project", required=True)

    subparsers.add_parser("validate-third-party-provenance", help="Validate source commits, licenses, influence links and formal plugin upstream references.")
    subparsers.add_parser("render-third-party-notices", help="Regenerate THIRD_PARTY_NOTICES.md from the machine-readable source registry.")

    template_registry = subparsers.add_parser("validate-template-registry", help="Validate discipline plugin manifests and template files.")
    template_registry.add_argument("--root", default=None, help="Optional discipline_modules root for testing or contribution review.")

    status = subparsers.add_parser("status", help="Report orchestrated pipeline status and next action.")
    status.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    review_policy = subparsers.add_parser("configure-review-policy", help="Choose manual, balanced, or delegated checkpoint review.")
    review_policy.add_argument("--project", required=True)
    review_policy.add_argument("--mode", required=True, choices=["manual", "balanced", "delegated"])
    grant_review = subparsers.add_parser("grant-agent-review", help="Grant a scoped, hashed Agent review delegation.")
    grant_review.add_argument("--project", required=True)
    grant_review.add_argument("--scope", required=True, help="Comma-separated stages or *.")
    grant_review.add_argument("--max-risk", dest="max_risk", default="C1", choices=["C0", "C1", "C2", "C3"])
    grant_review.add_argument("--actor-id", default="agent")
    grant_review.add_argument("--require-independent-agent", action="store_true")
    grant_review.add_argument("--revision-cycle-id", default=None)
    grant_review.add_argument("--expires-at", default=None)
    grant_review.add_argument("--allowed-change-class", dest="allowed_change_classes", action="append", default=[])
    grant_review.add_argument("--allow-scientific-freeze", action="store_true")
    grant_review.add_argument("--allow-external-side-effects", dest="forbid_external_side_effects", action="store_false")
    grant_review.add_argument("--allow-unresolved-items", dest="forbid_unresolved_items", action="store_false")
    grant_review.add_argument("--max-checkpoints", dest="max_checkpoint_count", type=int, default=None)
    grant_review.add_argument("--producer-agent-id", default=None)
    policy_status = subparsers.add_parser("review-policy-status", help="Show review mode and active delegations.")
    policy_status.add_argument("--project", required=True)
    shadow = subparsers.add_parser("review-authority-shadow", help="Report the new authority policy without changing decisions.")
    shadow.add_argument("--project", required=True)
    revoke_review = subparsers.add_parser("revoke-agent-review", help="Revoke all active Agent review delegations.")
    revoke_review.add_argument("--project", required=True)
    revoke_review.add_argument("--reason", required=True)
    authority = subparsers.add_parser("evaluate-checkpoint-authority", help="Evaluate whether a checkpoint is notification, delegable, or human-only.")
    authority.add_argument("--project", required=True)
    authority.add_argument("--checkpoint-hash", required=True)
    review_checkpoint = subparsers.add_parser("review-checkpoint", help="Record an authorized Agent review decision without impersonating the user.")
    review_checkpoint.add_argument("--project", required=True)
    review_checkpoint.add_argument("--checkpoint-hash", required=True)
    review_checkpoint.add_argument("--actor", default="agent", choices=["agent"])
    review_checkpoint.add_argument("--actor-id", default="agent")
    review_checkpoint.add_argument("--delegation-hash", default=None)
    review_checkpoint.add_argument("--reviewer-agent-id", default=None)
    review_checkpoint.add_argument("--decision", default="approve", choices=["approve", "reject", "refine"])
    stage_activity = subparsers.add_parser("show-stage-activity", help="Show the evidence-backed activity bundle for one stage.")
    stage_activity.add_argument("--project", required=True)
    stage_activity.add_argument("--stage", required=True)
    managed_begin = subparsers.add_parser("begin-managed-change", help="Create a hash-bound scoped edit packet.")
    managed_begin.add_argument("--project", required=True)
    managed_begin.add_argument("--intent", required=True)
    managed_begin.add_argument("--change-class", dest="change_class", required=True)
    managed_begin.add_argument("--path", dest="paths", action="append", default=[])
    managed_begin.add_argument("--content-file", default=None)
    managed_apply = subparsers.add_parser("apply-managed-change", help="Apply a previously previewed managed edit packet.")
    managed_apply.add_argument("--project", required=True)
    managed_apply.add_argument("--packet-id", required=True)
    managed_apply.add_argument("--packet-hash", required=True)
    revision_cycle = subparsers.add_parser("begin-revision-cycle", help="Open a revision cycle from the active immutable baseline.")
    revision_cycle.add_argument("--project", required=True)
    revision_cycle.add_argument("--reason", default="author_update")
    revision_cycle.add_argument("--requested-change", dest="requested_changes", action="append", default=[])
    revision_cycle.add_argument("--allowed-change-class", dest="allowed_change_classes", action="append", default=[])
    revision_cycle.add_argument("--protected-fact", dest="protected_facts", action="append", default=[])
    revision_cycle.add_argument("--expected-artifact", dest="expected_artifacts", action="append", default=[])
    revision_cycle.add_argument("--started-by", default="user")
    revision_cycle.add_argument("--baseline-id", default=None)
    consistency = subparsers.add_parser("audit-longitudinal-consistency", help="Audit facts and manuscript references across revision cycles.")
    consistency.add_argument("--project", required=True)
    consistency.add_argument("--output-root", default=None)
    reconcile = subparsers.add_parser("reconcile-project-drift", help="Resolve one recorded external-edit reconciliation route.")
    reconcile.add_argument("--project", required=True)
    reconcile.add_argument("--route", required=True, choices=["adopt_as_expected_change", "rebuild_derived_artifacts", "reopen_scientific_stage"])
    reconcile.add_argument("--reconciliation-id", default=None)
    baseline = subparsers.add_parser("show-scientific-baseline", help="Show the active or named immutable scientific baseline.")
    baseline.add_argument("--project", required=True)
    baseline.add_argument("--baseline-id", default=None)

    extension_doctor = subparsers.add_parser(
        "extension-doctor",
        help="Report installed extension compatibility and non-blocking event receipts.",
    )
    extension_doctor.add_argument(
        "--project", required=True, help="Path to a project directory or project.json."
    )

    checkpoint = subparsers.add_parser("checkpoint", help="Create an explicit user-confirmation checkpoint.")
    checkpoint.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    checkpoint.add_argument("--stage", required=True, help="Stage being checkpointed.")
    checkpoint.add_argument("--note", default="", help="Human-readable checkpoint note.")

    resume = subparsers.add_parser("resume", help="Resume from a checkpoint hash.")
    resume.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    resume.add_argument("--checkpoint-hash", required=True, help="Checkpoint hash to consume.")
    resume.add_argument("--note", default="", help="Human-readable resume note.")

    show_checkpoint = subparsers.add_parser("show-checkpoint-summary", help="Read the current Chinese human-checkpoint summary and exact local paths.")
    show_checkpoint.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    show_checkpoint.add_argument("--checkpoint-hash", default=None, help="Optional checkpoint hash; defaults to the latest checkpoint.")
    show_checkpoint.add_argument("--language", default="zh-CN", choices=["zh-CN", "en"], help="Summary language.")
    show_checkpoint.add_argument("--view", default="decision", choices=["decision", "audit"], help="Select the readable decision view or the technical audit view.")

    show_checkpoint_audit = subparsers.add_parser("show-checkpoint-audit", help="Show the technical audit JSON path and the optional renderer route for a v6 checkpoint.")
    show_checkpoint_audit.add_argument("--project", required=True)
    show_checkpoint_audit.add_argument("--checkpoint-package-id", default=None)
    show_checkpoint_audit.add_argument("--checkpoint-hash", default=None)
    render_checkpoint_audit = subparsers.add_parser("render-checkpoint-audit", help="Render a disposable HTML cache for one v6 technical audit JSON.")
    render_checkpoint_audit.add_argument("--project", required=True)
    render_checkpoint_audit.add_argument("--checkpoint-package-id", required=True)

    compare_checkpoint = subparsers.add_parser("compare-checkpoint-decision", help="Compare the current scientific decision with the latest confirmed one.")
    compare_checkpoint.add_argument("--project", required=True)
    compare_checkpoint.add_argument("--checkpoint-hash", default=None)
    compare_checkpoint.add_argument("--against", default="latest-confirmed")

    explain_reconfirmation = subparsers.add_parser("explain-reconfirmation", help="Explain why a checkpoint does or does not need new author confirmation.")
    explain_reconfirmation.add_argument("--project", required=True)
    explain_reconfirmation.add_argument("--checkpoint-package-id", default=None)

    validate_checkpoint_readability = subparsers.add_parser("validate-checkpoint-readability", help="Read the decision-page readability gate for a v5 checkpoint.")
    validate_checkpoint_readability.add_argument("--project", required=True)
    validate_checkpoint_readability.add_argument("--checkpoint-package-id", default=None)
    validate_checkpoint_readability.add_argument("--language", default="zh-CN", choices=["zh-CN", "en"])

    show_continuity = subparsers.add_parser("show-confirmation-continuity", help="Show the latest reusable scientific confirmation receipt.")
    show_continuity.add_argument("--project", required=True)
    show_continuity.add_argument("--checkpoint-type", default="core_evidence")

    rebuild_checkpoint_presentation = subparsers.add_parser("rebuild-checkpoint-presentation", help="Regenerate v5/v6 decision HTML without changing scientific identity.")
    rebuild_checkpoint_presentation.add_argument("--project", required=True)
    rebuild_checkpoint_presentation.add_argument("--checkpoint-package-id", required=True)

    checkpoint_migration = subparsers.add_parser("audit-checkpoint-v5-migration", help="Read-only readiness audit for migrating a legacy checkpoint to v5.")
    checkpoint_migration.add_argument("--project", required=True)
    checkpoint_migration.add_argument("--checkpoint-hash", default=None)

    checkpoint_shadow = subparsers.add_parser("shadow-checkpoint-v5", help="Run a read-only v5 checkpoint shadow audit outside the project directory.")
    checkpoint_shadow.add_argument("--project", required=True)
    checkpoint_shadow.add_argument("--output-root", default=None)
    checkpoint_shadow_v6 = subparsers.add_parser("shadow-checkpoint-v6", help="Run a read-only v6 checkpoint shadow audit outside the project directory.")
    checkpoint_shadow_v6.add_argument("--project", required=True)
    checkpoint_shadow_v6.add_argument("--output-root", default=None)

    preview_checkpoint = subparsers.add_parser(
        "preview-checkpoint-summary",
        help="Render an enriched offline checkpoint view without changing ledger or confirmation state.",
    )
    preview_checkpoint.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    preview_checkpoint.add_argument("--checkpoint-hash", default=None, help="Optional source checkpoint hash; defaults to the latest checkpoint.")

    run = subparsers.add_parser("run-pipeline", help="Plan the next orchestrated pipeline action.")
    run.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    drift = subparsers.add_parser("detect-artifact-drift", help="Detect artifact hash drift from project_passport.yaml.")
    drift.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    sync_stale = subparsers.add_parser("sync-artifact-stale", help="Mark dependent stages stale from artifact hash drift.")
    sync_stale.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    update = subparsers.add_parser("update-stage-status", help="Update one stage status.")
    update.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    update.add_argument("--stage", required=True, help="Stage name to update.")
    update.add_argument("--status", required=True, help="New stage status.")

    stale = subparsers.add_parser("mark-stage-stale", help="Mark downstream dependent stages as stale.")
    stale.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    stale.add_argument("--stage", required=True, help="Stage whose dependents should be marked stale.")
    stale.add_argument("--include-self", action="store_true", help="Also mark the named stage stale.")

    search = subparsers.add_parser("search-literature", help="Search or import literature and write references artifacts.")
    search.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    search.add_argument("--query", default=None, help="Optional explicit scholarly search query.")
    search.add_argument("--limit", type=int, default=30, help="Maximum number of ranked references to keep.")
    search.add_argument("--from-json", default=None, help="Use a local JSON list of literature items instead of live search.")
    search.add_argument("--zotero-collection", default=None, help="Import references from a named Zotero collection.")
    search.add_argument("--zotero-context", default="idea", choices=["idea", "data", "methods", "all"], help="Manuscript context assigned to Zotero collection references.")
    search.add_argument("--zotero-min-items", type=int, default=20, help="Minimum Zotero-first reference count before optional external supplementation.")
    search.add_argument("--no-zotero-supplement", action="store_true", help="Do not supplement a small Zotero collection with free external search.")
    online = search.add_mutually_exclusive_group()
    online.add_argument("--include-online", dest="include_online", action="store_true", help="Aggregate live online providers with JSON, Zotero, and registered local sources.")
    online.add_argument("--no-online", dest="include_online", action="store_false", help="Use only explicitly supplied, Zotero, and registered local sources.")
    search.set_defaults(include_online=None)
    code_sources = search.add_mutually_exclusive_group()
    code_sources.add_argument("--enrich-code-sources", dest="enrich_code_sources", action="store_true", help="Record metadata-only GitHub/Zenodo code leads for retained literature (default).")
    code_sources.add_argument("--no-code-source-enrichment", dest="enrich_code_sources", action="store_false", help="Disable the metadata-only code-source enrichment stage.")
    search.add_argument("--enrich-code-sources-online", action="store_true", help="Allow public GitHub/Zenodo metadata API calls during enrichment.")
    search.add_argument(
        "--fetch-policy",
        dest="fetch_policy_mode",
        choices=["off", "resolve_only", "resolve_then_fetch_on_demand", "fulltext_eager", "local_only"],
        default=None,
        help="Override the project paper identity/full-text policy for this search.",
    )
    search.set_defaults(enrich_code_sources=True, enrich_code_sources_online=False)

    add_source = subparsers.add_parser("add-literature-source", help="Register a local PDF folder or structured literature file.")
    add_source.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    add_source.add_argument("--type", dest="source_type", choices=["local_folder", "local-folder", "structured_file", "structured-file"], required=True)
    add_source.add_argument("--path", required=True, help="Local folder or JSON/BibTeX/RIS/EndNote file.")
    add_source.add_argument("--context", default="all", choices=["idea", "data", "methods", "all"])
    add_source.add_argument("--recursive", action="store_true", default=True)
    add_source.add_argument("--no-recursive", dest="recursive", action="store_false")
    add_source.add_argument("--copy-attachments", action="store_true", help="Copy local PDFs into the project under references/local_attachments/.")

    list_sources = subparsers.add_parser("list-literature-sources", help="List registered local literature sources without exposing absolute paths.")
    list_sources.add_argument("--project", required=True)
    collect_sources = subparsers.add_parser("collect-literature", help="Scan registered local literature sources and write a collection receipt.")
    collect_sources.add_argument("--project", required=True)
    reconcile_sources = subparsers.add_parser("reconcile-literature", help="Merge registered local sources into the current reference registry without live search.")
    reconcile_sources.add_argument("--project", required=True)
    parse_source_documents = subparsers.add_parser("parse-literature-source-documents", help="Batch-parse registered local PDFs with resumable per-file receipts.")
    parse_source_documents.add_argument("--project", required=True)
    parse_source_documents.add_argument("--no-mineru", dest="use_mineru", action="store_false")
    parse_source_documents.set_defaults(use_mineru=True)
    parse_source_documents.add_argument("--timeout-seconds", type=int, default=600)
    coverage = subparsers.add_parser("review-literature-coverage", help="Review literature coverage by scientific role and source type.")
    coverage.add_argument("--project", required=True)
    confirm_literature = subparsers.add_parser(
        "confirm-literature-corpus",
        help="Human-confirm the exact literature corpus hash used by teaching and project-role guidance.",
    )
    confirm_literature.add_argument("--project", required=True)
    confirm_literature.add_argument(
        "--packet-hash",
        required=True,
        help="Exact hash from references/literature_confirmation_packet.json after human review.",
    )

    integrity = subparsers.add_parser("audit-literature-integrity", help="Audit work identity, score state, parser binding, and orphan full-text reachability.")
    integrity.add_argument("--project", required=True)
    integrity.add_argument("--output", default=None)
    sync_literature = subparsers.add_parser("sync-literature-sources", help="Preview or apply registered local literature source synchronization.")
    sync_literature.add_argument("--project", required=True)
    sync_literature.add_argument("--apply", action="store_true")
    sync_literature.add_argument("--packet-hash", default=None)
    apply_literature = subparsers.add_parser("apply-literature-sync", help="Apply a hash-bound literature merge preview.")
    apply_literature.add_argument("--project", required=True)
    apply_literature.add_argument("--packet-hash", required=True)
    repair_identity = subparsers.add_parser("repair-literature-identities", help="Preview or apply canonical work identity repair for current literature records.")
    repair_identity.add_argument("--project", required=True)
    repair_identity.add_argument("--apply", action="store_true")
    migrate_literature = subparsers.add_parser("migrate-literature-index", help="Preview or apply a local-only migration of a legacy literature index.")
    migrate_literature.add_argument("--project", required=True)
    migrate_literature.add_argument("--index", default=None)
    migrate_literature.add_argument("--apply", action="store_true")
    migrate_literature.add_argument("--packet-hash", default=None)
    rollback_migration = subparsers.add_parser("rollback-literature-migration", help="Rollback one hash-bound legacy literature migration.")
    rollback_migration.add_argument("--project", required=True)
    rollback_migration.add_argument("--receipt", default=None)
    rebuild_index = subparsers.add_parser("rebuild-literature-index", help="Rebuild the Core bilingual offline literature index from current records.")
    rebuild_index.add_argument("--project", required=True)
    quarantine_orphan = subparsers.add_parser("quarantine-orphan-literature", help="Move previewed orphan full-text artifacts into the project quarantine area.")
    quarantine_orphan.add_argument("--project", required=True)
    quarantine_orphan.add_argument("--report", default=None)
    quarantine_orphan.add_argument("--apply", action="store_true", help="Apply the current preview after packet-hash verification.")
    quarantine_orphan.add_argument("--packet-hash", default=None)
    rollback_orphan = subparsers.add_parser("rollback-orphan-literature", help="Restore one hash-verified orphan quarantine transaction.")
    rollback_orphan.add_argument("--project", required=True)
    rollback_orphan.add_argument("--receipt", default=None)

    consent = subparsers.add_parser("record-remote-parser-consent", help="Record one project-scoped decision for optional remote MinerU parsing.")
    consent.add_argument("--project", required=True)
    consent.add_argument("--decision", choices=["once", "project", "deny"], required=True)
    consent.add_argument("--service", default="official-agent")
    consent.add_argument("--document-class", dest="document_classes", action="append", default=["published-public"])

    parse_document = subparsers.add_parser("parse-literature-document", help="Parse one local PDF with pypdf and optional MinerU routes.")
    parse_document.add_argument("--project", required=True)
    parse_document.add_argument("--input", required=True, help="PDF path.")
    parse_document.add_argument("--no-mineru", dest="use_mineru", action="store_false")
    parse_document.set_defaults(use_mineru=True)
    parse_document.add_argument("--timeout-seconds", type=int, default=600)
    parse_document.add_argument("--parser", choices=["auto", "pypdf", "mineru"], default="auto")
    parse_document.add_argument("--mineru-route", choices=["auto", "official-agent", "custom-endpoint", "local", "off"], default="auto")
    parse_document.add_argument("--purpose", choices=["metadata", "abstract", "sections", "tables", "formulas", "references", "evidence", "full"], default="evidence")
    parse_document.add_argument("--work-id", default=None)
    parse_document.add_argument("--remote-consent", choices=["ask_once", "once", "project", "deny"], default="ask_once")
    parse_document.add_argument("--document-class", choices=["published-public", "licensed-private", "unpublished", "sensitive", "unknown"], default="unknown")
    parse_document.add_argument("--custom-endpoint", default=None, help="User-provided MinerU endpoint; Draftpaper-loop does not deploy it.")

    benchmark_literature = subparsers.add_parser("benchmark-literature-quality", help="Run the deterministic all-discipline literature retrieval benchmark.")
    benchmark_literature.add_argument("--output", required=True)
    benchmark_parser = subparsers.add_parser("benchmark-document-parsers", help="Run the frozen parser-route contract benchmark without deploying MinerU.")
    benchmark_parser.add_argument("--output", required=True)

    zotero_collections = subparsers.add_parser("list-zotero-collections", help="List Zotero collections available through ZOTERO_* environment variables.")
    zotero_collections.add_argument("--project", default=None, help="Optional project path; accepted for Codex workflow symmetry.")

    journal = subparsers.add_parser("resolve-journal-template", help="Resolve target journal Overleaf/template formatting constraints.")
    journal.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    journal.add_argument("--target-journal", default=None, help="Target journal name or abbreviation, for example APJS.")
    journal.add_argument("--overleaf-url", default=None, help="Explicit Overleaf template URL.")
    journal.add_argument("--guideline-url", default=None, help="Journal author-guidelines URL when no Overleaf template exists.")
    journal.add_argument("--from-html", default=None, help="Use a local HTML file as the template/guideline source.")

    preflight = subparsers.add_parser("preflight-research-feasibility", help="Assess whether the idea, literature, and available data can support planning.")
    preflight.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    plan = subparsers.add_parser("generate-plan", help="Generate a literature-informed formal research plan.")
    plan.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    plan.add_argument("--allow-high-similarity", action="store_true", help="Continue even when a highly similar prior paper is detected.")

    capability_contract = subparsers.add_parser("resolve-research-capabilities", help="Resolve final composite discipline and research capability contracts from the current research plan.")
    capability_contract.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    plugin_sufficiency = subparsers.add_parser("assess-plugin-sufficiency", help="Gate planned core figures against structured data, method, runtime, and review plugin support.")
    plugin_sufficiency.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    project_capability_audit = subparsers.add_parser("audit-project-capabilities", help="Audit missing plugin requirements against stage-owned project-local data and method assets before external rescue.")
    project_capability_audit.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    plugin_rescue = subparsers.add_parser("prepare-plugin-rescue", help="Prepare scoped AcademicForge/GitHub/plugin-promotion rescue tasks for missing capabilities.")
    plugin_rescue.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    plugin_rescue.add_argument("--academicforge-root", default=None, help="Optional local AcademicForge skill root used only for candidate extraction commands.")
    plugin_rescue.add_argument("--github-metadata", default=None, help="Optional offline GitHub-search-style metadata JSON used for scoped discovery commands.")
    plugin_rescue.add_argument("--zenodo-metadata", default=None, help="Optional offline Zenodo metadata JSON used as a persistent archive route.")

    plugin_rescue_outcome = subparsers.add_parser("record-plugin-rescue-outcome", help="Record whether scoped local, AcademicForge, and GitHub capability rescue found an executable route.")
    plugin_rescue_outcome.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    plugin_rescue_outcome.add_argument("--requirement-id", required=True, help="Requirement identifier from review/plugin_rescue_plan.json.")
    plugin_rescue_outcome.add_argument("--outcome", required=True, choices=["capability_found", "not_found_after_search"])
    plugin_rescue_outcome.add_argument("--attempted-route", action="append", default=[], help="Audited route; repeat for each applicable local, catalog, live-host, or persistent-archive route.")
    plugin_rescue_outcome.add_argument("--route-evidence", action="append", default=[], help="Structured evidence artifact as route=project-relative-or-absolute-path; repeat for every attempted route.")
    plugin_rescue_outcome.add_argument("--evidence-note", required=True, help="Short auditable summary of the search result.")

    plan_feasibility = subparsers.add_parser("assess-research-plan-feasibility", help="Check research-plan figure/storyboard feasibility before data and method execution.")
    plan_feasibility.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    revise_plan = subparsers.add_parser("revise-research-plan", help="Write scope-revision suggestions from feasibility reports.")
    revise_plan.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    intro = subparsers.add_parser("write-introduction", help="Write a traceable LaTeX Introduction section.")
    intro.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    observation = subparsers.add_parser("record-observation", help="Record visible user/Codex analysis for staged writing context.")
    observation.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    observation.add_argument("--stage", required=True, help="Stage this observation supports, for example data or methods.")
    observation.add_argument("--kind", required=True, help="Observation kind, for example agent_analysis, data_summary, or method_rationale.")
    observation.add_argument("--text", required=True, help="Visible analysis summary to preserve in the local project.")
    observation.add_argument("--source", default="codex_visible_analysis", help="Observation source label.")

    data_inventory = subparsers.add_parser("inventory-data", help="Inventory local data files.")
    data_inventory.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    data_access = subparsers.add_parser("classify-data-access", help="Classify project data access modes without fetching field-specific data.")
    data_access.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    data_access.add_argument("--source-root", default=None, help="Optional external research folder to scan for access-mode evidence.")

    data_acquisition = subparsers.add_parser("prepare-data-acquisition", help="Write a plan-first data acquisition profile and source manifest.")
    data_acquisition.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    data_acquisition.add_argument("--source-root", default=None, help="Optional external research folder to scan for access-mode evidence.")

    data_plugins = subparsers.add_parser("execute-data-plugins", help="Execute selected local data-plugin fixture contracts and record data-stage provenance.")
    data_plugins.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    data_sources = subparsers.add_parser("inventory-data-sources", help="Refresh data acquisition source manifest without downloading data.")
    data_sources.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    data_sources.add_argument("--source-root", default=None, help="Optional external research folder to scan for access-mode evidence.")

    data_quality = subparsers.add_parser("assess-data-quality", help="Assess basic local data quality.")
    data_quality.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    data_quality.add_argument("--required-column", action="append", default=[], help="Column required for the current research plan.")
    data_quality.add_argument("--max-missing-ratio", type=float, default=0.2, help="Maximum acceptable missing-cell ratio.")

    data_feasibility = subparsers.add_parser("assess-data-feasibility", help="Assess whether data can support the research plan.")
    data_feasibility.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    data_feasibility.add_argument("--min-rows", type=int, default=30, help="Minimum tabular row count expected for the planned study.")

    data_context = subparsers.add_parser("build-data-context", help="Build manuscript-facing Data writing context from inventory, gates, and observations.")
    data_context.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    data_writer = subparsers.add_parser("write-data", help="Write data/data.tex from manuscript-facing Data context.")
    data_writer.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    method_plan = subparsers.add_parser("collect-method-plan", help="Collect user method intent and synthesize literature-informed method requirements.")
    method_plan.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    method_plan.add_argument("--method-note", action="append", default=[], help="User-provided method note. Can be repeated.")
    method_plan.add_argument("--primary-metric", default=None, help="Primary metric expected for result validity. When omitted, infer it from the structured research method contract.")
    method_plan.add_argument("--minimum-primary-metric", type=float, default=None, help="Minimum acceptable primary metric value.")

    method_blueprint = subparsers.add_parser("prepare-method-blueprint", help="Build a discipline-aware data-to-method code blueprint.")
    method_blueprint.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    method_plugins = subparsers.add_parser("execute-method-plugins", help="Execute selected local method-plugin fixture contracts and record method-stage provenance.")
    method_plugins.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    method_feasibility = subparsers.add_parser("assess-method-feasibility", help="Check method data contracts and executable method support before figure planning.")
    method_feasibility.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    figures = subparsers.add_parser("plan-figures", help="Observe project state and plan project-specific scientific figures.")
    figures.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    figures.add_argument("--use-review-tasks", action="store_true", help="Include review/actionable_analysis_tasks.json hints when planning figures.")

    figure_contracts = subparsers.add_parser("assess-figure-contracts", help="Gate planned main figures against data, method, and storyboard contracts before code generation.")
    figure_contracts.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    figure_plugin_trace = subparsers.add_parser("validate-figure-plugin-trace", help="Validate main-figure claim, plugin, run-output, and review-rule provenance.")
    figure_plugin_trace.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    codegen = subparsers.add_parser("generate-analysis-code", help="Generate project-local analysis code from literature and method requirements.")
    codegen.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    codegen.add_argument("--output", action="append", default=[], help="Project-relative output file expected from generated code.")
    codegen.add_argument("--auto-plan-figures", action="store_true", help="Generate results/figure_plan.json first if it is missing or stale.")
    codegen.add_argument("--use-review-tasks", action="store_true", help="Include review/actionable_analysis_tasks.json in generated analysis code.")

    code_owner = subparsers.add_parser("classify-code-ownership", help="Classify project-local Python code into data, methods, plotting, or compatibility ownership.")
    code_owner.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    route_code = subparsers.add_parser("route-stage-code", help="Copy or move legacy code/ scripts into stage-owned data and methods locations.")
    route_code.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    route_code.add_argument("--mode", default="copy", choices=["copy", "move"], help="Copy keeps legacy files; move leaves compatibility launchers when requested.")
    route_code.add_argument("--no-compat-launchers", action="store_true", help="Do not write code/ compatibility launchers when moving files.")

    code_provenance = subparsers.add_parser("build-code-provenance", help="Build a project-level code provenance manifest.")
    code_provenance.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    formulas = subparsers.add_parser("extract-method-formulas", help="Extract LaTeX method formulas from stage-owned method code.")
    formulas.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    figure_trace = subparsers.add_parser("trace-figures-to-code", help="Trace result figures back to stage-owned plotting or method code.")
    figure_trace.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    verify = subparsers.add_parser("verify-methods", help="Run method code and write methods/run_manifest.yaml.")
    verify.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    verify.add_argument("--command", dest="method_command", help="Optional legacy string command override. Defaults to methods/method_code_manifest.json verify_command_argv, then legacy verify_command.")
    verify.add_argument("--output", action="append", default=None, help="Project-relative output file that must exist after the command.")
    verify.add_argument("--input", action="append", default=None, help="Project-relative input data file used by the method command.")
    verify.add_argument("--allow-system-binary", action="store_true", help="Explicitly permit a non-project executable and record the elevated execution mode.")

    methods = subparsers.add_parser("write-methods", help="Write methods.tex after successful method verification.")
    methods.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    method_context = subparsers.add_parser("build-method-context", help="Build manuscript-facing Methods writing context from method plan, code verification, and observations.")
    method_context.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    inventory = subparsers.add_parser("inventory-results", help="Inventory local result figures and tables.")
    inventory.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    result_validity = subparsers.add_parser("assess-result-validity", help="Assess whether method outputs support expected result claims.")
    result_validity.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    result_validity.add_argument("--primary-metric", default=None, help="Override primary metric from methods/method_requirements.json.")
    result_validity.add_argument("--minimum-value", type=float, default=None, help="Override minimum acceptable primary metric value.")

    review_rules = subparsers.add_parser("assess-review-rules", help="Assess discipline review rules against current project evidence for a workflow stage.")
    review_rules.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    review_rules.add_argument("--stage", required=True, help="Workflow stage, such as method_plan, figure_contract, assess_result_validity, result_support_checkpoint, or citation_audit.")
    review_rules.add_argument("--output", help="Optional output JSON path. Defaults to results/review_rule_gate_report.json unless --no-write is set.")
    review_rules.add_argument("--no-write", action="store_true", help="Print the report without writing a runtime gate artifact.")

    result_support = subparsers.add_parser("assess-result-support", help="Assess whether current result evidence supports the research-plan claims.")
    result_support.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    downgrade_claim = subparsers.add_parser("apply-result-downgrade", help="Freeze current result evidence and downgrade unsupported research-plan claims without rerunning results.")
    downgrade_claim.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    downgrade_claim.add_argument("--checkpoint-hash", help="Hash of the current Result Support checkpoint; omit once to receive the current hash and complete command.")
    downgrade_claim.add_argument("--reason", default="", help="Optional human-readable reason for choosing the downgrade route.")

    result_rescue = subparsers.add_parser("prepare-result-rescue", help="Prepare data/method supplement tasks when current results cannot support planned claims.")
    result_rescue.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    result_rescue.add_argument("--checkpoint-hash", help="Hash of the current Result Support checkpoint; omit once to receive the current hash and complete command.")

    core_evidence = subparsers.add_parser("assess-core-evidence", help="Assess data-method-figure-result evidence before manuscript writing.")
    core_evidence.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    figure_diagnosis = subparsers.add_parser("diagnose-figure-execution", help="Diagnose whether contracted main figures need data or method repair.")
    figure_diagnosis.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    figure_data_repair = subparsers.add_parser("repair-figure-data", help="Plan data acquisition/integration repair for failed contracted figures.")
    figure_data_repair.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    figure_method_repair = subparsers.add_parser("repair-figure-method", help="Plan method-code discovery/generation repair for failed contracted figures.")
    figure_method_repair.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    results = subparsers.add_parser("write-results", help="Write results.tex from result_manifest.yaml.")
    results.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    result_discipline_review = subparsers.add_parser("review-results-with-discipline-rules", help="Audit Results against composite discipline review rules and complete figure-plugin traces.")
    result_discipline_review.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    resolve_evidence = subparsers.add_parser("resolve-result-evidence", help="Resolve run-bound model and statistical evidence.")
    resolve_evidence.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    reopen_evidence = subparsers.add_parser("reopen-core-evidence", help="Archive an approved evidence snapshot before scientific revision.")
    reopen_evidence.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    reopen_evidence.add_argument("--reason", required=True, help="Reason the human-approved evidence must be reopened.")

    paper_narrative = subparsers.add_parser("build-paper-narrative", help="Build the paper brief, figure-story arc, and section claim allocation before writing.")
    paper_narrative.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    section_outline = subparsers.add_parser("prepare-section-outline", help="Build a paragraph-level evidence outline before Codex composes a section.")
    section_outline.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    section_outline.add_argument("--section", required=True, choices=["introduction", "data", "methods", "results", "discussion"])

    results_synthesis = subparsers.add_parser("build-results-synthesis", help="Build finding blocks from the figure-story arc and resolved result evidence.")
    results_synthesis.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    argument_matrices = subparsers.add_parser("build-argument-matrices", help="Build Introduction gap and Discussion finding-comparison matrices.")
    argument_matrices.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    section_lifecycles = subparsers.add_parser("build-section-lifecycles", help="Build traceable Data and Methods scientific lifecycles.")
    section_lifecycles.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    panel_contracts = subparsers.add_parser("build-panel-contracts", help="Build panel-aware figure narrative and local-repair contracts.")
    panel_contracts.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    panel_repair = subparsers.add_parser("prepare-panel-repair", help="Diagnose and route panel-local data, method, rendering, statistics, or claim repairs.")
    panel_repair.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    venue_style = subparsers.add_parser("resolve-venue-writing-style", help="Resolve functional venue and style preferences without copying prose.")
    venue_style.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    scientific_editor = subparsers.add_parser("prepare-scientific-editor", help="Prepare bounded paragraph-local scientific revision tasks.")
    scientific_editor.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    scientific_editor.add_argument("--section", required=True, choices=["introduction", "data", "methods", "results", "discussion"])
    scientific_editor.add_argument("--input", required=True, help="Path to the section candidate to review.")
    editor_revision = subparsers.add_parser("record-scientific-editor-revision", help="Record one auditable paragraph-local scientific editor iteration.")
    editor_revision.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    editor_revision.add_argument("--section", required=True, choices=["introduction", "data", "methods", "results", "discussion"])
    editor_revision.add_argument("--before", required=True, help="Section candidate before this local revision round.")
    editor_revision.add_argument("--after", required=True, help="Section candidate after this local revision round.")
    editor_revision.add_argument("--iteration", required=True, type=int, choices=[1, 2, 3])

    functional_release = subparsers.add_parser("assess-functional-quality-release", help="Assess v0.22 functional quality-parity eligibility.")
    functional_release.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    submit_section = subparsers.add_parser("submit-section-draft", help="Validate and install a freely composed manuscript section draft.")
    submit_section.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    submit_section.add_argument("--section", required=True, choices=["introduction", "data", "methods", "results", "discussion"])
    submit_section.add_argument("--input", required=True, help="Path to a Codex-composed LaTeX section candidate.")

    apply_section_revision_parser = subparsers.add_parser("apply-section-revision", help="Validate, edit, accept, install, and stale a bounded section revision as one transaction.")
    apply_section_revision_parser.add_argument("--project", required=True)
    apply_section_revision_parser.add_argument("--section", required=True, choices=["introduction", "data", "methods", "results", "discussion"])
    apply_section_revision_parser.add_argument("--input", required=True)
    apply_section_revision_parser.add_argument("--change-class", choices=list(CANONICAL_CHANGE_CLASSES))

    accept_section = subparsers.add_parser("accept-section-draft", help="Accept an editor-cleared free-prose section for formal manuscript writing.")
    accept_section.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    accept_section.add_argument("--section", required=True, choices=["introduction", "data", "methods", "results", "discussion"])

    prepare_section = subparsers.add_parser("prepare-section-writing", help="Build the evidence and narrative-contract packet for free Codex section writing.")
    prepare_section.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    prepare_section.add_argument("--section", required=True, choices=["introduction", "data", "methods", "results", "discussion"])

    manuscript_quality = subparsers.add_parser("assess-manuscript-quality", help="Score Results against evidence fidelity and scientific narrative contracts.")
    manuscript_quality.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    manuscript_quality.add_argument("--section", default="results", choices=["results"])
    manuscript_quality.add_argument("--input", default=None, help="Optional Results LaTeX file; defaults to results/results.tex.")

    figure_publication_quality = subparsers.add_parser("assess-figure-publication-quality", help="Score rendered main figures against semantic, plugin-run, panel, evidence, and legibility contracts.")
    figure_publication_quality.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    results_semantic_repair = subparsers.add_parser("prepare-results-semantic-repair", help="Prepare minimal claim-level Results repairs without replacing the full section.")
    results_semantic_repair.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    paper_quality_parity = subparsers.add_parser("assess-paper-quality-parity", help="Score the complete manuscript and figures against the 0.95 release contract.")
    paper_quality_parity.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    submit_figure_semantics = subparsers.add_parser("submit-figure-semantic-annotations", help="Submit auditable semantic mappings for legacy rendered figures.")
    submit_figure_semantics.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    submit_figure_semantics.add_argument("--input", required=True, help="Path to a JSON semantic annotation file.")

    discussion = subparsers.add_parser("write-discussion", help="Write a traceable LaTeX Discussion section.")
    discussion.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    discussion_comparison = subparsers.add_parser("prepare-discussion-comparison", help="Prepare a comparison-literature matrix before writing Discussion.")
    discussion_comparison.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    latex = subparsers.add_parser("assemble-latex", help="Assemble staged sections into latex/main.tex.")
    latex.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    latex.add_argument("--compile-pdf", action="store_true", help="Compile latex/main.tex into latex/main.pdf for review.")

    pdf = subparsers.add_parser("compile-latex-pdf", help="Compile latex/main.tex into latex/main.pdf for review.")
    pdf.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    quality = subparsers.add_parser("quality-check", help="Run final staged manuscript quality checks.")
    quality.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    integrity = subparsers.add_parser("run-integrity-gate", help="Run citation evidence and result artifact integrity checks.")
    integrity.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    citation_audit = subparsers.add_parser("audit-citations", help="Run claim-level citation/source support audit before final quality check.")
    citation_audit.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    citation_audit.add_argument("--final", action="store_true", help="Write the final pass report when the audit passes.")

    citation_repair_plan = subparsers.add_parser("generate-citation-repair-plan", help="Generate a citation repair plan from the latest citation audit.")
    citation_repair_plan.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    citation_repair_apply = subparsers.add_parser("apply-citation-repair", help="Apply safe citation repairs from citation_audit/citation_repair_plan.json.")
    citation_repair_apply.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    citation_repair_apply.add_argument("--dry-run", action="store_true", help="Report repairs without editing manuscript files.")

    citation_reaudit = subparsers.add_parser("re-audit-citations", help="Rerun citation audit after repair and write final report if passed.")
    citation_reaudit.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    citation_loop = subparsers.add_parser("run-citation-repair-loop", help="Iterate citation audit, repair planning, repair application, and final re-audit.")
    citation_loop.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    citation_loop.add_argument("--max-iterations", type=int, default=3, help="Maximum repair iterations before stopping.")

    diagnose = subparsers.add_parser("diagnose-gate-failures", help="Convert failed gates into actionable revision issues.")
    diagnose.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    review = subparsers.add_parser("review-draft", help="Run a reviewer-style manuscript pass and write review artifacts.")
    review.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    readiness = subparsers.add_parser("assess-publication-readiness", help="Assess target-journal publication readiness and reviewer-style risk.")
    readiness.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    review_gaps = subparsers.add_parser("discover-review-workflow-gaps", help="Discover discipline-specific reviewer-engineering workflow gaps.")
    review_gaps.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    review_engineering = subparsers.add_parser("propose-review-engineering-plan", help="Propose a discipline-specific reviewer-engineering plan.")
    review_engineering.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    statistical_rescue = subparsers.add_parser("recommend-statistical-revision", help="Recommend statistical rescue routes for weak data or unsupported results.")
    statistical_rescue.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    analysis_revision = subparsers.add_parser("prepare-analysis-revision", help="Convert review/rescue advice into executable analysis tasks and data-feasibility checks.")
    analysis_revision.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    discover_repos = subparsers.add_parser("discover-research-repos", help="Discover metadata-only public research-code repository candidates.")
    discover_repos.add_argument("--output-root", required=True, help="Directory for research_code_mining reports.")
    discover_repos.add_argument("--discipline", required=True, help="Target discipline module, for example geography or machine_learning.")
    discover_repos.add_argument("--query", required=True, help="Research-code discovery query.")
    discover_repos.add_argument("--from-json", default=None, help="Offline GitHub-search-style JSON list or payload.")
    discover_repos.add_argument("--limit", type=int, default=30, help="Maximum repositories to keep.")

    enrich_code = subparsers.add_parser("enrich-literature-code-leads", help="Attach metadata-only GitHub and Zenodo code-source leads to retained literature.")
    enrich_code.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    enrich_code.add_argument("--work-selection", default="retained,anchor,user_selected", help="Comma-separated work selection: retained, anchor, user_selected, or all.")
    enrich_code.add_argument("--providers", default="github,zenodo", help="Comma-separated providers.")
    enrich_code.add_argument("--selection-mode", default="knowledge_base", choices=["knowledge_base", "plugin_candidate", "reproduction", "historical_reference", "citation_only"])
    enrich_code.add_argument("--metadata-only", action="store_true", default=True, help="Required metadata-only mode; source code is never downloaded by this command.")
    enrich_code.add_argument("--github-metadata", default=None, help="Optional offline GitHub metadata fixture/export.")
    enrich_code.add_argument("--zenodo-metadata", default=None, help="Optional offline Zenodo metadata fixture/export.")
    enrich_code.add_argument("--include-online", action="store_true", help="Query public provider APIs in addition to explicit links and offline metadata.")
    enrich_code.add_argument("--max-candidates", type=int, default=30)

    discover_code = subparsers.add_parser("discover-research-code", help="Discover metadata-only GitHub/Zenodo research-code candidates for a query.")
    discover_code.add_argument("--output-root", required=True)
    discover_code.add_argument("--discipline", required=True)
    discover_code.add_argument("--query", required=True)
    discover_code.add_argument("--providers", default="github,zenodo")
    discover_code.add_argument("--paper-doi", default=None)
    discover_code.add_argument("--selection-mode", default="knowledge_base", choices=["knowledge_base", "plugin_candidate", "reproduction", "historical_reference", "citation_only"])
    discover_code.add_argument("--github-metadata", default=None)
    discover_code.add_argument("--zenodo-metadata", default=None)

    inspect_code_source = subparsers.add_parser("inspect-research-code-source", help="Inspect one code-source candidate without downloading or executing it.")
    inspect_code_source.add_argument("--project", required=True)
    inspect_code_source.add_argument("--candidate-id", required=True)

    fetch_code_archive = subparsers.add_parser("fetch-research-code-archive", help="Download and statically inspect one confirmed code archive; never execute it.")
    fetch_code_archive.add_argument("--project", required=True)
    fetch_code_archive.add_argument("--candidate-id", required=True)
    fetch_code_archive.add_argument("--confirm-download", action="store_true", help="Explicitly authorize the download for this candidate.")

    session_preflight = subparsers.add_parser("session-preflight", help="Verify source, wheel, Skill, schema, and plugin runtime identity before project work.")
    session_preflight.add_argument("--project", required=True)
    session_preflight.add_argument(
        "--accept-runtime-update",
        action="store_true",
        help="Explicitly accept the current runtime identity and write a migration receipt when the project lock differs.",
    )

    score_repos = subparsers.add_parser("score-research-repos", help="Score discovered research-code repositories for reusable plugin mining.")
    score_repos.add_argument("--input", required=True, help="Path to *_repo_candidates.json.")
    score_repos.add_argument("--output-root", default=None, help="Optional output root for scored reports.")

    extract_candidates = subparsers.add_parser("extract-plugin-candidates", help="Extract metadata-only plugin candidate reports from scored repositories.")
    extract_candidates.add_argument("--input", required=True, help="Path to *_scored_repos.json.")
    extract_candidates.add_argument("--output-root", default=None, help="Optional output root for candidate reports.")
    extract_candidates.add_argument("--top-n", type=int, default=5, help="Number of top repositories to convert into candidate reports.")

    inspect_repo = subparsers.add_parser("inspect-research-repo", help="Inspect repository tree/docs for a mined candidate without copying source code.")
    inspect_repo.add_argument("--candidate", required=True, help="Path to candidate directory or candidate_manifest.json.")
    inspect_repo.add_argument("--local-repo", required=True, help="Local repository checkout to inspect.")
    inspect_repo.add_argument("--output-root", default=None, help="Optional output root for inspection reports.")
    inspect_repo.add_argument("--mode", default="tree", choices=["tree", "docs", "tree_docs"], help="Inspection depth; source code is not copied in any mode.")

    workflow_map = subparsers.add_parser("map-repository-workflow", help="Map repository structure inspection to reusable workflow roles.")
    workflow_map.add_argument("--inspection", required=True, help="Path to repository_structure.json.")
    workflow_map.add_argument("--output-root", default=None, help="Optional output root for workflow maps.")

    bootstrap_foundation = subparsers.add_parser("bootstrap-discipline-foundation", help="Write candidate-only discipline foundation suggestions from a workflow map.")
    bootstrap_foundation.add_argument("--workflow-map", required=True, help="Path to workflow_map.json.")
    bootstrap_foundation.add_argument("--output-root", default=None, help="Optional output root for foundation candidate reports.")

    capture_learning = subparsers.add_parser("capture-discipline-learning", help="Capture reusable discipline-learning candidates from a local paper project.")
    capture_learning.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    capture_learning.add_argument("--output-root", default=None, help="Optional output root; defaults to the project directory.")

    classify_reusability = subparsers.add_parser("classify-plugin-reusability", help="Classify a learning candidate as reusable, project-specific, or requiring generalization.")
    classify_reusability.add_argument("--candidate", required=True, help="Path to plugin_candidates/from_loop/<discipline>/<candidate_id>.")

    summarize_candidate = subparsers.add_parser("summarize-plugin-candidates", help="Summarize reusable discipline plugin candidates from a completed project.")
    summarize_candidate.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    summarize_candidate.add_argument("--source-file", default=None, help="Optional project or external source code file to summarize.")
    summarize_candidate.add_argument("--method", default=None, help="Optional method/template keyword to focus candidate generation.")

    snapshot_skills = subparsers.add_parser("snapshot-skill-source", help="Write a metadata-only snapshot of a local skill/source tree or supported public registry.")
    snapshot_skills.add_argument("--source-root", default=None, help="Folder containing SKILL.md, Markdown, or text skill/source files.")
    snapshot_skills.add_argument("--path", default=None, help="Alias for --source-root, useful for local-skill adapters.")
    snapshot_skills.add_argument("--adapter", default=None, help="Adapter label, e.g. academicforge or local-skill. Alias for --source.")
    snapshot_skills.add_argument("--repo", default=None, help="Optional upstream repo. The AcademicForge adapter reads public registry/classification metadata but never clones source repositories.")
    snapshot_skills.add_argument("--ref", default=None, help="Optional upstream branch/tag/commit recorded as provenance metadata only.")
    snapshot_skills.add_argument("--source", default="local_skill", help="Source label, e.g. academicforge or local_skill.")
    snapshot_skills.add_argument("--source-url", default=None, help="Optional upstream URL. Supported registry adapters may read public metadata from it; local adapters record it as provenance only.")
    snapshot_skills.add_argument("--source-ref", default=None, help="Optional upstream branch/tag/commit recorded as provenance metadata only.")
    snapshot_skills.add_argument("--output-root", default=None, help="Optional output root for adapter reports.")
    snapshot_skills.add_argument("--no-hashes", action="store_true", help="Skip SHA-256 file hashes in the metadata snapshot.")

    inspect_skills = subparsers.add_parser("inspect-skill-source", help="Inspect a local skill/source tree without copying source text.")
    inspect_skills.add_argument("--source-root", default=None, help="Folder containing SKILL.md, Markdown, or text skill/source files.")
    inspect_skills.add_argument("--path", default=None, help="Alias for --source-root.")
    inspect_skills.add_argument("--snapshot", default=None, help="Optional SNAPSHOT.json from snapshot-skill-source.")
    inspect_skills.add_argument("--adapter", default=None, help="Adapter label, e.g. academicforge or local-skill. Alias for --source.")
    inspect_skills.add_argument("--source", default="local_skill", help="Source label, e.g. academicforge or local_skill.")
    inspect_skills.add_argument("--source-url", default=None, help="Optional upstream URL recorded as provenance metadata only.")
    inspect_skills.add_argument("--source-ref", default=None, help="Optional upstream branch/tag/commit recorded as provenance metadata only.")
    inspect_skills.add_argument("--output-root", default=None, help="Optional output root for adapter reports.")

    index_skills = subparsers.add_parser("index-skill-source", help="Build a metadata index for skill/source files before extraction.")
    index_skills.add_argument("--source-root", default=None, help="Folder containing SKILL.md, Markdown, or text skill/source files.")
    index_skills.add_argument("--path", default=None, help="Alias for --source-root.")
    index_skills.add_argument("--snapshot", default=None, help="Optional SNAPSHOT.json from snapshot-skill-source.")
    index_skills.add_argument("--inspection", default=None, help="Optional source_inspection.json from inspect-skill-source.")
    index_skills.add_argument("--adapter", default=None, help="Adapter label, e.g. academicforge or local-skill. Alias for --source.")
    index_skills.add_argument("--source", default="local_skill", help="Source label, e.g. academicforge or local_skill.")
    index_skills.add_argument("--discipline", default="auto", help="Target discipline or auto.")
    index_skills.add_argument("--source-url", default=None, help="Optional upstream URL recorded as provenance metadata only.")
    index_skills.add_argument("--source-ref", default=None, help="Optional upstream branch/tag/commit recorded as provenance metadata only.")
    index_skills.add_argument("--output-root", default=None, help="Optional output root for adapter reports.")

    classify_skills = subparsers.add_parser("classify-skill-source", help="Classify skill/source files into discipline-plugin, support, external-only, or reject routes.")
    classify_skills.add_argument("--source-root", default=None, help="Folder containing SKILL.md, Markdown, or text skill/source files.")
    classify_skills.add_argument("--path", default=None, help="Alias for --source-root.")
    classify_skills.add_argument("--snapshot", default=None, help="Optional SNAPSHOT.json from snapshot-skill-source.")
    classify_skills.add_argument("--inspection", default=None, help="Optional source_inspection.json from inspect-skill-source.")
    classify_skills.add_argument("--index", default=None, help="Optional SKILL_INDEX.json from index-skill-source.")
    classify_skills.add_argument("--all", action="store_true", help="Classify all indexed records. Current implementation always classifies all local source files.")
    classify_skills.add_argument("--adapter", default=None, help="Adapter label, e.g. academicforge or local-skill. Alias for --source.")
    classify_skills.add_argument("--source", default="local_skill", help="Source label, e.g. academicforge or local_skill.")
    classify_skills.add_argument("--discipline", default="auto", help="Target discipline or auto.")
    classify_skills.add_argument("--source-url", default=None, help="Optional upstream URL recorded as provenance metadata only.")
    classify_skills.add_argument("--source-ref", default=None, help="Optional upstream branch/tag/commit recorded as provenance metadata only.")
    classify_skills.add_argument("--output-root", default=None, help="Optional output root for adapter reports.")

    map_skills = subparsers.add_parser("map-skill-capabilities", help="Map skill/source files to discipline plugin and support-layer targets.")
    map_skills.add_argument("--source-root", default=None, help="Folder containing SKILL.md, Markdown, or text skill/source files.")
    map_skills.add_argument("--path", default=None, help="Alias for --source-root.")
    map_skills.add_argument("--snapshot", default=None, help="Optional SNAPSHOT.json from snapshot-skill-source.")
    map_skills.add_argument("--inspection", default=None, help="Optional source_inspection.json from inspect-skill-source.")
    map_skills.add_argument("--index", default=None, help="Optional SKILL_INDEX.json from index-skill-source.")
    map_skills.add_argument("--candidates", default=None, help="Compatibility placeholder for candidate directory inputs; current mapper uses source-root metadata.")
    map_skills.add_argument("--against", default=None, help="Compatibility placeholder for target discipline_modules root.")
    map_skills.add_argument("--adapter", default=None, help="Adapter label, e.g. academicforge or local-skill. Alias for --source.")
    map_skills.add_argument("--source", default="local_skill", help="Source label, e.g. academicforge or local_skill.")
    map_skills.add_argument("--discipline", default="auto", help="Target discipline or auto.")
    map_skills.add_argument("--source-url", default=None, help="Optional upstream URL recorded as provenance metadata only.")
    map_skills.add_argument("--source-ref", default=None, help="Optional upstream branch/tag/commit recorded as provenance metadata only.")
    map_skills.add_argument("--output-root", default=None, help="Optional output root for adapter reports.")

    review_rule_signals = subparsers.add_parser("extract-review-rule-signals", help="Scan all skill/source records for review-rule backflow signals.")
    review_rule_signals.add_argument("--source-root", default=None, help="Folder containing SKILL.md, Markdown, or text skill/source files.")
    review_rule_signals.add_argument("--path", default=None, help="Alias for --source-root.")
    review_rule_signals.add_argument("--snapshot", default=None, help="Optional SNAPSHOT.json from snapshot-skill-source.")
    review_rule_signals.add_argument("--inspection", default=None, help="Optional source_inspection.json from inspect-skill-source.")
    review_rule_signals.add_argument("--index", default=None, help="Optional SKILL_INDEX.json from index-skill-source.")
    review_rule_signals.add_argument("--adapter", default=None, help="Adapter label, e.g. academicforge or local-skill. Alias for --source.")
    review_rule_signals.add_argument("--source", default="local_skill", help="Source label, e.g. academicforge or local_skill.")
    review_rule_signals.add_argument("--discipline", default="auto", help="Target discipline or auto.")
    review_rule_signals.add_argument("--source-url", default=None, help="Optional upstream URL recorded as provenance metadata only.")
    review_rule_signals.add_argument("--source-ref", default=None, help="Optional upstream branch/tag/commit recorded as provenance metadata only.")
    review_rule_signals.add_argument("--output-root", default=None, help="Optional output root for signal reports.")

    skill_capabilities = subparsers.add_parser("extract-skill-capabilities", help="Extract Draftpaper-loop candidate plugins from a local skill/source text file.")
    skill_capabilities.add_argument("--source-file", default=None, help="Path to SKILL.md, README, or source description to inspect.")
    skill_capabilities.add_argument("--path", default=None, help="Alias for --source-file when extracting a single skill file.")
    skill_capabilities.add_argument("--snapshot", default=None, help="Optional SNAPSHOT.json. If it contains one record, that file is used; otherwise use compile-skill-source for batch extraction.")
    skill_capabilities.add_argument("--adapter", default=None, help="Adapter label, e.g. academicforge or local-skill. Alias for --source.")
    skill_capabilities.add_argument("--source", default="local_skill", help="Source label, e.g. academicforge or local_skill.")
    skill_capabilities.add_argument("--skill-id", default=None, help="Stable skill id; defaults to the source file stem.")
    skill_capabilities.add_argument("--discipline", default="auto", help="Target discipline or auto.")
    skill_capabilities.add_argument("--output-root", default=None, help="Optional output root for candidate reports.")

    compile_skills = subparsers.add_parser("compile-skill-source", help="Batch-convert a skill/source folder into candidate-only Draftpaper-loop plugin reports.")
    compile_skills.add_argument("--source-root", default=None, help="Folder containing SKILL.md, Markdown, or text skill/source files.")
    compile_skills.add_argument("--path", default=None, help="Alias for --source-root.")
    compile_skills.add_argument("--snapshot", default=None, help="Optional SNAPSHOT.json from snapshot-skill-source.")
    compile_skills.add_argument("--inspection", default=None, help="Optional source_inspection.json from inspect-skill-source.")
    compile_skills.add_argument("--index", default=None, help="Optional SKILL_INDEX.json from index-skill-source.")
    compile_skills.add_argument("--adapter", default=None, help="Adapter label, e.g. academicforge or local-skill. Alias for --source.")
    compile_skills.add_argument("--source", default="local_skill", help="Source label, e.g. academicforge or local_skill.")
    compile_skills.add_argument("--discipline", default="auto", help="Target discipline or auto.")
    compile_skills.add_argument("--output-root", default=None, help="Optional output root for candidate reports.")
    compile_skills.add_argument("--stop-after", default="candidate", choices=["candidate"], help="Current command is candidate-only and never promotes plugins.")
    compile_skills.add_argument("--jobs", type=int, default=1, help="Reserved for future parallel extraction; current runner is sequential.")
    compile_skills.add_argument("--resume", action="store_true", help="Reserved flag recorded in the compile report.")

    generalize_candidate = subparsers.add_parser("generalize-plugin-candidate", help="Convert a project-specific candidate into a generic plugin template.")
    generalize_candidate.add_argument("--candidate", required=True, help="Path to plugin_candidates/<discipline>/<candidate_id>.")

    validate_candidate = subparsers.add_parser("validate-plugin-candidate", help="Run privacy, genericity, overlap, and fixture checks for a plugin candidate.")
    validate_candidate.add_argument("--candidate", required=True, help="Path to plugin_candidates/<discipline>/<candidate_id>.")

    promote_candidate = subparsers.add_parser("promote-plugin-candidate", help="Prepare or perform a guarded formal discipline plugin promotion.")
    promote_candidate.add_argument("--candidate", required=True, help="Path to a validated formal plugin candidate.")
    promote_candidate.add_argument("--require-human-confirmation", action="store_true", help="Required acknowledgement before any promotion plan or write.")
    promote_candidate.add_argument("--dry-run", action="store_true", default=True, help="Write promotion_plan.json without modifying discipline_modules. This is the default.")
    promote_candidate.add_argument("--write", action="store_true", help="Actually copy generalized files into the target discipline module directory.")
    promote_candidate.add_argument("--target-root", default=None, help="Optional discipline_modules root for testing or controlled promotion.")

    package_candidate = subparsers.add_parser("package-plugin-contribution", help="Package a validated plugin candidate for fork/PR review.")
    package_candidate.add_argument("--candidate", required=True, help="Path to plugin_candidates/<discipline>/<candidate_id>.")

    preflight_package = subparsers.add_parser("preflight-plugin-contribution", help="Validate a packaged plugin contribution before fork/PR review.")
    preflight_package.add_argument("--package", required=True, help="Path to a generated contribution_package directory.")

    review_package = subparsers.add_parser("review-plugin-contribution", help="Create a read-only maintainer review report for a packaged plugin contribution.")
    review_package.add_argument("--package", required=True, help="Path to a generated contribution_package directory, candidate root, or generalized_template child.")

    github_guide = subparsers.add_parser("write-github-contribution-guide", help="Write project-local fork/PR contribution guide for plugin candidates.")
    github_guide.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    revision_plan = subparsers.add_parser("generate-revision-plan", help="Merge gate, reviewer, readiness, and statistical-rescue issues into a revision plan.")
    revision_plan.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    apply = subparsers.add_parser("apply-revision", help="Safely apply a revision plan by marking affected stages stale.")
    apply.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    apply.add_argument("--issue-id", action="append", default=[], help="Only apply selected revision issue ids. Can be repeated.")
    apply.add_argument("--dry-run", action="store_true", help="Report affected stages without marking them stale.")

    rereview = subparsers.add_parser("re-review", help="Rerun gate diagnosis, reviewer pass, and revision planning.")
    rereview.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    style = subparsers.add_parser("learn-writing-style-from-draft", help="Extract non-verbatim writing style signals from an approved draft.")
    style.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    style.add_argument("--draft", required=True, help="Path to an approved .tex or text draft used only for style-signal extraction.")

    doctor = subparsers.add_parser("doctor", help="Run a deterministic, read-only Draftpaper-loop environment and project diagnosis.")
    doctor.add_argument("--project", default=None)
    doctor.add_argument("--json", action="store_true", help="Emit machine-readable JSON (the default CLI representation).")
    doctor.add_argument("--explain", action="store_true", help="Include artifact dependency and failure-route details.")
    evidence_audit = subparsers.add_parser(
        "audit-evidence-identity",
        help="Read-only audit of metric, count, run-bundle, and figure-trace identity with migration routing.",
    )
    evidence_audit.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    token_report = subparsers.add_parser("token-report", help="Summarize recorded and estimated project token usage without inventing provider prices.")
    token_report.add_argument("--project", required=True)
    start = subparsers.add_parser("start", help="Create a project and report the first executable workflow action.")
    start.add_argument("--root", "--projects-root", dest="root", default=None)
    start.add_argument("--idea", required=True)
    start.add_argument("--field", required=True)
    start.add_argument("--target-journal", default="General Academic Journal")
    for name, help_text in (
        ("continue", "Report the next executable workflow action."),
        ("review", "Report the current review and release action."),
        ("recover", "Diagnose a failed or inconsistent project and return safe recovery commands."),
    ):
        macro = subparsers.add_parser(name, help=help_text)
        macro.add_argument("--project", required=True)
    revise_macro = subparsers.add_parser("revise", help="Prepare a precise author revision request by line range or stable paragraph ID.")
    revise_macro.add_argument("--project", required=True)
    revise_macro.add_argument("--at", default=None)
    revise_macro.add_argument("--paragraph", default=None)
    revise_macro.add_argument("--instruction", required=True)
    revise_macro.add_argument("--content-file", default=None)
    revise_macro.add_argument("--expect-text", default=None, help="Expected current paragraph text used as a stable write guard.")
    revise_macro.add_argument("--expect-text-file", default=None, help="Project-local file containing the expected current paragraph text.")
    revise_macro.add_argument("--expect-sha256", default=None, help="Expected current paragraph SHA-256 from the source map.")
    revise_macro.add_argument("--occurrence", type=int, default=None, help="One-based occurrence when expected text is repeated.")
    revise_macro.add_argument("--operation", choices=["insert_before", "insert_after", "replace", "delete"], default="replace")
    revise_macro.add_argument("--mode", choices=["exact_text", "instruction_to_codex"], default="instruction_to_codex")
    revise_macro.add_argument("--change-class", choices=list(CANONICAL_CHANGE_CLASSES), default=None)
    verify_action = subparsers.add_parser("verify-next-action", help="Verify that status recommends a registered command with satisfiable CLI preconditions.")
    verify_action.add_argument("--project", required=True)
    rebuild = subparsers.add_parser("rebuild-derived", help="Plan rebuilds for current derived artifacts without touching canonical scientific sources.")
    rebuild.add_argument("--project", required=True)
    rebuild.add_argument("--dry-run", action="store_true", default=True)
    rebase = subparsers.add_parser("rebase-project-passport", help="Protected legacy recovery for rebasing a copied project passport from its origin.")
    rebase.add_argument("--project", required=True)
    rebase.add_argument("--from", dest="origin", required=True)
    rebase.add_argument("--confirm", action="store_true")

    independent = subparsers.add_parser("prepare-independent-manuscript-review", help="Freeze one anonymized generated manuscript bundle for independent reviewers.")
    independent.add_argument("--project", required=True)
    record_independent = subparsers.add_parser("record-independent-manuscript-review", help="Record one independent review against the frozen single-manuscript bundle.")
    record_independent.add_argument("--project", required=True)
    record_independent.add_argument("--reviewer", required=True)
    record_independent.add_argument("--input", required=True)
    release_review = subparsers.add_parser("assess-manuscript-quality-release", help="Aggregate independent single-manuscript reviews into a release decision.")
    release_review.add_argument("--project", required=True)

    source_map = subparsers.add_parser("build-manuscript-source-map", help="Build stable paragraph and LaTeX line anchors for author revisions.")
    source_map.add_argument("--project", required=True)
    completion_template = subparsers.add_parser(
        "prepare-manuscript-completion",
        help="Write a structured final-author completion template and journal missing-field report.",
    )
    completion_template.add_argument("--project", required=True)
    completion_status = subparsers.add_parser(
        "manuscript-completion-status",
        help="Report final-author metadata readiness without changing the project.",
    )
    completion_status.add_argument("--project", required=True)
    completion_preview = subparsers.add_parser(
        "preview-manuscript-completion",
        help="Build a batch metadata, reference, section, LaTeX and PDF overlay without changing canonical sources.",
    )
    completion_preview.add_argument("--project", required=True)
    completion_preview.add_argument("--input", required=True)
    completion_apply = subparsers.add_parser(
        "apply-manuscript-completion",
        help="Apply one human-accepted completion packet after packet-hash verification.",
    )
    completion_apply.add_argument("--project", required=True)
    completion_apply.add_argument("--packet-id", required=True)
    completion_apply.add_argument("--packet-hash", required=True)
    completion_rollback = subparsers.add_parser(
        "rollback-manuscript-completion",
        help="Rollback an applied completion transaction while all after-hashes remain current.",
    )
    completion_rollback.add_argument("--project", required=True)
    completion_rollback.add_argument("--transaction-id", required=True)
    preview_revision = subparsers.add_parser("preview-manuscript-revision", help="Preview a line- or paragraph-anchored manuscript revision without applying it.")
    preview_revision.add_argument("--project", required=True)
    preview_revision.add_argument("--at", default=None)
    preview_revision.add_argument("--paragraph", default=None)
    preview_revision.add_argument("--instruction", required=True)
    preview_revision.add_argument("--content-file", default=None)
    preview_revision.add_argument("--expect-text", default=None, help="Expected current paragraph text used as a stable write guard.")
    preview_revision.add_argument("--expect-text-file", default=None, help="Project-local file containing the expected current paragraph text.")
    preview_revision.add_argument("--expect-sha256", default=None, help="Expected current paragraph SHA-256 from the source map.")
    preview_revision.add_argument("--occurrence", type=int, default=None, help="One-based occurrence when expected text is repeated.")
    preview_revision.add_argument("--operation", choices=["insert_before", "insert_after", "replace", "delete"], default="replace")
    preview_revision.add_argument("--mode", choices=["exact_text", "instruction_to_codex"], default="instruction_to_codex")
    preview_revision.add_argument("--change-class", choices=list(CANONICAL_CHANGE_CLASSES), default=None)
    apply_manuscript = subparsers.add_parser("apply-manuscript-revision", help="Apply a previously previewed revision after hash and anchor verification.")
    apply_manuscript.add_argument("--project", required=True)
    apply_manuscript.add_argument("--request-id", required=True)
    rollback_manuscript = subparsers.add_parser("rollback-manuscript-revision", help="Rollback one accepted manuscript revision from its ledger snapshot.")
    rollback_manuscript.add_argument("--project", required=True)
    rollback_manuscript.add_argument("--revision-id", required=True)
    metadata = subparsers.add_parser("set-manuscript-metadata", help="Set structured author, affiliation, funding, acknowledgement, data and code metadata.")
    metadata.add_argument("--project", required=True)
    metadata.add_argument("--input", required=True)
    custom_reference = subparsers.add_parser("add-custom-reference", help="Add a structured user reference through registry, summary and audit preparation.")
    custom_reference.add_argument("--project", required=True)
    custom_reference.add_argument("--input", required=True)

    eval_command = subparsers.add_parser("eval", help="Capture, baseline, replay, or gate a privacy-preserving software regression case.")
    eval_actions = eval_command.add_subparsers(dest="eval_action", required=True)
    eval_capture = eval_actions.add_parser("capture", help="Capture project topology, schemas, state and invariants without scientific content.")
    eval_capture.add_argument("--project", required=True)
    eval_capture.add_argument("--case", required=True)
    eval_baseline = eval_actions.add_parser("baseline", help="Create a locator-free software regression baseline from a capture.")
    eval_baseline.add_argument("--capture", required=True)
    eval_baseline.add_argument("--output", default=None)
    eval_replay = eval_actions.add_parser("replay", help="Replay a software regression baseline against a project.")
    eval_replay.add_argument("--project", required=True)
    eval_replay.add_argument("--baseline", required=True)
    eval_gate = eval_actions.add_parser("gate", help="Gate a replay report.")
    eval_gate.add_argument("--report", required=True)

    import_findings = subparsers.add_parser("import-review-findings", help="Import independent-review findings as candidate revision tasks without editing the manuscript.")
    import_findings.add_argument("--project", required=True)
    import_findings.add_argument("--review", default=None)
    list_tasks = subparsers.add_parser("list-revision-tasks", help="List review-derived manuscript revision tasks.")
    list_tasks.add_argument("--project", required=True)
    prepare_revision = subparsers.add_parser("prepare-revision", help="Prepare a revision request from one review finding.")
    prepare_revision.add_argument("--project", required=True)
    prepare_revision.add_argument("--task", required=True)
    preview_compat = subparsers.add_parser("preview-revision", help="Inspect a prepared revision request and its unified diff.")
    preview_compat.add_argument("--project", required=True)
    preview_compat.add_argument("--revision", required=True)
    accept_compat = subparsers.add_parser("accept-revision", help="Accept a prepared revision after hash verification.")
    accept_compat.add_argument("--project", required=True)
    accept_compat.add_argument("--revision", required=True)

    install_skill = subparsers.add_parser("install-skill", help="Install the wheel-packaged canonical Draftpaper workflow skill into CODEX_HOME.")
    install_skill.add_argument("--destination")
    install_skill.add_argument("--force", action="store_true")
    skill_doctor = subparsers.add_parser("skill-doctor", help="Compare the installed Draftpaper workflow skill with the canonical package resource.")
    skill_doctor.add_argument("--destination")
    plugin_snapshot = subparsers.add_parser("snapshot-plugin-catalog", help="Freeze the current plugin manifests, templates, execution contracts, and catalog hash for a project run.")
    plugin_snapshot.add_argument("--project", required=True)
    plugin_diff = subparsers.add_parser("validate-plugin-contract-diff", help="Compare the active plugin catalog with the project planning snapshot.")
    plugin_diff.add_argument("--project", required=True)
    runtime_audit = subparsers.add_parser("audit-workflow-runtime", help="Detect command loops, repeated expensive inputs, stale churn, and oversized writing packets.")
    runtime_audit.add_argument("--project", required=True)
    submit_job_parser = subparsers.add_parser("submit-job", help="Submit an allowlisted Draftpaper command to the durable local scientific job controller.")
    submit_job_parser.add_argument("--project", required=True)
    submit_job_parser.add_argument("--command", dest="job_command", required=True)
    submit_job_parser.add_argument("--arguments-json")
    submit_job_parser.add_argument("--idempotency-key")
    submit_job_parser.add_argument("--timeout-seconds", type=int)
    job_status_parser = subparsers.add_parser("job-status", help="Read one persistent scientific job without changing its state.")
    job_status_parser.add_argument("--project", required=True)
    job_status_parser.add_argument("--job-id", required=True)
    job_cancel_parser = subparsers.add_parser("job-cancel", help="Cancel one persistent scientific job and its process tree.")
    job_cancel_parser.add_argument("--project", required=True)
    job_cancel_parser.add_argument("--job-id", required=True)
    notifications_parser = subparsers.add_parser("job-notifications", help="Read persistent job completion and failure notifications.")
    notifications_parser.add_argument("--project", required=True)
    notifications_parser.add_argument("--job-id")
    recover_jobs_parser = subparsers.add_parser("recover-jobs", help="Classify running persistent jobs after a terminal or MCP restart.")
    recover_jobs_parser.add_argument("--project", required=True)
    mcp_install_parser = subparsers.add_parser("mcp-install", help="Write a portable local stdio MCP configuration without an absolute working directory.")
    mcp_install_parser.add_argument("--output", required=True)
    subparsers.add_parser("mcp-doctor", help="Validate MCP dependencies, tool schemas, workflow skill hash, and security exposure policy.")

    parser_commands = set(subparsers.choices)
    missing_specs = sorted(parser_commands - set(COMMAND_SPECS))
    missing_parsers = sorted(set(COMMAND_SPECS) - parser_commands)
    if missing_specs:
        raise RuntimeError("CLI commands are missing CommandSpec declarations: " + ", ".join(missing_specs))
    if missing_parsers:
        raise RuntimeError("Registered CLI commands are missing parser definitions: " + ", ".join(missing_parsers))
    return parser


def _main_without_passport_refresh(
    argv: list[str] | None = None,
    *,
    result_sink: list[tuple[Any, dict[str, Any], int]] | None = None,
) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        registered = dispatch_registered_command(args)
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    if registered is not None:
        result, exit_code = registered
        if result_sink is not None:
            result_sink.append((args, dict(result), exit_code))
        output_stream = result.pop("_dpl_output_stream", "stdout")
        from .cli_output import prioritize_human_review

        print(json.dumps(prioritize_human_review(result), ensure_ascii=True), file=sys.stderr if output_stream == "stderr" else sys.stdout)
        return exit_code

    print(json.dumps({"status": "error", "message": f"Registered handler missing for {args.command}."}, ensure_ascii=True), file=sys.stderr)
    return 1


_READ_ONLY_PROJECT_COMMANDS = {
    "load-project",
    "validate-project",
    "inspect-project-migration",
    "plan-project-version",
    "validate-project-version",
    "inspect-system-of-record",
    "status",
    "run-pipeline",
    "detect-artifact-drift",
    "review-policy-status",
    "evaluate-checkpoint-authority",
    "show-stage-activity",
    "show-scientific-baseline",
    "show-checkpoint-summary",
    "show-checkpoint-audit",
    "compare-checkpoint-decision",
    "explain-reconfirmation",
    "validate-checkpoint-readability",
    "show-confirmation-continuity",
    "inspect-review-evidence",
    "audit-checkpoint-v5-migration",
    "shadow-checkpoint-v5",
    "shadow-checkpoint-v6",
}


def main(argv: list[str] | None = None) -> int:
    """Run one CLI command and commit managed writes independently of scientific outcome."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    compact_requested = "--compact" in raw_argv
    full_json = "--json-full" in raw_argv or "--verbose" in raw_argv or (not sys.stdout.isatty() and not compact_requested)
    raw_argv = [item for item in raw_argv if item not in {"--json-full", "--verbose", "--compact"}]
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    project = getattr(args, "project", None)
    command = str(getattr(args, "command", "") or "")
    spec = command_spec(command)
    mutates_project = bool(project and (spec.mutates_project if spec else command not in _READ_ONLY_PROJECT_COMMANDS))
    # Drift reconciliation is the guarded recovery command that resolves the
    # pending packet created by sync-artifact-stale. It must be allowed to run
    # while drift is present; otherwise the recovery route deadlocks behind the
    # very preflight check it is meant to clear.
    allows_preexisting_drift = command in {
        "sync-artifact-stale",
        "reconcile-project-drift",
        "rebase-project-passport",
        "session-preflight",
    }
    preexisting_drift = False
    if mutates_project:
        try:
            preexisting_drift = detect_artifact_drift(project).get("status") == "drift_detected"
        except (ArtifactDriftError, PassportError, ProjectStateError, OSError):
            preexisting_drift = True

    if mutates_project and preexisting_drift and not allows_preexisting_drift:
        message = "Project artifacts changed outside the managed command transaction. Synchronize stale state before retrying."
        try:
            record_command_transaction(
                project,
                command=command,
                scientific_exit_code=3,
                transaction_status="blocked_preexisting_drift",
                baseline_clean=False,
                message=message,
            )
        except (PassportError, ProjectStateError, OSError):
            pass
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "preexisting_artifact_drift",
                    "message": message,
                    "next_command": f'python -m draftpaper_cli.cli sync-artifact-stale --project "{project}"',
                },
                ensure_ascii=True,
            ),
            file=sys.stderr,
        )
        return 3

    if mutates_project and project and command not in {"session-preflight", "sync-artifact-stale", "rebase-project-passport"}:
        try:
            from .runtime_handshake import check_runtime_for_command

            runtime_guard = check_runtime_for_command(project, command)
        except (OSError, ValueError, RuntimeError) as exc:
            runtime_guard = {"status": "error", "reason": str(exc)}
        if runtime_guard.get("status") == "blocked":
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "reason": "runtime_identity_mismatch",
                        "runtime_preflight": runtime_guard,
                        "next_command": runtime_guard.get("next_command"),
                    },
                    ensure_ascii=True,
                ),
                file=sys.stderr,
            )
            return 3

    write_guard = None
    workflow_trace = None
    if mutates_project and spec is not None:
        try:
            write_guard = WriteSetGuard(project, spec)
        except (BoundaryViolation, OSError) as exc:
            print(json.dumps({"status": "boundary_violation", "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
            return 4
        preflight = write_guard.preflight()
        if preflight.get("status") != "passed":
            print(json.dumps(preflight, ensure_ascii=True), file=sys.stderr)
            return 4
        workflow_trace = begin_workflow_trace(
            project,
            command,
            vars(args),
            stage=spec.pipeline_stage or spec.formal_stage,
            action_kind="command",
        )

    captured = io.StringIO()
    execution_result: list[tuple[Any, dict[str, Any], int]] = []
    if full_json:
        exit_code = _main_without_passport_refresh(
            raw_argv,
            result_sink=execution_result,
        )
    else:
        with contextlib.redirect_stdout(captured):
            exit_code = _main_without_passport_refresh(
                raw_argv,
                result_sink=execution_result,
            )
        output = captured.getvalue().strip()
        if output:
            try:
                from .cli_output import compact_payload

                payload = json.loads(output.splitlines()[-1])
                print(json.dumps(compact_payload(payload), ensure_ascii=True))
            except (json.JSONDecodeError, TypeError, ValueError):
                print(output)
    command_args = execution_result[-1][0] if execution_result else args
    command_payload = execution_result[-1][1] if execution_result else {}

    if (
        not mutates_project
        and spec is not None
        and spec.mutates_project
        and exit_code == 0
        and command_payload.get("project_path")
    ):
        created_root = Path(str(command_payload["project_path"])).expanduser().resolve()
        changed_paths = tuple(
            relative
            for relative in ("idea/idea.md",)
            if (created_root / Path(*relative.split("/"))).is_file()
        )
        transaction_receipt = record_command_transaction(
            created_root,
            command=command,
            scientific_exit_code=exit_code,
            transaction_status="committed",
            baseline_clean=True,
            passport_event=f"cli:{command}",
        )
        dispatch_extensions_nonblocking(
            command_args,
            spec,
            command_payload,
            exit_code,
            project_override=created_root,
            changed_paths=changed_paths,
            transaction_receipt=transaction_receipt,
        )

    if mutates_project:
        actual_write_set: tuple[str, ...] = ()
        if write_guard is not None:
            assessment = write_guard.assess()
            if assessment.get("status") != "passed":
                assessment["rollback"] = write_guard.rollback_violations(assessment)
                try:
                    record_command_transaction(
                        project,
                        command=command,
                        scientific_exit_code=exit_code,
                        transaction_status=(
                            "boundary_violation_rolled_back"
                            if assessment["rollback"].get("status") == "rolled_back"
                            else "boundary_violation_rollback_incomplete"
                        ),
                        baseline_clean=not preexisting_drift,
                        message=json.dumps(assessment, ensure_ascii=True),
                    )
                except (PassportError, ProjectStateError, OSError):
                    pass
                print(json.dumps(assessment, ensure_ascii=True), file=sys.stderr)
                if workflow_trace is not None:
                    finish_workflow_trace(
                        project,
                        workflow_trace,
                        process_status="completed",
                        command_exit_code=4 if assessment["rollback"].get("status") == "rolled_back" else 5,
                        transaction_status=assessment["rollback"].get("status"),
                        scientific_decision="not_committed",
                        failure_class="write_boundary_violation",
                        action_kind="rollback",
                    )
                return 4 if assessment["rollback"].get("status") == "rolled_back" else 5
            actual_write_set = tuple(
                str(item) for item in assessment.get("actual_write_set") or ()
            )
        post_command_drift = True
        try:
            post_command_drift = detect_artifact_drift(project).get("status") == "drift_detected"
        except (ArtifactDriftError, PassportError, ProjectStateError, OSError):
            post_command_drift = True
        if exit_code != 0 and not post_command_drift:
            try:
                record_command_transaction(
                    project,
                    command=command,
                    scientific_exit_code=exit_code,
                    transaction_status="aborted_no_managed_writes",
                    baseline_clean=not preexisting_drift,
                    message="The command failed before changing any passport-managed artifact.",
                )
            except (PassportError, ProjectStateError, OSError):
                pass
            return exit_code
        event = f"cli:{command}" if exit_code == 0 else f"cli_nonzero:{command}"
        preserve_pending_drift = bool(command_payload.get("preserve_pending_drift"))
        try:
            if not preserve_pending_drift:
                refresh_project_passport(project, event=event)
        except (PassportError, ProjectStateError, OSError) as exc:
            try:
                record_command_transaction(
                    project,
                    command=command,
                    scientific_exit_code=exit_code,
                    transaction_status="passport_refresh_failed",
                    baseline_clean=not preexisting_drift,
                    passport_event=None if preserve_pending_drift else event,
                    message=str(exc),
                )
            except (PassportError, ProjectStateError, OSError):
                pass
            print(json.dumps({"status": "error", "message": f"Command completed but passport refresh failed: {exc}"}, ensure_ascii=True), file=sys.stderr)
            return 1
        try:
            transaction_receipt = record_command_transaction(
                project,
                command=command,
                scientific_exit_code=exit_code,
                transaction_status="committed_pending_reconciliation" if preserve_pending_drift else "committed",
                baseline_clean=not preexisting_drift,
                passport_event=None if preserve_pending_drift else event,
                stage=spec.pipeline_stage or spec.formal_stage if spec is not None else None,
                actual_write_set=actual_write_set,
                modified_paths=actual_write_set,
                reopen_required=bool(command_payload.get("reopen_required")),
                baseline_changed=bool(command_payload.get("baseline_changed")),
            )
        except (PassportError, ProjectStateError, OSError) as exc:
            print(json.dumps({"status": "error", "message": f"Command completed but transaction receipt failed: {exc}"}, ensure_ascii=True), file=sys.stderr)
            return 1
        if workflow_trace is not None:
            finish_workflow_trace(
                project,
                workflow_trace,
                process_status="completed",
                command_exit_code=exit_code,
                transaction_status="committed_pending_reconciliation" if preserve_pending_drift else "committed",
                scientific_decision="pass" if exit_code == 0 else "non_passing",
                failure_class=None if exit_code == 0 else "scientific_or_command_nonzero",
                action_kind="validate" if command.startswith(("validate", "assess", "audit", "review")) else "command",
                changed_paths=list(actual_write_set),
                validation_result_refs=[f"command:{command}"] if command.startswith(("validate", "assess", "audit")) else [],
                decision_refs=[f"transaction:{transaction_receipt.get('command_id')}"] if transaction_receipt.get("command_id") else [],
                user_visible_summary_fragment_zh=str(command_payload.get("summary") or command_payload.get("message") or ""),
            )
        if spec is not None:
            dispatch_extensions_nonblocking(
                command_args,
                spec,
                command_payload,
                exit_code,
                changed_paths=actual_write_set,
                transaction_receipt=transaction_receipt,
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
