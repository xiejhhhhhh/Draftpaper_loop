# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .artifact_identity import compute_artifact_identity, sha256_file
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status


class CodeOwnershipError(RuntimeError):
    """Raised when generated or legacy code cannot be classified safely."""


CODE_OWNERSHIP_MANIFEST = "code/code_ownership_manifest.json"
DATA_CODE_MANIFEST = "data/data_code_manifest.json"
METHOD_CODE_MANIFEST = "methods/method_code_manifest.json"
FIGURE_CODE_TRACE = "results/figure_code_trace.json"

DATA_KEYWORDS = {
    "data", "fetch", "download", "stream", "select", "parse", "manifest", "catalog", "input",
    "sample", "event", "source", "build", "remote", "api", "ssh", "fits", "zip", "photon",
}
METHOD_KEYWORDS = {
    "train", "model", "transformer", "cnn", "resnet", "tcn", "baseline", "ablation",
    "validate", "validation", "metric", "classif", "regression", "analysis", "analyze",
    "feature", "loss", "fit", "predict", "evaluate",
}
PLOTTING_KEYWORDS = {"plot", "figure", "fig", "visual", "chart", "make_final", "storyboard"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return fallback


def _project_relative(project_path: Path, path: Path) -> str:
    return path.relative_to(project_path).as_posix()


def _score_keywords(text: str, keywords: set[str]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword in lowered)


def _classify_file(project_path: Path, path: Path) -> dict[str, Any]:
    relative = _project_relative(project_path, path)
    text = _read_text(path)
    if relative.startswith("data/scripts/"):
        return {
            "source_path": relative,
            "owner_stage": "data",
            "code_role": "data_acquisition_or_processing",
            "canonical_path": relative,
            "route_action": "already_stage_owned",
            "formula_count": 0,
            "formula_ids": [],
            "privacy_status": "project_local_review_required",
            "source_type": "stage_owned_code",
        }
    if relative.startswith(("methods/scripts/", "methods/src/", "methods/plotting/")):
        code_role = "figure_generation" if relative.startswith("methods/plotting/") else "method_model_or_analysis"
        formulas = _extract_formula_entries_from_text(text, source_path=relative)
        return {
            "source_path": relative,
            "owner_stage": "methods",
            "code_role": code_role,
            "canonical_path": relative,
            "route_action": "already_stage_owned",
            "formula_count": len(formulas),
            "formula_ids": [item["id"] for item in formulas],
            "privacy_status": "project_local_review_required",
            "source_type": "stage_owned_code",
        }
    haystack = f"{relative}\n{text[:6000]}"
    data_score = _score_keywords(haystack, DATA_KEYWORDS)
    method_score = _score_keywords(haystack, METHOD_KEYWORDS)
    plotting_score = _score_keywords(haystack, PLOTTING_KEYWORDS)

    if relative.startswith("code/src/"):
        owner_stage = "methods"
        code_role = "method_support_library"
        canonical_dir = "methods/src"
    elif plotting_score >= 1 and ("figure" in haystack.lower() or "plot" in haystack.lower() or path.name.startswith("make_")):
        owner_stage = "methods"
        code_role = "figure_generation"
        canonical_dir = "methods/plotting"
    elif data_score > method_score:
        owner_stage = "data"
        code_role = "data_acquisition_or_processing"
        canonical_dir = "data/scripts"
    elif method_score >= data_score and method_score > 0:
        owner_stage = "methods"
        code_role = "method_model_or_analysis"
        canonical_dir = "methods/scripts"
    else:
        owner_stage = "code"
        code_role = "shared_or_uncertain"
        canonical_dir = "code/shared"

    if "def " in text and owner_stage == "methods" and code_role != "figure_generation":
        canonical_dir = "methods/scripts"
    target_path = f"{canonical_dir}/{path.name}"
    formulas = _extract_formula_entries_from_text(text, source_path=target_path)
    return {
        "source_path": relative,
        "owner_stage": owner_stage,
        "code_role": code_role,
        "canonical_path": target_path,
        "route_action": "copy_to_stage_owned_location" if target_path != relative else "already_stage_owned",
        "formula_count": len(formulas),
        "formula_ids": [item["id"] for item in formulas],
        "privacy_status": "project_local_review_required",
        "source_type": "legacy_code_or_codex_generated",
    }


def _scan_python_files(project_path: Path) -> list[Path]:
    files: list[Path] = []
    for base in ["code", "data/scripts", "methods/scripts", "methods/src", "methods/plotting"]:
        root = project_path / base
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if path.is_file() and "__pycache__" not in path.parts:
                files.append(path)
    return files


def _render_code_manifest_html(payload: dict[str, Any], title: str) -> str:
    lines = [f"# {title}", "", "| Source | Stage | Role | Canonical path |", "| --- | --- | --- | --- |"]
    for item in payload.get("files") or []:
        lines.append(
            f"| `{item.get('source_path')}` | {item.get('owner_stage')} | {item.get('code_role')} | `{item.get('canonical_path')}` |"
        )
    return "\n".join(lines) + "\n"


def classify_code_ownership(project: str | Path) -> dict[str, Any]:
    """Classify project-local Python code into data, methods, plotting, or compatibility ownership."""
    state = load_project(project)
    files = [_classify_file(state.path, path) for path in _scan_python_files(state.path)]
    payload = {
        "status": "written",
        "project_id": state.metadata.get("project_id"),
        "generated_at": utc_now(),
        "policy": "code_is_owned_by_data_or_methods; code/ is compatibility and external-mining workspace",
        "file_count": len(files),
        "files": files,
    }
    _write_json(state.path / CODE_OWNERSHIP_MANIFEST, payload)
    write_html_report(
        state.path / "code" / "code_ownership_manifest.html",
        _render_code_manifest_html(payload, "Code Ownership Manifest"),
        title="Code Ownership Manifest",
    )
    return {
        "status": "written",
        "project_path": str(state.path),
        "manifest": str(state.path / CODE_OWNERSHIP_MANIFEST),
        "file_count": len(files),
        "files": files,
    }


def _copy_or_move(source: Path, target: Path, mode: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == target.resolve():
        return
    if mode == "move":
        shutil.move(str(source), str(target))
    else:
        shutil.copy2(source, target)


def _compat_launcher(target_relative: str) -> str:
    return (
        "from __future__ import annotations\n\n"
        "import runpy\n"
        "from pathlib import Path\n\n"
        "_HERE = Path(__file__).resolve()\n"
        "PROJECT_ROOT = next((parent for parent in _HERE.parents if (parent / 'project.json').exists()), _HERE.parents[1])\n"
        f"TARGET = PROJECT_ROOT / {target_relative!r}\n"
        "if __name__ == '__main__':\n"
        "    runpy.run_path(str(TARGET), run_name='__main__')\n"
    )


def _stage_manifest(files: list[dict[str, Any]], owner_stage: str) -> dict[str, Any]:
    selected = [item for item in files if item.get("owner_stage") == owner_stage]
    return {
        "status": "written",
        "generated_at": utc_now(),
        "owner_stage": owner_stage,
        "file_count": len(selected),
        "files": selected,
        "canonical_files": [item["canonical_path"] for item in selected],
    }


def route_stage_code(project: str | Path, *, mode: str = "copy", keep_compat_launchers: bool = True) -> dict[str, Any]:
    """Route legacy code/ scripts into stage-owned data and methods locations."""
    if mode not in {"copy", "move"}:
        raise CodeOwnershipError("mode must be copy or move")
    state = load_project(project)
    classification = classify_code_ownership(state.path)
    routed: list[dict[str, Any]] = []
    for item in classification["files"]:
        source = state.path / item["source_path"]
        target = state.path / item["canonical_path"]
        if item["owner_stage"] in {"data", "methods"}:
            _copy_or_move(source, target, mode)
            routed.append({**item, "routed": True})
            if keep_compat_launchers and item["source_path"].startswith("code/") and mode == "move":
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(_compat_launcher(item["canonical_path"]), encoding="utf-8")
        else:
            routed.append({**item, "routed": False})

    data_manifest = _stage_manifest(routed, "data")
    method_manifest = _read_json(state.path / METHOD_CODE_MANIFEST, {})
    if not isinstance(method_manifest, dict):
        method_manifest = {}
    method_manifest.update(_stage_manifest(routed, "methods"))
    existing_declared = method_manifest.get("declared_outputs") if isinstance(method_manifest.get("declared_outputs"), list) else []
    method_manifest["declared_outputs"] = existing_declared
    method_manifest.setdefault("code_layout", "stage_owned_code_with_code_compatibility_launchers")
    method_manifest["formula_source_files"] = [
        item["canonical_path"] for item in routed
        if item.get("owner_stage") == "methods" and item.get("formula_count", 0) > 0
    ]
    _write_json(state.path / DATA_CODE_MANIFEST, data_manifest)
    _write_json(state.path / METHOD_CODE_MANIFEST, method_manifest)
    write_html_report(
        state.path / "data" / "data_code_manifest.html",
        _render_code_manifest_html(data_manifest, "Data Code Manifest"),
        title="Data Code Manifest",
    )
    write_html_report(
        state.path / "methods" / "method_code_manifest.html",
        _render_code_manifest_html(method_manifest, "Method Code Manifest"),
        title="Method Code Manifest",
    )
    update_stage_status(state.path, "code", "draft")
    return {
        "status": "written",
        "project_path": str(state.path),
        "mode": mode,
        "data_code_manifest": str(state.path / DATA_CODE_MANIFEST),
        "method_code_manifest": str(state.path / METHOD_CODE_MANIFEST),
        "routed_files": routed,
    }


def build_code_provenance(project: str | Path) -> dict[str, Any]:
    """Build one project-level provenance view over data, method, and figure code."""
    state = load_project(project)
    classification = classify_code_ownership(state.path)
    payload = {
        "status": "written",
        "project_id": state.metadata.get("project_id"),
        "generated_at": utc_now(),
        "code_ownership_manifest": CODE_OWNERSHIP_MANIFEST,
        "data_code_manifest": DATA_CODE_MANIFEST if (state.path / DATA_CODE_MANIFEST).exists() else None,
        "method_code_manifest": METHOD_CODE_MANIFEST if (state.path / METHOD_CODE_MANIFEST).exists() else None,
        "figure_code_trace": FIGURE_CODE_TRACE if (state.path / FIGURE_CODE_TRACE).exists() else None,
        "file_count": classification["file_count"],
        "files": classification["files"],
    }
    _write_json(state.path / "code" / "code_provenance_manifest.json", payload)
    write_html_report(
        state.path / "code" / "code_provenance_manifest.html",
        _render_code_manifest_html(payload, "Code Provenance Manifest"),
        title="Code Provenance Manifest",
    )
    return {
        "status": "written",
        "project_path": str(state.path),
        "manifest": str(state.path / "code" / "code_provenance_manifest.json"),
        "file_count": payload["file_count"],
    }


def _extract_formula_entries_from_text(text: str, *, source_path: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pattern = re.compile(
        r"draftpaper:formula\s+id=(?P<id>[A-Za-z0-9_.:-]+)\s+latex=(?P<latex>.*?)(?:\s+variables=(?P<variables>.*))?$"
    )
    for line in text.splitlines():
        match = pattern.search(line.strip().lstrip("#").strip())
        if not match:
            continue
        variables = [item.strip() for item in str(match.group("variables") or "").split(",") if item.strip()]
        entries.append({
            "id": match.group("id"),
            "name": match.group("id").replace("_", " "),
            "latex": match.group("latex").strip(),
            "variables": variables,
            "source_path": source_path,
            "source": "code_annotation",
        })
    lowered = text.lower()
    if "cross_entropy" in lowered or "log p" in lowered:
        entries.append({
            "id": "cross_entropy",
            "name": "Cross-entropy objective",
            "latex": r"L=-\sum_i y_i \log p_i",
            "variables": ["y_i", "p_i"],
            "source_path": source_path,
            "source": "static_code_pattern",
        })
    if "softmax" in lowered:
        entries.append({
            "id": "softmax",
            "name": "Softmax normalization",
            "latex": r"p_i=\frac{\exp z_i}{\sum_j \exp z_j}",
            "variables": ["z_i", "p_i"],
            "source_path": source_path,
            "source": "static_code_pattern",
        })
    if "pearson" in lowered or "corr(" in lowered or ".corr" in lowered:
        entries.append({
            "id": "pearson_correlation",
            "name": "Pearson correlation",
            "latex": r"r=\frac{\sum_i (x_i-\bar{x})(y_i-\bar{y})}{\sqrt{\sum_i (x_i-\bar{x})^2}\sqrt{\sum_i (y_i-\bar{y})^2}}",
            "variables": ["x_i", "y_i", "r"],
            "source_path": source_path,
            "source": "static_code_pattern",
        })
    unique: dict[str, dict[str, Any]] = {}
    for entry in entries:
        unique.setdefault(entry["id"], entry)
    return list(unique.values())


def extract_method_formulas(project: str | Path) -> dict[str, Any]:
    """Build formulas from the active method contract and verified stage-owned code."""
    state = load_project(project)
    route_stage_code(state.path)
    from .methods import _read_manifest, _write_method_formulas

    run_manifest_path = state.path / "methods" / "run_manifest.yaml"
    run_manifest = _read_manifest(run_manifest_path) if run_manifest_path.exists() else {}
    _write_method_formulas(state.path, run_manifest)
    payload = _read_json(state.path / "methods" / "method_formula_manifest.json", {})
    formulas = payload.get("formulas") if isinstance(payload.get("formulas"), list) else []
    return {
        "status": "written",
        "project_path": str(state.path),
        "formula_manifest": str(state.path / "methods" / "method_formula_manifest.json"),
        "method_formulas": str(state.path / "methods" / "method_formulas.tex"),
        "formula_count": len(formulas),
    }


def trace_figures_to_code(project: str | Path) -> dict[str, Any]:
    """Trace final result figures back to stage-owned plotting or method scripts."""
    state = load_project(project)
    route_stage_code(state.path)
    metadata = _read_json(state.path / "results" / "figure_metadata.json", {})
    figures = metadata.get("figures") if isinstance(metadata, dict) else []
    plotting_files = [
        _project_relative(state.path, path)
        for path in _scan_python_files(state.path)
        if _project_relative(state.path, path).startswith(("methods/plotting/", "methods/scripts/"))
    ]
    run_manifest = _read_json(state.path / "methods" / "run_manifest.yaml", {})
    resolved_evidence = _read_json(state.path / "results" / "resolved_result_evidence.json", {})
    count_report = _read_json(state.path / "results" / "count_identity_report.json", {})
    metric_records = resolved_evidence.get("metric_evidence_records") if isinstance(resolved_evidence, dict) else []
    metric_refs = [str(item.get("metric_record_id")) for item in metric_records or [] if isinstance(item, dict) and item.get("metric_record_id")]
    count_records = count_report.get("records") if isinstance(count_report, dict) else []
    count_refs = [str(item.get("count_record_id")) for item in count_records or [] if isinstance(item, dict) and item.get("count_record_id")]
    metadata_identity = None
    metadata_path = state.path / "results" / "figure_metadata.json"
    if metadata_path.is_file():
        metadata_identity = compute_artifact_identity(metadata_path, "results/figure_metadata.json")
    transaction_id = str(run_manifest.get("run_transaction_id") or run_manifest.get("transaction_id") or run_manifest.get("run_id") or "").strip()
    traces = []
    for item in figures or []:
        figure_id = str(item.get("figure_id") or item.get("storyboard_id") or Path(str(item.get("path") or "")).stem)
        matched = []
        for relative in plotting_files:
            text = _read_text(state.path / relative)
            if figure_id in text or Path(str(item.get("path") or "")).name in text or "figure" in relative:
                matched.append(relative)
        if not matched and plotting_files:
            matched = [plotting_files[0]]
        figure_relative = str(item.get("path") or "").replace("\\", "/")
        figure_path = state.path / figure_relative
        figure_identity = compute_artifact_identity(figure_path, figure_relative) if figure_path.is_file() else {}
        code_hashes = {
            relative: sha256_file(state.path / relative)
            for relative in matched
            if (state.path / relative).is_file()
        }
        input_hashes = {}
        for raw in run_manifest.get("input_artifacts") or run_manifest.get("input_files") or []:
            raw_relative = str(raw.get("path") if isinstance(raw, dict) else raw).replace("\\", "/")
            raw_path = state.path / raw_relative
            if raw_relative and raw_path.is_file():
                input_hashes[raw_relative] = sha256_file(raw_path)
        traces.append({
            "schema_version": "dpl.figure_code_trace.v2",
            "figure_id": figure_id,
            "figure_path": figure_relative,
            "code_files": matched,
            "interpretation_summary": item.get("interpretation_summary") or "",
            "statistics": item.get("statistics") or {},
            "figure_hash": figure_identity.get("byte_sha256"),
            "semantic_hash": figure_identity.get("semantic_sha256"),
            "metadata_hash": metadata_identity.get("byte_sha256") if metadata_identity else None,
            "producer_code_hashes": code_hashes,
            "input_artifact_hashes": input_hashes,
            "run_transaction_id": transaction_id,
            "run_id": str(run_manifest.get("run_id") or ""),
            "cohort_id": str(run_manifest.get("cohort_id") or run_manifest.get("cohort") or ""),
            "metric_record_refs": metric_refs,
            "count_record_refs": count_refs,
            "caption_contract_ref": str(item.get("caption_contract_ref") or ""),
            "producer_fingerprint": {"module": "draftpaper_cli.code_ownership", "version": "v2"},
            "trace_status": "current" if figure_identity and transaction_id else "legacy_unqualified",
        })
    payload = {
        "status": "written",
        "schema_version": "dpl.figure_code_trace.v2",
        "generated_at": utc_now(),
        "trace_count": len(traces),
        "traces": traces,
        "run_transaction_id": transaction_id,
        "run_id": str(run_manifest.get("run_id") or ""),
        "policy": "Figure traces are current only when image, metadata, code, inputs, run transaction, and evidence references are bound.",
    }
    _write_json(state.path / FIGURE_CODE_TRACE, payload)
    lines = ["# Figure Code Trace", "", "| Figure | Code files |", "| --- | --- |"]
    for trace in traces:
        lines.append(f"| {trace['figure_id']} | {', '.join('`' + item + '`' for item in trace['code_files'])} |")
    write_html_report(state.path / "results" / "figure_code_trace.html", "\n".join(lines), title="Figure Code Trace")
    return {
        "status": "written",
        "schema_version": "dpl.figure_code_trace.v2",
        "project_path": str(state.path),
        "figure_code_trace": str(state.path / FIGURE_CODE_TRACE),
        "trace_count": len(traces),
        "traces": traces,
    }


def assess_figure_code_trace(project: str | Path) -> dict[str, Any]:
    """Recompute v2 bindings without rewriting the trace or project state."""

    state = load_project(project)
    payload = _read_json(state.path / FIGURE_CODE_TRACE, {})
    traces = payload.get("traces") if isinstance(payload, dict) else []
    checks: list[dict[str, Any]] = []
    for item in traces or []:
        if not isinstance(item, dict):
            continue
        figure_relative = str(item.get("figure_path") or "").replace("\\", "/")
        issues: list[dict[str, Any]] = []
        if str(item.get("schema_version") or payload.get("schema_version") or "") != "dpl.figure_code_trace.v2":
            issues.append({"kind": "legacy_unqualified", "detail": "Trace does not use FigureCodeTrace v2."})
        figure_path = state.path / figure_relative
        if not figure_path.is_file():
            issues.append({"kind": "missing_figure", "detail": figure_relative})
        else:
            identity = compute_artifact_identity(figure_path, figure_relative)
            if item.get("figure_hash") != identity.get("byte_sha256") or item.get("semantic_hash") != identity.get("semantic_sha256"):
                issues.append({"kind": "figure_hash_changed", "detail": figure_relative})
        metadata_path = state.path / "results" / "figure_metadata.json"
        if metadata_path.is_file() and item.get("metadata_hash"):
            metadata_identity = compute_artifact_identity(metadata_path, "results/figure_metadata.json")
            if item.get("metadata_hash") != metadata_identity.get("byte_sha256"):
                issues.append({"kind": "metadata_hash_changed", "detail": "results/figure_metadata.json"})
        for relative, expected in (item.get("producer_code_hashes") or {}).items():
            path = state.path / str(relative)
            if not path.is_file() or sha256_file(path) != expected:
                issues.append({"kind": "producer_code_hash_changed", "detail": str(relative)})
        for relative, expected in (item.get("input_artifact_hashes") or {}).items():
            path = state.path / str(relative)
            if not path.is_file() or sha256_file(path) != expected:
                issues.append({"kind": "input_artifact_hash_changed", "detail": str(relative)})
        if not str(item.get("run_transaction_id") or ""):
            issues.append({"kind": "missing_run_transaction", "detail": "run_transaction_id"})
        checks.append({
            "figure_id": item.get("figure_id"),
            "figure_path": figure_relative,
            "status": "current" if not issues else "stale",
            "issues": issues,
        })
    status = "current" if checks and all(item["status"] == "current" for item in checks) else "stale" if checks else "missing"
    return {
        "schema_version": "dpl.figure_code_trace_validation.v1",
        "status": status,
        "trace_schema_version": payload.get("schema_version") if isinstance(payload, dict) else None,
        "checks": checks,
        "policy": "A trace is current only when every bound artifact hash and run transaction remains current.",
    }


def validate_figure_code_trace(project: str | Path) -> dict[str, Any]:
    """Write a read-only validation receipt for FigureCodeTrace v2."""

    state = load_project(project)
    report = assess_figure_code_trace(state.path)
    _write_json(state.path / "results" / "figure_code_trace_validation.json", report)
    return report
