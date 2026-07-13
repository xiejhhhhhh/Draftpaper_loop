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
NUMBER = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?(?:(?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?(?![A-Za-z0-9_])"
)
METRIC_NUMBER = re.compile(
    r"(?P<metric>macro[- ]?f1|f1|roc[- ]?auc|auc|accuracy|precision|recall|r2|r\^2|p[-_ ]?value)"
    r"[^.;\n]{0,32}?(?P<value>[-+]?(?:(?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?)",
    flags=re.I,
)


REQUIRED_BINDING_FIELDS = (
    "evidence_id", "run_id", "cohort_id", "sample_unit", "split", "model_id", "metric_dimension",
)
SCIENTIFIC_SCOPE_FIELDS = tuple(field for field in REQUIRED_BINDING_FIELDS if field != "evidence_id")


def _strip_alphanumeric_identifiers(text: str) -> str:
    """Remove model, checkpoint, and dataset identifiers before claim parsing."""
    return re.sub(
        r"\b(?=[A-Za-z0-9_./+-]*[A-Za-z])(?=[A-Za-z0-9_./+-]*\d{2})[A-Za-z][A-Za-z0-9_./+-]*\b",
        " ",
        text,
    )


def _evidence_records(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in (registry.get("records") or registry.get("evidence_records") or [])
        if isinstance(item, dict)
    ]


def _binding_value(record: dict[str, Any], field: str) -> str:
    aliases = {"cohort_id": "cohort", "model_id": "model"}
    return str(record.get(field) or record.get(aliases.get(field, "")) or "").strip()


def _normalized_words(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _scope_mentioned(sentence: str, value: str) -> bool:
    normalized_sentence = _normalized_words(sentence)
    normalized_value = _normalized_words(value)
    if not normalized_value or normalized_value in {"main", "not applicable", "run summary"}:
        return normalized_value == "main" and bool(re.search(r"\bmain\b", normalized_sentence))
    if normalized_value in normalized_sentence:
        return True
    if len(normalized_value.split()) == 1 and len(normalized_value) >= 4:
        return bool(re.search(rf"\b{re.escape(normalized_value)}s?\b", normalized_sentence))
    return False


def _numeric_claims_with_context(text: str) -> list[dict[str, Any]]:
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
    without_commands = re.sub(
        r"\b(?:figure|fig\.?|table|panel|section|equation|appendix)\s*~?\s*\d+[A-Za-z]?\b",
        "",
        without_commands,
        flags=re.I,
    )
    without_commands = _strip_alphanumeric_identifiers(without_commands)
    claims: list[dict[str, Any]] = []
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", without_commands):
        boundaries = [0]
        boundaries.extend(
            match.start()
            for match in re.finditer(r"\b(?:whereas|while)\b|,\s*(?:whereas|while|but)\b", sentence, flags=re.I)
        )
        boundaries.extend(
            match.start()
            for match in re.finditer(r"\band\b", sentence, flags=re.I)
            if NUMBER.search(sentence[:match.start()]) and NUMBER.search(sentence[match.end():])
        )
        boundaries.append(len(sentence))
        boundaries = sorted(set(boundaries))
        for match in NUMBER.finditer(sentence):
            try:
                value = float(match.group(0).replace(",", ""))
            except ValueError:
                continue
            segment_start = max(boundary for boundary in boundaries if boundary <= match.start())
            segment_end = min(boundary for boundary in boundaries if boundary > match.start())
            local_context = sentence[segment_start:segment_end].strip(" ,")
            local_offset = sentence.find(local_context, segment_start, segment_end) if local_context else segment_start
            suffix = sentence[match.end(): match.end() + 2]
            normalized_number = match.group(0).replace(",", "")
            claims.append({
                "value": value,
                "raw_value": match.group(0),
                "decimal_places": len(normalized_number.split(".", 1)[1]) if "." in normalized_number else 0,
                "sentence": sentence.strip(),
                "local_context": local_context,
                "percent": "%" in suffix,
                "start": match.start(),
                "end": match.end(),
                "local_start": match.start() - max(local_offset, 0),
            })
    return claims


def _value_matches(claim: dict[str, Any], record: dict[str, Any]) -> bool:
    try:
        candidate = float(record.get("value"))
    except (TypeError, ValueError):
        return False
    values = [claim["value"]]
    if claim.get("percent"):
        values.append(claim["value"] / 100.0)
    decimals = int(claim.get("decimal_places") or 0)
    rounding_tolerance = 0.5 * (10 ** (-decimals)) if decimals else 1e-8
    return any(abs(value - candidate) <= max(1e-8, rounding_tolerance, abs(candidate) * 5e-5) for value in values)


def _value_distance(claim: dict[str, Any], record: dict[str, Any]) -> float:
    try:
        candidate = float(record.get("value"))
    except (TypeError, ValueError):
        return float("inf")
    values = [float(claim["value"])]
    if claim.get("percent"):
        values.append(float(claim["value"]) / 100.0)
    return min(abs(value - candidate) for value in values)


def _role_matches_sentence(record: dict[str, Any], sentence: str) -> bool:
    role = str(record.get("entity_role") or "").lower()
    normalized = _normalized_words(sentence)
    hints = {
        "source_count": ("source", "sources", "object", "objects"),
        "event_count": ("event", "events"),
        "token_bin_count": ("token", "tokens", "bins"),
        "spatial_block_count": ("region", "regions", "spatial block", "spatial blocks"),
    }
    if role in hints:
        return any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in hints[role])
    if "token" in role and re.search(r"\btokens?\b", normalized):
        return True
    if "prediction" in role and re.search(r"\bpredictions?\b", normalized):
        return True
    if role.startswith("result_metric_"):
        metric = role.removeprefix("result_metric_").replace("_", " ")
        aliases = {"f1 macro": ("macro f1", "macro-f1"), "roc auc": ("roc auc", "roc-auc", "auc")}
        terms = aliases.get(metric, (metric,))
        return any(_normalized_words(term) in normalized for term in terms)
    return False


def _metric_signal(sentence: str, claim: dict[str, Any]) -> str:
    match = next(
        (
            candidate for candidate in METRIC_NUMBER.finditer(sentence)
            if candidate.start("value") == int(claim.get("local_start", claim.get("start", -1)))
        ),
        None,
    )
    if match is None:
        return ""
    raw = _normalized_words(match.group("metric")).replace(" ", "_")
    aliases = {
        "macro_f1": "f1_macro",
        "f1": "f1",
        "roc_auc": "roc_auc",
        "auc": "auc",
        "r_2": "r2",
        "r2": "r2",
        "p_value": "p_value",
    }
    return aliases.get(raw, raw)


def _record_metric(record: dict[str, Any]) -> str:
    explicit = _normalized_words(record.get("metric_name")).replace(" ", "_")
    if explicit:
        return explicit
    role = str(record.get("entity_role") or "").lower()
    return role.removeprefix("result_metric_") if role.startswith("result_metric_") else ""


def _metric_matches(expected: str, observed: str) -> bool:
    aliases = {
        "f1": {"f1", "f1_macro", "macro_f1"},
        "f1_macro": {"f1_macro", "macro_f1"},
        "auc": {"auc", "roc_auc"},
        "roc_auc": {"roc_auc", "auc"},
        "r2": {"r2", "r_squared", "goodness_of_fit"},
        "p_value": {"p_value", "pvalue", "p"},
    }
    family = aliases.get(expected, {expected})
    return observed in family or any(observed.endswith(f"_{item}") for item in family)


def _metric_dimension_matches(record: dict[str, Any], metric: str, claim: dict[str, Any]) -> bool:
    dimension = _normalized_words(record.get("metric_dimension") or record.get("unit")).replace(" ", "_")
    if not dimension:
        return False
    if metric in {"f1", "f1_macro", "auc", "roc_auc", "accuracy", "precision", "recall", "r2"}:
        return dimension in {"score", "dimensionless_score", "probability", "proportion", "fraction", "dimensionless", "percent"}
    if metric == "p_value":
        return dimension in {"score", "probability", "proportion", "dimensionless", "p_value"}
    if claim.get("percent"):
        return dimension in {"percent", "proportion", "fraction", "score", "probability", "dimensionless"}
    return True


def _resolve_numeric_claim(
    claim: dict[str, Any], records: list[dict[str, Any]], section: str, preferred_run_id: str = "",
) -> dict[str, Any]:
    candidates = [record for record in records if _value_matches(claim, record)]
    if not candidates:
        return {
            "status": "unsupported",
            "value": claim["value"],
            "sentence": claim["sentence"],
            "scope_signals": {},
        }
    section_candidates = [
        record for record in candidates
        if not record.get("target_sections") or section in (record.get("target_sections") or [])
    ]
    if section_candidates:
        candidates = section_candidates
    preferred = [record for record in candidates if preferred_run_id and _binding_value(record, "run_id") == preferred_run_id]
    if preferred:
        candidates = preferred
    run_verified = [record for record in candidates if str(record.get("confidence") or "") == "verified_run_output"]
    if run_verified:
        candidates = run_verified
    local_context = str(claim.get("local_context") or claim["sentence"])
    metric_signal = _metric_signal(local_context, claim)
    if metric_signal:
        metric_matches = [record for record in candidates if _metric_matches(metric_signal, _record_metric(record))]
        if not metric_matches:
            return {
                "status": "metric_mismatch", "value": claim["value"], "sentence": claim["sentence"],
                "expected_metric": metric_signal,
                "candidate_metrics": sorted({_record_metric(record) for record in candidates if _record_metric(record)}),
            }
        dimension_matches = [record for record in metric_matches if _metric_dimension_matches(record, metric_signal, claim)]
        if not dimension_matches:
            return {
                "status": "metric_dimension_mismatch", "value": claim["value"], "sentence": claim["sentence"],
                "expected_metric": metric_signal,
                "candidate_dimensions": sorted({_binding_value(record, "metric_dimension") for record in metric_matches}),
            }
        candidates = dimension_matches
    else:
        role_matches = [record for record in candidates if _role_matches_sentence(record, local_context)]
        if role_matches:
            candidates = role_matches

    if candidates:
        best_distance = min(_value_distance(claim, record) for record in candidates)
        candidates = [
            record for record in candidates
            if abs(_value_distance(claim, record) - best_distance) <= 1e-12
        ]

    scope_signals: dict[str, set[str]] = {}
    for field in ("run_id", "cohort_id", "sample_unit", "split", "model_id"):
        known_all = {_binding_value(record, field) for record in records}
        mentioned = {value for value in known_all if value and _scope_mentioned(local_context, value)}
        if mentioned:
            scope_signals[field] = mentioned
            if not any(_binding_value(record, field) in mentioned for record in candidates):
                return {
                    "status": "scope_mismatch",
                    "value": claim["value"],
                    "sentence": claim["sentence"],
                    "scope_signals": {key: sorted(values) for key, values in scope_signals.items()},
                }
            candidates = [record for record in candidates if _binding_value(record, field) in mentioned]
    serialized_scope_signals = {field: sorted(values) for field, values in scope_signals.items()}

    if not candidates:
        return {
            "status": "scope_mismatch" if scope_signals else "unsupported",
            "value": claim["value"], "sentence": claim["sentence"], "scope_signals": serialized_scope_signals,
        }
    complete = [record for record in candidates if all(_binding_value(record, field) for field in REQUIRED_BINDING_FIELDS)]
    if not complete:
        return {
            "status": "incomplete_binding", "value": claim["value"], "sentence": claim["sentence"],
            "evidence_ids": [record.get("evidence_id") for record in candidates],
            "missing_fields": sorted({field for record in candidates for field in REQUIRED_BINDING_FIELDS if not _binding_value(record, field)}),
        }
    scopes = {
        tuple(_binding_value(record, field) for field in SCIENTIFIC_SCOPE_FIELDS)
        for record in complete
    }
    if len(scopes) > 1:
        return {
            "status": "ambiguous", "value": claim["value"], "sentence": claim["sentence"],
            "evidence_ids": [record.get("evidence_id") for record in complete], "scope_signals": serialized_scope_signals,
        }
    record = complete[0]
    return {
        "status": "bound", "value": claim["value"], "sentence": claim["sentence"],
        "evidence_id": record.get("evidence_id"),
        "binding": {field: _binding_value(record, field) for field in REQUIRED_BINDING_FIELDS},
    }


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
    without_commands = _strip_alphanumeric_identifiers(without_commands)
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
    control_characters = sorted({ord(character) for character in text if ord(character) < 32 and character not in "\n\r\t"})
    if control_characters:
        issues.append({
            "severity": "blocking",
            "kind": "latex_control_character",
            "detail": f"Candidate contains non-whitespace control characters: {control_characters}.",
        })
    prose_outside_math = re.sub(
        r"\\begin\{equation\}.*?\\end\{equation\}|\\\[.*?\\\]|\\\(.*?\\\)|\$[^$]*\$",
        "",
        text,
        flags=re.S,
    )
    prose_outside_math = re.sub(
        r"\\(?:includegraphics|input|label|ref|pageref|cite\w*|bibliography)\*?"
        r"(?:\[[^\]]*\])?(?:\{[^{}]*\})+",
        "",
        prose_outside_math,
        flags=re.I,
    )
    if re.search(r"(?<!\\)_[A-Za-z0-9{]", prose_outside_math):
        issues.append({
            "severity": "blocking",
            "kind": "unescaped_underscore_outside_math",
            "detail": "Candidate contains an underscore outside a LaTeX math environment.",
        })
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
    records = _evidence_records(registry)
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
    numeric_bindings: list[dict[str, Any]] = []
    if normalized_section in {"abstract", "results", "data", "discussion"}:
        for claim in _numeric_claims_with_context(text):
            binding = _resolve_numeric_claim(
                claim, records, normalized_section, str(registry.get("preferred_run_id") or ""),
            )
            numeric_bindings.append(binding)
            issue_kinds = {
                "unsupported": "unsupported_numeric_claim",
                "scope_mismatch": "numeric_claim_scope_mismatch",
                "metric_mismatch": "numeric_claim_metric_mismatch",
                "metric_dimension_mismatch": "numeric_claim_metric_dimension_mismatch",
                "incomplete_binding": "incomplete_evidence_binding",
                "ambiguous": "ambiguous_numeric_claim_binding",
            }
            if binding["status"] in issue_kinds:
                issues.append({
                    "severity": "blocking",
                    "kind": issue_kinds[binding["status"]],
                    "detail": f"{binding['value']}: {binding.get('sentence') or ''}",
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
        "numeric_claim_bindings": numeric_bindings,
        "required_binding_fields": list(REQUIRED_BINDING_FIELDS),
        "policy": "Composition is free-form; only evidence grounding and manuscript hard constraints are deterministic.",
    }
