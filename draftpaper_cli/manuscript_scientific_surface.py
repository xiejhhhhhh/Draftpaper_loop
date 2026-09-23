"""Deterministic, conservative extraction of a manuscript's scientific surface."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json
from .change_impact import artifact_role_for_path
from .passport import collect_artifacts, project_root


SURFACE_SCHEMA = "dpl.manuscript_scientific_surface.v1"
_NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?%?")
_CITATION_RE = re.compile(r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear)\w*\s*(?:\[[^]]*\])?\s*\{([^}]*)\}")
_NEGATION_RE = re.compile(r"\b(?:not|no|never|without|cannot|does\s+not|did\s+not|不|无|未|不能|不支持)\b", re.I)
_CAUSAL_RE = re.compile(r"\b(?:cause|causes|caused|causal|drives?|lead(?:s|ing)?\s+to|improve(?:s|d|ment)?|associated|correlat(?:e|ed|ion))\b", re.I)
_FORMAT_COMMAND_RE = re.compile(r"\\(?:textbf|textit|texttt|textrm|textsf|emph|underline|bfseries|itshape|centering|raggedright|small|footnotesize|normalsize|large|Large|color|textcolor|vspace|hspace)\s*(?:\[[^]]*\])?\s*(?:\{([^{}]*)\})?")


def normalize_scientific_text(text: str) -> str:
    """Remove comments and presentation wrappers while preserving assertions."""
    body = re.sub(r"(?m)^\s*%.*$", "", text)
    body = re.sub(r"(?<!\\)%.*$", "", body, flags=re.M)
    previous = None
    while previous != body:
        previous = body
        body = _FORMAT_COMMAND_RE.sub(lambda match: match.group(1) or "", body)
    body = re.sub(r"\\(?:newcommand|renewcommand|setlength|addtolength)\s*(?:\[[^]]*\])?\s*\{[^{}]*\}(?:\s*\{[^{}]*\})?", "", body)
    if "\\begin{document}" in body:
        body = body.split("\\begin{document}", 1)[1]
    if "\\end{document}" in body:
        body = body.split("\\end{document}", 1)[0]
    return re.sub(r"\s+", " ", body).strip()


def _surface_for_text(text: str) -> dict[str, Any]:
    normalized = normalize_scientific_text(text)
    citations = sorted({item.strip() for group in _CITATION_RE.findall(normalized) for item in group.split(",") if item.strip()})
    numbers = _NUMBER_RE.findall(normalized)
    negations = sorted({item.lower() for item in _NEGATION_RE.findall(normalized)})
    causal_terms = sorted({item.lower() for item in _CAUSAL_RE.findall(normalized)})
    return {
        "normalized_text": normalized,
        "numbers": numbers,
        "citations": citations,
        "negations": negations,
        "causal_terms": causal_terms,
        "scientific_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    }


def compare_manuscript_text(before: str, after: str) -> dict[str, Any]:
    before_surface = _surface_for_text(before)
    after_surface = _surface_for_text(after)
    numbers_changed = before_surface["numbers"] != after_surface["numbers"]
    negation_changed = before_surface["negations"] != after_surface["negations"]
    causal_changed = before_surface["causal_terms"] != after_surface["causal_terms"]
    citations_changed = before_surface["citations"] != after_surface["citations"]
    semantic_changed = before_surface["scientific_text_sha256"] != after_surface["scientific_text_sha256"]
    if numbers_changed or negation_changed or causal_changed:
        classification = "scientific_semantics_changed"
        reason = "Numbers, direction/negation, or causal language changed."
    elif citations_changed:
        classification = "citation_change"
        reason = "Citation identities or placement changed without detected numeric/directional change."
    elif semantic_changed:
        classification = "prose_change"
        reason = "Scientific prose changed but no high-risk token family was detected."
    else:
        classification = "presentation_only"
        reason = "Only formatting or presentation wrappers changed."
    return {
        "classification": classification,
        "scientific_semantics_changed": classification == "scientific_semantics_changed",
        "presentation_changed": before != after,
        "numbers_changed": numbers_changed,
        "negation_changed": negation_changed,
        "causal_changed": causal_changed,
        "citations_changed": citations_changed,
        "reason": reason,
        "before": before_surface,
        "after": after_surface,
    }


def extract_manuscript_surface(project: str | Path, candidate_id: str | None = None) -> dict[str, Any]:
    root = project_root(project)
    artifacts: list[dict[str, Any]] = []
    for item in collect_artifacts(root):
        relative = str(item.get("path") or "")
        role, _stage = artifact_role_for_path(relative)
        if role not in {"manuscript_source", "section_prose", "citation_repair", "reference_library"}:
            continue
        path = root / relative
        if path.suffix.lower() not in {".tex", ".md", ".txt", ".bib"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        surface = _surface_for_text(text)
        artifacts.append({
            "path": relative,
            "role": role,
            "stage": _stage,
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            **surface,
        })
    payload = {"schema_version": SURFACE_SCHEMA, "candidate_id": candidate_id, "artifacts": artifacts}
    payload["surface_sha256"] = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return {**payload, "project_path": str(root), "status": "passed"}


__all__ = ["SURFACE_SCHEMA", "compare_manuscript_text", "extract_manuscript_surface", "normalize_scientific_text"]
