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
from .core_evidence import CoreEvidenceError, assess_core_evidence
from .data_acquisition import DataAcquisitionError, classify_data_access, prepare_data_acquisition
from .data_feasibility import DataGateError, assess_data_feasibility, assess_data_quality, build_data_writing_context, inventory_data, write_data
from .discussion import DiscussionCitationIntegrityError, MissingDiscussionInputsError, write_discussion
from .introduction import CitationIntegrityError, MissingIntroductionInputsError, write_introduction
from .integrity_gate import IntegrityGateError, run_integrity_gate
from .journal_profile import JournalProfileError, resolve_journal_template
from .latex_assembly import LatexAssemblyError, assemble_latex, compile_latex_pdf
from .literature_search import search_literature_for_project
from .method_plan import MethodPlanError, collect_method_plan
from .method_blueprint import MethodBlueprintError, prepare_method_blueprint
from .figure_plan import FigurePlanError, plan_figures
from .methods import MethodsGateError, build_method_writing_context, verify_methods, write_methods
from .observations import ObservationError, record_observation
from .orchestrator import OrchestratorError, checkpoint_project, resume_project, run_pipeline, status_project
from .passport import PassportError
from .plugin_candidates import (
    PluginCandidateError,
    generalize_plugin_candidate,
    package_plugin_contribution,
    summarize_plugin_candidates,
    validate_plugin_candidate,
    write_github_contribution_guide,
)
from .project_scaffold import ProjectAlreadyExistsError, create_project
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
from .results import ResultsGateError, inventory_results, write_results
from .stale_sync import ArtifactDriftError, detect_artifact_drift, sync_artifact_stale
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

    plan = subparsers.add_parser("generate-plan", help="Generate a literature-informed formal research plan.")
    plan.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    plan.add_argument("--allow-high-similarity", action="store_true", help="Continue even when a highly similar prior paper is detected.")

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

    figures = subparsers.add_parser("plan-figures", help="Observe project state and plan project-specific scientific figures.")
    figures.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    figures.add_argument("--use-review-tasks", action="store_true", help="Include review/actionable_analysis_tasks.json hints when planning figures.")

    codegen = subparsers.add_parser("generate-analysis-code", help="Generate project-local analysis code from literature and method requirements.")
    codegen.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    codegen.add_argument("--output", action="append", default=[], help="Project-relative output file expected from generated code.")
    codegen.add_argument("--auto-plan-figures", action="store_true", help="Generate results/figure_plan.json first if it is missing or stale.")
    codegen.add_argument("--use-review-tasks", action="store_true", help="Include review/actionable_analysis_tasks.json in generated analysis code.")

    verify = subparsers.add_parser("verify-methods", help="Run method code and write methods/run_manifest.yaml.")
    verify.add_argument("--project", required=True, help="Path to a project directory or project.json.")
    verify.add_argument("--command", required=True, dest="method_command", help="Command that verifies method code and outputs.")
    verify.add_argument("--output", action="append", default=[], help="Project-relative output file that must exist after the command.")
    verify.add_argument("--input", action="append", default=[], help="Project-relative input data file used by the method command.")

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

    core_evidence = subparsers.add_parser("assess-core-evidence", help="Assess data-method-figure-result evidence before manuscript writing.")
    core_evidence.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    results = subparsers.add_parser("write-results", help="Write results.tex from result_manifest.yaml.")
    results.add_argument("--project", required=True, help="Path to a project directory or project.json.")

    discussion = subparsers.add_parser("write-discussion", help="Write a traceable LaTeX Discussion section.")
    discussion.add_argument("--project", required=True, help="Path to a project directory or project.json.")

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

    generalize_candidate = subparsers.add_parser("generalize-plugin-candidate", help="Convert a project-specific candidate into a generic plugin template.")
    generalize_candidate.add_argument("--candidate", required=True, help="Path to plugin_candidates/<discipline>/<candidate_id>.")

    validate_candidate = subparsers.add_parser("validate-plugin-candidate", help="Run privacy, genericity, overlap, and fixture checks for a plugin candidate.")
    validate_candidate.add_argument("--candidate", required=True, help="Path to plugin_candidates/<discipline>/<candidate_id>.")

    package_candidate = subparsers.add_parser("package-plugin-contribution", help="Package a validated plugin candidate for fork/PR review.")
    package_candidate.add_argument("--candidate", required=True, help="Path to plugin_candidates/<discipline>/<candidate_id>.")

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
        return 0

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

    if args.command == "package-plugin-contribution":
        try:
            result = package_plugin_contribution(args.candidate)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0

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

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
