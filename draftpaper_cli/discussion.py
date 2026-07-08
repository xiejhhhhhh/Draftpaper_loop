# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .citation_utils import bibtex_keys_in_text
from .html_utils import write_html_report
from .latex_utils import safe_latex_text
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status
from .reference_usage import ensure_reference_usage_plan, missing_entries_for_section


DISCUSSION_INPUTS = [
    "research_plan/research_plan.md",
    "introduction/introduction.tex",
    "results/results.tex",
    "references/citation_evidence.csv",
    "references/library.bib",
]

DISCUSSION_OUTPUTS = [
    "discussion/comparison_literature_matrix.csv",
    "discussion/comparison_evidence_notes.html",
    "discussion/innovation_limitations_plan.json",
    "discussion/discussion.tex",
]


class MissingDiscussionInputsError(FileNotFoundError):
    """Raised when Discussion is requested before prior sections and reference evidence exist."""


class DiscussionCitationIntegrityError(RuntimeError):
    """Raised when Discussion citation evidence cannot be matched to the BibTeX library."""


def _read_citation_evidence(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _bibtex_keys(content: str) -> set[str]:
    return bibtex_keys_in_text(content)


def _require_inputs(project_path: Path) -> tuple[str, str, str, list[dict[str, str]]]:
    missing = [relative for relative in DISCUSSION_INPUTS if not (project_path / relative).exists()]
    if missing:
        raise MissingDiscussionInputsError(
            "Discussion writing requires research plan, Introduction, Results, and references outputs first. Missing: "
            + ", ".join(missing)
        )
    plan_text = (project_path / "research_plan" / "research_plan.md").read_text(encoding="utf-8")
    introduction_text = (project_path / "introduction" / "introduction.tex").read_text(encoding="utf-8")
    results_text = (project_path / "results" / "results.tex").read_text(encoding="utf-8")
    citation_rows = _read_citation_evidence(project_path / "references" / "citation_evidence.csv")
    bibtex = (project_path / "references" / "library.bib").read_text(encoding="utf-8")
    if not citation_rows:
        raise MissingDiscussionInputsError("references/citation_evidence.csv has no evidence rows.")
    keys = _bibtex_keys(bibtex)
    missing_keys = sorted({row.get("citation_key", "") for row in citation_rows if row.get("citation_key")} - keys)
    if missing_keys:
        raise DiscussionCitationIntegrityError(
            "Citation evidence keys are missing from library.bib: " + ", ".join(missing_keys)
        )
    return plan_text, introduction_text, results_text, citation_rows


def _safe_latex_text(text: str) -> str:
    return safe_latex_text(text)


def _paragraph(text: str) -> str:
    escaped = _safe_latex_text(text)
    escaped = re.sub(
        r"(Appendix\s+Figure|Figure)\\textasciitilde\{\}\\textbackslash\{\}ref\\\{([^{}]+)\\\}",
        r"\1~\\ref{\2}",
        escaped,
    )
    escaped = re.sub(
        r"(Figures)\\textasciitilde\{\}\\textbackslash\{\}ref\\\{([^{}]+)\\\}",
        r"\1~\\ref{\2}",
        escaped,
    )
    escaped = re.sub(r"\\textbackslash\{\}citep\\\{([^{}\\]+)\\\}", r"\\citep{\1}", escaped)
    escaped = re.sub(r"\\citep\\\{([^{}\\]+)\\\}", r"\\citep{\1}", escaped)
    return escaped


def _compact(text: str, limit: int = 300) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0] + "..."


def _rows_by_claim(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row.get("claim") or "background evidence", []).append(row)
    return grouped


def _pick(rows: list[dict[str, str]], claim: str, fallback_index: int = 0) -> dict[str, str]:
    candidates = _rows_by_claim(rows).get(claim) or rows
    return candidates[min(fallback_index, len(candidates) - 1)]


def _cite(row: dict[str, str]) -> str:
    return f"\\citep{{{row.get('citation_key')}}}"


def _evidence(row: dict[str, str]) -> str:
    return _compact(row.get("evidence_summary", ""))


def _reference_coverage_paragraphs(project_path: Path, section: str, existing_text: str) -> list[str]:
    entries = missing_entries_for_section(project_path, section, existing_text)
    if not entries:
        return []
    sentences = []
    for entry in entries:
        evidence = _compact(str(entry.get("evidence_summary") or entry.get("title") or "This retained reference provides relevant context."))
        key = str(entry.get("citation_key") or "")
        if key:
            sentences.append(f"{evidence} \\citep{{{key}}}.")
    paragraphs = []
    for index in range(0, len(sentences), 4):
        paragraphs.append(
            "Additional retained references delimit how the present findings compare with prior work and where the current interpretation remains cautious. "
            + " ".join(sentences[index:index + 4])
        )
    return paragraphs


def _manuscript_context_text(text: str) -> str:
    cleaned = str(text or "")
    replacements = {
        "an auditable Draftpaper-loop workflow": "a reproducible empirical design",
        "auditable Draftpaper-loop workflow": "reproducible empirical design",
        "Draftpaper-loop workflow": "reproducible empirical design",
        "Draftpaper-loop": "the drafting tool",
        "publication-ready PNG figure generation": "scientific figure production",
        "figure-level metadata": "figure interpretation records",
        "data inventory": "data characterization",
        "method verification": "method evaluation",
        "manuscript writing": "manuscript interpretation",
        "method verification manifest": "method outputs",
        "Results manifest": "result figures and tables",
        "citation-evidence table": "citation evidence",
        "project artifacts": "empirical evidence",
        "result artifacts": "result figures and tables",
        "result files": "result figures and tables",
        "generated project outputs": "generated empirical outputs",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return re.sub(r"\s+", " ", cleaned).strip()


def _sanitize_discussion_artifacts(text: str) -> str:
    cleaned = _manuscript_context_text(str(text or ""))
    replacements = [
        (r"\bresults[/\\]figures[/\\][^\s{}]+", "the corresponding result figure"),
        (r"\bresults[/\\]tables[/\\][^\s{}]+", "the corresponding quantitative table"),
        (r"\bdata[/\\](?:raw|processed)[/\\][^\s{}]+", "the verified data product"),
        (r"\bmethods[/\\][^\s{}]+", "the implemented method evidence"),
        (r"\b[A-Za-z]:[/\\][^\s{}]+", "the local empirical evidence"),
        (r"\b[\w.-]+\.(?:png|jpg|jpeg|pdf|svg)\b", "the result figure"),
        (r"\b[\w.-]+\.(?:csv|tsv|xlsx|json|yaml|yml|py|html|md|tex|fits|zip)\b", "the analysis evidence"),
    ]
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.I)
    cleaned = re.sub(r"\b(?:manifest|artifact|file path|filename|local file)\b", "evidence record", cleaned, flags=re.I)
    return re.sub(r"\s+", " ", cleaned).strip()


def _result_signal(results_text: str) -> str:
    subsection_match = re.search(r"\\subsection\{([^{}]+)\}", results_text)
    if subsection_match:
        return _sanitize_discussion_artifacts(subsection_match.group(1))
    refs = re.findall(r"(?:Appendix\s+)?Figure~?\\ref\{([^{}]+)\}", results_text)
    if refs:
        main_refs = [item for item in refs if "appendix" not in item.lower()]
        selected = main_refs[:2] or refs[:2]
        return "the classification and diagnostic evidence summarized in " + " and ".join(f"Figure~\\ref{{{item}}}" for item in selected)
    figure_match = re.search(r"\\includegraphics(?:\[[^\]]+\])?\{([^{}]+)\}", results_text)
    if figure_match:
        return "the primary result figure"
    return "the verified result figures and diagnostic evidence"


def _result_anchor(results_text: str) -> str:
    metric_match = re.search(r"\b(?:F1|AUC|R\^?2|accuracy|balanced accuracy|r)\s*[=：:]\s*[-+]?\d+(?:\.\d+)?", results_text, flags=re.I)
    figure_match = re.search(r"Figure~?\\ref\{([^{}]+)\}|Figures?~?\\ref\{([^{}]+)\}", results_text)
    parts = []
    if metric_match:
        parts.append(metric_match.group(0))
    if figure_match:
        parts.append("figure " + next(group for group in figure_match.groups() if group))
    return _sanitize_discussion_artifacts("; ".join(parts) or _compact(_manuscript_context_text(results_text), 220))


def _load_literature_items(project_path: Path) -> dict[str, dict[str, Any]]:
    path = project_path / "references" / "literature_items.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    items = payload if isinstance(payload, list) else payload.get("items") if isinstance(payload, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("bibtex_key") or item.get("citation_key") or "")
        if key:
            result[key] = item
    return result


def prepare_discussion_comparison(project: str | Path) -> dict[str, Any]:
    """Prepare a comparison-literature matrix before writing Discussion."""
    state = load_project(project)
    plan_text, introduction_text, results_text, citation_rows = _require_inputs(state.path)
    _ = plan_text, introduction_text
    discussion_dir = state.path / "discussion"
    discussion_dir.mkdir(parents=True, exist_ok=True)
    literature = _load_literature_items(state.path)
    result_anchor = _result_anchor(results_text)
    matrix_path = discussion_dir / "comparison_literature_matrix.csv"
    notes_path = discussion_dir / "comparison_evidence_notes.html"
    plan_path = discussion_dir / "innovation_limitations_plan.json"
    rows = []
    for row in citation_rows:
        key = str(row.get("citation_key") or "")
        section = str(row.get("section") or "")
        if section and section not in {"discussion", "introduction", "methods", "results", "data"}:
            continue
        item = literature.get(key, {})
        summary = (
            ((item.get("deep_summary") or {}).get("results") if isinstance(item.get("deep_summary"), dict) else "")
            or row.get("evidence_summary")
            or item.get("abstract")
            or item.get("title")
            or ""
        )
        comparison_mode = "method_or_result_comparison" if any(token in summary.lower() for token in ["metric", "result", "validation", "classification", "model"]) else "background_boundary"
        rows.append({
            "citation_key": key,
            "result_anchor": result_anchor,
            "comparison_mode": comparison_mode,
            "prior_evidence_summary": _compact(str(summary), 420),
            "discussion_use": "compare local result strength, method behavior, innovation boundary, or limitation",
            "doi": row.get("doi") or item.get("doi") or "",
            "url": row.get("url") or item.get("url") or "",
        })
    if not rows:
        raise MissingDiscussionInputsError("No citation evidence rows are available for discussion comparison.")
    with matrix_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    notes = [
        "# Discussion Comparison Evidence",
        "",
        f"Result anchor: {result_anchor}",
        "",
        "| Citation | Comparison mode | Prior evidence |",
        "| --- | --- | --- |",
    ]
    for item in rows:
        notes.append(
            f"| {item['citation_key']} | {item['comparison_mode']} | {item['prior_evidence_summary']} |"
        )
    write_html_report(notes_path, "\n".join(notes), title="Discussion Comparison Evidence")
    _write_json(plan_path, {
        "status": "written",
        "result_anchor": result_anchor,
        "comparison_count": len(rows),
        "innovation_prompts": [
            "State what the verified local results add relative to the comparison matrix.",
            "Separate method novelty from dataset novelty and result strength.",
        ],
        "limitation_prompts": [
            "Identify where local metrics, sample support, validation design, or data provenance are weaker than prior work.",
            "Keep future-work claims tied to comparison evidence rather than broad promises.",
        ],
    })
    return {
        "status": "written",
        "project_path": str(state.path),
        "comparison_literature_matrix": str(matrix_path),
        "comparison_evidence_notes": str(notes_path),
        "innovation_limitations_plan": str(plan_path),
        "comparison_count": len(rows),
    }


def _expected_contribution(plan_text: str) -> str:
    match = re.search(r"## Expected Contribution\s+(.*?)(?:\n## |\Z)", plan_text, flags=re.S)
    if match:
        return _compact(_manuscript_context_text(match.group(1)), 360)
    return "the traceable connection between the research gap, local evidence, verified methods, and result interpretation"


def _method_route(plan_text: str) -> str:
    match = re.search(r"## Method Route\s+(.*?)(?:\n## |\Z)", plan_text, flags=re.S)
    if match:
        return _compact(_manuscript_context_text(match.group(1)), 360)
    return "the planned method route"


def render_discussion_tex(
    project_meta: dict[str, Any],
    plan_text: str,
    introduction_text: str,
    results_text: str,
    citation_rows: list[dict[str, str]],
    project_path: Path | None = None,
) -> str:
    idea = project_meta.get("idea") or project_meta.get("title") or "the proposed study"
    field = project_meta.get("field") or "the target field"
    background = _pick(citation_rows, "background evidence", 0)
    data = _pick(citation_rows, "data background", 0)
    method = _pick(citation_rows, "method background", 0)
    gap = _pick(citation_rows, "current gap", 0)
    result_signal = _result_signal(results_text)
    contribution = _expected_contribution(plan_text)
    method_route = _method_route(plan_text)
    intro_citation_count = len(re.findall(r"\\cite[a-zA-Z*]*\{", introduction_text))

    paragraphs = [
        "\\section{Discussion}",
        (
            f"The findings provide evidence for a reproducible empirical design for {idea} rather than an isolated modelling result. "
            f"In {field}, the literature basis identifies a concrete gap: {_evidence(gap)} {_cite(gap)}. The local results, especially {result_signal}, "
            f"matter because they connect the planned research question to empirical evidence from the current analysis rather than to unsupported narrative claims."
        ),
        (
            f"The main contribution is consistent with the research plan: {contribution} This contribution extends the Introduction rather than repeating it, "
            f"because the Discussion relates the retrieved literature to what the result figures and quantitative diagnostics show. The Introduction used {intro_citation_count} "
            f"citation-backed statements to establish the study frame, and the present section uses those evidence records to explain why the results are meaningful."
        ),
        (
            f"Compared with existing work, the local findings are most informative where they agree with or depart from the cited evidence. "
            f"Prior data-oriented work indicates that {_evidence(data).lower()} {_cite(data)}. Method-oriented work further suggests that {_evidence(method).lower()} {_cite(method)}. "
            f"The present results are therefore interpreted through data construction, validation design, and method behavior rather than through a broad claim of novelty."
        ),
        (
            f"Limitations and future work follow the same evidence boundary. The principal limitation is that the interpretation remains constrained by the available empirical evidence. When local results are preliminary, sparse, "
            f"or generated from a narrow validation setting, the defensible conclusion is correspondingly narrow and cannot be converted into a general population-level claim. "
            f"The method route also requires continued checking: {method_route} Future revisions can extend the claim only when the result figures, quantitative diagnostics, method outputs, "
            f"and citation evidence jointly support a broader interpretation."
        ),
        (
            f"Overall, the study is best presented as a literature-informed and locally reproducible answer to the gap identified above. Background evidence shows why the topic is relevant. "
            f"{_evidence(background)} {_cite(background)}. The result figures and quantitative diagnostics determine how far the manuscript can go in interpreting the specific findings. This keeps the Discussion aligned with the "
            f"paper's evidence trail and avoids adding claims that are not supported by either the retrieved literature or the empirical outputs."
        ),
    ]
    if project_path is not None:
        ensure_reference_usage_plan(project_path)
        paragraphs.extend(_reference_coverage_paragraphs(project_path, "discussion", "\n\n".join(paragraphs)))
    sanitized = [paragraph if paragraph.startswith("\\section") else _sanitize_discussion_artifacts(paragraph) for paragraph in paragraphs]
    tex = "\n\n".join(_paragraph(paragraph) if not paragraph.startswith("\\section") else paragraph for paragraph in sanitized) + "\n"
    forbidden = re.search(r"\b[A-Za-z]:[/\\][^\s{}]+|\b(?:results|data|methods|code)[/\\][^\s{}]+|\b[\w.-]+\.(?:png|jpg|jpeg|csv|json|py|html|md|tex)\b", tex, flags=re.I)
    if forbidden:
        tex = re.sub(r"\b[A-Za-z]:[/\\][^\s{}]+", "local empirical evidence", tex)
        tex = re.sub(r"\b(?:results|data|methods|code)[/\\][^\s{}]+", "analysis evidence", tex, flags=re.I)
        tex = re.sub(r"\b[\w.-]+\.(?:png|jpg|jpeg|csv|json|py|html|md|tex)\b", "analysis evidence", tex, flags=re.I)
    return tex


def _set_discussion_manifest(project_path: Path) -> None:
    manifest_path = project_path / "discussion" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = DISCUSSION_INPUTS
    manifest["output_files"] = DISCUSSION_OUTPUTS
    _write_json(manifest_path, manifest)


def write_discussion(project: str | Path) -> dict[str, Any]:
    """Write a traceable LaTeX Discussion from prior sections, results, and citation evidence."""
    state = load_project(project)
    plan_text, introduction_text, results_text, citation_rows = _require_inputs(state.path)
    discussion_dir = state.path / "discussion"
    discussion_dir.mkdir(parents=True, exist_ok=True)
    prepare_discussion_comparison(state.path)
    output_path = discussion_dir / "discussion.tex"
    output_path.write_text(
        render_discussion_tex(state.metadata, plan_text, introduction_text, results_text, citation_rows, state.path),
        encoding="utf-8",
    )

    update_stage_status(state.path, "discussion", "draft")
    _set_discussion_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "discussion": str(output_path),
        "citation_count": len(citation_rows),
        "outputs": DISCUSSION_OUTPUTS,
    }
