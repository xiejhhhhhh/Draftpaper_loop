# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from typing import Any

IDENTIFIER_ROLES = {"identifier", "source_id", "obs_id", "observation_id", "event_id", "row_id"}


def normalize_semantic_role(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return ""
    if text in IDENTIFIER_ROLES or text.endswith("_id") or text == "id":
        return "identifier"
    if any(token in text for token in ["label", "target", "class", "category", "response", "yield"]):
        return "label_or_response"
    if any(token in text for token in ["model", "variant", "estimator", "architecture"]):
        return "model_variant"
    if any(token in text for token in ["f1", "auc", "accuracy", "precision", "recall", "r2", "score"]):
        return "performance_metric"
    if any(token in text for token in ["time", "date", "mjd", "cadence", "light_curve"]):
        return "temporal_feature"
    if any(token in text for token in ["latitude", "longitude", "region", "coordinate", "spatial"]):
        return "spatial_feature"
    if text in {"lat", "lon", "ra", "dec", "right_ascension", "declination"}:
        return "spatial_feature"
    if any(token in text for token in ["ndvi", "evi", "flux", "hardness", "spectral", "feature", "predictor", "embedding"]):
        return "features"
    if any(token in text for token in ["count", "number", "sample_size", "row"]):
        return "sample_count"
    return text


def _metric_dimension(metric: str) -> str:
    lowered = str(metric or "").lower()
    if any(token in lowered for token in ["f1", "auc", "accuracy", "precision", "recall", "r2", "correlation", "pearson"]):
        return "dimensionless_score"
    if any(token in lowered for token in ["count", "number", "sample_size", "row"]):
        return "count"
    if any(token in lowered for token in ["time", "duration", "cadence"]):
        return "time"
    return ""


def build_semantic_figure_contract(figure: dict[str, Any]) -> dict[str, Any]:
    """Derive a domain-neutral semantic contract from an explicit figure specification."""
    kind = str(figure.get("figure_type") or figure.get("visualization_type") or "").lower()
    blob = " ".join(
        str(figure.get(key) or "")
        for key in ["title", "figure_group"]
    ).lower()
    if kind == "data_overview":
        grammar = "workflow_schematic" if "workflow" in blob else "coverage_summary"
    elif kind in {"histogram", "feature_distribution"}:
        grammar = "distribution"
    elif kind == "class_balance":
        grammar = "class_distribution"
    elif kind == "correlation_heatmap":
        grammar = "correlation_matrix"
    elif kind in {"scatter_regression", "feature_relationship", "feature_response", "time_series"}:
        grammar = "relationship"
    elif kind in {"metric_summary", "performance", "model_performance"}:
        if "ablation" in blob:
            grammar = "ablation"
        elif any(token in blob for token in ["uncertainty", "error"]):
            grammar = "uncertainty_summary"
        elif any(token in blob for token in ["model", "baseline", "performance", "classification"]):
            grammar = "model_comparison"
        else:
            grammar = "metric_summary"
    else:
        grammar = kind or "scientific_figure"

    roles: list[str] = []
    if grammar == "workflow_schematic":
        roles.append("data_flow")
    elif grammar == "class_distribution":
        roles.append("label_or_response")
    elif grammar in {"model_comparison", "ablation"}:
        roles.extend(["model_variant", "performance_metric"])
    elif grammar == "uncertainty_summary":
        roles.extend(["label_or_response", "performance_metric"])
    else:
        planned_roles = _items(
            figure.get("required_data_roles")
            or figure.get("required_data")
            or figure.get("data_roles")
        )
        for value in planned_roles:
            role = normalize_semantic_role(value)
            if role and role != "identifier" and role not in roles:
                roles.append(role)
        if not roles:
            for field in ["x", "y", "group"]:
                value = figure.get(field)
                role = normalize_semantic_role(value) if value else ""
                if role and role not in roles:
                    roles.append(role)
    validation_metric = str(figure.get("validation_metric") or "")
    metric_dimension = _metric_dimension(validation_metric)
    if grammar in {"model_comparison", "ablation"}:
        for role in ["model_variant", "performance_metric"]:
            if role not in roles:
                roles.append(role)
        metric_dimension = metric_dimension or "dimensionless_score"
    elif grammar == "correlation_matrix" and "features" not in roles:
        roles.append("features")
    elif grammar == "class_distribution" and "label_or_response" not in roles:
        roles.append("label_or_response")
    required_outputs = _items(figure.get("required_method_outputs"))
    if validation_metric and validation_metric not in required_outputs:
        required_outputs.append(validation_metric)
    required_panels = _items(figure.get("required_panels") or figure.get("ablation_variants"))
    forbidden = [] if grammar in {"workflow_schematic", "coverage_summary"} else ["identifier"]
    return {
        "scientific_question": str(figure.get("scientific_question") or figure.get("research_question") or "").strip(),
        "required_variable_roles": roles,
        "forbidden_variable_roles": forbidden,
        "required_method_outputs": required_outputs,
        "plot_grammar": grammar,
        "required_panels": required_panels,
        "metric_dimensions": [metric_dimension] if metric_dimension else [],
        "expected_claim": str(figure.get("expected_finding") or figure.get("result_claim_template") or "").strip(),
    }


def rendered_semantic_metadata(figure: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Describe variables and units actually rendered, independently of the title."""
    contract = build_semantic_figure_contract(figure)
    variables = payload.get("variables") if isinstance(payload.get("variables"), dict) else {}
    statistics = payload.get("statistics") if isinstance(payload.get("statistics"), dict) else {}
    x_name = str(variables.get("x") or "")
    y_name = str(variables.get("y") or "")
    group_name = str(variables.get("group") or "")
    variable_roles = []
    for name in [x_name, y_name, group_name]:
        role = normalize_semantic_role(name) if name else ""
        if role and role not in variable_roles:
            variable_roles.append(role)
    metric_names = variables.get("metrics") if isinstance(variables.get("metrics"), list) else []
    series = []
    for name in metric_names:
        metric = str(name)
        dimension = _metric_dimension(metric) or "unknown"
        series.append({
            "role": "sample_count" if dimension == "count" else "performance_metric",
            "unit_family": dimension,
            "metric": metric,
        })
    if metric_names:
        variable_roles.extend(role for role in ["model_variant", "performance_metric"] if role not in variable_roles)
    method_outputs = [str(key) for key in statistics]
    panels = _items(payload.get("panels") or figure.get("rendered_panels"))
    return {
        "x_role": normalize_semantic_role(x_name) if x_name else "",
        "y_role": normalize_semantic_role(y_name) if y_name else "",
        "variable_roles": variable_roles,
        "series": series,
        "method_outputs": method_outputs,
        "panels": panels,
        "plot_grammar": contract["plot_grammar"],
    }


def _items(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def validate_figure_semantics(contract: dict[str, Any], produced: dict[str, Any]) -> dict[str, Any]:
    """Validate that a rendered figure answers its scientific contract."""
    issues: list[dict[str, str]] = []
    x_role = str(produced.get("x_role") or "").lower()
    y_role = str(produced.get("y_role") or "").lower()
    observed_roles = {x_role, y_role}
    observed_roles.update(str(item).lower() for item in _items(produced.get("variable_roles")))
    series = [item for item in (produced.get("series") or []) if isinstance(item, dict)]
    observed_roles.update(str(item.get("role") or "").lower() for item in series)
    observed_roles.discard("")

    if x_role in IDENTIFIER_ROLES and y_role in IDENTIFIER_ROLES:
        issues.append({
            "severity": "blocking",
            "kind": "identifier_only_scientific_plot",
            "detail": "Identifiers cannot serve as both scientific axes.",
        })

    forbidden = {item.lower() for item in _items(contract.get("forbidden_variable_roles"))}
    forbidden_observed = sorted(
        role for role in observed_roles
        if role in forbidden or (role in IDENTIFIER_ROLES and "identifier" in forbidden)
    )
    for role in forbidden_observed:
        issues.append({"severity": "blocking", "kind": "forbidden_variable_role", "detail": role})

    required_roles = {item.lower() for item in _items(contract.get("required_variable_roles"))}
    missing_roles = sorted(required_roles - observed_roles)
    for role in missing_roles:
        issues.append({"severity": "blocking", "kind": "missing_required_variable_role", "detail": role})

    unit_families = {
        str(item.get("unit_family") or "").lower()
        for item in series
        if str(item.get("unit_family") or "").strip()
    }
    permitted_dimensions = {item.lower() for item in _items(contract.get("metric_dimensions"))}
    if len(unit_families) > 1 and not bool(produced.get("separate_axes")):
        issues.append({
            "severity": "blocking",
            "kind": "mixed_unit_families",
            "detail": ", ".join(sorted(unit_families)),
        })
    unexpected_dimensions = sorted(unit_families - permitted_dimensions) if permitted_dimensions else []
    for dimension in unexpected_dimensions:
        issues.append({"severity": "blocking", "kind": "unexpected_metric_dimension", "detail": dimension})

    required_outputs = set(_items(contract.get("required_method_outputs")))
    observed_outputs = set(_items(produced.get("method_outputs")))
    for output in sorted(required_outputs - observed_outputs):
        issues.append({"severity": "blocking", "kind": "missing_method_output", "detail": output})

    required_panels = set(_items(contract.get("required_panels")))
    observed_panels = set(_items(produced.get("panels")))
    for panel in sorted(required_panels - observed_panels):
        issues.append({"severity": "blocking", "kind": "missing_required_panel", "detail": panel})

    expected_grammar = str(contract.get("plot_grammar") or "").lower()
    observed_grammar = str(produced.get("plot_grammar") or "").lower()
    if expected_grammar and observed_grammar and expected_grammar != observed_grammar:
        issues.append({
            "severity": "blocking",
            "kind": "plot_grammar_mismatch",
            "detail": f"expected={expected_grammar}; observed={observed_grammar}",
        })

    return {
        "figure_id": contract.get("figure_id") or contract.get("storyboard_id") or "",
        "decision": "blocked" if any(item["severity"] == "blocking" for item in issues) else "pass",
        "issues": issues,
        "observed_variable_roles": sorted(observed_roles),
        "observed_unit_families": sorted(unit_families),
        "observed_method_outputs": sorted(observed_outputs),
    }
