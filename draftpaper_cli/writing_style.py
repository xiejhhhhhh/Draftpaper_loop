# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project


STYLE_PROFILE_JSON = "writing/style_profile.json"


class WritingStyleError(RuntimeError):
    """Raised when a writing-style profile cannot be learned from a draft."""


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _resolve_tex_include(base: Path, target: str) -> Path:
    candidate = (base / target.strip()).resolve()
    if candidate.suffix:
        return candidate
    return candidate.with_suffix(".tex")


def _expand_latex_inputs(path: Path, *, seen: set[Path] | None = None, depth: int = 0) -> str:
    resolved = path.resolve()
    seen = seen or set()
    if resolved in seen or depth > 8:
        return ""
    seen.add(resolved)
    text = _read_text_file(resolved)

    def replace(match: re.Match[str]) -> str:
        include_path = _resolve_tex_include(resolved.parent, match.group(2))
        if not include_path.exists():
            return ""
        return "\n" + _expand_latex_inputs(include_path, seen=seen, depth=depth + 1) + "\n"

    return re.sub(r"\\(input|include)\{([^{}]+)\}", replace, text)


def _read_draft(path: Path) -> str:
    if not path.exists():
        raise WritingStyleError(f"Draft file does not exist: {path}")
    if path.suffix.lower() == ".pdf":
        raise WritingStyleError("PDF style learning requires a text or LaTeX export; pass main.tex when available.")
    if path.suffix.lower() == ".tex":
        return _expand_latex_inputs(path)
    return _read_text_file(path)


def _section(text: str, name: str) -> str:
    match = re.search(rf"\\section\{{{re.escape(name)}\}}(.*?)(?=\\section\{{|\Z)", text, flags=re.S | re.I)
    return match.group(1).strip() if match else ""


def _paragraph_stats(text: str) -> dict[str, Any]:
    paragraphs = [re.sub(r"\s+", " ", item).strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    word_counts = [len(re.findall(r"\b\w+\b", item)) for item in paragraphs]
    average = sum(word_counts) / len(word_counts) if word_counts else 0
    if average >= 150:
        length = "long"
    elif average >= 80:
        length = "medium"
    else:
        length = "short"
    return {"paragraph_count": len(paragraphs), "average_words": round(average, 1), "paragraph_length": length}


def _style_flags(section_text: str) -> dict[str, Any]:
    lowered = section_text.lower()
    return {
        "uses_scientific_judgment": any(token in lowered for token in ["suggest", "indicate", "imply", "consistent", "limited", "rather than"]),
        "avoids_mechanical_figure_listing": "this figure shows" not in lowered and "the corresponding evidence is shown" not in lowered,
        "prefers_metric_then_interpretation": bool(re.search(r"\b(?:f1|auc|accuracy|r\^?2|r)\s*[=:]", section_text, flags=re.I)),
        "compares_against_literature": "\\cite" in section_text and any(token in lowered for token in ["compared", "consistent with", "differs", "prior"]),
    }


def learn_writing_style_from_draft(project: str | Path, draft: str | Path) -> dict[str, Any]:
    """Extract non-verbatim writing preferences from an approved draft."""
    state = load_project(project)
    draft_path = Path(draft)
    text = _read_draft(draft_path)
    results = _section(text, "Results")
    discussion = _section(text, "Discussion")
    methods = _section(text, "Methods")
    profile = {
        "schema_version": "dpl.writing_style_profile.v2",
        "source": "derived_style_signals_only_no_verbatim_reuse",
        "results_style": {**_paragraph_stats(results), **_style_flags(results)},
        "discussion_style": {**_paragraph_stats(discussion), **_style_flags(discussion)},
        "methods_style": {**_paragraph_stats(methods), **_style_flags(methods)},
        "avoid_phrases": [
            "first establishes the main empirical pattern",
            "the second checks whether the same conclusion is stable",
            "this figure shows",
            "the corresponding evidence is shown",
            "result artifact",
            "local filenames",
        ],
        "writing_guidance": [
            "Use figure metadata and metrics to make a scientific judgment before citing the figure label.",
            "Discuss weak or negative model behavior as evidence about method limits rather than as a workflow failure.",
            "Keep artifact names, paths, and manifest terminology out of manuscript prose.",
            "Use appendix diagnostics to qualify reliability, ablation, and sensitivity claims.",
        ],
    }
    out = state.path / STYLE_PROFILE_JSON
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_json(out, profile)
    return {"status": "written", "project_path": str(state.path), "style_profile": str(out), "schema_version": profile["schema_version"]}
