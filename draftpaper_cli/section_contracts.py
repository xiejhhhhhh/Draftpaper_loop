# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import re
from typing import Any

from .citation_utils import has_citation_command


INTERNAL_LANGUAGE = re.compile(
    r"(?:[A-Za-z]:[/\\]|results[/\\]figures|methods[/\\]|run_manifest|figure_metadata|Draftpaper[-_ ]?loop|"
    r"\b[\w.-]+\.(?:png|csv|json|py)\b)",
    flags=re.I,
)
NUMBER = re.compile(r"(?<![A-Za-z_])[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?(?![A-Za-z_])")
METRIC_NUMBER = re.compile(
    r"(?:macro[- ]?f1|f1|auc|accuracy|precision|recall|r2|r\^2|p[-_ ]?value)"
    r"[^.;\n]{0,32}?([-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?)",
    flags=re.I,
)


def _supported_numbers(registry: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for item in registry.get("records") or registry.get("evidence_records") or []:
        if not isinstance(item, dict):
            continue
        try:
            values.append(float(item.get("value")))
        except (TypeError, ValueError):
            continue
    return values


def _numeric_claims(text: str) -> list[float]:
    without_commands = re.sub(
        r"\\begin\{equation\}.*?\\end\{equation\}|\\\[.*?\\\]",
        "",
        text,
        flags=re.S,
    )
    without_commands = re.sub(r"\{[-+]?(?:\d+\.\d+|\d+)\\linewidth\}", "", without_commands)
    without_commands = re.sub(r"\\(?:ref|cite\w*)\{[^}]*\}", "", without_commands)
    without_commands = re.sub(
        r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?",
        "",
        without_commands,
    )
    values = []
    for match in NUMBER.findall(without_commands):
        try:
            values.append(float(match))
        except ValueError:
            continue
    return values


def validate_section_writing(section: str, text: str, registry: dict[str, Any]) -> dict[str, Any]:
    """Apply scientific hard gates after free-form section composition."""
    normalized_section = str(section or "").strip().lower()
    issues: list[dict[str, str]] = []
    plain_sentences = [
        re.sub(r"\s+", " ", sentence).strip().lower()
        for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\\[A-Za-z]+(?:\{[^}]*\})?", " ", text))
        if len(re.findall(r"[A-Za-z]+", sentence)) >= 8
    ]
    repeated = sorted({sentence for sentence in plain_sentences if plain_sentences.count(sentence) > 1})
    if repeated:
        issues.append({
            "severity": "blocking",
            "kind": "repeated_template_sentence",
            "detail": repeated[0],
        })
    if normalized_section == "abstract" and re.search(
        r"\b(?:to be supplied|to be completed|placeholder|tbd|insert abstract)\b",
        text,
        flags=re.I,
    ):
        issues.append({
            "severity": "blocking",
            "kind": "placeholder_abstract",
            "detail": "The abstract is still a placeholder.",
        })
    if normalized_section == "results" and has_citation_command(text):
        issues.append({
            "severity": "blocking",
            "kind": "results_citation",
            "detail": "Results must report project evidence without literature citations.",
        })
    prose_for_internal_check = re.sub(
        r"\\(?:includegraphics|input|bibliography)\*?(?:\[[^\]]*\])?\{[^}]*\}",
        "",
        text,
        flags=re.I,
    )
    if INTERNAL_LANGUAGE.search(prose_for_internal_check):
        issues.append({
            "severity": "blocking",
            "kind": "internal_artifact_language",
            "detail": "Manuscript prose contains a local path, artifact name, or workflow implementation term.",
        })
    supported = _supported_numbers(registry)
    if normalized_section in {"introduction", "data", "methods"} and re.search(
        r"\b(?:achieved|reached|obtained|yielded|attained|was)\b[^.;\n]{0,48}"
        r"(?:macro[- ]?f1|f1|auc|accuracy|precision|recall|r2|r\^2)\s*(?:=|of|was)?\s*\d",
        text,
        flags=re.I,
    ):
        issues.append({
            "severity": "blocking",
            "kind": "result_metric_leakage",
            "detail": "Observed result metrics belong in Results, not in pre-Results framing or method description.",
        })
    if normalized_section in {"results", "data", "discussion"} and supported:
        metric_values = []
        for match in METRIC_NUMBER.findall(text):
            try:
                metric_values.append(float(match))
            except ValueError:
                continue
        for value in metric_values:
            if value in {0.0, 1.0, 100.0}:
                continue
            if not any(abs(value - candidate) <= max(1e-8, abs(candidate) * 5e-5) for candidate in supported):
                issues.append({
                    "severity": "blocking",
                    "kind": "unsupported_numeric_claim",
                    "detail": str(value),
                })
    if normalized_section == "methods" and (
        "\\begin{equation}" in text or "\\[" in text
    ):
        explanatory = re.search(
            r"\b(?:where|denotes|represents|is the|are the)\b",
            text,
            flags=re.I,
        )
        if not explanatory:
            issues.append({
                "severity": "blocking",
                "kind": "unexplained_formula_variables",
                "detail": "Each displayed formula must be followed by prose defining its symbols and scientific role.",
            })
        if not re.search(
            r"\b(?:model|objective|loss|probability|feature|validation|estimate|correlation|transform|encoding|classification|regression|metric)\b",
            text,
            flags=re.I,
        ):
            issues.append({
                "severity": "blocking",
                "kind": "irrelevant_formula",
                "detail": "A displayed formula is not connected to an implemented method stage or validation quantity.",
            })
    extensions = registry.get("section_contract_extensions") if isinstance(registry, dict) else {}
    extension = extensions.get(normalized_section) if isinstance(extensions, dict) else {}
    for pattern in (extension or {}).get("forbidden_patterns") or []:
        if re.search(str(pattern), text, flags=re.I):
            issues.append({
                "severity": "blocking",
                "kind": "discipline_extension_violation",
                "detail": str(pattern),
            })
    return {
        "section": normalized_section,
        "decision": "blocked" if any(item["severity"] == "blocking" for item in issues) else "pass",
        "issues": issues,
        "policy": "Composition is free-form; only evidence grounding and manuscript hard constraints are deterministic.",
    }
