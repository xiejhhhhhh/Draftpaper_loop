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

from .discipline import infer_discipline_from_text, infer_discipline_profile
from .discipline_modules import get_discipline_module
from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .safe_fetch import SafeFetchError, fetch_text


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


def _pipeline_hooks_for_rule(rule_family: str) -> dict[str, str]:
    return dict(REVIEW_RULE_PIPELINE_HOOKS.get(rule_family, {
        "research_plan": "optional",
        "data_acquisition": "optional",
        "method_plan": "optional",
        "figure_contract": "optional",
        "result_support_checkpoint": "optional",
        "write_results": "optional",
        "write_discussion": "optional",
        "citation_audit": "optional",
        "reviewer_rescue_loop": "required",
    }))


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


def _infer_skill_profile(text: str, discipline: str | None) -> dict[str, Any]:
    if discipline and discipline != "auto":
        return {
            "discipline": discipline,
            "primary_discipline": discipline,
            "secondary_disciplines": [],
            "discipline_modules": ["default", discipline] if discipline != "default" else ["default"],
        }
    return infer_discipline_from_text(text)


def _support_routes_for_text(text: str) -> list[str]:
    lowered = text.lower()
    routes = []
    for route, terms in SUPPORT_ROUTE_KEYWORDS.items():
        if any(term in lowered for term in terms):
            routes.append(route)
    return routes or ["shared_capability"]


def _matched_dimension_terms(lowered: str, dimension: str, family_terms: list[str]) -> list[str]:
    terms = list(REVIEW_RULE_SIGNAL_DIMENSIONS.get(dimension) or [])
    if dimension in {"scientific_action", "evidence_binding", "failure_observable"}:
        terms.extend(family_terms)
    matches: list[str] = []
    for term in terms:
        if term in lowered and term not in matches:
            matches.append(term)
    return matches


def _review_rule_signal_scan(text: str, review_rule_hints: dict[str, list[str]]) -> dict[str, Any]:
    """Return auditable signal scores for review-rule backflow extraction."""

    lowered = text.lower()
    family_scans: dict[str, dict[str, Any]] = {}
    for family, matched_terms in sorted(review_rule_hints.items()):
        dimensions: dict[str, dict[str, Any]] = {}
        for dimension in REVIEW_RULE_SIGNAL_DIMENSIONS:
            matches = _matched_dimension_terms(lowered, dimension, matched_terms)
            if dimension == "generalization_risk":
                passed = len(matches) == 0
            elif dimension == "repair_route":
                passed = bool(matches) or REVIEW_RULE_KEYWORDS.get(family, {}).get("failure_route") is not None
            elif dimension == "threshold_source_quality":
                passed = bool(matches)
            elif dimension == "discipline_specificity":
                passed = bool(matches)
            else:
                passed = bool(matches)
            dimensions[dimension] = {
                "passed": passed,
                "matched_terms": matches[:20],
            }
        core_ready = all(dimensions[key]["passed"] for key in ["scientific_action", "evidence_binding", "failure_observable"])
        evidence_bound = bool(dimensions["evidence_binding"]["passed"])
        has_repair_route = bool(dimensions["repair_route"]["passed"])
        threshold_has_source = bool(dimensions["threshold_source_quality"]["passed"])
        generalization_risk_low = bool(dimensions["generalization_risk"]["passed"])
        score = sum(1 for value in dimensions.values() if value["passed"])
        if not core_ready:
            recommendation = "do_not_generate_rule_candidate"
        elif not has_repair_route:
            recommendation = "advisory_candidate_only"
        elif not threshold_has_source:
            recommendation = "contextual_or_human_confirmed_candidate"
        elif not generalization_risk_low:
            recommendation = "candidate_requires_manual_generalization"
        else:
            recommendation = "review_rule_candidate"
        family_scans[family] = {
            "rule_family": family,
            "matched_terms": list(matched_terms),
            "score": score,
            "max_score": len(REVIEW_RULE_SIGNAL_DIMENSIONS),
            "core_ready": core_ready,
            "evidence_bound": evidence_bound,
            "has_repair_route": has_repair_route,
            "threshold_has_source": threshold_has_source,
            "generalization_risk_low": generalization_risk_low,
            "recommendation": recommendation,
            "dimensions": dimensions,
        }
    return {
        "scan_version": "review_rule_signal_scan.v1",
        "families": family_scans,
        "eligible_rule_families": [
            family for family, scan in family_scans.items()
            if scan["recommendation"] != "do_not_generate_rule_candidate"
        ],
        "policy": "Only evidence-bound, observable scientific quality signals may backflow into review_rule candidates; thresholds remain contextual unless sourced.",
    }


def _threshold_policy_for_text(text: str) -> dict[str, Any]:
    lowered = text.lower()
    fixed_match = re.search(r"p\s*(?:<|<=)\s*0\.0?5", lowered)
    if "benchmark" in lowered or "baseline" in lowered:
        return {"mode": "comparative", "value": None, "comparator": "not_applicable"}
    if fixed_match:
        return {"mode": "contextual", "value": "p<0.05 mentioned; require discipline/context confirmation", "comparator": "not_applicable"}
    if "journal" in lowered or "guideline" in lowered:
        return {"mode": "journal_guided", "value": None, "comparator": "not_applicable"}
    return {"mode": "contextual", "value": None, "comparator": "not_applicable"}


def _threshold_source_for_text(text: str) -> dict[str, Any]:
    lowered = text.lower()
    if "journal" in lowered or "guideline" in lowered:
        source_type = "journal_guideline"
    elif "benchmark" in lowered or "challenge" in lowered:
        source_type = "public_benchmark"
    elif "baseline" in lowered or "ablation" in lowered:
        source_type = "benchmark_comparison"
    elif "human confirmed" in lowered or "user confirmed" in lowered or "manual confirmation" in lowered:
        source_type = "user_confirmation"
    else:
        source_type = "source_skill_statement"
    return {
        "type": source_type,
        "citation_or_note": "Candidate extracted from skill/source text; maintainer must confirm before promotion.",
    }


def _threshold_validation_status(threshold_policy: dict[str, Any], threshold_source: dict[str, Any]) -> str:
    mode = str(threshold_policy.get("mode") or "contextual")
    source_type = str(threshold_source.get("type") or "source_skill_statement")
    if mode in {"fixed", "journal_guided"}:
        if source_type in {"journal_guideline", "discipline_convention", "public_benchmark", "benchmark_comparison", "user_confirmation"}:
            return "source_backed_requires_human_review"
        return "fixed_threshold_source_missing"
    if mode == "comparative":
        return "comparative_context_required"
    if mode == "human_confirmed":
        return "requires_user_confirmation"
    return "candidate_contextual"


def _criterion_type_for_rule_family(family: str) -> str:
    mapping = {
        "statistical_validity": "statistical_validation_condition",
        "model_validity": "model_quality_condition",
        "data_validity": "data_integrity_condition",
        "figure_claim_validity": "figure_claim_alignment_condition",
        "citation_and_manuscript_validity": "citation_and_claim_scope_condition",
        "reproducibility_and_operational_validity": "reproducibility_condition",
    }
    return mapping.get(family, "scientific_quality_gate")


def _support_layer_signal_refs(
    *,
    source: str,
    skill_id: str,
    family: str,
    support_routes: list[str] | None,
    matched_terms: list[str],
) -> list[dict[str, Any]]:
    routes = list(support_routes or []) or ["explicit_review"]
    return [
        {
            "source": source,
            "source_skill_id": skill_id,
            "source_type": route,
            "rule_family": family,
            "matched_terms": list(matched_terms[:20]),
            "extraction_policy": "metadata_only_review_rule_signal_scan",
        }
        for route in routes
    ]


def _metric_family_for_rule(rule_family: str, text: str) -> str | None:
    lowered = text.lower()
    for metric in ["auc", "f1", "accuracy", "r2", "r²", "rmse", "mae", "p-value", "p value"]:
        if metric in lowered:
            return "r2" if metric in {"r²", "r2"} else metric.replace(" ", "_")
    if rule_family == "model_validity":
        return "task_metric"
    if rule_family == "statistical_validity":
        return "statistical_inference"
    return None


def _review_rule_rationale(manifest: dict[str, Any]) -> str:
    return "\n".join([
        f"# Review Rule Candidate: {manifest.get('rule_id')}",
        "",
        "This candidate is a metadata-only, generalized review rule extracted from a skill/source description.",
        "It must be fixture-tested and manually confirmed before promotion into a formal discipline module.",
        "",
        "## Scope",
        f"- Rule family: `{manifest.get('rule_family')}`",
        f"- Applicable disciplines: {', '.join(str(item) for item in manifest.get('applicable_disciplines') or [])}",
        f"- Evidence roles: {', '.join(str(item) for item in manifest.get('evidence_roles') or [])}",
        f"- Failure route: `{manifest.get('failure_route')}`",
        f"- Blocking level: `{manifest.get('blocking_level')}`",
        "",
        "## Matched Signals",
        *[f"- `{term}`" for term in (manifest.get('matched_terms') or [])],
        "",
        "## Signal Scan",
        f"- Recommendation: `{manifest.get('backflow_recommendation')}`",
        f"- Score: `{manifest.get('signal_score')}`",
        *[
            f"- {name}: {'passed' if (detail or {}).get('passed') else 'not confirmed'}; terms={', '.join((detail or {}).get('matched_terms') or []) or 'none'}"
            for name, detail in sorted(((manifest.get('signal_dimensions') or {}).items()))
        ],
        "",
        "## Threshold Policy",
        f"- Mode: `{(manifest.get('threshold_policy') or {}).get('mode')}`",
        f"- Source type: `{(manifest.get('threshold_source') or {}).get('type')}`",
        "",
        "## Human Review Notes",
        "- Confirm that this is a discipline-general rule, not a project-specific preference.",
        "- Confirm that any numeric threshold is contextual unless backed by a journal guideline, discipline convention, or public benchmark.",
        "- Confirm that the positive and negative fixtures cover the evidence roles named above.",
    ])


def _review_rule_fixture(manifest: dict[str, Any], *, positive: bool) -> dict[str, Any]:
    rule_id = str(manifest.get("rule_id") or manifest.get("candidate_id") or "review_rule")
    evidence_roles = [str(item) for item in manifest.get("evidence_roles") or ["review_rule_evidence"]]
    return {
        "fixture_id": f"{rule_id}_{'positive' if positive else 'negative'}_fixture",
        "rule_id": rule_id,
        "expected_status": "passed" if positive else "failed",
        "evidence": {
            role: {
                "present": positive,
                "unit_or_scale": manifest.get("unit_or_scale") or "context_bound",
                "metric_family": manifest.get("metric_family"),
                "sample_unit": "fixture_sample_unit",
                "notes": "Synthetic fixture for schema and rule-behavior validation; replace with discipline fixture before promotion.",
            }
            for role in evidence_roles
        },
        "expected_failure_route": None if positive else manifest.get("failure_route") or "human_checkpoint",
        "source_policy": "synthetic_fixture_no_third_party_source",
    }


def _validate_review_rule_fixture_pair(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate the synthetic positive/negative contract without executing candidate code."""

    rule_id = str(manifest.get("rule_id") or manifest.get("candidate_id") or "")
    required_roles = [str(item) for item in manifest.get("minimum_evidence_required") or manifest.get("evidence_roles") or []]
    expected_route = str(manifest.get("failure_route") or "human_checkpoint")
    problems: list[str] = []
    fixture_summaries: list[dict[str, Any]] = []
    for polarity, expected_status in (("positive", "passed"), ("negative", "failed")):
        path = root / f"{polarity}_fixture.json"
        fixture = _read_json(path, {})
        evidence = fixture.get("evidence") if isinstance(fixture.get("evidence"), dict) else {}
        missing_roles = [role for role in required_roles if role not in evidence]
        present_values = [bool((evidence.get(role) or {}).get("present")) for role in required_roles]
        fixture_problems: list[str] = []
        if not fixture:
            fixture_problems.append("missing_or_invalid_json")
        if str(fixture.get("rule_id") or "") != rule_id:
            fixture_problems.append("rule_id_mismatch")
        if str(fixture.get("expected_status") or "") != expected_status:
            fixture_problems.append("expected_status_mismatch")
        if missing_roles:
            fixture_problems.append("missing_required_evidence_roles")
        if polarity == "positive" and required_roles and not all(present_values):
            fixture_problems.append("positive_fixture_has_absent_evidence")
        if polarity == "negative" and required_roles and all(present_values):
            fixture_problems.append("negative_fixture_does_not_fail_evidence")
        if polarity == "negative" and str(fixture.get("expected_failure_route") or "") != expected_route:
            fixture_problems.append("failure_route_mismatch")
        if fixture.get("source_policy") != "synthetic_fixture_no_third_party_source":
            fixture_problems.append("unsafe_fixture_source_policy")
        problems.extend(f"{polarity}:{item}" for item in fixture_problems)
        fixture_summaries.append({
            "fixture": path.name,
            "expected_status": expected_status,
            "required_evidence_roles": required_roles,
            "problems": fixture_problems,
        })
    return {
        "status": "passed" if not problems else "failed",
        "validation_level": "synthetic_contract",
        "runtime_execution_performed": False,
        "fixtures": fixture_summaries,
        "problems": problems,
    }


def _review_rule_backflow_scope(review_rules: list[dict[str, Any]]) -> dict[str, list[str]]:
    scope: dict[str, list[str]] = {family: [] for family in REVIEW_RULE_KEYWORDS}
    for rule in review_rules:
        family = str(rule.get("rule_family") or "")
        candidate_id = str(rule.get("candidate_id") or rule.get("rule_id") or "")
        if family in scope and candidate_id:
            scope[family].append(candidate_id)
    return {family: ids for family, ids in scope.items() if ids}


def _capability_ir_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    plugin_type = manifest.get("plugin_type")
    support_type = manifest.get("support_type")
    capability_kind = "formal_discipline_plugin" if plugin_type in FORMAL_DISCIPLINE_PLUGIN_TYPES else "support_layer_candidate"
    if plugin_type == "data_connector":
        scientific_action = manifest.get("connector_id")
        target = manifest.get("intended_merge_target")
    elif plugin_type == "method_template":
        scientific_action = manifest.get("method_family") or manifest.get("template_id")
        target = manifest.get("intended_merge_target")
    elif plugin_type == "review_rule":
        scientific_action = manifest.get("rule_family") or manifest.get("rule_id")
        target = manifest.get("intended_merge_target")
    else:
        scientific_action = support_type or manifest.get("candidate_id")
        target = manifest.get("intended_support_target")
    return {
        "ir_version": CAPABILITY_IR_VERSION,
        "capability_id": manifest.get("candidate_id") or manifest.get("plugin_id"),
        "capability_kind": capability_kind,
        "formal_plugin_type": plugin_type if plugin_type in FORMAL_DISCIPLINE_PLUGIN_TYPES else None,
        "support_type": support_type if support_type in SUPPORT_LAYER_TYPES else None,
        "primary_discipline": manifest.get("primary_discipline") or manifest.get("discipline") or "default",
        "secondary_disciplines": list(manifest.get("secondary_disciplines") or []),
        "discipline_modules": list(manifest.get("discipline_modules") or []),
        "scientific_action": scientific_action,
        "input_roles": list(manifest.get("input_roles") or manifest.get("applicable_data_roles") or []),
        "output_roles": list(manifest.get("output_artifacts") or manifest.get("evidence_roles") or []),
        "evidence_roles": list(manifest.get("evidence_roles") or []),
        "method_family": manifest.get("method_family") or manifest.get("model_family"),
        "rule_family": manifest.get("rule_family"),
        "review_rule_backflow_candidate_ids": list(manifest.get("review_rule_backflow_candidate_ids") or []),
        "review_rule_backflow_scope": dict(manifest.get("review_rule_backflow_scope") or {}),
        "review_rule_signal_scan": manifest.get("review_rule_signal_scan") or manifest.get("backflow_signal_scan") or {},
        "signal_score": manifest.get("signal_score"),
        "backflow_recommendation": manifest.get("backflow_recommendation"),
        "maturity": manifest.get("maturity") or "candidate",
        "deployment_state": manifest.get("deployment_state") or ("review_rule_candidate" if plugin_type == "review_rule" else "candidate"),
        "promotion_allowed": bool(manifest.get("promotion_allowed", plugin_type in FORMAL_DISCIPLINE_PLUGIN_TYPES)),
        "human_confirmation_required": bool(manifest.get("human_confirmation_required", True)),
        "source": manifest.get("source"),
        "source_skill_id": manifest.get("source_skill_id"),
        "source_policy": manifest.get("source_policy"),
        "intended_target": target,
    }


def _runtime_metadata(manifest: dict[str, Any]) -> dict[str, str]:
    """Infer safe execution metadata without claiming an unrun external service."""

    declared_class = str(manifest.get("runtime_class") or "")
    declared_level = str(manifest.get("validation_level") or "")
    access_modes = " ".join(str(item).lower() for item in manifest.get("access_modes") or [])
    packages = " ".join(str(item).lower() for item in manifest.get("packages") or [])
    method_text = " ".join(str(manifest.get(key) or "").lower() for key in ["method_family", "template_id", "connector_id"])
    if declared_class in RUNTIME_CLASSES:
        runtime_class = declared_class
    elif any(token in access_modes for token in ["ssh", "remote_server", "cluster"]):
        runtime_class = "remote_server"
    elif any(token in access_modes for token in ["api", "archive_query", "web_download"]):
        runtime_class = "remote_api"
    elif any(token in f"{packages} {method_text}" for token in ["gpu", "cuda", "deepspeed", "megatron"]):
        runtime_class = "gpu_model"
    elif manifest.get("packages"):
        runtime_class = "local_optional_dependency"
    else:
        runtime_class = "local_pure_python"
    validation_level = declared_level if declared_level in VALIDATION_LEVELS else "plan_only"
    return {"runtime_class": runtime_class, "validation_level": validation_level}


def _capability_ir_records_from_hints(
    *,
    source: str,
    skill_id: str,
    profile: dict[str, Any],
    hints: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build metadata-only capability IR records before candidate extraction.

    This intentionally records only matched capability families and deployment
    targets. It must not copy third-party skill text or executable source code.
    """

    primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
    secondary = list(profile.get("secondary_disciplines") or [])
    modules = list(profile.get("discipline_modules") or (["default", primary] if primary != "default" else ["default"]))
    records: list[dict[str, Any]] = []

    for connector_family in sorted((hints.get("data_connector") or {}).keys()):
        config = DATA_CONNECTOR_KEYWORDS.get(connector_family, {})
        connector_id = _safe_id(f"{skill_id}_{connector_family}")
        records.append(_capability_ir_from_manifest({
            "candidate_id": connector_id,
            "plugin_type": "data_connector",
            "connector_id": connector_id,
            "primary_discipline": primary,
            "secondary_disciplines": secondary,
            "discipline_modules": modules,
            "input_roles": [],
            "output_artifacts": list(config.get("data_formats") or []),
            "maturity": "candidate",
            "deployment_state": "data_connector_candidate",
            "human_confirmation_required": True,
            "source": source,
            "source_skill_id": skill_id,
            "source_policy": "metadata_index_only_no_direct_upload",
            "intended_merge_target": f"draftpaper_cli/discipline_modules/{primary}/data_connectors/{connector_id}",
        }))

    for template_family in sorted((hints.get("method_template") or {}).keys()):
        config = METHOD_TEMPLATE_KEYWORDS.get(template_family, {})
        template_id = _safe_id(f"{skill_id}_{template_family}")
        records.append(_capability_ir_from_manifest({
            "candidate_id": template_id,
            "plugin_type": "method_template",
            "template_id": template_id,
            "method_family": config.get("method_family") or template_family,
            "primary_discipline": primary,
            "secondary_disciplines": secondary,
            "discipline_modules": modules,
            "input_roles": list(config.get("input_roles") or []),
            "output_artifacts": list(config.get("output_artifacts") or []),
            "maturity": "candidate",
            "deployment_state": "method_template_candidate",
            "human_confirmation_required": True,
            "source": source,
            "source_skill_id": skill_id,
            "source_policy": "metadata_index_only_no_direct_upload",
            "intended_merge_target": f"draftpaper_cli/discipline_modules/{primary}/method_templates/{template_id}",
        }))

    review_rule_ids: list[str] = []
    review_rule_scope: dict[str, list[str]] = {}
    signal_scan = hints.get("review_rule_signal_scan") or {}
    signal_families = signal_scan.get("families") or {}
    for rule_family in sorted((hints.get("review_rule") or {}).keys()):
        rule_id = _safe_id(f"{skill_id}_{rule_family}")
        family_signal = signal_families.get(rule_family) or {}
        review_rule_ids.append(rule_id)
        review_rule_scope.setdefault(rule_family, []).append(rule_id)
        family_meta = REVIEW_RULE_FAMILY_METADATA.get(rule_family, {})
        records.append(_capability_ir_from_manifest({
            "candidate_id": rule_id,
            "plugin_type": "review_rule",
            "rule_id": rule_id,
            "rule_family": rule_family,
            "primary_discipline": primary,
            "secondary_disciplines": secondary,
            "discipline_modules": modules,
            "evidence_roles": [f"{rule_family}_evidence"],
            "review_rule_signal_scan": family_signal,
            "signal_score": family_signal.get("score"),
            "backflow_recommendation": family_signal.get("recommendation"),
            "maturity": "candidate",
            "deployment_state": "review_rule_candidate",
            "human_confirmation_required": True,
            "review_question": family_meta.get("review_question"),
            "scientific_risk": family_meta.get("scientific_risk"),
            "source": source,
            "source_skill_id": skill_id,
            "source_policy": "metadata_index_only_no_direct_upload",
            "intended_merge_target": f"draftpaper_cli/discipline_modules/{primary}/review_rules/{rule_id}",
        }))

    for route in hints.get("support_routes") or []:
        route_meta = SUPPORT_ROUTE_TARGETS.get(route)
        if not route_meta:
            continue
        support_id = _safe_id(f"{skill_id}_{route}")
        records.append(_capability_ir_from_manifest({
            "candidate_id": support_id,
            "candidate_kind": "support_candidate",
            "support_type": route,
            "primary_discipline": primary,
            "secondary_disciplines": secondary,
            "review_rule_backflow_candidate_ids": review_rule_ids,
            "review_rule_backflow_scope": review_rule_scope,
            "backflow_signal_scan": signal_scan,
            "maturity": "candidate",
            "deployment_state": "support_only",
            "promotion_allowed": False,
            "human_confirmation_required": True,
            "source": source,
            "source_skill_id": skill_id,
            "source_policy": "metadata_index_only_no_direct_upload",
            "intended_support_target": route_meta["target"],
        }))

    return records


def _support_backflow_links_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    backflow_ids = [str(item) for item in manifest.get("review_rule_backflow_candidate_ids") or []]
    return {
        "support_candidate_id": manifest.get("candidate_id"),
        "support_type": manifest.get("support_type"),
        "backflow_review_rule_ids": backflow_ids,
        "backflow_scope": manifest.get("review_rule_backflow_scope") or {},
        "backflow_signal_scan": manifest.get("backflow_signal_scan") or {},
        "backflow_reason": (
            "This support-layer candidate contains reusable validation conditions that can be generalized "
            "into discipline-specific review_rule candidates."
            if backflow_ids else
            "No reusable validation condition was confidently extracted from this support-layer candidate."
        ),
        "non_backflow_reason": None if backflow_ids else "No statistical, model, data, figure, citation, or reproducibility gate was identified.",
        "manual_confirmation_required": True,
        "promotion_allowed": False,
    }


def _review_rule_backflow_source_type(support_routes: list[str] | None) -> str:
    routes = [str(item) for item in support_routes or []]
    for route in ["workflow_recipe", "paper_contract", "shared_capability", "data_connector", "method_template"]:
        if route in routes:
            return route
    return "explicit_review"


def _review_rule_evidence_binding(family: str, evidence_roles: list[str]) -> dict[str, Any]:
    record_types_by_family = {
        "statistical_validity": ["metric", "method_output", "figure"],
        "model_validity": ["method_output", "metric", "figure"],
        "data_validity": ["data", "method_output", "metric"],
        "figure_claim_validity": ["figure", "metric", "manuscript"],
        "citation_and_manuscript_validity": ["citation", "manuscript", "figure"],
        "reproducibility_and_operational_validity": ["method_output", "data", "metric"],
    }
    conflicts_by_family = {
        "statistical_validity": ["metric_without_unit_or_test_context", "effect_claim_without_uncertainty"],
        "model_validity": ["train_test_leakage", "baseline_missing_for_performance_claim"],
        "data_validity": ["sample_unit_conflict", "cohort_boundary_conflict"],
        "figure_claim_validity": ["identifier_axis_as_scientific_variable", "mixed_metric_dimension"],
        "citation_and_manuscript_validity": ["unsupported_claim", "citation_scope_mismatch"],
        "reproducibility_and_operational_validity": ["missing_run_provenance", "credential_dependent_unverified_data"],
    }
    return {
        "registry_record_types": record_types_by_family.get(family, ["method_output", "metric"]),
        "required_fields": list(evidence_roles),
        "forbidden_conflicts": conflicts_by_family.get(family, []),
    }


def _extract_review_rule_manifests(
    text: str,
    *,
    source: str,
    skill_id: str,
    profile: dict[str, Any],
    support_routes: list[str] | None = None,
) -> list[dict[str, Any]]:
    lowered = text.lower()
    manifests = []
    primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
    disciplines = [primary] + [str(item) for item in profile.get("secondary_disciplines") or []]
    for family, config in REVIEW_RULE_KEYWORDS.items():
        matched_terms = [term for term in config["terms"] if term in lowered]
        if not matched_terms:
            continue
        signal_scan = (_review_rule_signal_scan(text, {family: matched_terms}).get("families") or {}).get(family, {})
        if signal_scan.get("recommendation") == "do_not_generate_rule_candidate":
            continue
        rule_stem = _safe_id(f"{skill_id}_{family}")
        family_meta = REVIEW_RULE_FAMILY_METADATA.get(family, {})
        evidence_roles = [f"{family}_evidence"]
        fixture_refs = ["positive_fixture.json", "negative_fixture.json"]
        threshold_policy = _threshold_policy_for_text(text)
        threshold_source = _threshold_source_for_text(text)
        manifests.append({
            "status": "candidate_extracted",
            "candidate_id": rule_stem,
            "generated_at": utc_now(),
            "source": source,
            "source_skill_id": skill_id,
            "plugin_type": "review_rule",
            "plugin_id": f"{primary}.review.{rule_stem}",
            "rule_id": rule_stem,
            "rule_group_id": rule_stem,
            "rule_family": family,
            "criterion_type": _criterion_type_for_rule_family(family),
            "display_name": " ".join(part.capitalize() for part in rule_stem.split("_")[:8]),
            "discipline": primary,
            "primary_discipline": primary,
            "secondary_disciplines": [item for item in disciplines if item != primary],
            "discipline_modules": profile.get("discipline_modules") or ["default", primary],
            "applicable_disciplines": disciplines,
            "applicable_methods": [],
            "applicable_data_roles": [],
            "evidence_roles": evidence_roles,
            "evidence_binding": _review_rule_evidence_binding(family, evidence_roles),
            "checks": list(config["checks"]),
            "matched_terms": matched_terms,
            "review_rule_signal_scan": signal_scan,
            "signal_score": signal_scan.get("score"),
            "signal_dimensions": signal_scan.get("dimensions") or {},
            "backflow_recommendation": signal_scan.get("recommendation"),
            "metric_family": _metric_family_for_rule(family, text),
            "unit_or_scale": "context_bound",
            "threshold_policy": threshold_policy,
            "threshold_source": threshold_source,
            "threshold_mode": threshold_policy.get("mode"),
            "threshold_validation_status": _threshold_validation_status(threshold_policy, threshold_source),
            "minimum_sample_policy": "context_bound; infer from discipline/method fixture before blocking",
            "model_family": "context_bound" if family == "model_validity" else None,
            "blocking_level": "warn_and_repair",
            "failure_route": config["failure_route"],
            "pipeline_hooks": _pipeline_hooks_for_rule(family),
            "maturity": "candidate",
            "deployment_state": "review_rule_candidate",
            "human_confirmation_required": True,
            "review_question": family_meta.get("review_question") or "Does the evidence satisfy this discipline-aware review condition?",
            "scientific_risk": family_meta.get("scientific_risk") or "The manuscript may make a claim that is not supported by the available evidence.",
            "minimum_evidence_required": evidence_roles,
            "sample_unit_policy": "must be declared before the rule blocks a scientific claim",
            "metric_dimension_policy": "must be compatible with the declared metric family and figure contract",
            "allowed_claim_strength": family_meta.get("allowed_claim_strength") or "exploratory",
            "repair_priority": list(family_meta.get("repair_priority") or [config["failure_route"], "human_checkpoint"]),
            "manual_review_triggers": list(family_meta.get("manual_review_triggers") or []),
            "non_goals": list(family_meta.get("non_goals") or []),
            "fixture_paths": fixture_refs,
            "positive_fixture_refs": ["positive_fixture.json"],
            "negative_fixture_refs": ["negative_fixture.json"],
            "source_skill_refs": [f"{source}:{skill_id}"],
            "backflow_source_type": _review_rule_backflow_source_type(support_routes),
            "support_layer_signal_refs": _support_layer_signal_refs(
                source=source,
                skill_id=skill_id,
                family=family,
                support_routes=support_routes,
                matched_terms=matched_terms,
            ),
            "aliases": [rule_stem, family],
            "variants": [f"{primary}_{family}_candidate"],
            "source_policy": "candidate_only_no_direct_upload",
            "intended_merge_target": f"draftpaper_cli/discipline_modules/{primary}/review_rules/{rule_stem}",
            "provenance_notes": "Generated from a source skill. Keep as candidate until fixture-tested and human-approved.",
        })
    return manifests


def _extract_support_candidate_manifests(
    *,
    source: str,
    skill_id: str,
    profile: dict[str, Any],
    support_routes: list[str],
    review_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
    review_rule_ids = [str(rule.get("candidate_id")) for rule in review_rules if rule.get("candidate_id")]
    review_rule_scope = _review_rule_backflow_scope(review_rules)
    backflow_signal_scan = {
        "scan_version": "review_rule_signal_scan.v1",
        "families": {
            str(rule.get("rule_family")): rule.get("review_rule_signal_scan")
            for rule in review_rules
            if rule.get("rule_family") and rule.get("review_rule_signal_scan")
        },
        "eligible_rule_families": sorted({str(rule.get("rule_family")) for rule in review_rules if rule.get("rule_family")}),
    }
    manifests: list[dict[str, Any]] = []
    for route in support_routes:
        route_meta = SUPPORT_ROUTE_TARGETS.get(route)
        if not route_meta:
            continue
        support_id = _safe_id(f"{skill_id}_{route}")
        manifests.append({
            "status": "support_candidate_extracted",
            "candidate_id": support_id,
            "generated_at": utc_now(),
            "source": source,
            "source_skill_id": skill_id,
            "candidate_kind": "support_candidate",
            "support_type": route,
            "discipline": primary,
            "primary_discipline": primary,
            "secondary_disciplines": profile.get("secondary_disciplines") or [],
            "intended_support_target": route_meta["target"],
            "support_purpose": route_meta["purpose"],
            "review_rule_backflow_candidate_ids": review_rule_ids,
            "review_rule_backflow_scope": review_rule_scope,
            "backflow_signal_scan": backflow_signal_scan,
            "source_policy": "candidate_only_no_direct_upload",
            "maturity": "candidate",
            "deployment_state": "support_only",
            "human_confirmation_required": True,
            "promotion_allowed": False,
            "promotion_policy": (
                "Support candidates must not be promoted into discipline_modules. "
                "Only extracted data_connector, method_template, and review_rule candidates may be promoted there."
            ),
            "formal_plugin_types": ["data_connector", "method_template", "review_rule"],
        })
    return manifests


def _package_names_from_text(text: str) -> list[str]:
    known = [
        "numpy", "pandas", "scipy", "statsmodels", "scikit-learn", "sklearn", "xgboost", "lightgbm",
        "torch", "pytorch", "tensorflow", "matplotlib", "seaborn", "geopandas", "rasterio", "xarray",
        "earthengine-api", "ee", "astropy", "astroquery", "lightkurve", "scanpy", "anndata",
        "pydicom", "nibabel", "lifelines", "shap",
    ]
    lowered = text.lower()
    packages = []
    for package in known:
        if package.lower() in lowered and package not in packages:
            packages.append(package)
    return packages


def _extract_data_connector_manifests(text: str, *, source: str, skill_id: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
    lowered = text.lower()
    primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
    packages = _package_names_from_text(text)
    manifests = []
    for connector_family, config in DATA_CONNECTOR_KEYWORDS.items():
        matched_terms = [term for term in config["terms"] if term in lowered]
        if not matched_terms:
            continue
        connector_id = _safe_id(f"{skill_id}_{connector_family}")
        requires_credentials = any(term in lowered for term in ["api key", "token", "credential", "login", "password"])
        manifests.append({
            "status": "candidate_extracted",
            "candidate_id": connector_id,
            "generated_at": utc_now(),
            "source": source,
            "source_skill_id": skill_id,
            "plugin_type": "data_connector",
            "plugin_id": f"{primary}.data.{connector_id}",
            "connector_id": connector_id,
            "display_name": " ".join(part.capitalize() for part in connector_id.split("_")[:8]),
            "discipline": primary,
            "primary_discipline": primary,
            "secondary_disciplines": profile.get("secondary_disciplines") or [],
            "discipline_modules": profile.get("discipline_modules") or ["default", primary],
            "access_modes": list(config["access_modes"]),
            "packages": packages,
            "package_modules": ["sklearn" if item == "scikit-learn" else item for item in packages],
            "download_or_access": ["plan_first_user_confirmed_fetch"],
            "data_formats": list(config["data_formats"]),
            "requires_credentials": requires_credentials,
            "credential_env_vars": [],
            "matched_terms": matched_terms,
            "template_paths": [],
            "fixture_paths": [],
            "genericity_rules": [
                "Parameterize dataset identifiers, date ranges, regions, cohort filters, and output paths.",
                "Do not package credentials, server addresses, private paths, or project-specific sample IDs.",
            ],
            "source_policy": "candidate_only_no_direct_upload",
            "intended_merge_target": f"draftpaper_cli/discipline_modules/{primary}/data_connectors/{connector_id}",
            "provenance_notes": "Generated from a source skill. Keep as candidate until fixture-tested and human-approved.",
        })
    return manifests


def _extract_method_template_manifests(text: str, *, source: str, skill_id: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
    lowered = text.lower()
    primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
    packages = _package_names_from_text(text)
    manifests = []
    for template_family, config in METHOD_TEMPLATE_KEYWORDS.items():
        matched_terms = [term for term in config["terms"] if term in lowered]
        if not matched_terms:
            continue
        template_id = _safe_id(f"{skill_id}_{template_family}")
        manifests.append({
            "status": "candidate_extracted",
            "candidate_id": template_id,
            "generated_at": utc_now(),
            "source": source,
            "source_skill_id": skill_id,
            "plugin_type": "method_template",
            "plugin_id": f"{primary}.method.{template_id}",
            "template_id": template_id,
            "display_name": " ".join(part.capitalize() for part in template_id.split("_")[:8]),
            "discipline": primary,
            "primary_discipline": primary,
            "secondary_disciplines": profile.get("secondary_disciplines") or [],
            "discipline_modules": profile.get("discipline_modules") or ["default", primary],
            "method_family": config["method_family"],
            "input_roles": list(config["input_roles"]),
            "optional_roles": [],
            "packages": packages,
            "package_modules": ["sklearn" if item == "scikit-learn" else item for item in packages],
            "output_artifacts": list(config["output_artifacts"]),
            "figure_groups": [],
            "formula_families": [],
            "validation_checks": ["evidence_role_binding", "figure_contract_binding", "fixture_smoke_test"],
            "matched_terms": matched_terms,
            "aliases": matched_terms[:10],
            "variants": ["candidate_from_skill_source"],
            "genericity_rules": [
                "Expose data roles, model parameters, output paths, and validation split definitions as parameters.",
                "Keep project-specific constants out of the promoted template.",
            ],
            "source_policy": "candidate_only_no_direct_upload",
            "intended_merge_target": f"draftpaper_cli/discipline_modules/{primary}/method_templates/{template_id}",
            "provenance_notes": "Generated from a source skill. Keep as candidate until fixture-tested and human-approved.",
        })
    return manifests


def _source_evidence_summary(text: str, manifests: list[dict[str, Any]], *, limit: int = 1800) -> str:
    """Return a bounded evidence summary without copying full third-party skill text."""

    terms: list[str] = []
    for manifest in manifests:
        for term in manifest.get("matched_terms") or []:
            value = str(term)
            if value not in terms:
                terms.append(value)
    lowered = text.lower()
    snippets: list[str] = []
    for term in terms[:12]:
        idx = lowered.find(term.lower())
        if idx < 0:
            continue
        start = max(0, idx - 90)
        end = min(len(text), idx + len(term) + 140)
        snippet = " ".join(text[start:end].split())
        if snippet and snippet not in snippets:
            snippets.append(snippet)
    summary = "\n".join([
        "# Source Evidence Summary",
        "",
        "This file stores bounded evidence snippets for candidate review only. It is not a copy of the source skill.",
        "",
        "Matched terms: " + ", ".join(terms[:30]),
        "",
        "## Snippets",
        *[f"- {snippet}" for snippet in snippets],
    ])
    return summary[:limit]


def extract_skill_capabilities(
    source_file: str | Path,
    *,
    source: str = "local_skill",
    skill_id: str | None = None,
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    """Extract Draftpaper-loop plugin candidates from a skill/source text file.

    This writes metadata-only candidates. It does not copy third-party source code
    into runtime modules and never promotes directly into discipline_modules.
    """

    path = Path(source_file).resolve()
    if not path.exists():
        raise PluginCandidateError(f"Missing source file: {path}")
    text = _read_text(path, limit=120_000)
    resolved_skill_id = _safe_id(skill_id or path.stem)
    profile = _infer_skill_profile(text, discipline)
    primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
    root = Path(output_root).resolve() if output_root else path.parent / "plugin_candidates" / "skill_capabilities"
    source_root = root / _safe_id(source) / primary / resolved_skill_id
    source_root.mkdir(parents=True, exist_ok=True)
    privacy = _privacy_scan_text(text)
    support_routes = _support_routes_for_text(text)
    data_connectors = _extract_data_connector_manifests(text, source=source, skill_id=resolved_skill_id, profile=profile)
    method_templates = _extract_method_template_manifests(text, source=source, skill_id=resolved_skill_id, profile=profile)
    review_rules = _extract_review_rule_manifests(text, source=source, skill_id=resolved_skill_id, profile=profile, support_routes=support_routes)
    support_candidates = _extract_support_candidate_manifests(
        source=source,
        skill_id=resolved_skill_id,
        profile=profile,
        support_routes=support_routes,
        review_rules=review_rules,
    )
    support_candidate_ids = [str(item.get("candidate_id")) for item in support_candidates if item.get("candidate_id")]
    for manifest in review_rules:
        manifest["backflow_from_support_routes"] = support_routes
        manifest["support_candidate_ids"] = support_candidate_ids
    manifests = data_connectors + method_templates + review_rules
    for manifest in manifests:
        manifest.update(_runtime_metadata(manifest))
        manifest["capability_ir"] = _capability_ir_from_manifest(manifest)
    for manifest in support_candidates:
        manifest["capability_ir"] = _capability_ir_from_manifest(manifest)
    candidates = []
    for manifest in manifests:
        candidate_root = source_root / manifest["candidate_id"]
        candidate_root.mkdir(parents=True, exist_ok=True)
        _write_json(candidate_root / "candidate_manifest.json", manifest)
        if manifest.get("plugin_type") == "review_rule":
            (candidate_root / "rule_rationale.md").write_text(_review_rule_rationale(manifest), encoding="utf-8")
            _write_json(candidate_root / "positive_fixture.json", _review_rule_fixture(manifest, positive=True))
            _write_json(candidate_root / "negative_fixture.json", _review_rule_fixture(manifest, positive=False))
            _write_json(candidate_root / "provenance_summary.json", {
                "status": "written",
                "generated_at": utc_now(),
                "candidate_id": manifest.get("candidate_id"),
                "source": manifest.get("source"),
                "source_skill_id": manifest.get("source_skill_id"),
                "source_policy": manifest.get("source_policy"),
                "backflow_from_support_routes": manifest.get("backflow_from_support_routes") or [],
                "support_candidate_ids": manifest.get("support_candidate_ids") or [],
            })
        (candidate_root / "source_evidence_summary.md").write_text(_source_evidence_summary(text, [manifest]), encoding="utf-8")
        write_html_report(candidate_root / "candidate_summary.html", _render_candidate_summary(manifest), title="Skill Capability Candidate")
        candidate_record = {
            "candidate_id": manifest["candidate_id"],
            "plugin_type": manifest["plugin_type"],
            "path": str(candidate_root),
            "manifest": str(candidate_root / "candidate_manifest.json"),
            "capability_ir": manifest.get("capability_ir") or {},
        }
        for key in ["connector_id", "method_family", "rule_family"]:
            if manifest.get(key):
                candidate_record[key] = manifest.get(key)
        candidates.append(candidate_record)
    support_records = []
    support_root = source_root / "support_candidates"
    for manifest in support_candidates:
        route = str(manifest.get("support_type") or "shared_capability")
        candidate_root = support_root / route / str(manifest["candidate_id"])
        candidate_root.mkdir(parents=True, exist_ok=True)
        _write_json(candidate_root / "support_manifest.json", manifest)
        _write_json(candidate_root / "review_rule_backflow_links.json", _support_backflow_links_manifest(manifest))
        (candidate_root / "source_evidence_summary.md").write_text(_source_evidence_summary(text, []), encoding="utf-8")
        write_html_report(candidate_root / "support_candidate_summary.html", _render_support_candidate_summary(manifest), title="Skill Support Candidate")
        support_records.append({
            "candidate_id": manifest["candidate_id"],
            "candidate_kind": "support_candidate",
            "support_type": route,
            "path": str(candidate_root),
            "manifest": str(candidate_root / "support_manifest.json"),
            "intended_support_target": manifest.get("intended_support_target"),
            "review_rule_backflow_candidate_ids": manifest.get("review_rule_backflow_candidate_ids") or [],
            "review_rule_backflow_scope": manifest.get("review_rule_backflow_scope") or {},
            "capability_ir": manifest.get("capability_ir") or {},
        })
    capability_records = [
        item.get("capability_ir")
        for item in manifests + support_candidates
        if item.get("capability_ir")
    ]
    disposition = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_file": str(path),
        "disposition_path": str(source_root / "SKILL_DISPOSITION.json"),
        "skill_id": resolved_skill_id,
        "discipline_profile": profile,
        "support_routes": support_routes,
        "formal_plugin_types": ["data_connector", "method_template", "review_rule"],
        "plugin_type_counts": {
            "data_connector": len(data_connectors),
            "method_template": len(method_templates),
            "review_rule": len(review_rules),
        },
        "support_candidate_count": len(support_records),
        "support_candidates": support_records,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "privacy_scan": privacy,
        "promotion_policy": "candidate_only; promote-plugin-candidate with human confirmation is required for discipline_modules writes",
        "support_route_policy": {
            "workflow_recipe": "draftpaper_cli/pipeline_recipes/",
            "paper_contract": "draftpaper_cli/paper_contracts/",
            "shared_capability": "draftpaper_cli/shared_capabilities/",
            "review_rule_backflow": "discipline_modules/<discipline>/review_rules/ candidates only",
        },
    }
    _write_json(source_root / "SKILL_DISPOSITION.json", disposition)
    return disposition


def _iter_skill_source_files(source_root: Path, *, exclude_roots: list[Path] | None = None) -> list[Path]:
    allowed = {".md", ".txt"}
    excluded = [path.resolve() for path in (exclude_roots or [])]
    generated_names = {
        "source_evidence_summary.md",
        "discipline_gap_report.md",
        "github_contribution_guide.md",
    }
    generated_dirs = {"plugin_candidates", "generalized_template", "contribution_package"}
    files: list[Path] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if any(resolved == root or root in resolved.parents for root in excluded):
            continue
        if path.name.lower() in generated_names:
            continue
        if any(part.lower() in generated_dirs for part in path.parts):
            continue
        if path.name.lower() == "skill.md" or path.suffix.lower() in allowed:
            files.append(path)
    return files


def _skill_source_adapter_root(source_root: Path | None, output_root: str | Path | None = None) -> Path:
    if output_root:
        return Path(output_root).resolve()
    if source_root is not None:
        return source_root / "plugin_candidates" / "skill_source_adapter"
    return Path.cwd() / "plugin_candidates" / "skill_source_adapter"


def _skill_source_exclude_roots(source_root: Path, output_root: Path) -> list[Path]:
    resolved_source = source_root.resolve()
    resolved_output = output_root.resolve()
    if resolved_source == resolved_output or resolved_output in resolved_source.parents:
        return []
    return [resolved_output]


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _markdown_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def _requires_source_inspection(text: str) -> bool:
    return bool(re.search(r"(?im)^requires source inspection:\s*(true|yes|1)\s*$", text))


def _candidate_type_hints(text: str) -> dict[str, Any]:
    if _requires_source_inspection(text):
        return {
            "data_connector": {},
            "method_template": {},
            "review_rule": {},
            "review_rule_raw_signals": {},
            "review_rule_signal_scan": _review_rule_signal_scan(text, {}),
            "support_routes": [],
            "packages": [],
            "formal_plugin_types_present": [],
        }
    lowered = text.lower()
    data_connector_hints = {
        family: [term for term in config["terms"] if term in lowered]
        for family, config in DATA_CONNECTOR_KEYWORDS.items()
    }
    method_template_hints = {
        family: [term for term in config["terms"] if term in lowered]
        for family, config in METHOD_TEMPLATE_KEYWORDS.items()
    }
    review_rule_hints = {
        family: [term for term in config["terms"] if term in lowered]
        for family, config in REVIEW_RULE_KEYWORDS.items()
    }
    data_connector_hints = {key: value for key, value in data_connector_hints.items() if value}
    method_template_hints = {key: value for key, value in method_template_hints.items() if value}
    review_rule_hints = {key: value for key, value in review_rule_hints.items() if value}
    review_rule_signal_scan = _review_rule_signal_scan(text, review_rule_hints)
    eligible_review_rule_hints = {
        family: terms for family, terms in review_rule_hints.items()
        if family in review_rule_signal_scan["eligible_rule_families"]
    }
    support_routes = _support_routes_for_text(text)
    return {
        "data_connector": data_connector_hints,
        "method_template": method_template_hints,
        "review_rule": eligible_review_rule_hints,
        "review_rule_raw_signals": review_rule_hints,
        "review_rule_signal_scan": review_rule_signal_scan,
        "support_routes": support_routes,
        "packages": _package_names_from_text(text),
        "formal_plugin_types_present": [
            key for key, value in {
                "data_connector": data_connector_hints,
                "method_template": method_template_hints,
                "review_rule": review_rule_hints,
            }.items() if value
        ],
    }


def _source_record_from_file(path: Path, root: Path, *, include_hashes: bool) -> dict[str, Any]:
    stat = path.stat()
    text = _read_text(path, limit=30_000)
    record = {
        "relative_path": _relative_path(path, root),
        "name": path.name,
        "suffix": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified_time": stat.st_mtime,
        "is_skill_file": path.name.lower() == "skill.md",
        "document_kind": "skill" if path.name.lower() == "skill.md" else ("markdown" if path.suffix.lower() == ".md" else "text"),
        "title": _markdown_title(text, path.stem),
        "privacy_status": _privacy_scan_text(text)["status"],
    }
    if include_hashes:
        record["sha256"] = _sha256_file(path)
    return record


def _detect_license_files(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if lowered in {"license", "license.md", "license.txt", "copying", "notice", "notice.md", "notice.txt"}:
            text = _read_text(path, limit=12_000).lower()
            if "apache license" in text or "apache-2.0" in text:
                license_hint = "Apache-2.0"
            elif "mit license" in text:
                license_hint = "MIT"
            elif "creative commons" in text or "cc by" in text:
                license_hint = "Creative Commons"
            elif "gpl" in text or "gnu general public license" in text:
                license_hint = "GPL-family"
            else:
                license_hint = "unknown_or_custom"
            records.append({
                "relative_path": _relative_path(path, root),
                "license_hint": license_hint,
                "size_bytes": path.stat().st_size,
            })
    return records


def _license_audit_report(
    *,
    source: str,
    source_root: str | None,
    source_url: str | None,
    source_ref: str | None,
    license_records: list[dict[str, Any]],
) -> dict[str, Any]:
    status = "requires_review"
    if license_records and all(item.get("license_hint") not in {"unknown_or_custom", "GPL-family"} for item in license_records):
        status = "metadata_recorded"
    return {
        "status": status,
        "generated_at": utc_now(),
        "source": source,
        "source_root": source_root,
        "source_url": source_url,
        "source_ref": source_ref,
        "license_records": license_records,
        "promotion_policy": (
            "Unknown, custom, non-commercial, copyleft, or conflicting licenses must not be promoted into the core runtime "
            "without maintainer review. This command records provenance only and does not copy third-party source text."
        ),
    }


def _write_license_audit(out: Path, report: dict[str, Any]) -> None:
    _write_json(out / "LICENSE_AUDIT_REPORT.json", report)
    lines = [
        "# License Audit Report",
        "",
        f"Status: `{report.get('status')}`",
        f"Source: `{report.get('source')}`",
        f"Source URL: `{report.get('source_url') or 'not_recorded'}`",
        f"Source ref: `{report.get('source_ref') or 'not_recorded'}`",
        "",
        "## Detected License Files",
    ]
    records = report.get("license_records") or []
    if records:
        lines.extend(f"- `{item.get('relative_path')}`: `{item.get('license_hint')}`" for item in records)
    else:
        lines.append("- No license file was detected in the inspected local source tree. Treat this source as `requires_review` before promotion.")
    lines.extend(["", "## Promotion Policy", "", str(report.get("promotion_policy") or "")])
    (out / "LICENSE_AUDIT_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def _github_raw_file_url(repo_url: str, ref: str, path: str) -> str | None:
    parsed = urllib.parse.urlparse(repo_url)
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path.lstrip('/')}"


def _resolve_github_commit_sha(repo_url: str | None, ref: str) -> str | None:
    if not repo_url:
        return None
    parsed = urllib.parse.urlparse(repo_url)
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{urllib.parse.quote(ref, safe='')}"
    request = urllib.request.Request(url, headers={"User-Agent": "Draftpaper-loop metadata adapter"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - fixed GitHub API host.
            payload = json.loads(response.read().decode("utf-8-sig", errors="replace"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        payload = {}
    sha = str(payload.get("sha") or "") if isinstance(payload, dict) else ""
    if re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        return sha
    if shutil.which("gh"):
        try:
            completed = subprocess.run(
                ["gh", "api", f"repos/{owner}/{repo}/commits/{ref}", "--jq", ".sha"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        candidate = completed.stdout.strip()
        if completed.returncode == 0 and re.fullmatch(r"[0-9a-fA-F]{40}", candidate):
            return candidate
    return None


def _academicforge_registry_url(source_url: str | None, source_ref: str | None) -> str | None:
    if source_url and source_url.lower().endswith("skills.json"):
        return source_url
    ref = source_ref or "site-first"
    if source_url:
        raw = _github_raw_file_url(source_url, ref, "registry/skills.json")
        if raw:
            return raw
    return None


def _read_registry_json(url_or_path: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url_or_path)
    try:
        if parsed.scheme in {"http", "https", "file", "data"}:
            payload = fetch_text(
                url_or_path,
                user_agent="Draftpaper-loop metadata adapter",
                allowed_hosts={"raw.githubusercontent.com", "api.github.com"},
            )
        else:
            payload = Path(url_or_path).read_text(encoding="utf-8-sig")
    except (OSError, SafeFetchError) as exc:
        raise PluginCandidateError(f"Unable to read skill registry metadata: {url_or_path}: {exc}") from exc
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PluginCandidateError(f"Invalid skill registry JSON: {url_or_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PluginCandidateError(f"Skill registry JSON must be an object: {url_or_path}")
    return data


def _registry_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        preferred = value.get("en") or value.get("zh") or value.get("text")
        if preferred is not None:
            return _registry_text(preferred)
        return "; ".join(_registry_text(item) for item in value.values() if _registry_text(item))
    if isinstance(value, list):
        return ", ".join(_registry_text(item) for item in value if _registry_text(item))
    return str(value)


def _academicforge_registry_skills(data: dict[str, Any]) -> list[dict[str, Any]]:
    skills = data.get("skills") if isinstance(data, dict) else None
    if isinstance(skills, list):
        return [item for item in skills if isinstance(item, dict)]
    return []


ACADEMICFORGE_COLLECTION_PREFIXES = {
    "claude-science": "cs",
    "scientific-agent-skills": "sa",
    "AI-research-SKILLs": "air",
    "nature-skills": "ns",
}


def _academicforge_auxiliary_url(registry_url: str, relative_path: str) -> str | None:
    normalized = registry_url.replace("\\", "/")
    marker = "/registry/skills.json"
    if normalized.startswith(("http://", "https://")) and marker in normalized:
        return normalized.split(marker, 1)[0] + "/" + relative_path.lstrip("/")
    return None


def _academicforge_expanded_skills(
    collections: list[dict[str, Any]],
    *,
    registry_url: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Expand collection-level registry records without copying upstream skill bodies."""

    classification: dict[str, Any] = {}
    translations: dict[str, Any] = {}
    auxiliary_errors: list[str] = []
    for relative_path, target in [
        ("scripts/skill-classification.json", classification),
        ("scripts/skill-translations.zh.json", translations),
    ]:
        url = _academicforge_auxiliary_url(registry_url, relative_path)
        if not url:
            continue
        try:
            target.update(_read_registry_json(url))
        except PluginCandidateError as exc:
            auxiliary_errors.append(str(exc))

    collection_by_prefix = {
        prefix: item
        for item in collections
        for collection_id, prefix in ACADEMICFORGE_COLLECTION_PREFIXES.items()
        if str(item.get("id") or "") == collection_id
    }
    expanded: list[dict[str, Any]] = []
    detailed_counts: dict[str, int] = {}
    for qualified_id, detail in sorted(classification.items()):
        prefix, _, skill_name = str(qualified_id).partition(".")
        collection = collection_by_prefix.get(prefix)
        if not collection or not skill_name:
            continue
        collection_id = str(collection.get("id") or prefix)
        category = str((detail or {}).get("category") or "unclassified") if isinstance(detail, dict) else "unclassified"
        translated = translations.get(qualified_id)
        inherited_tags = [str(item) for item in collection.get("tags") or []]
        expanded.append({
            **collection,
            "id": qualified_id,
            "name": skill_name.replace("-", " ").replace("_", " ").title(),
            "summary": {
                "en": f"AcademicForge skill `{qualified_id}` classified as {category}.",
                "zh": translated if isinstance(translated, str) else "",
            },
            "skill_count": 1,
            "category": category,
            "tags": list(dict.fromkeys(inherited_tags + [category, skill_name])),
            "parent_collection_id": collection_id,
            "metadata_detail_status": "classified_skill",
        })
        detailed_counts[collection_id] = detailed_counts.get(collection_id, 0) + 1

    placeholder_count = 0
    for collection in collections:
        collection_id = str(collection.get("id") or "collection")
        declared = max(1, int(collection.get("skill_count") or 1))
        known = detailed_counts.get(collection_id, 0)
        if declared == 1 and known == 0:
            expanded.append({
                **collection,
                "skill_count": 1,
                "parent_collection_id": collection_id,
                "metadata_detail_status": "registry_skill",
                "requires_source_inspection": False,
            })
            continue
        for index in range(known + 1, declared + 1):
            placeholder_count += 1
            placeholder_id = collection_id if declared == 1 else f"{collection_id}.declared-skill-{index:03d}"
            expanded.append({
                **collection,
                "id": placeholder_id,
                "name": collection.get("name") if declared == 1 else f"{collection.get('name') or collection_id} declared skill {index}",
                "skill_count": 1,
                "parent_collection_id": collection_id,
                "metadata_detail_status": "collection_declared_placeholder",
                "requires_source_inspection": True,
            })

    declared_count = sum(max(1, int(item.get("skill_count") or 1)) for item in collections)
    return expanded or collections, {
        "collection_count": len(collections),
        "declared_skill_count": declared_count,
        "expanded_skill_count": len(expanded or collections),
        "detailed_skill_count": len(expanded) - placeholder_count if expanded else 0,
        "placeholder_skill_count": placeholder_count if expanded else len(collections),
        "silent_loss_count": max(0, declared_count - len(expanded or collections)),
        "classification_metadata_count": len(classification),
        "auxiliary_metadata_errors": auxiliary_errors,
    }


def _write_academicforge_metadata_profiles(
    *,
    out: Path,
    source_url: str | None,
    source_ref: str | None,
) -> tuple[Path, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    requested_ref = source_ref or "site-first"
    immutable_commit = _resolve_github_commit_sha(source_url, requested_ref)
    registry_url = _academicforge_registry_url(source_url, immutable_commit or requested_ref)
    if not registry_url:
        raise PluginCandidateError("AcademicForge snapshot requires --repo/--source-url pointing to a GitHub repo or registry/skills.json.")
    registry = _read_registry_json(registry_url)
    collections = _academicforge_registry_skills(registry)
    if not collections:
        raise PluginCandidateError(f"AcademicForge registry contained no skill records: {registry_url}")
    skills, expansion = _academicforge_expanded_skills(collections, registry_url=registry_url)
    derived_root = out / "derived_skill_metadata"
    if derived_root.exists():
        shutil.rmtree(derived_root)
    derived_root.mkdir(parents=True, exist_ok=True)
    registry_records: list[dict[str, Any]] = []
    license_records: list[dict[str, Any]] = []
    for index, item in enumerate(skills, start=1):
        skill_id = _safe_id(str(item.get("id") or item.get("name") or f"skill_{index}"))
        name = _registry_text(item.get("name")) or skill_id
        summary = _registry_text(item.get("summary"))
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        repository = _registry_text(item.get("repository") or item.get("repo"))
        license_name = _registry_text(item.get("license") or "unknown") or "unknown"
        category = _registry_text(item.get("category") or item.get("domain"))
        subdiscipline = _registry_text(item.get("subdiscipline") or item.get("discipline"))
        install = item.get("install") if isinstance(item.get("install"), dict) else {}
        install_text = _registry_text(install)
        profile_path = derived_root / f"{skill_id}.md"
        lines = [
            f"# {name}",
            "",
            "Metadata-only AcademicForge skill profile generated by Draftpaper-loop.",
            "This file is derived from registry metadata only and does not copy upstream SKILL.md bodies or source code.",
            "",
            f"Skill id: {item.get('id') or skill_id}",
            f"Metadata detail status: {item.get('metadata_detail_status') or 'registry_skill'}",
            f"Requires source inspection: {'true' if item.get('requires_source_inspection') else 'false'}",
            "Source registry: AcademicForge registry metadata snapshot",
            f"Source ref: {requested_ref}",
            f"Immutable commit: {immutable_commit or 'unresolved'}",
            f"Repository: {repository or 'not recorded'}",
            f"Author: {_registry_text(item.get('author')) or 'not recorded'}",
            f"License: {license_name}",
            f"Category: {category or 'unknown'}",
            f"Subdiscipline: {subdiscipline or 'unknown'}",
            f"Tags: {', '.join(str(tag) for tag in tags) or 'none'}",
            f"Skill count: {item.get('skill_count') or 'unknown'}",
            f"Install metadata: {install_text or 'not recorded'}",
            "",
            "Summary:",
            summary or "No summary provided in registry metadata.",
        ]
        profile_path.write_text("\n".join(lines), encoding="utf-8")
        registry_records.append({
            "skill_id": skill_id,
            "registry_id": item.get("id"),
            "name": name,
            "relative_path": profile_path.relative_to(derived_root).as_posix(),
            "repository": repository,
            "author": item.get("author"),
            "license": license_name,
            "category": category,
            "subdiscipline": subdiscipline,
            "tags": tags,
            "parent_collection_id": item.get("parent_collection_id") or item.get("id"),
            "metadata_detail_status": item.get("metadata_detail_status") or "registry_skill",
            "requires_source_inspection": bool(item.get("requires_source_inspection")),
            "metadata_profile": str(profile_path),
        })
        lowered_license = license_name.lower()
        if "mit" in lowered_license:
            license_hint = "MIT"
        elif "apache" in lowered_license:
            license_hint = "Apache-2.0"
        elif "bsd" in lowered_license:
            license_hint = "BSD-family"
        elif "cc by" in lowered_license or "creative commons" in lowered_license:
            license_hint = "Creative Commons"
        elif "gpl" in lowered_license:
            license_hint = "GPL-family"
        else:
            license_hint = "unknown_or_custom"
        license_records.append({
            "relative_path": profile_path.relative_to(derived_root).as_posix(),
            "license_hint": license_hint,
            "declared_license": license_name,
            "repository": repository,
            "author": item.get("author"),
            "registry_id": item.get("id"),
        })
    adapter_report = {
        "status": "written",
        "generated_at": utc_now(),
        "adapter": "academicforge",
        "registry_url": registry_url,
        "source_ref": requested_ref,
        "immutable_commit": immutable_commit,
        "immutable_ref_resolved": bool(immutable_commit),
        "metadata_only": True,
        "source_files_copied": False,
        "skill_count": len(registry_records),
        **expansion,
        "derived_source_root": str(derived_root),
        "records": registry_records,
        "policy": "Derived profiles contain registry and classification metadata only. Upstream SKILL.md bodies and source code are not copied. Collection-only declarations remain explicit placeholders until source inspection resolves them.",
    }
    _write_json(out / "ACADEMICFORGE_REGISTRY_ADAPTER.json", adapter_report)
    return derived_root, registry_records, license_records, adapter_report


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _write_simple_yaml(path: Path, data: dict[str, Any]) -> None:
    def emit(value: Any, indent: int = 0) -> list[str]:
        prefix = " " * indent
        if isinstance(value, dict):
            lines: list[str] = []
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}{key}:")
                    lines.extend(emit(item, indent + 2))
                else:
                    lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
            return lines
        if isinstance(value, list):
            lines = []
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}-")
                    lines.extend(emit(item, indent + 2))
                else:
                    lines.append(f"{prefix}- {_yaml_scalar(item)}")
            return lines
        return [f"{prefix}{_yaml_scalar(value)}"]

    path.write_text("\n".join(emit(data)) + "\n", encoding="utf-8")


def _write_skill_matrix(out: Path, capability_map: dict[str, Any]) -> None:
    rows = []
    for record in capability_map.get("records") or []:
        formal = record.get("formal_targets") or {}
        rows.append([
            str(record.get("relative_path") or ""),
            str(record.get("discipline") or ""),
            ", ".join(formal.get("data_connector") or []),
            ", ".join(formal.get("method_template") or []),
            ", ".join(formal.get("review_rule") or []),
            ", ".join(str(item) for item in (record.get("support_targets") or [])),
            "yes" if record.get("review_rule_backflow_possible") else "no",
        ])
    lines = [
        "# AcademicForge Skill Matrix",
        "",
        "This matrix is metadata-only. It maps source skills to Draftpaper-loop formal plugin candidates and support-layer targets without copying third-party source text.",
        "",
        "| Skill | Discipline | Data connectors | Method templates | Review rules | Support targets | Review-rule backflow |",
        "|---|---|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows)
    if not rows:
        lines.append("| none | none | none | none | none | none | no |")
    lines.extend([
        "",
        "Formal discipline modules accept only `data_connector`, `method_template`, and `review_rule`. Support-layer skills can produce review-rule backflow candidates but cannot be promoted directly into `discipline_modules/`.",
    ])
    (out / "ACADEMICFORGE_SKILL_MATRIX.md").write_text("\n".join(lines), encoding="utf-8")


def _write_discipline_gap_report(out: Path, capability_map: dict[str, Any]) -> None:
    lines = [
        "# Discipline Gap Report",
        "",
        "This report summarizes metadata-only capability coverage by discipline.",
        "",
        "| Discipline | Data connector sources | Method template sources | Review rule sources | Support sources | Packages |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for discipline, bucket in sorted((capability_map.get("discipline_map") or {}).items()):
        packages = ", ".join(sorted((bucket.get("packages") or {}).keys())) or "none"
        lines.append(
            f"| {discipline} | {bucket.get('data_connector_sources', 0)} | {bucket.get('method_template_sources', 0)} | "
            f"{bucket.get('review_rule_sources', 0)} | {bucket.get('support_sources', 0)} | {packages} |"
        )
    lines.extend([
        "",
        "Use this report to decide which validated candidates should be generalized, fixture-tested, and submitted as contribution packages.",
    ])
    (out / "DISCIPLINE_GAP_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def snapshot_skill_source(
    source_root: str | Path | None = None,
    *,
    source: str = "local_skill",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
    include_hashes: bool = True,
) -> dict[str, Any]:
    """Write a metadata-only snapshot of a skill source tree.

    The snapshot intentionally records file metadata and hashes only. It does
    not copy source files or third-party skill text into Draftpaper-loop.
    """

    root = Path(source_root).resolve() if source_root else None
    if root is not None and not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)
    adapter_report: dict[str, Any] | None = None
    registry_records: list[dict[str, Any]] = []
    registry_license_records: list[dict[str, Any]] = []
    if root is None and source.lower().replace("-", "_") == "academicforge":
        root, registry_records, registry_license_records, adapter_report = _write_academicforge_metadata_profiles(
            out=out,
            source_url=source_url,
            source_ref=source_ref,
        )
    files = _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out)) if root is not None else []
    records = [_source_record_from_file(path, root, include_hashes=include_hashes) for path in files] if root is not None else []
    if registry_records:
        by_relative = {str(item.get("relative_path") or ""): item for item in registry_records}
        for record in records:
            registry_record = by_relative.get(str(record.get("relative_path") or ""))
            if registry_record:
                record["registry_metadata"] = registry_record
    snapshot = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root) if root is not None else None,
        "source_url": source_url,
        "source_ref": source_ref,
        "metadata_only": True,
        "source_files_copied": False,
        "adapter_report": adapter_report,
        "file_count": len(records),
        "records": records,
        "policy": "metadata_snapshot_only; run inspect/index/classify/map before candidate extraction",
    }
    _write_json(out / "SNAPSHOT.json", snapshot)
    _write_license_audit(out, _license_audit_report(
        source=source,
        source_root=str(root) if root is not None else None,
        source_url=source_url,
        source_ref=source_ref,
        license_records=registry_license_records or (_detect_license_files(root) if root is not None else []),
    ))
    return snapshot


def inspect_skill_source(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Inspect skill docs without copying their source text."""

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)
    files = _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out))
    records: list[dict[str, Any]] = []
    aggregate_packages: dict[str, int] = {}
    aggregate_formal_types: dict[str, int] = {"data_connector": 0, "method_template": 0, "review_rule": 0}
    aggregate_support_routes: dict[str, int] = {key: 0 for key in SUPPORT_ROUTE_TARGETS}
    privacy_failures = 0
    for path in files:
        text = _read_text(path, limit=60_000)
        hints = _candidate_type_hints(text)
        privacy = _privacy_scan_text(text)
        if privacy["status"] != "passed":
            privacy_failures += 1
        for package in hints["packages"]:
            aggregate_packages[package] = aggregate_packages.get(package, 0) + 1
        for plugin_type in hints["formal_plugin_types_present"]:
            aggregate_formal_types[plugin_type] += 1
        for route in hints["support_routes"]:
            aggregate_support_routes[route] = aggregate_support_routes.get(route, 0) + 1
        records.append({
            "relative_path": _relative_path(path, root),
            "title": _markdown_title(text, path.stem),
            "privacy_status": privacy["status"],
            "formal_plugin_types_present": hints["formal_plugin_types_present"],
            "support_routes": hints["support_routes"],
            "packages": hints["packages"],
            "matched_data_connector_families": sorted(hints["data_connector"].keys()),
            "matched_method_template_families": sorted(hints["method_template"].keys()),
            "matched_review_rule_families": sorted(hints["review_rule"].keys()),
        })
    inspection = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root),
        "source_url": source_url,
        "source_ref": source_ref,
        "metadata_only": True,
        "file_count": len(records),
        "privacy_failure_count": privacy_failures,
        "package_counts": aggregate_packages,
        "formal_plugin_type_file_counts": aggregate_formal_types,
        "support_route_file_counts": aggregate_support_routes,
        "records": records,
        "policy": "inspection stores matched terms and route hints only; no source text is copied",
    }
    _write_json(out / "SKILL_SOURCE_INSPECTION.json", inspection)
    _write_json(out / "source_inspection.json", inspection)
    _write_license_audit(out, _license_audit_report(
        source=source,
        source_root=str(root),
        source_url=source_url,
        source_ref=source_ref,
        license_records=_detect_license_files(root),
    ))
    return inspection


def index_skill_source(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Build a metadata index for skill files before candidate extraction."""

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    discipline_counts: dict[str, int] = {}
    review_rule_backflow_candidates = 0
    capability_records: list[dict[str, Any]] = []
    for path in _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out)):
        text = _read_text(path, limit=60_000)
        profile = _infer_skill_profile(text, discipline)
        primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
        discipline_counts[primary] = discipline_counts.get(primary, 0) + 1
        hints = _candidate_type_hints(text)
        relative = _relative_path(path, root)
        skill_id = _safe_id(str(Path(relative).with_suffix("")))
        skill_capability_records = _capability_ir_records_from_hints(
            source=source,
            skill_id=skill_id,
            profile=profile,
            hints=hints,
        )
        capability_records.extend(skill_capability_records)
        review_rule_backflow_candidates += len(hints["review_rule"])
        records.append({
            "skill_id": skill_id,
            "relative_path": relative,
            "title": _markdown_title(text, path.stem),
            "discipline_profile": profile,
            "formal_plugin_types_present": hints["formal_plugin_types_present"],
            "support_routes": hints["support_routes"],
            "packages": hints["packages"],
            "review_rule_backflow_family_count": len(hints["review_rule"]),
            "capability_record_count": len(skill_capability_records),
            "capability_ir_records": skill_capability_records,
            "candidate_generation_command": (
                "python -m draftpaper_cli.cli extract-skill-capabilities "
                f"--source-file {path} --source {source} --skill-id {skill_id} --discipline {primary}"
            ),
        })
    index = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root),
        "source_url": source_url,
        "source_ref": source_ref,
        "discipline": discipline,
        "metadata_only": True,
        "skill_count": len(records),
        "discipline_counts": discipline_counts,
        "review_rule_backflow_family_count": review_rule_backflow_candidates,
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "skills": records,
        "policy": "index only; formal candidates are produced by extract-skill-capabilities or compile-skill-source",
    }
    _write_json(out / "SKILL_SOURCE_INDEX.json", index)
    _write_json(out / "SKILL_INDEX.json", index)
    return index


def classify_skill_source(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Classify skill files into formal-candidate, support, external-only, or reject routes."""

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    disposition_counts: dict[str, int] = {}
    capability_records: list[dict[str, Any]] = []
    for path in _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out)):
        text = _read_text(path, limit=60_000)
        hints = _candidate_type_hints(text)
        profile = _infer_skill_profile(text, discipline)
        relative = _relative_path(path, root)
        skill_id = _safe_id(str(Path(relative).with_suffix("")))
        skill_capability_records = _capability_ir_records_from_hints(
            source=source,
            skill_id=skill_id,
            profile=profile,
            hints=hints,
        )
        capability_records.extend(skill_capability_records)
        privacy = _privacy_scan_text(text)
        if _requires_source_inspection(text):
            disposition = "unresolved_metadata"
        elif privacy["status"] != "passed":
            disposition = "requires_privacy_review"
        elif hints["formal_plugin_types_present"]:
            disposition = "formal_candidate_source"
        elif hints["support_routes"]:
            disposition = "support_candidate_source"
        elif _package_names_from_text(text):
            disposition = "external_only"
        else:
            disposition = "non_research_reject"
        disposition_counts[disposition] = disposition_counts.get(disposition, 0) + 1
        records.append({
            "skill_id": skill_id,
            "relative_path": relative,
            "title": _markdown_title(text, path.stem),
            "disposition": disposition,
            "discipline_profile": profile,
            "formal_plugin_types_present": hints["formal_plugin_types_present"],
            "support_routes": hints["support_routes"],
            "review_rule_backflow_families": sorted(hints["review_rule"].keys()),
            "capability_record_count": len(skill_capability_records),
            "capability_ir_records": skill_capability_records,
            "promotion_allowed": False,
            "next_step": "compile-skill-source" if disposition in {"formal_candidate_source", "support_candidate_source"} else "manual_review",
        })
    classification = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root),
        "source_url": source_url,
        "source_ref": source_ref,
        "metadata_only": True,
        "disposition_counts": disposition_counts,
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "records": records,
        "policy": "classification is advisory; candidate validation and human confirmation are required before promotion",
    }
    _write_json(out / "SKILL_SOURCE_CLASSIFICATION.json", classification)
    _write_json(out / "SKILL_DISPOSITION.json", classification)
    return classification


def map_skill_capabilities(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Map source skills to discipline plugin and support-layer targets."""

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)
    discipline_map: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    capability_records: list[dict[str, Any]] = []
    for path in _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out)):
        text = _read_text(path, limit=60_000)
        hints = _candidate_type_hints(text)
        profile = _infer_skill_profile(text, discipline)
        primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
        relative = _relative_path(path, root)
        skill_id = _safe_id(str(Path(relative).with_suffix("")))
        skill_capability_records = _capability_ir_records_from_hints(
            source=source,
            skill_id=skill_id,
            profile=profile,
            hints=hints,
        )
        capability_records.extend(skill_capability_records)
        bucket = discipline_map.setdefault(primary, {
            "data_connector_sources": 0,
            "method_template_sources": 0,
            "review_rule_sources": 0,
            "support_sources": 0,
            "capability_records": 0,
            "capability_kinds": {},
            "support_routes": {},
            "packages": {},
        })
        bucket["capability_records"] += len(skill_capability_records)
        for capability in skill_capability_records:
            kind = str(capability.get("formal_plugin_type") or capability.get("support_type") or "unknown")
            bucket["capability_kinds"][kind] = bucket["capability_kinds"].get(kind, 0) + 1
        if hints["data_connector"]:
            bucket["data_connector_sources"] += 1
        if hints["method_template"]:
            bucket["method_template_sources"] += 1
        if hints["review_rule"]:
            bucket["review_rule_sources"] += 1
        if hints["support_routes"]:
            bucket["support_sources"] += 1
        for route in hints["support_routes"]:
            bucket["support_routes"][route] = bucket["support_routes"].get(route, 0) + 1
        for package in hints["packages"]:
            bucket["packages"][package] = bucket["packages"].get(package, 0) + 1
        records.append({
            "skill_id": skill_id,
            "relative_path": relative,
            "discipline": primary,
            "formal_targets": {
                "data_connector": sorted(hints["data_connector"].keys()),
                "method_template": sorted(hints["method_template"].keys()),
                "review_rule": sorted(hints["review_rule"].keys()),
            },
            "support_targets": [SUPPORT_ROUTE_TARGETS.get(route, {}).get("target", route) for route in hints["support_routes"]],
            "review_rule_backflow_possible": bool(hints["review_rule"]),
            "capability_record_count": len(skill_capability_records),
            "capability_ir_records": skill_capability_records,
            "packages": hints["packages"],
        })
    capability_map = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root),
        "source_url": source_url,
        "source_ref": source_ref,
        "metadata_only": True,
        "discipline_map": discipline_map,
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "records": records,
        "deployment_policy": {
            "formal_discipline_plugin_types": ["data_connector", "method_template", "review_rule"],
            "support_layer_targets": SUPPORT_ROUTE_TARGETS,
            "promotion_allowed_by_this_command": False,
            "review_rule_backflow_policy": "support skills may create review_rule candidates, but only validated formal candidates can be promoted",
        },
    }
    _write_json(out / "SKILL_CAPABILITY_MAP.json", capability_map)
    _write_json(out / "SKILL_MAPPING.json", capability_map)
    _write_simple_yaml(out / "SKILL_MAPPING.yaml", capability_map)
    _write_skill_matrix(out, capability_map)
    _write_discipline_gap_report(out, capability_map)
    return capability_map


def extract_review_rule_signals(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Write a standalone review-rule signal report for a skill/source tree.

    This is the stable intermediate API between support-layer skills and
    formal discipline review-rule candidates. It scans every source file,
    regardless of whether that file is later classified as data, method,
    workflow, paper-contract, or shared-capability material.
    """

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    capability_records: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    recommendation_counts: dict[str, int] = {}
    support_backflow_count = 0

    for path in _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out)):
        text = _read_text(path, limit=60_000)
        hints = _candidate_type_hints(text)
        profile = _infer_skill_profile(text, discipline)
        primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
        relative = _relative_path(path, root)
        skill_id = _safe_id(str(Path(relative).with_suffix("")))
        scan = hints.get("review_rule_signal_scan") or {}
        families = scan.get("families") or {}
        eligible_families = list(scan.get("eligible_rule_families") or [])
        for family, family_scan in families.items():
            family_counts[family] = family_counts.get(family, 0) + 1
            recommendation = str(family_scan.get("recommendation") or "unknown")
            recommendation_counts[recommendation] = recommendation_counts.get(recommendation, 0) + 1
        skill_capability_records = _capability_ir_records_from_hints(
            source=source,
            skill_id=skill_id,
            profile=profile,
            hints=hints,
        )
        capability_records.extend(skill_capability_records)
        support_routes = list(hints.get("support_routes") or [])
        if support_routes and eligible_families:
            support_backflow_count += 1
        records.append({
            "skill_id": skill_id,
            "relative_path": relative,
            "title": _markdown_title(text, path.stem),
            "primary_discipline": primary,
            "secondary_disciplines": list(profile.get("secondary_disciplines") or []),
            "formal_plugin_types_present": list(hints.get("formal_plugin_types_present") or []),
            "support_routes": support_routes,
            "review_rule_backflow_families": eligible_families,
            "review_rule_signal_scan": scan,
            "capability_ir_records": skill_capability_records,
            "candidate_generation_command": (
                "python -m draftpaper_cli.cli extract-skill-capabilities "
                f"--source-file {path} --source {source} --skill-id {skill_id} --discipline {primary}"
            ),
        })

    report = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root),
        "source_url": source_url,
        "source_ref": source_ref,
        "discipline": discipline,
        "metadata_only": True,
        "file_count": len(records),
        "review_rule_family_counts": family_counts,
        "recommendation_counts": recommendation_counts,
        "support_backflow_source_count": support_backflow_count,
        "formal_candidate_signal_count": sum(
            1
            for record in capability_records
            if record.get("formal_plugin_type") == "review_rule"
        ),
        "support_layer_signal_count": sum(
            1
            for record in capability_records
            if record.get("capability_kind") == "support_layer_candidate"
        ),
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "records": records,
        "formal_plugin_types": FORMAL_DISCIPLINE_PLUGIN_TYPES,
        "support_layer_targets": SUPPORT_ROUTE_TARGETS,
        "review_rule_backflow_policy": {
            "formal_promotion_targets": FORMAL_DISCIPLINE_PLUGIN_TYPES,
            "support_layer_types": SUPPORT_LAYER_TYPES,
            "support_candidates_promotion_allowed": False,
            "rule": "Support-layer skills may backflow evidence-bound review_rule candidates, but they are not promoted directly into discipline_modules.",
        },
        "policy": (
            "All skill/source files are scanned for evidence-bound scientific quality signals. "
            "Support-layer records may backflow only as validated data_connector, method_template, or review_rule candidates; "
            "thresholds remain contextual unless backed by guideline, benchmark, discipline convention, or human confirmation."
        ),
    }
    _write_json(out / "REVIEW_RULE_SIGNAL_REPORT.json", report)
    _write_json(out / "review_rule_signal_report.json", report)
    lines = [
        "# Review Rule Signal Report",
        "",
        f"Source: `{source}`",
        f"Files scanned: {len(records)}",
        f"Support-layer sources with backflow signals: {support_backflow_count}",
        "",
        "## Rule Family Counts",
        *[f"- `{family}`: {count}" for family, count in sorted(family_counts.items())],
        "",
        "## Recommendation Counts",
        *[f"- `{name}`: {count}" for name, count in sorted(recommendation_counts.items())],
        "",
        "## Policy",
        "",
        str(report["policy"]),
    ]
    (out / "REVIEW_RULE_SIGNAL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def compile_skill_source(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
    stop_after: str = "candidate",
    jobs: int = 1,
    resume: bool = False,
) -> dict[str, Any]:
    """Batch-convert a skill/source tree into candidate-only plugin reports.

    The first implementation is intentionally sequential. The ``jobs`` value is
    recorded for future runners but does not enable concurrent writes yet.
    """

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    if stop_after != "candidate":
        raise PluginCandidateError("compile-skill-source currently supports --stop-after candidate only.")
    out = Path(output_root).resolve() if output_root else root / "plugin_candidates" / "compiled_skill_source"
    source_files = _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out))
    out.mkdir(parents=True, exist_ok=True)
    records = []
    type_counts: dict[str, int] = {"data_connector": 0, "method_template": 0, "review_rule": 0}
    support_type_counts: dict[str, int] = {"workflow_recipe": 0, "paper_contract": 0, "shared_capability": 0}
    discipline_counts: dict[str, int] = {}
    discipline_review_rule_counts: dict[str, int] = {}
    support_backflow_records: list[dict[str, Any]] = []
    capability_records: list[dict[str, Any]] = []
    candidate_records: list[dict[str, Any]] = []
    support_candidate_records: list[dict[str, Any]] = []
    unresolved_source_count = 0
    for file_path in source_files:
        relative = file_path.relative_to(root)
        skill_id = _safe_id(str(relative.with_suffix("")))
        source_text = _read_text(file_path, limit=60_000)
        if _requires_source_inspection(source_text):
            unresolved_source_count += 1
            records.append({
                "source_file": str(file_path),
                "relative_path": str(relative),
                "skill_id": skill_id,
                "candidate_count": 0,
                "plugin_type_counts": {},
                "support_candidate_count": 0,
                "support_candidates": [],
                "support_routes": [],
                "capability_record_count": 0,
                "disposition": "unresolved_metadata",
                "requires_source_inspection": True,
            })
            continue
        disposition = extract_skill_capabilities(
            file_path,
            source=source,
            skill_id=skill_id,
            discipline=discipline,
            output_root=out,
        )
        for candidate in disposition.get("candidates") or []:
            plugin_type = str(candidate.get("plugin_type") or "unknown")
            type_counts[plugin_type] = type_counts.get(plugin_type, 0) + 1
            candidate_records.append({
                **candidate,
                "source_file": str(file_path),
                "relative_path": str(relative),
                "skill_id": disposition.get("skill_id") or skill_id,
            })
        primary = str((disposition.get("discipline_profile") or {}).get("primary_discipline") or "default")
        discipline_counts[primary] = discipline_counts.get(primary, 0) + int(disposition.get("candidate_count") or 0)
        discipline_review_rule_counts[primary] = discipline_review_rule_counts.get(primary, 0) + int((disposition.get("plugin_type_counts") or {}).get("review_rule") or 0)
        capability_records.extend([item for item in disposition.get("capability_records") or [] if isinstance(item, dict)])
        support_candidates = disposition.get("support_candidates") or []
        for support_candidate in support_candidates:
            support_type = str(support_candidate.get("support_type") or "shared_capability")
            support_type_counts[support_type] = support_type_counts.get(support_type, 0) + 1
            support_candidate_records.append({
                **support_candidate,
                "source_file": str(file_path),
                "relative_path": str(relative),
                "skill_id": disposition.get("skill_id") or skill_id,
            })
            support_backflow_records.append({
                "source_file": str(file_path),
                "relative_path": str(relative),
                "skill_id": disposition.get("skill_id") or skill_id,
                "discipline": primary,
                "support_type": support_type,
                "support_candidate_id": support_candidate.get("candidate_id"),
                "support_candidate_path": support_candidate.get("path"),
                "intended_support_target": support_candidate.get("intended_support_target"),
                "review_rule_backflow_candidate_ids": support_candidate.get("review_rule_backflow_candidate_ids") or [],
                "review_rule_backflow_scope": support_candidate.get("review_rule_backflow_scope") or {},
                "capability_ir": support_candidate.get("capability_ir") or {},
            })
        records.append({
            "source_file": str(file_path),
            "relative_path": str(relative),
            "skill_id": disposition.get("skill_id") or skill_id,
            "candidate_count": disposition.get("candidate_count") or 0,
            "plugin_type_counts": disposition.get("plugin_type_counts") or {},
            "support_candidate_count": disposition.get("support_candidate_count") or 0,
            "support_candidates": disposition.get("support_candidates") or [],
            "support_routes": disposition.get("support_routes") or [],
            "capability_record_count": disposition.get("capability_record_count") or 0,
            "disposition": disposition.get("disposition_path"),
        })
    support_candidate_count = sum(int(item.get("support_candidate_count") or 0) for item in records)
    review_rule_backflow_count = sum(len(item.get("review_rule_backflow_candidate_ids") or []) for item in support_backflow_records)
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "source_root": str(root),
        "source": source,
        "discipline": discipline,
        "stop_after": stop_after,
        "jobs_requested": jobs,
        "resume": resume,
        "source_file_count": len(records),
        "unresolved_source_count": unresolved_source_count,
        "candidate_count": sum(int(item["candidate_count"] or 0) for item in records),
        "candidates": candidate_records,
        "plugin_type_counts": type_counts,
        "support_candidate_count": support_candidate_count,
        "support_candidates": support_candidate_records,
        "support_type_counts": support_type_counts,
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "review_rule_backflow_count": review_rule_backflow_count,
        "support_backflow_records": support_backflow_records,
        "discipline_candidate_counts": discipline_counts,
        "discipline_review_rule_counts": discipline_review_rule_counts,
        "records": records,
        "policy": "candidate_only; no formal discipline module writes are performed by this command",
    }
    index = {
        "status": "written",
        "source_root": str(root),
        "skills": records,
    }
    gap_lines = [
        "# Discipline Gap Report",
        "",
        "This report summarizes candidate-only coverage from the inspected skill source tree.",
        "",
        "## Plugin Type Counts",
        *[f"- {key}: {value}" for key, value in sorted(type_counts.items())],
        "",
        "## Support Candidate Counts",
        *[f"- {key}: {value}" for key, value in sorted(support_type_counts.items())],
        "",
        f"Review rule backflow links: {review_rule_backflow_count}",
        "",
        "## Discipline Candidate Counts",
        *[f"- {key}: {value}" for key, value in sorted(discipline_counts.items())],
        "",
        "## Discipline Review Rule Backflow",
        *[f"- {key}: {value}" for key, value in sorted(discipline_review_rule_counts.items())],
        "",
        "## Support Candidates With Review Rule Backflow",
        *[
            f"- {item['relative_path']} -> {item['support_type']} -> {len(item['review_rule_backflow_candidate_ids'])} review_rule candidates"
            for item in support_backflow_records
        ],
        "",
        "Support candidates stay outside `discipline_modules/`; only their validated `data_connector`, `method_template`, or `review_rule` backflow candidates can be promoted with explicit human confirmation.",
    ]
    _write_json(out / "COMPILE_SKILL_SOURCE_REPORT.json", report)
    _write_json(out / "SKILL_INDEX.json", index)
    (out / "DISCIPLINE_GAP_REPORT.md").write_text("\n".join(gap_lines), encoding="utf-8")
    return report


def _method_template_candidates(module: Any, requested: str | None = None) -> list[dict[str, Any]]:
    templates = module.spec.method_template_dicts()
    if requested:
        wanted = requested.lower()
        templates = [
            item for item in templates
            if wanted in item.get("template_id", "").lower()
            or wanted in item.get("method_family", "").lower()
            or any(wanted in str(alias).lower() for alias in item.get("aliases") or [])
        ]
    return templates


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


def _genericity_report(text: str, manifest: dict[str, Any]) -> dict[str, Any]:
    project_specific_terms = []
    for term in ["beijing", "北京市", "3-6", "march", "june", "d:\\", "c:\\"]:
        if term in text.lower():
            project_specific_terms.append(term)
    placeholders = ["{{input_table}}", "{{target_column}}", "{{predictor_columns}}", "{{output_dir}}"]
    return {
        "status": "passed" if not project_specific_terms else "needs_generalization",
        "project_specific_terms": project_specific_terms,
        "recommended_placeholders": placeholders,
        "template_id": manifest.get("template_id") or manifest.get("plugin_id"),
    }


def summarize_plugin_candidates(project: str | Path, *, source_file: str | Path | None = None, method: str | None = None) -> dict[str, Any]:
    state = load_project(project)
    profile = infer_discipline_profile(state.path)
    module = get_discipline_module(profile)
    templates = _method_template_candidates(module, method)
    if not templates:
        templates = module.spec.method_template_dicts()[:1]
    source_text = _read_text(Path(source_file)) if source_file else _read_text(state.path / "methods" / "src" / "generated_pipeline.py")
    if not source_text:
        source_text = _read_text(state.path / "methods" / "scripts" / "run_analysis.py")
    candidates = []
    for template in templates:
        candidate_id = _safe_id(f"{profile['discipline']}_{template.get('template_id')}")
        root = _candidate_root(state.path, profile["discipline"], candidate_id)
        root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "status": "candidate_summarized",
            "candidate_id": candidate_id,
            "generated_at": utc_now(),
            "project_id": state.metadata.get("project_id"),
            "discipline": profile["discipline"],
            "primary_discipline": profile.get("primary_discipline") or profile["discipline"],
            "secondary_disciplines": profile.get("secondary_disciplines") or [],
            "discipline_modules": profile.get("discipline_modules") or [profile["discipline"]],
            "plugin_type": "method_template",
            "plugin_id": f"{profile['discipline']}.method.{template.get('template_id')}",
            "template_id": template.get("template_id"),
            "method_family": template.get("method_family"),
            "aliases": template.get("aliases") or [],
            "input_roles": template.get("input_roles") or [],
            "output_artifacts": template.get("output_artifacts") or [],
            "figure_groups": template.get("figure_groups") or [],
            "source_file": "local_project_source_not_packaged",
            "source_policy": "candidate_only_no_direct_upload",
            "intended_merge_target": f"draftpaper_cli/discipline_modules/{profile['discipline']}/method_templates/{template.get('template_id')}",
            **_runtime_metadata(dict(template)),
        }
        _write_json(root / "candidate_manifest.json", manifest)
        (root / "source_excerpt.py").write_text(source_text[:20_000], encoding="utf-8")
        write_html_report(root / "candidate_summary.html", _render_candidate_summary(manifest), title="Plugin Candidate Summary")
        candidates.append({"candidate_id": candidate_id, "path": str(root), "manifest": str(root / "candidate_manifest.json")})
    return {
        "status": "written",
        "project_path": str(state.path),
        "discipline": profile["discipline"],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "next_command": f'python -m draftpaper_cli.cli generalize-plugin-candidate --candidate "{candidates[0]["path"]}"' if candidates else "",
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


def generalize_plugin_candidate(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    if (root / "support_manifest.json").exists():
        raise PluginCandidateError("Support candidates cannot be generalized as formal discipline plugins; extract their review_rule backflow candidates instead.")
    manifest = _read_json(root / "candidate_manifest.json", {})
    if not manifest:
        raise PluginCandidateError(f"Missing candidate manifest: {root}")
    source = _read_text(root / "source_excerpt.py") or _read_text(root / "source_excerpt.md") or _read_text(root / "source_evidence_summary.md")
    generalized_dir = root / "generalized_template"
    generalized_dir.mkdir(parents=True, exist_ok=True)
    plugin_type = str(manifest.get("plugin_type") or "method_template")
    if plugin_type == "data_connector":
        data_connector = {
            "connector_id": manifest.get("connector_id"),
            "display_name": manifest.get("display_name"),
            "access_modes": manifest.get("access_modes") or [],
            "packages": manifest.get("packages") or [],
            "package_modules": manifest.get("package_modules") or [],
            "download_or_access": manifest.get("download_or_access") or [],
            "data_formats": manifest.get("data_formats") or [],
            "requires_credentials": bool(manifest.get("requires_credentials")),
            "credential_env_vars": manifest.get("credential_env_vars") or [],
            "template_paths": manifest.get("template_paths") or [],
            "fixture_paths": manifest.get("fixture_paths") or [],
            "genericity_rules": manifest.get("genericity_rules") or [],
            "source_skill_refs": manifest.get("source_skill_refs") or [f"{manifest.get('source')}:{manifest.get('source_skill_id')}"],
            "provenance_notes": manifest.get("provenance_notes") or "Candidate data connector generalized from skill/source text.",
            **_runtime_metadata(manifest),
        }
        _write_json(generalized_dir / "data_connector.json", data_connector)
        template = "\n".join([
            "# Copyright (c) 2026 Jinray Xie",
            "# Contact: xiejinhui22@mails.ucas.ac.cn",
            "# Source-available for non-commercial use only; commercial use requires written authorization.",
            "",
            "from __future__ import annotations",
            "",
            "from pathlib import Path",
            "from typing import Any",
            "",
            "",
            "def prepare_data_connector(*, output_dir: Path, parameters: dict[str, Any] | None = None) -> dict[str, Any]:",
            "    \"\"\"Prepare a reusable data connector without embedding private project inputs.\"\"\"",
            "    output_dir.mkdir(parents=True, exist_ok=True)",
            "    params = dict(parameters or {})",
            "    return {",
            f"        'connector_id': {data_connector['connector_id']!r},",
            "        'status': 'template_ready_for_project_binding',",
            "        'output_dir': str(output_dir),",
            "        'parameter_keys': sorted(str(key) for key in params.keys()),",
            "    }",
            "",
            "SOURCE_DERIVATION_METADATA = {",
            f"    'source': {manifest.get('source')!r},",
            f"    'source_skill_id': {manifest.get('source_skill_id')!r},",
            f"    'matched_terms': {list(manifest.get('matched_terms') or [])!r},",
            "    'source_text_copied': False,",
            "}",
        ])
        (generalized_dir / "template.py").write_text(template, encoding="utf-8")
        report = {
            "status": "written",
            "generated_at": utc_now(),
            "candidate_id": manifest.get("candidate_id"),
            "plugin_type": "data_connector",
            "template_path": str(generalized_dir / "template.py"),
            "data_connector_path": str(generalized_dir / "data_connector.json"),
            "rules": [
                "Parameterize dataset ids, dates, regions, cohorts, credentials, and output paths.",
                "Do not promote connectors until a public or synthetic fixture validates access-shape assumptions.",
            ],
        }
        _write_json(root / "genericity_report.json", _genericity_report(json.dumps(data_connector, ensure_ascii=False), manifest))
        _write_json(root / "generalization_report.json", report)
        return report
    if plugin_type == "review_rule":
        review_rule = {
            "rule_id": manifest.get("rule_id") or manifest.get("rule_group_id"),
            "rule_group_id": manifest.get("rule_group_id") or manifest.get("rule_id"),
            "display_name": manifest.get("display_name"),
            "rule_family": manifest.get("rule_family"),
            "criterion_type": manifest.get("criterion_type") or _criterion_type_for_rule_family(str(manifest.get("rule_family") or "")),
            "applicable_disciplines": manifest.get("applicable_disciplines") or [manifest.get("discipline")],
            "applicable_methods": manifest.get("applicable_methods") or [],
            "applicable_data_roles": manifest.get("applicable_data_roles") or [],
            "evidence_roles": manifest.get("evidence_roles") or [],
            "evidence_binding": manifest.get("evidence_binding") or _review_rule_evidence_binding(
                str(manifest.get("rule_family") or "discipline_review"),
                list(manifest.get("evidence_roles") or []),
            ),
            "checks": manifest.get("checks") or [],
            "metric_family": manifest.get("metric_family"),
            "unit_or_scale": manifest.get("unit_or_scale"),
            "threshold_policy": manifest.get("threshold_policy") or {"mode": "contextual"},
            "threshold_source": manifest.get("threshold_source") or {"type": "source_skill_statement"},
            "threshold_mode": manifest.get("threshold_mode") or (manifest.get("threshold_policy") or {}).get("mode") or "contextual",
            "threshold_validation_status": manifest.get("threshold_validation_status") or _threshold_validation_status(
                manifest.get("threshold_policy") or {"mode": "contextual"},
                manifest.get("threshold_source") or {"type": "source_skill_statement"},
            ),
            "minimum_sample_policy": manifest.get("minimum_sample_policy"),
            "model_family": manifest.get("model_family"),
            "blocking_level": manifest.get("blocking_level") or "warn_and_repair",
            "failure_route": manifest.get("failure_route") or "human_checkpoint",
            "pipeline_hooks": manifest.get("pipeline_hooks") or {},
            "maturity": manifest.get("maturity") or "candidate",
            "deployment_state": manifest.get("deployment_state") or "review_rule_candidate",
            "human_confirmation_required": bool(manifest.get("human_confirmation_required", True)),
            "review_question": manifest.get("review_question") or "Does the available evidence satisfy this discipline-aware review condition?",
            "scientific_risk": manifest.get("scientific_risk") or "The manuscript may make a claim that is not supported by the available evidence.",
            "minimum_evidence_required": manifest.get("minimum_evidence_required") or manifest.get("evidence_roles") or [],
            "sample_unit_policy": manifest.get("sample_unit_policy"),
            "metric_dimension_policy": manifest.get("metric_dimension_policy"),
            "allowed_claim_strength": manifest.get("allowed_claim_strength") or "exploratory",
            "repair_priority": manifest.get("repair_priority") or [manifest.get("failure_route") or "human_checkpoint"],
            "manual_review_triggers": manifest.get("manual_review_triggers") or [],
            "non_goals": manifest.get("non_goals") or [],
            "fixture_paths": manifest.get("fixture_paths") or [],
            "positive_fixture_refs": manifest.get("positive_fixture_refs") or [path for path in manifest.get("fixture_paths") or [] if "positive" in str(path).lower()],
            "negative_fixture_refs": manifest.get("negative_fixture_refs") or [path for path in manifest.get("fixture_paths") or [] if "negative" in str(path).lower()],
            "source_skill_refs": manifest.get("source_skill_refs") or [],
            "backflow_source_type": manifest.get("backflow_source_type") or "explicit_review",
            "support_layer_signal_refs": manifest.get("support_layer_signal_refs") or [],
            "aliases": manifest.get("aliases") or [],
            "variants": manifest.get("variants") or [],
            "provenance_notes": manifest.get("provenance_notes") or "Candidate review rule generalized from skill/source text.",
            **_runtime_metadata(manifest),
        }
        _write_json(generalized_dir / "review_rule.json", review_rule)
        template = "\n".join([
            "# Copyright (c) 2026 Jinray Xie",
            "# Contact: xiejinhui22@mails.ucas.ac.cn",
            "# Source-available for non-commercial use only; commercial use requires written authorization.",
            "",
            "from __future__ import annotations",
            "",
            "",
            "def evaluate_rule(evidence: dict[str, object]) -> dict[str, object]:",
            "    \"\"\"Evaluate a generalized review rule against evidence roles.",
            "",
            "    Replace this scaffold with a discipline fixture-tested implementation before promotion.",
            "    \"\"\"",
            "    return {",
            f"        'rule_id': {review_rule['rule_id']!r},",
            "        'status': 'requires_fixture_implementation',",
            "        'evidence_keys': sorted(str(key) for key in evidence.keys()),",
            "    }",
            "",
            "SOURCE_DERIVATION_METADATA = {",
            f"    'source': {manifest.get('source')!r},",
            f"    'source_skill_id': {manifest.get('source_skill_id')!r},",
            f"    'matched_terms': {list(manifest.get('matched_terms') or [])!r},",
            "    'source_text_copied': False,",
            "}",
        ])
        (generalized_dir / "template.py").write_text(template, encoding="utf-8")
        report = {
            "status": "written",
            "generated_at": utc_now(),
            "candidate_id": manifest.get("candidate_id"),
            "plugin_type": "review_rule",
            "template_path": str(generalized_dir / "template.py"),
            "review_rule_path": str(generalized_dir / "review_rule.json"),
            "rules": [
                "Review rules must declare discipline, evidence roles, threshold policy, threshold source, and failure route.",
                "Do not promote fixed thresholds unless a discipline convention, journal guideline, or benchmark source is documented.",
            ],
        }
        _write_json(root / "genericity_report.json", _genericity_report(json.dumps(review_rule, ensure_ascii=False), manifest))
        _write_json(root / "generalization_report.json", report)
        return report
    method_template = {
        "template_id": manifest.get("template_id"),
        "display_name": manifest.get("display_name"),
        "discipline": manifest.get("discipline"),
        "method_family": manifest.get("method_family"),
        "input_roles": manifest.get("input_roles") or [],
        "optional_roles": manifest.get("optional_roles") or [],
        "packages": manifest.get("packages") or [],
        "package_modules": manifest.get("package_modules") or [],
        "output_artifacts": manifest.get("output_artifacts") or [],
        "figure_groups": manifest.get("figure_groups") or [],
        "formula_families": manifest.get("formula_families") or [],
        "validation_checks": manifest.get("validation_checks") or [],
        "aliases": manifest.get("aliases") or [],
        "variants": manifest.get("variants") or [],
        "genericity_rules": manifest.get("genericity_rules") or [],
        **_runtime_metadata(manifest),
    }
    _write_json(generalized_dir / "method_template.json", method_template)
    template = "\n".join([
        "# Copyright (c) 2026 Jinray Xie",
        "# Contact: xiejinhui22@mails.ucas.ac.cn",
        "# Source-available for non-commercial use only; commercial use requires written authorization.",
        "",
        "from __future__ import annotations",
        "",
        "from pathlib import Path",
        "",
        "",
        "def run_template(*, input_table: Path, output_dir: Path, target_column: str = '{{target_column}}') -> dict[str, object]:",
        '    """Generalized method template derived from a completed Draftpaper-loop project."""',
        "    output_dir.mkdir(parents=True, exist_ok=True)",
        "    return {",
        f"        'template_id': '{manifest.get('template_id')}',",
        "        'input_table': str(input_table),",
        "        'target_column': target_column,",
        "        'status': 'template_ready_for_project_binding',",
        "    }",
        "",
        "SOURCE_DERIVATION_METADATA = {",
        f"    'source': {manifest.get('source')!r},",
        f"    'source_skill_id': {manifest.get('source_skill_id')!r},",
        f"    'matched_terms': {list(manifest.get('matched_terms') or [])!r},",
        "    'source_text_copied': False,",
        "}",
    ])
    (generalized_dir / "template.py").write_text(template, encoding="utf-8")
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "candidate_id": manifest.get("candidate_id"),
        "plugin_type": "method_template",
        "template_path": str(generalized_dir / "template.py"),
        "method_template_path": str(generalized_dir / "method_template.json"),
        "rules": [
            "No local file paths, API keys, fixed regions, fixed dates, or project-specific sample IDs.",
            "Expose data columns, output paths, and optional groups as parameters.",
        ],
    }
    _write_json(root / "genericity_report.json", _genericity_report(template, manifest))
    _write_json(root / "generalization_report.json", report)
    return report


def validate_plugin_candidate(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    if (root / "support_manifest.json").exists():
        raise PluginCandidateError("Support candidates are not formal plugin candidates. Validate their extracted data_connector, method_template, or review_rule backflow candidates instead.")
    manifest = _read_json(root / "candidate_manifest.json", {})
    if not manifest:
        raise PluginCandidateError(f"Missing candidate manifest: {root}")
    contribution_texts = []
    for path in [
        root / "generalized_template" / "template.py",
        root / "generalized_template" / "data_connector.json",
        root / "generalized_template" / "method_template.json",
        root / "generalized_template" / "review_rule.json",
        root / "candidate_manifest.json",
    ]:
        contribution_texts.append(_read_text(path))
    raw_source_privacy = _privacy_scan_text(_read_text(root / "source_excerpt.py") or _read_text(root / "source_excerpt.md") or _read_text(root / "source_evidence_summary.md"))
    privacy = _privacy_scan_text("\n".join(contribution_texts))
    genericity = _genericity_report("\n".join(contribution_texts), manifest)
    overlap = detect_plugin_overlap(candidate)
    schema = _candidate_schema_report(manifest, root)
    plugin_type = str(manifest.get("plugin_type") or "method_template")
    checked_files = ["generalized_template/template.py"]
    if plugin_type == "review_rule":
        checked_files.extend([
            "generalized_template/review_rule.json",
            "rule_rationale.md",
            "positive_fixture.json",
            "negative_fixture.json",
        ])
    elif plugin_type == "data_connector":
        checked_files.append("generalized_template/data_connector.json")
    else:
        checked_files.append("generalized_template/method_template.json")
    missing_checked_files = [path for path in checked_files if not (root / path).exists()]
    fixture_contract = (
        _validate_review_rule_fixture_pair(root, manifest)
        if plugin_type == "review_rule" and not missing_checked_files
        else {
            "status": "passed" if not missing_checked_files else "failed",
            "validation_level": "file_presence",
            "runtime_execution_performed": False,
            "fixtures": [],
            "problems": [f"missing:{path}" for path in missing_checked_files],
        }
    )
    fixture_status = fixture_contract["status"]
    validation = {
        "status": "passed" if privacy["status"] == "passed" and genericity["status"] == "passed" and schema["status"] == "passed" and fixture_status == "passed" else "failed",
        "generated_at": utc_now(),
        "candidate_id": manifest.get("candidate_id"),
        "privacy_scan": privacy,
        "raw_source_privacy_scan": raw_source_privacy,
        "genericity_report": genericity,
        "schema_report": schema,
        "overlap_report": overlap,
        "fixture_test_report": {
            "status": fixture_status,
            "checked_files": checked_files,
            "missing_files": missing_checked_files,
            "validation_level": fixture_contract.get("validation_level"),
            "runtime_execution_performed": fixture_contract.get("runtime_execution_performed", False),
            "fixtures": fixture_contract.get("fixtures") or [],
            "problems": fixture_contract.get("problems") or [],
        },
    }
    _write_json(root / "privacy_scan.json", privacy)
    _write_json(root / "genericity_report.json", genericity)
    _write_json(root / "overlap_report.json", overlap)
    _write_json(root / "schema_report.json", schema)
    _write_json(root / "validation_report.json", validation)
    return validation


def promote_plugin_candidate(
    candidate: str | Path,
    *,
    require_human_confirmation: bool = False,
    dry_run: bool = True,
    target_root: str | Path | None = None,
) -> dict[str, Any]:
    """Prepare or perform a guarded promotion into formal discipline modules.

    This command is intentionally narrow: only validated ``data_connector``,
    ``method_template``, and ``review_rule`` candidates can target
    ``discipline_modules``. Support-layer candidates must remain outside formal
    discipline plugin directories, although their extracted review-rule backflow
    candidates can be promoted after validation.
    """

    root = Path(candidate).resolve()
    support_manifest = _read_json(root / "support_manifest.json", {})
    if support_manifest:
        raise PluginCandidateError("Support candidates cannot be promoted into discipline_modules; promote extracted formal review_rule candidates instead.")
    manifest = _read_json(root / "candidate_manifest.json", {})
    if not manifest:
        raise PluginCandidateError(f"Missing candidate manifest: {root}")
    plugin_type = str(manifest.get("plugin_type") or "")
    allowed = {"data_connector", "method_template", "review_rule"}
    if plugin_type not in allowed:
        raise PluginCandidateError(f"Unsupported formal plugin type for promotion: {plugin_type}")
    validation = _read_json(root / "validation_report.json", {})
    if validation.get("status") != "passed":
        raise PluginCandidateError("validate-plugin-candidate must pass before promotion.")
    if not require_human_confirmation:
        raise PluginCandidateError("Promotion requires --require-human-confirmation to prevent unreviewed discipline module writes.")

    from .third_party_provenance import ThirdPartyProvenanceError, validate_candidate_promotion_provenance

    try:
        promotion_provenance = validate_candidate_promotion_provenance(manifest)
    except ThirdPartyProvenanceError as exc:
        raise PluginCandidateError(str(exc)) from exc

    if plugin_type == "review_rule":
        generalized_rule = _read_json(root / "generalized_template" / "review_rule.json", {})
        maturity = str(generalized_rule.get("maturity") or manifest.get("maturity") or "candidate")
        if maturity not in {"runnable", "mature", "paper_integrated", "runtime_integrated"}:
            raise PluginCandidateError(
                "Review-rule promotion requires maturity=runnable or higher after an executable discipline fixture has been reviewed."
            )

    discipline = _safe_id(str(manifest.get("discipline") or manifest.get("primary_discipline") or "default"))
    if plugin_type == "data_connector":
        kind_dir = "data_connectors"
        plugin_id = _safe_id(str(manifest.get("connector_id") or manifest.get("candidate_id") or "data_connector"))
        required_generalized = root / "generalized_template" / "data_connector.json"
    elif plugin_type == "review_rule":
        kind_dir = "review_rules"
        plugin_id = _safe_id(str(manifest.get("rule_id") or manifest.get("candidate_id") or "review_rule"))
        required_generalized = root / "generalized_template" / "review_rule.json"
    else:
        kind_dir = "method_templates"
        plugin_id = _safe_id(str(manifest.get("template_id") or manifest.get("candidate_id") or "method_template"))
        required_generalized = root / "generalized_template" / "method_template.json"
    if not required_generalized.exists():
        raise PluginCandidateError(f"Missing generalized template file: {required_generalized}")

    module_root = Path(target_root).resolve() if target_root else Path(__file__).resolve().parent / "discipline_modules"
    target_dir = module_root / discipline / kind_dir / plugin_id
    overlap = detect_plugin_overlap(root)
    promotion_mode = "augment_existing" if overlap.get("decision") == "merge_with_existing" else "create_new"
    canonical_manifest = _canonical_promoted_manifest(manifest, _read_json(required_generalized, {}), plugin_type)
    canonical_manifest.update(promotion_provenance)
    canonical_manifest["merge_strategy"] = promotion_mode
    canonical_manifest["promotion_mode"] = promotion_mode
    canonical_manifest["intended_merge_target"] = str(target_dir)
    plan = {
        "status": "planned" if dry_run else "promoted",
        "generated_at": utc_now(),
        "candidate_id": manifest.get("candidate_id"),
        "plugin_type": plugin_type,
        "discipline": discipline,
        "source_candidate": str(root),
        "target_dir": str(target_dir),
        "dry_run": dry_run,
        "human_confirmation_required": True,
        "human_confirmation_received": require_human_confirmation,
        "policy": "Only generalized candidate files are copied; source evidence summaries and third-party source are not copied.",
        "promotion_mode": promotion_mode,
        "overlap_report": overlap,
        "runtime_registration": "available_after_write_via_manifest.json",
        "canonical_manifest": canonical_manifest,
        "provenance": promotion_provenance,
    }
    _write_json(root / "promotion_plan.json", plan)
    if dry_run:
        return plan

    target_dir.mkdir(parents=True, exist_ok=True)
    existing_manifest = _read_json(target_dir / "manifest.json", {})
    if existing_manifest:
        canonical_manifest = _merge_promoted_manifest(existing_manifest, canonical_manifest)
    elif promotion_mode == "augment_existing":
        canonical_manifest["augmentation_of"] = overlap.get("existing_matches") or []
    _copy_promotion_fixtures(root, target_dir, canonical_manifest, plugin_type)
    _write_json(target_dir / "manifest.json", canonical_manifest)
    template_path = root / "generalized_template" / "template.py"
    if template_path.exists() and not (target_dir / "template.py").exists():
        shutil.copy2(template_path, target_dir / "template.py")
    _write_json(target_dir / "PROMOTION_MANIFEST.json", plan)
    _write_json(target_dir / "PLUGIN_PROVENANCE.json", {
        "status": "written",
        "candidate_id": manifest.get("candidate_id"),
        "source": manifest.get("source"),
        "source_skill_id": manifest.get("source_skill_id"),
        "source_policy": manifest.get("source_policy"),
        "promotion_mode": promotion_mode,
        "overlap_report": overlap,
        "source_text_copied": False,
        **promotion_provenance,
    })
    return plan


def _canonical_promoted_manifest(
    candidate: dict[str, Any],
    generalized: dict[str, Any],
    plugin_type: str,
) -> dict[str, Any]:
    """Build the single runtime manifest consumed by automatic registration."""

    manifest = dict(generalized)
    manifest.update({
        "candidate_id": candidate.get("candidate_id"),
        "discipline": candidate.get("discipline") or candidate.get("primary_discipline") or generalized.get("discipline") or "default",
        "plugin_type": plugin_type,
        "maturity": generalized.get("maturity") or candidate.get("maturity") or "foundation",
        "aliases": list(dict.fromkeys(list(generalized.get("aliases") or []) + list(candidate.get("aliases") or []))),
        "variants": list(dict.fromkeys(list(generalized.get("variants") or []) + list(candidate.get("variants") or []))),
        "source_skill_refs": list(dict.fromkeys(list(generalized.get("source_skill_refs") or []) + list(candidate.get("source_skill_refs") or [f"{candidate.get('source')}:{candidate.get('source_skill_id')}"]))),
        "provenance_notes": generalized.get("provenance_notes") or candidate.get("provenance_notes") or "Promoted generalized plugin candidate.",
        **_runtime_metadata({**candidate, **generalized}),
    })
    if plugin_type == "data_connector":
        manifest.setdefault("connector_id", candidate.get("connector_id"))
        manifest.setdefault("template", "template.py")
    elif plugin_type == "method_template":
        manifest.setdefault("template_id", candidate.get("template_id"))
        manifest.setdefault("template", "template.py")
    else:
        rule_id = generalized.get("rule_id") or candidate.get("rule_id") or candidate.get("rule_group_id")
        manifest.setdefault("rule_id", rule_id)
        manifest.setdefault("rule_group_id", rule_id)
        manifest.setdefault("template", "template.py")
    return manifest


def _merge_promoted_manifest(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge duplicate contributions without weakening an existing runtime contract."""

    merged = dict(existing)
    for key, value in incoming.items():
        current = merged.get(key)
        if isinstance(current, list) and isinstance(value, list):
            merged[key] = list(dict.fromkeys(current + value))
        elif isinstance(current, dict) and isinstance(value, dict):
            merged[key] = {**current, **{name: item for name, item in value.items() if item not in (None, "", [], {})}}
        elif current in (None, "", [], {}):
            merged[key] = value
    merged["merge_strategy"] = "augment_existing"
    merged["promotion_mode"] = "augment_existing"
    merged["merged_candidate_ids"] = list(dict.fromkeys(list(existing.get("merged_candidate_ids") or []) + [str(incoming.get("candidate_id") or "")]))
    return merged


def _copy_promotion_fixtures(root: Path, target_dir: Path, manifest: dict[str, Any], plugin_type: str) -> None:
    fixture_paths: list[str] = []
    if plugin_type == "review_rule":
        for source_name, target_name in [("positive_fixture.json", "fixture_positive.json"), ("negative_fixture.json", "fixture_negative.json")]:
            source = root / source_name
            if source.exists():
                shutil.copy2(source, target_dir / target_name)
                fixture_paths.append(target_name)
        manifest["fixture_paths"] = fixture_paths
        manifest["positive_fixture_refs"] = ["fixture_positive.json"] if "fixture_positive.json" in fixture_paths else []
        manifest["negative_fixture_refs"] = ["fixture_negative.json"] if "fixture_negative.json" in fixture_paths else []
    elif not manifest.get("fixture_paths"):
        manifest["fixture_paths"] = []


def _candidate_schema_report(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    plugin_type = str(manifest.get("plugin_type") or "method_template")
    missing: list[str] = []
    warnings: list[str] = []
    if manifest.get("runtime_class") not in RUNTIME_CLASSES:
        missing.append("valid_runtime_class")
    if manifest.get("validation_level") not in VALIDATION_LEVELS:
        missing.append("valid_validation_level")
    if plugin_type == "review_rule":
        for field in [
            "rule_id",
            "rule_family",
            "criterion_type",
            "applicable_disciplines",
            "evidence_roles",
            "evidence_binding",
            "threshold_policy",
            "threshold_source",
            "threshold_mode",
            "threshold_validation_status",
            "failure_route",
            "pipeline_hooks",
            "fixture_paths",
            "maturity",
            "deployment_state",
            "review_question",
            "scientific_risk",
            "minimum_evidence_required",
            "allowed_claim_strength",
            "repair_priority",
            "positive_fixture_refs",
            "negative_fixture_refs",
            "backflow_source_type",
            "support_layer_signal_refs",
        ]:
            if not manifest.get(field):
                missing.append(field)
        binding = manifest.get("evidence_binding") or {}
        if not isinstance(binding, dict):
            missing.append("valid_evidence_binding")
        else:
            for field in ["registry_record_types", "required_fields", "forbidden_conflicts"]:
                if field not in binding:
                    missing.append(f"evidence_binding.{field}")
        if "human_confirmation_required" not in manifest:
            missing.append("human_confirmation_required")
        hooks = manifest.get("pipeline_hooks") or {}
        allowed_hook_values = {"optional", "required", "not_applicable"}
        required_hooks = {
            "research_plan",
            "data_acquisition",
            "method_plan",
            "figure_contract",
            "result_support_checkpoint",
            "write_results",
            "write_discussion",
            "citation_audit",
            "reviewer_rescue_loop",
        }
        if set(hooks) != required_hooks:
            missing.append("complete_pipeline_hooks")
        elif any(str(value) not in allowed_hook_values for value in hooks.values()):
            missing.append("valid_pipeline_hook_values")
        threshold = manifest.get("threshold_policy") or {}
        source = manifest.get("threshold_source") or {}
        allowed_threshold_modes = {"fixed", "contextual", "comparative", "journal_guided", "human_confirmed", "none"}
        threshold_mode = manifest.get("threshold_mode") or threshold.get("mode")
        if threshold.get("mode") not in allowed_threshold_modes:
            missing.append("valid_threshold_policy_mode")
        if threshold_mode != threshold.get("mode"):
            missing.append("threshold_mode_matches_policy")
        if threshold.get("mode") == "fixed" and source.get("type") not in {"discipline_convention", "journal_guideline", "benchmark_comparison", "public_benchmark", "user_confirmation", "human_confirmed"}:
            missing.append("fixed_threshold_authoritative_source")
        if threshold.get("mode") == "journal_guided" and source.get("type") != "journal_guideline":
            missing.append("journal_guided_threshold_source")
        if manifest.get("deployment_state") == "promoted_review_rule" and manifest.get("maturity") not in {"runnable", "mature"}:
            missing.append("promoted_review_rule_requires_runnable_or_mature")
        for path_name in ["rule_rationale.md", "positive_fixture.json", "negative_fixture.json", "provenance_summary.json"]:
            if not (root / path_name).exists():
                missing.append(path_name)
        if not (root / "generalized_template" / "review_rule.json").exists():
            warnings.append("generalized_template/review_rule.json missing before generalization")
    elif plugin_type == "method_template":
        for field in ["template_id", "method_family", "input_roles", "output_artifacts"]:
            if not manifest.get(field):
                missing.append(field)
        if not (root / "generalized_template" / "method_template.json").exists():
            warnings.append("generalized_template/method_template.json missing before generalization")
    elif plugin_type == "data_connector":
        for field in ["connector_id", "access_modes", "data_formats", "source_policy"]:
            if not manifest.get(field):
                missing.append(field)
        if manifest.get("source_policy") != "candidate_only_no_direct_upload":
            missing.append("candidate_only_source_policy")
        if not (root / "generalized_template" / "data_connector.json").exists():
            warnings.append("generalized_template/data_connector.json missing before generalization")
    else:
        missing.append(f"unsupported_plugin_type:{plugin_type}")
    return {
        "status": "passed" if not missing else "failed",
        "plugin_type": plugin_type,
        "missing_fields": missing,
        "warnings": warnings,
    }


def detect_plugin_overlap(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    manifest = _read_json(root / "candidate_manifest.json", {})
    discipline = str(manifest.get("discipline") or "default")
    module = get_discipline_module({"discipline": discipline})
    plugin_type = str(manifest.get("plugin_type") or "method_template")
    if plugin_type == "review_rule":
        target_id = str(manifest.get("rule_id") or manifest.get("rule_group_id") or "")
        existing = module.spec.review_rule_dicts()
        id_key = "rule_group_id"
        family_key = "rule_family"
    elif plugin_type == "data_connector":
        target_id = str(manifest.get("connector_id") or "")
        existing = module.spec.connector_dicts()
        id_key = "connector_id"
        family_key = "access_modes"
    else:
        target_id = str(manifest.get("template_id") or "")
        existing = module.spec.method_template_dicts()
        id_key = "template_id"
        family_key = "method_family"
    matches = []
    for item in existing:
        score = 0.0
        if item.get(id_key) == target_id or item.get("rule_id") == target_id:
            score += 0.7
        if plugin_type == "data_connector":
            existing_modes = set(str(value).lower() for value in item.get("access_modes") or [])
            candidate_modes = set(str(value).lower() for value in manifest.get("access_modes") or [])
            existing_formats = set(str(value).lower() for value in item.get("data_formats") or [])
            candidate_formats = set(str(value).lower() for value in manifest.get("data_formats") or [])
            existing_packages = set(str(value).lower() for value in item.get("packages") or [])
            candidate_packages = set(str(value).lower() for value in manifest.get("packages") or [])
            if existing_modes & candidate_modes:
                score += 0.15
            if existing_formats & candidate_formats:
                score += 0.15
            if existing_packages & candidate_packages:
                score += 0.1
        elif item.get(family_key) == manifest.get(family_key):
            score += 0.2
        aliases = set(str(a).lower() for a in item.get("aliases") or [])
        candidate_aliases = set(str(a).lower() for a in manifest.get("aliases") or [])
        if aliases & candidate_aliases:
            score += 0.1
        if score:
            matches.append({id_key: item.get(id_key), family_key: item.get(family_key), "overlap_score": round(score, 3)})
    decision = "merge_with_existing" if matches and max(m["overlap_score"] for m in matches) >= 0.7 else "new_plugin_candidate"
    report = {
        "status": "written",
        "decision": decision,
        "candidate_id": manifest.get("candidate_id"),
        "existing_matches": sorted(matches, key=lambda item: item["overlap_score"], reverse=True),
        "merge_action": "merge aliases, variants, fixtures, and source provenance into the existing discipline module" if decision == "merge_with_existing" else "add a new plugin directory under the discipline module after validation",
    }
    _write_json(root / "overlap_report.json", report)
    return report


def _support_backflow_provenance(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    support_candidate_ids = [str(item) for item in manifest.get("support_candidate_ids") or []]
    support_routes = [str(item) for item in manifest.get("backflow_from_support_routes") or []]
    source_root = root.parent
    while source_root.name and source_root.name != str(manifest.get("source_skill_id") or ""):
        if (source_root / "SKILL_DISPOSITION.json").exists():
            break
        if source_root.parent == source_root:
            break
        source_root = source_root.parent
    disposition = _read_json(source_root / "SKILL_DISPOSITION.json", {})
    support_manifests: list[dict[str, Any]] = []
    for support_record in disposition.get("support_candidates") or []:
        if support_candidate_ids and str(support_record.get("candidate_id")) not in support_candidate_ids:
            continue
        support_path = Path(str(support_record.get("path") or ""))
        support_manifest = _read_json(support_path / "support_manifest.json", {}) if support_path else {}
        backflow_links = _read_json(support_path / "review_rule_backflow_links.json", {}) if support_path else {}
        if support_manifest:
            support_manifests.append({
                "candidate_id": support_manifest.get("candidate_id"),
                "support_type": support_manifest.get("support_type"),
                "intended_support_target": support_manifest.get("intended_support_target"),
                "support_purpose": support_manifest.get("support_purpose"),
                "review_rule_backflow_candidate_ids": support_manifest.get("review_rule_backflow_candidate_ids") or [],
                "review_rule_backflow_scope": support_manifest.get("review_rule_backflow_scope") or {},
                "backflow_signal_scan": support_manifest.get("backflow_signal_scan") or backflow_links.get("backflow_signal_scan") or {},
                "capability_ir": support_manifest.get("capability_ir") or {},
                "backflow_links": backflow_links,
                "source_policy": support_manifest.get("source_policy"),
                "promotion_policy": support_manifest.get("promotion_policy"),
            })
    return {
        "status": "written",
        "generated_at": utc_now(),
        "candidate_id": manifest.get("candidate_id"),
        "plugin_type": manifest.get("plugin_type"),
        "source": manifest.get("source"),
        "source_skill_id": manifest.get("source_skill_id"),
        "backflow_from_support_routes": support_routes,
        "support_candidate_ids": support_candidate_ids,
        "support_candidates": support_manifests,
        "source_policy": "metadata_only; source_evidence_summary and third-party source files are intentionally excluded from contribution packages",
        "review_rule_backflow_policy": "Support candidates remain outside discipline_modules; only validated formal candidates can be promoted with human confirmation.",
    }


def _render_contribution_provenance(provenance: dict[str, Any]) -> str:
    return "\n".join([
        "# Contribution Provenance and Backflow",
        "",
        f"Candidate: `{provenance.get('candidate_id')}`",
        f"Plugin type: `{provenance.get('plugin_type')}`",
        f"Source skill: `{provenance.get('source')}:{provenance.get('source_skill_id')}`",
        "",
        "## Support Routes",
        *[f"- `{route}`" for route in (provenance.get("backflow_from_support_routes") or [])],
        "",
        "## Support Candidates",
        *[
            f"- `{item.get('candidate_id')}` ({item.get('support_type')}) -> {item.get('intended_support_target')}"
            for item in (provenance.get("support_candidates") or [])
        ],
        "",
        "## Review Rule Backflow Signal Scan",
        *[
            f"- `{item.get('candidate_id')}` eligible families: "
            f"{', '.join((item.get('backflow_signal_scan') or {}).get('eligible_rule_families') or []) or 'none'}"
            for item in (provenance.get("support_candidates") or [])
        ],
        "",
        "This package includes metadata-only provenance. It intentionally excludes source evidence summaries, third-party source code, private files, credentials, PDFs, and project-specific artifacts.",
    ])


def _render_contribution_preflight_actions() -> str:
    return "\n".join([
        "# GitHub Actions Preflight",
        "",
        "Use this snippet in a PR workflow to check packaged plugin contributions before maintainer review.",
        "It validates the contribution package itself and does not read third-party source text.",
        "",
        "```yaml",
        "name: Draftpaper plugin contribution preflight",
        "on: [pull_request]",
        "jobs:",
        "  plugin-preflight:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - uses: actions/checkout@v4",
        "      - uses: actions/setup-python@v5",
        "        with:",
        "          python-version: '3.11'",
        "      - run: python -m pip install -e .",
        "      - run: python -m draftpaper_cli.cli preflight-plugin-contribution --package <path-to-contribution_package>",
        "```",
        "",
        "The package must contain only metadata, generalized templates, fixtures, validation reports, and provenance/backflow summaries.",
    ])


def _render_contributor_checklist(manifest: dict[str, Any]) -> str:
    return "\n".join([
        "# Plugin Contribution Checklist",
        "",
        f"Candidate: `{manifest.get('candidate_id')}`",
        f"Plugin type: `{manifest.get('plugin_type')}`",
        f"Target: `{manifest.get('intended_merge_target')}`",
        "",
        "Before opening a PR:",
        "",
        "- Run `generalize-plugin-candidate` and `validate-plugin-candidate` locally.",
        "- Run `package-plugin-contribution` and then `preflight-plugin-contribution` on the generated package.",
        "- Confirm the package contains no third-party skill text, source excerpts, PDFs, private data, local paths, server names, credentials, or generated manuscript drafts.",
        "- Confirm support-layer candidates are not submitted as formal discipline plugins; submit validated backflow candidates instead.",
        "- Confirm any fixed threshold has a journal guideline, discipline convention, or benchmark source. Otherwise keep it contextual, comparative, or human-confirmed.",
        "- Confirm normal, failure, and boundary fixtures are small, public, credential-free, and CI-suitable before requesting promotion beyond candidate/foundation maturity.",
    ])


def package_plugin_contribution(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    if (root / "support_manifest.json").exists():
        raise PluginCandidateError("Support candidates cannot be packaged as formal discipline plugin contributions; package their validated formal backflow candidates instead.")
    manifest = _read_json(root / "candidate_manifest.json", {})
    validation = _read_json(root / "validation_report.json", {})
    if validation.get("status") != "passed":
        raise PluginCandidateError("validate-plugin-candidate must pass before packaging a contribution.")
    package_dir = root / "contribution_package"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)
    for name in ["candidate_manifest.json", "overlap_report.json", "genericity_report.json", "privacy_scan.json", "validation_report.json"]:
        src = root / name
        if src.exists():
            shutil.copy2(src, package_dir / name)
    for name in ["rule_rationale.md", "positive_fixture.json", "negative_fixture.json", "provenance_summary.json"]:
        src = root / name
        if src.exists():
            shutil.copy2(src, package_dir / name)
    if (root / "generalized_template").exists():
        shutil.copytree(root / "generalized_template", package_dir / "generalized_template")
    provenance = _support_backflow_provenance(root, manifest)
    _write_json(package_dir / "PROVENANCE_AND_BACKFLOW.json", provenance)
    (package_dir / "PROVENANCE_AND_BACKFLOW.md").write_text(_render_contribution_provenance(provenance), encoding="utf-8")
    (package_dir / "CONTRIBUTOR_CHECKLIST.md").write_text(_render_contributor_checklist(manifest), encoding="utf-8")
    (package_dir / "GITHUB_ACTIONS_PREFLIGHT.md").write_text(_render_contribution_preflight_actions(), encoding="utf-8")
    merge_plan = {
        "status": "written",
        "candidate_id": manifest.get("candidate_id"),
        "target": manifest.get("intended_merge_target"),
        "fork_policy": "Open a temporary PR branch; main remains the only stable plugin registry.",
        "source_policy": "Only metadata, generalized templates, validation reports, and provenance/backflow summaries are packaged. Third-party source text and source_evidence_summary.md are excluded.",
        "provenance": "PROVENANCE_AND_BACKFLOW.json",
        "maintainer_steps": [
            "gh pr checkout <PR_NUMBER>",
            "python -m draftpaper_cli.cli validate-plugin-candidate --candidate <candidate>",
            "review overlap_report.json and merge_plan.json",
            "review PROVENANCE_AND_BACKFLOW.json to confirm support-skill backflow and source policy",
            "run review-plugin-contribution to generate a read-only maintainer review report",
            "merge generalized reusable files into the target discipline module",
            "run pytest before squash-merging into main",
        ],
    }
    _write_json(package_dir / "merge_plan.json", merge_plan)
    _write_json(root / "merge_plan.json", merge_plan)
    return {"status": "packaged", "candidate_id": manifest.get("candidate_id"), "package_dir": str(package_dir), "merge_plan": str(package_dir / "merge_plan.json")}


def _resolve_contribution_package_root(package: str | Path) -> tuple[Path, Path]:
    requested_root = Path(package).resolve()
    root = requested_root
    if not root.exists() or not root.is_dir():
        raise PluginCandidateError(f"Missing contribution package directory: {root}")
    if not (root / "candidate_manifest.json").exists():
        if (root / "contribution_package" / "candidate_manifest.json").exists():
            root = root / "contribution_package"
        elif root.name == "generalized_template" and (root.parent / "candidate_manifest.json").exists():
            root = root.parent
    return requested_root, root


def preflight_plugin_contribution_package(package: str | Path) -> dict[str, Any]:
    """Validate a packaged contribution before GitHub PR review.

    This checks the package boundary, not the original third-party skill source.
    It is intended for contributor-side preflight and GitHub Actions.
    """

    requested_root, root = _resolve_contribution_package_root(package)
    stale_report = root / "PLUGIN_CONTRIBUTION_PREFLIGHT.json"
    if stale_report.exists():
        stale_report.unlink()

    required_files = [
        "candidate_manifest.json",
        "validation_report.json",
        "PROVENANCE_AND_BACKFLOW.json",
        "merge_plan.json",
        "genericity_report.json",
        "privacy_scan.json",
    ]
    missing_files = [name for name in required_files if not (root / name).exists()]
    forbidden_names = {
        "source_evidence_summary.md",
        "source_excerpt.md",
        "source_excerpt.py",
        "SKILL.md",
        "paper.pdf",
        "main.pdf",
        "main.tex",
    }
    forbidden_suffixes = {".pdf", ".docx", ".zip", ".7z", ".tar", ".gz", ".pt", ".pth", ".ckpt", ".pkl"}
    forbidden_paths = []
    text_chunks = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        lowered = path.name.lower()
        if lowered in {item.lower() for item in forbidden_names} or path.suffix.lower() in forbidden_suffixes:
            forbidden_paths.append(rel)
        if path.suffix.lower() in {".json", ".md", ".py", ".txt", ".yaml", ".yml"}:
            text_chunks.append(_read_text(path, limit=50_000))

    manifest = _read_json(root / "candidate_manifest.json", {})
    validation = _read_json(root / "validation_report.json", {})
    provenance = _read_json(root / "PROVENANCE_AND_BACKFLOW.json", {})
    merge_plan = _read_json(root / "merge_plan.json", {})
    plugin_type = str(manifest.get("plugin_type") or "")
    allowed_types = {"data_connector", "method_template", "review_rule"}
    generalized_dir = root / "generalized_template"
    expected_generalized = {
        "data_connector": generalized_dir / "data_connector.json",
        "method_template": generalized_dir / "method_template.json",
        "review_rule": generalized_dir / "review_rule.json",
    }
    generalized_missing = []
    if plugin_type in expected_generalized and not expected_generalized[plugin_type].exists():
        generalized_missing.append(str(expected_generalized[plugin_type].relative_to(root).as_posix()))
    if not (generalized_dir / "template.py").exists():
        generalized_missing.append("generalized_template/template.py")

    privacy = _privacy_scan_text("\n".join(text_chunks))
    problems: list[str] = []
    if missing_files:
        problems.append("missing_required_files")
    if forbidden_paths:
        problems.append("forbidden_source_or_binary_files")
    if plugin_type not in allowed_types:
        problems.append("unsupported_or_support_layer_plugin_type")
    if validation.get("status") != "passed":
        problems.append("candidate_validation_not_passed")
    if privacy.get("status") != "passed":
        problems.append("privacy_or_secret_scan_failed")
    if generalized_missing:
        problems.append("missing_generalized_template_files")
    if "metadata_only" not in str(provenance.get("source_policy") or ""):
        problems.append("provenance_source_policy_not_metadata_only")
    if "discipline_modules" not in str(merge_plan.get("target") or manifest.get("intended_merge_target") or ""):
        problems.append("merge_target_not_formal_discipline_module")
    if manifest.get("source_policy") != "candidate_only_no_direct_upload":
        problems.append("candidate_source_policy_not_candidate_only")

    preflight = {
        "status": "passed" if not problems else "failed",
        "generated_at": utc_now(),
        "requested_package_dir": str(requested_root),
        "resolved_package_dir": str(root),
        "package_dir": root.name,
        "candidate_id": manifest.get("candidate_id"),
        "plugin_type": plugin_type,
        "problems": problems,
        "missing_files": missing_files,
        "forbidden_paths": forbidden_paths,
        "generalized_missing": generalized_missing,
        "privacy_scan": privacy,
        "validation_status": validation.get("status"),
        "promotion_allowed_by_preflight": False,
        "policy": "Preflight verifies package safety and reviewability only; promotion still requires maintainer review and explicit human confirmation.",
    }
    _write_json(root / "PLUGIN_CONTRIBUTION_PREFLIGHT.json", preflight)
    return preflight


def _render_plugin_contribution_review(review: dict[str, Any]) -> str:
    lines = [
        "# Plugin Contribution Maintainer Review",
        "",
        f"- Status: `{review.get('status')}`",
        f"- Recommendation: `{review.get('maintainer_recommendation')}`",
        f"- Candidate: `{review.get('candidate_id')}`",
        f"- Plugin type: `{review.get('plugin_type')}`",
        f"- Discipline: `{review.get('discipline')}`",
        f"- Target: `{review.get('target')}`",
        "",
        "## Preflight",
        "",
        f"- Preflight status: `{review.get('preflight_status')}`",
        f"- Problems: {', '.join(review.get('preflight_problems') or []) or 'none'}",
        "",
        "## Source And Backflow",
        "",
        f"- Source policy: {review.get('source_policy') or 'not declared'}",
        f"- Metadata-only source: `{review.get('metadata_only_source')}`",
        f"- Backflow from support routes: {', '.join(review.get('backflow_from_support_routes') or []) or 'none'}",
        f"- Backflow rule families: {', '.join(review.get('backflow_rule_families') or []) or 'none'}",
        "",
        "## Threshold And Review Policy",
        "",
        f"- Threshold mode: `{review.get('threshold_mode')}`",
        f"- Threshold source: `{review.get('threshold_source_type')}`",
        f"- Threshold validation status: `{review.get('threshold_validation_status')}`",
        f"- Human confirmation required: `{review.get('human_confirmation_required')}`",
        f"- Blocking level: `{review.get('blocking_level')}`",
        f"- Failure route: `{review.get('failure_route')}`",
        "",
        "## Files To Review",
        "",
    ]
    for item in review.get("files_to_review") or []:
        lines.append(f"- `{item}`")
    if not review.get("files_to_review"):
        lines.append("- none")
    lines.extend([
        "",
        "## Maintainer Notes",
        "",
    ])
    for note in review.get("maintainer_notes") or []:
        lines.append(f"- {note}")
    if not review.get("maintainer_notes"):
        lines.append("- No additional notes.")
    lines.extend([
        "",
        "## Next Steps",
        "",
    ])
    for step in review.get("next_steps") or []:
        lines.append(f"- {step}")
    if not review.get("next_steps"):
        lines.append("- No next steps recorded.")
    return "\n".join(lines) + "\n"


def review_plugin_contribution_package(package: str | Path) -> dict[str, Any]:
    """Create a read-only maintainer review report for a packaged contribution."""

    requested_root, root = _resolve_contribution_package_root(package)
    preflight = preflight_plugin_contribution_package(root)
    manifest = _read_json(root / "candidate_manifest.json", {})
    validation = _read_json(root / "validation_report.json", {})
    provenance = _read_json(root / "PROVENANCE_AND_BACKFLOW.json", {})
    merge_plan = _read_json(root / "merge_plan.json", {})
    genericity = _read_json(root / "genericity_report.json", {})
    privacy = _read_json(root / "privacy_scan.json", {})

    plugin_type = str(manifest.get("plugin_type") or "")
    threshold_policy = manifest.get("threshold_policy") if isinstance(manifest.get("threshold_policy"), dict) else {}
    threshold_source = manifest.get("threshold_source") if isinstance(manifest.get("threshold_source"), dict) else {}
    backflow_routes = provenance.get("backflow_from_support_routes") or []
    support_candidates = provenance.get("support_candidates") if isinstance(provenance.get("support_candidates"), list) else []
    backflow_families: set[str] = set()
    for item in support_candidates:
        if not isinstance(item, dict):
            continue
        scan = item.get("backflow_signal_scan") if isinstance(item.get("backflow_signal_scan"), dict) else {}
        for family in scan.get("families") or item.get("review_rule_backflow_scope") or []:
            backflow_families.add(str(family))
    if manifest.get("rule_family"):
        backflow_families.add(str(manifest.get("rule_family")))

    files_to_review = [
        name for name in [
            "candidate_manifest.json",
            "validation_report.json",
            "PROVENANCE_AND_BACKFLOW.json",
            "merge_plan.json",
            "genericity_report.json",
            "privacy_scan.json",
            "rule_rationale.md" if plugin_type == "review_rule" else "",
            "positive_fixture.json" if plugin_type == "review_rule" else "",
            "negative_fixture.json" if plugin_type == "review_rule" else "",
            f"generalized_template/{plugin_type}.json" if plugin_type else "",
            "generalized_template/template.py",
        ]
        if name and (root / name).exists()
    ]

    notes: list[str] = []
    if plugin_type == "review_rule":
        notes.append("Review the rule family, evidence binding, failure route, and threshold policy before any promotion.")
    if backflow_routes:
        notes.append("This candidate includes support-layer backflow; confirm workflow/paper/shared skill content was generalized into a formal rule rather than copied.")
    if threshold_policy.get("mode") in {"fixed", "journal_guided"}:
        notes.append("Confirm the threshold source is a journal guideline, public benchmark, discipline convention, or explicit human confirmation.")
    elif plugin_type == "review_rule":
        notes.append("Contextual or comparative thresholds should remain advisory until they are evidence-bound in a paper workflow.")
    if preflight.get("status") != "passed":
        notes.append("Preflight failed; do not review for merge until the package boundary problems are fixed.")
    if privacy.get("status") and privacy.get("status") != "passed":
        notes.append("Privacy scan is not clean; inspect all flagged paths before continuing.")
    if genericity.get("status") and genericity.get("status") != "passed":
        notes.append("Genericity report is not clean; require a more reusable template or fixture boundary.")

    if preflight.get("status") != "passed":
        recommendation = "fix_required"
    elif plugin_type not in {"data_connector", "method_template", "review_rule"}:
        recommendation = "reject_support_layer_or_unsafe"
    elif manifest.get("source_policy") != "candidate_only_no_direct_upload":
        recommendation = "fix_required"
    else:
        recommendation = "ready_for_human_review"

    next_steps = [
        "Review the listed files without opening or copying third-party source repositories into the public tree.",
        "Confirm overlap and aliases before merging to avoid duplicate discipline plugins.",
        "Run validate-plugin-candidate and the relevant discipline regression tests before promotion.",
    ]
    if plugin_type == "review_rule":
        next_steps.append("Confirm the rule can bind to Scientific Evidence Registry records before enabling any blocking behavior.")
    if recommendation == "fix_required":
        next_steps.insert(0, "Ask the contributor to fix the preflight or package-policy problems before maintainer review.")

    review = {
        "status": "written",
        "generated_at": utc_now(),
        "requested_package_dir": str(requested_root),
        "resolved_package_dir": str(root),
        "candidate_id": manifest.get("candidate_id"),
        "plugin_type": plugin_type,
        "discipline": manifest.get("discipline") or manifest.get("primary_discipline"),
        "target": merge_plan.get("target") or manifest.get("intended_merge_target"),
        "preflight_status": preflight.get("status"),
        "preflight_problems": preflight.get("problems") or [],
        "validation_status": validation.get("status"),
        "source_policy": provenance.get("source_policy") or manifest.get("source_policy"),
        "metadata_only_source": "metadata_only" in str(provenance.get("source_policy") or ""),
        "backflow_from_support_routes": sorted(str(item) for item in backflow_routes),
        "backflow_rule_families": sorted(backflow_families),
        "threshold_mode": threshold_policy.get("mode"),
        "threshold_source_type": threshold_source.get("type"),
        "threshold_validation_status": manifest.get("threshold_validation_status"),
        "human_confirmation_required": bool(manifest.get("human_confirmation_required")),
        "blocking_level": manifest.get("blocking_level"),
        "failure_route": manifest.get("failure_route"),
        "files_to_review": files_to_review,
        "maintainer_notes": notes,
        "maintainer_recommendation": recommendation,
        "next_steps": next_steps,
        "policy": "Read-only maintainer review. This report never promotes, copies, or vendors third-party source files.",
    }
    _write_json(root / "PLUGIN_CONTRIBUTION_REVIEW.json", review)
    (root / "PLUGIN_CONTRIBUTION_REVIEW.md").write_text(_render_plugin_contribution_review(review), encoding="utf-8")
    return review


def write_github_contribution_guide(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    out = state.path / "plugin_candidates" / "GITHUB_CONTRIBUTION_GUIDE.md"
    content = """# Draftpaper-loop Plugin Contribution Guide

Use forks and PR branches only as temporary contribution channels. Stable reusable capabilities must be merged into `main` under the matching discipline module.

Contributor preflight:

```powershell
git remote add upstream https://github.com/xiejhhhhhh/Draftpaper_loop.git
git fetch upstream
git rebase upstream/main
python -m draftpaper_cli.cli extract-skill-capabilities --source-file <SKILL.md> --source local_skill --discipline auto --output-root <out>
python -m draftpaper_cli.cli compile-skill-source --source-root <skills_or_project_docs> --source local_skill --discipline auto --output-root <compiled>
python -m draftpaper_cli.cli summarize-plugin-candidates --project <project>
python -m draftpaper_cli.cli generalize-plugin-candidate --candidate <candidate>
python -m draftpaper_cli.cli validate-plugin-candidate --candidate <candidate>
python -m draftpaper_cli.cli package-plugin-contribution --candidate <candidate>
python -m draftpaper_cli.cli preflight-plugin-contribution --package <candidate>/contribution_package
python -m draftpaper_cli.cli review-plugin-contribution --package <candidate>/contribution_package
python -m draftpaper_cli.cli promote-plugin-candidate --candidate <candidate> --require-human-confirmation --dry-run
```

Formal discipline plugin PRs can include only validated `data_connector`, `method_template`, or `review_rule` candidates. `workflow_recipe`, `paper_contract`, and `shared_capability` outputs are support-layer candidates: keep them as provenance/backflow records, and submit the extracted formal backflow candidates instead.

For review rules, include `rule_rationale.md`, `positive_fixture.json`, `negative_fixture.json`, `provenance_summary.json`, and `PROVENANCE_AND_BACKFLOW.json`. A review rule should describe the evidence role it checks, the pipeline hooks where it applies, the failure route, and whether any threshold is contextual, comparative, journal-guided, or human-confirmed.

Do not submit private data, local paths, credentials, paper PDFs, generated manuscript drafts, or project-specific scripts. Submit generalized templates, manifests, fixtures, preflight reports, and tests only.
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return {"status": "written", "guide": str(out)}
