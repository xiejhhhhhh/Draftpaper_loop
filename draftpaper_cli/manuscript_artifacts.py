"""Canonical and derived manuscript-section artifact identities."""

from __future__ import annotations

from pathlib import Path


SECTION_ORDER = ("introduction", "data", "methods", "results", "discussion")

SECTION_CANONICAL_ARTIFACTS = {
    "introduction": "introduction/introduction.tex",
    "data": "data/data.tex",
    "methods": "methods/methods.tex",
    "results": "results/results.tex",
    "discussion": "discussion/discussion.tex",
}

SECTION_DERIVED_ARTIFACTS = {
    section: f"latex/sections/{section}.tex" for section in SECTION_ORDER
}

SECTION_STAGE_NAMES = {
    "introduction": "introduction",
    "data": "data_writing",
    "methods": "methods_writing",
    "results": "results",
    "discussion": "discussion",
}


def canonical_section_path(project: str | Path, section: str) -> Path:
    normalized = str(section or "").strip().lower()
    try:
        relative = SECTION_CANONICAL_ARTIFACTS[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported manuscript section: {normalized}") from exc
    return Path(project) / relative
