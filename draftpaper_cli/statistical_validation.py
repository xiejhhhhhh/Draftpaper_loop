"""Task-aware statistical validation contracts and review-rule coverage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .discipline import infer_discipline_profile
from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .review_rule_runtime import load_discipline_review_rules


CONTRACT_JSON = "research_plan/statistical_validation_contract.json"
CONTRACT_MD = "research_plan/statistical_validation_contract.md"
COVERAGE_JSON = "research_plan/review_rule_coverage_report.json"
COVERAGE_HTML = "research_plan/review_rule_coverage_report.html"


class StatisticalValidationError(RuntimeError):
    """Raised when a statistical validation contract cannot be built."""


_FAMILY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "sampling_and_independence": {
        "question": "Are the sampling unit, cohort, repeated observations, and dependence structure explicitly defined?",
        "evidence": ["cohort_definition", "sample_unit", "split_or_sampling_design"],
        "preferred_rules": ["experimental_design_gate", "statistical_assumption_gate"],
    },
    "missingness_and_selection": {
        "question": "Are missingness, exclusions, selection effects, and analysis-cohort construction quantified?",
        "evidence": ["cohort_flow", "missingness_summary", "exclusion_reasons"],
        "preferred_rules": ["peer_review_evidence_gate", "nature_reporting_completeness_gate"],
    },
    "uncertainty_reporting": {
        "question": "Are effect or performance estimates accompanied by uncertainty at the correct sampling level?",
        "evidence": ["point_estimate", "uncertainty_interval", "resampling_unit"],
        "preferred_rules": ["statistical_power_gate", "peer_review_evidence_gate"],
    },
    "classification_validation": {
        "question": "Are discrimination, class-wise performance, imbalance, and held-out generalization evaluated together?",
        "evidence": ["held_out_predictions", "class_support", "classwise_metrics", "confusion_matrix"],
        "preferred_rules": ["model_statistical_validity_gate", "baseline_ablation_gate"],
    },
    "calibration": {
        "question": "Are prediction scores calibrated and interpreted as probabilities only when calibration evidence exists?",
        "evidence": ["calibration_curve", "calibration_metric", "held_out_predictions"],
        "preferred_rules": ["clinical_model_calibration_gate", "model_statistical_validity_gate"],
    },
    "group_leakage_and_generalization": {
        "question": "Do train and test partitions respect source, subject, spatial, temporal, or acquisition groups?",
        "evidence": ["group_id", "fold_assignments", "leakage_audit"],
        "preferred_rules": ["subject_leakage_gate", "clinical_data_leakage_gate", "baseline_ablation_gate"],
    },
    "baseline_and_ablation": {
        "question": "Are the proposed model, transparent baselines, and ablations compared on identical cohorts and splits?",
        "evidence": ["baseline_metrics", "ablation_metrics", "matched_split_id"],
        "preferred_rules": ["baseline_ablation_gate", "classical_baseline_gate"],
    },
    "regression_fit_diagnostics": {
        "question": "Are fit quality, residual structure, heteroscedasticity, influence, and parameter uncertainty reported?",
        "evidence": ["fit_metrics", "residual_diagnostics", "parameter_uncertainty"],
        "preferred_rules": ["model_statistical_validity_gate", "statistical_assumption_gate"],
    },
    "multiple_testing": {
        "question": "Are multiplicity and false-discovery control addressed when many hypotheses or features are tested?",
        "evidence": ["hypothesis_count", "adjustment_method", "adjusted_significance"],
        "preferred_rules": ["multiple_testing_fdr_gate", "multiple_comparison_gate"],
    },
    "spatial_validation": {
        "question": "Are spatial dependence, coordinate reference, and blocked or external spatial validation addressed?",
        "evidence": ["spatial_group", "crs", "spatial_validation_result"],
        "preferred_rules": ["crs_consistency_gate", "spatial_unit_alignment_gate", "local_spatial_coverage_gate"],
    },
    "temporal_validation": {
        "question": "Does validation respect temporal order, cadence, autocorrelation, and future-information boundaries?",
        "evidence": ["time_index", "temporal_split", "temporal_leakage_audit"],
        "preferred_rules": ["time_system_declaration_gate", "statistical_assumption_gate"],
    },
    "representation_confounding": {
        "question": "Is representation structure separated from labels, identifiers, selection variables, and measured confounders?",
        "evidence": ["embedding", "independent_target", "confounder_diagnostics", "identifier_exclusion"],
        "preferred_rules": ["baseline_ablation_gate", "peer_review_evidence_gate"],
    },
    "anomaly_stability": {
        "question": "Are anomaly rankings stable across seeds, preprocessing choices, and reference cohorts?",
        "evidence": ["candidate_scores", "seed_stability", "quality_flags", "independent_review_boundary"],
        "preferred_rules": ["rigor_reviewer_reproducibility_gate", "peer_review_evidence_gate"],
    },
    "survival_validation": {
        "question": "Are censoring, time origin, proportionality, discrimination, and calibration handled correctly?",
        "evidence": ["censoring_definition", "time_origin", "survival_metrics"],
        "preferred_rules": ["survival_censoring_gate", "clinical_endpoint_definition_gate"],
    },
    "simulation_convergence": {
        "question": "Are numerical convergence, boundary conditions, dimensional consistency, and uncertainty demonstrated?",
        "evidence": ["convergence_trace", "boundary_conditions", "unit_check"],
        "preferred_rules": ["simulation_convergence_gate", "dimension_consistency_gate"],
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _context(project_path: Path, blueprint: dict[str, Any]) -> str:
    state = load_project(project_path)
    parts = [str(state.metadata.get(key) or "") for key in ("idea", "field", "title")]
    parts.append(json.dumps(blueprint, ensure_ascii=False))
    return " ".join(parts).lower()


def _task_families(text: str, profile: dict[str, Any]) -> list[str]:
    families = ["sampling_and_independence", "missingness_and_selection", "uncertainty_reporting"]

    def add(value: str) -> None:
        if value not in families:
            families.append(value)

    if any(term in text for term in ("classif", "classifier", "f1", "auc", "confusion", "label")):
        add("classification_validation")
        add("group_leakage_and_generalization")
        add("baseline_and_ablation")
        add("calibration")
    if any(term in text for term in ("regression", "r2", "fit", "fitting", "residual", "parameter")):
        add("regression_fit_diagnostics")
    if any(term in text for term in ("multiple testing", "fdr", "many features", "differential")):
        add("multiple_testing")
    disciplines = {str(profile.get("primary_discipline") or ""), *(str(item) for item in profile.get("secondary_disciplines") or [])}
    if "geography" in disciplines or any(term in text for term in ("spatial", "geographic", "raster", "ndvi", "tile")):
        add("spatial_validation")
        add("group_leakage_and_generalization")
    if any(term in text for term in ("time series", "temporal", "light curve", "longitudinal", "cadence")):
        add("temporal_validation")
        add("group_leakage_and_generalization")
    if any(term in text for term in ("embedding", "representation", "dinov2", "latent", "umap", "pca")):
        add("representation_confounding")
    if any(term in text for term in ("anomaly", "outlier", "candidate discovery")):
        add("anomaly_stability")
    if any(term in text for term in ("survival", "censor", "hazard", "kaplan")):
        add("survival_validation")
    if any(term in text for term in ("simulation", "solver", "quantum", "fluid", "convergence")):
        add("simulation_convergence")
    return families


def _validation_items(families: list[str]) -> list[dict[str, Any]]:
    items = []
    for index, family in enumerate(families, start=1):
        definition = _FAMILY_DEFINITIONS[family]
        items.append({
            "validation_id": f"stat_{index:02d}_{family}",
            "rule_family": family,
            "review_question": definition["question"],
            "required_evidence_roles": definition["evidence"],
            "preferred_review_rule_ids": definition["preferred_rules"],
            "threshold_policy": {
                "mode": "source_bound_contextual",
                "source_precedence": ["user_or_journal", "cited_domain_standard", "validated_discipline_plugin", "advisory_only"],
                "universal_fixed_threshold_forbidden": True,
            },
            "blocking_policy": "May block only when the threshold source, cohort, sample unit, run, and evidence fields are all bound.",
        })
    return items


def _render_contract(contract: dict[str, Any]) -> str:
    lines = [
        "# Statistical Validation Contract",
        "",
        f"Primary discipline: `{contract['discipline_profile'].get('primary_discipline')}`",
        "",
        "## Validation Families",
        "",
    ]
    for item in contract["validations"]:
        lines.extend([
            f"### {item['rule_family']}",
            "",
            item["review_question"],
            "",
            "Required evidence: " + ", ".join(item["required_evidence_roles"]),
            "",
        ])
    lines.extend([
        "## Threshold Policy",
        "",
        "No universal F1, R2, p-value, fit-accuracy, or model-performance threshold is valid across all projects. Hard thresholds require an explicit user/journal source, a cited domain standard, or a validated discipline plugin with matching evidence.",
        "",
    ])
    return "\n".join(lines)


def build_statistical_validation_contract(project: str | Path, *, blueprint: dict[str, Any] | None = None) -> dict[str, Any]:
    state = load_project(project)
    payload = blueprint or _read_json(state.path / "research_plan" / "research_blueprint.json")
    if not payload:
        raise StatisticalValidationError("research_plan/research_blueprint.json is required.")
    profile = infer_discipline_profile(state.path)
    families = _task_families(_context(state.path, payload), profile)
    contract = {
        "schema_version": "dpl.statistical_validation_contract.v1",
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "discipline_profile": profile,
        "task_families": families,
        "validations": _validation_items(families),
        "threshold_source_precedence": ["user_or_journal", "cited_domain_standard", "validated_discipline_plugin", "advisory_only"],
        "policy": "Statistical design is fixed before key-figure execution and reviewed again against Results prose after execution.",
    }
    _write_json(state.path / CONTRACT_JSON, contract)
    (state.path / CONTRACT_MD).write_text(_render_contract(contract), encoding="utf-8")
    return {"status": "written", "project_path": str(state.path), "contract": CONTRACT_JSON, "task_families": families, "validation_count": len(contract["validations"])}


def bind_statistical_validations_to_storyboard(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    contract = _read_json(state.path / CONTRACT_JSON)
    storyboard = _read_json(state.path / "research_plan" / "figure_storyboard.json")
    blueprint = _read_json(state.path / "research_plan" / "research_blueprint.json")
    if not contract or not storyboard:
        raise StatisticalValidationError("Statistical contract and figure storyboard are required before binding.")
    validations = [item for item in contract.get("validations") or [] if isinstance(item, dict)]
    generic_ids = [str(item.get("validation_id")) for item in validations if item.get("rule_family") in {"sampling_and_independence", "missingness_and_selection", "uncertainty_reporting"}]
    for figure in storyboard.get("figures") or []:
        if not isinstance(figure, dict):
            continue
        blob = " ".join(str(figure.get(key) or "") for key in ("research_question", "expected_finding", "proposed_title", "validation_metric")).lower()
        selected = list(generic_ids)
        for item in validations:
            family = str(item.get("rule_family") or "")
            tokens = [token for token in family.split("_") if len(token) > 4]
            if any(token in blob for token in tokens):
                selected.append(str(item.get("validation_id")))
        if not selected and validations:
            selected.append(str(validations[0].get("validation_id")))
        figure["statistical_validation_ids"] = list(dict.fromkeys(selected))
    blueprint["figure_storyboard"] = storyboard
    blueprint["statistical_validation_contract"] = contract
    _write_json(state.path / "research_plan" / "figure_storyboard.json", storyboard)
    _write_json(state.path / "research_plan" / "research_blueprint.json", blueprint)
    return {"status": "written", "project_path": str(state.path), "figure_count": len(storyboard.get("figures") or [])}


def _rule_ids(project_path: Path) -> set[str]:
    loaded = load_discipline_review_rules(project_path)
    return {
        str(item.get("rule_id") or item.get("rule_group_id") or "")
        for item in loaded.get("review_rules") or []
        if isinstance(item, dict)
    }


def _render_coverage(report: dict[str, Any]) -> str:
    lines = ["# Review-rule Coverage", "", f"Decision: `{report['decision']}`", "", "## Statistical Families", ""]
    for item in report["family_coverage"]:
        lines.append(f"- `{item['rule_family']}`: {item['status']} ({', '.join(item['matched_rule_ids']) or 'no matching rule'})")
    if report["missing_rule_families"]:
        lines.extend(["", "## Rescue Required", "", "Missing families are explicit advisory/rescue items and are not silently treated as passed."])
    return "\n".join(lines)


def assess_review_rule_coverage(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    contract = _read_json(state.path / CONTRACT_JSON)
    if not contract:
        build_statistical_validation_contract(state.path)
        contract = _read_json(state.path / CONTRACT_JSON)
    available = _rule_ids(state.path)
    coverage = []
    missing = []
    for item in contract.get("validations") or []:
        preferred = [str(value) for value in item.get("preferred_review_rule_ids") or []]
        matched = [rule_id for rule_id in preferred if rule_id in available]
        status = "covered" if matched else "advisory_gap"
        family = str(item.get("rule_family") or "unknown")
        if not matched:
            missing.append(family)
        coverage.append({
            "validation_id": item.get("validation_id"),
            "rule_family": family,
            "status": status,
            "preferred_rule_ids": preferred,
            "matched_rule_ids": matched,
            "required_evidence_roles": item.get("required_evidence_roles") or [],
        })
    report = {
        "schema_version": "dpl.review_rule_coverage.v1",
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "decision": "pass" if not missing else "advisory_and_rescue_required",
        "available_rule_ids": sorted(available),
        "family_coverage": coverage,
        "missing_rule_families": missing,
        "rescue_sources": ["discipline_plugins", "shared_statistics_rules", "project_local_validated_code", "AcademicForge", "GitHub_research_code"],
        "policy": "Missing statistical review families remain explicit; only evidence-bound mature rules can block scientific progression.",
    }
    _write_json(state.path / COVERAGE_JSON, report)
    write_html_report(state.path / COVERAGE_HTML, _render_coverage(report), title="Review-rule Coverage")
    return {"status": "written", "project_path": str(state.path), "decision": report["decision"], "report": COVERAGE_JSON, "missing_rule_families": missing}


def statistical_plan_summary(project: str | Path, *, language: str = "en") -> str:
    state = load_project(project)
    contract = _read_json(state.path / CONTRACT_JSON)
    families = [str(item) for item in contract.get("task_families") or []]
    if language.lower().startswith("zh"):
        lines = ["## 统计验证计划", "", "关键图表执行前需要固定以下统计验证范围：", ""]
        lines.extend(f"- `{family}`：按正确的样本单位、cohort、数据划分和不确定性证据进行验证。" for family in families)
        lines.extend(["", "任何硬阈值都必须来自用户或期刊要求、有引用的领域规范，或已经验证且证据匹配的学科插件；系统不得使用跨项目通用的 F1、R2 或 p 值门槛。", ""])
        return "\n".join(lines)
    lines = ["## Statistical Validation Plan", "", "The key-figure execution is bound to these task-aware validation families:", ""]
    lines.extend(f"- `{family}`" for family in families)
    lines.extend(["", "Any hard threshold requires a user/journal source, a cited domain standard, or a validated evidence-matched discipline plugin.", ""])
    return "\n".join(lines)
