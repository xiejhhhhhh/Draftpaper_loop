# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .citation_utils import has_citation_command
from .evidence_registry import ensure_registry_consistent
from .evidence_snapshot import EvidenceSnapshotMismatch, validate_evidence_snapshot
from .io_utils import read_json
from .latex_utils import safe_latex_text
from .manuscript_composer import SectionCompositionError, select_validated_section_draft
from .paper_narrative import build_results_synthesis_plan
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status
from .result_validity import ResultValidityError, validate_result_validity_for_results
from .result_support import ResultSupportError, validate_result_support_for_manuscript
from .result_evidence import ResultEvidenceError, resolve_result_evidence


RESULT_INPUTS = [
    "results/result_validity_report.json",
    "results/result_manifest.yaml",
]

RESULT_OUTPUTS = [
    "results/results.tex",
    "results/results_summary_zh.md",
    "results/figure_interpretation_blueprint.json",
]

FIGURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".svg"}
TABLE_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".json"}

class ResultsGateError(RuntimeError):
    """Raised when Results writing would use unsupported or missing artifacts."""


def _safe_latex_text(text: str) -> str:
    return safe_latex_text(text)


def _manuscript_result_text(text: str) -> str:
    replacements = {
        "the result validity gate": "the quantitative validation summary",
        "result validity gate": "quantitative validation summary",
        "the project workflow": "the analysis",
        "project workflow": "analysis",
        "the verified workflow": "the current analysis",
        "verified workflow": "current analysis",
        "the verified analysis": "the current analysis",
        "verified analysis": "current analysis",
        "local filenames": "administrative artifact names",
        "storage paths": "administrative storage details",
        "Draftpaper-loop": "the drafting tool",
        "DraftPaper": "the drafting tool",
        "Draftpaper": "the drafting tool",
    }
    cleaned = str(text or "")
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return re.sub(r"\s+", " ", cleaned).strip()


def _project_relative_path(project_path: Path, relative: str) -> Path:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError as exc:
        raise ResultsGateError(f"Result artifact path escapes project directory: {relative}") from exc
    return candidate


def _artifact_id(prefix: str, index: int, path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", path.stem).strip("_").lower() or str(index)
    return f"{prefix}_{index}_{stem}"


def _read_json(path: Path) -> dict[str, Any]:
    payload = read_json(path, {})
    return payload if isinstance(payload, dict) else {}



def _rendered_metadata_paths(project_path: Path) -> set[str]:
    figure_metadata = _read_json(project_path / "results" / "figure_metadata.json")
    paths: set[str] = set()
    for item in figure_metadata.get("figures") or []:
        if isinstance(item, dict) and item.get("path"):
            paths.add(str(item.get("path")).replace("\\", "/"))
    return paths


def _unrendered_planned_figure_paths(project_path: Path) -> dict[str, dict[str, Any]]:
    """Return planned generated figures that should not be inventoried as results.

    Stale PNGs can remain in results/figures after a new figure execution skips a
    supporting figure for missing data or method code. Those files are useful as
    local debris for debugging, but they are not current scientific evidence and
    must not enter result_manifest.yaml.
    """
    figure_plan = _read_json(project_path / "results" / "figure_plan.json")
    diagnosis = _read_json(project_path / "results" / "figure_execution_diagnosis.json")
    metadata_paths = _rendered_metadata_paths(project_path)
    generated_diagnosis_paths: set[str] = set()
    for item in diagnosis.get("figures") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").lower() == "generated":
            rendered = str(item.get("rendered_path") or item.get("path") or "").replace("\\", "/")
            if rendered:
                generated_diagnosis_paths.add(rendered)
    excluded: dict[str, dict[str, Any]] = {}
    for figure in figure_plan.get("figures") or []:
        if not isinstance(figure, dict):
            continue
        relative = str(figure.get("path") or "").replace("\\", "/")
        if not relative or str(figure.get("generation_mode") or "") != "generated_code":
            continue
        if relative in metadata_paths or relative in generated_diagnosis_paths:
            continue
        excluded[relative] = {
            "id": figure.get("id") or figure.get("figure_id") or figure.get("storyboard_id") or Path(relative).stem,
            "path": relative,
            "figure_role": figure.get("figure_role") or "supporting",
            "manuscript_role": figure.get("manuscript_role") or ("appendix" if figure.get("counts_toward_main_figures") is False else "main"),
            "reason": "planned_generated_figure_was_not_rendered_in_current_run",
        }
    return excluded

def _artifact_context(project_path: Path) -> dict[str, dict[str, Any]]:
    analysis_manifest = _read_json(project_path / "methods" / "analysis_code_manifest.json")
    run_manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    resolved_evidence = _read_json(project_path / "results" / "resolved_result_evidence.json")
    figure_plan = _read_json(project_path / "results" / "figure_plan.json")
    figure_metadata = _read_json(project_path / "results" / "figure_metadata.json")
    metadata_by_path = {
        str(item.get("path") or ""): item
        for item in figure_metadata.get("figures") or []
        if item.get("path")
    }
    context: dict[str, dict[str, Any]] = {}
    for figure in figure_plan.get("figures") or []:
        path = Path(str(figure.get("path") or ""))
        if not path.name:
            continue
        metadata = metadata_by_path.get(path.as_posix()) or metadata_by_path.get(str(figure.get("path") or ""))
        interpretation = str((metadata or {}).get("interpretation_summary") or "")
        n_value = (metadata or {}).get("n")
        caption = str(figure.get("caption_draft") or figure.get("title") or path.stem.replace("_", " "))
        if n_value:
            caption = f"{caption} The plotted evidence uses n={n_value} usable observations."
        context[path.name] = {
            "caption": caption,
            "claim": str(
                interpretation
                or figure.get("result_claim_template")
                or figure.get("scientific_question")
            or "This figure shows an empirical pattern from the current analysis and should be interpreted in relation to the plotted variables."
            ),
            "figure_role": str(figure.get("figure_role") or "main_result"),
            "manuscript_role": str(figure.get("manuscript_role") or ("appendix" if figure.get("figure_role") != "main_result" else "main")),
            "supporting_reason": str(figure.get("supporting_reason") or ""),
            "storyboard_id": str(figure.get("storyboard_id") or figure.get("id") or ""),
            "figure_group": str(figure.get("figure_group") or figure.get("group") or ""),
            "scientific_question": str(figure.get("scientific_question") or ""),
            "expected_finding": str(figure.get("expected_finding") or figure.get("result_claim_template") or ""),
            "claim_boundary": str(figure.get("scientific_claim_boundary") or figure.get("claim_boundary") or ""),
            "counts_toward_main_figures": figure.get("counts_toward_main_figures"),
            "linked_main_figure": str(figure.get("linked_main_figure") or figure.get("supports_figure") or figure.get("supports_storyboard_id") or ""),
            "metrics": (metadata or {}).get("metrics") or (metadata or {}).get("statistics") or {},
            "interpretation_summary": interpretation,
        }
    selected_input = analysis_manifest.get("selected_input_data") or "the selected local data"
    method_families = ", ".join(str(item).replace("_", " ") for item in (analysis_manifest.get("method_families") or []))
    primary_metric = analysis_manifest.get("primary_metric") or "primary metric"
    resolved_primary = resolved_evidence.get("primary_metric") or {}
    observed = resolved_primary.get("value")
    if observed is None:
        observed = (run_manifest.get("metrics") or {}).get(str(primary_metric))
    if resolved_primary.get("metric_name"):
        primary_metric = resolved_primary.get("metric_name")
    metric_text = f"{primary_metric}={observed}" if observed is not None else str(primary_metric)
    context.update({
        "metrics.csv": {
            "caption": "Scalar metrics from the method run.",
            "claim": f"The metrics table records the observed method output used in the quantitative validation summary, including {metric_text}.",
        },
        "analysis_summary.csv": {
            "caption": "Analysis summary produced by the method pipeline.",
            "claim": "The analysis summary records selected input data, detected label column, method families, and generation metadata for traceability.",
        },
    })
    if not context and selected_input:
        context["analysis_summary.csv"] = {
            "caption": "Analysis summary produced by the project analysis.",
            "claim": f"The analysis summary records how {selected_input} was used to produce result artifacts.",
        }
    return context


def _is_appendix_figure(entry: dict[str, Any]) -> bool:
    return (
        str(entry.get("manuscript_role") or "").lower() == "appendix"
        or str(entry.get("figure_role") or "").lower() not in {"", "main_result"}
        or entry.get("counts_toward_main_figures") is False
    )


def _scientific_object_name(entry: dict[str, Any]) -> str:
    title = str(entry.get("caption_draft") or entry.get("title") or entry.get("figure_group") or "result evidence")
    title = title.split(". The plotted evidence uses", 1)[0]
    title = re.sub(r"\bresults[/\\]figures[/\\][^\s{}]+", "result evidence", title, flags=re.I)
    title = re.sub(r"\b[\w.-]+\.(?:png|jpg|jpeg|pdf|svg|csv|json|py)\b", "result evidence", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" .")
    if not title or title.lower() in {"result evidence", "result figure"}:
        return "result evidence"
    return title[:1].lower() + title[1:]


def _figure_entry(project_path: Path, path: Path, index: int, context: dict[str, dict[str, Any]]) -> dict[str, Any]:
    relative = path.relative_to(project_path).as_posix()
    details = context.get(path.name, {})
    manuscript_role = details.get("manuscript_role") or "main"
    counts_toward_main = details.get("counts_toward_main_figures")
    if str(manuscript_role).lower() == "appendix":
        counts_toward_main = False
    return {
        "id": _artifact_id("fig", index, path),
        "path": relative,
        "figure_role": details.get("figure_role") or "main_result",
        "manuscript_role": manuscript_role,
        "counts_toward_main_figures": counts_toward_main if counts_toward_main is not None else True,
        "supporting_reason": details.get("supporting_reason") or "",
        "storyboard_id": details.get("storyboard_id") or "",
        "figure_group": details.get("figure_group") or "",
        "scientific_question": _manuscript_result_text(details.get("scientific_question") or ""),
        "expected_finding": _manuscript_result_text(details.get("expected_finding") or ""),
        "claim_boundary": _manuscript_result_text(details.get("claim_boundary") or ""),
        "linked_main_figure": details.get("linked_main_figure") or "",
        "metrics": details.get("metrics") or {},
        "caption_draft": _manuscript_result_text(details.get("caption") or f"Result figure {index}: {path.stem.replace('_', ' ')}."),
        "result_claim": _manuscript_result_text(details.get("claim") or "The figure provides visual evidence for one result and should be interpreted directly from the plotted empirical pattern."),
    }


def _table_entry(project_path: Path, path: Path, index: int, context: dict[str, dict[str, Any]]) -> dict[str, Any]:
    relative = path.relative_to(project_path).as_posix()
    details = context.get(path.name, {})
    return {
        "id": _artifact_id("table", index, path),
        "path": relative,
        "table_role": "internal" if path.name.lower() in {"metrics.csv", "analysis_summary.csv"} else "result_table",
        "caption_draft": _manuscript_result_text(details.get("caption") or f"Result table {index}: {path.stem.replace('_', ' ')}."),
        "result_claim": _manuscript_result_text(details.get("claim") or "The table provides quantitative support for one result and should be interpreted alongside the corresponding figures."),
    }


def _load_figure_code_trace(project_path: Path) -> dict[str, Any]:
    for relative in ["results/figure_code_trace.json", "methods/figure_code_trace.json"]:
        payload = _read_json(project_path / relative)
        if payload:
            return payload
    return {}


def _supporting_links(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    main_ids = [str(item.get("storyboard_id") or item.get("id")) for item in figures if not _is_appendix_figure(item)]
    default_main = main_ids[0] if main_ids else ""
    links = []
    for item in figures:
        if not _is_appendix_figure(item):
            continue
        target = str(item.get("linked_main_figure") or "") or default_main
        links.append({
            "appendix_figure_id": item.get("id"),
            "supports_main_figure": target,
            "reason": item.get("supporting_reason") or "diagnostic evidence supports the reliability or boundary of the main result",
        })
    return links


def _claim_boundaries(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boundaries = []
    for item in figures:
        boundary = str(item.get("claim_boundary") or item.get("expected_finding") or item.get("result_claim") or "").strip()
        if boundary:
            boundaries.append({
                "figure_id": item.get("id"),
                "storyboard_id": item.get("storyboard_id") or "",
                "claim_boundary": boundary,
                "manuscript_role": item.get("manuscript_role") or "main",
            })
    return boundaries


def inventory_results(project: str | Path) -> dict[str, Any]:
    """Create results/result_manifest.yaml from existing local figures and tables."""
    state = load_project(project)
    results_dir = state.path / "results"
    figures_dir = results_dir / "figures"
    tables_dir = results_dir / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    excluded_planned = _unrendered_planned_figure_paths(state.path)
    figure_paths = sorted(
        path
        for path in figures_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in FIGURE_EXTENSIONS
        and path.relative_to(state.path).as_posix() not in excluded_planned
    )
    table_paths = sorted(path for path in tables_dir.iterdir() if path.is_file() and path.suffix.lower() in TABLE_EXTENSIONS)
    try:
        resolved_evidence = resolve_result_evidence(state.path)
    except ResultEvidenceError:
        resolved_evidence = {}
    context = _artifact_context(state.path)
    figures = [_figure_entry(state.path, path, index + 1, context) for index, path in enumerate(figure_paths)]
    tables = [_table_entry(state.path, path, index + 1, context) for index, path in enumerate(table_paths)]
    main_figures = [item for item in figures if not _is_appendix_figure(item)]
    appendix_figures = [item for item in figures if _is_appendix_figure(item)]
    manifest = {
        "schema_version": "v0.16.5",
        "figures": figures,
        "tables": tables,
        "main_figures": main_figures,
        "appendix_figures": appendix_figures,
        "supporting_links": _supporting_links(figures),
        "excluded_unrendered_figures": list(excluded_planned.values()),
        "internal_tables": [item for item in tables if item.get("table_role") == "internal"],
        "claim_boundaries": _claim_boundaries(figures),
        "figure_code_trace": _load_figure_code_trace(state.path),
        "resolved_result_evidence": resolved_evidence,
    }
    _write_json(results_dir / "result_manifest.yaml", manifest)
    update_stage_status(state.path, "results", "draft")
    _set_results_stage_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "result_manifest": str(results_dir / "result_manifest.yaml"),
        "figure_count": len(manifest["figures"]),
        "excluded_unrendered_figure_count": len(excluded_planned),
        "table_count": len(manifest["tables"]),
    }


def _read_manifest(project_path: Path) -> dict[str, Any]:
    path = project_path / "results" / "result_manifest.yaml"
    if not path.exists():
        raise ResultsGateError("results/result_manifest.yaml is required before writing results.tex.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ResultsGateError(f"results/result_manifest.yaml is not valid JSON-compatible YAML: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ResultsGateError("results/result_manifest.yaml must contain an object.")
    return manifest


def _all_entries(manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    has_structured_figures = bool(manifest.get("main_figures") or manifest.get("appendix_figures"))
    figures = manifest.get("main_figures") or ([] if has_structured_figures else manifest.get("figures") or [])
    appendix = manifest.get("appendix_figures") or []
    seen: set[str] = set()
    for entry in figures:
        if isinstance(entry, dict):
            seen.add(str(entry.get("id") or entry.get("path") or ""))
            entries.append(("figure", entry))
    for entry in appendix:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("id") or entry.get("path") or "")
        if key not in seen:
            entries.append(("figure", entry))
    for entry in manifest.get("tables") or []:
        entries.append(("table", entry))
    return entries


def _validate_manifest(project_path: Path, manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    entries = _all_entries(manifest)
    if not entries:
        raise ResultsGateError("result_manifest.yaml must contain at least one figure or table.")
    missing = []
    for kind, entry in entries:
        relative = str(entry.get("path") or "")
        if not relative:
            raise ResultsGateError(f"A {kind} entry is missing its path.")
        if not _project_relative_path(project_path, relative).exists():
            missing.append(relative)
        text = " ".join(str(entry.get(key) or "") for key in ("caption_draft", "result_claim"))
        if has_citation_command(text):
            raise ResultsGateError(f"Results manifest entry {entry.get('id') or relative} contains a citation command.")
    if missing:
        raise ResultsGateError("Declared result artifacts are missing: " + ", ".join(missing))
    return entries


def _render_figure(entry: dict[str, Any]) -> str:
    path = str(entry["path"]).replace("\\", "/")
    caption = _safe_latex_text(str(entry.get("caption_draft") or entry.get("id") or "Result figure"))
    return (
        "\\begin{figure}[htbp]\n"
        "\\centering\n"
        f"\\includegraphics[width=0.92\\linewidth]{{{path}}}\n"
        f"\\caption{{{caption}}}\n"
        f"\\label{{fig:{_safe_label(str(entry.get('id') or Path(path).stem))}}}\n"
        "\\end{figure}"
    )


def _render_table(entry: dict[str, Any]) -> str:
    caption = _safe_latex_text(str(entry.get("caption_draft") or entry.get("id") or "Result table"))
    claim = _safe_latex_text(_sanitize_result_prose(entry.get("result_claim") or "The table summarizes quantitative evidence used to interpret the result figures."))
    return (
        "\\begin{table}[htbp]\n"
        "\\centering\n"
        f"\\caption{{{caption}}}\n"
        f"\\label{{tab:{_safe_label(str(entry.get('id') or 'result-table'))}}}\n"
        "\\begin{minipage}{0.86\\linewidth}\n"
        "\\small\n"
        f"{claim}\n"
        "\\end{minipage}\n"
        "\\end{table}"
    )


def _safe_label(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9:-]+", "-", text).strip("-") or "result"


def _entry_label(kind: str, entry: dict[str, Any]) -> str:
    path = str(entry.get("path") or "")
    identifier = str(entry.get("id") or Path(path).stem or "result")
    prefix = "fig" if kind == "figure" else "tab"
    return f"{prefix}:{_safe_label(identifier)}"


def _entry_reference(kind: str, entry: dict[str, Any]) -> str:
    if kind == "figure" and str(entry.get("manuscript_role") or "") == "appendix":
        name = "Appendix Figure"
    else:
        name = "Figure" if kind == "figure" else "Table"
    return f"{name}~\\ref{{{_entry_label(kind, entry)}}}"


def _safe_latex_prose_with_refs(text: str) -> str:
    """Escape prose while preserving internally generated LaTeX figure/table refs."""
    escaped = _safe_latex_text(text)
    return re.sub(
        r"\\textasciitilde\{\}\\textbackslash\{\}ref\\\{([^{}]+)\\\}",
        lambda match: f"~\\ref{{{match.group(1)}}}",
        escaped,
    )


def _sanitize_result_prose(text: str) -> str:
    cleaned = _manuscript_result_text(str(text or ""))
    cleaned = re.sub(
        r"\bsource[_\s-]*id has ([0-9,.e+\-]+) usable observations with mean [0-9,.e+\-]+ and range [0-9,.e+\-]+ to [0-9,.e+\-]+\.",
        r"The panel summarizes source-level coverage across \1 usable observations.",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"\bobs[_\s-]*id has ([0-9,.e+\-]+) usable observations with mean [0-9,.e+\-]+ and range [0-9,.e+\-]+ to [0-9,.e+\-]+\.",
        r"The panel summarizes observation-level coverage across \1 usable observations.",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"\bsource[_\s-]*id and obs[_\s-]*id show a [^\.]+\(r=[0-9,.e+\-]+, R2=[0-9,.e+\-]+\)\.",
        "The paired source-observation view is treated as a coverage diagnostic rather than as a physical association.",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\bcategory contains\b", "The class-label field contains", cleaned, flags=re.I)
    cleaned = re.sub(r"\brow_count\s*=\s*", "sample size=", cleaned, flags=re.I)
    cleaned = re.sub(r"\bfeature_column_count\s*=\s*", "feature count=", cleaned, flags=re.I)
    cleaned = re.sub(r"\b[A-Za-z]:[/\\][^\s{}]+", "the local analysis evidence", cleaned)
    cleaned = re.sub(r"\bresults[/\\]figures[/\\][^\s{}]+", "the plotted result evidence", cleaned, flags=re.I)
    cleaned = re.sub(r"\bresults[/\\]tables[/\\][^\s{}]+", "the quantitative result evidence", cleaned, flags=re.I)
    cleaned = re.sub(r"\b[\w.-]+\.(?:png|jpg|jpeg|pdf|svg)\b", "the plotted result evidence", cleaned, flags=re.I)
    cleaned = re.sub(r"\b[\w.-]+\.(?:csv|tsv|xlsx|json|yaml|yml|py)\b", "the quantitative result evidence", cleaned, flags=re.I)
    cleaned = cleaned.replace("first establishes the main empirical pattern", "identifies the main empirical pattern")
    cleaned = cleaned.replace("the second checks whether the same conclusion is stable", "the diagnostic evidence constrains how far that conclusion can be taken")
    return re.sub(r"\s+", " ", cleaned).strip()


def _question_clause(question: str) -> str:
    cleaned = _sanitize_result_prose(question).strip().rstrip("?")
    if not cleaned:
        return "the planned empirical pattern"
    lowered = cleaned[:1].lower() + cleaned[1:]
    clause = ""
    for prefix in ["does ", "do ", "did ", "can ", "is ", "are "]:
        if lowered.startswith(prefix):
            clause = "whether " + lowered[len(prefix):]
            break
    if lowered.startswith("what "):
        clause = "the " + lowered[len("what "):]
    if not clause:
        clause = lowered
    clause = re.sub(r"\s+are available\b", "", clause)
    clause = clause.replace("the proposed method improve", "the proposed method improves")
    return clause


def _main_and_appendix_entries(entries: list[tuple[str, dict[str, Any]]]) -> tuple[list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]]]:
    main: list[tuple[str, dict[str, Any]]] = []
    appendix: list[tuple[str, dict[str, Any]]] = []
    other: list[tuple[str, dict[str, Any]]] = []
    for kind, entry in entries:
        if kind == "figure" and str(entry.get("manuscript_role") or "").lower() == "appendix":
            appendix.append((kind, entry))
        elif kind == "figure":
            main.append((kind, entry))
        else:
            other.append((kind, entry))
    return main, appendix, other


def _appendix_refs_for_main(main_entry: dict[str, Any], appendix_entries: list[tuple[str, dict[str, Any]]], *, fallback: bool) -> list[str]:
    main_keys = {
        str(main_entry.get("id") or ""),
        str(main_entry.get("storyboard_id") or ""),
        str(main_entry.get("figure_group") or ""),
    }
    refs = []
    seen_refs: set[str] = set()
    main_token_text = " ".join(main_keys).lower()
    main_tokens = {token for token in re.split(r"[^a-z0-9]+", main_token_text) if len(token) >= 4}
    for kind, entry in appendix_entries:
        link = str(entry.get("linked_main_figure") or entry.get("supports_main_figure") or "")
        reason = str(entry.get("supporting_reason") or "").lower()
        appendix_token_text = " ".join(
            str(entry.get(key) or "")
            for key in ["id", "storyboard_id", "figure_group", "scientific_question", "caption_draft", "result_claim"]
        ).lower()
        appendix_tokens = {token for token in re.split(r"[^a-z0-9]+", appendix_token_text) if len(token) >= 4}
        overlaps = main_tokens & appendix_tokens
        should_link = (
            (link and link in main_keys)
            or (not link and overlaps and any(token in reason for token in ["diagnostic", "reliability", "validation", "stability", "appendix", "supports"]))
            or (not link and fallback and any(token in reason for token in ["diagnostic", "reliability", "validation", "stability", "appendix"]))
        )
        if should_link:
            ref = _entry_reference(kind, entry)
            if ref not in seen_refs:
                seen_refs.add(ref)
                refs.append(ref)
    return refs[:2]


def _metric_value(metrics: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = metrics.get(name)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


_METRIC_LABELS = {
    "f1": "F1",
    "f1_macro": "macro F1",
    "macro_f1": "macro F1",
    "accuracy": "accuracy",
    "baseline_accuracy": "baseline accuracy",
    "balanced_accuracy": "balanced accuracy",
    "auc": "AUC",
    "roc_auc": "AUC",
    "pearson_r": "Pearson r",
    "r": "Pearson r",
    "r2": "R2",
    "R2": "R2",
    "class_count": "class count",
    "feature_count": "feature count",
    "feature_column_count": "feature count",
    "max_min_imbalance": "class imbalance ratio",
    "sample_size": "sample size",
    "n": "sample size",
}

_INTERNAL_METRIC_KEYS = {
    "row_count",
    "rows",
    "count",
    "source_id",
    "obs_id",
    "event_id",
    "history_event_id",
    "history_obs_id",
    "mean",
    "min",
    "max",
    "slope",
    "intercept",
    "bin_count",
    "column_count",
}


def _metric_label(key: str) -> str:
    return _METRIC_LABELS.get(key, key.replace("_", " "))


def _metric_bits(metrics: dict[str, Any]) -> list[str]:
    bits: list[str] = []
    for key, value in metrics.items():
        normalized = str(key or "").strip()
        lowered = normalized.lower()
        if lowered in _INTERNAL_METRIC_KEYS:
            continue
        if value is None or value == "" or isinstance(value, (dict, list)):
            continue
        if lowered not in {item.lower() for item in _METRIC_LABELS}:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if lowered in {"class_count", "feature_count", "feature_column_count"}:
            rendered = f"{int(numeric)}" if numeric.is_integer() else f"{numeric:.3g}"
        else:
            rendered = f"{numeric:.3g}"
        bits.append(f"{_metric_label(normalized)}={rendered}")
        if len(bits) >= 3:
            break
    return bits


def _primary_metric_map(metrics: dict[str, Any]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for key, label in [("f1", "F1"), ("f1_macro", "macro F1"), ("macro_f1", "macro F1"), ("auc", "AUC"), ("roc_auc", "AUC"), ("accuracy", "accuracy")]:
        if key not in metrics:
            continue
        try:
            value = float(metrics[key])
        except (TypeError, ValueError):
            continue
        rendered[label] = f"{value:.3g}"
    return rendered


def build_figure_interpretation_blueprint(entries: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Build a writer-facing interpretation plan for main figures and appendix diagnostics."""
    main_entries, appendix_entries, _table_entries = _main_and_appendix_entries(entries)
    groups: list[dict[str, Any]] = []
    for index, (kind, entry) in enumerate(main_entries, start=1):
        if kind != "figure":
            continue
        appendix_refs = _appendix_refs_for_main(entry, appendix_entries, fallback=index == 1)
        metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
        groups.append({
            "group_index": index,
            "main_figure_id": entry.get("id") or entry.get("path"),
            "scientific_question": _sanitize_result_prose(entry.get("scientific_question") or ""),
            "main_claim": _sanitize_result_prose(entry.get("result_claim") or entry.get("expected_finding") or ""),
            "primary_metrics": _primary_metric_map(metrics),
            "interpretation_sentence": _scientific_result_sentence(entry, _sanitize_result_prose(entry.get("result_claim") or "")),
            "claim_boundary": _sanitize_result_prose(entry.get("claim_boundary") or ""),
            "appendix_support": appendix_refs,
        })
    return {
        "status": "written",
        "schema_version": "v0.17.0",
        "main_group_count": len(groups),
        "groups": groups,
    }


def _sample_size_from_entry(entry: dict[str, Any], metrics: dict[str, Any]) -> str:
    caption = str(entry.get("caption_draft") or "")
    match = re.search(r"n=([0-9,.e+\-]+)", caption, flags=re.I)
    if match:
        return match.group(1)
    value = _metric_value(metrics, "row_count", "sample_size", "n", "count")
    if value is not None:
        return f"{value:.4g}"
    return ""


def _class_support_sentence(metrics: dict[str, Any], claim: str) -> str:
    class_count = _metric_value(metrics, "class_count")
    imbalance = _metric_value(metrics, "max_min_imbalance")
    if class_count is not None and imbalance is not None:
        if imbalance <= 1.2:
            return f"The class distribution is effectively balanced across {int(class_count)} classes, so later performance differences are less likely to be explained by label-count asymmetry alone."
        return f"The class distribution spans {int(class_count)} classes with an imbalance ratio of {imbalance:.3g}, which must be treated as part of the claim boundary."
    if "largest-to-smallest support ratio is 1" in claim:
        return "The class support is balanced, so the subsequent classification evidence is not simply a consequence of a dominant label."
    return ""


def _performance_sentence(metrics: dict[str, Any]) -> str:
    f1 = _metric_value(metrics, "f1", "f1_macro", "macro_f1")
    accuracy = _metric_value(metrics, "accuracy", "baseline_accuracy", "balanced_accuracy")
    auc = _metric_value(metrics, "auc", "roc_auc")
    primary = f1 if f1 is not None else accuracy
    if primary is None and auc is None:
        return ""
    parts = []
    if f1 is not None:
        parts.append(f"F1={f1:.3g}")
    if accuracy is not None:
        parts.append(f"accuracy={accuracy:.3g}")
    if auc is not None:
        parts.append(f"AUC={auc:.3g}")
    metric_text = ", ".join(parts)
    comparison_value = primary if primary is not None else auc
    if comparison_value is not None and comparison_value <= 0.58:
        return f"The reported {metric_text} places the current model close to a weak or baseline-level decision boundary, so this result is stronger as a feasibility and limitation signal than as evidence of a mature classifier."
    if comparison_value is not None and comparison_value >= 0.75:
        return f"The reported {metric_text} indicates useful discrimination under the declared validation setting, while the claim still depends on the hold-out design and sample coverage."
    return f"The reported {metric_text} indicates moderate discrimination and should be interpreted together with the validation and ablation diagnostics."


def _association_sentence(metrics: dict[str, Any], claim: str) -> str:
    r_value = _metric_value(metrics, "pearson_r", "r")
    r2 = _metric_value(metrics, "r2", "R2")
    if r_value is None and r2 is None and "coverage diagnostic" not in claim:
        return ""
    if r2 is not None and r2 < 0.1:
        return f"The low goodness of fit (R2={r2:.3g}) indicates that this panel should be read as a coverage or separability diagnostic, not as a strong explanatory relationship."
    if r_value is not None:
        return f"The association statistic (r={r_value:.3g}) summarizes the plotted relation but does not by itself establish statistical confidence or physical causality."
    return "The plotted relation is used as a diagnostic view of sample structure rather than as a stand-alone physical association."


def _scientific_result_sentence(entry: dict[str, Any], claim: str) -> str:
    title = str(entry.get("caption_draft") or entry.get("id") or "").lower()
    question = str(entry.get("scientific_question") or "").lower()
    metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
    sample_size = _sample_size_from_entry(entry, metrics)
    class_sentence = _class_support_sentence(metrics, claim)
    if class_sentence:
        return class_sentence
    performance = _performance_sentence(metrics)
    if performance and any(token in title + " " + question for token in ["baseline", "performance", "ablation", "error", "uncertain", "metric"]):
        return performance
    association = _association_sentence(metrics, claim)
    if association:
        return association
    if any(token in title + " " + question for token in ["coverage", "workflow", "sample", "modality"]):
        if sample_size:
            if "source-level coverage" in claim:
                return f"The panel summarizes source-level coverage across {sample_size} usable observations, fixing the empirical boundary before model interpretation."
            return f"The evidence first fixes the empirical boundary of the study by showing that {sample_size} usable observations enter the plotted analysis."
        return "The evidence first fixes the empirical boundary of the study by showing which observations and modalities are available for the planned analysis."
    if any(token in title + " " + question for token in ["feature", "temporal", "spectral", "space"]):
        return "The feature-space view is interpreted as a pre-model diagnostic: it indicates whether the available temporal and spectral descriptors contain structure worth testing with the planned classifier."
    return claim


def _result_evidence_paragraph(index: int, entry: dict[str, Any], appendix_refs: list[str]) -> str:
    question = _sanitize_result_prose(entry.get("scientific_question") or "")
    claim = _sanitize_result_prose(entry.get("result_claim") or entry.get("expected_finding") or "")
    boundary = _sanitize_result_prose(entry.get("claim_boundary") or "")
    metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
    metric_bits = _metric_bits(metrics)
    metric_sentence = f" A concise quantitative summary is {', '.join(metric_bits)}." if metric_bits else ""
    object_name = _sanitize_result_prose(_scientific_object_name(entry))
    ref = _entry_reference("figure", entry)
    if question:
        lead = f"The {object_name} evaluates {_question_clause(question)}"
    else:
        lead = f"The {object_name} provides the {index} evidence block for the planned analysis"
    scientific_sentence = _scientific_result_sentence(entry, claim)
    if scientific_sentence:
        claim = scientific_sentence
    appendix_sentence = ""
    if appendix_refs:
        appendix_sentence = " Diagnostic or supporting evidence in " + " and ".join(appendix_refs) + " is used to qualify the reliability and boundary of this interpretation."
    boundary_sentence = f" {boundary}" if boundary else " The interpretation remains limited to the verified data, method design, and validation setting."
    return f"{lead}. {claim}{metric_sentence} The corresponding main evidence is shown in {ref}.{appendix_sentence}{boundary_sentence}"


def _entry_groups(entries: list[tuple[str, dict[str, Any]]]) -> list[list[tuple[str, dict[str, Any]]]]:
    groups: list[list[tuple[str, dict[str, Any]]]] = []
    current: list[tuple[str, dict[str, Any]]] = []
    figure_count = 0
    for kind, entry in entries:
        current.append((kind, entry))
        if kind == "figure":
            figure_count += 1
        if figure_count >= 2 or (kind == "table" and current):
            groups.append(current)
            current = []
            figure_count = 0
    if current:
        groups.append(current)
    return groups


def render_results_tex(
    project_meta: dict[str, Any],
    entries: list[tuple[str, dict[str, Any]]],
    synthesis_plan: dict[str, Any] | None = None,
) -> str:
    finding_blocks = (synthesis_plan or {}).get("finding_blocks") or []
    by_artifact: dict[str, dict[str, Any]] = {}
    for block in finding_blocks:
        if not isinstance(block, dict):
            continue
        for artifact_id in block.get("figure_evidence") or []:
            by_artifact[str(artifact_id)] = block
    lines = [
        "\\section{Results}",
        (
            "The Results section follows the empirical argument established by the approved figure story. Each finding reports what was observed, identifies the relevant comparison or diagnostic evidence, and states the boundary of the corresponding interpretation."
        ),
        "",
    ]
    main_entries, appendix_entries, table_entries = _main_and_appendix_entries(entries)
    if not main_entries and appendix_entries:
        main_entries = appendix_entries
        appendix_entries = []
    rendered_findings: set[str] = set()
    for index, (kind, entry) in enumerate(main_entries, start=1):
        appendix_refs = _appendix_refs_for_main(entry, appendix_entries, fallback=index == 1)
        block = by_artifact.get(str(entry.get("id") or entry.get("path") or ""), {})
        finding_id = str(block.get("finding_id") or "")
        if block and finding_id not in rendered_findings:
            rendered_findings.add(finding_id)
            question = _sanitize_result_prose(str(block.get("scientific_question") or entry.get("scientific_question") or ""))
            observed = _sanitize_result_prose(str(block.get("observed_result") or entry.get("result_claim") or ""))
            scientific_sentence = _scientific_result_sentence(entry, _sanitize_result_prose(str(entry.get("result_claim") or ""))) or observed
            reference = _entry_reference(kind, entry)
            supporting = ""
            if appendix_refs:
                supporting = " Diagnostic or supporting evidence in " + " and ".join(appendix_refs) + " qualifies the stability or scope of this finding."
            boundary = _sanitize_result_prose(str(block.get("claim_boundary") or entry.get("claim_boundary") or ""))
            lead = f"The {_scientific_object_name(entry)} evaluates {_question_clause(question)}" if question else "This finding resolves the planned empirical comparison"
            paragraph_text = (
                f"{lead}. {scientific_sentence} The relevant empirical evidence is presented in {reference}."
                f"{supporting} {boundary or 'The interpretation is limited to the represented cohort, method, and validation setting.'}"
            )
            paragraph_text = re.sub(r"\s+", " ", paragraph_text).replace(". .", ".")
        elif not block:
            paragraph_text = _result_evidence_paragraph(index, entry, appendix_refs)
        else:
            paragraph_text = ""
        if paragraph_text:
            lines.extend([_safe_latex_prose_with_refs(paragraph_text), ""])
        lines.extend([_render_figure(entry), ""])
    if table_entries:
        refs = ", ".join(_entry_reference(kind, entry) for kind, entry in table_entries)
        lines.extend([
            _safe_latex_prose_with_refs(f"The quantitative tables provide the scalar values used to check the figure-level interpretations; these tabulated outputs are reported in {refs} without extending the claims beyond the plotted evidence."),
            "",
        ])
        for kind, entry in table_entries:
            lines.extend([_render_table(entry), ""])
    for kind, entry in appendix_entries:
        lines.extend([_render_figure(entry), ""])
    tex = "\n".join(lines)
    if has_citation_command(tex):
        raise ResultsGateError("Generated results.tex contains a citation command, which is forbidden.")
    prose_only = re.sub(r"\\begin\{figure\}.*?\\end\{figure\}", "", tex, flags=re.S)
    prose_only = re.sub(r"\\begin\{table\}.*?\\end\{table\}", "", prose_only, flags=re.S)
    forbidden = re.search(r"\bresults[/\\]figures[/\\][^\s{}]+|\b[\w.-]+\.(?:png|jpg|jpeg|csv|json|py)\b", prose_only, flags=re.I)
    if forbidden:
        raise ResultsGateError(f"Generated Results prose contains manuscript-internal artifact language: {forbidden.group(0)}")
    return tex


def render_results_summary_zh(entries: list[tuple[str, dict[str, Any]]]) -> str:
    lines = [
        "# 结果部分中文审阅摘要",
        "",
        "本摘要用于人工快速检查图表是否支撑结果叙述，不作为论文正文直接使用。",
        "",
    ]
    for index, group in enumerate(_entry_groups(entries), start=1):
        refs = "、".join(str(entry.get("id") or entry.get("path") or f"artifact_{index}") for _kind, entry in group)
        claims = [
            _manuscript_result_text(str(entry.get("result_claim") or "该图表支持当前分析中的一个经验结果。"))
            for _kind, entry in group
        ]
        lines.append(f"## 图表组 {index}: {refs}")
        lines.append("")
        lines.append("这一组图表主要用于说明：" + "；".join(claims) + "。")
        lines.append("审阅时需要重点确认图中的坐标、图例、统计量和可视化模式是否与这一解释一致，若不一致，应先回退到方法代码或图表规划阶段，而不是直接修改结果文字。")
        lines.append("")
    return "\n".join(lines)


def _set_results_stage_manifest(project_path: Path) -> None:
    manifest_path = project_path / "results" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = RESULT_INPUTS
    manifest["output_files"] = RESULT_OUTPUTS
    _write_json(manifest_path, manifest)


def _existing_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def write_results(project: str | Path) -> dict[str, Any]:
    """Write results.tex only from existing artifacts declared in result_manifest.yaml."""
    state = load_project(project)
    ensure_registry_consistent(state.path)
    snapshot_path = state.path / "results" / "promoted_evidence_snapshot.json"
    if snapshot_path.exists():
        try:
            validate_evidence_snapshot(state.path)
        except EvidenceSnapshotMismatch as exc:
            raise ResultsGateError(str(exc)) from exc
    try:
        validate_result_validity_for_results(state.path)
        validate_result_support_for_manuscript(state.path)
    except (ResultValidityError, ResultSupportError) as exc:
        raise ResultsGateError(str(exc)) from exc
    manifest = _read_manifest(state.path)
    entries = _validate_manifest(state.path, manifest)
    output_path = state.path / "results" / "results.tex"
    summary_path = state.path / "results" / "results_summary_zh.md"
    blueprint_path = state.path / "results" / "figure_interpretation_blueprint.json"
    blueprint = build_figure_interpretation_blueprint(entries)
    synthesis_plan = build_results_synthesis_plan(state.path)
    fallback_tex = render_results_tex(state.metadata, entries, synthesis_plan)
    try:
        composition = select_validated_section_draft(state.path, "results", fallback_tex)
    except SectionCompositionError as exc:
        raise ResultsGateError(str(exc)) from exc
    rendered_tex = str(composition["text"])
    rendered_summary = render_results_summary_zh(entries)
    results_stage = state.metadata.get("stages", {}).get("results", {})
    outputs_unchanged = (
        not results_stage.get("stale")
        and results_stage.get("status") in {"draft", "approved", "completed"}
        and _existing_text(output_path) == rendered_tex
        and _existing_text(summary_path) == rendered_summary
        and _existing_text(blueprint_path) == json.dumps(blueprint, ensure_ascii=False, indent=2) + "\n"
    )
    if outputs_unchanged:
        return {
            "status": "unchanged",
            "project_path": str(state.path),
            "results": str(output_path),
            "results_summary_zh": str(summary_path),
            "artifact_count": len(entries),
            "outputs": RESULT_OUTPUTS,
            "message": "Results outputs are already current; downstream manuscript stages were not marked stale.",
        }

    output_path.write_text(rendered_tex, encoding="utf-8")
    summary_path.write_text(rendered_summary, encoding="utf-8")
    _write_json(blueprint_path, blueprint)
    update_stage_status(state.path, "results", "draft")
    _set_results_stage_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "results": str(output_path),
        "results_summary_zh": str(summary_path),
        "artifact_count": len(entries),
        "outputs": RESULT_OUTPUTS,
    }
