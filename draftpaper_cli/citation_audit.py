# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path
from typing import Any

from .evidence_snapshot import (
    EvidenceSnapshotMismatch,
    manuscript_snapshot,
    validate_promoted_snapshot_for_writing,
)
from .metadata import GENERATOR_HTML_META
from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .review_rule_runtime import assess_review_rules


CITATION_PATTERN = re.compile(
    r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{([^{}]+)\}",
    re.IGNORECASE,
)
BIB_ENTRY_PATTERN = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n@\w+\s*\{|$)", re.IGNORECASE | re.DOTALL)
BIB_FIELD_PATTERN = re.compile(r"(\w+)\s*=\s*[\{\"]([^}\"]*)[\}\"]", re.IGNORECASE)
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")

SECTION_FILES = {
    "introduction": ["introduction/introduction.tex", "latex/sections/introduction.tex"],
    "data": ["data/data.tex", "latex/sections/data.tex"],
    "methods": ["methods/methods.tex", "latex/sections/methods.tex"],
    "discussion": ["discussion/discussion.tex", "latex/sections/discussion.tex"],
}

STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "among",
    "based",
    "because",
    "been",
    "being",
    "between",
    "both",
    "could",
    "data",
    "does",
    "for",
    "from",
    "have",
    "into",
    "model",
    "models",
    "more",
    "paper",
    "results",
    "show",
    "study",
    "such",
    "that",
    "the",
    "their",
    "these",
    "this",
    "using",
    "were",
    "when",
    "with",
}


@dataclass
class CitationUsage:
    usage_id: str
    citation_key: str
    section: str
    file: str
    passage: str
    claim: str
    verdict: str
    match_score: float
    citation_intent: str
    support_status: str
    topic_relevance_score: float
    claim_alignment_score: float
    blocking: bool
    repair_hint: str
    reasoning: str
    supporting_evidence: str
    doi: str
    url: str
    semantic_verdict: str
    semantic_checks: dict[str, Any]
    evidence_passage: str
    evidence_locator: str
    needs_review: bool


class CitationAuditError(RuntimeError):
    """Raised when the citation audit loop cannot load project artifacts."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_bib(project_path: Path) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    content = "\n".join(
        _read_text(project_path / relative)
        for relative in ["references/library.bib", "latex/library.bib"]
        if (project_path / relative).exists()
    )
    for match in BIB_ENTRY_PATTERN.finditer(content):
        key = match.group(1).strip()
        body = match.group(2)
        fields = {field.group(1).lower(): field.group(2).strip() for field in BIB_FIELD_PATTERN.finditer(body)}
        entries[key] = fields
    return entries


def _read_evidence(project_path: Path) -> dict[str, list[dict[str, str]]]:
    path = project_path / "references" / "citation_evidence.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    evidence: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        key = (row.get("citation_key") or "").strip()
        if key:
            evidence.setdefault(key, []).append(row)
    return evidence


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in WORD_PATTERN.findall(text) if token.lower() not in STOPWORDS}


def _score_overlap(left: set[str], right: set[str], *, denominator: str = "left") -> float:
    if not left or not right:
        return 0.0
    base = len(left) if denominator == "left" else len(right)
    return len(left & right) / max(1, base)


def _supporting_passage(row: dict[str, str], bib_fields: dict[str, str]) -> str:
    parts: list[str] = []
    for value in (bib_fields.get("title"), row.get("claim"), row.get("evidence_summary")):
        normalized = str(value or "").strip()
        if not normalized or normalized.lower() in {"current gap", "method background", "data background"}:
            continue
        if normalized.lower() not in {item.lower() for item in parts}:
            parts.append(normalized)
    return ". ".join(parts)


def _clean_latex(text: str) -> str:
    text = CITATION_PATTERN.sub("", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?", r"\1", text)
    text = text.replace("~", " ")
    return re.sub(r"\s+", " ", text).strip()


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    start = 0
    for match in re.finditer(r"(?<=[.!?。！？])\s+", text):
        end = match.start()
        sentence = text[start:end].strip()
        if sentence:
            spans.append((start, end, sentence))
        start = match.end()
    tail = text[start:].strip()
    if tail:
        spans.append((start, len(text), tail))
    return spans


def _best_passage_for_citation(text: str, match_start: int) -> str:
    spans = _sentence_spans(text)
    for index, (start, end, sentence) in enumerate(spans):
        if start <= match_start <= end:
            if not _tokens(_clean_latex(sentence)) and index > 0:
                return spans[index - 1][2] + " " + sentence
            return sentence
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[0] if lines else ""


def _local_citation_passage(text: str, match_start: int, match_end: int) -> str:
    """Return the clause immediately governed by one citation command."""
    for start, end, _sentence in _sentence_spans(text):
        if not (start <= match_start <= end):
            continue
        raw = text[start:end]
        citation_end = min(len(raw), max(0, match_end - start))
        prefix = raw[:citation_end]
        boundaries = [0]
        earlier_citation = CITATION_PATTERN.search(prefix, 0, max(0, match_start - start))
        if earlier_citation:
            boundaries.extend(match.end() for match in re.finditer(r";\s*", prefix))
            boundaries.extend(
                match.end()
                for match in re.finditer(r"(?:,\s*|\s+)(?:whereas|while|but)\s+", prefix, flags=re.I)
            )
            boundaries.extend(
                match.end()
                for match in re.finditer(
                    CITATION_PATTERN.pattern + r"\s*,\s*and\s+",
                    prefix,
                    flags=re.I,
                )
            )
        local = prefix[max(boundaries):].strip(" ,;\n\t")
        if not _tokens(_clean_latex(local)):
            return _best_passage_for_citation(text, match_start)
        return local or raw.strip()
    return _best_passage_for_citation(text, match_start)


def _infer_citation_intent(section: str, passage: str, evidence_text: str, bib_fields: dict[str, str]) -> str:
    blob = " ".join([passage, evidence_text, bib_fields.get("title", ""), bib_fields.get("journal", "")]).lower()
    if any(term in blob for term in ["software", "application", "tool", "package", "library", "modeling", "fitting application"]):
        return "method_tool_background"
    if section == "methods" and any(term in blob for term in ["method", "model", "baseline", "transformer", "encoding", "fitting", "feature"]):
        return "method_background"
    if section == "data" and any(term in blob for term in ["mission", "survey", "dataset", "catalog", "instrument", "telescope", "archive"]):
        return "data_source_background"
    if section == "discussion" and any(term in blob for term in ["baseline", "alternative", "comparison", "prior work", "recent work"]):
        return "comparison_context"
    if section == "discussion":
        cleaned_passage = _clean_latex(passage)
        has_causal_or_proof_claim = bool(re.search(
            r"\b(?:causes?|leads? to|results? in|improves?|increases?|reduces?|decreases?|prove[sd]?)\b",
            cleaned_passage,
            flags=re.I,
        ))
        if not has_causal_or_proof_claim and not _numbers(cleaned_passage):
            return "comparison_context"
    if section == "introduction":
        return "background_context"
    return "claim_support"


def _numbers(text: str) -> list[float]:
    text = re.sub(
        r"\b(?=[A-Za-z0-9_./+-]*[A-Za-z])(?=[A-Za-z0-9_./+-]*\d{2})[A-Za-z][A-Za-z0-9_./+-]*\b",
        " ",
        text,
    )
    values = []
    for raw in re.findall(r"(?<![A-Za-z0-9_])[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?%?(?![A-Za-z0-9_])", text):
        try:
            value = float(raw.rstrip("%"))
        except ValueError:
            continue
        values.append(value / 100.0 if raw.endswith("%") else value)
    return values


def _negated(text: str) -> bool:
    return bool(re.search(r"\b(?:no evidence|not|never|failed to|did not|does not|cannot)\b", text, flags=re.I))


def _causal_pair(text: str) -> tuple[set[str], set[str]] | None:
    match = re.search(r"(.{3,100}?)\b(?:causes?|leads? to|results? in|improves?|increases?|reduces?|decreases?)\b(.{3,100})", text, flags=re.I)
    if not match:
        return None
    return _tokens(match.group(1)), _tokens(match.group(2))


def _effect_direction(text: str) -> str:
    if re.search(r"\b(?:increase[sd]?|improve[sd]?|raise[sd]?|higher|positive)\b", text, flags=re.I):
        return "increase"
    if re.search(r"\b(?:decrease[sd]?|reduce[sd]?|lower(?:ed)?|worse|negative)\b", text, flags=re.I):
        return "decrease"
    return "unspecified"


def _semantic_support_checks(claim: str, evidence_passage: str, intent: str, lexical_alignment: float, topic_relevance: float) -> dict[str, Any]:
    claim_numbers = _numbers(claim)
    evidence_numbers = _numbers(evidence_passage)
    unmatched_numbers = [
        value for value in claim_numbers
        if not any(abs(value - candidate) <= max(1e-8, abs(candidate) * 5e-4) for candidate in evidence_numbers)
    ]
    numeric_status = "consistent" if not unmatched_numbers else "unsupported_or_mismatched"
    polarity_status = "consistent"
    if lexical_alignment >= 0.15 and _negated(claim) != _negated(evidence_passage):
        polarity_status = "possible_negation_mismatch"
    claim_cause = _causal_pair(claim)
    evidence_cause = _causal_pair(evidence_passage)
    causal_status = "not_claimed"
    if claim_cause:
        causal_status = "supported" if evidence_cause and claim_cause[0] & evidence_cause[0] and claim_cause[1] & evidence_cause[1] else "unsupported_direction"
        if evidence_cause and claim_cause[0] & evidence_cause[1] and claim_cause[1] & evidence_cause[0]:
            causal_status = "reversed_direction"
        if evidence_cause and _effect_direction(claim) != "unspecified" and _effect_direction(evidence_passage) != "unspecified" and _effect_direction(claim) != _effect_direction(evidence_passage):
            causal_status = "reversed_direction"
    strong_claim = bool(re.search(r"\b(?:prove[sd]?|demonstrate[sd]? conclusively|always|necessarily|causes?|superior|eliminates?|guarantees?)\b", claim, flags=re.I))
    cautious_evidence = bool(re.search(r"\b(?:may|might|could|suggests?|associated|correlat|preliminary|limited)\b", evidence_passage, flags=re.I))
    strength_status = "overstated" if strong_claim and cautious_evidence else "compatible"
    contradictions = []
    if polarity_status != "consistent":
        contradictions.append("negation_or_polarity")
    if causal_status in {"unsupported_direction", "reversed_direction"}:
        contradictions.append("causal_direction")
    if numeric_status != "consistent":
        contradictions.append("numeric_support")
    if contradictions:
        verdict = "contradicted_or_unsupported"
    elif strength_status == "overstated":
        verdict = "claim_too_strong"
    elif lexical_alignment >= 0.28:
        verdict = "direct_support"
    elif intent != "claim_support" and topic_relevance >= 0.45:
        verdict = "contextual_support"
    elif lexical_alignment >= 0.15:
        verdict = "partial_support"
    else:
        verdict = "insufficient_support"
    return {
        "semantic_verdict": verdict,
        "numeric_consistency": numeric_status,
        "claim_numbers": claim_numbers,
        "evidence_numbers": evidence_numbers,
        "unmatched_claim_numbers": unmatched_numbers,
        "polarity_consistency": polarity_status,
        "causal_direction_consistency": causal_status,
        "claim_strength_consistency": strength_status,
        "contradiction_types": contradictions,
        "requires_paragraph_repair": verdict in {"contradicted_or_unsupported", "claim_too_strong", "insufficient_support"},
    }


def _judge_usage(key: str, section: str, passage: str, bib: dict[str, dict[str, str]], evidence: dict[str, list[dict[str, str]]], planned_role: str | None = None) -> tuple[str, float, str, float, float, bool, str, str, str, str, str, dict[str, Any], str]:
    if key not in bib:
        semantic = {"semantic_verdict": "unverifiable", "requires_paragraph_repair": True}
        return "unverifiable", 0.0, "unknown", 0.0, 0.0, True, "resolve_bibtex_key", "The citation key is absent from BibTeX, so the cited source cannot be resolved.", "", "", "", semantic, ""
    rows = evidence.get(key) or []
    if not rows:
        fields = bib.get(key) or {}
        semantic = {"semantic_verdict": "unverifiable", "requires_paragraph_repair": True}
        return "unverifiable", 0.0, "unknown", 0.0, 0.0, True, "add_citation_evidence", "The source exists in BibTeX but has no citation_evidence row for claim-level checking.", "", fields.get("doi", ""), fields.get("url", ""), semantic, ""
    section_rows = [row for row in rows if (row.get("section") or "").strip().lower() == section]
    candidate_rows = section_rows or rows
    claim_tokens = _tokens(_clean_latex(passage))
    best_row: dict[str, str] = candidate_rows[0]
    best_score = 0.0
    for row in candidate_rows:
        evidence_text = " ".join(str(row.get(name) or "") for name in ["claim", "evidence_summary", "source", "doi", "url"])
        evidence_tokens = _tokens(evidence_text)
        if not claim_tokens or not evidence_tokens:
            score = 0.0
        else:
            score = len(claim_tokens & evidence_tokens) / max(1, len(claim_tokens))
        if score >= best_score:
            best_score = score
            best_row = row
    fields = bib.get(key) or {}
    supporting = _supporting_passage(best_row, fields)
    doi = str(best_row.get("doi") or (bib.get(key) or {}).get("doi") or "")
    url = str(best_row.get("url") or (bib.get(key) or {}).get("url") or "")
    evidence_blob = " ".join(str(best_row.get(name) or "") for name in ["claim", "evidence_summary", "source", "doi", "url"])
    evidence_tokens = _tokens(evidence_blob)
    bib_tokens = _tokens(" ".join(str(fields.get(name) or "") for name in ["title", "journal", "booktitle", "keywords"]))
    relevance_tokens = evidence_tokens | bib_tokens
    topic_relevance = max(
        best_score,
        _score_overlap(claim_tokens, relevance_tokens, denominator="right"),
        _score_overlap(relevance_tokens, claim_tokens, denominator="right"),
    )
    intent = str(planned_role or "").strip() or _infer_citation_intent(section, _clean_latex(passage), evidence_blob, fields)
    if intent != "claim_support" and (claim_tokens & relevance_tokens):
        topic_relevance = max(topic_relevance, 0.55)
    claim_alignment = best_score
    semantic = _semantic_support_checks(_clean_latex(passage), supporting, intent, claim_alignment, topic_relevance)
    semantic["citation_role_source"] = "prewriting_contract" if planned_role else "legacy_posthoc_compatibility"
    semantic_verdict = semantic["semantic_verdict"]
    locator = str(best_row.get("passage_id") or best_row.get("page") or best_row.get("section_locator") or best_row.get("source") or "")
    if semantic_verdict == "contradicted_or_unsupported":
        return "unsupported", round(claim_alignment, 3), intent, round(topic_relevance, 3), round(claim_alignment, 3), True, "agent_paragraph_rewrite_required", "The source passage conflicts with the claim's numeric, polarity, or causal semantics; preserve the reference and repair the paragraph against the passage.", supporting, doi, url, semantic, locator
    if semantic_verdict == "claim_too_strong":
        return "partially_supported", round(claim_alignment, 3), intent, round(topic_relevance, 3), round(claim_alignment, 3), True, "narrow_claim_strength", "The claim is stronger than the source passage and must be narrowed without deleting the reference.", supporting, doi, url, semantic, locator
    if semantic_verdict == "contextual_support":
        return "partially_supported", round(claim_alignment, 3), intent, round(topic_relevance, 3), round(claim_alignment, 3), False, "keep_contextual_citation", "The source is valid context or provenance; it is not treated as proof of every surrounding scientific detail.", supporting, doi, url, semantic, locator
    if claim_alignment >= 0.28:
        return "supported", round(claim_alignment, 3), intent, round(topic_relevance, 3), round(claim_alignment, 3), False, "keep_citation", "The cited source passage supports the local claim without detected numeric, polarity, causal, or strength conflict.", supporting, doi, url, semantic, locator
    if claim_alignment >= 0.15:
        return "partially_supported", round(claim_alignment, 3), intent, round(topic_relevance, 3), round(claim_alignment, 3), False, "rewrite_to_supported_claim", "The citation is topically related, but the local claim should be narrowed or supplemented.", supporting, doi, url, semantic, locator
    if topic_relevance >= 0.45:
        return "partially_supported", round(claim_alignment, 3), intent, round(topic_relevance, 3), round(claim_alignment, 3), False, "rewrite_to_contextual_citation", "The citation is highly relevant as context, method background, data-source background, or tool provenance, but the local claim is stronger than the stored evidence.", supporting, doi, url, semantic, locator
    return "unsupported", round(claim_alignment, 3), intent, round(topic_relevance, 3), round(claim_alignment, 3), True, "agent_paragraph_rewrite_required", "The local claim lacks passage-level support; keep the retained reference and repair the paragraph rather than replacing it with an evidence summary.", supporting, doi, url, semantic, locator


def _collect_usages(project_path: Path, bib: dict[str, dict[str, str]], evidence: dict[str, list[dict[str, str]]]) -> list[CitationUsage]:
    usages: list[CitationUsage] = []
    usage_plan = _read_json(project_path / "references" / "reference_usage_plan.json")
    planned_roles = {
        (str(item.get("citation_key") or ""), str(item.get("target_section") or "").lower()): str(item.get("citation_role") or item.get("citation_intent") or "")
        for item in usage_plan.get("entries") or []
        if isinstance(item, dict)
    }
    seen: set[tuple[str, str, str]] = set()
    for section, relatives in SECTION_FILES.items():
        canonical_exists = any((project_path / relative).exists() for relative in relatives if not relative.startswith("latex/sections/"))
        for relative in relatives:
            if relative.startswith("latex/sections/") and canonical_exists:
                continue
            path = project_path / relative
            if not path.exists():
                continue
            text = _read_text(path)
            for match in CITATION_PATTERN.finditer(text):
                passage = _local_citation_passage(text, match.start(), match.end())
                for raw_key in match.group(1).split(","):
                    key = raw_key.strip()
                    if not key:
                        continue
                    dedupe = (relative, key, passage)
                    if dedupe in seen:
                        continue
                    seen.add(dedupe)
                    verdict, score, intent, relevance, alignment, blocking, repair_hint, reasoning, supporting, doi, url, semantic, locator = _judge_usage(key, section, passage, bib, evidence, planned_roles.get((key, section)))
                    usage_id = f"{section}_{len(usages) + 1:03d}_{re.sub(r'[^A-Za-z0-9_-]+', '_', key)}"
                    usages.append(CitationUsage(
                        usage_id=usage_id,
                        citation_key=key,
                        section=section,
                        file=relative,
                        passage=passage,
                        claim=_clean_latex(passage),
                        verdict=verdict,
                        match_score=score,
                        citation_intent=intent,
                        support_status=(
                            "directly_supported" if verdict == "supported" else
                            "contextually_relevant" if not blocking and relevance >= 0.45 and alignment < 0.18 else
                            "partially_supported_rewrite_needed" if verdict == "partially_supported" else
                            "unverifiable" if verdict == "unverifiable" else
                            "unsupported_irrelevant"
                        ),
                        topic_relevance_score=relevance,
                        claim_alignment_score=alignment,
                        blocking=blocking,
                        repair_hint=repair_hint,
                        reasoning=reasoning,
                        supporting_evidence=supporting,
                        doi=doi,
                        url=url,
                        semantic_verdict=str(semantic.get("semantic_verdict") or "unknown"),
                        semantic_checks=semantic,
                        evidence_passage=supporting,
                        evidence_locator=locator,
                        needs_review=blocking or verdict == "partially_supported",
                    ))
    return usages


def _summary(usages: list[CitationUsage]) -> dict[str, Any]:
    counts = {name: 0 for name in ["supported", "partially_supported", "unsupported", "unverifiable"]}
    for usage in usages:
        counts[usage.verdict] = counts.get(usage.verdict, 0) + 1
    blocking = sum(1 for usage in usages if usage.blocking)
    contextual = sum(1 for usage in usages if usage.support_status == "contextually_relevant")
    low_confidence = sum(1 for usage in usages if usage.match_score < 0.55)
    average = round(sum(usage.match_score for usage in usages) / len(usages), 3) if usages else 1.0
    return {
        "total_usages": len(usages),
        "supported": counts["supported"],
        "partially_supported": counts["partially_supported"],
        "unsupported": counts["unsupported"],
        "unverifiable": counts["unverifiable"],
        "contextually_relevant": contextual,
        "low_confidence": low_confidence,
        "blocking_issue_count": blocking,
        "average_match_score": average,
    }


def _read_literature_item_keys(project_path: Path) -> dict[str, dict[str, Any]]:
    path = project_path / "references" / "literature_items.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    result: dict[str, dict[str, Any]] = {}
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            key = str(item.get("bibtex_key") or item.get("citation_key") or "").strip()
            if key:
                result[key] = item
    return result


def _read_summary_keys(project_path: Path, item_keys: dict[str, dict[str, Any]]) -> set[str]:
    summary_dir = project_path / "references" / "literature_summaries"
    keys = set(item_keys)
    if not summary_dir.exists():
        return keys
    html = "\n".join(_read_text(path) for path in summary_dir.glob("*.html"))
    lowered = html.lower()
    for key in item_keys:
        if key.lower() in lowered:
            keys.add(key)
    return keys


def _topic_suspect_keys(project_path: Path, keys: set[str], item_keys: dict[str, dict[str, Any]], evidence: dict[str, list[dict[str, str]]], usages: list[CitationUsage]) -> list[str]:
    project_json = {}
    try:
        project_json = json.loads((project_path / "project.json").read_text(encoding="utf-8-sig"))
    except Exception:
        project_json = {}
    project_blob = " ".join([
        _read_text(project_path / "idea" / "idea.md"),
        _read_text(project_path / "research_plan" / "research_plan.md"),
        str(project_json.get("idea") or ""),
        str(project_json.get("field") or ""),
        str(project_json.get("target_journal") or ""),
        str(project_json.get("title") or ""),
        str(project_json.get("project_slug") or ""),
    ])
    project_tokens = _tokens(project_blob)
    suspects = {
        usage.citation_key
        for usage in usages
        if usage.support_status == "unsupported_irrelevant" or (usage.blocking and usage.verdict == "unsupported")
    }
    for key in sorted(keys):
        item = item_keys.get(key) or {}
        rows = evidence.get(key) or []
        ref_blob = " ".join([
            str(item.get("title") or ""),
            str(item.get("abstract") or ""),
            " ".join(str(row.get("claim") or "") + " " + str(row.get("evidence_summary") or "") for row in rows),
        ])
        ref_tokens = _tokens(ref_blob)
        if project_tokens and ref_tokens and _score_overlap(ref_tokens, project_tokens, denominator="left") < 0.05:
            suspects.add(key)
    return sorted(suspects)


def _reference_coverage(project_path: Path, usages: list[CitationUsage], evidence: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    item_keys = _read_literature_item_keys(project_path)
    summarized = _read_summary_keys(project_path, item_keys)
    cited = {usage.citation_key for usage in usages}
    suspect = _topic_suspect_keys(project_path, summarized, item_keys, evidence, usages)
    coverage = {
        "coverage_status": "passed" if not (summarized - cited) else "failed",
        "total_summarized_references": len(summarized),
        "total_cited_references": len(cited),
        "unique_cited_reference_count": len(cited),
        "summarized_reference_count": len(summarized),
        "summarized_but_uncited_count": len(summarized - cited),
        "cited_summarized_references": sorted(summarized & cited),
        "summarized_but_uncited": sorted(summarized - cited),
        "cited_but_not_summarized": sorted(cited - summarized),
        "topic_suspect_references": suspect,
        "coverage_ratio": round(len(summarized & cited) / len(summarized), 3) if summarized else 1.0,
        "review_required": sorted((summarized - cited) | set(suspect)),
    }
    return coverage


def _render_coverage_html(coverage: dict[str, Any]) -> str:
    def list_items(values: list[str]) -> str:
        return "".join(f"<li>{escape(str(value))}</li>" for value in values) or "<li>None</li>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>Reference Coverage Report</title></head>
<body>
  <h1>Reference Coverage Report</h1>
  <p>Status: {escape(str(coverage.get('coverage_status') or 'unknown'))}</p>
  <p>Total summarized references: {coverage.get('total_summarized_references', 0)}</p>
  <p>Total cited references: {coverage.get('total_cited_references', 0)}</p>
  <p>Coverage ratio: {coverage.get('coverage_ratio', 1.0)}</p>
  <h2>summarized but uncited</h2><ul>{list_items(coverage.get('summarized_but_uncited') or [])}</ul>
  <h2>Topic Suspect References</h2><ul>{list_items(coverage.get('topic_suspect_references') or [])}</ul>
  <h2>Review Required</h2><ul>{list_items(coverage.get('review_required') or [])}</ul>
</body>
</html>
"""


def _next_iteration(audit_dir: Path) -> int:
    iteration_dir = audit_dir / "iterations"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    indices = []
    for path in iteration_dir.glob("citation_audit_iteration_*.html"):
        match = re.search(r"_(\d+)\.html$", path.name)
        if match:
            indices.append(int(match.group(1)))
    return (max(indices) + 1) if indices else 1


def _render_html(report: dict[str, Any], *, title: str) -> str:
    summary = report.get("summary") or {}
    coverage = report.get("reference_coverage") or {}
    rows = []
    for usage in report.get("usages") or []:
        verdict = str(usage.get("verdict") or "unverifiable")
        score = float(usage.get("match_score") or 0)
        percent = max(0, min(100, int(round(score * 100))))
        rows.append(
            "<article class='ref-card'>"
            f"<div class='card-head'><span class='ref-id'>{escape(str(usage.get('citation_key') or ''))}</span>"
            f"<span class='verdict verdict-{escape(verdict)}'>{escape(verdict)}</span></div>"
            f"<p class='meta'>{escape(str(usage.get('section') or ''))} · {escape(str(usage.get('file') or ''))}</p>"
            f"<p><strong>Claim</strong>: {escape(str(usage.get('claim') or ''))}</p>"
            f"<p><strong>Evidence</strong>: {escape(str(usage.get('supporting_evidence') or ''))}</p>"
            f"<p><strong>Reasoning</strong>: {escape(str(usage.get('reasoning') or ''))}</p>"
            f"<p><strong>Intent</strong>: {escape(str(usage.get('citation_intent') or 'unknown'))} · "
            f"support status {escape(str(usage.get('support_status') or 'unknown'))} · "
            f"topic relevance {float(usage.get('topic_relevance_score') or 0):.3f} · "
            f"claim alignment {float(usage.get('claim_alignment_score') or 0):.3f} · "
            f"blocking {escape(str(usage.get('blocking') or False))}</p>"
            f"<div class='score'><span style='width:{percent}%'></span></div><p class='meta'>match score {score:.3f}</p>"
            "</article>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
{GENERATOR_HTML_META.rstrip()}
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg-paper:#faf9f5; --bg-soft:#f5f3ec; --ink:#1a1d2a; --ink-soft:#4a4f5f;
      --hairline:#e7e4d9; --positive:#0891b2; --attention:#8a6d3b; --negative:#c0392b; --neutral:#4a4f5f;
      --positive-bg:#e6f9fc; --attention-bg:#faf3e4; --negative-bg:#fbeceb; --neutral-bg:#f1f0ec;
    }}
    body {{ font-family: Georgia, 'Noto Serif SC', serif; color:var(--ink); background:var(--bg-paper); max-width:1000px; margin:0 auto; padding:40px 32px 80px; line-height:1.7; }}
    .report-header {{ display:flex; gap:18px; align-items:center; border-bottom:1px solid var(--hairline); padding-bottom:18px; margin-bottom:28px; }}
    .seal {{ width:56px; height:56px; border-radius:12px; background:var(--negative); color:white; display:flex; align-items:center; justify-content:center; font-size:28px; font-weight:700; }}
    h1 {{ font-size:28px; margin:0; }} .subtitle,.meta {{ color:var(--ink-soft); font-size:13px; }}
    .summary-grid {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin:22px 0 30px; }}
    .summary-card {{ background:var(--bg-soft); border:1px solid var(--hairline); border-radius:8px; padding:14px; text-align:center; }}
    .summary-card .num {{ font-family:Consolas,monospace; font-size:26px; }}
    .ref-card {{ background:white; border:1px solid var(--hairline); border-radius:8px; padding:18px; margin:14px 0; }}
    .card-head {{ display:flex; justify-content:space-between; gap:12px; align-items:center; }}
    .ref-id {{ font-family:Consolas,monospace; font-weight:700; }}
    .verdict {{ border-radius:999px; padding:3px 10px; font-family:Consolas,monospace; font-size:12px; }}
    .verdict-supported {{ color:var(--positive); background:var(--positive-bg); }}
    .verdict-partially_supported {{ color:var(--attention); background:var(--attention-bg); }}
    .verdict-unsupported {{ color:var(--negative); background:var(--negative-bg); }}
    .verdict-unverifiable {{ color:var(--neutral); background:var(--neutral-bg); }}
    .score {{ height:7px; background:#e7e4d9; border-radius:999px; overflow:hidden; }}
    .score span {{ display:block; height:100%; background:var(--positive); }}
  </style>
</head>
<body>
  <header class="report-header"><div class="seal">引</div><div><h1>{escape(title)}</h1><p class="subtitle">Generated at {escape(str(report.get('generated_at') or ''))} · status {escape(str(report.get('status') or ''))}</p></div></header>
  <section class="summary-grid">
    <div class="summary-card"><div class="num">{summary.get('total_usages', 0)}</div><div>citation usages</div></div>
    <div class="summary-card"><div class="num">{summary.get('supported', 0)}</div><div>supported</div></div>
    <div class="summary-card"><div class="num">{summary.get('partially_supported', 0)}</div><div>partial</div></div>
    <div class="summary-card"><div class="num">{summary.get('unsupported', 0)}</div><div>unsupported</div></div>
    <div class="summary-card"><div class="num">{summary.get('unverifiable', 0)}</div><div>unverifiable</div></div>
  </section>
  <h2>Claim-level Citation Audit</h2>
  {''.join(rows) if rows else '<p>No citation usages were found.</p>'}
  <h2>Reference Coverage</h2>
  <p>Status: {escape(str(coverage.get('coverage_status') or 'unknown'))}. The audit found {coverage.get('unique_cited_reference_count', 0)} unique cited references from {coverage.get('summarized_reference_count', 0)} retained literature summaries.</p>
  <p>summarized but uncited references: {coverage.get('summarized_but_uncited_count', 0)}. Coverage ratio: {coverage.get('coverage_ratio', 1.0)}.</p>
  <h3>Cited summarized references</h3>
  <ul>{''.join(f'<li>{escape(str(item))}</li>' for item in coverage.get('cited_summarized_references') or []) or '<li>None</li>'}</ul>
  <h3>summarized but uncited</h3>
  <ul>{''.join(f'<li>{escape(str(item))}</li>' for item in coverage.get('summarized_but_uncited') or []) or '<li>None</li>'}</ul>
  <h3>Topic suspect references</h3>
  <ul>{''.join(f'<li>{escape(str(item))}</li>' for item in coverage.get('topic_suspect_references') or []) or '<li>None</li>'}</ul>
  <h2>Discipline Review Rules</h2>
  <p>Decision: {escape(str(report.get('review_rule_gate_decision') or 'not assessed'))}.</p>
  <ul>{''.join(
      f'<li>{escape(str(item.get("rule_id") or "review_rule"))}: {escape(str(item.get("decision") or "unknown"))}</li>'
      for item in ((report.get('review_rule_gate') or {}).get('rule_assessments') or [])
      if isinstance(item, dict) and item.get('decision') != 'satisfied'
  ) or '<li>No active discipline review-rule issue.</li>'}</ul>
</body>
</html>
"""


def audit_citations(project: str | Path, *, final: bool = False) -> dict[str, Any]:
    """Run a local claim-level citation audit and write JSON/HTML reports."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise CitationAuditError(str(exc)) from exc

    if final:
        required_sections = [
            "introduction/introduction.tex",
            "data/data.tex",
            "methods/methods.tex",
            "results/results.tex",
            "discussion/discussion.tex",
        ]
        missing_sections = [relative for relative in required_sections if not (state.path / relative).is_file()]
        if missing_sections:
            raise CitationAuditError(
                "Final citation audit requires all final manuscript sections and must run after writing: "
                + ", ".join(missing_sections)
            )
        try:
            promoted_snapshot = validate_promoted_snapshot_for_writing(state.path)
        except EvidenceSnapshotMismatch as exc:
            raise CitationAuditError(str(exc)) from exc
    else:
        promoted_snapshot = {}

    stale_marker_path = state.path / "citation_audit" / "stale_marker.json"
    stale_marker = _read_json(stale_marker_path) if stale_marker_path.is_file() else {}
    bib = _read_bib(state.path)
    evidence = _read_evidence(state.path)
    usages = _collect_usages(state.path, bib, evidence)
    summary = _summary(usages)
    coverage = _reference_coverage(state.path, usages, evidence)
    summary["unique_cited_reference_count"] = coverage.get("unique_cited_reference_count", 0)
    summary["summarized_reference_count"] = coverage.get("summarized_reference_count", 0)
    summary["summarized_but_uncited_count"] = coverage.get("summarized_but_uncited_count", 0)
    summary["reference_coverage_status"] = coverage.get("coverage_status", "unknown")
    review_rule_gate = assess_review_rules(
        state.path,
        stage="citation_audit",
        evidence_context={
            "available_evidence_roles": [
                "citation_audit",
                "citation_evidence",
                "manuscript_claims",
                "reference_coverage",
            ],
            "observed_conflicts": [
                "unsupported_claim" if summary.get("unsupported") else "",
                "citation_scope_mismatch" if summary.get("partially_supported") else "",
            ],
        },
        write_path=state.path / "citation_audit" / "review_rule_gate_report.json",
    )
    status = "passed" if (
        summary["blocking_issue_count"] == 0
        and coverage.get("coverage_status") == "passed"
        and review_rule_gate.get("decision") != "revise_required"
    ) else "failed"
    report = {
        "status": status,
        "generated_at": utc_now(),
        "project_path": str(state.path),
        "strict_target": {
            "unsupported": 0,
            "unverifiable": 0,
            "not_found": 0,
            "missing_from_list": 0,
            "orphan_in_list": 0,
            "minimum_average_match_score": 0.65,
            "blocking_issue_count": 0,
            "summarized_but_uncited": 0,
        },
        "summary": summary,
        "reference_coverage": coverage,
        "review_rule_gate_decision": review_rule_gate.get("decision"),
        "review_rule_gate_report": "citation_audit/review_rule_gate_report.json",
        "review_rule_gate": review_rule_gate,
        "review_rule_rescue_tasks": review_rule_gate.get("rescue_tasks") or [],
        "recommended_next_commands": review_rule_gate.get("recommended_next_commands") or [],
        "usages": [asdict(usage) for usage in usages],
        "manuscript_snapshot": manuscript_snapshot(state.path),
        "evidence_snapshot_id": str(promoted_snapshot.get("snapshot_id") or "legacy_unpromoted"),
        "superseded_stale_marker": stale_marker if final else {},
    }
    audit_dir = state.path / "citation_audit"
    iteration_dir = audit_dir / "iterations"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    _write_json(audit_dir / "citation_audit_report.json", report)
    _write_json(audit_dir / "reference_coverage_report.json", coverage)
    (audit_dir / "reference_coverage_report.html").write_text(_render_coverage_html(coverage), encoding="utf-8")
    title = "引用核查报告" if not final else "最终达标引用核查报告"
    html = _render_html(report, title=title)
    (audit_dir / "citation_audit_report.html").write_text(html, encoding="utf-8")
    index = _next_iteration(audit_dir)
    (iteration_dir / f"citation_audit_iteration_{index:03d}.html").write_text(html, encoding="utf-8")
    if final and status == "passed":
        (audit_dir / "final_citation_audit_report.html").write_text(html, encoding="utf-8")
        _write_json(audit_dir / "final_citation_audit_report.json", report)
        stale_marker_path.unlink(missing_ok=True)
    return report
