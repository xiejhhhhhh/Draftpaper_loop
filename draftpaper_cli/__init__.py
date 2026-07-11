# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Local-first CLI workflow for staged research paper projects.

Contact: xiejinhui22@mails.ucas.ac.cn
Commercial use requires written authorization from the developer.
"""

from .analysis_code import AnalysisCodeGenerationError, generate_analysis_code
from .analysis_revision import AnalysisRevisionError, prepare_analysis_revision
from .citation_audit import CitationAuditError, audit_citations
from .change_impact import ChangeClassification, affected_stages, classify_change
from .citation_repair import CitationRepairError, apply_citation_repair, generate_citation_repair_plan, re_audit_citations, run_citation_repair_loop
from .data_acquisition import DataAcquisitionError, classify_data_access, prepare_data_acquisition
from .data_feasibility import DataGateError, assess_data_feasibility, assess_data_quality, inventory_data
from .discussion import DiscussionCitationIntegrityError, MissingDiscussionInputsError, write_discussion
from .evidence_registry import EvidenceConflictError, build_scientific_evidence_registry, ensure_registry_consistent
from .evidence_snapshot import create_evidence_snapshot, reopen_evidence_snapshot, validate_evidence_snapshot
from .figure_semantic_annotations import FigureSemanticAnnotationError, submit_figure_semantic_annotations
from .figure_semantics import build_semantic_figure_contract, validate_figure_semantics
from .introduction import CitationIntegrityError, MissingIntroductionInputsError, write_introduction
from .integrity_gate import IntegrityGateError, latest_integrity_report, run_integrity_gate
from .latex_assembly import LatexAssemblyError, LatexCitationError, assemble_latex, compile_latex_pdf
from .method_blueprint import MethodBlueprintError, prepare_method_blueprint
from .methods import MethodsGateError, verify_methods, write_methods
from .manuscript_composer import SectionCompositionError, build_section_evidence_packet, submit_section_draft
from .manuscript_quality import assess_results_manuscript_quality, build_results_narrative_contract
from .scientific_figure_quality import assess_scientific_figure_quality
from .paper_quality_parity import assess_paper_quality_parity
from .results_semantic_repair import prepare_results_semantic_repair
from .orchestrator import OrchestratorError, checkpoint_project, resume_project, run_pipeline, status_project
from .passport import PassportError, load_project_passport, refresh_project_passport
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
    promote_plugin_candidate,
    review_plugin_contribution_package,
    snapshot_skill_source,
    summarize_plugin_candidates,
    validate_plugin_candidate,
    write_github_contribution_guide,
)
from .project_scaffold import ProjectAlreadyExistsError, ProjectScaffold, create_project
from .project_state import (
    InvalidStageStatusError,
    ProjectState,
    ProjectStateError,
    UnknownStageError,
    load_project,
    mark_stage_stale,
    update_stage_status,
    validate_project,
)
from .quality_gate import QualityGateError, run_quality_check
from .references import write_reference_outputs
from .research_plan import MissingReferencesError, generate_research_plan
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
from .review_engines import ReviewEngineError, discover_review_workflow_gaps, infer_review_discipline, propose_review_engineering_plan
from .results import ResultsGateError, inventory_results, write_results
from .result_evidence import ResultEvidenceError, resolve_result_evidence
from .review_rule_runtime import assess_review_rules, build_review_rule_rescue_tasks, collect_review_rule_evidence_roles, load_discipline_review_rules
from .scientific_fact_ledger import build_scientific_fact_ledger, load_or_build_scientific_fact_ledger
from .stale_sync import ArtifactDriftError, detect_artifact_drift, sync_artifact_stale
from .writing_style import WritingStyleError, learn_writing_style_from_draft

__all__ = [
    "InvalidStageStatusError",
    "CitationIntegrityError",
    "MissingIntroductionInputsError",
    "MissingDiscussionInputsError",
    "DiscussionCitationIntegrityError",
    "DataGateError",
    "DataAcquisitionError",
    "AnalysisCodeGenerationError",
    "AnalysisRevisionError",
    "CitationAuditError",
    "ChangeClassification",
    "EvidenceConflictError",
    "FigureSemanticAnnotationError",
    "ResultEvidenceError",
    "SectionCompositionError",
    "CitationRepairError",
    "ArtifactDriftError",
    "LatexAssemblyError",
    "LatexCitationError",
    "MethodBlueprintError",
    "MethodsGateError",
    "OrchestratorError",
    "PassportError",
    "PluginCandidateError",
    "ResultsGateError",
    "ProjectAlreadyExistsError",
    "ProjectScaffold",
    "ProjectState",
    "ProjectStateError",
    "QualityGateError",
    "IntegrityGateError",
    "ReviewRevisionError",
    "ReviewEngineError",
    "WritingStyleError",
    "UnknownStageError",
    "create_project",
    "load_project",
    "mark_stage_stale",
    "update_stage_status",
    "validate_project",
    "run_quality_check",
    "run_integrity_gate",
    "latest_integrity_report",
    "status_project",
    "checkpoint_project",
    "resume_project",
    "run_pipeline",
    "audit_citations",
    "generate_citation_repair_plan",
    "apply_citation_repair",
    "re_audit_citations",
    "run_citation_repair_loop",
    "load_project_passport",
    "refresh_project_passport",
    "summarize_plugin_candidates",
    "snapshot_skill_source",
    "inspect_skill_source",
    "index_skill_source",
    "classify_skill_source",
    "map_skill_capabilities",
    "extract_skill_capabilities",
    "compile_skill_source",
    "extract_review_rule_signals",
    "generalize_plugin_candidate",
    "validate_plugin_candidate",
    "promote_plugin_candidate",
    "package_plugin_contribution",
    "review_plugin_contribution_package",
    "write_github_contribution_guide",
    "detect_artifact_drift",
    "sync_artifact_stale",
    "generate_analysis_code",
    "classify_change",
    "affected_stages",
    "build_scientific_evidence_registry",
    "ensure_registry_consistent",
    "create_evidence_snapshot",
    "reopen_evidence_snapshot",
    "validate_evidence_snapshot",
    "build_semantic_figure_contract",
    "validate_figure_semantics",
    "submit_figure_semantic_annotations",
    "build_section_evidence_packet",
    "submit_section_draft",
    "build_results_narrative_contract",
    "assess_results_manuscript_quality",
    "assess_scientific_figure_quality",
    "assess_paper_quality_parity",
    "prepare_results_semantic_repair",
    "resolve_result_evidence",
    "assess_review_rules",
    "build_review_rule_rescue_tasks",
    "collect_review_rule_evidence_roles",
    "load_discipline_review_rules",
    "prepare_analysis_revision",
    "write_introduction",
    "inventory_data",
    "classify_data_access",
    "prepare_data_acquisition",
    "assess_data_quality",
    "assess_data_feasibility",
    "write_discussion",
    "assemble_latex",
    "compile_latex_pdf",
    "prepare_method_blueprint",
    "verify_methods",
    "write_methods",
    "inventory_results",
    "write_results",
    "write_reference_outputs",
    "MissingReferencesError",
    "generate_research_plan",
    "diagnose_gate_failures",
    "review_draft",
    "assess_publication_readiness",
    "infer_review_discipline",
    "discover_review_workflow_gaps",
    "propose_review_engineering_plan",
    "recommend_statistical_revision",
    "generate_revision_plan",
    "apply_revision",
    "re_review",
    "learn_writing_style_from_draft",
]
