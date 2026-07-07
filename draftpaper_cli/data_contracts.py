# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now


DATA_ROLE_COVERAGE_JSON = "data/data_role_coverage_report.json"
DATA_ROLE_COVERAGE_HTML = "data/data_role_coverage_report.html"
DATA_CONTRACT_FULFILLMENT_JSON = "data/data_contract_fulfillment.json"
DATA_DEGRADATION_RECOMMENDATIONS_JSON = "data/data_degradation_recommendations.json"


ROLE_ALIASES = {
    "target": "label_or_response",
    "response": "label_or_response",
    "label": "label_or_response",
    "class": "label_or_response",
    "classification_label": "label_or_response",
    "time": "time_series",
    "date": "time_series",
    "timestamp": "time_series",
    "event_time": "time_series",
    "ra": "spatial_or_sky_coordinates",
    "dec": "spatial_or_sky_coordinates",
    "lat": "spatial_or_sky_coordinates",
    "latitude": "spatial_or_sky_coordinates",
    "lon": "spatial_or_sky_coordinates",
    "longitude": "spatial_or_sky_coordinates",
    "region": "spatial_or_sky_coordinates",
    "region_id": "spatial_or_sky_coordinates",
    "flux": "spectral_or_remote_sensing_features",
    "hardness": "spectral_or_remote_sensing_features",
    "spectral": "spectral_or_remote_sensing_features",
    "band": "spectral_or_remote_sensing_features",
    "ndvi": "spectral_or_remote_sensing_features",
    "evi": "spectral_or_remote_sensing_features",
    "image": "image_or_raster_data",
    "raster": "image_or_raster_data",
}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def normalize_role(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    if not text:
        return ""
    if text in ROLE_ALIASES:
        return ROLE_ALIASES[text]
    for key, role in ROLE_ALIASES.items():
        if key in text:
            return role
    if "validation" in text or "split" in text:
        return "validation_design"
    if "identifier" in text or text.endswith("_id") or text == "id":
        return "identifier_or_metadata"
    return text


def normalize_roles(values: Any) -> list[str]:
    roles: list[str] = []
    if isinstance(values, str):
        candidates = re.split(r"[,;/|]+", values)
    elif isinstance(values, list):
        candidates = values
    else:
        candidates = []
    for value in candidates:
        role = normalize_role(value)
        if role and role not in roles:
            roles.append(role)
    return roles


def available_data_roles(inventory: dict[str, Any], acquisition_plan: dict[str, Any] | None = None) -> list[str]:
    roles: list[str] = []

    def add(role: str) -> None:
        if role and role not in roles:
            roles.append(role)

    files = inventory.get("files") if isinstance(inventory, dict) else []
    if files:
        add("local_data")
        add("tabular_data")
    if inventory.get("total_rows"):
        add("sample_records")
    if inventory.get("remote_source_count"):
        add("remote_or_api_source")
    if inventory.get("result_artifacts"):
        add("supplied_result_artifacts")
    for item in files or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "processed":
            add("processed_dataset")
        suffix = str(item.get("suffix") or "").lower()
        if suffix in {".fits", ".fit"}:
            add("fits_data")
            add("image_or_raster_data")
        if suffix in {".tif", ".tiff", ".nc", ".h5"}:
            add("image_or_raster_data")
        for column in item.get("columns") or []:
            add(normalize_role(column))
    if isinstance(acquisition_plan, dict):
        for task in acquisition_plan.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            for role in normalize_roles(task.get("data_roles") or task.get("required_roles") or task.get("outputs") or []):
                add(role)
            if task.get("status") in {"ready", "planned", "requires_user_confirmation"}:
                add("planned_data_acquisition")
    return roles


def required_roles_from_storyboard(storyboard: dict[str, Any]) -> list[str]:
    required: list[str] = []
    for item in (storyboard.get("figures") or []) if isinstance(storyboard, dict) else []:
        if not isinstance(item, dict):
            continue
        candidates = []
        candidates.extend(item.get("required_data") or [])
        candidates.extend(item.get("required_data_roles") or [])
        candidates.extend(item.get("data_roles") or [])
        for role in normalize_roles(candidates):
            if role not in required:
                required.append(role)
    return required


def assess_role_coverage(required_roles: list[str], available_roles: list[str]) -> dict[str, Any]:
    normalized_required = normalize_roles(required_roles)
    normalized_available = normalize_roles(available_roles)
    missing = [role for role in normalized_required if role not in normalized_available]
    partial = [role for role in missing if role in {"validation_design", "processed_dataset", "remote_or_api_source"}]
    blocking = [role for role in missing if role not in partial]
    if blocking:
        decision = "blocked"
    elif partial:
        decision = "conditional"
    else:
        decision = "pass"
    return {
        "decision": decision,
        "required_roles": normalized_required,
        "available_roles": normalized_available,
        "missing_roles": missing,
        "blocking_missing_roles": blocking,
        "partial_missing_roles": partial,
    }


def write_data_contract_reports(project_path: str | Path, *, required_roles: list[str] | None = None) -> dict[str, Any]:
    root = Path(project_path)
    inventory = read_json(root / "data" / "data_inventory.json", {})
    acquisition = read_json(root / "data" / "data_acquisition_plan.json", {})
    storyboard = read_json(root / "research_plan" / "figure_storyboard.json", {})
    roles = required_roles or required_roles_from_storyboard(storyboard)
    coverage = assess_role_coverage(roles, available_data_roles(inventory, acquisition))
    payload = {
        "status": "written",
        "generated_at": utc_now(),
        "project_path": str(root),
        "source": "research_plan/figure_storyboard.json + data/data_inventory.json",
        **coverage,
    }
    recommendations = {
        "status": "written",
        "generated_at": utc_now(),
        "decision": coverage["decision"],
        "recommendations": _recommendations(coverage),
    }
    fulfillment = {
        "status": "written",
        "generated_at": utc_now(),
        "contract_fulfilled": coverage["decision"] == "pass",
        "role_coverage": coverage,
    }
    (root / "data").mkdir(parents=True, exist_ok=True)
    _write_json(root / DATA_ROLE_COVERAGE_JSON, payload)
    _write_json(root / DATA_CONTRACT_FULFILLMENT_JSON, fulfillment)
    _write_json(root / DATA_DEGRADATION_RECOMMENDATIONS_JSON, recommendations)
    write_html_report(root / DATA_ROLE_COVERAGE_HTML, render_role_coverage_markdown(payload, recommendations), title="Data Role Coverage")
    return payload


def _recommendations(coverage: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for role in coverage.get("missing_roles") or []:
        items.append({
            "role": role,
            "action": "prepare-data-acquisition",
            "reason": "The research plan or main-figure storyboard needs this data role before strong claims can be made.",
            "degradation": "If the role cannot be supplied, revise the research plan to remove or narrow figures and claims that depend on it.",
        })
    if not items:
        items.append({"role": "all_required_roles", "action": "proceed", "reason": "Required data roles are represented in the current project evidence.", "degradation": "No data-driven degradation is currently required."})
    return items


def render_role_coverage_markdown(report: dict[str, Any], recommendations: dict[str, Any]) -> str:
    lines = [
        "# Data Role Coverage",
        "",
        f"Decision: `{report.get('decision')}`",
        "",
        "## Required Roles",
        "",
    ]
    for role in report.get("required_roles") or []:
        lines.append(f"- {role}")
    lines.extend(["", "## Available Roles", ""])
    for role in report.get("available_roles") or []:
        lines.append(f"- {role}")
    lines.extend(["", "## Recommendations", ""])
    for item in recommendations.get("recommendations") or []:
        lines.append(f"- {item.get('role')}: {item.get('action')} -- {item.get('reason')}")
    return "\n".join(lines)
