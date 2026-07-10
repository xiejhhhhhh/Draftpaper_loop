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
from .manuscript_composer import SectionCompositionError, select_validated_section_draft
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status
from .reference_usage import ensure_reference_usage_plan, missing_entries_for_section


INTRODUCTION_INPUTS = [
    "research_plan/research_plan.md",
    "references/literature_review_notes.md",
    "references/citation_evidence.csv",
    "references/library.bib",
]

INTRODUCTION_OUTPUTS = [
    "introduction/introduction.tex",
]


class MissingIntroductionInputsError(FileNotFoundError):
    """Raised when Introduction is requested before plan and reference evidence exist."""


class CitationIntegrityError(RuntimeError):
    """Raised when citation evidence cannot be matched to the BibTeX library."""


def _read_citation_evidence(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _bibtex_keys(content: str) -> set[str]:
    return bibtex_keys_in_text(content)


def _require_inputs(project_path: Path) -> tuple[str, list[dict[str, str]]]:
    missing = [relative for relative in INTRODUCTION_INPUTS if not (project_path / relative).exists()]
    if missing:
        raise MissingIntroductionInputsError(
            "Introduction writing requires research plan and references outputs first. Missing: "
            + ", ".join(missing)
        )
    plan_text = (project_path / "research_plan" / "research_plan.md").read_text(encoding="utf-8")
    citation_rows = _read_citation_evidence(project_path / "references" / "citation_evidence.csv")
    bibtex = (project_path / "references" / "library.bib").read_text(encoding="utf-8")
    if not citation_rows:
        raise MissingIntroductionInputsError("references/citation_evidence.csv has no evidence rows.")
    keys = _bibtex_keys(bibtex)
    missing_keys = sorted({row.get("citation_key", "") for row in citation_rows if row.get("citation_key")} - keys)
    if missing_keys:
        raise CitationIntegrityError("Citation evidence keys are missing from library.bib: " + ", ".join(missing_keys))
    return plan_text, citation_rows


def _safe_latex_text(text: str) -> str:
    return safe_latex_text(text)


def _compact(text: str, limit: int = 280) -> str:
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


def _evidence(row: dict[str, str]) -> str:
    return _compact(row.get("evidence_summary", ""))


def _paragraph(text: str) -> str:
    # Escape normal text first, then restore citation commands inserted by this module.
    escaped = _safe_latex_text(text)
    escaped = re.sub(r"\\textbackslash\{\}citep\\\{([^{}\\]+)\\\}", r"\\citep{\1}", escaped)
    escaped = re.sub(r"\\citep\\\{([^{}\\]+)\\\}", r"\\citep{\1}", escaped)
    return escaped


def _cite(row: dict[str, str]) -> str:
    return f"\\citep{{{row.get('citation_key')}}}"


_INTRO_STOPWORDS = {
    "study",
    "paper",
    "research",
    "analysis",
    "method",
    "model",
    "models",
    "data",
    "using",
    "based",
    "with",
    "from",
    "field",
    "astronomy",
    "machine",
    "learning",
    "domain",
    "time",
    "long",
    "term",
    "source",
    "sources",
}
_INTRO_SHORT_KEYWORDS = {"ep", "wxt", "fxt", "agn", "xrb", "tde", "xray", "x-ray", "roc", "auc"}


def _keyword_tokens(text: str) -> set[str]:
    normalized = str(text or "").lower().replace("x-ray", "xray").replace("time-domain", "timedomain")
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    return {
        token
        for token in tokens
        if (len(token) >= 4 or token in _INTRO_SHORT_KEYWORDS)
        and token not in _INTRO_STOPWORDS
    }


def _introduction_relevance_score(row: dict[str, str], project_tokens: set[str]) -> int:
    evidence_text = " ".join(str(row.get(key) or "") for key in ["claim", "evidence_summary", "citation_key"])
    row_tokens = _keyword_tokens(evidence_text)
    overlap = project_tokens & row_tokens
    return len(overlap)


def _filter_introduction_rows(project_meta: dict[str, Any], plan_text: str, citation_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    project_text = " ".join([
        str(project_meta.get("idea") or ""),
        str(project_meta.get("title") or ""),
        str(project_meta.get("field") or ""),
    ])
    project_tokens = _keyword_tokens(project_text)
    if not project_tokens:
        return citation_rows
    scored = [
        (_introduction_relevance_score(row, project_tokens), index, row)
        for index, row in enumerate(citation_rows)
    ]
    filtered = [row for score, _index, row in scored if score >= 1]
    if not filtered:
        return citation_rows
    filtered.sort(key=lambda item: (-_introduction_relevance_score(item, project_tokens), citation_rows.index(item)))
    return filtered


def _reference_coverage_paragraphs(
    project_path: Path,
    section: str,
    existing_text: str,
    *,
    project_meta: dict[str, Any] | None = None,
    plan_text: str = "",
    preserve_all: bool = False,
) -> list[str]:
    paragraphs: list[str] = []
    entries = missing_entries_for_section(project_path, section, existing_text)
    if section == "introduction" and project_meta and not preserve_all:
        project_tokens = _keyword_tokens(" ".join([
            str(project_meta.get("idea") or ""),
            str(project_meta.get("title") or ""),
            str(project_meta.get("field") or ""),
        ]))
        entries = [
            entry for entry in entries
            if not project_tokens or _introduction_relevance_score(
                {
                    "claim": str(entry.get("intended_use") or ""),
                    "evidence_summary": str(entry.get("evidence_summary") or entry.get("title") or ""),
                    "citation_key": str(entry.get("citation_key") or ""),
                },
                project_tokens,
            ) >= 1
        ]
    if not entries:
        return paragraphs
    sentences = []
    for entry in entries:
        evidence = _compact(str(entry.get("evidence_summary") or entry.get("title") or "This retained reference provides relevant context."))
        key = str(entry.get("citation_key") or "")
        if key:
            sentences.append(f"{evidence} \\citep{{{key}}}.")
    for index in range(0, len(sentences), 4):
        chunk = sentences[index:index + 4]
        paragraphs.append(
            "The retained literature summaries also define additional background that should remain visible in the manuscript. "
            + " ".join(chunk)
        )
    return paragraphs


def render_introduction_tex(project_meta: dict[str, Any], _plan_text: str, citation_rows: list[dict[str, str]], project_path: Path | None = None) -> str:
    citation_rows = _filter_introduction_rows(project_meta, _plan_text, citation_rows)
    idea = project_meta.get("idea") or project_meta.get("title") or "the proposed study"
    field = project_meta.get("field") or "the target field"
    background = _pick(citation_rows, "background evidence", 0)
    data = _pick(citation_rows, "data background", 0)
    method = _pick(citation_rows, "method background", 0)
    gap = _pick(citation_rows, "current gap", 0)

    paragraphs = [
        (
            f"{idea} is positioned within {field}, where recent work has increasingly emphasized the need to connect "
            f"domain-specific data construction with reproducible analytical design. {_evidence(background)} {_cite(background)}. "
            f"This background motivates a study design that treats the research question, data provenance, and validation strategy "
            f"as connected parts of the same manuscript workflow."
        ),
        (
            f"The current literature also indicates that the relevant empirical setting depends on carefully prepared data rather "
            f"than on a generic modelling pipeline. {_evidence(data)} {_cite(data)}. Methodological work provides a second line of "
            f"support, because {_evidence(method).lower()} {_cite(method)}. Together, these studies suggest that the Introduction "
            f"should frame the topic through both data availability and model evaluation rather than through a broad technical claim alone."
        ),
        (
            f"The main research gap is therefore defined through traceable citation evidence instead of free-form speculation. "
            f"{_evidence(gap)} {_cite(gap)}. In practical terms, this means the proposed paper should focus on the part of the problem "
            f"that can be tested with available data, compared with defensible baselines, and evaluated under a validation protocol "
            f"that is explicit enough to support later Methods and Results sections."
        ),
        (
            f"Building on this literature-informed plan, the present study will develop a reproducible design for {idea}. The planned "
            f"contribution is not only a model or analysis result, but a complete chain from research gap, data construction, method "
            f"evaluation, and manuscript evidence. The research plan already identifies data requirements, method route, expected "
            f"figures, and user-confirmation risks, so the next writing stages should preserve that evidence trail rather than "
            f"replacing it with unsupported narrative."
        ),
    ]
    if project_path is not None:
        ensure_reference_usage_plan(project_path)
        preserve_all_references = "use all retained references" in str(_plan_text or "").lower()
        paragraphs.extend(_reference_coverage_paragraphs(
            project_path,
            "introduction",
            "\n\n".join(paragraphs),
            project_meta=project_meta,
            plan_text=_plan_text,
            preserve_all=preserve_all_references,
        ))
    return "\\section{Introduction}\n" + "\n\n".join(_paragraph(paragraph) for paragraph in paragraphs) + "\n"


def _set_introduction_manifest(project_path: Path) -> None:
    manifest_path = project_path / "introduction" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = INTRODUCTION_INPUTS
    manifest["output_files"] = INTRODUCTION_OUTPUTS
    _write_json(manifest_path, manifest)


def write_introduction(project: str | Path) -> dict[str, Any]:
    """Write a traceable LaTeX Introduction from the research plan and citation evidence."""
    state = load_project(project)
    plan_text, citation_rows = _require_inputs(state.path)
    introduction_dir = state.path / "introduction"
    introduction_dir.mkdir(parents=True, exist_ok=True)
    output_path = introduction_dir / "introduction.tex"
    fallback = render_introduction_tex(state.metadata, plan_text, citation_rows, state.path)
    try:
        composition = select_validated_section_draft(state.path, "introduction", fallback)
    except SectionCompositionError as exc:
        raise RuntimeError(str(exc)) from exc
    output_path.write_text(str(composition["text"]), encoding="utf-8")

    update_stage_status(state.path, "introduction", "draft")
    _set_introduction_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "introduction": str(output_path),
        "citation_count": len(citation_rows),
        "outputs": INTRODUCTION_OUTPUTS,
    }
