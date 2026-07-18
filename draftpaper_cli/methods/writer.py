# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from ..data_feasibility import DataGateError, validate_data_feasibility_for_methods
from ..execution_policy import redact_sensitive, sanitized_environment
from ..html_utils import write_html_report
from ..io_utils import read_json, read_text
from ..latex_utils import safe_latex_text
from ..method_plan import MethodPlanError, validate_method_plan_for_methods
from ..manuscript_composer import SectionCompositionError, select_validated_section_draft
from ..observations import load_observations
from ..project_scaffold import _write_json, utc_now
from ..project_state import load_project, mark_stage_stale, update_stage_status
from ..reference_usage import ensure_reference_usage_plan, missing_entries_for_section
from ..evidence_registry import EVIDENCE_REGISTRY_JSON, build_scientific_evidence_registry, ensure_registry_consistent
from ..result_evidence import ResultEvidenceError, resolve_result_evidence
from ..writing_brief import METHOD_WRITING_BRIEF_HTML, METHOD_WRITING_BRIEF_JSON, build_method_writing_brief
from ..write_set_guard import BoundaryViolation, resolve_confined_path

from .common import (
    METHOD_INPUTS,
    METHOD_OUTPUTS,
    METHOD_TOKEN_LABELS,
    METHOD_WRITING_INPUTS,
    MethodsGateError,
    _clean_sentence,
    _drop_internal_method_sentences,
    _ensure_method_plan,
    _missing_declared_outputs,
    _read_json,
    _read_manifest,
    _strip_forbidden_paths,
)

from .formulas import (
    _formula_step_tokens,
    _latex_formula_entries,
    _render_formula_block,
    _safe_latex_text,
    _write_method_formulas,
)

def _humanize_method_text(text: str) -> str:
    output = str(text or "")
    for token, label in METHOD_TOKEN_LABELS.items():
        output = re.sub(rf"\b{re.escape(token)}\b", label, output)
        output = re.sub(rf"\b{re.escape(token.replace('_', '-'))}\b", label, output)
    output = re.sub(r"\b(?:history|current)_[A-Za-z0-9_]+_id\b", "observation identifier", output, flags=re.I)
    output = re.sub(r"\b[A-Za-z0-9_]+_(?:file|path|filename|pathname)\b", "data-product descriptor", output, flags=re.I)
    output = output.replace("software operations", "analytical steps")
    output = re.sub(r"(^|(?<=[.!?])\s+)Use\s+", r"\1The analysis uses ", output)
    output = re.sub(r"(^|(?<=[.!?])\s+)Build\s+from\s+", r"\1The model is built from ", output)
    output = re.sub(r"(^|(?<=[.!?])\s+)Build\s+", r"\1The model is built to support ", output)
    output = re.sub(r"(^|(?<=[.!?])\s+)Treat\s+", r"\1The planned comparisons treat ", output)
    output = re.sub(r"(^|(?<=[.!?])\s+)Restrict claims to\s+", r"\1Claims are restricted to ", output)
    output = re.sub(r";\s*do not claim\s+", "; claims do not extend to ", output)
    output = output.replace("as planned model comparisons", "as model-comparison axes")
    output = output.replace("Current planned modeling route:", "The modeling route combines")
    output = _canonicalize_method_label_text(output)
    return output


def _canonicalize_method_label_text(text: str) -> str:
    """Clean repeated labels created by layered field-name normalization."""
    output = str(text or "")
    replacements = {
        "classification target target": "classification target",
        "class label label": "class label",
        "processing-processing-version metadata metadata": "processing-version metadata",
        "processing-version metadata metadata": "processing-version metadata",
        "metadata metadata": "metadata",
        "detector detector metadata": "detector metadata",
        "observation observation identifier": "observation identifier",
        "identifier identifier": "identifier",
        "products products": "products",
        "processed research processed research materials": "processed research materials",
    }
    for old, new in replacements.items():
        output = re.sub(re.escape(old), new, output, flags=re.I)
    return output


def _canonical_method_column_label(column: str) -> str:
    """Map an input column or data role to a prose-safe scientific label."""
    raw = _strip_forbidden_paths(str(column or "")).strip()
    if not raw:
        return ""
    normalized = raw.lower().replace("-", "_")
    if normalized in METHOD_TOKEN_LABELS:
        return METHOD_TOKEN_LABELS[normalized]
    label = _humanize_method_text(raw).strip()
    label = re.sub(r"\b[A-Za-z0-9]+_[A-Za-z0-9_]+\b", lambda match: match.group(0).replace("_", " "), label)
    return _canonicalize_method_label_text(label).strip()


def _dedupe_method_labels(labels: list[str]) -> list[str]:
    kept: list[str] = []
    seen: set[str] = set()
    for label in labels:
        cleaned = _canonicalize_method_label_text(label).strip(" ,;.")
        if not cleaned:
            continue
        key = re.sub(r"\s+", " ", cleaned.lower())
        if key in seen:
            continue
        seen.add(key)
        kept.append(cleaned)
    return kept


def _code_output_role_labels(outputs: list[Any]) -> list[str]:
    labels: list[str] = []
    for item in outputs:
        text = str(item or "").replace("\\", "/").lower()
        if not text:
            continue
        if "generated_pipeline" in text or "run_analysis" in text:
            labels.append("stage-owned analysis pipeline")
        elif "scientific_plotting" in text or "plot" in text:
            labels.append("publication figure utilities")
        elif "test_" in text or "/tests/" in text:
            labels.append("execution smoke tests")
        elif "requirements" in text:
            labels.append("declared analysis dependencies")
        elif "manifest" in text:
            labels.append("method-output trace records")
    return _dedupe_method_labels(labels)


def _method_role_label(role: str) -> str:
    normalized = str(role or "").strip().lower()
    labels = {
        "figure_generation": "scientific figure synthesis",
        "method_model_or_analysis": "model fitting and statistical analysis",
        "method_support_library": "reusable analytical utilities",
        "time_aware_transformer_training": "time-aware sequence classification",
        "baseline_model": "baseline model comparison",
        "ablation_study": "ablation analysis",
        "spatial_block_validation": "spatially blocked validation",
    }
    return labels.get(normalized, normalized.replace("_", " ") or "method implementation")


def _section_profile_for_methods(context: dict[str, Any], formula_entries: list[dict[str, Any]]) -> dict[str, str]:
    blob = " ".join(
        str(value or "")
        for value in [
            context.get("method_family_summary"),
            context.get("data_role"),
            context.get("analysis_steps"),
            context.get("code_trace_summary"),
        ]
    ).lower()
    formula_blob = " ".join(str(item.get("method_step") or item.get("name") or "") for item in formula_entries).lower()
    combined = blob + " " + formula_blob
    if any(token in combined for token in ["transformer", "light-curve", "light curve", "spectral", "astronom", "current-observation", "time2vec"]):
        return {
            "design": "Sample Construction and Observation Products",
            "model": "Temporal, Spectral, and Tabular Representation",
            "validation": "Classifier Objective, Validation, and Ablation",
            "bridge": "The method follows the evidence chain used to generate the main figures: event-level sample construction, current-observation tokens, historical time-series context, spectral or tabular features, temporal encoding, feature fusion, validation, ablation, and metrics.",
        }
    if any(token in combined for token in ["random forest", "xgboost", "classification", "regression", "ablation", "baseline"]):
        return {
            "design": "Sample Construction and Feature Sets",
            "model": "Model Formulation and Training Objective",
            "validation": "Validation, Baselines, Ablation, and Metrics",
            "bridge": "The method is organized around sample construction, feature representation, model fitting, validation design, baseline comparison, ablation, and diagnostic metrics.",
        }
    return {
        "design": "Sample Construction and Analytical Design",
        "model": "Model and Feature Formulation",
        "validation": "Validation and Metrics",
        "bridge": "The method is organized around sample construction, representation, model formulation, optimization, validation, and diagnostic metrics so that each empirical claim remains tied to the verified inputs and outputs.",
    }


def _method_citation_paragraphs(project_dir: Path, existing: str) -> list[str]:
    ensure_reference_usage_plan(project_dir)
    entries = missing_entries_for_section(project_dir, "methods", existing)
    if not entries:
        return []
    paragraphs: list[str] = []
    sentences: list[str] = []
    for entry in entries:
        key = str(entry.get("citation_key") or "")
        evidence = _drop_internal_method_sentences(entry.get("evidence_summary") or entry.get("title"))
        if key and evidence:
            sentences.append(f"{_safe_latex_text(evidence)} \\citep{{{key}}}.")
    for index in range(0, len(sentences), 4):
        paragraphs.append(" ".join(sentences[index:index + 4]))
    return paragraphs


def _method_family_text(requirements: dict[str, Any]) -> str:
    families = [str(item).replace("_", " ") for item in requirements.get("method_families") or []]
    if not families or families == ["method family requires user confirmation"]:
        return "The method family requires user confirmation and should be described conservatively."
    return "The planned method family is " + ", ".join(families) + "."


def _metrics_text(manifest: dict[str, Any], requirements: dict[str, Any]) -> str:
    metrics = manifest.get("metrics") or {}
    primary = requirements.get("primary_metric") or next(iter(metrics.keys()), "primary metric")
    observed = metrics.get(primary)
    threshold = requirements.get("minimum_primary_metric")
    if observed is not None and threshold is not None:
        return f"Model evaluation reports {_humanize_method_text(str(primary))}={observed} against a predefined acceptance value of {threshold}."
    if observed is not None:
        return f"Model evaluation reports {_humanize_method_text(str(primary))}={observed}; interpretation remains conditional because no explicit acceptance value was configured."
    if metrics:
        compact = ", ".join(f"{_humanize_method_text(str(key))}={value}" for key, value in list(metrics.items())[:5])
        return "Model evaluation reports scalar outputs including " + compact + "."
    return "The implemented analysis completed without parsed scalar metrics, so the method narrative should focus on validated inputs, outputs, and claim boundaries rather than performance magnitude."


def _analysis_steps_text(requirements: dict[str, Any], observations: list[dict[str, Any]], analysis_manifest: dict[str, Any]) -> str:
    observed = " ".join(_clean_sentence(item.get("text")) for item in observations if item.get("kind") in {"method_rationale", "agent_analysis", "code_design", "method_summary"})
    user_method = _clean_sentence(requirements.get("user_method"))
    if observed and user_method:
        return _humanize_method_text(user_method + " " + observed)[:1600]
    if observed:
        return _humanize_method_text(observed)[:1400]
    if user_method:
        return _humanize_method_text(user_method)
    method_excerpt = _clean_sentence(analysis_manifest.get("method_plan_excerpt"))
    if method_excerpt:
        return _humanize_method_text(method_excerpt[:1000])
    code_plan = analysis_manifest.get("method_code_plan") or {}
    method_families = ", ".join(str(item).replace("_", " ") for item in code_plan.get("method_families") or [])
    validation_checks = ", ".join(str(item).replace("_", " ") for item in code_plan.get("validation_checks") or [])
    if method_families or validation_checks:
        return ("The implemented method follows the discipline-aware method blueprint. "
                f"Planned method families include {method_families or 'general analytical modelling'}; "
                f"validation checks include {validation_checks or 'basic execution and output verification'}.")
    return "The method should be described as an implemented analytical design whose steps are constrained by the method plan and available data."


def _data_role_text(manifest: dict[str, Any], analysis_manifest: dict[str, Any]) -> str:
    selected = analysis_manifest.get("selected_input_profile") or {}
    columns = selected.get("columns") or []
    role_labels: list[str] = []
    for column in columns:
        label = _canonical_method_column_label(str(column))
        if label:
            role_labels.append(label)
    role_labels = _dedupe_method_labels(role_labels)
    if role_labels:
        column_text = ", ".join(role_labels[:10])
        return "The analysis uses prepared scientific variable groups, including " + column_text + ", to connect the data evidence with the planned analysis."
    inputs = manifest.get("input_data") or []
    if inputs:
        return "The analysis uses user-specified, analysis-ready inputs rather than making unverified raw-data claims."
    return "The analysis uses the evidence approved by the data feasibility gate."


def _method_code_trace_text(analysis_manifest: dict[str, Any], formula_manifest: dict[str, Any], figure_code_trace: dict[str, Any]) -> str:
    files = analysis_manifest.get("files") if isinstance(analysis_manifest, dict) else []
    formula_count = int(formula_manifest.get("formula_count") or len(formula_manifest.get("formulas") or [])) if isinstance(formula_manifest, dict) else 0
    trace_count = int(
        figure_code_trace.get("trace_count")
        or len(figure_code_trace.get("traces") or [])
        or len(figure_code_trace.get("figure_checks") or [])
    ) if isinstance(figure_code_trace, dict) else 0
    pieces = []
    if isinstance(files, list) and files:
        roles = sorted({str(item.get("code_role") or "method_code") for item in files if isinstance(item, dict)})
        pieces.append(
            "The implemented analysis scripts cover "
            + ", ".join(_method_role_label(role) for role in roles[:5])
            + "."
        )
    elif isinstance(analysis_manifest, dict) and analysis_manifest.get("canonical_code_outputs"):
        role_labels = _code_output_role_labels(analysis_manifest.get("canonical_code_outputs") or [])
        if role_labels:
            pieces.append(
                "The implemented method package covers "
                + ", ".join(role_labels[:5])
                + "."
            )
        else:
            pieces.append("The implemented method package records stage-owned analysis outputs, so the method narrative remains tied to verified execution rather than unrun design notes.")
    elif isinstance(analysis_manifest, dict) and analysis_manifest.get("method_families"):
        families = [
            _method_role_label(str(item))
            for item in analysis_manifest.get("method_families") or [] if str(item)
        ]
        pieces.append(
            "The verified project-local method implementation covers "
            + ", ".join(families[:8])
            + (", and related validation diagnostics." if len(families) > 8 else ".")
        )
    else:
        pieces.append("No dedicated method-code summary was found, so the method narrative must remain conservative.")
    if formula_count:
        pieces.append("The mathematical specification covers representation, prediction, optimization, validation, and diagnostic metrics where supported by the implemented analysis.")
    else:
        pieces.append("No method formula has been extracted yet; formula-bearing methods should regenerate the method context before final Methods writing.")
    if trace_count:
        pieces.append("Figure-linked summaries are used to align validation metrics and diagnostic quantities with the empirical outputs.")
    return " ".join(pieces)


def _render_method_context_md(context: dict[str, Any]) -> str:
    lines = [
        "# Method Writing Context",
        "",
        "## Narrative Summary",
        "",
        context.get("narrative_summary", ""),
        "",
        "## Analysis Steps",
        "",
        context.get("analysis_steps", ""),
        "",
        "## Data Role",
        "",
        context.get("data_role", ""),
        "",
        "## Method Code and Formula Trace",
        "",
        context.get("code_trace_summary", ""),
        "",
        "## Verification",
        "",
        context.get("verification_summary", ""),
        "",
        "## Claim Boundary",
        "",
        context.get("claim_boundary", ""),
        "",
    ]
    return "\n".join(lines)


def _ast_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _ast_call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _safe_ast_literal(node: ast.AST) -> Any:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None
    if isinstance(value, str) and (re.search(r"[A-Za-z]:[\\/]", value) or value.startswith(("/", "\\\\"))):
        return None
    if isinstance(value, (list, tuple, dict, set)) and len(value) > 40:
        return None
    return value if isinstance(value, (str, int, float, bool, list, tuple, dict, set, type(None))) else None


def _method_reproducibility_contract(project_path: Path) -> dict[str, Any]:
    code_files = sorted({
        *project_path.glob("methods/scripts/**/*.py"),
        *project_path.glob("methods/analysis/**/*.py"),
        *project_path.glob("methods/code/**/*.py"),
    })
    imports: set[str] = set()
    constants: dict[str, Any] = {}
    feature_groups: dict[str, list[str]] = {}
    calls: list[dict[str, Any]] = []
    call_names_seen: set[str] = set()
    for path in code_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value_node = node.value
                value = _safe_ast_literal(value_node) if value_node is not None else None
                for target in targets:
                    if not isinstance(target, ast.Name) or value is None:
                        continue
                    name = target.id
                    lowered = name.lower()
                    if isinstance(value, (list, tuple)) and value and all(isinstance(item, str) for item in value):
                        if any(token in lowered for token in ("feature", "column", "predictor", "covariate", "input")):
                            feature_groups[name] = list(value)
                    elif name.isupper() and name not in {"PROJECT", "RESULTS", "FIGURES", "TABLES"}:
                        constants[name] = value
            elif isinstance(node, ast.Call):
                name = _ast_call_name(node.func).split(".")[-1]
                if not name or name in call_names_seen:
                    continue
                if not (name[:1].isupper() or name.lower().endswith(("split", "score", "metric"))):
                    continue
                kwargs = {}
                for keyword in node.keywords:
                    if keyword.arg:
                        value = _safe_ast_literal(keyword.value)
                        if value is not None:
                            kwargs[keyword.arg] = value
                calls.append({"component": name, "parameters": kwargs})
                call_names_seen.add(name)
    provenance = _read_json(project_path / "methods" / "model_provenance.json", {})
    environment = _read_json(project_path / "methods" / "environment_manifest.json", {})
    splitters = [item for item in calls if any(token in item["component"].lower() for token in ("split", "fold", "kfold"))]
    estimators = [item for item in calls if any(token in item["component"].lower() for token in ("regression", "classifier", "forest", "boost", "svm", "network", "model"))]
    transforms = [item for item in calls if any(token in item["component"].lower() for token in ("imputer", "scaler", "pca", "encoder", "transform"))]
    return {
        "schema_version": "dpl.method_reproducibility_contract.v1",
        "source_file_count": len(code_files),
        "software_modules": sorted(imports),
        "software_versions": environment.get("packages") or environment.get("software_versions") or {},
        "model_provenance": provenance,
        "declared_constants": constants,
        "feature_groups": feature_groups,
        "preprocessing_components": transforms,
        "estimators": estimators,
        "validation_splitters": splitters,
        "all_implemented_components": calls,
        "required_writer_topics": [
            "input and target construction",
            "preprocessing order and train-fold fitting boundary",
            "model or checkpoint provenance",
            "feature groups and exclusions",
            "estimator hyperparameters and convergence",
            "validation splitter, group unit, seeds, and tuning policy",
            "metric aggregation and uncertainty interpretation",
            "software environment or explicitly unavailable version metadata",
            "preprocessing scope for every compared model or pipeline variant",
            "whether the comparison is a nested feature addition or a non-nested pipeline contrast",
        ],
        "comparison_semantics_policy": "Describe a score difference as an incremental or conditional feature contribution only when one variant preserves the other variant's inputs and transformations. Otherwise call it a model- or pipeline-performance contrast and name the differing preprocessing.",
        "policy": "Write only implemented or explicitly unavailable details; never infer missing checkpoint, preprocessing, tuning, software metadata, or nested-comparison semantics.",
    }


def build_method_writing_context(project: str | Path) -> dict[str, Any]:
    """Build a manuscript-facing Methods context from method plan, code manifests, and observations."""
    state = load_project(project)
    manifest = _validate_successful_manifest(state.path)
    requirements = validate_method_plan_for_methods(state.path)
    feasibility = validate_data_feasibility_for_methods(state.path)
    observations = load_observations(state.path, stage="methods")
    analysis_manifest = _read_json(state.path / "methods" / "method_code_manifest.json", {})
    if not analysis_manifest:
        analysis_manifest = _read_json(state.path / "methods" / "analysis_code_manifest.json", {})
    _write_method_formulas(state.path, manifest)
    formula_manifest = _read_json(state.path / "methods" / "method_formula_manifest.json", {})
    executable_analysis_spec = _read_json(state.path / "methods" / "executable_analysis_spec.json", {})
    analysis_formula_ast = _read_json(state.path / "methods" / "analysis_formula_ast.json", {})
    run_selection_policy = _read_json(state.path / "methods" / "run_selection_policy.json", {})
    resampling_contract = _read_json(state.path / "methods" / "resampling_contract.json", {})
    figure_code_trace = _read_json(state.path / "results" / "figure_code_trace.json", {})
    if not figure_code_trace:
        figure_code_trace = _read_json(state.path / "results" / "figure_plugin_trace_report.json", {})
    method_blueprint = _read_json(state.path / "methods" / "method_blueprint.json", {})
    plugin_binding_plan = _read_json(state.path / "research_plan" / "plugin_binding_plan.json", {})
    method_bindings = [
        item for item in plugin_binding_plan.get("bindings") or []
        if isinstance(item, dict) and item.get("kind") == "method" and item.get("state") in {"covered", "covered_project_local"}
    ]
    if method_blueprint and "method_code_plan" not in analysis_manifest:
        analysis_manifest["method_code_plan"] = method_blueprint.get("method_code_plan") or {}
    family_summary = _method_family_text(requirements)
    analysis_steps = _strip_forbidden_paths(_analysis_steps_text(requirements, observations, analysis_manifest))
    binding_families = [str(item.get("requirement_id") or "").split(":")[-1].replace("_", " ") for item in method_bindings]
    if binding_families:
        analysis_steps = _strip_forbidden_paths(
            analysis_steps + " The implemented analysis uses declared method roles for " + ", ".join(dict.fromkeys(binding_families)) + "."
        )
    data_role = _strip_forbidden_paths(_data_role_text(manifest, analysis_manifest))
    code_trace_summary = _strip_forbidden_paths(_method_code_trace_text(analysis_manifest, formula_manifest, figure_code_trace))
    verification_summary = _strip_forbidden_paths(_metrics_text(manifest, requirements))
    claim_boundary = _clean_sentence(feasibility.get("supported_claim_level"))
    if claim_boundary:
        claim_boundary = "Interpretation is bounded by current data support: " + claim_boundary + "."
    else:
        claim_boundary = "Interpretation remains aligned with the available data and validated empirical outputs."
    narrative_summary = " ".join([family_summary, data_role, analysis_steps, code_trace_summary, verification_summary, claim_boundary]).strip()
    context = {
        "project_id": state.metadata.get("project_id"),
        "project_path": str(state.path),
        "method_family_summary": family_summary,
        "data_role": data_role,
        "analysis_steps": analysis_steps,
        "code_trace_summary": code_trace_summary,
        "verification_summary": verification_summary,
        "claim_boundary": claim_boundary,
        "observation_count": len(observations),
        "observations": observations,
        "method_blueprint": method_blueprint,
        "method_plugin_bindings": method_bindings,
        "method_code_manifest": analysis_manifest,
        "formula_manifest": formula_manifest if isinstance(formula_manifest, dict) else {},
        "executable_analysis_spec": executable_analysis_spec,
        "analysis_formula_ast": analysis_formula_ast,
        "run_selection_policy": run_selection_policy,
        "resampling_contract": resampling_contract,
        "figure_code_trace": figure_code_trace if isinstance(figure_code_trace, dict) else {},
        "reproducibility_contract": _method_reproducibility_contract(state.path),
        "narrative_summary": narrative_summary,
        "forbidden_in_manuscript": ["local filesystem paths", "execution commands", "manifest field dumps", "raw output file lists"],
    }
    try:
        context["resolved_result_evidence"] = resolve_result_evidence(state.path)
    except ResultEvidenceError:
        context["resolved_result_evidence"] = {}
    context["scientific_evidence_registry"] = build_scientific_evidence_registry(state.path)
    context["writing_brief"] = build_method_writing_brief(state.path, context)
    context_path = state.path / "methods" / "method_writing_context.json"
    _write_json(context_path, context)
    write_html_report(state.path / "methods" / "method_writing_context.html", _render_method_context_md(context), title="Method Writing Context")
    update_stage_status(state.path, "methods_writing", "draft")
    _set_methods_writing_manifest(state.path)
    return context


def _validate_successful_manifest(project_path: Path) -> dict[str, Any]:
    _ensure_method_plan(project_path)
    try:
        validate_method_plan_for_methods(project_path)
    except MethodPlanError as exc:
        raise MethodsGateError(str(exc)) from exc
    try:
        validate_data_feasibility_for_methods(project_path)
    except DataGateError as exc:
        raise MethodsGateError(str(exc)) from exc
    manifest_path = project_path / "methods" / "run_manifest.yaml"
    if not manifest_path.exists():
        raise MethodsGateError("methods/run_manifest.yaml is required before writing methods.tex.")
    manifest = _read_manifest(manifest_path)
    if manifest.get("status") != "success":
        raise MethodsGateError("methods/run_manifest.yaml must have status=success before writing methods.tex.")
    missing = _missing_declared_outputs(project_path, manifest)
    if missing:
        raise MethodsGateError("Declared method output files are missing: " + ", ".join(missing))
    return manifest


def _render_methods_tex(project_meta: dict[str, Any], manifest: dict[str, Any], context: dict[str, Any]) -> str:
    brief = context.get("writing_brief") if isinstance(context.get("writing_brief"), dict) else {}
    stage_briefs = brief.get("stage_briefs") if isinstance(brief.get("stage_briefs"), list) else []
    stage_goals = [
        _drop_internal_method_sentences(item.get("writing_goal"))
        for item in stage_briefs[:6]
        if isinstance(item, dict) and item.get("writing_goal")
    ]
    data_role_raw = _drop_internal_method_sentences(context.get("data_role", ""))
    analysis_steps_raw = _drop_internal_method_sentences(context.get("analysis_steps", ""))
    verification_raw = _drop_internal_method_sentences(context.get("verification_summary", ""))
    code_trace_raw = _drop_internal_method_sentences(context.get("code_trace_summary", ""))
    boundary_raw = _drop_internal_method_sentences(context.get("claim_boundary", ""))
    family_raw = _drop_internal_method_sentences(context.get("method_family_summary", ""))
    formula_entries = _latex_formula_entries(context)
    section_profile = _section_profile_for_methods(context, formula_entries)
    step_tokens = _formula_step_tokens(formula_entries)
    project_path = context.get("project_path")
    citation_paragraphs: list[str] = []
    if project_path:
        existing = "\n\n".join([family_raw, data_role_raw, analysis_steps_raw, verification_raw, boundary_raw])
        citation_paragraphs = _method_citation_paragraphs(Path(str(project_path)), existing)

    introduction = _safe_latex_text(
        " ".join(
            part for part in [
                family_raw,
                data_role_raw,
                section_profile["bridge"],
            ] if part
        )
    )
    stage_sentence = " ".join(stage_goals[:3])
    design = _safe_latex_text(
        " ".join(
            part for part in [
                analysis_steps_raw,
                stage_sentence,
                "Data construction, feature representation, model fitting, and validation are therefore treated as linked parts of the same empirical test rather than as separate bookkeeping steps.",
            ] if part
        )
    )
    trace = _safe_latex_text(code_trace_raw) if code_trace_raw else ""
    model_formula_block = _render_formula_block(
        formula_entries,
        only_steps={"temporal", "sequence", "feature", "prediction", "optimization", "model", "softmax", "classifier", "loss"},
    )
    validation_formula_block = _render_formula_block(
        formula_entries,
        only_steps={"validation", "metric", "ablation", "classification", "association", "pearson", "correlation", "auc"},
    )
    if not model_formula_block and formula_entries:
        split = max(1, len(formula_entries) // 2)
        model_formula_block = _render_formula_block(formula_entries[:split])
    if not validation_formula_block and len(formula_entries) > 1:
        split = max(1, len(formula_entries) // 2)
        validation_formula_block = _render_formula_block(formula_entries[split:])
    if model_formula_block:
        model_formula_block = "\n\n" + model_formula_block
    if validation_formula_block:
        validation_formula_block = "\n\n" + validation_formula_block
    citation_block = ""
    if citation_paragraphs:
        citation_block = "\n\n" + "\n\n".join(citation_paragraphs)
    representation_sentence = "Sequence or temporal representations are defined explicitly because the ordering, cadence, and masking of observations affect the information available to the model."
    if "sequence" not in step_tokens:
        representation_sentence = "Feature construction is described before model fitting so that the input variables and claim boundary remain clear."
    if stage_goals:
        representation_sentence += " " + " ".join(stage_goals[3:5])
    validation_sentence = "Validation uses the verified outputs and declared metrics to determine whether the fitted model supports the planned empirical comparison."
    if stage_goals[5:]:
        validation_sentence += " " + " ".join(stage_goals[5:])
    if boundary_raw:
        validation_sentence += " " + boundary_raw
    if verification_raw:
        validation_sentence += " " + verification_raw
    return (
        "\\section{Methods}\n"
        f"{introduction}\n\n"
        f"\\subsection{{{section_profile['design']}}}\n"
        f"{design} {trace}\n\n"
        f"\\subsection{{{section_profile['model']}}}\n"
        f"{_safe_latex_text(representation_sentence)}{model_formula_block}{citation_block}\n\n"
        f"\\subsection{{{section_profile['validation']}}}\n"
        f"{_safe_latex_text(validation_sentence.replace('verified outputs and declared metrics', 'held-out evaluation outputs and model metrics'))}{validation_formula_block}\n"
    )


def _set_methods_manifest(project_path: Path) -> None:
    manifest_path = project_path / "methods" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = METHOD_INPUTS
    manifest["output_files"] = ["methods/run_manifest.yaml", "methods/method_formula_manifest.json", "methods/method_formulas.tex"]
    _write_json(manifest_path, manifest)


def _set_methods_writing_manifest(project_path: Path) -> None:
    manifest_path = project_path / "methods_writing" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = METHOD_WRITING_INPUTS + ["results/results.tex", "core_evidence/core_evidence_report.json"]
    manifest["output_files"] = METHOD_OUTPUTS
    _write_json(manifest_path, manifest)


def write_methods(project: str | Path) -> dict[str, Any]:
    """Write methods.tex only if methods/run_manifest.yaml proves a successful run."""
    state = load_project(project)
    from ..manuscript_revision import assert_writer_may_replace_section
    assert_writer_may_replace_section(state.path, "methods")
    ensure_registry_consistent(state.path)
    manifest = _validate_successful_manifest(state.path)
    context = build_method_writing_context(state.path)
    methods_dir = state.path / "methods"
    output_path = methods_dir / "methods.tex"
    fallback = _render_methods_tex(state.metadata, manifest, context)
    try:
        composition = select_validated_section_draft(state.path, "methods", fallback)
    except SectionCompositionError as exc:
        raise MethodsGateError(str(exc)) from exc
    output_path.write_text(str(composition["text"]), encoding="utf-8")
    update_stage_status(state.path, "methods_writing", "draft")
    _set_methods_writing_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "methods": str(output_path),
        "run_manifest": str(methods_dir / "run_manifest.yaml"),
        "outputs": METHOD_OUTPUTS,
    }
