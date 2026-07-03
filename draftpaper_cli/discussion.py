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
            "Additional retained references help delimit how the present findings should be compared with prior work and where the current interpretation should remain cautious. "
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


def _result_signal(results_text: str) -> str:
    subsection_match = re.search(r"\\subsection\{([^{}]+)\}", results_text)
    if subsection_match:
        return subsection_match.group(1)
    figure_match = re.search(r"\\includegraphics(?:\[[^\]]+\])?\{([^{}]+)\}", results_text)
    if figure_match:
        return f"the result artifact {figure_match.group(1)}"
    return "the registered local result artifacts"


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
            f"The findings should be interpreted as evidence for a reproducible empirical design for {idea} rather than as an isolated modelling result. "
            f"In {field}, the literature basis identified a concrete gap: {_evidence(gap)} {_cite(gap)}. The local results, especially {result_signal}, "
            f"therefore matter because they connect the planned research question to evidence generated from the current analysis rather than to unsupported narrative claims."
        ),
        (
            f"The main contribution is consistent with the research plan: {contribution} This contribution extends the Introduction rather than repeating it, "
            f"because the Discussion can now relate the retrieved literature to what the result figures and tables actually show. The Introduction used {intro_citation_count} "
            f"citation-backed statements to establish the study frame, and the present section uses those same evidence records to explain why the results are meaningful."
        ),
        (
            f"Compared with existing work, the current draft should emphasize where the local findings agree with or depart from the cited evidence. "
            f"Prior data-oriented work indicates that {_evidence(data).lower()} {_cite(data)}. Method-oriented work further suggests that {_evidence(method).lower()} {_cite(method)}. "
            f"The present results should therefore be discussed through data construction, validation design, and method behavior rather than through a broad claim of novelty."
        ),
        (
            f"Limitations and future work should be interpreted through the same evidence boundary. The principal limitation is that the present Discussion remains constrained by the available empirical evidence. If the local results are preliminary, sparse, "
            f"or generated from a narrow validation setting, the manuscript should state that limitation directly and avoid converting an observed pattern into a general conclusion. "
            f"The method route also requires continued checking: {method_route} Future revisions should update this section whenever the result figures and tables, method outputs, "
            f"or citation evidence changes, because those sources define the defensible boundary of the paper."
        ),
        (
            f"Overall, the study is best presented as a literature-informed and locally reproducible answer to the gap identified above. Background evidence shows why the topic is relevant. "
            f"{_evidence(background)} {_cite(background)}. The result figures and tables determine how far the manuscript can go in interpreting the specific findings. This keeps the Discussion aligned with the "
            f"paper's evidence trail and avoids adding claims that are not supported by either the retrieved literature or the generated empirical outputs."
        ),
    ]
    if project_path is not None:
        ensure_reference_usage_plan(project_path)
        paragraphs.extend(_reference_coverage_paragraphs(project_path, "discussion", "\n\n".join(paragraphs)))
    return "\n\n".join(_paragraph(paragraph) if not paragraph.startswith("\\section") else paragraph for paragraph in paragraphs) + "\n"


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
