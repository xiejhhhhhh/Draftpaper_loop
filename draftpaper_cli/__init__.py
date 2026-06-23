# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Local-first CLI workflow for staged research paper projects.

Contact: xiejinhui22@mails.ucas.ac.cn
Commercial use requires written authorization from the developer.
"""

from .analysis_code import AnalysisCodeGenerationError, generate_analysis_code
from .analysis_revision import AnalysisRevisionError, prepare_analysis_revision
from .data_feasibility import DataGateError, assess_data_feasibility, assess_data_quality, inventory_data
from .discussion import DiscussionCitationIntegrityError, MissingDiscussionInputsError, write_discussion
from .introduction import CitationIntegrityError, MissingIntroductionInputsError, write_introduction
from .integrity_gate import IntegrityGateError, latest_integrity_report, run_integrity_gate
from .latex_assembly import LatexAssemblyError, LatexCitationError, assemble_latex, compile_latex_pdf
from .methods import MethodsGateError, verify_methods, write_methods
from .orchestrator import OrchestratorError, checkpoint_project, resume_project, run_pipeline, status_project
from .passport import PassportError, load_project_passport, refresh_project_passport
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
from .stale_sync import ArtifactDriftError, detect_artifact_drift, sync_artifact_stale

__all__ = [
    "InvalidStageStatusError",
    "CitationIntegrityError",
    "MissingIntroductionInputsError",
    "MissingDiscussionInputsError",
    "DiscussionCitationIntegrityError",
    "DataGateError",
    "AnalysisCodeGenerationError",
    "AnalysisRevisionError",
    "ArtifactDriftError",
    "LatexAssemblyError",
    "LatexCitationError",
    "MethodsGateError",
    "OrchestratorError",
    "PassportError",
    "ResultsGateError",
    "ProjectAlreadyExistsError",
    "ProjectScaffold",
    "ProjectState",
    "ProjectStateError",
    "QualityGateError",
    "IntegrityGateError",
    "ReviewRevisionError",
    "ReviewEngineError",
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
    "load_project_passport",
    "refresh_project_passport",
    "detect_artifact_drift",
    "sync_artifact_stale",
    "generate_analysis_code",
    "prepare_analysis_revision",
    "write_introduction",
    "inventory_data",
    "assess_data_quality",
    "assess_data_feasibility",
    "write_discussion",
    "assemble_latex",
    "compile_latex_pdf",
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
]
