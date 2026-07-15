# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .data_contracts import normalize_roles
from .discipline import infer_discipline_from_text
from .discipline_modules import get_discipline_module
from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


DATA_ACCESS_PROFILE_JSON = "data/data_access_profile.json"
DATA_ACQUISITION_PLAN_JSON = "data/data_acquisition_plan.json"
DATA_ACQUISITION_PLAN_HTML = "data/data_acquisition_plan.html"
DATA_SOURCE_MANIFEST_CSV = "data/data_source_manifest.csv"
DATA_ACCESS_LOG_CSV = "data/data_access_log.csv"
DATA_PROVENANCE_JSON = "data/data_provenance.json"
DATA_COMPLETENESS_REPORT_HTML = "data/data_completeness_report.html"
DATA_ACQUISITION_TASKS_JSON = "data/data_acquisition_tasks.json"
DATA_ACQUISITION_TASKS_HTML = "data/data_acquisition_tasks.html"
DATA_CODE_MANIFEST_JSON = "data/data_code_manifest.json"
EXTERNAL_DATA_LOCATORS_JSON = "data/external_data_locators.json"
EXTERNAL_DATA_LOCATORS_PRIVATE_JSON = "data/external_data_locators.private.json"
DATA_SOURCE_CONTRACT_JSON = "data/data_source_contract.json"
DATA_FINGERPRINT_MANIFEST_JSON = "data/data_fingerprint_manifest.json"

DATA_ACQUISITION_OUTPUTS = [
    DATA_ACCESS_PROFILE_JSON,
    DATA_ACQUISITION_PLAN_JSON,
    DATA_ACQUISITION_PLAN_HTML,
    DATA_SOURCE_MANIFEST_CSV,
    DATA_ACCESS_LOG_CSV,
    DATA_PROVENANCE_JSON,
    DATA_COMPLETENESS_REPORT_HTML,
    DATA_ACQUISITION_TASKS_JSON,
    DATA_ACQUISITION_TASKS_HTML,
    DATA_CODE_MANIFEST_JSON,
    EXTERNAL_DATA_LOCATORS_JSON,
    EXTERNAL_DATA_LOCATORS_PRIVATE_JSON,
    DATA_SOURCE_CONTRACT_JSON,
    DATA_FINGERPRINT_MANIFEST_JSON,
]

DATA_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".xlsx",
    ".xls",
    ".json",
    ".parquet",
    ".txt",
    ".fits",
    ".fit",
    ".h5",
    ".hdf5",
    ".npy",
    ".npz",
    ".tif",
    ".tiff",
    ".nc",
    ".zip",
}

API_TERMS = [
    "api",
    "endpoint",
    "token",
    "request",
    "requests.",
    "urllib",
    "graphql",
    "google earth engine",
    "gee",
    "photon",
    "swift",
    "query",
]
REMOTE_SERVER_TERMS = [
    "ssh",
    "server",
    "remote",
    "symlink",
    "manifest",
    "/ep_data",
    "/home/",
    "scp",
    "sftp",
    "read-only",
    "read only",
]
FITS_ZIP_STREAM_TERMS = [
    "fits",
    "zip",
    "fits-in-zip",
    "stream",
    "streaming",
    "event list",
    "light curve",
    "spectrum",
    "spectral",
    "instrument archive",
    "observation product",
    "product archive",
]


class DataAcquisitionError(RuntimeError):
    """Raised when data acquisition planning cannot run."""


@dataclass(frozen=True)
class SourceScan:
    root: Path | None
    files: list[dict[str, Any]]
    text: str


def _redact(text: str) -> str:
    text = re.sub(r"(?i)(api[_-]?key|token|password|passwd|secret)\s*[:=]\s*['\"]?[^'\"\s,;]+", r"\1=<redacted>", text)
    text = re.sub(r"ghp_[A-Za-z0-9_]+", "ghp_<redacted>", text)
    return text


def _safe_relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _scan_source_root(source_root: str | Path | None) -> SourceScan:
    if not source_root:
        return SourceScan(root=None, files=[], text="")
    root = Path(source_root).expanduser().resolve()
    if not root.exists():
        raise DataAcquisitionError(f"source root does not exist: {root}")
    files: list[dict[str, Any]] = []
    text_chunks: list[str] = []
    skip_parts = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}
    candidates = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in skip_parts for part in path.parts):
            continue
        suffix = path.suffix.lower()
        if suffix not in DATA_EXTENSIONS and suffix not in {".py", ".md", ".html"}:
            continue
        priority = 0 if suffix in {".csv", ".tsv", ".parquet", ".json", ".npy", ".npz", ".h5", ".hdf5"} else 1 if len(path.relative_to(root).parts) <= 2 else 2
        candidates.append((priority, len(path.relative_to(root).parts), path.as_posix().lower(), path))
    for _priority, _depth, _name, path in sorted(candidates)[:800]:
        suffix = path.suffix.lower()
        relative = _safe_relative(root, path)
        size = path.stat().st_size
        digest = None
        if size <= 50_000_000:
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
        record = {
            "path": relative,
            "suffix": suffix,
            "size_bytes": size,
            "sha256": digest,
            "kind": "candidate_data" if suffix in DATA_EXTENSIONS else "context_file",
        }
        files.append(record)
        if suffix in {".txt", ".md", ".py", ".html"} and path.stat().st_size <= 250_000 and len(" ".join(text_chunks)) < 90_000:
            try:
                snippet = path.read_text(encoding="utf-8-sig", errors="replace")[:4000]
            except OSError:
                snippet = ""
            if snippet:
                text_chunks.append(f"{relative}\n{_redact(snippet)}")
    return SourceScan(root=root, files=files, text="\n".join(text_chunks))


def _core_project_text(state: Any) -> str:
    chunks = [
        str(state.metadata.get("idea") or ""),
        str(state.metadata.get("field") or ""),
        str(state.metadata.get("target_journal") or ""),
    ]
    for relative in [
        "research_plan/research_plan.md",
        "data/data_writing_context.json",
        "methods/method_requirements.json",
        "references/literature_review_notes.html",
    ]:
        path = state.path / relative
        if path.exists() and path.stat().st_size <= 250_000:
            chunks.append(_redact(path.read_text(encoding="utf-8-sig", errors="replace")[:5000]))
    return "\n".join(chunks)


def _project_text(state: Any, source_scan: SourceScan) -> str:
    return "\n".join([
        _core_project_text(state),
        source_scan.text,
        " ".join(str(item.get("path") or "") for item in source_scan.files[:300]),
    ])


def _local_project_files(project_path: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for base in [project_path / "data" / "raw", project_path / "data" / "processed", project_path / "results" / "tables", project_path / "results" / "figures"]:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.suffix.lower() not in DATA_EXTENSIONS and base.name != "figures":
                continue
            files.append({
                "path": path.relative_to(project_path).as_posix(),
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "kind": "local_project_artifact",
            })
    return files


def _connector_profile(name: str, detected: bool, confidence: str, evidence: list[str], actions: list[str], risks: list[str]) -> dict[str, Any]:
    return {
        "connector": name,
        "detected": detected,
        "confidence": confidence if detected else "none",
        "evidence": evidence[:12],
        "planned_actions": actions,
        "risks": risks,
        "fetch_policy": "plan_and_inventory_first",
    }


def _connector_profiles(project_files: list[dict[str, Any]], source_scan: SourceScan, text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    source_data_files = [item for item in source_scan.files if item.get("kind") == "candidate_data"]
    local_evidence = [item["path"] for item in (project_files + source_data_files)[:12]]
    api_evidence = [term for term in API_TERMS if term in lowered]
    remote_evidence = [term for term in REMOTE_SERVER_TERMS if term in lowered]
    fits_zip_evidence = [term for term in FITS_ZIP_STREAM_TERMS if term in lowered]
    profiles = [
        _connector_profile(
            "local_files",
            bool(local_evidence),
            "high" if len(local_evidence) >= 3 else "medium",
            local_evidence,
            [
                "Inventory local raw, processed, table, and result artifacts without using filenames as manuscript evidence.",
                "Summarize scientific content, variable groups, coverage, and preprocessing status into data context.",
            ],
            ["Local files may be processed exports rather than raw data; provenance must be stated explicitly."],
        ),
        _connector_profile(
            "api_access",
            bool(api_evidence),
            "high" if len(api_evidence) >= 3 else "medium",
            api_evidence,
            [
                "Record API endpoint family, query scope, authentication mode, rate-limit assumptions, and cache policy.",
                "Run a small access check or use an existing access log before any large download.",
            ],
            ["API tokens and credentials must be stored outside tracked project files.", "API availability can change, so cache and access logs are part of reproducibility."],
        ),
        _connector_profile(
            "remote_server",
            bool(remote_evidence),
            "high" if len(remote_evidence) >= 3 else "medium",
            remote_evidence,
            [
                "Create a remote manifest before analysis and keep protected data directories read-only.",
                "Prefer server-side processing plus local summary tables when raw data are too large or inaccessible.",
            ],
            ["Remote paths are not manuscript evidence by themselves; local manifests and processed summaries must be preserved."],
        ),
        _connector_profile(
            "fits_zip_stream",
            bool(fits_zip_evidence),
            "high" if len(fits_zip_evidence) >= 3 else "medium",
            fits_zip_evidence,
            [
                "Build an event-level product manifest before any large remote read.",
                "Inspect ZIP/FITS headers and required members without full extraction.",
                "Stream compact event, current-observation, history, spectral inventory, parse-status, and quality tables back to the local project.",
            ],
            [
                "FITS/ZIP stream workflows require explicit provenance and parse-status reports.",
                "Raw observation products may remain remote, so manuscript claims must rely on local processed summaries and documented access logs.",
            ],
        ),
    ]
    return profiles


def _access_modes(profiles: list[dict[str, Any]]) -> list[str]:
    return [str(profile["connector"]) for profile in profiles if profile.get("detected")]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _connector_names(profile: dict[str, Any]) -> list[str]:
    names = [str(item.get("connector")) for item in profile.get("connectors") or [] if item.get("detected")]
    for name in ["local_files", "api_access", "remote_server", "fits_zip_stream"]:
        if name not in names:
            names.append(name)
    return names


def _suggest_connectors_for_need(need: str, discipline: str, available: list[str]) -> list[str]:
    need_text = need.lower()
    preferred: list[str]
    if any(token in need_text for token in ["spatial", "coordinate", "region", "raster", "geotiff", "earth engine"]):
        preferred = ["local_files", "api_access", "remote_server"]
    elif any(token in need_text for token in ["catalog", "cross", "label", "class", "source", "photometric", "spectral", "light", "cadence", "exposure"]):
        preferred = ["fits_zip_stream", "api_access", "remote_server", "local_files"]
    elif any(token in need_text for token in ["quality", "qc", "flag", "cloud", "mask"]):
        preferred = ["local_files", "api_access", "remote_server"]
    elif any(token in need_text for token in ["target", "predictor", "feature", "group", "time"]):
        preferred = ["local_files", "remote_server", "api_access"]
    else:
        preferred = ["local_files", "api_access", "remote_server"]
    if discipline == "geography" and "api_access" not in preferred:
        preferred.append("api_access")
    if discipline == "astronomy":
        for connector in ["fits_zip_stream", "remote_server"]:
            if connector not in preferred:
                preferred.append(connector)
    result = [name for name in preferred if name in available]
    for name in available:
        if name not in result:
            result.append(name)
    return result[:3]


def _task_id(source: str, code: str, needed_data: list[str]) -> str:
    digest = abs(hash((source, code, tuple(needed_data)))) % 10_000_000
    return f"DQ-{digest:07d}"


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _task_from_analysis_revision(raw: dict[str, Any], *, discipline: str, available_connectors: list[str]) -> dict[str, Any] | None:
    feasibility = raw.get("feasibility") if isinstance(raw.get("feasibility"), dict) else {}
    if feasibility.get("status") != "blocked_missing_data":
        return None
    needed = _clean_list(feasibility.get("missing_required_roles"))
    optional = _clean_list(feasibility.get("missing_optional_roles"))
    if not needed:
        return None
    suggested: list[str] = []
    for need in needed:
        for connector in _suggest_connectors_for_need(need, discipline, available_connectors):
            if connector not in suggested:
                suggested.append(connector)
    return {
        "task_id": _task_id("analysis_revision", str(raw.get("task_id") or raw.get("operation_family") or ""), needed),
        "source": "analysis_revision",
        "source_id": str(raw.get("task_id") or ""),
        "source_code": ", ".join(_clean_list(raw.get("source_codes"))),
        "title": f"Acquire data required for {raw.get('operation_family') or 'review-task rerun'}",
        "needed_data": needed,
        "optional_data": optional,
        "suggested_connectors": suggested,
        "requires_user_confirmation": True,
        "confirmation_question": str(raw.get("fallback_if_missing") or "Confirm whether these missing data roles can be supplied or accessed."),
        "recommended_next_command": "prepare-data-acquisition",
        "status": "pending_user_confirmation",
    }


def _infer_needed_data_from_text(text: str) -> list[str]:
    lowered = text.lower()
    needs: list[str] = []
    rules = [
        ("spatial_group_or_coordinates", ["coordinate", "coordinates", "spatial", "region", "administrative", "plot", "field", "grid", "block"]),
        ("time", ["year", "date", "time", "temporal", "season", "cadence", "interval"]),
        ("quality_flag", ["quality", "qc", "flag", "cloud", "mask", "signal-to-noise", "exposure"]),
        ("class_label", ["label", "class", "catalog", "source class", "rare class"]),
        ("external_validation", ["external validation", "holdout", "independent", "field-holdout", "survey-holdout"]),
        ("predictors", ["predictor", "feature", "covariate", "variable"]),
        ("target", ["target", "response", "outcome", "yield"]),
    ]
    for role, terms in rules:
        if any(term in lowered for term in terms):
            needs.append(role)
    return needs


def _task_from_review_issue(raw: dict[str, Any], *, source: str, discipline: str, available_connectors: list[str]) -> dict[str, Any] | None:
    target_stage = str(raw.get("target_stage") or "")
    if target_stage not in {"data", "methods", "method_plan", "result_validity"}:
        return None
    text = " ".join(str(raw.get(key) or "") for key in ["title", "reason", "rationale", "required_user_input", "confirmation_question", "code"])
    needed = _infer_needed_data_from_text(text)
    if not needed and target_stage == "data":
        needed = ["data_source_or_processed_artifact"]
    if not needed:
        return None
    suggested: list[str] = []
    for need in needed:
        for connector in _suggest_connectors_for_need(need, discipline, available_connectors):
            if connector not in suggested:
                suggested.append(connector)
    question = str(raw.get("required_user_input") or raw.get("confirmation_question") or "Confirm whether the needed data can be supplied, queried, or summarized.")
    return {
        "task_id": _task_id(source, str(raw.get("issue_id") or raw.get("code") or ""), needed),
        "source": source,
        "source_id": str(raw.get("issue_id") or ""),
        "source_code": str(raw.get("code") or raw.get("route_id") or ""),
        "title": str(raw.get("title") or "Acquire data requested by reviewer/rescue feedback"),
        "needed_data": needed,
        "suggested_connectors": suggested,
        "requires_user_confirmation": bool(raw.get("requires_user_confirmation", True)),
        "confirmation_question": question,
        "recommended_next_command": "prepare-data-acquisition",
        "status": "pending_user_confirmation",
    }


def _task_from_missing_roles(
    *,
    source: str,
    source_code: str,
    title: str,
    missing_roles: list[str],
    discipline: str,
    available_connectors: list[str],
    confirmation_question: str,
) -> dict[str, Any] | None:
    needed = normalize_roles(missing_roles)
    if not needed:
        return None
    suggested: list[str] = []
    for need in needed:
        for connector in _suggest_connectors_for_need(need, discipline, available_connectors):
            if connector not in suggested:
                suggested.append(connector)
    return {
        "task_id": _task_id(source, source_code, needed),
        "source": source,
        "source_id": source_code,
        "source_code": source_code,
        "title": title,
        "needed_data": needed,
        "suggested_connectors": suggested,
        "requires_user_confirmation": True,
        "confirmation_question": confirmation_question,
        "recommended_next_command": "prepare-data-acquisition",
        "status": "pending_user_confirmation",
    }


def _tasks_from_data_role_coverage(project_path: Path, *, discipline: str, available_connectors: list[str]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    coverage = _read_json(project_path / "data" / "data_role_coverage_report.json")
    if coverage:
        task = _task_from_missing_roles(
            source="data_role_coverage",
            source_code=str(coverage.get("source") or "data_role_coverage_report"),
            title="Acquire data roles required by the research-plan figure contracts",
            missing_roles=list(coverage.get("blocking_missing_roles") or coverage.get("missing_roles") or []),
            discipline=discipline,
            available_connectors=available_connectors,
            confirmation_question="Confirm whether these missing data roles can be supplied, queried, or replaced by documented processed artifacts before figure code generation.",
        )
        if task:
            tasks.append(task)

    feasibility = _read_json(project_path / "research_plan" / "research_plan_feasibility_report.json")
    for item in feasibility.get("figure_assessments") or []:
        if not isinstance(item, dict):
            continue
        missing_roles = list(item.get("missing_data_roles") or [])
        if not missing_roles:
            continue
        figure_id = str(item.get("figure_id") or "planned_figure")
        task = _task_from_missing_roles(
            source="research_plan_feasibility",
            source_code=figure_id,
            title=f"Acquire data needed for planned main figure {figure_id}",
            missing_roles=missing_roles,
            discipline=discipline,
            available_connectors=available_connectors,
            confirmation_question="Confirm whether the missing figure-level data roles can be obtained before rerunning plan-figures and assess-figure-contracts.",
        )
        if task:
            tasks.append(task)
    return tasks


def _data_acquisition_tasks(project_path: Path, profile: dict[str, Any]) -> dict[str, Any]:
    discipline = str((profile.get("discipline_profile") or {}).get("discipline") or "default")
    available = _connector_names(profile)
    tasks: list[dict[str, Any]] = []

    tasks.extend(_tasks_from_data_role_coverage(project_path, discipline=discipline, available_connectors=available))

    analysis_revision = _read_json(project_path / "review" / "actionable_analysis_tasks.json")
    for raw in analysis_revision.get("tasks") or []:
        if isinstance(raw, dict):
            task = _task_from_analysis_revision(raw, discipline=discipline, available_connectors=available)
            if task:
                tasks.append(task)

    sources = [
        ("review_engineering", project_path / "review" / "review_engineering_plan.json", "issues"),
        ("statistical_rescue", project_path / "review" / "statistical_rescue_plan.json", "recommended_routes"),
        ("revision_plan", project_path / "review" / "revision_plan.json", "issues"),
        ("gate_failure_diagnosis", project_path / "review" / "gate_failure_diagnosis.json", "issues"),
    ]
    for source, path, key in sources:
        payload = _read_json(path)
        for raw in payload.get(key) or []:
            if isinstance(raw, dict):
                task = _task_from_review_issue(raw, source=source, discipline=discipline, available_connectors=available)
                if task:
                    tasks.append(task)

    unique: dict[tuple[str, tuple[str, ...], str], dict[str, Any]] = {}
    for task in tasks:
        key = (task["source"], tuple(task.get("needed_data") or []), str(task.get("source_code") or ""))
        unique.setdefault(key, task)
    task_list = list(unique.values())
    return {
        "status": "tasks_written" if task_list else "no_review_data_acquisition_task",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "discipline_profile": profile.get("discipline_profile") or {},
        "available_connectors": available,
        "task_count": len(task_list),
        "tasks": task_list,
    }


def _render_tasks_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Data Acquisition Tasks",
        "",
        f"Status: {payload.get('status')}",
        "",
        f"Task count: {payload.get('task_count', 0)}",
        "",
    ]
    if not payload.get("tasks"):
        lines.append("No reviewer/rescue missing-data request was found.")
        return "\n".join(lines)
    for task in payload.get("tasks") or []:
        lines.extend([
            f"## {task['task_id']}: {task['title']}",
            "",
            f"- Source: {task['source']}",
            f"- Source code: {task.get('source_code') or 'none'}",
            f"- Needed data: {', '.join(task.get('needed_data') or [])}",
            f"- Suggested connectors: {', '.join(task.get('suggested_connectors') or [])}",
            f"- Requires user confirmation: {task.get('requires_user_confirmation')}",
            f"- Confirmation question: {task.get('confirmation_question')}",
            "",
        ])
    return "\n".join(lines)


def classify_data_access(project: str | Path, *, source_root: str | Path | None = None) -> dict[str, Any]:
    state = load_project(project)
    source_scan = _scan_source_root(source_root)
    project_files = _local_project_files(state.path)
    core_text = _core_project_text(state)
    text = _project_text(state, source_scan)
    discipline_profile = infer_discipline_from_text(core_text)
    if discipline_profile.get("discipline") == "default":
        discipline_profile = infer_discipline_from_text(text)
    connectors = _connector_profiles(project_files, source_scan, text)
    detected = _access_modes(connectors)
    if not detected:
        detected = ["user_input_required"]
    profile = {
        "status": "classified",
        "generated_at": utc_now(),
        "project_path": str(state.path),
        "source_root": str(source_scan.root) if source_scan.root else "",
        "discipline_profile": discipline_profile,
        "access_modes": detected,
        "connectors": connectors,
        "source_scan": {
            "file_count": len(source_scan.files),
            "candidate_data_file_count": sum(1 for item in source_scan.files if item.get("kind") == "candidate_data"),
            "context_file_count": sum(1 for item in source_scan.files if item.get("kind") == "context_file"),
            "files": source_scan.files,
        },
        "shared_with_review_engines": True,
    }
    _write_json(state.path / DATA_ACCESS_PROFILE_JSON, profile)
    return profile


def _manifest_rows(profile: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for connector in profile.get("connectors") or []:
        if not connector.get("detected"):
            continue
        evidence = connector.get("evidence") or []
        rows.append({
            "source_id": str(connector.get("connector")),
            "access_mode": str(connector.get("connector")),
            "discipline": str((profile.get("discipline_profile") or {}).get("discipline") or "default"),
            "evidence": "; ".join(str(item) for item in evidence[:8]),
            "fetch_policy": str(connector.get("fetch_policy") or ""),
            "status": "planned",
            "notes": "Connector was detected during plan-first data acquisition classification.",
        })
    if not rows:
        rows.append({
            "source_id": "user_input_required",
            "access_mode": "unknown",
            "discipline": str((profile.get("discipline_profile") or {}).get("discipline") or "default"),
            "evidence": "",
            "fetch_policy": "ask_user_before_fetching",
            "status": "blocked",
            "notes": "No data access mode could be inferred from project state.",
        })
    return rows


def _discipline_connector_catalog(profile: dict[str, Any]) -> list[dict[str, Any]]:
    module = get_discipline_module(profile.get("discipline_profile") or {})
    return module.data_acquisition_hints({"profile": profile})


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _render_plan_markdown(plan: dict[str, Any]) -> str:
    discipline = plan["discipline_profile"].get("discipline")
    lines = [
        "# Data Acquisition Plan",
        "",
        f"Discipline: {discipline}",
        "",
        f"Access modes: {', '.join(plan.get('access_modes') or [])}",
        "",
        "## Connector Plan",
        "",
    ]
    for connector in plan.get("connectors") or []:
        lines.extend([
            f"### {connector['connector']}",
            "",
            f"- Detected: {connector['detected']}",
            f"- Confidence: {connector['confidence']}",
            f"- Evidence: {', '.join(str(item) for item in connector.get('evidence') or []) or 'None'}",
            "",
        ])
        for action in connector.get("planned_actions") or []:
            lines.append(f"- {action}")
        lines.append("")
    lines.extend(["## Discipline Data Connectors", ""])
    for connector in plan.get("discipline_connector_catalog") or []:
        lines.extend([
            f"### {connector.get('display_name') or connector.get('connector_id')}",
            "",
            f"- Connector id: `{connector.get('connector_id')}`",
            f"- Access modes: {', '.join(connector.get('access_modes') or [])}",
            f"- Packages: {', '.join(connector.get('packages') or []) or 'none'}",
            f"- Feasibility: `{connector.get('feasibility_status')}`",
            f"- Missing packages: {', '.join(connector.get('missing_packages') or []) or 'none'}",
            f"- Missing credential env vars: {', '.join(connector.get('missing_env_vars') or []) or 'none'}",
            f"- Data formats: {', '.join(connector.get('data_formats') or [])}",
            "",
        ])
        for action in connector.get("download_or_access") or []:
            lines.append(f"- {action}")
        lines.append("")
    lines.extend(["## Completeness Gate", ""])
    for item in plan.get("completeness_checks") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Reviewer/Rescue Data Requests", ""])
    acquisition_tasks = plan.get("data_acquisition_tasks") or {}
    lines.append(f"Task count: {acquisition_tasks.get('task_count', 0)}")
    for task in acquisition_tasks.get("tasks") or []:
        lines.append(f"- {task['task_id']}: {', '.join(task.get('needed_data') or [])} via {', '.join(task.get('suggested_connectors') or [])}")
    lines.extend(["", "## Review Linkage", "", plan.get("review_linkage", "")])
    return "\n".join(lines)


def prepare_data_acquisition(project: str | Path, *, source_root: str | Path | None = None) -> dict[str, Any]:
    state = load_project(project)
    effective_source_root = source_root
    if effective_source_root is None:
        existing_locator = _read_json(state.path / EXTERNAL_DATA_LOCATORS_PRIVATE_JSON)
        existing_root = str(existing_locator.get("source_root") or "").strip()
        if existing_root:
            effective_source_root = existing_root
    profile = classify_data_access(state.path, source_root=effective_source_root)
    binding_plan = _read_json(state.path / "research_plan" / "plugin_binding_plan.json")
    bound_data_plugins = [
        item for item in binding_plan.get("bindings") or []
        if isinstance(item, dict) and item.get("kind") == "data"
    ]
    acquisition_tasks = _data_acquisition_tasks(state.path, profile)
    discipline_connector_catalog = _discipline_connector_catalog(profile)
    plan = {
        "status": "data_acquisition_plan_written",
        "generated_at": utc_now(),
        "project_path": str(state.path),
        "source_root": profile.get("source_root", ""),
        "discipline_profile": profile["discipline_profile"],
        "access_modes": profile["access_modes"],
        "connectors": profile["connectors"],
        "discipline_connector_catalog": discipline_connector_catalog,
        "plugin_binding_plan": "research_plan/plugin_binding_plan.json" if binding_plan else None,
        "bound_data_plugins": bound_data_plugins,
        "data_acquisition_tasks": acquisition_tasks,
        "completeness_checks": [
            "Every detected connector must provide a local manifest, access log, or processed summary before manuscript writing.",
            "Credentials, API keys, passwords, and private tokens must not be written to tracked project files.",
            "If raw data are inaccessible or too large, the loop may proceed only from documented processed tables, result artifacts, and explicit claim boundaries.",
            "Review and rescue engines should consume this profile before asking for additional data or rerunning analysis code.",
        ],
        "review_linkage": (
            "The data acquisition profile uses the same discipline profile as the review-engine layer. "
            "Reviewer or rescue issues that require additional data should map back to these connector types instead of hard-coding a field-specific package."
        ),
        "outputs": DATA_ACQUISITION_OUTPUTS,
    }
    _write_json(state.path / DATA_ACQUISITION_TASKS_JSON, acquisition_tasks)
    write_html_report(state.path / DATA_ACQUISITION_TASKS_HTML, _render_tasks_markdown(acquisition_tasks), title="Data Acquisition Tasks")
    _write_json(state.path / DATA_ACQUISITION_PLAN_JSON, plan)
    source_root_value = str(profile.get("source_root") or "")
    locator_entries = list(((profile.get("source_scan") or {}).get("files") or []))
    public_entries = [
        {
            "path_id": f"asset_{index:04d}",
            "path": item.get("path"),
            "relative_path": item.get("path"),
            "size_bytes": item.get("size_bytes"),
            "sha256": item.get("sha256"),
            "kind": item.get("kind"),
        }
        for index, item in enumerate(locator_entries, start=1)
    ]
    _write_json(state.path / EXTERNAL_DATA_LOCATORS_JSON, {
        "schema_version": "dpl.external_data_locators.v1",
        "status": "ready" if source_root_value and locator_entries else "empty",
        "generated_at": utc_now(),
        "source_id": "external_read_only_source_1",
        "source_root": "private_locator:data/external_data_locators.private.json" if source_root_value else "",
        "read_only": True,
        "private_locator": True,
        "entries": public_entries,
        "policy": "External assets are inventoried in place. Only explicitly selected derived assets may be copied into the project; source data remain read-only.",
    })
    _write_json(state.path / EXTERNAL_DATA_LOCATORS_PRIVATE_JSON, {
        "schema_version": "dpl.external_data_locators.private.v1",
        "status": "ready" if source_root_value else "empty",
        "generated_at": utc_now(),
        "source_id": "external_read_only_source_1",
        "source_root": source_root_value,
        "read_only": True,
        "private_locator": True,
        "entries": locator_entries,
        "tracking_policy": "machine_local_private_locator_do_not_publish",
    })
    _write_json(state.path / DATA_SOURCE_CONTRACT_JSON, {
        "schema_version": "dpl.data_source_contract.v1",
        "status": "ready" if source_root_value else "empty",
        "generated_at": utc_now(),
        "sources": [{
            "source_id": "external_read_only_source_1",
            "access_mode": "read_only_in_place",
            "copy_policy": "manifest_only",
            "data_roles": sorted({str(item.get("kind") or "external_asset") for item in public_entries}),
            "locator": EXTERNAL_DATA_LOCATORS_PRIVATE_JSON,
            "public_inventory": EXTERNAL_DATA_LOCATORS_JSON,
        }] if source_root_value else [],
        "policy": "Large source datasets remain in place; only selected derived evidence enters the paper project.",
    })
    _write_json(state.path / DATA_FINGERPRINT_MANIFEST_JSON, {
        "schema_version": "dpl.data_fingerprint_manifest.v1",
        "status": "ready" if public_entries else "empty",
        "generated_at": utc_now(),
        "source_id": "external_read_only_source_1",
        "fingerprint_mode": "full_sha256_for_files_up_to_50mb_else_size_and_relative_locator",
        "entries": public_entries,
    })
    write_html_report(state.path / DATA_ACQUISITION_PLAN_HTML, _render_plan_markdown(plan), title="Data Acquisition Plan")
    rows = _manifest_rows(profile)
    _write_csv(
        state.path / DATA_SOURCE_MANIFEST_CSV,
        rows,
        ["source_id", "access_mode", "discipline", "evidence", "fetch_policy", "status", "notes"],
    )
    _write_csv(
        state.path / DATA_ACCESS_LOG_CSV,
        [{
            "event": "prepare_data_acquisition",
            "status": "planned",
            "source_root": str(profile.get("source_root") or ""),
            "access_modes": ", ".join(plan["access_modes"]),
            "notes": "No external download or credentialed access was performed.",
        }],
        ["event", "status", "source_root", "access_modes", "notes"],
    )
    _write_json(state.path / DATA_PROVENANCE_JSON, {
        "status": "written",
        "generated_at": utc_now(),
        "source_root": profile.get("source_root", ""),
        "discipline_profile": profile["discipline_profile"],
        "access_modes": profile["access_modes"],
        "credential_policy": "credentials_are_never_written_to_project_artifacts",
        "fetch_policy": "plan_first_then_user_confirmed_fetch_or_link",
    })
    _write_json(state.path / DATA_CODE_MANIFEST_JSON, {
        "status": "planned",
        "generated_at": utc_now(),
        "generator": "draftpaper_cli.data_acquisition.prepare_data_acquisition",
        "stage_owned_code_locations": ["data/scripts"],
        "script_count": 0,
        "planned_connectors": plan["access_modes"],
        "discipline_connector_catalog": discipline_connector_catalog,
        "bound_data_plugins": bound_data_plugins,
        "data_acquisition_tasks": acquisition_tasks.get("tasks") or [],
        "notes": [
            "Data collection, API access, remote manifests, and preprocessing code should be saved under data/scripts.",
            "No external download or credentialed access was performed by prepare-data-acquisition.",
        ],
    })
    write_html_report(state.path / DATA_COMPLETENESS_REPORT_HTML, _render_plan_markdown(plan), title="Data Completeness Report")
    return {
        "status": "written",
        "project_path": str(state.path),
        "discipline": profile["discipline_profile"].get("discipline"),
        "primary_discipline": profile["discipline_profile"].get("primary_discipline"),
        "secondary_disciplines": profile["discipline_profile"].get("secondary_disciplines") or [],
        "discipline_modules": profile["discipline_profile"].get("discipline_modules") or [],
        "access_modes": profile["access_modes"],
        "data_access_profile": str(state.path / DATA_ACCESS_PROFILE_JSON),
        "data_acquisition_plan": str(state.path / DATA_ACQUISITION_PLAN_JSON),
        "data_acquisition_plan_html": str(state.path / DATA_ACQUISITION_PLAN_HTML),
        "data_source_manifest": str(state.path / DATA_SOURCE_MANIFEST_CSV),
        "data_acquisition_tasks": str(state.path / DATA_ACQUISITION_TASKS_JSON),
        "data_acquisition_task_count": acquisition_tasks.get("task_count", 0),
        "outputs": DATA_ACQUISITION_OUTPUTS,
    }
