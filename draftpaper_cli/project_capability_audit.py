# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Audit apparent plugin gaps against stage-owned project-local capabilities."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import utc_now
from .project_state import load_project, update_stage_status


SUFFICIENCY_REPORT = "research_plan/plugin_sufficiency_report.json"
BINDING_PLAN = "research_plan/plugin_binding_plan.json"
AUDIT_JSON = "research_plan/project_capability_audit.json"
AUDIT_HTML = "research_plan/project_capability_audit.html"
CODE_ACCEPTANCE_JSON = "methods/project_local_code_acceptance.json"

ROLE_TERMS = {
    "label": {"label", "class", "category", "target", "source_class"},
    "light_curve": {"light_curve", "lightcurve", "history_lc", "time_series", "mjd", "rate"},
    "spectral_features": {"spectral", "hardness", "pha", "arf", "rmf", "spectrum"},
    "multiwavelength_features": {"multiwavelength", "multi_wavelength", "multiband", "counterpart", "crossmatch", "catalog_match"},
    "multimodal_learning": {"multimodal", "fusion", "transformer", "token", "timeaware", "time_aware"},
    "modality_availability": {"dataset_quality", "completeness", "inventory", "availability", "token", "spectrum"},
    "class_balance_check": {"class_balance", "class_count", "label", "category", "value_counts"},
    "feature_space_diagnostic": {"feature_space", "feature", "spectral", "importance", "embedding"},
    "baseline_model": {"baseline", "dummy", "logistic", "random_forest", "majority"},
    "cohort_flow_audit": {"cohort", "source_catalog", "image_available", "analysis_cohort"},
    "missingness_analysis": {"missing", "cutout_exists", "image_available", "exclusion"},
    "representation_projection": {"projection", "pca", "explained_variance", "embedding"},
    "target_confounder_diagnostic": {"redshift", "morphtype", "target", "luminosity"},
    "group_aware_validation": {"group", "fold", "leakage", "stratifiedgroupkfold"},
    "transparent_baseline_comparison": {"catalog_only", "embedding_only", "combined", "baseline"},
    "uncertainty_estimation": {"standard deviation", "bootstrap", "interval", "std"},
    "feature_group_ablation": {"catalog_only", "embedding_only", "combined", "incremental"},
    "confounder_control": {"confounder", "redshift", "luminosity", "acquisition"},
    "label_leakage_check": {"label leakage", "identifier exclusion", "label-defining"},
    "confusion_or_error_analysis": {"confusion_matrix", "true_label", "predicted_label", "out-of-fold"},
    "class_imbalance_analysis": {"class_weight", "balanced", "class support", "class_f1"},
    "uncertainty_summary": {"calibration", "brier", "confidence", "reliability"},
    "anomaly_stability_analysis": {"anomaly", "resampling", "preprocessing", "reference cohort"},
    "image_quality_review": {"image_quality_failure", "quality_failure_reason", "unreadable_cutout"},
    "candidate_interpretation_boundary": {"candidate", "quality_filtered", "claim_boundary", "independent confirmation"},
    "cohort_accounting_reconciliation": {"source_catalog", "image_available", "embedding_valid", "analysis_cohort"},
    "selection_missingness_analysis": {"missingness", "missing_rate", "covariate", "cutout_exists", "logistic"},
    "morphology_state_association": {"adaptive_label", "color_gr", "abs_mag_r", "morphtype"},
    "representation_projection": {"pca", "projection", "explained_variance_ratio"},
    "image_level_validation": {"representative", "cutout", "gradient"},
    "confounder_adjusted_association": {"confounder_only", "embedding_plus_confounders", "representation_increment_over_confounders"},
    "stratified_bootstrap": {"bootstrap", "group", "incremental_macro_f1"},
    "label_definition_audit": {"label_defining_columns", "deterministic_label_proxy", "direct_label_or_label_defining_variable"},
    "stratified_population_analysis": {"population", "redshift", "luminosity", "stratum"},
    "interaction_estimation": {"interaction", "redshift", "luminosity"},
    "selection_sensitivity_analysis": {"selection", "weight", "support_restriction"},
    "transition_population_analysis": {"green_valley", "transition", "physical_state"},
    "image_catalog_discordance_analysis": {"discordance", "morphtype", "adaptive_label"},
    "uncertainty_resampling": {"resampling", "group_difference", "interval"},
}

ROLE_MIN_MATCHES = {
    "cohort_accounting_reconciliation": 4,
    "selection_missingness_analysis": 3,
    "morphology_state_association": 3,
    "representation_projection": 2,
    "image_level_validation": 3,
    "confounder_adjusted_association": 3,
    "stratified_bootstrap": 3,
    "label_definition_audit": 3,
    "stratified_population_analysis": 3,
    "interaction_estimation": 3,
    "selection_sensitivity_analysis": 3,
    "transition_population_analysis": 3,
    "image_catalog_discordance_analysis": 3,
    "uncertainty_resampling": 3,
}

DATA_ROLE_COVERAGE_ALIASES = {
    "source_catalog": {"source_catalog"},
    "image_availability": {"image_or_raster_data", "missingness_reason"},
    "valid_image_cohort": {"image_or_raster_data", "features"},
    "missingness_reason": {"missingness_reason"},
    "image_embedding": {"features"},
    "independent_target": {"label_or_response"},
    "confounder_variables": {"confounder_variables"},
    "group_validation_split": {"sample_group", "validation_design"},
    "class_label": {"label_or_response"},
    "catalog_baseline_features": {"tabular_data", "confounder_variables"},
    "image_cutout": {"image_or_raster_data"},
    "quality_flags": {"quality_flags"},
    "image_validity": {"image_or_raster_data", "quality_flags"},
    "embedding_membership": {"features"},
    "selection_covariates": {"confounder_variables"},
    "continuous_colour_magnitude_observables": {"mag_g", "mag_r", "mag_z", "color_gr", "color_rz", "abs_mag_r", "color_w1w2"},
    "continuous_color_magnitude_observables": {"mag_g", "mag_r", "mag_z", "color_gr", "color_rz", "abs_mag_r", "color_w1w2"},
    "catalog_profile_morphology": {"label_or_response"},
    "physical_state_proxy": {"label_or_response"},
    "continuous_physical_observables": {"confounder_variables"},
    "redshift": {"z"},
    "absolute_magnitude": {"abs_mag_r"},
    "apparent_magnitude": {"mag_r"},
    "observed_colours": {"photometric_colours"},
    "observed_colors": {"photometric_colours"},
    "calibration_bins": {"prediction_score"},
    "image_quality_flags": {"quality_flags"},
    "group_id": {"sample_group"},
    "proxy_label_definition": {"label_or_response", "confounder_variables"},
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _role_for(requirement: dict[str, Any]) -> str:
    return str(requirement.get("role") or requirement.get("method_family") or "").strip().lower()


def _candidate_files(project_path: Path, kind: str) -> list[Path]:
    roots = [project_path / "data" / "raw", project_path / "data" / "processed"] if kind == "data" else [project_path / "methods" / "scripts", project_path / "methods" / "src", project_path / "data" / "scripts", project_path / "code" / "src"]
    suffixes = {".csv", ".tsv", ".json"} if kind == "data" else {".py"}
    files = []
    for root in roots:
        if root.exists():
            files.extend(
                path for path in root.rglob("*")
                if path.is_file()
                and path.suffix.lower() in suffixes
                and "__pycache__" not in path.parts
                and path.name not in {"generated_pipeline.py", "scientific_plotting.py", "install_plotting_requirements.py"}
            )
    if kind == "method":
        files.extend(_verified_lineage_method_files(project_path))
    return sorted(set(files))


def _verified_lineage_method_files(project_path: Path) -> list[Path]:
    ledger = _read_json(project_path / "lineage" / "import_ledger.json")
    project = _read_json(project_path / "project.json")
    lineage = project.get("lineage") if isinstance(project.get("lineage"), dict) else {}
    if (
        ledger.get("status") != "imported"
        or str(ledger.get("project_id") or "") != str(project.get("project_id") or "")
        or str(ledger.get("source_project_id") or "") != str(lineage.get("parent_project_id") or "")
    ):
        return []
    verified = []
    for event in ledger.get("events") or []:
        if not isinstance(event, dict) or event.get("state") != "imported":
            continue
        relative = str(event.get("target_path") or "").replace("\\", "/")
        if not relative.startswith(("lineage/imported_code/methods/", "lineage/imported_code/data/")) or not relative.endswith(".py"):
            continue
        if any(part in relative for part in ("/__pycache__/", "/tests/", "/.pytest_cache/")):
            continue
        path = project_path / Path(relative)
        if path.is_file() and event.get("sha256") and _sha256(path) == str(event.get("sha256")):
            verified.append(path)
    return verified


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")[:100000].lower()
    except OSError:
        return ""


def _matches(requirement: dict[str, Any], path: Path) -> tuple[int, list[str]]:
    role = _role_for(requirement)
    terms = ROLE_TERMS.get(role, {part for part in role.replace("_", " ").split() if part})
    text = f"{path.name.lower()} {_text(path)}"
    if role == "confounder_control" and "no acquisition-condition confounder ablation is claimed" in text:
        return 0, []
    if role == "label_leakage_check" and not re.search(r"(?:label.{0,60}leak|leak.{0,60}label|identifier.{0,60}exclu)", text):
        return 0, []
    if role == "uncertainty_summary" and not any(term in text for term in ("calibration", "brier", "reliability")):
        return 0, []
    if role == "anomaly_stability_analysis" and (
        "not resampling stability" in text
        or not all(term in text for term in ("anomaly", "resampling", "preprocessing"))
    ):
        return 0, []
    matched = sorted(term for term in terms if term in text)
    minimum = ROLE_MIN_MATCHES.get(role)
    if minimum is not None and len(matched) < minimum:
        return 0, matched
    if requirement.get("kind") == "method" and role == "multimodal_learning":
        valid = ("fusion" in matched and "transformer" in matched) or "multimodal" in matched
        return (len(matched) if valid else 0), matched
    score = len(matched)
    if requirement.get("kind") == "method" and path.name.lower().startswith(("train_", "fit_", "run_")):
        score += 2
    return score, matched


def _binding(requirement: dict[str, Any], evidence: Path, matched_terms: list[str], score: int, project_path: Path) -> dict[str, Any]:
    role = _role_for(requirement)
    lineage_import = "lineage" in evidence.relative_to(project_path).parts and "imported_code" in evidence.relative_to(project_path).parts
    return {
        "requirement_id": requirement.get("requirement_id"),
        "figure_id": requirement.get("figure_id"),
        "kind": requirement.get("kind"),
        "plugin_id": f"project_local:{role}",
        "binding_scope": "project_local",
        "state": "covered_project_local",
        "coverage_basis": "verified_lineage_import" if lineage_import else "stage_owned_project_asset",
        "runtime_class": "project_local_verified_asset",
        "validation_level": "lineage_hash_and_semantic_audited" if lineage_import else "project_asset_audited",
        "evidence": {
            "path": str(evidence.relative_to(project_path)).replace("\\", "/"),
            "sha256": _sha256(evidence),
            "matched_terms": matched_terms,
            "match_score": score,
        },
        "promotion_policy": "project_local_only; run candidate generalization and explicit promotion separately before any discipline-module write",
    }


def _coverage_binding(
    requirement: dict[str, Any],
    project_path: Path,
    coverage: dict[str, Any],
) -> dict[str, Any] | None:
    if requirement.get("kind") != "data" or requirement.get("data_role_class") == "derived_method_output":
        return None
    role = _role_for(requirement)
    from .data_contracts import normalize_role

    normalized_role = normalize_role(role)
    required_roles = DATA_ROLE_COVERAGE_ALIASES.get(role, {normalized_role or role})
    available = {str(item).strip().lower() for item in coverage.get("available_roles") or [] if str(item).strip()}
    # Coverage is evaluated per requirement. One genuinely missing role (for
    # example a literature-derived interval) must not invalidate unrelated
    # project-local roles already verified by the same inventory.
    if not required_roles.issubset(available):
        return None
    evidence = project_path / "data" / "data_role_coverage_report.json"
    inventory = project_path / "data" / "data_inventory.json"
    if not evidence.is_file() or not inventory.is_file():
        return None
    return {
        "requirement_id": requirement.get("requirement_id"),
        "figure_id": requirement.get("figure_id"),
        "kind": "data",
        "plugin_id": f"project_local:{role}",
        "binding_scope": "project_local",
        "state": "covered_project_local",
        "coverage_basis": "verified_data_role_coverage",
        "runtime_class": "project_local_verified_asset",
        "validation_level": "inventory_and_role_contract_verified",
        "evidence": {
            "path": "data/data_role_coverage_report.json",
            "sha256": _sha256(evidence),
            "inventory_path": "data/data_inventory.json",
            "inventory_sha256": _sha256(inventory),
            "matched_roles": sorted(required_roles),
            "match_score": len(required_roles),
        },
        "promotion_policy": "project_local_only; validate the method run before treating derived outputs as evidence",
    }


def _render(report: dict[str, Any]) -> str:
    lines = ["# Project Capability Audit", "", f"Decision: `{report.get('decision')}`", ""]
    for item in report.get("assessments") or []:
        evidence = (item.get("binding") or {}).get("evidence") or {}
        lines.append(f"- `{item.get('requirement_id')}`: **{item.get('state')}**; evidence: `{evidence.get('path') or 'none'}`")
    return "\n".join(lines)


def audit_project_capabilities(project: str | Path) -> dict[str, Any]:
    """Resolve missing capability requirements from local stage-owned evidence only."""
    state = load_project(project)
    sufficiency = _read_json(state.path / SUFFICIENCY_REPORT)
    assessments = list(sufficiency.get("requirement_assessments") or [])
    bindings_payload = _read_json(state.path / BINDING_PLAN)
    bindings = [item for item in bindings_payload.get("bindings") or [] if isinstance(item, dict)]
    coverage = _read_json(state.path / "data" / "data_role_coverage_report.json")
    audit_items = []
    for requirement in assessments:
        if not isinstance(requirement, dict) or requirement.get("kind") not in {"data", "method"} or requirement.get("state") not in {"missing", "partially_covered", "audit_required", "execution_required", "covered_project_local", "true_missing", "project_method_implementation_required", "project_data_implementation_required"}:
            continue
        coverage_binding = _coverage_binding(requirement, state.path, coverage)
        if coverage_binding:
            requirement.update({
                "state": "covered_project_local",
                "matched_plugin_id": coverage_binding["plugin_id"],
                "binding_scope": "project_local",
                "coverage_basis": coverage_binding["coverage_basis"],
                "project_local_evidence": coverage_binding["evidence"],
            })
            bindings = [item for item in bindings if item.get("requirement_id") != coverage_binding["requirement_id"]]
            bindings.append(coverage_binding)
            audit_items.append({"requirement_id": requirement.get("requirement_id"), "state": "covered_project_local", "binding": coverage_binding})
            continue
        candidates = []
        for path in _candidate_files(state.path, str(requirement["kind"])):
            score, terms = _matches(requirement, path)
            if score:
                candidates.append((score, path, terms))
        candidates.sort(key=lambda item: (-item[0], str(item[1])))
        if candidates:
            score, evidence, terms = candidates[0]
            binding = _binding(requirement, evidence, terms, score, state.path)
            requirement.update({
                "state": "covered_project_local",
                "matched_plugin_id": binding["plugin_id"],
                "binding_scope": "project_local",
                "coverage_basis": binding["coverage_basis"],
                "project_local_evidence": binding["evidence"],
            })
            bindings = [item for item in bindings if item.get("requirement_id") != binding["requirement_id"]]
            bindings.append(binding)
            audit_items.append({"requirement_id": requirement.get("requirement_id"), "state": "covered_project_local", "binding": binding})
        else:
            unresolved_state = (
                "project_method_implementation_required"
                if requirement.get("kind") == "method"
                else "project_data_implementation_required"
            )
            requirement["state"] = unresolved_state
            bindings = [item for item in bindings if item.get("requirement_id") != requirement.get("requirement_id")]
            audit_items.append({"requirement_id": requirement.get("requirement_id"), "state": unresolved_state, "binding": None})
    core_unresolved = [
        item for item in assessments
        if isinstance(item, dict)
        and item.get("core")
        and item.get("kind") in {"data", "method"}
        and item.get("state") not in {"covered", "covered_project_local", "method_output_pending"}
    ]
    sufficiency["requirement_assessments"] = assessments
    method_implementation = [item for item in core_unresolved if item.get("state") == "project_method_implementation_required"]
    data_implementation = [item for item in core_unresolved if item.get("state") == "project_data_implementation_required"]
    sufficiency["decision"] = "project_implementation_required" if method_implementation or data_implementation else "pass"
    sufficiency["core_figure_decision"] = sufficiency["decision"]
    sufficiency["rescue_tasks"] = [
        {
            "requirement_id": item.get("requirement_id"),
            "kind": item.get("kind"),
            "figure_id": item.get("figure_id"),
            "state": item.get("state"),
            "reason": "The verified project-local assets do not yet implement the complete contracted capability.",
            "recommended_command": (
                "prepare-project-method-implementation"
                if item.get("kind") == "method"
                else "prepare-data-acquisition"
            ),
            "search_scope": {
                "discipline": item.get("discipline"),
                "role": item.get("role") or item.get("method_family"),
            },
        }
        for item in core_unresolved
    ]
    bindings_payload.update({"status": "written", "generated_at": utc_now(), "bindings": bindings})
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "research_capability_contract_sha256": sufficiency.get("research_capability_contract_sha256") or "",
        "source_sufficiency_generated_at": sufficiency.get("generated_at") or "",
        "decision": sufficiency["decision"],
        "project_method_implementation_required": [item.get("requirement_id") for item in method_implementation],
        "project_data_implementation_required": [item.get("requirement_id") for item in data_implementation],
        "assessments": audit_items,
        "unresolved_requirement_ids": [item.get("requirement_id") for item in core_unresolved],
        "policy": "Project-local bindings are auditable only within this project. They do not create a discipline plugin, alter a global manifest, or bypass candidate validation and explicit promotion.",
    }
    accepted_method_bindings = [
        item for item in bindings
        if item.get("kind") == "method"
        and item.get("state") == "covered_project_local"
        and isinstance(item.get("evidence"), dict)
        and str((item.get("evidence") or {}).get("path") or "").endswith(".py")
    ]
    if report["decision"] == "pass" and accepted_method_bindings:
        figure_plan = state.path / "results" / "figure_plan.json"
        acceptance = {
            "schema_version": "dpl.project_local_code_acceptance.v1",
            "status": "accepted_for_verification",
            "generated_at": utc_now(),
            "figure_plan_sha256": _sha256(figure_plan) if figure_plan.is_file() else None,
            "binding_plan_semantic_sha256": hashlib.sha256(
                json.dumps(bindings_payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "method_bindings": accepted_method_bindings,
            "policy": "Project-local code may satisfy the current code stage only after all core capability requirements are covered. verify-methods must still execute it and validate declared outputs.",
        }
        _write_json(state.path / CODE_ACCEPTANCE_JSON, acceptance)
        report["code_stage_accepted"] = True
        report["code_acceptance_receipt"] = CODE_ACCEPTANCE_JSON
    else:
        report["code_stage_accepted"] = False
    _write_json(state.path / SUFFICIENCY_REPORT, sufficiency)
    _write_json(state.path / BINDING_PLAN, bindings_payload)
    _write_json(state.path / AUDIT_JSON, report)
    write_html_report(state.path / AUDIT_HTML, _render(report), title="Project Capability Audit")
    if report["code_stage_accepted"]:
        update_stage_status(state.path, "code", "draft")
    return {"status": "written", "project_path": str(state.path), "decision": report["decision"], "covered_project_local": sum(item.get("state") == "covered_project_local" for item in audit_items), "unresolved_count": len(core_unresolved), "report": AUDIT_JSON}
