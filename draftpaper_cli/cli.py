# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis_code import AnalysisCodeGenerationError, generate_analysis_code
from .analysis_revision import AnalysisRevisionError, prepare_analysis_revision
from .citation_audit import CitationAuditError, audit_citations
from .citation_repair import (
    CitationRepairError,
    apply_citation_repair,
    generate_citation_repair_plan,
    re_audit_citations,
    run_citation_repair_loop,
)
from .code_ownership import (
    CodeOwnershipError,
    build_code_provenance,
    classify_code_ownership,
    extract_method_formulas,
    route_stage_code,
    trace_figures_to_code,
)
from .claim_contract import ClaimContractError, apply_result_downgrade
from .core_evidence import CoreEvidenceError, assess_core_evidence
from .evidence_snapshot import EvidenceSnapshotMismatch, reopen_evidence_snapshot
from .data_acquisition import DataAcquisitionError, classify_data_access, prepare_data_acquisition
from .data_feasibility import DataGateError, assess_data_feasibility, assess_data_quality, build_data_writing_context, inventory_data, write_data
from .discussion import DiscussionCitationIntegrityError, MissingDiscussionInputsError, prepare_discussion_comparison, write_discussion
from .introduction import CitationIntegrityError, MissingIntroductionInputsError, write_introduction
from .integrity_gate import IntegrityGateError, run_integrity_gate
from .journal_profile import JournalProfileError, resolve_journal_template
from .latex_assembly import LatexAssemblyError, assemble_latex, compile_latex_pdf
from .literature_search import search_literature_for_project
from .manuscript_composer import SectionCompositionError, build_section_evidence_packet, submit_section_draft
from .manuscript_quality import assess_results_manuscript_quality
from .scientific_figure_quality import assess_scientific_figure_quality
from .results_semantic_repair import prepare_results_semantic_repair
from .paper_quality_parity import assess_paper_quality_parity
from .paper_narrative import PaperNarrativeError, build_paper_narrative, build_results_synthesis_plan, build_section_outline
from .writing_architecture import (
    WritingArchitectureError,
    assess_functional_quality_release,
    build_argument_matrices,
    build_panel_writing_contracts,
    build_section_lifecycles,
    prepare_panel_repair,
    prepare_scientific_editor,
    record_scientific_editor_revision,
    resolve_venue_style_adapter,
)
from .method_plan import MethodPlanError, collect_method_plan
from .method_blueprint import MethodBlueprintError, prepare_method_blueprint
from .method_feasibility import MethodFeasibilityError, assess_method_feasibility
from .figure_plan import FigurePlanError, plan_figures
from .figure_contract_gate import FigureContractGateError, assess_figure_contracts
from .figure_semantic_annotations import FigureSemanticAnnotationError, submit_figure_semantic_annotations
from .figure_plugin_trace import validate_figure_plugin_trace
from .figure_repair import FigureRepairError, diagnose_figure_execution, repair_figure_data, repair_figure_method
from .methods import MethodsGateError, build_method_writing_context, verify_methods, write_methods
from .observations import ObservationError, record_observation
from .orchestrator import OrchestratorError, checkpoint_project, resume_project, run_pipeline, status_project
from .passport import PassportError
from .plugin_candidates import (
    PluginCandidateError,
    classify_skill_source,
    compile_skill_source,
    extract_review_rule_signals,
    extract_skill_capabilities,
    generalize_plugin_candidate,
    index_skill_source,
    inspect_skill_source,
    map_skill_capabilities,
    package_plugin_contribution,
    preflight_plugin_contribution_package,
    promote_plugin_candidate,
    review_plugin_contribution_package,
    snapshot_skill_source,
    summarize_plugin_candidates,
    validate_plugin_candidate,
    write_github_contribution_guide,
)
from .project_scaffold import ProjectAlreadyExistsError, create_project
from .project_capability_audit import audit_project_capabilities
from .plugin_rescue import PluginRescueError, prepare_plugin_rescue, record_plugin_rescue_outcome
from .plugin_execution import PluginExecutionError, execute_data_plugins, execute_method_plugins
from .research_capabilities import assess_plugin_sufficiency, resolve_research_capabilities
from .project_state import (
    InvalidStageStatusError,
    ProjectStateError,
    UnknownStageError,
    load_project,
    mark_stage_stale,
    update_stage_status,
    validate_project,
)
from .quality_gate import QualityGateError, run_quality_check
from .research_code_mining import (
    ResearchCodeMiningError,
    bootstrap_discipline_foundation,
    capture_discipline_learning,
    classify_plugin_reusability,
    discover_research_repos,
    extract_plugin_candidates,
    inspect_research_repo,
    map_repository_workflow,
    score_research_repos,
)
from .research_plan import MissingReferencesError, NoveltyOverlapError, generate_research_plan
from .research_feasibility import ResearchFeasibilityError, assess_research_plan_feasibility, preflight_research_feasibility, revise_research_plan
from .review_revision import (
    ReviewRevisionError,
    apply_revision,
    assess_publication_readiness,
    diagnose_gate_failures,
    generate_revision_plan,
    re_review,
    recommend_statistical_revision,
    review_draft,
)
from .review_engines import ReviewEngineError, discover_review_workflow_gaps, propose_review_engineering_plan
from .result_validity import ResultValidityError, assess_result_validity
from .result_support import ResultSupportError, assess_result_support
from .result_rescue import ResultRescueError, prepare_result_rescue
from .result_evidence import ResultEvidenceError, resolve_result_evidence
from .result_discipline_review import ResultDisciplineReviewError, review_results_with_discipline_rules
from .review_rule_runtime import assess_review_rules
from .results import ResultsGateError, inventory_results, write_results
from .stale_sync import ArtifactDriftError, detect_artifact_drift, sync_artifact_stale
from .template_registry import validate_template_registry
from .writing_style import WritingStyleError, learn_writing_style_from_draft


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
from .zotero_adapter import ZoteroAdapterError, list_zotero_collections


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="draftpaper",
        description="Local-first staged workflow for research paper projects.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-project", help="Create a single-paper project directory model.")
    create.add_argument("--root", required=True, help="Directory that will contain paper projects.")
    create.add_argument("--idea", required=True, help="Research idea or working title.")
    create.add_argument("--field", required=True, help="Research field or aim.")
    create.add_argument("--target-journal", default="General Academic Journal", help="Target journal or template family.")
    create.add_argument("--overwrite", action="store_true", help="Allow regenerating an existing project scaffold.")

    load = subparsers.add_parser("load-project", help="Load project metadata as JSON.")
    load.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    validate = subparsers.add_parser("validate-project", help="Validate project metadata and stage manifests.")
    validate.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    template_registry = subparsers.add_parser("validate-template-registry", help="Validate discipline plugin manifests and template files.")
    template_registry.add_argument("--root", default=None, help="Optional discipline_modules root for testing or contribution review.")

    status = subparsers.add_parser("status", help="Report orchestrated pipeline status and next action.")
    status.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    checkpoint = subparsers.add_parser("checkpoint", help="Create an explicit user-confirmation checkpoint.")
    checkpoint.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    checkpoint.add_argument("--stage", required=True, help="Stage being checkpointed.")
    checkpoint.add_argument("--note", default="", help="Human-readable checkpoint note.")

    resume = subparsers.add_parser("resume", help="Resume from a checkpoint hash.")
    resume.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    resume.add_argument("--checkpoint-hash", required=True, help="Checkpoint hash to consume.")
    resume.add_argument("--note", default="", help="Human-readable resume note.")

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

    plugin_rescue_outcome = subparsers.add_parser("record-plugin-rescue-outcome", help="Record whether scoped local, AcademicForge, and GitHub capability rescue found an executable route.")
    plugin_rescue_outcome.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    plugin_rescue_outcome.add_argument("--requirement-id", required=True, help="Requirement identifier from review/plugin_rescue_plan.json.")
    plugin_rescue_outcome.add_argument("--outcome", required=True, choices=["capability_found", "not_found_after_search"])
    plugin_rescue_outcome.add_argument("--attempted-route", action="append", default=[], help="Audited route; repeat for project_local, existing_registry, academicforge, and github_research_code.")
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
    method_plan.add_argument("--primary-metric", default="f1", help="Primary metric expected for result validity.")
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
    downgrade_claim.add_argument("--reason", default="", help="Optional human-readable reason for choosing the downgrade route.")

    result_rescue = subparsers.add_parser("prepare-result-rescue", help="Prepare data/method supplement tasks when current results cannot support planned claims.")
    result_rescue.add_argument("--project", required=True, help="Path to a project directory or project.json.")

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
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "create-project":
        try:
            project = create_project(
                root=Path(args.root),
                idea=args.idea,
                field=args.field,
                target_journal=args.target_journal,
                overwrite=args.overwrite,
            )
        except ProjectAlreadyExistsError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2
        except ValueError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1

        print(json.dumps({
            "status": "created",
            "project_id": project.project_id,
            "project_slug": project.project_slug,
            "project_path": str(project.path),
            "project_json": str(project.path / "project.json"),
            "project_yaml": str(project.path / "project.yaml"),
        }, ensure_ascii=False))
        return 0

    if args.command == "load-project":
        try:
            state = load_project(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "loaded",
            "project_path": str(state.path),
            "metadata": state.metadata,
        }, ensure_ascii=False))
        return 0

    if args.command == "validate-project":
        report = validate_project(args.project)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get("status") == "passed" else 1

    if args.command == "validate-template-registry":
        result = validate_template_registry(Path(args.root) if args.root else None)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1

    if args.command == "status":
        try:
            result = status_project(args.project)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "checkpoint":
        try:
            result = checkpoint_project(args.project, stage=args.stage, note=args.note)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "resume":
        try:
            result = resume_project(args.project, checkpoint_hash=args.checkpoint_hash, note=args.note)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "run-pipeline":
        try:
            result = run_pipeline(args.project)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") in {"planned", "awaiting_confirmation", "drift_detected"} else 1

    if args.command == "detect-artifact-drift":
        try:
            result = detect_artifact_drift(args.project)
        except (ArtifactDriftError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "sync-artifact-stale":
        try:
            result = sync_artifact_stale(args.project)
        except (ArtifactDriftError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "update-stage-status":
        try:
            state = update_stage_status(args.project, args.stage, args.status)
        except (ProjectStateError, UnknownStageError, InvalidStageStatusError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "updated",
            "project_path": str(state.path),
            "stage": args.stage,
            "stage_status": state.metadata["stages"][args.stage]["status"],
            "stale": state.metadata["stages"][args.stage]["stale"],
        }, ensure_ascii=False))
        return 0

    if args.command == "mark-stage-stale":
        try:
            changed = mark_stage_stale(args.project, args.stage, include_self=args.include_self)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "updated",
            "stage": args.stage,
            "stale_stages": changed,
        }, ensure_ascii=False))
        return 0

    if args.command == "search-literature":
        try:
            result = search_literature_for_project(
                args.project,
                query=args.query,
                limit=args.limit,
                from_json=args.from_json,
                zotero_collection=args.zotero_collection,
                zotero_context=args.zotero_context,
                zotero_min_items=args.zotero_min_items,
                zotero_supplement=not args.no_zotero_supplement,
            )
        except (ValueError, ZoteroAdapterError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "list-zotero-collections":
        try:
            collections = list_zotero_collections()
        except ZoteroAdapterError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "listed",
            "count": len(collections),
            "collections": collections,
        }, ensure_ascii=False))
        return 0

    if args.command == "resolve-journal-template":
        try:
            result = resolve_journal_template(
                args.project,
                target_journal=args.target_journal,
                overleaf_url=args.overleaf_url,
                guideline_url=args.guideline_url,
                from_html=args.from_html,
            )
        except (JournalProfileError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "preflight-research-feasibility":
        try:
            result = preflight_research_feasibility(args.project)
        except (ResearchFeasibilityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "blocked" else 1
    if args.command == "generate-plan":
        try:
            result = generate_research_plan(args.project, allow_high_similarity=args.allow_high_similarity)
        except MissingReferencesError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except NoveltyOverlapError as exc:
            print(json.dumps({
                "status": "blocked_high_similarity",
                "message": str(exc),
                "novelty_overlap_report": str(exc.report_path),
            }, ensure_ascii=False), file=sys.stderr)
            return 3
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-research-plan-feasibility":
        try:
            result = assess_research_plan_feasibility(args.project)
        except (ResearchFeasibilityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "blocked" else 1

    if args.command == "revise-research-plan":
        try:
            result = revise_research_plan(args.project)
        except (ResearchFeasibilityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "write-introduction":
        try:
            result = write_introduction(args.project)
        except (MissingIntroductionInputsError, CitationIntegrityError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "record-observation":
        try:
            result = record_observation(args.project, stage=args.stage, kind=args.kind, text=args.text, source=args.source)
        except (ObservationError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "resolve-research-capabilities":
        try:
            result = resolve_research_capabilities(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-plugin-sufficiency":
        try:
            result = assess_plugin_sufficiency(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "rescue_required"} else 1

    if args.command == "audit-project-capabilities":
        try:
            result = audit_project_capabilities(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "rescue_required"} else 1

    if args.command == "prepare-plugin-rescue":
        try:
            result = prepare_plugin_rescue(
                args.project,
                academicforge_root=args.academicforge_root,
                github_metadata=args.github_metadata,
            )
        except (PluginRescueError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "record-plugin-rescue-outcome":
        try:
            route_evidence = {}
            for item in args.route_evidence:
                if "=" not in item:
                    raise PluginRescueError("--route-evidence must use route=path syntax.")
                route, path = item.split("=", 1)
                route_evidence[route.strip()] = path.strip()
            result = record_plugin_rescue_outcome(
                args.project,
                requirement_id=args.requirement_id,
                outcome=args.outcome,
                attempted_routes=args.attempted_route,
                route_evidence=route_evidence,
                evidence_note=args.evidence_note,
            )
        except (PluginRescueError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "blocked_unavailable" else 1

    if args.command == "inventory-data":
        try:
            result = inventory_data(args.project)
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "classify-data-access":
        try:
            result = classify_data_access(args.project, source_root=args.source_root)
        except (DataAcquisitionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command in {"prepare-data-acquisition", "inventory-data-sources"}:
        try:
            result = prepare_data_acquisition(args.project, source_root=args.source_root)
        except (DataAcquisitionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "execute-data-plugins":
        try:
            result = execute_data_plugins(args.project)
        except (PluginExecutionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "written" else 1

    if args.command == "assess-data-quality":
        try:
            result = assess_data_quality(
                args.project,
                required_columns=args.required_column,
                max_missing_ratio=args.max_missing_ratio,
            )
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-data-feasibility":
        try:
            result = assess_data_feasibility(args.project, min_rows=args.min_rows)
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "conditional_pass"} else 1

    if args.command == "build-data-context":
        try:
            context = build_data_writing_context(args.project)
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "written",
            "project_id": context.get("project_id"),
            "data_writing_context": "data/data_writing_context.json",
            "observation_count": context.get("observation_count", 0),
        }, ensure_ascii=False))
        return 0

    if args.command == "write-data":
        try:
            result = write_data(args.project)
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "verify-methods":
        try:
            result = verify_methods(args.project, command=args.method_command, output_files=args.output, input_data=args.input)
        except MethodsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "success" else 1

    if args.command == "plan-figures":
        try:
            result = plan_figures(args.project, use_review_tasks=args.use_review_tasks)
        except (FigurePlanError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-figure-contracts":
        try:
            result = assess_figure_contracts(args.project)
        except (FigureContractGateError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "blocked" else 1
    if args.command == "validate-figure-plugin-trace":
        try:
            result = validate_figure_plugin_trace(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"ready_for_codegen", "pass"} else 1
    if args.command == "generate-analysis-code":
        try:
            result = generate_analysis_code(args.project, output_files=args.output, auto_plan_figures=args.auto_plan_figures, use_review_tasks=args.use_review_tasks)
        except (AnalysisCodeGenerationError, FigurePlanError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "classify-code-ownership":
        try:
            result = classify_code_ownership(args.project)
        except (CodeOwnershipError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "route-stage-code":
        try:
            result = route_stage_code(
                args.project,
                mode=args.mode,
                keep_compat_launchers=not args.no_compat_launchers,
            )
        except (CodeOwnershipError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "build-code-provenance":
        try:
            result = build_code_provenance(args.project)
        except (CodeOwnershipError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "extract-method-formulas":
        try:
            result = extract_method_formulas(args.project)
        except (CodeOwnershipError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "trace-figures-to-code":
        try:
            result = trace_figures_to_code(args.project)
        except (CodeOwnershipError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "collect-method-plan":
        try:
            result = collect_method_plan(
                args.project,
                user_method="\n".join(args.method_note or []),
                primary_metric=args.primary_metric,
                minimum_primary_metric=args.minimum_primary_metric,
            )
        except (MethodPlanError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "prepare-method-blueprint":
        try:
            result = prepare_method_blueprint(args.project)
        except (MethodBlueprintError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "execute-method-plugins":
        try:
            result = execute_method_plugins(args.project)
        except (PluginExecutionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "written" else 1

    if args.command == "assess-method-feasibility":
        try:
            result = assess_method_feasibility(args.project)
        except (MethodFeasibilityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "blocked" else 1
    if args.command == "write-methods":
        try:
            result = write_methods(args.project)
        except MethodsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "build-method-context":
        try:
            context = build_method_writing_context(args.project)
        except MethodsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "written",
            "project_id": context.get("project_id"),
            "method_writing_context": "methods/method_writing_context.json",
            "observation_count": context.get("observation_count", 0),
        }, ensure_ascii=False))
        return 0

    if args.command == "inventory-results":
        try:
            result = inventory_results(args.project)
        except ResultsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-result-validity":
        try:
            result = assess_result_validity(
                args.project,
                primary_metric=args.primary_metric,
                minimum_value=args.minimum_value,
            )
        except (ResultValidityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-review-rules":
        try:
            state = load_project(args.project)
            output = None if args.no_write else Path(args.output) if args.output else state.path / "results" / "review_rule_gate_report.json"
            result = assess_review_rules(state.path, stage=args.stage, write_path=output)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "warn_and_repair"} else 1

    if args.command == "assess-result-support":
        try:
            result = assess_result_support(args.project)
        except (ResultSupportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") == "pass" else 1

    if args.command == "apply-result-downgrade":
        try:
            result = apply_result_downgrade(args.project, reason=args.reason)
        except (ClaimContractError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "prepare-result-rescue":
        try:
            result = prepare_result_rescue(args.project)
        except (ResultRescueError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-core-evidence":
        try:
            result = assess_core_evidence(args.project)
        except (CoreEvidenceError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "diagnose-figure-execution":
        try:
            result = diagnose_figure_execution(args.project)
        except (FigureRepairError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "repair-figure-data":
        try:
            result = repair_figure_data(args.project)
        except (FigureRepairError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "repair-figure-method":
        try:
            result = repair_figure_method(args.project)
        except (FigureRepairError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "write-results":
        try:
            result = write_results(args.project)
        except ResultsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "review-results-with-discipline-rules":
        try:
            result = review_results_with_discipline_rules(args.project)
        except (ResultDisciplineReviewError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "repair_required"} else 1

    if args.command == "resolve-result-evidence":
        try:
            result = resolve_result_evidence(args.project)
        except (ResultEvidenceError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "reopen-core-evidence":
        try:
            result = reopen_evidence_snapshot(args.project, reason=args.reason)
        except (EvidenceSnapshotMismatch, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "build-paper-narrative":
        try:
            result = build_paper_narrative(args.project)
        except (PaperNarrativeError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "prepare-section-outline":
        try:
            result = build_section_outline(args.project, args.section)
        except (PaperNarrativeError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "build-results-synthesis":
        try:
            result = build_results_synthesis_plan(args.project)
        except (PaperNarrativeError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command in {"build-argument-matrices", "build-section-lifecycles", "build-panel-contracts", "prepare-panel-repair", "resolve-venue-writing-style", "prepare-scientific-editor", "record-scientific-editor-revision", "assess-functional-quality-release"}:
        try:
            if args.command == "build-argument-matrices":
                result = build_argument_matrices(args.project)
            elif args.command == "build-section-lifecycles":
                result = build_section_lifecycles(args.project)
            elif args.command == "build-panel-contracts":
                result = build_panel_writing_contracts(args.project)
            elif args.command == "prepare-panel-repair":
                result = prepare_panel_repair(args.project)
            elif args.command == "resolve-venue-writing-style":
                result = resolve_venue_style_adapter(args.project)
            elif args.command == "prepare-scientific-editor":
                result = prepare_scientific_editor(args.project, args.section, args.input)
            elif args.command == "record-scientific-editor-revision":
                result = record_scientific_editor_revision(args.project, args.section, args.before, args.after, args.iteration)
            else:
                result = assess_functional_quality_release(args.project)
        except (WritingArchitectureError, PaperNarrativeError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "submit-section-draft":
        try:
            result = submit_section_draft(args.project, args.section, args.input)
        except (SectionCompositionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "prepare-section-writing":
        try:
            result = build_section_evidence_packet(args.project, args.section)
        except (SectionCompositionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-manuscript-quality":
        try:
            text = Path(args.input).read_text(encoding="utf-8-sig") if args.input else None
            result = assess_results_manuscript_quality(args.project, text=text)
        except (OSError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") == "pass" else 1

    if args.command == "assess-figure-publication-quality":
        try:
            result = assess_scientific_figure_quality(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") == "pass" else 1

    if args.command == "prepare-results-semantic-repair":
        try:
            result = prepare_results_semantic_repair(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-paper-quality-parity":
        try:
            result = assess_paper_quality_parity(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") == "pass" else 1

    if args.command == "submit-figure-semantic-annotations":
        try:
            result = submit_figure_semantic_annotations(args.project, args.input)
        except (FigureSemanticAnnotationError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "write-discussion":
        try:
            result = write_discussion(args.project)
        except (MissingDiscussionInputsError, DiscussionCitationIntegrityError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "prepare-discussion-comparison":
        try:
            result = prepare_discussion_comparison(args.project)
        except (MissingDiscussionInputsError, DiscussionCitationIntegrityError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assemble-latex":
        try:
            result = assemble_latex(args.project, compile_pdf=args.compile_pdf)
        except LatexAssemblyError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "compile-latex-pdf":
        try:
            result = compile_latex_pdf(args.project)
        except LatexAssemblyError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "quality-check":
        try:
            result = run_quality_check(args.project)
        except QualityGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1

    if args.command == "run-integrity-gate":
        try:
            result = run_integrity_gate(args.project)
        except IntegrityGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1

    if args.command == "audit-citations":
        try:
            result = audit_citations(args.project, final=args.final)
        except CitationAuditError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1

    if args.command == "generate-citation-repair-plan":
        try:
            result = generate_citation_repair_plan(args.project)
        except (CitationAuditError, CitationRepairError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "apply-citation-repair":
        try:
            result = apply_citation_repair(args.project, dry_run=args.dry_run)
        except CitationRepairError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "re-audit-citations":
        try:
            result = re_audit_citations(args.project)
        except CitationAuditError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1

    if args.command == "run-citation-repair-loop":
        try:
            result = run_citation_repair_loop(args.project, max_iterations=args.max_iterations)
        except (CitationAuditError, CitationRepairError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1

    if args.command == "diagnose-gate-failures":
        try:
            result = diagnose_gate_failures(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "review-draft":
        try:
            result = review_draft(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "assess-publication-readiness":
        try:
            result = assess_publication_readiness(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "discover-review-workflow-gaps":
        try:
            result = discover_review_workflow_gaps(args.project)
        except (ReviewEngineError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "propose-review-engineering-plan":
        try:
            result = propose_review_engineering_plan(args.project)
        except (ReviewEngineError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "recommend-statistical-revision":
        try:
            result = recommend_statistical_revision(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "prepare-analysis-revision":
        try:
            result = prepare_analysis_revision(args.project)
        except (AnalysisRevisionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "discover-research-repos":
        try:
            result = discover_research_repos(
                output_root=args.output_root,
                discipline=args.discipline,
                query=args.query,
                from_json=args.from_json,
                limit=args.limit,
            )
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "score-research-repos":
        try:
            result = score_research_repos(input_file=args.input, output_root=args.output_root)
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "extract-plugin-candidates":
        try:
            result = extract_plugin_candidates(input_file=args.input, output_root=args.output_root, top_n=args.top_n)
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "inspect-research-repo":
        try:
            result = inspect_research_repo(
                candidate=args.candidate,
                local_repo=args.local_repo,
                output_root=args.output_root,
                mode=args.mode,
            )
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "map-repository-workflow":
        try:
            result = map_repository_workflow(inspection_file=args.inspection, output_root=args.output_root)
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "bootstrap-discipline-foundation":
        try:
            result = bootstrap_discipline_foundation(workflow_map=args.workflow_map, output_root=args.output_root)
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "capture-discipline-learning":
        try:
            result = capture_discipline_learning(args.project, output_root=args.output_root)
        except (ResearchCodeMiningError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "classify-plugin-reusability":
        try:
            result = classify_plugin_reusability(args.candidate)
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "summarize-plugin-candidates":
        try:
            result = summarize_plugin_candidates(args.project, source_file=args.source_file, method=args.method)
        except (PluginCandidateError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "snapshot-skill-source":
        try:
            result = snapshot_skill_source(
                _skill_source_root_from_args(args),
                source=_skill_source_label(args),
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref or args.ref,
                include_hashes=not args.no_hashes,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "inspect-skill-source":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("inspect-skill-source requires --source-root/--path or a SNAPSHOT.json with source_root.")
            result = inspect_skill_source(
                source_root,
                source=_skill_source_label(args),
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "index-skill-source":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("index-skill-source requires --source-root/--path or a snapshot/inspection report with source_root.")
            result = index_skill_source(
                source_root,
                source=_skill_source_label(args),
                discipline=args.discipline,
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "classify-skill-source":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("classify-skill-source requires --source-root/--path or a snapshot/inspection/index report with source_root.")
            result = classify_skill_source(
                source_root,
                source=_skill_source_label(args),
                discipline=args.discipline,
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "map-skill-capabilities":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("map-skill-capabilities requires --source-root/--path or a snapshot/inspection/index report with source_root.")
            result = map_skill_capabilities(
                source_root,
                source=_skill_source_label(args),
                discipline=args.discipline,
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "extract-review-rule-signals":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("extract-review-rule-signals requires --source-root/--path or a snapshot/inspection/index report with source_root.")
            result = extract_review_rule_signals(
                source_root,
                source=_skill_source_label(args),
                discipline=args.discipline,
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "extract-skill-capabilities":
        try:
            source_file = _single_skill_source_file_from_args(args)
            if not source_file:
                raise PluginCandidateError("extract-skill-capabilities requires --source-file/--path or a SNAPSHOT.json with exactly one source record. Use compile-skill-source for multi-file snapshots.")
            result = extract_skill_capabilities(
                source_file,
                source=_skill_source_label(args),
                skill_id=args.skill_id,
                discipline=args.discipline,
                output_root=args.output_root,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "compile-skill-source":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("compile-skill-source requires --source-root/--path or a snapshot/inspection/index report with source_root.")
            result = compile_skill_source(
                source_root,
                source=_skill_source_label(args),
                discipline=args.discipline,
                output_root=args.output_root,
                stop_after=args.stop_after,
                jobs=args.jobs,
                resume=args.resume,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generalize-plugin-candidate":
        try:
            result = generalize_plugin_candidate(args.candidate)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "validate-plugin-candidate":
        try:
            result = validate_plugin_candidate(args.candidate)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1

    if args.command == "promote-plugin-candidate":
        try:
            result = promote_plugin_candidate(
                args.candidate,
                require_human_confirmation=args.require_human_confirmation,
                dry_run=not args.write,
                target_root=args.target_root,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "package-plugin-contribution":
        try:
            result = package_plugin_contribution(args.candidate)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "preflight-plugin-contribution":
        try:
            result = preflight_plugin_contribution_package(args.package)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1

    if args.command == "review-plugin-contribution":
        try:
            result = review_plugin_contribution_package(args.package)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("maintainer_recommendation") == "ready_for_human_review" else 1

    if args.command == "write-github-contribution-guide":
        try:
            result = write_github_contribution_guide(args.project)
        except (PluginCandidateError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "generate-revision-plan":
        try:
            result = generate_revision_plan(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "apply-revision":
        try:
            result = apply_revision(args.project, issue_ids=args.issue_id, dry_run=args.dry_run)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "re-review":
        try:
            result = re_review(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "learn-writing-style-from-draft":
        try:
            result = learn_writing_style_from_draft(args.project, args.draft)
        except (WritingStyleError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
