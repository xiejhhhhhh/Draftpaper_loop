# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .observations import load_observations
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


DATA_INVENTORY_OUTPUT = "data/data_inventory.json"
DATA_QUALITY_OUTPUT = "data/data_quality_report.json"
DATA_FEASIBILITY_JSON = "data/data_feasibility_report.json"
DATA_FEASIBILITY_MD = "data/data_feasibility_report.md"
DATA_WRITING_CONTEXT_JSON = "data/data_writing_context.json"
DATA_WRITING_CONTEXT_HTML = "data/data_writing_context.html"
DATA_TEX = "data/data.tex"
REMOTE_SOURCE_FILES = ["data/remote_sources.json", "data/source_manifest.json"]

DATA_OUTPUTS = [
    DATA_INVENTORY_OUTPUT,
    DATA_QUALITY_OUTPUT,
    DATA_FEASIBILITY_JSON,
    DATA_FEASIBILITY_MD,
    DATA_WRITING_CONTEXT_JSON,
    DATA_WRITING_CONTEXT_HTML,
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
            if any(token in lowered for token in ["ndvi", "evi", "savi", "vegetation", "lai"]):
                target = "remote_sensing_indicators"
            elif any(token in lowered for token in ["yield", "biomass", "production", "response", "target"]):
                target = "response_variables"
            elif any(token in lowered for token in ["nitrogen", "tnc", "no2", "n2o", "nitrate", "ammonium"]):
                target = "nitrogen_related_proxies"
            elif any(token in lowered for token in ["temperature", "precip", "soil", "clay", "sand", "carbon", "ph", "density", "evapotranspiration"]):
                target = "environmental_covariates"
            elif any(token in lowered for token in ["id", "source", "sheet", "file", "date", "time", "month", "crop"]):
                target = "identifiers_or_metadata"
            else:
                continue
            if name not in groups[target]:
                groups[target].append(name)
    return {key: values[:12] for key, values in groups.items() if values}


def _data_source_summary(inventory: dict[str, Any]) -> str:
    local_files = inventory.get("files") or []
    processed = [item for item in local_files if item.get("kind") == "processed"]
    raw = [item for item in local_files if item.get("kind") == "raw"]
    remote = inventory.get("remote_sources") or []
    if remote:
        descriptions = [_clean_sentence(item.get("description") or item.get("local_summary")) for item in remote]
        descriptions = [item for item in descriptions if item]
        if descriptions:
            return "The data source is represented by remote or server-side resources summarized for local manuscript writing: " + " ".join(descriptions[:2])
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
    if groups.get("environmental_covariates"):
        parts.append("Environmental covariates include " + ", ".join(groups["environmental_covariates"][:6]) + ".")
    return " ".join(parts) or "The available metadata are insufficient to describe the data content without additional user notes."


def _processing_summary(inventory: dict[str, Any], observations: list[dict[str, Any]]) -> str:
    notes = " ".join(_clean_sentence(item.get("text")) for item in observations if item.get("kind") in {"processing_note", "agent_analysis", "data_summary"})
    if notes:
        return notes[:1200]
    processed_count = sum(1 for item in inventory.get("files") or [] if item.get("kind") == "processed")
    if processed_count:
        return "Processed local artifacts are available and should be described as analysis-ready tables rather than as filesystem objects."
    return "No explicit preprocessing narrative has been recorded; omit detailed processing claims unless the user provides them."


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
    groups = _variable_groups(list(inventory.get("files") or []))
    source_summary = _data_source_summary(inventory)
    content_summary = _data_content_summary(inventory, groups)
    processing_summary = _processing_summary(inventory, observations)
    claim_boundary = _clean_sentence(feasibility.get("supported_claim_level"))
    if claim_boundary:
        claim_boundary = "The data support level is bounded as follows: " + claim_boundary + "."
    else:
        claim_boundary = "The claim boundary should be kept aligned with the current data feasibility decision."
    narrative_summary = " ".join([
        source_summary,
        content_summary,
        processing_summary,
        claim_boundary,
    ]).strip()
    context = {
        "project_id": state.metadata.get("project_id"),
        "source_summary": source_summary,
        "content_summary": content_summary,
        "processing_summary": processing_summary,
        "claim_boundary": claim_boundary,
        "variable_groups": groups,
        "observation_count": len(observations),
        "observations": observations,
        "narrative_summary": narrative_summary,
        "forbidden_in_manuscript": ["local filesystem paths", "raw filenames", "processed filenames", "execution commands"],
    }
    _write_json(state.path / DATA_WRITING_CONTEXT_JSON, context)
    write_html_report(state.path / DATA_WRITING_CONTEXT_HTML, _render_data_context_md(context), title="Data Writing Context")
    _set_data_manifest(state.path)
    return context


def _strip_forbidden_paths(text: str) -> str:
    text = re.sub(r"[A-Za-z]:\\[^\s,.;)]+", "local project artifact", text)
    text = re.sub(r"\b(?:data|results|code)/(?:raw|processed|figures|tables|scripts)/[^\s,.;)]+", "local project artifact", text)
    text = re.sub(r"\b[\w.-]+\.(?:csv|tsv|xlsx|xls|json|py|svg|png|jpg|jpeg)\b", "local project artifact", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def render_data_tex(context: dict[str, Any]) -> str:
    source = _strip_forbidden_paths(context.get("source_summary", ""))
    content = _strip_forbidden_paths(context.get("content_summary", ""))
    processing = _strip_forbidden_paths(context.get("processing_summary", ""))
    boundary = _strip_forbidden_paths(context.get("claim_boundary", ""))
    observations = [
        _strip_forbidden_paths(_clean_sentence(item.get("text")))
        for item in context.get("observations") or []
        if item.get("text")
    ]
    observation_text = " ".join(observations[:3]).strip()
    if not observation_text:
        observation_text = (
            "The data description should therefore be read as a manuscript-facing synthesis of the accessible evidence, "
            "not as a listing of local artifacts."
        )
    return (
        "\\section{Data}\n"
        f"{_safe_latex_text(source)} {_safe_latex_text(content)} The manuscript should describe these materials by their scientific role, source context, measured content, temporal or spatial coverage when available, and relationship to the stated research question rather than by local storage names.\n\n"
        f"{_safe_latex_text(processing)} This construction step is important because the subsequent methods section can only make claims that are supported by analysis-ready variables and documented preprocessing decisions. When raw access is incomplete or the working material is a processed export, the text should state that boundary directly while still explaining what the processed records represent scientifically.\n\n"
        f"{_safe_latex_text(observation_text)} {_safe_latex_text(boundary)} These constraints define the scope of the empirical claims: the data section should make clear what evidence is available, how it was made usable, and which conclusions would require additional observations, external validation data, or more complete provenance before they could be stated more strongly.\n"
    )


def write_data(project: str | Path) -> dict[str, Any]:
    """Write data.tex from the manuscript-facing data context."""
    state = load_project(project)
    context_path = state.path / DATA_WRITING_CONTEXT_JSON
    context = _load_json(state.path, DATA_WRITING_CONTEXT_JSON) if context_path.exists() else build_data_writing_context(state.path)
    output_path = state.path / DATA_TEX
    output_path.write_text(render_data_tex(context), encoding="utf-8")
    update_stage_status(state.path, "data", "draft")
    _set_data_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "data": str(output_path),
        "data_writing_context": str(state.path / DATA_WRITING_CONTEXT_JSON),
        "outputs": DATA_OUTPUTS,
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
        "stale_if_goal_changes": ["research_plan", "introduction", "method_plan", "figure_plan", "code", "methods", "result_validity", "results", "discussion", "latex", "quality_checks"],
    }
    _write_json(state.path / DATA_FEASIBILITY_JSON, report)
    (state.path / DATA_FEASIBILITY_MD).write_text(_render_feasibility_md(report), encoding="utf-8")
    update_stage_status(state.path, "data", "draft" if decision in {"pass", "conditional_pass"} else "failed")
    _set_data_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "data_feasibility_report": str(state.path / DATA_FEASIBILITY_JSON),
        "scientific_goal_supported": scientific_goal_supported,
        "supported_claim_level": claim_level,
    }


def _set_data_manifest(project_path: Path) -> None:
    manifest_path = project_path / "data" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = ["research_plan/research_plan.md", "data/raw", "data/processed"]
    manifest["output_files"] = DATA_OUTPUTS
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
