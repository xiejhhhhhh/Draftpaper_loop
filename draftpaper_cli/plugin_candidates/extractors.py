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

from .common import (
    CAPABILITY_IR_VERSION,
    DATA_CONNECTOR_KEYWORDS,
    FORMAL_DISCIPLINE_PLUGIN_TYPES,
    METHOD_TEMPLATE_KEYWORDS,
    PluginCandidateError,
    REVIEW_RULE_FAMILY_METADATA,
    REVIEW_RULE_KEYWORDS,
    REVIEW_RULE_PIPELINE_HOOKS,
    REVIEW_RULE_SIGNAL_DIMENSIONS,
    RUNTIME_CLASSES,
    SUPPORT_LAYER_TYPES,
    SUPPORT_ROUTE_KEYWORDS,
    SUPPORT_ROUTE_TARGETS,
    VALIDATION_LEVELS,
    _privacy_scan_text,
    _read_json,
    _read_text,
    _render_candidate_summary,
    _render_support_candidate_summary,
    _safe_id,
)

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
