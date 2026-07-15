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
    "sample": "event_level_samples",
    "samples": "event_level_samples",
    "sample_records": "event_level_samples",
    "event_sample": "event_level_samples",
    "event_samples": "event_level_samples",
    "event_level_sample": "event_level_samples",
    "event_level_samples": "event_level_samples",
    "observation_sample": "event_level_samples",
    "observation_samples": "event_level_samples",
    "row": "event_level_samples",
    "rows": "event_level_samples",
    "n_rows": "event_level_samples",
    "sample_group": "sample_group",
    "sample_groups": "sample_group",
    "group": "sample_group",
    "group_id": "sample_group",
    "source_group": "sample_group",
    "source_or_object_group": "sample_group",
    "object_group": "sample_group",
    "fold": "sample_group",
    "split": "sample_group",
    "source": "source_catalog",
    "source_id": "source_catalog",
    "source_identifier": "source_catalog",
    "targetid": "identifier_or_metadata",
    "sourceid": "identifier_or_metadata",
    "objectid": "identifier_or_metadata",
    "paired_object_id": "identifier_or_metadata",
    "catalog": "source_catalog",
    "catalog_id": "source_catalog",
    "target": "label_or_response",
    "response": "label_or_response",
    "label": "label_or_response",
    "class": "label_or_response",
    "category": "label_or_response",
    "class_label": "label_or_response",
    "classification_label": "label_or_response",
    "morphtype": "label_or_response",
    "morphology_label": "label_or_response",
    "profile_label": "label_or_response",
    "profile_type": "label_or_response",
    "probability": "prediction_score",
    "prediction": "prediction_score",
    "prediction_score": "prediction_score",
    "score": "prediction_score",
    "logit": "prediction_score",
    "time": "time_series",
    "date": "time_series",
    "timestamp": "time_series",
    "event_time": "time_series",
    "mjd": "light_curve",
    "rate": "light_curve",
    "delta_time_days": "light_curve",
    "light_curve": "light_curve",
    "history_lc": "light_curve",
    "history_lc_tokens": "light_curve",
    "history_n_tokens": "history_sequence_tokens",
    "history_tokens": "history_sequence_tokens",
    "history_sequence": "history_sequence_tokens",
    "history_sequence_tokens": "history_sequence_tokens",
    "historical_tokens": "history_sequence_tokens",
    "current_observation": "current_observation_tokens",
    "current_observation_tokens": "current_observation_tokens",
    "current_lc_tokens": "current_observation_tokens",
    "current_n_tokens": "current_observation_tokens",
    "current_tokens": "current_observation_tokens",
    "current_token_count": "current_observation_tokens",
    "n_current_tokens": "current_observation_tokens",
    "ra": "spatial_or_sky_coordinates",
    "dec": "spatial_or_sky_coordinates",
    "lat": "spatial_or_sky_coordinates",
    "latitude": "spatial_or_sky_coordinates",
    "lon": "spatial_or_sky_coordinates",
    "longitude": "spatial_or_sky_coordinates",
    "region": "spatial_or_sky_coordinates",
    "region_id": "spatial_or_sky_coordinates",
    "flux": "spectral_or_remote_sensing_features",
    "pha": "spectral_or_remote_sensing_features",
    "bkg_pha": "spectral_or_remote_sensing_features",
    "arf": "spectral_or_remote_sensing_features",
    "rmf": "spectral_or_remote_sensing_features",
    "has_pha": "modality_availability",
    "has_bkg_pha": "modality_availability",
    "has_arf": "modality_availability",
    "has_rmf": "modality_availability",
    "has_photon_lc": "modality_availability",
    "modality_availability": "modality_availability",
    "modality_coverage": "modality_availability",
    "spectral_availability": "modality_availability",
    "channel": "spectral_or_remote_sensing_features",
    "hardness": "spectral_or_remote_sensing_features",
    "spectral": "spectral_or_remote_sensing_features",
    "band": "spectral_or_remote_sensing_features",
    "ndvi": "spectral_or_remote_sensing_features",
    "evi": "spectral_or_remote_sensing_features",
    "feature": "features",
    "features": "features",
    "feature_name": "features",
    "feature_matrix": "features",
    "importance": "features",
    "feature_importance": "features",
    "embedding": "features",
    "embeddings": "features",
    "physical_observables": "physical_observables",
    "literature_observational_interval": "literature_observational_interval",
    "citation_evidence": "citation_evidence",
    "redshift_uncertainty": "redshift_uncertainty",
    "spectral_type": "spectral_type",
    "spectype": "spectral_type",
    "photometric_colours": "photometric_colours",
    "photometric_colors": "photometric_colours",
    "image_quality_flags": "image_quality_flags",
    "token_sequence_arrays": "features",
    "image": "image_or_raster_data",
    "raster": "image_or_raster_data",
    "image_manifest": "image_manifest",
    "acquisition_group": "acquisition_group",
}


# Some research-plan roles are deliberately more specific than inventory
# roles. Keep that specificity in reports, but define the concrete evidence
# combination that can satisfy each role.
ROLE_EVIDENCE_REQUIREMENTS = {
    "vis_cutout_manifest": {"image_manifest"},
    "held_out_vis_cutouts": {"image_manifest", "validation_design"},
    "euclid_tile": {"acquisition_group"},
    "observed_colours": {"photometric_colours"},
    "observed_colors": {"photometric_colours"},
    "apparent_r_magnitude": {"apparent_magnitude"},
    "spectroscopic_redshift": {"redshift"},
    "calibration_bins": {"prediction_score"},
    "dev_exp_vis_images": {"image_or_raster_data"},
    "ser_rex_images": {"image_or_raster_data"},
    "euclid_tile_groups": {"acquisition_group"},
    "curated_literature_evidence": {"citation_evidence"},
    "study_passbands": {"passband_metadata"},
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
    if text in {"targetid", "sourceid", "objectid", "paired_object_id"}:
        return "identifier_or_metadata"
    if text in ROLE_ALIASES:
        return ROLE_ALIASES[text]
    for key, role in ROLE_ALIASES.items():
        if len(key) >= 4 and re.search(rf"(?:^|_){re.escape(key)}(?:_|$)", text):
            return role
    if any(token in text for token in ["source_catalog", "ra_dec", "skycoord"]):
        return "source_catalog"
    if any(token in text for token in ["event_level", "event_sample", "sample_record", "n_rows", "row_count"]):
        return "event_level_samples"
    if any(token in text for token in ["sample_group", "source_group", "object_group", "group_holdout", "fold"]):
        return "sample_group"
    if any(token in text for token in ["lightcurve", "light_curve", "lc_token", "mjd", "cadence"]):
        return "light_curve"
    if any(token in text for token in ["current_observation", "current_token", "observation_token", "current_n_token"]):
        return "current_observation_tokens"
    if any(token in text for token in ["history_token", "historical_token", "history_sequence", "history_n_token"]):
        return "history_sequence_tokens"
    if any(token in text for token in ["has_pha", "has_arf", "has_rmf", "has_photon", "modality", "availability"]):
        return "modality_availability"
    if any(token in text for token in ["feature", "importance", "embedding", "token_sequence_array"]):
        return "features"
    if any(token in text for token in ["auc", "f1", "accuracy", "prob", "score", "logit"]):
        return "prediction_score"
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
        add("event_level_samples")
    if inventory.get("remote_source_count"):
        add("remote_or_api_source")
    if inventory.get("result_artifacts"):
        add("supplied_result_artifacts")
    all_columns: list[str] = []
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
            all_columns.append(str(column))
            if re.fullmatch(r"emb_\d+", str(column).lower()):
                add("features")
                continue
            add(normalize_role(column))
    column_blob = " ".join(re.sub(r"[^a-z0-9]+", "_", column.lower()) for column in all_columns)
    column_set = {re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_") for column in all_columns}
    if any(column in column_set for column in {"current_n_tokens", "current_tokens", "current_lc_tokens"}):
        add("current_observation_tokens")
        add("light_curve")
    if any(column in column_set for column in {"history_n_tokens", "history_tokens", "history_lc_tokens"}):
        add("history_sequence_tokens")
        add("light_curve")
    if {"has_pha", "has_arf", "has_rmf"} & column_set or "has_photon" in column_blob:
        add("modality_availability")
        add("spectral_or_remote_sensing_features")
    if {"feature", "importance", "feature_importance"} & column_set or "embedding" in column_blob or any(re.fullmatch(r"emb_\d+", column) for column in column_set):
        add("features")
    if any(
        column in column_set
        for column in {"z", "redshift", "mag_g", "mag_r", "mag_z", "abs_mag_r", "color_gr", "color_rz", "color_w1w2", "age", "sex", "site", "batch"}
    ):
        add("confounder_variables")
        add("selection_covariates")
        add("continuous_physical_observables")
        add("physical_observables")
    if {"color_gr", "abs_mag_r"}.issubset(column_set) or {"mag_g", "mag_r", "mag_z"}.issubset(column_set):
        add("continuous_colour_magnitude_observables")
    if "adaptive_label" in column_set:
        add("physical_state_proxy")
    if "morphtype" in column_set:
        add("catalog_profile_morphology")
    if {"z", "redshift"} & column_set:
        add("redshift")
    if {"zerr", "redshift_error", "redshift_uncertainty"} & column_set:
        add("redshift_uncertainty")
    if {"spectype", "spectral_type"} & column_set:
        add("spectral_type")
    if {"color_gr", "color_rz", "color_w1w2"} & column_set:
        add("photometric_colours")
    if "abs_mag_r" in column_set:
        add("absolute_magnitude")
    if "mag_r" in column_set:
        add("apparent_magnitude")
    if "mag_r" in column_set and ({"bgs_target", "target_state"} & column_set):
        add("selection_function")
    if {"citation_key", "evidence_locator"}.issubset(column_set) or {
        "citation_key", "doi", "evidence_status"
    }.issubset(column_set):
        add("citation_evidence")
    if {"citation_key", "physical_parameter", "interval_kind"}.issubset(column_set) and (
        {"lower", "upper"} & column_set or "central" in column_set
    ):
        add("literature_observational_interval")
    if {"passband", "filter", "band_definition"} & column_set:
        add("passband_metadata")
    if {"neighbour_contamination", "neighbor_contamination", "neighbour_contamination_score", "neighbor_contamination_score"} & column_set:
        add("neighbour_contamination")
    if {"background_quality", "background_quality_score", "background_quality_failure", "border_mad"} & column_set:
        add("background_quality")
    if any(
        "missing" in column
        or "availability" in column
        or column.endswith(("_available", "_exists"))
        or column in {"coverage", "availability"}
        for column in column_set
    ):
        add("missingness_reason")
    if any(
        token in column_blob
        for token in ("quality", "flag", "zwarn", "fiberstatus", "cutout_exists", "is_anomaly", "valid_image")
    ):
        add("quality_flags")
        add("image_quality_flags")
    if {"rows", "n_rows", "row_count", "evt_n_rows", "cat_n_rows", "n_events"} & column_set:
        add("event_level_samples")
    if {"fold", "split", "n_train", "n_test", "source_id", "object_id", "group_id"} & column_set:
        add("sample_group")
        add("validation_design")
    if {"cutout_file_path", "image_file_path", "raster_file_path"} & column_set and (
        {"cutout_exists", "image_exists", "raster_exists"} & column_set
    ):
        add("image_manifest")
    if any(
        column in column_set
        for column in {"tile", "tile_id", "euclid_tile", "euclid_primary_tile_id", "field_id", "exposure_id", "acquisition_group"}
    ):
        add("acquisition_group")
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
    from .research_capabilities import is_derived_method_output_role

    required: list[str] = []
    for item in (storyboard.get("figures") or []) if isinstance(storyboard, dict) else []:
        if not isinstance(item, dict):
            continue
        candidates = []
        candidates.extend(item.get("required_data") or [])
        candidates.extend(item.get("required_data_roles") or [])
        candidates.extend(item.get("data_roles") or [])
        input_candidates = [
            role
            for role in candidates
            if not is_derived_method_output_role(role)
        ]
        for role in normalize_roles(input_candidates):
            if role not in required:
                required.append(role)
    return required


def assess_role_coverage(required_roles: list[str], available_roles: list[str]) -> dict[str, Any]:
    normalized_required = normalize_roles(required_roles)
    normalized_available = normalize_roles(available_roles)
    available = set(normalized_available)
    missing = []
    role_evidence: dict[str, list[str]] = {}
    for role in normalized_required:
        required_evidence = ROLE_EVIDENCE_REQUIREMENTS.get(role, {role})
        role_evidence[role] = sorted(required_evidence)
        if not required_evidence.issubset(available):
            missing.append(role)
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
        "role_evidence_requirements": role_evidence,
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
    from .cohort_semantics import build_data_semantic_contracts

    semantic_contracts = build_data_semantic_contracts(root)
    payload["semantic_contracts"] = semantic_contracts
    _write_json(root / DATA_ROLE_COVERAGE_JSON, payload)
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
