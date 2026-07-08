# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .data_contracts import DATA_CONTRACT_FULFILLMENT_JSON, DATA_DEGRADATION_RECOMMENDATIONS_JSON, DATA_ROLE_COVERAGE_HTML, DATA_ROLE_COVERAGE_JSON, write_data_contract_reports
from .html_utils import write_html_report
from .observations import load_observations
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status
from .reference_usage import ensure_reference_usage_plan, missing_entries_for_section
from .writing_brief import DATA_WRITING_BRIEF_HTML, DATA_WRITING_BRIEF_JSON, build_data_writing_brief


DATA_INVENTORY_OUTPUT = "data/data_inventory.json"
DATA_QUALITY_OUTPUT = "data/data_quality_report.json"
DATA_FEASIBILITY_JSON = "data/data_feasibility_report.json"
DATA_FEASIBILITY_MD = "data/data_feasibility_report.md"
DATA_WRITING_CONTEXT_JSON = "data/data_writing_context.json"
DATA_WRITING_CONTEXT_HTML = "data/data_writing_context.html"
DATA_KEY_FACTS_JSON = "data/data_key_facts.json"
DATA_TEX = "data/data.tex"
REMOTE_SOURCE_FILES = ["data/remote_sources.json", "data/source_manifest.json"]

DATA_OUTPUTS = [
    "data/data_acquisition_plan.json",
    DATA_INVENTORY_OUTPUT,
    DATA_QUALITY_OUTPUT,
    DATA_FEASIBILITY_JSON,
    DATA_FEASIBILITY_MD,
    DATA_ROLE_COVERAGE_JSON,
    DATA_ROLE_COVERAGE_HTML,
    DATA_CONTRACT_FULFILLMENT_JSON,
    DATA_DEGRADATION_RECOMMENDATIONS_JSON,
]

DATA_WRITING_OUTPUTS = [
    DATA_WRITING_CONTEXT_JSON,
    DATA_WRITING_CONTEXT_HTML,
    DATA_KEY_FACTS_JSON,
    DATA_WRITING_BRIEF_JSON,
    DATA_WRITING_BRIEF_HTML,
    DATA_TEX,
]

TABULAR_EXTENSIONS = {".csv", ".tsv"}
DATA_EXTENSIONS = TABULAR_EXTENSIONS | {".json", ".xlsx", ".xls", ".parquet", ".txt", ".fits", ".fit", ".h5", ".hdf5", ".npy", ".npz"}


class DataGateError(RuntimeError):
    """Raised when data inventory, quality, or feasibility cannot be assessed."""


def _project_relative(project_path: Path, path: Path) -> str:
    return path.relative_to(project_path).as_posix()


def _read_tabular_profile(path: Path) -> dict[str, Any]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            columns = list(reader.fieldnames or [])
            row_count = 0
            missing_cells = 0
            total_cells = 0
            for row in reader:
                row_count += 1
                for column in columns:
                    total_cells += 1
                    value = row.get(column)
                    if value is None or str(value).strip() == "":
                        missing_cells += 1
    except UnicodeDecodeError:
        return {"readable": False, "columns": [], "row_count": None, "column_count": None, "missing_cells": None, "total_cells": None}
    return {
        "readable": True,
        "columns": columns,
        "row_count": row_count,
        "column_count": len(columns),
        "missing_cells": missing_cells,
        "total_cells": total_cells,
        "missing_cell_ratio": (missing_cells / total_cells) if total_cells else 0.0,
    }


def inventory_data(project: str | Path) -> dict[str, Any]:
    """Inventory local data files plus optional remote/API/server data manifests."""
    state = load_project(project)
    files = []
    for base in [state.path / "data" / "raw", state.path / "data" / "processed"]:
        base.mkdir(parents=True, exist_ok=True)
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.name.startswith(".") or path.name.endswith(".tex"):
                continue
            if path.suffix.lower() not in DATA_EXTENSIONS:
                continue
            profile = _read_tabular_profile(path) if path.suffix.lower() in TABULAR_EXTENSIONS else {
                "readable": None,
                "columns": [],
                "row_count": None,
                "column_count": None,
                "missing_cells": None,
                "total_cells": None,
                "missing_cell_ratio": None,
            }
            files.append({
                "path": _project_relative(state.path, path),
                "kind": "raw" if "data/raw" in _project_relative(state.path, path) else "processed",
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                **profile,
            })
    remote_sources = _load_remote_sources(state.path)
    result_artifacts = _inventory_existing_result_artifacts(state.path)
    payload = {
        "project_id": state.metadata.get("project_id"),
        "file_count": len(files),
        "files": files,
        "remote_source_count": len(remote_sources),
        "remote_sources": remote_sources,
        "result_artifacts": result_artifacts,
        "total_rows": sum(int(item.get("row_count") or 0) for item in files),
        "tabular_file_count": sum(1 for item in files if item.get("suffix") in TABULAR_EXTENSIONS),
    }
    _write_json(state.path / DATA_INVENTORY_OUTPUT, payload)
    _set_data_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "data_inventory": str(state.path / DATA_INVENTORY_OUTPUT),
        "file_count": len(files),
        "remote_source_count": len(remote_sources),
        "total_rows": payload["total_rows"],
    }


def _load_remote_sources(project_path: Path) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for relative in REMOTE_SOURCE_FILES:
        path = project_path / relative
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise DataGateError(f"{relative} is not valid JSON: {exc}") from exc
        entries = payload if isinstance(payload, list) else payload.get("sources") if isinstance(payload, dict) else []
        if not isinstance(entries, list):
            raise DataGateError(f"{relative} must contain a list or an object with a sources list.")
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                continue
            sources.append({
                "id": entry.get("id") or f"remote_source_{index}",
                "kind": entry.get("kind") or entry.get("type") or "remote",
                "access": entry.get("access") or entry.get("url") or entry.get("api") or entry.get("server") or "",
                "description": entry.get("description") or entry.get("note") or "",
                "processed_data": entry.get("processed_data") or entry.get("processed_files") or [],
                "result_artifacts": entry.get("result_artifacts") or entry.get("results") or [],
                "local_summary": entry.get("local_summary") or entry.get("summary") or "",
                "download_policy": entry.get("download_policy") or "remote_or_large_data_not_downloaded",
                "manifest_path": relative,
            })
    return sources


def _inventory_existing_result_artifacts(project_path: Path) -> list[dict[str, Any]]:
    artifacts = []
    for base_relative in ["results/figures", "results/tables", "data/processed"]:
        base = project_path / base_relative
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            artifacts.append({
                "path": _project_relative(project_path, path),
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "kind": "figure" if "figures" in base_relative else "table_or_processed_data",
            })
    return artifacts


def _load_json(project_path: Path, relative: str) -> dict[str, Any]:
    path = project_path / relative
    if not path.exists():
        raise DataGateError(f"{relative} is required.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise DataGateError(f"{relative} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DataGateError(f"{relative} must contain an object.")
    return payload


def _read_optional_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return fallback


def assess_data_quality(project: str | Path, *, required_columns: list[str] | None = None, max_missing_ratio: float = 0.2) -> dict[str, Any]:
    """Assess basic local data quality from data_inventory.json."""
    state = load_project(project)
    inventory = _load_json(state.path, DATA_INVENTORY_OUTPUT)
    required = [column for column in (required_columns or []) if column]
    all_columns = set()
    total_missing = 0
    total_cells = 0
    unreadable_files = []
    for item in inventory.get("files") or []:
        all_columns.update(item.get("columns") or [])
        total_missing += int(item.get("missing_cells") or 0)
        total_cells += int(item.get("total_cells") or 0)
        if item.get("readable") is False:
            unreadable_files.append(item.get("path"))
    missing_required = sorted(set(required) - all_columns)
    missing_ratio = (total_missing / total_cells) if total_cells else 0.0
    issues = []
    if not inventory.get("file_count") and not inventory.get("remote_source_count") and not inventory.get("result_artifacts"):
        issues.append("No local data files, remote source manifests, or processed result artifacts were found.")
    if missing_required:
        issues.append("Missing required columns: " + ", ".join(missing_required))
    if missing_ratio > max_missing_ratio:
        issues.append(f"Overall missing-cell ratio {missing_ratio:.3f} exceeds threshold {max_missing_ratio:.3f}.")
    if unreadable_files:
        issues.append("Some tabular files could not be read: " + ", ".join(str(item) for item in unreadable_files))
    overall = "pass" if not issues else "warning"
    payload = {
        "project_id": state.metadata.get("project_id"),
        "overall_status": overall,
        "required_columns": required,
        "missing_required_columns": missing_required,
        "overall_missing_cell_ratio": missing_ratio,
        "max_missing_ratio": max_missing_ratio,
        "unreadable_files": unreadable_files,
        "issues": issues,
        "total_rows": inventory.get("total_rows", 0),
        "file_count": inventory.get("file_count", 0),
        "remote_source_count": inventory.get("remote_source_count", 0),
        "result_artifact_count": len(inventory.get("result_artifacts") or []),
    }
    _write_json(state.path / DATA_QUALITY_OUTPUT, payload)
    _set_data_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "data_quality_report": str(state.path / DATA_QUALITY_OUTPUT),
        "overall_status": overall,
        "issue_count": len(issues),
    }


def _plan_requires_external_validation(plan_text: str) -> bool:
    lowered = plan_text.lower()
    return "external validation" in lowered or "generalizable" in lowered or "generalization" in lowered


def _plan_is_exploratory(plan_text: str) -> bool:
    lowered = plan_text.lower()
    return "exploratory" in lowered or "pilot" in lowered or "preliminary" in lowered


def _render_feasibility_md(report: dict[str, Any]) -> str:
    lines = [
        "# Data Feasibility Report",
        "",
        f"Decision: {report['decision']}",
        "",
        f"Scientific goal supported: {str(report['scientific_goal_supported']).lower()}",
        "",
        f"Supported claim level: {report['supported_claim_level']}",
        "",
        "## Blocking Issues",
        "",
    ]
    for issue in report.get("blocking_issues") or ["None."]:
        lines.append(f"- {issue}")
    lines.extend(["", "## Recommended Actions", ""])
    for action in report.get("recommended_actions") or ["Proceed with the current staged workflow."]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def _safe_latex_text(text: Any) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in str(text or ""))


def _clean_sentence(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


ASTRONOMY_PRODUCT_REPLACEMENTS = [
    (re.compile(r"\bbkg[_-]?pha(?:[_-]?(?:file|path|filename|pathname))\b", re.IGNORECASE), "background spectra (PHA)"),
    (re.compile(r"\bpha(?:[_-]?(?:file|path|filename|pathname))\b", re.IGNORECASE), "source spectra (PHA)"),
    (re.compile(r"\barf(?:[_-]?(?:file|path|filename|pathname))\b", re.IGNORECASE), "effective-area response products (ARF)"),
    (re.compile(r"\brmf(?:[_-]?(?:file|path|filename|pathname))\b", re.IGNORECASE), "redistribution response matrices (RMF)"),
    (re.compile(r"\b(?:bkg[_-]?)?lc(?:[_-]?(?:file|path|filename|pathname))\b", re.IGNORECASE), "source and background light-curve products"),
    (re.compile(r"\bevt(?:[_-]?(?:file|path|filename|pathname))\b", re.IGNORECASE), "event products"),
    (re.compile(r"\bimg(?:[_-]?(?:file|path|filename|pathname))\b", re.IGNORECASE), "image products"),
    (re.compile(r"\bexp(?:[_-]?(?:file|path|filename|pathname))\b", re.IGNORECASE), "exposure products"),
]


def _manuscript_clean_text(text: Any) -> str:
    """Remove local implementation tokens before text can enter manuscript prose."""
    cleaned = str(text or "")
    for pattern, replacement in ASTRONOMY_PRODUCT_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = re.sub(r"[A-Za-z]:\\[^\s,.;)]+", "processed research materials", cleaned)
    cleaned = re.sub(r"\b(?:data|results|code|methods|references)/(?:raw|processed|figures|tables|scripts|code_templates|literature_summaries)/[^\s,.;)]+", "processed research materials", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b[\w.-]+\.(?:csv|tsv|xlsx|xls|json|py|svg|png|jpg|jpeg|html|md|tex|fits|zip)\b", "processed research materials", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:training_)?smoke[_-]?test\b", "execution check", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:XRB|TDE|AGN)[_-]?verify\b", "class-specific verification subset", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:file|path|filename|pathname)\b", "record", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\w+(?:_file|_path|_filename|_pathname)\b", "data-product descriptor", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(local project artifact|DraftPaper project|stage-owned|manifest|workflow\.html)\b", "processed research evidence", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\blocal manuscript writing\b", "scientific description", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bpaper workspace\b", "analysis dataset", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bthe manuscript should describe these materials[^.]*\. ?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bprocessed research\s+processed research materials\b", "processed evidence records", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bprocessed research\s+processed research evidence\b", "processed evidence records", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:processed research materials\s*){2,}", "processed evidence records", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:processed research evidence\s*){2,}", "processed evidence records", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bprocessed research materials\b", "processed evidence records", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bprocessed research evidence\b", "processed evidence records", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bcopied into this processed evidence records under processed evidence records\b", "retained as compact processed evidence records", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bunder processed evidence records\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bthis processed evidence records\b", "processed evidence records", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bnot copied into the processed evidence records\b", "not duplicated in full", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(source and background spectral products)(?:/\1)+\b", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(effective-area response products)(?:/\1)+\b", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(energy-redistribution response products)(?:/\1)+\b", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(products)\s+\1\b", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(source)\s+\1\b", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _tokenize_column_name(name: str) -> set[str]:
    return {token for token in re.split(r"[^A-Za-z0-9]+", name.lower()) if token}


def _is_access_descriptor_column(name: str) -> bool:
    tokens = _tokenize_column_name(name)
    if tokens & {"path", "pathname", "filename", "dir", "directory", "folder", "url", "uri", "local", "server"}:
        return True
    return False


def _astronomy_product_label(name: str) -> str | None:
    lowered = name.lower()
    if any(token in lowered for token in ["pha", "spectrum", "spectral"]):
        return "source and background spectral products"
    if "arf" in lowered:
        return "effective-area response products"
    if "rmf" in lowered:
        return "energy-redistribution response products"
    if re.search(r"(?:^|[_-])lc(?:[_-]|$)", lowered) or "light_curve" in lowered or "lightcurve" in lowered:
        return "source and background light-curve products"
    if "evt" in lowered or "event" in lowered:
        return "event products"
    if "exp" in lowered or "exposure" in lowered:
        return "exposure products"
    if "flux" in lowered or "hardness" in lowered or "wxt" in lowered or "fxt" in lowered:
        return _manuscript_clean_text(name)
    return None


def _variable_groups(files: list[dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "remote_sensing_indicators": [],
        "response_variables": [],
        "nitrogen_related_proxies": [],
        "environmental_covariates": [],
        "identifiers_or_metadata": [],
    }
    for item in files:
        for column in item.get("columns") or []:
            name = str(column)
            lowered = name.lower()
            astronomy_label = _astronomy_product_label(name)
            if astronomy_label:
                target = "astronomical_observation_products"
                label = astronomy_label
                if label and label not in groups.setdefault(target, []):
                    groups[target].append(label)
                continue
            if _is_access_descriptor_column(name):
                continue
            if any(token in lowered for token in ["ndvi", "evi", "savi", "vegetation", "lai"]):
                target = "remote_sensing_indicators"
            elif any(token in lowered for token in ["yield", "biomass", "production", "response", "target"]):
                target = "response_variables"
            elif any(token in lowered for token in ["nitrogen", "tnc", "no2", "n2o", "nitrate", "ammonium"]):
                target = "nitrogen_related_proxies"
            elif any(token in lowered for token in ["temperature", "precip", "soil", "clay", "sand", "carbon", "density", "evapotranspiration"]) or "ph" in _tokenize_column_name(name):
                target = "environmental_covariates"
            elif any(token in lowered for token in ["id", "source", "sheet", "file", "date", "time", "month", "crop"]):
                target = "identifiers_or_metadata"
            else:
                continue
            label = _manuscript_clean_text(name)
            if label not in groups[target]:
                groups[target].append(label)
    return {key: values[:12] for key, values in groups.items() if values}


def _data_source_summary(inventory: dict[str, Any]) -> str:
    local_files = inventory.get("files") or []
    processed = [item for item in local_files if item.get("kind") == "processed"]
    raw = [item for item in local_files if item.get("kind") == "raw"]
    remote = inventory.get("remote_sources") or []
    if remote:
        descriptions = [_manuscript_clean_text(item.get("description") or item.get("local_summary")) for item in remote]
        descriptions = [item for item in descriptions if item]
        if descriptions:
            return "The study uses remote or server-side research products that are converted into compact analysis-ready summaries: " + " ".join(descriptions[:2])
        return "The data source includes remote or server-side resources, with locally available processed artifacts used for manuscript writing."
    if processed and raw:
        return "The study uses locally prepared processed tables derived from user-supplied raw research data."
    if processed:
        return "The study uses locally supplied processed tables as the accessible evidence base."
    if raw:
        return "The study uses locally supplied raw research data that have been inventoried for analysis readiness."
    return "The current project does not yet contain a clear local or remote data source description."


def _data_content_summary(inventory: dict[str, Any], groups: dict[str, list[str]]) -> str:
    rows = int(inventory.get("total_rows") or 0)
    readable = [item for item in inventory.get("files") or [] if item.get("readable") is True]
    parts = []
    if rows:
        parts.append(f"The local tabular evidence contains {rows} inventoried rows across {len(readable)} readable table(s).")
    if groups.get("remote_sensing_indicators"):
        parts.append("Remote-sensing indicators include " + ", ".join(groups["remote_sensing_indicators"][:5]) + ".")
    if groups.get("response_variables"):
        parts.append("The response or outcome variables include " + ", ".join(groups["response_variables"][:5]) + ".")
    if groups.get("nitrogen_related_proxies"):
        parts.append("Nitrogen-related proxy variables include " + ", ".join(groups["nitrogen_related_proxies"][:5]) + ".")
    if groups.get("astronomical_observation_products"):
        parts.append("Astronomical observation products include " + ", ".join(groups["astronomical_observation_products"][:6]) + ".")
    if groups.get("environmental_covariates"):
        parts.append("Environmental covariates include " + ", ".join(groups["environmental_covariates"][:6]) + ".")
    return " ".join(parts) or "The available metadata are insufficient to describe the data content without additional user notes."


def _processing_summary(inventory: dict[str, Any], observations: list[dict[str, Any]]) -> str:
    cleaned_notes = []
    for item in observations:
        if item.get("kind") not in {"processing_note", "agent_analysis", "data_summary"}:
            continue
        note = _manuscript_clean_text(item.get("text"))
        lowered = note.lower()
        artifact_terms = sum(
            term in lowered
            for term in [
                "processed research materials",
                "primary local project materials",
                "key generated training inputs",
                "verified source folders",
                "training execution check",
            ]
        )
        if artifact_terms >= 2:
            continue
        cleaned_notes.append(note)
    notes = " ".join(cleaned_notes)
    if notes:
        return notes[:1200]
    processed_count = sum(1 for item in inventory.get("files") or [] if item.get("kind") == "processed")
    if inventory.get("remote_source_count"):
        return "Large remote products are treated as read-only source material, and compact analysis-ready records are produced by selective extraction or streaming rather than by bulk copying."
    if processed_count:
        return "Processed analysis-ready records provide the scientific content and provenance for the Data section."
    return "No explicit preprocessing narrative has been recorded; omit detailed processing claims unless the user provides them."


def _data_code_summary(data_code_manifest: dict[str, Any]) -> str:
    files = data_code_manifest.get("files") if isinstance(data_code_manifest, dict) else []
    if not isinstance(files, list) or not files:
        return "No dedicated data acquisition or preprocessing code summary is available yet; the data description is therefore based on recorded observations and the data inventory."
    roles = sorted({str(item.get("code_role") or "data_processing") for item in files if isinstance(item, dict)})
    canonical = [str(item.get("canonical_path") or "") for item in files if isinstance(item, dict) and item.get("canonical_path")]
    role_text = ", ".join(role.replace("_", " ") for role in roles[:4]) or "data processing"
    return (
        f"The data construction process is supported by {len(files)} data acquisition or preprocessing code record(s) covering {role_text}. "
        "These records should be interpreted as evidence for data acquisition, parsing, cleaning, or integration rather than as manuscript-visible storage details."
        + (f" The documented code route covers {len(canonical)} reusable data-processing component(s)." if canonical else "")
    )


def _evidence_number_roles(inventory: dict[str, Any], data_code_manifest: dict[str, Any]) -> dict[str, Any]:
    files = inventory.get("files") if isinstance(inventory, dict) else []
    files = files if isinstance(files, list) else []
    readable = [item for item in files if isinstance(item, dict) and item.get("readable") is True]
    roles: dict[str, Any] = {
        "inventory_total_rows": int(inventory.get("total_rows") or 0) if isinstance(inventory, dict) else 0,
        "readable_table_count": len(readable),
        "processed_table_count": sum(1 for item in files if isinstance(item, dict) and item.get("kind") == "processed"),
        "raw_table_count": sum(1 for item in files if isinstance(item, dict) and item.get("kind") == "raw"),
        "remote_source_count": int(inventory.get("remote_source_count") or 0) if isinstance(inventory, dict) else 0,
    }
    for item in readable:
        name = str(item.get("path") or item.get("name") or "").lower()
        rows = int(item.get("rows") or item.get("row_count") or 0)
        columns = [str(column).lower() for column in item.get("columns") or []]
        haystack = " ".join(columns + [name])
        if rows and any(token in name for token in ["event", "sample", "training", "model"]):
            roles["main_modeling_sample"] = max(int(roles.get("main_modeling_sample") or 0), rows)
        if rows and any(token in haystack for token in ["token", "light_curve", "lc", "mjd", "rate"]):
            roles["token_record_count"] = max(int(roles.get("token_record_count") or 0), rows)
        if any(token in haystack for token in ["pha", "arf", "rmf", "spectral", "hardness"]):
            roles["spectral_readiness_table_count"] = int(roles.get("spectral_readiness_table_count") or 0) + 1
        if rows and any(token in haystack for token in ["source_id", "source", "catalog"]):
            roles["source_catalog_record_count"] = max(int(roles.get("source_catalog_record_count") or 0), rows)
    manifest_files = data_code_manifest.get("files") if isinstance(data_code_manifest, dict) else []
    if isinstance(manifest_files, list):
        roles["data_stage_code_file_count"] = len([item for item in manifest_files if isinstance(item, dict)])
    return {key: value for key, value in roles.items() if value not in {0, "", None}}


def _data_key_facts(inventory: dict[str, Any], observations: list[dict[str, Any]], number_roles: dict[str, Any]) -> dict[str, Any]:
    """Extract manuscript-facing sample facts without exposing local file names."""
    text_sources = [
        str(item.get("text") or "")
        for item in observations
        if isinstance(item, dict) and item.get("kind") in {"processing_note", "agent_analysis", "data_summary", "method_summary"}
    ]
    text_sources.extend([str(inventory.get("description") or ""), str(inventory.get("summary") or "")])
    blob = " ".join(text_sources)
    facts: dict[str, Any] = {}
    patterns = {
        "event_count": r"\b(\d[\d,]*)\s+(?:events?|event-level samples?)\b",
        "source_count": r"\b(\d[\d,]*)\s+(?:sources?|objects?)\b",
        "token_bin_count": r"\b(\d(?:[\d,]*|\.\d+)\s*(?:M|million)?|\d[\d,]*)\s+(?:token bins?|tokens?)\b",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, blob, flags=re.I)
        if match:
            facts[key] = match.group(1).replace(",", "")
    balance = re.search(r"\b(\d+)\s*AGN\s*(?:/|and|,)?\s*(\d+)\s*XRB\b", blob, flags=re.I)
    if balance:
        facts["class_balance"] = f"{balance.group(1)} AGN and {balance.group(2)} XRB sources"
    if re.search(r"\bTDE\b", blob, flags=re.I):
        facts["stress_test_boundary"] = "TDE cases are treated as a stress-testing or boundary-evaluation group unless the verified design states that they are part of primary supervised training."
    for source_key, target_key in [
        ("main_modeling_sample", "main_modeling_sample"),
        ("token_record_count", "token_record_count"),
        ("source_catalog_record_count", "source_catalog_record_count"),
    ]:
        if number_roles.get(source_key) and target_key not in facts:
            facts[target_key] = number_roles[source_key]
    return facts


def _render_data_context_md(context: dict[str, Any]) -> str:
    lines = [
        "# Data Writing Context",
        "",
        "## Narrative Summary",
        "",
        context.get("narrative_summary", ""),
        "",
        "## Source",
        "",
        context.get("source_summary", ""),
        "",
        "## Content",
        "",
        context.get("content_summary", ""),
        "",
        "## Processing and Claim Boundary",
        "",
        context.get("processing_summary", ""),
        "",
        "## Stage-Owned Data Code",
        "",
        context.get("data_code_summary", ""),
        "",
        context.get("claim_boundary", ""),
        "",
        "## Variable Groups",
        "",
    ]
    for group, values in (context.get("variable_groups") or {}).items():
        lines.append(f"- {group}: {', '.join(values)}")
    lines.append("")
    return "\n".join(lines)


def build_data_writing_context(project: str | Path) -> dict[str, Any]:
    """Build a manuscript-facing Data context from inventory, gates, and visible observations."""
    state = load_project(project)
    inventory = _load_json(state.path, DATA_INVENTORY_OUTPUT)
    feasibility = _load_json(state.path, DATA_FEASIBILITY_JSON)
    observations = load_observations(state.path, stage="data")
    data_code_manifest = _read_optional_json(state.path / "data" / "data_code_manifest.json", {})
    groups = _variable_groups(list(inventory.get("files") or []))
    source_summary = _data_source_summary(inventory)
    content_summary = _data_content_summary(inventory, groups)
    processing_summary = _processing_summary(inventory, observations)
    data_code_summary = _data_code_summary(data_code_manifest if isinstance(data_code_manifest, dict) else {})
    number_roles = _evidence_number_roles(inventory if isinstance(inventory, dict) else {}, data_code_manifest if isinstance(data_code_manifest, dict) else {})
    key_facts = _data_key_facts(inventory if isinstance(inventory, dict) else {}, observations, number_roles)
    claim_boundary = _clean_sentence(feasibility.get("supported_claim_level"))
    if claim_boundary:
        claim_boundary = "The data support level is bounded as follows: " + claim_boundary + "."
    else:
        claim_boundary = "The claim boundary should be kept aligned with the current data feasibility decision."
    narrative_summary = " ".join([
        source_summary,
        content_summary,
        processing_summary,
        data_code_summary,
        claim_boundary,
    ]).strip()
    context = {
        "project_id": state.metadata.get("project_id"),
        "project_path": str(state.path),
        "inventory": inventory if isinstance(inventory, dict) else {},
        "feasibility": feasibility if isinstance(feasibility, dict) else {},
        "source_summary": source_summary,
        "content_summary": content_summary,
        "processing_summary": processing_summary,
        "data_code_summary": data_code_summary,
        "data_code_manifest": data_code_manifest if isinstance(data_code_manifest, dict) else {},
        "evidence_number_roles": number_roles,
        "data_key_facts": key_facts,
        "claim_boundary": claim_boundary,
        "variable_groups": groups,
        "observation_count": len(observations),
        "observations": observations,
        "narrative_summary": narrative_summary,
        "forbidden_in_manuscript": ["local filesystem paths", "raw filenames", "processed filenames", "execution commands"],
    }
    context["writing_brief"] = build_data_writing_brief(state.path, context)
    _write_json(state.path / DATA_WRITING_CONTEXT_JSON, context)
    _write_json(state.path / DATA_KEY_FACTS_JSON, key_facts)
    write_html_report(state.path / DATA_WRITING_CONTEXT_HTML, _render_data_context_md(context), title="Data Writing Context")
    _set_data_writing_manifest(state.path)
    return context


def _strip_forbidden_paths(text: str) -> str:
    return _manuscript_clean_text(text)


def _join_scientific_sentences(*parts: str) -> str:
    sentences: list[str] = []
    for part in parts:
        cleaned = _strip_forbidden_paths(_clean_sentence(part))
        if not cleaned:
            continue
        if cleaned not in sentences:
            sentences.append(cleaned)
    return " ".join(sentences).strip()


def _select_data_observation(observations: list[dict[str, Any]]) -> str:
    accepted_kinds = {"processing_note", "agent_analysis", "data_summary"}
    selected: list[str] = []
    for item in observations:
        if item.get("kind") not in accepted_kinds or not item.get("text"):
            continue
        cleaned = _strip_forbidden_paths(_clean_sentence(item.get("text")))
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if any(token in lowered for token in ["the manuscript should", "should describe", "write this", "regenerate"]):
            continue
        artifact_terms = sum(
            term in lowered
            for term in [
                "processed evidence records",
                "primary local project materials",
                "key generated training inputs",
                "verified source folders",
                "training execution check",
            ]
        )
        if artifact_terms >= 2:
            continue
        if cleaned not in selected:
            selected.append(cleaned)
        if len(selected) >= 2:
            break
    return " ".join(selected)


def _render_reference_paragraph(project_dir: Path, section_text: str) -> list[str]:
    ensure_reference_usage_plan(project_dir)
    entries = missing_entries_for_section(project_dir, "data", section_text)
    paragraphs: list[str] = []
    if not entries:
        return paragraphs
    sentences = []
    for entry in entries:
        key = str(entry.get("citation_key") or "")
        evidence = _strip_forbidden_paths(_clean_sentence(entry.get("evidence_summary") or entry.get("title")))
        if key and evidence:
            sentences.append(f"{_safe_latex_text(evidence)} \\citep{{{key}}}.")
    for index in range(0, len(sentences), 4):
        paragraphs.append(
            "The data source and empirical boundary are interpreted in relation to prior survey, dataset, and measurement evidence: "
            + " ".join(sentences[index:index + 4])
        )
    return paragraphs


def _brief_guided_data_paragraphs(context: dict[str, Any]) -> list[str]:
    brief = context.get("writing_brief") if isinstance(context.get("writing_brief"), dict) else {}
    guidance = brief.get("coverage_guidance") if isinstance(brief.get("coverage_guidance"), dict) else {}
    source = _strip_forbidden_paths(guidance.get("data_source") or context.get("source_summary", ""))
    content = _strip_forbidden_paths(guidance.get("processed_dataset") or context.get("content_summary", ""))
    processing = _strip_forbidden_paths(guidance.get("missingness_coverage") or context.get("processing_summary", ""))
    data_code = _strip_forbidden_paths(context.get("data_code_summary", ""))
    boundary = _strip_forbidden_paths(guidance.get("claim_boundary") or context.get("claim_boundary", ""))
    groups = context.get("variable_groups") if isinstance(context.get("variable_groups"), dict) else {}
    number_roles = context.get("evidence_number_roles") if isinstance(context.get("evidence_number_roles"), dict) else {}
    key_facts = context.get("data_key_facts") if isinstance(context.get("data_key_facts"), dict) else {}
    feature_sentence = ""
    if groups:
        group_names = [str(name).replace("_", " ") for name in groups.keys() if groups.get(name)]
        if group_names:
            feature_sentence = "The variables are organized around " + ", ".join(group_names[:5]) + ", which defines the scientific content available for later modeling."
    observation_text = _select_data_observation(list(context.get("observations") or []))
    if observation_text and observation_text in processing:
        observation_text = ""
    if not source:
        source = "The study data are described from the verified project evidence rather than from local storage artifacts."
    if not content:
        content = "The analysis-ready dataset is treated as the empirical basis for subsequent modeling, with the observable units and variables interpreted at the scientific level."
    if not processing:
        processing = "Data preparation is described only to the extent needed to define the usable analytical sample, coverage, and measurement boundary."
    if not feature_sentence:
        feature_sentence = "The available variables are grouped by their measurement role so that later analyses can distinguish predictors, responses, identifiers, and diagnostic quantities."
    if not boundary:
        boundary = "Claims based on these data should remain tied to the verified coverage of the available sample and should avoid unsupported population-level generalization."
    number_sentence = ""
    if number_roles:
        role_parts = []
        if number_roles.get("inventory_total_rows"):
            role_parts.append(f"{number_roles.get('inventory_total_rows')} inventoried tabular records")
        if number_roles.get("main_modeling_sample"):
            role_parts.append(f"{number_roles.get('main_modeling_sample')} records in the main modeling sample")
        if number_roles.get("token_record_count"):
            role_parts.append(f"{number_roles.get('token_record_count')} time-series or token-level records")
        if number_roles.get("spectral_readiness_table_count"):
            role_parts.append(f"{number_roles.get('spectral_readiness_table_count')} table(s) carrying spectral-readiness descriptors")
        if role_parts:
            number_sentence = "The reported counts are interpreted by role rather than as interchangeable sample sizes: " + "; ".join(role_parts) + "."
    key_fact_sentence = ""
    if key_facts:
        fact_parts = []
        if key_facts.get("event_count"):
            fact_parts.append(f"{key_facts.get('event_count')} events")
        if key_facts.get("source_count"):
            fact_parts.append(f"{key_facts.get('source_count')} sources")
        if key_facts.get("class_balance"):
            fact_parts.append(str(key_facts.get("class_balance")))
        if key_facts.get("token_bin_count"):
            fact_parts.append(f"{key_facts.get('token_bin_count')} token bins")
        if fact_parts:
            key_fact_sentence = "The manuscript-facing sample facts are " + ", ".join(fact_parts) + "."
        if key_facts.get("stress_test_boundary"):
            key_fact_sentence = _join_scientific_sentences(key_fact_sentence, str(key_facts.get("stress_test_boundary")))
    boundary_note = (
        "This boundary is reported as part of the data description because sample coverage, missing measurements, "
        "and available variable groups determine which hypotheses can be examined later in the manuscript."
    )
    paragraphs = [
        _join_scientific_sentences(source, content),
        _join_scientific_sentences(processing, data_code, feature_sentence, key_fact_sentence, number_sentence),
        _join_scientific_sentences(observation_text, boundary, boundary_note),
    ]
    return [paragraph for paragraph in paragraphs if paragraph]


def render_data_tex(context: dict[str, Any]) -> str:
    data_paragraphs = _brief_guided_data_paragraphs(context)
    if not data_paragraphs:
        data_paragraphs = ["The data section is constrained by the available verified data evidence."]
    paragraphs = ["\\section{Data}\n" + _safe_latex_text(data_paragraphs[0])]
    paragraphs.extend(_safe_latex_text(paragraph) for paragraph in data_paragraphs[1:])
    project_path = context.get("project_path")
    if project_path:
        project_dir = Path(str(project_path))
        paragraphs.extend(_render_reference_paragraph(project_dir, "\n\n".join(paragraphs)))
    return "\n\n".join(paragraphs) + "\n"


def write_data(project: str | Path) -> dict[str, Any]:
    """Write data.tex from the manuscript-facing data context."""
    state = load_project(project)
    context_path = state.path / DATA_WRITING_CONTEXT_JSON
    context = _load_json(state.path, DATA_WRITING_CONTEXT_JSON) if context_path.exists() else build_data_writing_context(state.path)
    output_path = state.path / DATA_TEX
    output_path.write_text(render_data_tex(context), encoding="utf-8")
    update_stage_status(state.path, "data_writing", "draft")
    _set_data_writing_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "data": str(output_path),
        "data_writing_context": str(state.path / DATA_WRITING_CONTEXT_JSON),
        "outputs": DATA_WRITING_OUTPUTS,
    }


def assess_data_feasibility(project: str | Path, *, min_rows: int = 30) -> dict[str, Any]:
    """Assess whether current local data can support the research plan."""
    state = load_project(project)
    quality = _load_json(state.path, DATA_QUALITY_OUTPUT)
    plan_path = state.path / "research_plan" / "research_plan.md"
    plan_text = plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""
    total_rows = int(quality.get("total_rows") or 0)
    missing_required = list(quality.get("missing_required_columns") or [])
    issues: list[str] = []
    actions: list[str] = []

    has_remote_or_processed_context = bool(quality.get("remote_source_count") or quality.get("result_artifact_count"))
    has_claim_limited_context = bool(quality.get("remote_source_count") or (total_rows < min_rows and quality.get("result_artifact_count")))
    if total_rows < min_rows and not has_remote_or_processed_context:
        issues.append(f"Total tabular row count {total_rows} is below the minimum threshold {min_rows}.")
        actions.append("Add more observations or reduce the scope to a small exploratory analysis.")
    elif total_rows < min_rows and has_remote_or_processed_context:
        actions.append(
            "Raw data are not fully local; treat available remote-source manifests, processed tables, or result artifacts as the writing context and avoid claiming unverified raw-data access."
        )
    if missing_required:
        issues.append("Required variables are missing: " + ", ".join(missing_required))
        actions.append("Provide data containing the missing variables or revise the research question.")
    if _plan_requires_external_validation(plan_text) and "external_validation_id" in missing_required:
        issues.append("The research plan requires external validation, but no external validation identifier or split is available.")
        actions.append("Collect or define an external validation dataset before making generalizable prediction claims.")
    if quality.get("overall_missing_cell_ratio", 0) > quality.get("max_missing_ratio", 0.2):
        issues.append("Missingness exceeds the configured quality threshold.")
        actions.append("Impute, filter, or recollect data before model verification.")

    if not issues and has_claim_limited_context:
        decision = "conditional_pass"
        scientific_goal_supported = True
        claim_level = "claims must be limited to the provided processed data, remote-source description, or supplied result artifacts"
        actions.append("Keep Data, Methods, and Results wording tied to the accessible processed artifacts rather than unverified raw-data access.")
    elif not issues and _plan_is_exploratory(plan_text):
        decision = "conditional_pass"
        scientific_goal_supported = True
        claim_level = "exploratory or pilot claims only"
        actions.append("Keep conclusion strength aligned with the exploratory or pilot study framing.")
    elif not issues:
        decision = "pass"
        scientific_goal_supported = True
        claim_level = "planned confirmatory or predictive claims are supportable by the current data gate"
    elif total_rows >= min_rows and not missing_required:
        decision = "conditional_pass"
        scientific_goal_supported = False
        claim_level = "exploratory or pilot claims only"
        actions.append("Lower conclusion strength and explicitly describe limitations in Results and Discussion.")
    elif has_remote_or_processed_context:
        decision = "conditional_pass"
        scientific_goal_supported = True
        claim_level = "claims must be limited to the provided processed data, remote-source description, or supplied result artifacts"
    elif total_rows >= max(3, min_rows // 2):
        decision = "revise_required"
        scientific_goal_supported = False
        claim_level = "insufficient for the stated scientific goal without revision"
    else:
        decision = "blocked"
        scientific_goal_supported = False
        claim_level = "insufficient for the stated scientific goal"

    if not actions:
        actions.append("Proceed to Methods with the current data assumptions.")

    report = {
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "scientific_goal_supported": scientific_goal_supported,
        "supported_claim_level": claim_level,
        "min_rows": min_rows,
        "observed_rows": total_rows,
        "blocking_issues": issues,
        "recommended_actions": actions,
        "stale_if_goal_changes": ["research_plan", "method_plan", "figure_plan", "code", "methods", "result_validity", "core_evidence", "results", "introduction", "data_writing", "methods_writing", "discussion", "latex", "quality_checks"],
    }
    _write_json(state.path / DATA_FEASIBILITY_JSON, report)
    (state.path / DATA_FEASIBILITY_MD).write_text(_render_feasibility_md(report), encoding="utf-8")
    role_coverage = write_data_contract_reports(state.path)
    update_stage_status(state.path, "data", "draft" if decision in {"pass", "conditional_pass"} else "failed")
    _set_data_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "data_feasibility_report": str(state.path / DATA_FEASIBILITY_JSON),
        "scientific_goal_supported": scientific_goal_supported,
        "supported_claim_level": claim_level,
        "data_role_coverage_decision": role_coverage.get("decision"),
    }


def _set_data_manifest(project_path: Path) -> None:
    manifest_path = project_path / "data" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = ["research_plan/research_plan.md", "data/raw", "data/processed"]
    manifest["output_files"] = DATA_OUTPUTS
    _write_json(manifest_path, manifest)


def _set_data_writing_manifest(project_path: Path) -> None:
    manifest_path = project_path / "data_writing" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = [
        "data/data_inventory.json",
        "data/data_quality_report.json",
        "data/data_feasibility_report.json",
        "observations",
        "references/reference_usage_plan.json",
        "results/results.tex",
    ]
    manifest["output_files"] = DATA_WRITING_OUTPUTS
    _write_json(manifest_path, manifest)


def validate_data_feasibility_for_methods(project_path: Path) -> dict[str, Any]:
    """Return feasibility report if Methods may proceed; otherwise raise DataGateError."""
    report = _load_json(project_path, DATA_FEASIBILITY_JSON)
    decision = report.get("decision")
    if decision not in {"pass", "conditional_pass"}:
        raise DataGateError(
            "Methods writing requires data feasibility decision pass or conditional_pass. Current decision: "
            + str(decision)
        )
    return report
