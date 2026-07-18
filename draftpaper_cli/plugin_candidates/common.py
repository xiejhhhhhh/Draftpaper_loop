# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from ..discipline import infer_discipline_from_text, infer_discipline_profile
from ..discipline_modules import get_discipline_module
from ..html_utils import write_html_report
from ..project_scaffold import _write_json, utc_now
from ..project_state import load_project
from ..safe_fetch import SafeFetchError, fetch_text

class PluginCandidateError(RuntimeError):
    """Raised when plugin candidate operations cannot proceed."""


SENSITIVE_PATTERNS = [
    r"ghp_[A-Za-z0-9_]+",
    r"(?i)(api[_-]?key|token|password|passwd|secret)\s*[:=]\s*['\"]?[^'\"\s,;]+",
    r"[A-Za-z]:\\[^ \n\r\t]+",
    r"(?i)ssh\s+[^ \n\r\t]+@[^ \n\r\t]+",
]


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return fallback


def _read_text(path: Path, limit: int = 80_000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return text[:limit]


def _candidate_root(project_path: Path, discipline: str, candidate_id: str) -> Path:
    return project_path / "plugin_candidates" / discipline / candidate_id


def _safe_id(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return cleaned[:80] or "plugin_candidate"


REVIEW_RULE_KEYWORDS: dict[str, dict[str, Any]] = {
    "statistical_validity": {
        "terms": [
            "p-value", "p value", "confidence interval", "effect size", "fdr", "multiple testing",
            "residual", "goodness of fit", "r2", "r²", "rmse", "mae", "statistical power",
            "uncertainty", "distribution assumption", "robustness",
        ],
        "checks": ["statistical_assumption_check", "uncertainty_or_effect_size_check"],
        "failure_route": "method_rescue",
    },
    "model_validity": {
        "terms": [
            "baseline", "ablation", "held-out", "holdout", "train validation test", "split",
            "leakage", "calibration", "external validation", "auc", "f1", "accuracy", "overfitting",
            "hyperparameter", "benchmark",
        ],
        "checks": ["baseline_ablation_check", "split_leakage_metric_check"],
        "failure_route": "method_rescue",
    },
    "data_validity": {
        "terms": [
            "missingness", "missing data", "unit consistency", "cohort", "batch effect", "coverage",
            "sample unit", "measurement error", "quality flag", "patient leakage", "train test independence",
        ],
        "checks": ["data_role_consistency_check", "coverage_and_leakage_check"],
        "failure_route": "data_rescue",
    },
    "figure_claim_validity": {
        "terms": [
            "figure", "caption", "axis", "panel", "dimension", "claim", "visualization",
            "main figure", "appendix", "identifier plot", "error bar", "uncertainty visualization",
        ],
        "checks": ["figure_claim_alignment_check", "axis_panel_dimension_check"],
        "failure_route": "result_downgrade",
    },
    "citation_and_manuscript_validity": {
        "terms": [
            "citation", "reference", "claim scope", "unsupported", "ethics", "privacy",
            "data availability", "code availability", "manuscript", "introduction", "discussion",
        ],
        "checks": ["citation_support_scope_check", "manuscript_claim_boundary_check"],
        "failure_route": "manuscript_repair",
    },
    "reproducibility_and_operational_validity": {
        "terms": [
            "random seed", "seed", "environment", "dependency", "version", "remote compute",
            "server", "fixture", "smoke test", "reproducibility", "provenance",
        ],
        "checks": ["reproducibility_provenance_check", "fixture_smoke_test_check"],
        "failure_route": "human_checkpoint",
    },
}


REVIEW_RULE_SIGNAL_DIMENSIONS: dict[str, list[str]] = {
    "scientific_action": [
        "check", "validate", "evaluate", "report", "compare", "diagnose", "test", "audit",
        "baseline", "ablation", "split", "metric", "cohort", "figure", "citation",
    ],
    "evidence_binding": [
        "data", "method", "metric", "evidence", "figure", "result", "citation", "claim",
        "sample", "cohort", "unit", "split", "output", "artifact", "baseline", "benchmark",
    ],
    "failure_observable": [
        "missing", "leakage", "unsupported", "invalid", "inconsistent", "failure", "fail",
        "overfitting", "bias", "confound", "diagnostic", "assumption", "risk", "error",
    ],
    "repair_route": [
        "rescue", "repair", "fix", "rerun", "supplement", "downgrade", "revise", "recompute",
        "manual", "checkpoint", "confirm", "replace", "add", "remove", "adjust",
    ],
    "discipline_specificity": [
        "patient", "source", "event", "observation", "pixel", "plot", "field", "cohort",
        "batch", "spatial", "temporal", "astronomy", "geography", "medicine", "biology",
        "engineering", "finance", "machine learning", "deep learning",
    ],
    "threshold_source_quality": [
        "journal", "guideline", "standard", "benchmark", "challenge", "baseline", "comparative",
        "confidence interval", "effect size", "human confirmed", "confirmed", "discipline convention",
    ],
    "generalization_risk": [
        "my project", "this project", "local", "private", "server", "password", "absolute path",
        "hard-code", "hardcoded", "fixed threshold", "always", "must exceed", "must be greater than",
    ],
}


REVIEW_RULE_PIPELINE_HOOKS: dict[str, dict[str, str]] = {
    "statistical_validity": {
        "research_plan": "optional",
        "data_acquisition": "not_applicable",
        "method_plan": "required",
        "figure_contract": "optional",
        "result_support_checkpoint": "required",
        "write_results": "required",
        "write_discussion": "required",
        "citation_audit": "not_applicable",
        "reviewer_rescue_loop": "required",
    },
    "model_validity": {
        "research_plan": "optional",
        "data_acquisition": "not_applicable",
        "method_plan": "required",
        "figure_contract": "required",
        "result_support_checkpoint": "required",
        "write_results": "required",
        "write_discussion": "required",
        "citation_audit": "not_applicable",
        "reviewer_rescue_loop": "required",
    },
    "data_validity": {
        "research_plan": "optional",
        "data_acquisition": "required",
        "method_plan": "required",
        "figure_contract": "optional",
        "result_support_checkpoint": "required",
        "write_results": "optional",
        "write_discussion": "optional",
        "citation_audit": "not_applicable",
        "reviewer_rescue_loop": "required",
    },
    "figure_claim_validity": {
        "research_plan": "required",
        "data_acquisition": "optional",
        "method_plan": "required",
        "figure_contract": "required",
        "result_support_checkpoint": "required",
        "write_results": "required",
        "write_discussion": "required",
        "citation_audit": "not_applicable",
        "reviewer_rescue_loop": "required",
    },
    "citation_and_manuscript_validity": {
        "research_plan": "optional",
        "data_acquisition": "not_applicable",
        "method_plan": "not_applicable",
        "figure_contract": "optional",
        "result_support_checkpoint": "optional",
        "write_results": "required",
        "write_discussion": "required",
        "citation_audit": "required",
        "reviewer_rescue_loop": "required",
    },
    "reproducibility_and_operational_validity": {
        "research_plan": "optional",
        "data_acquisition": "required",
        "method_plan": "required",
        "figure_contract": "optional",
        "result_support_checkpoint": "optional",
        "write_results": "not_applicable",
        "write_discussion": "optional",
        "citation_audit": "not_applicable",
        "reviewer_rescue_loop": "required",
    },
}


SUPPORT_ROUTE_KEYWORDS: dict[str, list[str]] = {
    "workflow_recipe": ["workflow", "pipeline", "step", "checkpoint", "rescue", "run order", "orchestration"],
    "paper_contract": ["paper", "manuscript", "writing", "section", "citation", "claim", "journal", "submission"],
    "shared_capability": ["package", "library", "visualization", "statistics", "reproducibility", "environment", "utility"],
}


SUPPORT_ROUTE_TARGETS: dict[str, dict[str, str]] = {
    "workflow_recipe": {
        "target": "draftpaper_cli/pipeline_recipes/",
        "purpose": "Process orchestration, run order, checkpoints, and rescue route guidance.",
    },
    "paper_contract": {
        "target": "draftpaper_cli/paper_contracts/",
        "purpose": "Writing, citation, figure, submission, and section-level post-check contracts.",
    },
    "shared_capability": {
        "target": "draftpaper_cli/shared_capabilities/",
        "purpose": "Reusable package, statistics, visualization, reproducibility, or environment capability notes.",
    },
}


CAPABILITY_IR_VERSION = "draftpaper.capability_ir.v1"


FORMAL_DISCIPLINE_PLUGIN_TYPES = ["data_connector", "method_template", "review_rule"]


RUNTIME_CLASSES = {
    "local_pure_python",
    "local_optional_dependency",
    "remote_api",
    "remote_server",
    "gpu_model",
    "laboratory_hardware",
    "support_only",
}


VALIDATION_LEVELS = {"plan_only", "mock_validated", "fixture_runnable", "live_validated"}


SUPPORT_LAYER_TYPES = ["workflow_recipe", "paper_contract", "shared_capability"]


REVIEW_RULE_FAMILY_METADATA: dict[str, dict[str, Any]] = {
    "statistical_validity": {
        "review_question": "Do the statistical assumptions, uncertainty expression, and metric interpretation match the study design?",
        "scientific_risk": "The manuscript may overstate statistical support or mix incompatible inferential quantities.",
        "allowed_claim_strength": "associative",
        "repair_priority": ["method_rescue", "result_downgrade", "manuscript_repair", "human_checkpoint"],
        "manual_review_triggers": ["fixed threshold without authoritative source", "small or unclear sample unit", "multiple testing without correction policy"],
        "non_goals": ["Does not guarantee causal identification", "Does not define a universal p-value or model-fit cutoff"],
    },
    "model_validity": {
        "review_question": "Are the model split, baseline, ablation, leakage checks, and metric family sufficient for the intended claim?",
        "scientific_risk": "The paper may report model scores that are inflated, non-comparable, or unsupported by an appropriate validation design.",
        "allowed_claim_strength": "predictive",
        "repair_priority": ["method_rescue", "data_rescue", "result_downgrade", "human_checkpoint"],
        "manual_review_triggers": ["missing baseline", "missing ablation", "unlabeled sample unit", "metric without benchmark context"],
        "non_goals": ["Does not assert a universal AUC/F1 threshold", "Does not replace domain-specific external validation"],
    },
    "data_validity": {
        "review_question": "Are data roles, sample units, coverage, missingness, cohort boundaries, and provenance sufficient for the analysis?",
        "scientific_risk": "The methods and figures may be built on inconsistent cohorts, hidden missingness, or invalid sample-unit assumptions.",
        "allowed_claim_strength": "descriptive",
        "repair_priority": ["data_rescue", "method_rescue", "result_downgrade", "human_checkpoint"],
        "manual_review_triggers": ["ambiguous cohort", "missing provenance", "unresolved batch or coverage boundary", "train/test dependence risk"],
        "non_goals": ["Does not judge whether the research question is novel", "Does not fetch private data automatically"],
    },
    "figure_claim_validity": {
        "review_question": "Does the figure answer the declared scientific question with valid variables, panels, metric dimensions, and claim scope?",
        "scientific_risk": "A visually valid figure may still fail to support the stated result or may mix incompatible quantities.",
        "allowed_claim_strength": "descriptive",
        "repair_priority": ["result_downgrade", "method_rescue", "data_rescue", "human_checkpoint"],
        "manual_review_triggers": ["identifier-vs-identifier plot", "mixed metric dimensions", "missing method output", "caption overclaims panel evidence"],
        "non_goals": ["Does not approve aesthetic style alone", "Does not allow substitute figures outside the research contract"],
    },
    "citation_and_manuscript_validity": {
        "review_question": "Do citations, claim scope, section placement, availability statements, and manuscript assertions match the evidence?",
        "scientific_risk": "The draft may contain unsupported claims, misplaced references, or writing that exceeds the evidence snapshot.",
        "allowed_claim_strength": "descriptive",
        "repair_priority": ["manuscript_repair", "citation_repair", "result_downgrade", "human_checkpoint"],
        "manual_review_triggers": ["citation supports only background", "claim not covered by reference summary", "result leakage into introduction"],
        "non_goals": ["Does not delete references by default", "Does not override verified scientific evidence"],
    },
    "reproducibility_and_operational_validity": {
        "review_question": "Are environment, dependencies, seeds, remote-compute provenance, and fixture/smoke-test boundaries recorded?",
        "scientific_risk": "The analysis may not be reproducible or may depend on hidden credentials, private paths, or unrecorded runtime state.",
        "allowed_claim_strength": "descriptive",
        "repair_priority": ["method_rescue", "data_rescue", "human_checkpoint"],
        "manual_review_triggers": ["missing seed", "missing dependency version", "credential-dependent data route", "no fixture or smoke test"],
        "non_goals": ["Does not vendor third-party code automatically", "Does not expose private server or credential details"],
    },
}


DATA_CONNECTOR_KEYWORDS: dict[str, dict[str, Any]] = {
    "table_file_connector": {
        "terms": ["csv", "tsv", "parquet", "excel", "xlsx", "dataframe", "tabular"],
        "access_modes": ["local_file"],
        "data_formats": ["csv", "tsv", "parquet", "xlsx"],
    },
    "api_data_connector": {
        "terms": ["api", "rest", "graphql", "download", "query", "endpoint", "client"],
        "access_modes": ["api", "download"],
        "data_formats": ["json", "csv", "domain_specific"],
    },
    "remote_compute_data_connector": {
        "terms": ["ssh", "server", "remote", "cluster", "hpc", "stream", "scp", "rsync"],
        "access_modes": ["remote_server", "streaming"],
        "data_formats": ["domain_specific", "archive", "table"],
    },
    "geospatial_data_connector": {
        "terms": ["geotiff", "shapefile", "geojson", "raster", "vector", "google earth engine", "gee", "crs"],
        "access_modes": ["local_file", "api"],
        "data_formats": ["geotiff", "shapefile", "geojson", "raster", "vector"],
    },
    "astronomy_archive_connector": {
        "terms": ["fits", "votable", "catalog", "light curve", "spectrum", "telescope", "archive", "wcs"],
        "access_modes": ["archive_query", "local_file"],
        "data_formats": ["fits", "votable", "csv", "light_curve", "spectrum"],
    },
    "biomedical_matrix_connector": {
        "terms": ["h5ad", "fastq", "fasta", "bam", "dicom", "bids", "expression matrix", "omics"],
        "access_modes": ["repository_download", "local_file"],
        "data_formats": ["h5ad", "fastq", "fasta", "bam", "dicom", "bids"],
    },
}


METHOD_TEMPLATE_KEYWORDS: dict[str, dict[str, Any]] = {
    "statistical_modeling_template": {
        "terms": ["regression", "anova", "mixed model", "survival", "cox", "bootstrap", "bayesian", "hypothesis test"],
        "method_family": "statistical_modeling",
        "input_roles": ["analysis_table", "target_or_response", "predictor_columns"],
        "output_artifacts": ["results/tables/statistical_model_summary.csv", "results/figures/model_diagnostics.png"],
    },
    "machine_learning_model_template": {
        "terms": ["random forest", "xgboost", "classifier", "classification", "baseline", "ablation", "cross validation", "calibration"],
        "method_family": "supervised_learning",
        "input_roles": ["feature_matrix", "target_or_label", "split_definition"],
        "output_artifacts": ["results/tables/model_metrics.csv", "results/figures/model_performance.png"],
    },
    "deep_learning_training_template": {
        "terms": ["deep learning", "transformer", "cnn", "resnet", "pytorch", "tensorflow", "training loop", "embedding"],
        "method_family": "deep_learning_training",
        "input_roles": ["training_dataset", "validation_dataset", "model_config"],
        "output_artifacts": ["results/tables/training_metrics.csv", "results/figures/training_curves.png", "methods/artifacts/model.pt"],
    },
    "geospatial_analysis_template": {
        "terms": ["spatial join", "zonal statistics", "reprojection", "spatial block", "kriging", "autocorrelation", "moran"],
        "method_family": "geospatial_analysis",
        "input_roles": ["spatial_units", "raster_or_vector_data", "coordinate_reference_system"],
        "output_artifacts": ["results/tables/spatial_summary.csv", "results/figures/spatial_validation.png"],
    },
    "time_series_analysis_template": {
        "terms": ["time series", "forecast", "seasonality", "light curve", "temporal", "sliding window", "irregular"],
        "method_family": "time_series_analysis",
        "input_roles": ["time_index", "observation_series", "group_or_source_id"],
        "output_artifacts": ["results/tables/time_series_features.csv", "results/figures/time_series_patterns.png"],
    },
    "publication_figure_template": {
        "terms": ["matplotlib", "seaborn", "plot", "figure", "visualization", "panel", "caption", "dpi"],
        "method_family": "publication_visualization",
        "input_roles": ["result_table", "figure_metadata"],
        "output_artifacts": ["results/figures/publication_panel.png", "results/figure_metadata.json"],
    },
}


ACADEMICFORGE_COLLECTION_PREFIXES = {
    "claude-science": "cs",
    "scientific-agent-skills": "sa",
    "AI-research-SKILLs": "air",
    "nature-skills": "ns",
}


def _privacy_scan_text(text: str) -> dict[str, Any]:
    findings = []
    for pattern in SENSITIVE_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            findings.append({"pattern": pattern, "count": len(matches)})
    return {
        "status": "failed" if findings else "passed",
        "findings": findings,
    }


def _render_candidate_summary(manifest: dict[str, Any]) -> str:
    return "\n".join([
        "# Plugin Candidate Summary",
        "",
        f"Candidate: `{manifest.get('candidate_id')}`",
        f"Plugin id: `{manifest.get('plugin_id')}`",
        f"Discipline: `{manifest.get('discipline')}`",
        f"Method family: `{manifest.get('method_family')}`",
        "",
        "This is a candidate contribution package. It must be generalized, privacy-scanned, fixture-tested, and user-approved before any GitHub fork or PR workflow.",
    ])


def _render_support_candidate_summary(manifest: dict[str, Any]) -> str:
    return "\n".join([
        "# Support Candidate Summary",
        "",
        f"Candidate: `{manifest.get('candidate_id')}`",
        f"Support type: `{manifest.get('support_type')}`",
        f"Intended support target: `{manifest.get('intended_support_target')}`",
        f"Discipline for review-rule backflow: `{manifest.get('discipline')}`",
        "",
        "This is a support-layer candidate. It must not be promoted into `discipline_modules/` as a formal discipline plugin.",
        "Only extracted `data_connector`, `method_template`, and `review_rule` candidates may enter formal discipline modules after validation and human confirmation.",
        "",
        "## Review Rule Backflow Candidates",
        *[f"- `{candidate_id}`" for candidate_id in (manifest.get("review_rule_backflow_candidate_ids") or [])],
    ])
