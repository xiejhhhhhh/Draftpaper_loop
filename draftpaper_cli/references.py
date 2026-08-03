# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from collections import Counter
from html import escape
from html import unescape
from pathlib import Path
from typing import Any

from .literature_language import tokenize_multilingual

from .html_utils import write_html_report
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


REFERENCE_OUTPUTS = [
    "references/library.bib",
    "references/literature_items.json",
    "references/search_queries.json",
    "references/zotero_collection_manifest.json",
    "references/citation_evidence.csv",
    "references/literature_review_notes.md",
    "references/literature_review_notes.html",
    "references/literature_summaries/index.html",
    "references/reference_registry.json",
    "references/bibliography_contract.json",
    "references/reference_duplicate_report.json",
    "references/literature_source_registry.json",
    "references/literature_source_collection.json",
    "references/query_contract.json",
    "references/literature_candidates.jsonl",
    "references/literature_relevance_report.json",
    "references/literature_rejection_report.json",
    "references/literature_confirmation_packet.json",
    "references/literature_confirmation_packet.zh-CN.md",
    "references/unresolved_reference_tasks.json",
]

MAX_REFERENCE_ITEMS = 30
CONTEXT_MINIMUM_ITEMS = 5
RECENT_YEAR_CUTOFF = 2021
OLD_YEAR_CUTOFF = 2011
RECENT_TARGET_RATIO = 0.60


def extract_year(raw_date: str | int | None) -> str:
    match = re.search(r"(19|20)\d{2}", str(raw_date or ""))
    return match.group(0) if match else "n.d."


def citation_key(item: dict[str, Any], index: int) -> str:
    authors = item.get("authors") or []
    first_author = str(authors[0]).split()[-1] if authors else "source"
    year = extract_year(item.get("year"))
    title_word_match = re.search(r"[A-Za-z0-9]+", item.get("title", "paper"))
    title_word = title_word_match.group(0) if title_word_match else "paper"
    raw_key = f"{first_author}{year}{title_word}{index + 1}"
    return re.sub(r"[^A-Za-z0-9_:-]", "", raw_key)


def _escape_bibtex_value(value: Any) -> str:
    clean = unescape(str(value or "")).replace("\xa0", " ")
    clean = re.sub(r"\s+", " ", clean).strip()
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in clean)


def normalize_reference_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    title = " ".join(str(item.get("title") or f"Untitled source {index + 1}").split())
    authors = [str(author).strip() for author in (item.get("authors") or []) if str(author).strip()]
    search_context = str(item.get("search_context") or "idea").strip().lower()
    search_contexts = [str(context).strip().lower() for context in (item.get("search_contexts") or []) if str(context).strip()]
    if search_context and search_context not in search_contexts:
        search_contexts.append(search_context)
    raw_source = str(item.get("source_type") or "").strip()
    raw_origin = str(item.get("reference_origin") or "").strip()
    raw_provider = str(item.get("source") or "unknown").strip()
    online_providers = {"semantic_scholar", "arxiv", "crossref", "google_scholar_serpapi", "openalex", "pubmed", "europe_pmc", "dblp", "nasa_ads"}
    source_type = raw_source or ("online_search" if raw_provider in online_providers else raw_origin or raw_provider)
    source_type = {
        "existing_zotero": "zotero",
        "zotero_collection": "zotero",
        "local_folder": "local_import",
        "supplemental_external": "online_search",
    }.get(source_type, source_type)
    normalized = {
        "title": title,
        "authors": authors,
        "year": extract_year(item.get("year")),
        "doi": str(item.get("doi") or "").strip(),
        "pmid": str(item.get("pmid") or "").strip(),
        "pmcid": str(item.get("pmcid") or "").strip(),
        "arxiv_id": str(item.get("arxiv_id") or "").strip(),
        "bibcode": str(item.get("bibcode") or "").strip(),
        "openalex_id": str(item.get("openalex_id") or "").strip(),
        "url": str(item.get("url") or "").strip(),
        "abstract": " ".join(str(item.get("abstract") or "").split()),
        "venue": str(item.get("venue") or item.get("publication") or "").strip(),
        "publication": str(item.get("publication") or item.get("venue") or "").strip(),
        "volume": str(item.get("volume") or "").strip(),
        "issue": str(item.get("issue") or item.get("number") or "").strip(),
        "pages_or_article_number": str(item.get("pages_or_article_number") or item.get("pages") or item.get("page") or item.get("article_number") or "").strip(),
        "publisher": str(item.get("publisher") or "").strip(),
        "citation_count": int(item.get("citation_count") or item.get("citationCount") or 0),
        "source": str(item.get("source") or "unknown").strip(),
        "source_type": source_type,
        "reference_origin": raw_origin,
        "source_records": [dict(record) for record in (item.get("source_records") or []) if isinstance(record, dict)],
        "field_provenance": item.get("field_provenance") if isinstance(item.get("field_provenance"), dict) else {},
        "document_parses": [dict(record) for record in (item.get("document_parses") or []) if isinstance(record, dict)],
        "retained": bool(item.get("retained", False)),
        "current_project_use": str(item.get("current_project_use") or "").strip(),
        "local_file_id": str(item.get("local_file_id") or "").strip(),
        "local_document_id": str(item.get("local_document_id") or "").strip(),
        "local_file_size": int(item.get("local_file_size") or 0),
        "local_file_mtime_ns": int(item.get("local_file_mtime_ns") or 0),
        "local_mime": str(item.get("local_mime") or "").strip(),
        "local_page_count": item.get("local_page_count"),
        "local_parser": str(item.get("local_parser") or "").strip(),
        "local_parser_version": str(item.get("local_parser_version") or "").strip(),
        "local_source_id": str(item.get("local_source_id") or "").strip(),
        "local_logical_path": str(item.get("local_logical_path") or "").strip(),
        "local_attachment_path": str(item.get("local_attachment_path") or "").strip(),
        "metadata_status": str(item.get("metadata_status") or ("complete" if authors and (item.get("doi") or item.get("year")) else "incomplete")).strip(),
        "zotero_key": str(item.get("zotero_key") or "").strip(),
        "zotero_collection": str(item.get("zotero_collection") or "").strip(),
        "pdf_url": str(item.get("pdf_url") or item.get("openAccessPdf") or "").strip(),
        "pdf_path": str(item.get("pdf_path") or "").strip(),
        "pdf_text_excerpt": str(item.get("pdf_text_excerpt") or "").strip(),
        "pdf_read_status": str(item.get("pdf_read_status") or "").strip(),
        "search_context": search_context,
        "search_contexts": search_contexts or [search_context or "idea"],
        "search_query": str(item.get("search_query") or "").strip(),
        "search_queries": [str(query).strip() for query in (item.get("search_queries") or []) if str(query).strip()],
        "search_query_id": str(item.get("search_query_id") or "").strip(),
        "combination_level": str(item.get("combination_level") or "").strip(),
        "discipline_anchor": str(item.get("discipline_anchor") or "").strip(),
        "query_components": item.get("query_components") if isinstance(item.get("query_components"), dict) else {},
        "query_provenance": item.get("query_provenance") if isinstance(item.get("query_provenance"), list) else [],
        "canonical_identity": item.get("canonical_identity") if isinstance(item.get("canonical_identity"), dict) else {},
        "selection_policy": str(item.get("selection_policy") or "").strip(),
        "user_confirmed": bool(item.get("user_confirmed")),
        "prior_user_confirmed": bool(item.get("prior_user_confirmed")),
        "lineage_previous_origin": str(item.get("lineage_previous_origin") or "").strip(),
        "lineage_source_project_id": str(item.get("lineage_source_project_id") or "").strip(),
        "lineage_asset_id": str(item.get("lineage_asset_id") or "").strip(),
        "lineage_topic_overlap": [str(value) for value in (item.get("lineage_topic_overlap") or []) if str(value)],
        "lineage_domain_overlap": [str(value) for value in (item.get("lineage_domain_overlap") or []) if str(value)],
        "lineage_title_domain_overlap": [str(value) for value in (item.get("lineage_title_domain_overlap") or []) if str(value)],
        "lineage_requires_current_citation_audit": bool(item.get("lineage_requires_current_citation_audit")),
        "_lineage_runtime_verified": bool(item.get("_lineage_runtime_verified")),
        "candidate_state": str(item.get("candidate_state") or "").strip(),
        "rejection_codes": [str(value) for value in (item.get("rejection_codes") or []) if str(value).strip()],
        "topic_relevance_score": float(item.get("topic_relevance_score") or 0),
        "discipline_match_score": float(item.get("discipline_match_score") or 0),
        "role_evidence_score": float(item.get("role_evidence_score") or 0),
        "metadata_completeness_score": float(item.get("metadata_completeness_score") or 0),
        "evidence_readiness_score": float(item.get("evidence_readiness_score") or 0),
        "topic_hits": [str(value) for value in (item.get("topic_hits") or []) if str(value).strip()],
        "discipline_hypotheses": [str(value) for value in (item.get("discipline_hypotheses") or []) if str(value).strip()],
        "role_evidence": item.get("role_evidence") if isinstance(item.get("role_evidence"), dict) else {},
        "evidence_passages": [dict(value) for value in (item.get("evidence_passages") or []) if isinstance(value, dict)],
    }
    if normalized["reference_origin"] == "parent_lineage_curated" and not normalized["_lineage_runtime_verified"]:
        normalized["reference_origin"] = normalized["lineage_previous_origin"] or "unverified_lineage_carryover"
    if not normalized["query_provenance"] and normalized["search_query"]:
        normalized["query_provenance"] = [{
            "query_id": normalized["search_query_id"],
            "context": normalized["search_context"],
            "combination_level": normalized["combination_level"],
            "query": normalized["search_query"],
            "query_components": normalized["query_components"],
        }]
    if not normalized["source_records"]:
        normalized["source_records"] = [{
            "source_type": normalized["source_type"],
            "provider": normalized["source"] if normalized["source_type"] == "online_search" else "",
            "query": normalized["search_query"],
            "retention_policy": normalized["selection_policy"] or "ranked_by_relevance_and_authority",
        }]
    if not normalized["field_provenance"]:
        normalized["field_provenance"] = {
            field: normalized["source_type"]
            for field in ("title", "authors", "year", "doi", "abstract", "publication")
            if normalized.get(field)
        }
    normalized["bibtex_key"] = str(item.get("bibtex_key") or citation_key(normalized, index))
    normalized["evidence_notes"] = item.get("evidence_notes") or infer_evidence_summary(normalized)
    return normalized


def normalize_reference_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items or []:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        candidate = normalize_reference_item(item, len(normalized))
        identity = _reference_identity(candidate)
        existing = next((row for row in normalized if _reference_identity(row) == identity), None) if identity else None
        if existing is None:
            normalized.append(candidate)
        else:
            _merge_context_metadata(existing, candidate)
            for key in ("source_records", "document_parses"):
                merged = list(existing.get(key) or [])
                seen = {json.dumps(value, sort_keys=True, ensure_ascii=False) for value in merged if isinstance(value, dict)}
                for value in candidate.get(key) or []:
                    marker = json.dumps(value, sort_keys=True, ensure_ascii=False)
                    if marker not in seen:
                        merged.append(value)
                        seen.add(marker)
                existing[key] = merged
            for key in ("source_type", "reference_origin", "local_file_id", "local_source_id", "local_logical_path"):
                if candidate.get(key) and candidate.get(key) not in str(existing.get(key) or "").split("|"):
                    existing[key] = "|".join(filter(None, [str(existing.get(key) or ""), str(candidate.get(key) or "")]))
            if candidate.get("retained"):
                existing["retained"] = True
                existing["selection_policy"] = "user_curated_preserve"
    return normalized


def tokenize_for_relevance(text: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "with", "using", "based", "from", "this", "that",
        "study", "research", "paper", "method", "methods", "model", "models",
        "data", "analysis", "classification", "framework",
    }
    return {token for token in tokenize_multilingual(text) if token not in stopwords and len(token) >= 2}


def rank_text_to_score(rank_text: str) -> float:
    rank = (rank_text or "").strip().upper()
    if rank in {"TOP", "T", "Q1", "A+", "AA", "A*"}:
        return 1.0
    if rank in {"A", "Q2"}:
        return 0.85
    if rank in {"B+", "B", "Q3"}:
        return 0.65
    if rank in {"C", "Q4"}:
        return 0.4
    if rank in {"D", "E"}:
        return 0.2
    return 0.0


def infer_journal_score(publication: str) -> tuple[float, list[str]]:
    """Assign a conservative journal authority score without requiring paid rank APIs."""
    pub = (publication or "").lower()
    if not pub or pub == "arxiv":
        return (0.25 if pub == "arxiv" else 0.0), (["preprint:arXiv"] if pub == "arxiv" else [])
    top_patterns = {
        "nature": 1.0,
        "science": 1.0,
        "astrophysical journal": 0.9,
        "monthly notices": 0.9,
        "astronomy & astrophysics": 0.9,
        "astronomy and astrophysics": 0.9,
        "research in astronomy and astrophysics": 0.75,
        "publications of the astronomical society": 0.75,
        "astronomical journal": 0.85,
    }
    for pattern, score in top_patterns.items():
        if pattern in pub:
            return score, [f"heuristic:{pattern}"]
    if any(term in pub for term in ["journal", "transactions", "proceedings"]):
        return 0.45, ["heuristic:scholarly-venue"]
    return 0.2, ["heuristic:unknown-venue"]


def weight_literature_items(items: list[dict[str, Any]], idea: str = "", target_journal: str = "") -> list[dict[str, Any]]:
    """Rank literature by topic relevance, citation authority, and journal authority."""
    idea_terms = tokenize_for_relevance(idea)
    weighted = []
    for item in items:
        item_terms = tokenize_for_relevance(
            " ".join([str(item.get("title") or ""), str(item.get("abstract") or ""), str(item.get("publication") or "")])
        )
        overlap = len(idea_terms & item_terms)
        relevance = overlap / max(len(idea_terms), 1)
        citation_count = int(item.get("citation_count") or 0)
        citation_authority = min(1.0, citation_count / 300.0)
        journal_score, journal_labels = infer_journal_score(str(item.get("publication") or ""))
        venue_bonus = 0.08 if target_journal and target_journal.lower() in str(item.get("publication") or "").lower() else 0.0
        authority = (0.45 * citation_authority) + (0.55 * journal_score)
        citation_weight = min(1.0, (0.55 * relevance) + (0.30 * authority) + venue_bonus + 0.10)
        copied = dict(item)
        copied["relevance_score"] = round(relevance, 3)
        copied["authority_score"] = round(authority, 3)
        copied["citation_authority_score"] = round(citation_authority, 3)
        copied["journal_score"] = round(journal_score, 3)
        copied["journal_rank_labels"] = journal_labels
        copied["citation_weight"] = round(citation_weight, 3)
        weighted.append(copied)
    weighted.sort(key=lambda entry: (entry.get("citation_weight", 0), entry.get("citation_count", 0)), reverse=True)
    return weighted


def has_sufficient_metadata_or_pdf(item: dict[str, Any]) -> bool:
    if item.get("pdf_url") or item.get("pdf_path"):
        return True
    if _is_zotero_reference(item):
        return bool(item.get("title") and (item.get("authors") or item.get("doi") or item.get("url")))
    return bool(
        item.get("title")
        and item.get("authors")
        and item.get("year")
        and item.get("year") != "n.d."
        and item.get("abstract")
    )


def _extract_pdf_text_from_bytes(content: bytes, *, max_pages: int = 5, max_chars: int = 5000) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception:
        return ""
    parts = []
    for page in reader.pages[:max_pages]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
        if sum(len(part) for part in parts) >= max_chars:
            break
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:max_chars]


def _extract_pdf_text_from_path(path: str, *, max_pages: int = 5, max_chars: int = 5000) -> str:
    try:
        content = Path(path).read_bytes()
    except Exception:
        return ""
    return _extract_pdf_text_from_bytes(content, max_pages=max_pages, max_chars=max_chars)


def _extract_pdf_text_from_url(url: str, *, timeout: int = 8, max_bytes: int = 8_000_000) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return ""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Draftpaper-loop literature metadata reader"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read(max_bytes + 1)
    except Exception:
        return ""
    if len(content) > max_bytes:
        return ""
    return _extract_pdf_text_from_bytes(content)


def enrich_pdf_text(item: dict[str, Any]) -> dict[str, Any]:
    copied = dict(item)
    if copied.get("pdf_text_excerpt"):
        return copied
    text = ""
    if copied.get("pdf_path"):
        text = _extract_pdf_text_from_path(str(copied.get("pdf_path") or ""))
    if not text and copied.get("pdf_url"):
        text = _extract_pdf_text_from_url(str(copied.get("pdf_url") or ""))
    if text:
        copied["pdf_text_excerpt"] = text
        if not copied.get("abstract"):
            copied["abstract"] = text[:1200]
        copied["pdf_read_status"] = "quick_read"
    elif copied.get("pdf_url") or copied.get("pdf_path"):
        copied["pdf_read_status"] = "pdf_available_unreadable"
    return copied


def has_readable_evidence(item: dict[str, Any]) -> bool:
    return bool(
        item.get("abstract")
        or item.get("pdf_text_excerpt")
        or (
            item.get("reference_origin") == "parent_lineage_curated"
            and (item.get("evidence_notes") or item.get("deep_summary"))
        )
    )


def _is_zotero_reference(item: dict[str, Any]) -> bool:
    return item.get("source") == "zotero_collection" or item.get("reference_origin") == "existing_zotero"


def _is_user_curated_reference(item: dict[str, Any]) -> bool:
    return _is_zotero_reference(item) or bool(item.get("retained")) or str(item.get("selection_policy") or "") == "user_curated_preserve" or str(item.get("reference_origin") or "") in {"local_import", "manual"}


def _source_type_labels(item: dict[str, Any]) -> list[str]:
    labels = []
    aliases = {
        "existing_zotero": "zotero",
        "zotero_collection": "zotero",
        "local_folder": "local_import",
        "supplemental_external": "online_search",
        "semantic_scholar": "online_search",
        "arxiv": "online_search",
        "crossref": "online_search",
        "google_scholar_serpapi": "online_search",
        "openalex": "online_search",
        "pubmed": "online_search",
        "europe_pmc": "online_search",
        "dblp": "online_search",
        "nasa_ads": "online_search",
    }
    for record in item.get("source_records") or []:
        if isinstance(record, dict):
            value = aliases.get(str(record.get("source_type") or "").strip(), str(record.get("source_type") or "").strip())
            if value and value not in labels:
                labels.append(value)
    for value in [item.get("source_type"), item.get("source"), item.get("reference_origin")]:
        for raw_part in str(value or "").split("|"):
            clean = aliases.get(raw_part.strip(), raw_part.strip())
            if clean and clean not in labels:
                labels.append(clean)
    return labels or ["unknown"]


def _zotero_collection_label(item: dict[str, Any]) -> str:
    explicit = str(item.get("zotero_collection") or "").strip()
    if explicit:
        return explicit
    for query in [item.get("search_query"), *(item.get("search_queries") or [])]:
        match = re.match(r"\s*Zotero collection:\s*(.+?)\s*$", str(query or ""), flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _reference_identity(item: dict[str, Any]) -> str:
    """Return a stable work identity without merging unrelated same-title records."""
    identifier_fields = (
        "doi",
        "pmid",
        "pmcid",
        "arxiv_id",
        "bibcode",
        "openalex_id",
        "local_document_id",
    )
    for field in identifier_fields:
        value = str(item.get(field) or "").strip().lower()
        if value:
            value = re.sub(r"^(https?://(doi\.org/|arxiv\.org/abs/))", "", value)
            value = re.sub(r"\s+", "", value)
            return f"{field}:{value}"
    title = re.sub(r"[^a-z0-9]+", " ", str(item.get("title") or "").lower()).strip()
    authors = item.get("authors") or []
    first_author = re.sub(r"[^a-z0-9]+", " ", str(authors[0] if authors else "").lower()).strip()
    year = extract_year(item.get("year"))
    if not title:
        return ""
    return f"title:{title}|author:{first_author}|year:{year}"


def _merge_context_metadata(target: dict[str, Any], source: dict[str, Any]) -> None:
    contexts = list(target.get("search_contexts") or [target.get("search_context") or "idea"])
    for context in source.get("search_contexts") or [source.get("search_context") or "idea"]:
        clean = str(context).strip().lower()
        if clean and clean not in contexts:
            contexts.append(clean)
    queries = list(target.get("search_queries") or [])
    for query in [target.get("search_query"), source.get("search_query"), *(source.get("search_queries") or [])]:
        clean_query = str(query or "").strip()
        if clean_query and clean_query not in queries:
            queries.append(clean_query)
    target["search_contexts"] = contexts
    target["search_queries"] = queries
    provenance = list(target.get("query_provenance") or [])
    seen = {
        (
            str(entry.get("query_id") or ""),
            str(entry.get("context") or ""),
            str(entry.get("query") or ""),
        )
        for entry in provenance
        if isinstance(entry, dict)
    }
    for entry in source.get("query_provenance") or []:
        if not isinstance(entry, dict):
            continue
        key = (
            str(entry.get("query_id") or ""),
            str(entry.get("context") or ""),
            str(entry.get("query") or ""),
        )
        if key not in seen:
            provenance.append(entry)
            seen.add(key)
    target["query_provenance"] = provenance
    source_records = list(target.get("source_records") or [])
    seen_records = {json.dumps(entry, sort_keys=True, ensure_ascii=False) for entry in source_records if isinstance(entry, dict)}
    for entry in source.get("source_records") or []:
        if not isinstance(entry, dict):
            continue
        marker = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        if marker not in seen_records:
            source_records.append(entry)
            seen_records.add(marker)
    target["source_records"] = source_records
    field_provenance = dict(target.get("field_provenance") or {})
    for field, value in (source.get("field_provenance") or {}).items():
        if field not in field_provenance:
            field_provenance[field] = value
    target["field_provenance"] = field_provenance
    if source.get("retained"):
        target["retained"] = True
        target["selection_policy"] = "user_curated_preserve"


_GENERIC_RESEARCH_TERMS = {
    "after", "algorithm", "anomaly", "automated", "baseline", "bounded", "candidate", "catalog", "class",
    "control", "controlling", "deep", "detection", "dinov2", "discovery", "evaluate",
    "feature", "features", "group", "image", "imagenet", "imaging", "information", "learning",
    "machine", "missingness", "multimodal", "network", "pretrained", "prediction", "quality", "representation",
    "representations", "retain", "sample", "scientific", "selection", "self-supervised", "spatial", "supported",
    "supervised", "test", "testing", "training", "transformer", "uncertainty", "use", "validation", "visual",
    "whether", "associated", "determine", "indicator", "indicators", "limit", "limits", "measured", "objective",
    "only", "one", "provide", "provides", "quantify", "rather", "tool", "tools", "used", "activity",
    "cross-matched", "physical", "relation", "state", "states", "survey",
}

_DOMAIN_TOKEN_ALIASES = {
    "astronomical": "astronomy",
    "galaxies": "galaxy",
    "morphological": "morphology",
    "spectroscopic": "spectroscopy",
}


def domain_anchor_terms(text: str) -> set[str]:
    """Return topic terms likely to identify a scientific domain rather than a reusable method."""
    return tokenize_for_relevance(text) - _GENERIC_RESEARCH_TERMS


def domain_title_overlap(title: str, domain_terms: set[str]) -> set[str]:
    normalized_domain = {_DOMAIN_TOKEN_ALIASES.get(term, term) for term in domain_terms}
    title_terms = {_DOMAIN_TOKEN_ALIASES.get(term, term) for term in tokenize_for_relevance(title)}
    return normalized_domain & title_terms


def _year_int(item: dict[str, Any]) -> int | None:
    try:
        return int(str(item.get("year") or ""))
    except ValueError:
        return None


def _rank_for_context(items: list[dict[str, Any]], context: str, query: str, target_journal: str) -> list[dict[str, Any]]:
    weighted = weight_literature_items(items, query, target_journal)
    ranked = []
    for item in weighted:
        copied = dict(item)
        copied["context_rank_score"] = copied.get("citation_weight", 0)
        if copied.get("_lineage_runtime_verified"):
            copied["citation_weight"] = round(min(1.0, float(copied.get("citation_weight") or 0) + 0.18), 3)
            copied["context_rank_score"] = copied["citation_weight"]
        copied["search_context"] = context
        copied["search_query"] = copied.get("search_query") or query
        ranked.append(copied)
    ranked.sort(key=lambda entry: (entry.get("context_rank_score", 0), entry.get("citation_count", 0)), reverse=True)
    return ranked


def _dedupe_ranked(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    by_key: dict[str, dict[str, Any]] = {}
    deduped = []
    for item in items:
        key = _reference_identity(item)
        if not key:
            continue
        if key in seen:
            existing = by_key[key]
            _merge_context_metadata(existing, item)
            continue
        seen.add(key)
        by_key[key] = item
        deduped.append(item)
    return deduped


def _apply_age_preference(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(candidates) < limit:
        return candidates[:limit]
    not_too_old = [item for item in candidates if (_year_int(item) or 9999) >= OLD_YEAR_CUTOFF]
    pool = not_too_old if len(not_too_old) >= limit else candidates
    recent = [item for item in pool if (_year_int(item) or 0) >= RECENT_YEAR_CUTOFF]
    target_recent = int(limit * RECENT_TARGET_RATIO + 0.999)
    if len(recent) >= target_recent:
        selected = recent[:target_recent]
        selected.extend(item for item in pool if item not in selected)
        return selected[:limit]
    return pool[:limit]


def select_references_by_context(
    items: list[dict[str, Any]],
    *,
    project_text: str,
    target_journal: str,
    limit: int = MAX_REFERENCE_ITEMS,
) -> list[dict[str, Any]]:
    normalized = normalize_reference_items([
        item for item in (items or []) if str(item.get("title") or "").strip()
    ])
    has_lineage_seeds = any(item.get("_lineage_runtime_verified") for item in normalized)
    if has_lineage_seeds:
        project_terms = tokenize_for_relevance(project_text)
        domain_terms = domain_anchor_terms(project_text)
        filtered = []
        for item in normalized:
            if item.get("_lineage_runtime_verified") or item.get("user_confirmed"):
                filtered.append(item)
                continue
            canonical = item.get("canonical_identity") if isinstance(item.get("canonical_identity"), dict) else {}
            if canonical.get("status") == "verified":
                filtered.append(item)
                continue
            item_terms = tokenize_for_relevance(
                " ".join([str(item.get("title") or ""), str(item.get("abstract") or ""), str(item.get("evidence_notes") or "")])
            )
            overlap = project_terms & item_terms
            domain_overlap = overlap & domain_terms
            title_overlap = domain_title_overlap(str(item.get("title") or ""), domain_terms)
            if len(overlap) >= 2 and (
                not domain_terms or (bool(domain_overlap) and bool(title_overlap))
            ):
                filtered.append(item)
        normalized = filtered
    curated_items = []
    external_items = []
    for item in normalized:
        if _is_user_curated_reference(item):
            preserved = dict(item)
            preserved["selection_policy"] = "user_curated_preserve"
            if _is_zotero_reference(preserved):
                preserved["reference_origin"] = preserved.get("reference_origin") or "existing_zotero"
                preserved["zotero_collection"] = _zotero_collection_label(preserved)
            preserved.setdefault("citation_weight", 0)
            preserved.setdefault("relevance_score", 0)
            preserved.setdefault("authority_score", 0)
            preserved.setdefault("citation_authority_score", 0)
            preserved.setdefault("journal_score", 0)
            curated_items.append(preserved)
        elif has_sufficient_metadata_or_pdf(item) or (
            item.get("_lineage_runtime_verified")
            and item.get("title")
            and item.get("authors")
            and item.get("year") not in {None, "", "n.d."}
            and item.get("evidence_notes")
        ):
            external_items.append(item)
    by_context: dict[str, list[dict[str, Any]]] = {"idea": [], "introduction": [], "target_journal_anchor": [], "data": [], "methods": []}
    for item in external_items:
        context = str(item.get("search_context") or "idea").lower()
        if context not in by_context:
            context = "idea"
        by_context[context].append(item)
    ranked_by_context = {
        context: _rank_for_context(
            context_items,
            context,
            " ".join([project_text, " ".join(str(item.get("search_query") or "") for item in context_items)]),
            target_journal,
        )
        for context, context_items in by_context.items()
    }
    selected = []
    for context in ["data", "methods"]:
        for item in ranked_by_context[context][:CONTEXT_MINIMUM_ITEMS]:
            selected.append(item)
    remainder = _dedupe_ranked(
        selected
        + ranked_by_context["target_journal_anchor"]
        + ranked_by_context["introduction"]
        + ranked_by_context["idea"]
        + ranked_by_context["data"][CONTEXT_MINIMUM_ITEMS:]
        + ranked_by_context["methods"][CONTEXT_MINIMUM_ITEMS:]
    )
    selected_external = _apply_age_preference(remainder, limit)
    curated_by_key = {
        key: item
        for item in curated_items
        if (key := _reference_identity(item))
    }
    external_without_zotero_duplicates = []
    for item in selected_external:
        key = _reference_identity(item)
        if key and key in curated_by_key:
            _merge_context_metadata(curated_by_key[key], item)
            continue
        external_without_zotero_duplicates.append(item)
    selected_items = curated_items + external_without_zotero_duplicates
    for item in selected_items:
        item.pop("_lineage_runtime_verified", None)
    return selected_items


def generate_bibtex(items: list[dict[str, Any]]) -> str:
    entries = []
    for item in items:
        entry_type = "article" if item.get("publication") else "misc"
        fields = {
            "title": item.get("title", ""),
            "author": " and ".join(item.get("authors") or []) or "Unknown Author",
            "year": item.get("year", "n.d."),
            "journal": item.get("publication", ""),
            "volume": item.get("volume", ""),
            "number": item.get("issue", ""),
            "pages": item.get("pages_or_article_number", ""),
            "publisher": item.get("publisher", ""),
            "doi": item.get("doi", ""),
            "url": item.get("url", ""),
        }
        populated_fields = [
            f"  {name} = {{{_escape_bibtex_value(value)}}}"
            for name, value in fields.items()
            if value
        ]
        entries.append(
            f"@{entry_type}{{{item['bibtex_key']},\n"
            + ",\n".join(populated_fields)
            + "\n}"
        )
    return "\n\n".join(entries) + ("\n" if entries else "")


def _first_sentence(text: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return fallback
    match = re.search(r"(.+?[.!?])(?:\s|$)", cleaned)
    return (match.group(1) if match else cleaned[:300]).strip()


def infer_claim(item: dict[str, Any]) -> str:
    text = f"{item.get('title', '')} {item.get('abstract', '')}".lower()
    if any(word in text for word in ["gap", "limitation", "lack", "challenge", "not yet", "remain"]):
        return "current gap"
    if any(word in text for word in ["method", "model", "framework", "algorithm", "transformer"]):
        return "method background"
    if any(word in text for word in ["data", "dataset", "survey", "catalog", "multimodal"]):
        return "data background"
    return "background evidence"


def infer_evidence_summary(item: dict[str, Any]) -> str:
    fallback = f"{item.get('title', 'This source')} provides relevant context for the proposed study."
    return _first_sentence(str(item.get("abstract") or ""), fallback)


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if len(part.strip()) > 30]


def _pick_sentences(text: str, keywords: list[str], fallback: str, limit: int = 3) -> str:
    chosen = []
    for sentence in _sentences(text):
        lower = sentence.lower()
        if any(keyword in lower for keyword in keywords):
            chosen.append(sentence)
        if len(chosen) >= limit:
            break
    return " ".join(chosen) if chosen else fallback


def analyze_reference_item(item: dict[str, Any]) -> dict[str, str]:
    title = item.get("title") or "this paper"
    abstract = item.get("abstract") or item.get("pdf_text_excerpt") or ""
    return {
        "read_status": str(item.get("pdf_read_status") or "metadata_abstract_only"),
        "research_question": _pick_sentences(
            abstract,
            ["aim", "objective", "investigate", "classify", "detect", "identify", "transient"],
            f"The paper appears to address a topic related to {title}.",
            limit=2,
        ),
        "data_used": _pick_sentences(
            abstract,
            ["data", "dataset", "survey", "telescope", "light curve", "spectral", "observation", "sample"],
            "The available metadata does not state the dataset clearly; inspect the full paper before final manuscript claims.",
            limit=3,
        ),
        "methods": _pick_sentences(
            abstract,
            ["model", "method", "algorithm", "classification", "machine learning", "deep learning", "transformer", "cnn"],
            "The method family is not explicit in the available metadata.",
            limit=3,
        ),
        "scientific_results": _pick_sentences(
            abstract,
            ["result", "performance", "accuracy", "f1", "detect", "discover", "classified", "identified"],
            infer_evidence_summary(item),
            limit=3,
        ),
        "limitations": _pick_sentences(
            abstract,
            ["limitation", "limited", "future", "however", "challenge", "uncertain", "validation", "lack"],
            "No explicit limitation statement was identified in the available metadata.",
            limit=3,
        ),
        "relevance_to_study": _pick_sentences(
            abstract,
            ["x-ray", "transient", "einstein probe", "light curve", "spectral", "classification", "wxt", "fxt"],
            "Relevance should be judged from the title, abstract, citation weight, and method overlap.",
            limit=3,
        ),
        "pdf_excerpt": str(item.get("pdf_text_excerpt") or "")[:1200],
    }


def synthesize_cross_literature(items: list[dict[str, Any]]) -> dict[str, str]:
    summaries = [item.get("deep_summary") or {} for item in items]

    def join(key: str, fallback: str) -> str:
        text = " ".join(str(summary.get(key) or "") for summary in summaries)
        return re.sub(r"\s+", " ", text).strip()[:1800] or fallback

    return {
        "data_patterns": join("data_used", "No shared data pattern was extracted from the available metadata."),
        "method_patterns": join("methods", "No shared method pattern was extracted from the available metadata."),
        "limitation_patterns": join("limitations", "No shared limitation pattern was extracted from the available metadata."),
        "result_patterns": join("scientific_results", "No shared result pattern was extracted from the available metadata."),
    }


def citation_evidence_rows(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    context_order = {
        "idea": 0,
        "introduction": 0,
        "target_journal_anchor": 0,
        "data": 1,
        "methods": 2,
        "discussion": 3,
    }
    for item in items:
        contexts = item.get("search_contexts") or [item.get("search_context") or "idea"]
        # Retained references must remain usable during Discussion writing.  The
        # citation audit loop is intended to narrow claims and move citations, not
        # silently remove references because no section-specific evidence row was
        # generated for the final interpretive section.
        normalized_contexts = {str(context_value or "idea").lower() for context_value in contexts}
        normalized_contexts.add("discussion")
        ordered_contexts = sorted(normalized_contexts, key=lambda value: (context_order.get(value, 99), value))
        for context in ordered_contexts:
            section = {
                "idea": "introduction",
                "introduction": "introduction",
                "target_journal_anchor": "introduction",
                "discussion": "discussion",
                "data": "data",
                "methods": "methods",
            }.get(context, "introduction")
            citation_role = _citation_role(item, context)
            rows.append({
                "citation_key": item["bibtex_key"],
                "section": section,
                "claim": infer_claim(item),
                "evidence_summary": str(item.get("evidence_notes") or infer_evidence_summary(item)),
                "source": str(item.get("source") or "unknown"),
                "doi": str(item.get("doi") or ""),
                "url": str(item.get("url") or ""),
                "citation_role": citation_role,
                "data_citation_requirement": (
                    "precise_data_section_citation"
                    if citation_role in {"dataset_provenance", "instrument_product_definition", "processing_method_support"}
                    else "background_coverage_may_be_satisfied_in_introduction_or_discussion"
                ),
            })
    return rows


def _citation_role(item: dict[str, Any], context: str) -> str:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("title", "abstract", "evidence_notes", "publication")
    ).lower()
    normalized_context = str(context or "idea").lower()
    if normalized_context == "data":
        if any(token in text for token in ("dataset", "catalog", "survey data", "data release", "archive")):
            return "dataset_provenance"
        if any(token in text for token in ("instrument", "telescope", "mission", "detector", "data product")):
            return "instrument_product_definition"
        if any(token in text for token in ("calibration", "processing", "pipeline", "software", "reduction")):
            return "processing_method_support"
        return "data_context_background"
    if normalized_context == "methods":
        return "method_definition_or_precedent"
    if normalized_context == "discussion":
        return "result_comparison_or_interpretation"
    return "problem_gap_or_background"


def literature_review_notes(items: list[dict[str, Any]], query: str = "") -> str:
    lines = ["# Literature Review Notes", ""]
    if query:
        lines.extend([f"Search query: {query}", ""])
    synthesis = synthesize_cross_literature(items)
    lines.extend([
        "## Cross-Paper Synthesis",
        "",
        "### Data Patterns",
        synthesis["data_patterns"],
        "",
        "### Method Patterns",
        synthesis["method_patterns"],
        "",
        "### Result Patterns",
        synthesis["result_patterns"],
        "",
        "### Limitation Patterns",
        synthesis["limitation_patterns"],
        "",
        "## Ranked Paper Notes",
        "",
    ])
    for index, item in enumerate(items, start=1):
        authors = ", ".join(item.get("authors") or ["Unknown author"])
        summary = item.get("deep_summary") or {}
        recommended_section = {"idea": "introduction", "data": "data", "methods": "methods"}.get(
            str(item.get("search_context") or "idea"),
            "introduction",
        )
        lines.extend([
            f"## {index}. {item['title']}",
            "",
            f"- Citation key: `{item['bibtex_key']}`",
            f"- Source: {item.get('source') or 'unknown'}",
            f"- Reference origin: {item.get('reference_origin') or 'external_search'}",
            f"- Zotero collection: {item.get('zotero_collection') or 'n/a'}",
            f"- Selection policy: {item.get('selection_policy') or 'ranked_by_relevance_and_authority'}",
            f"- Search context: {', '.join(item.get('search_contexts') or [item.get('search_context') or 'idea'])}",
            f"- Search query: {'; '.join(item.get('search_queries') or [item.get('search_query') or query])}",
            f"- Recommended section: {recommended_section}",
            f"- Authors/year: {authors} ({item.get('year')})",
            f"- Venue: {item.get('publication') or 'n/a'}",
            f"- Citation weight: {item.get('citation_weight', 0)}",
            f"- Relevance score: {item.get('relevance_score', 0)}",
            f"- Authority score: {item.get('authority_score', 0)}",
            f"- Journal authority: {item.get('journal_score', 0)}",
            f"- Evidence role: {infer_claim(item)}",
            f"- Evidence summary: {item.get('evidence_notes') or infer_evidence_summary(item)}",
            f"- Data used: {summary.get('data_used', '')}",
            f"- Methods: {summary.get('methods', '')}",
            f"- Limitations: {summary.get('limitations', '')}",
            "",
        ])
    return "\n".join(lines)


def _safe_filename(text: str, fallback: str) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_").lower()
    return (name[:70].strip("_") or fallback)


def _reference_links_html(item: dict[str, Any]) -> str:
    links = []
    doi = str(item.get("doi") or "").strip()
    url = str(item.get("url") or "").strip()
    if doi:
        doi_url = doi if doi.lower().startswith(("http://", "https://")) else f"https://doi.org/{doi}"
        links.append(f'<a href="{escape(doi_url)}" target="_blank" rel="noopener">DOI: {escape(doi)}</a>')
    if url:
        links.append(f'<a href="{escape(url)}" target="_blank" rel="noopener">URL</a>')
    return " ".join(links) if links else "n/a"


def write_literature_html_summaries(references_dir: Path, items: list[dict[str, Any]]) -> list[str]:
    summary_dir = references_dir / "literature_summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    for old_summary in summary_dir.glob("*.html"):
        old_summary.unlink()
    output_files = []
    index_rows = []
    source_counts: Counter[str] = Counter()
    source_options: set[str] = set()
    code_by_work: dict[str, list[dict[str, Any]]] = {}
    code_sources_path = references_dir / "code_sources.json"
    if code_sources_path.is_file():
        try:
            code_payload = json.loads(code_sources_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            code_payload = {}
        for record in code_payload.get("records") or [] if isinstance(code_payload, dict) else []:
            if isinstance(record, dict) and record.get("work_id"):
                code_by_work.setdefault(str(record["work_id"]), []).append(record)

    def literature_work_id(item: dict[str, Any]) -> str:
        existing = str(item.get("work_id") or "").strip()
        if existing:
            return existing
        doi = str(item.get("doi") or "").strip().lower()
        return f"work:doi:{doi}" if doi else ""

    for index, item in enumerate(items, start=1):
        source_categories = _source_type_labels(item)
        code_leads = code_by_work.get(literature_work_id(item), [])
        for code_lead in code_leads:
            source_type = str(code_lead.get("source_type") or "code_source")
            source_categories.append(source_type)
        source_counts.update(source_categories)
        source_options.update(source_categories)
        code_source_summary = "; ".join(
            f"{record.get('source_type')}:{record.get('version') or record.get('record_id') or 'metadata-only'} ({record.get('selection_status') or 'candidate'})"
            for record in code_leads
        ) or "none"
        summary = item.get("deep_summary") or {}
        provenance_rows = []
        for entry in item.get("query_provenance") or []:
            if not isinstance(entry, dict):
                continue
            provenance_rows.append(
                "<tr>"
                f"<td>{escape(str(entry.get('query_id') or item.get('search_query_id') or 'n/a'))}</td>"
                f"<td>{escape(str(entry.get('context') or item.get('search_context') or 'idea'))}</td>"
                f"<td>{escape(str(entry.get('combination_level') or item.get('combination_level') or 'n/a'))}</td>"
                f"<td>{escape(str(entry.get('query') or ''))}</td>"
                "</tr>"
            )
        provenance_table = (
            "<table><tr><th>Query ID</th><th>Context</th><th>Combination level</th><th>Query</th></tr>"
            + "\n".join(provenance_rows)
            + "</table>"
            if provenance_rows
            else "<p>No structured query provenance was recorded for this item.</p>"
        )
        source_record_rows = []
        for record in item.get("source_records") or []:
            if not isinstance(record, dict):
                continue
            source_record_rows.append(
                "<tr>"
                f"<td>{escape(str(record.get('source_type') or 'unknown'))}</td>"
                f"<td>{escape(str(record.get('provider') or record.get('collection') or 'n/a'))}</td>"
                f"<td>{escape(str(record.get('logical_locator') or 'n/a'))}</td>"
                f"<td>{escape(str(record.get('file_id') or 'n/a'))}</td>"
                "</tr>"
            )
        source_records_table = (
            "<table><tr><th>Source type</th><th>Provider/collection</th><th>Logical locator</th><th>File ID</th></tr>"
            + "\n".join(source_record_rows)
            + "</table>"
            if source_record_rows
            else "<p>No source record was recorded.</p>"
        )
        field_provenance = json.dumps(item.get("field_provenance") or {}, ensure_ascii=False, sort_keys=True)
        parse_receipts = json.dumps(item.get("document_parses") or [], ensure_ascii=False, sort_keys=True)
        parse_route = "n/a"
        if item.get("document_parses") and isinstance(item.get("document_parses")[0], dict):
            parse_route = str(item.get("document_parses")[0].get("route") or item.get("document_parses")[0].get("parser") or "n/a")
        filename = f"{index:02d}_{_safe_filename(item.get('bibtex_key', ''), 'paper')}.html"
        relative = f"references/literature_summaries/{filename}"
        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(item.get('title') or 'Literature Summary')}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 980px; margin: 32px auto; line-height: 1.55; color: #202124; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    .score {{ font-weight: 600; }}
  </style>
</head>
<body>
  <h1>{escape(item.get('title') or 'Literature Summary')}</h1>
  <table>
    <tr><th>Citation key</th><td>{escape(item.get('bibtex_key') or '')}</td></tr>
    <tr><th>Source categories</th><td>{escape(', '.join(source_categories))}</td></tr>
    <tr><th>Reference origin</th><td>{escape(item.get('reference_origin') or 'external_search')}</td></tr>
    <tr><th>Zotero collection</th><td>{escape(item.get('zotero_collection') or 'n/a')}</td></tr>
    <tr><th>Local logical locator</th><td>{escape(item.get('local_logical_path') or 'n/a')}</td></tr>
    <tr><th>Local attachment</th><td>{escape(item.get('local_attachment_path') or 'n/a')}</td></tr>
    <tr><th>Local file ID</th><td>{escape(item.get('local_file_id') or 'n/a')}</td></tr>
    <tr><th>Metadata status</th><td>{escape(item.get('metadata_status') or 'unknown')}</td></tr>
    <tr><th>PDF/parser status</th><td>{escape(item.get('pdf_read_status') or 'not_parsed')} ({escape(item.get('local_parser_version') or item.get('local_parser') or 'n/a')})</td></tr>
    <tr><th>Parser route</th><td>{escape(parse_route)}</td></tr>
    <tr><th>Candidate state</th><td>{escape(item.get('candidate_state') or 'unknown')}</td></tr>
    <tr><th>GitHub/Zenodo code sources</th><td>{escape(code_source_summary)}</td></tr>
    <tr><th>Selection policy</th><td>{escape(item.get('selection_policy') or 'ranked_by_relevance_and_authority')}</td></tr>
    <tr><th>Authors/year</th><td>{escape(', '.join(item.get('authors') or ['Unknown author']))} ({escape(str(item.get('year') or 'n.d.'))})</td></tr>
    <tr><th>Venue</th><td>{escape(item.get('publication') or 'n/a')}</td></tr>
    <tr><th>Search context</th><td>{escape(', '.join(item.get('search_contexts') or [item.get('search_context') or 'idea']))}</td></tr>
    <tr><th>Search query</th><td>{escape('; '.join(item.get('search_queries') or [item.get('search_query') or '']))}</td></tr>
    <tr><th>Search query ID</th><td>{escape(item.get('search_query_id') or 'n/a')}</td></tr>
    <tr><th>Combination level</th><td>{escape(item.get('combination_level') or 'n/a')}</td></tr>
    <tr><th>Discipline anchor</th><td>{escape(item.get('discipline_anchor') or 'n/a')}</td></tr>
    <tr><th>Recommended section</th><td>{escape({'idea': 'introduction', 'data': 'data', 'methods': 'methods'}.get(str(item.get('search_context') or 'idea'), 'introduction'))}</td></tr>
    <tr><th>Citation weight</th><td class="score">{escape(str(item.get('citation_weight', 0)))}</td></tr>
    <tr><th>Relevance to Study</th><td>{escape(str(item.get('relevance_score', 0)))}</td></tr>
    <tr><th>Journal authority</th><td>{escape(str(item.get('journal_score', 0)))} {escape(', '.join(item.get('journal_rank_labels') or []))}</td></tr>
    <tr><th>Citation authority</th><td>{escape(str(item.get('citation_authority_score', 0)))}</td></tr>
    <tr><th>Topic / discipline / role evidence</th><td>{escape(str(item.get('topic_relevance_score', 0)))} / {escape(str(item.get('discipline_match_score', 0)))} / {escape(str(item.get('role_evidence_score', 0)))}</td></tr>
    <tr><th>DOI / URL</th><td>{_reference_links_html(item)}</td></tr>
  </table>
  <h2>Query provenance</h2>
  {provenance_table}
  <h2>Source records</h2>
  {source_records_table}
  <h2>Field provenance</h2>
  <pre>{escape(field_provenance)}</pre>
  <h2>Document parse receipts</h2>
  <pre>{escape(parse_receipts)}</pre>
  <h2>Abstract Summary</h2>
  <p>{escape(item.get('abstract') or 'No abstract metadata is available.')}</p>
  <h2>Structured Reading Notes</h2>
  <h3>Read Status</h3><p>{escape(summary.get('read_status') or '')}</p>
  <h3>Research Question</h3><p>{escape(summary.get('research_question') or '')}</p>
  <h3>Data Used</h3><p>{escape(summary.get('data_used') or '')}</p>
  <h3>Methods</h3><p>{escape(summary.get('methods') or '')}</p>
  <h3>Scientific Results</h3><p>{escape(summary.get('scientific_results') or '')}</p>
  <h3>Limitations</h3><p>{escape(summary.get('limitations') or '')}</p>
  <h3>Relevance to Study</h3><p>{escape(summary.get('relevance_to_study') or '')}</p>
  <h3>PDF Quick-Read Excerpt</h3><p>{escape(summary.get('pdf_excerpt') or 'No readable PDF excerpt was available.')}</p>
</body>
</html>
"""
        (summary_dir / filename).write_text(html, encoding="utf-8")
        output_files.append(relative)
        index_rows.append(
            f"<tr data-source-categories=\"{escape('|'.join(source_categories))}\"><td>{index}</td><td><a href=\"{escape(filename)}\">{escape(item.get('title') or '')}</a></td>"
            f"<td>{escape(item.get('bibtex_key') or '')}</td><td data-source-raw=\"{escape(item.get('source') or '')}\">{escape(', '.join(source_categories))}</td>"
            f"<td>{escape(item.get('reference_origin') or 'external_search')}</td>"
            f"<td>{escape(item.get('zotero_collection') or 'n/a')}</td>"
            f"<td>{escape(item.get('local_logical_path') or 'n/a')}</td>"
            f"<td>{escape(item.get('local_file_id') or 'n/a')}</td>"
            f"<td>{escape(item.get('metadata_status') or 'unknown')}</td>"
            f"<td>{escape(item.get('pdf_read_status') or 'not_parsed')}</td>"
            f"<td>{escape(parse_route)}</td>"
            f"<td>{escape(item.get('candidate_state') or 'unknown')}</td>"
            f"<td>{escape(code_source_summary)}</td>"
            f"<td>{escape(', '.join(item.get('search_contexts') or [item.get('search_context') or 'idea']))}</td>"
            f"<td>{escape('; '.join(item.get('search_queries') or [item.get('search_query') or '']))}</td>"
            f"<td>{escape(item.get('search_query_id') or 'n/a')}</td>"
            f"<td>{escape(item.get('combination_level') or 'n/a')}</td>"
            f"<td>{escape(item.get('selection_policy') or 'ranked_by_relevance_and_authority')}</td>"
            f"<td>{escape(str(item.get('citation_weight', 0)))}</td>"
            f"<td>{escape(str(item.get('relevance_score', 0)))}</td><td>{escape(str(item.get('journal_score', 0)))}</td></tr>"
        )
    source_summary = ", ".join(f"{escape(source)}: {count}" for source, count in sorted(source_counts.items())) or "none"
    source_options_html = "".join(f'<option value="{escape(source)}">{escape(source)}</option>' for source in sorted(source_options))
    index_html = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Literature Summary Index</title>
<script>
function filterSources() {{
  const selected = document.getElementById('source-filter').value;
  document.querySelectorAll('tbody tr[data-source-categories]').forEach((row) => {{
    const categories = (row.dataset.sourceCategories || '').split('|');
    row.style.display = !selected || categories.includes(selected) ? '' : 'none';
  }});
}}
</script>
</head>
<body>
<h1>Literature Summary Index</h1>
<p>Source counts: {source_summary}</p>
<label for="source-filter">Filter by source: </label>
<select id="source-filter" onchange="filterSources()"><option value="">all</option>{source_options_html}</select>
<table border="1" cellpadding="6" cellspacing="0">
<thead><tr><th>#</th><th>Title</th><th>Citation key</th><th>Source categories</th><th>Origin</th><th>Zotero collection</th><th>Local locator</th><th>File ID</th><th>Metadata</th><th>PDF/parser</th><th>Parser route</th><th>Candidate state</th><th>GitHub/Zenodo code sources</th><th>Context</th><th>Search query</th><th>Query ID</th><th>Combination</th><th>Retention</th><th>Citation weight</th><th>Relevance</th><th>Journal authority</th></tr></thead>
<tbody>
""" + "\n".join(index_rows) + "\n</tbody></table>\n</body>\n</html>\n"
    (summary_dir / "index.html").write_text(index_html, encoding="utf-8")
    return ["references/literature_summaries/index.html", *output_files]


def _write_citation_evidence(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["citation_key", "section", "claim", "evidence_summary", "source", "doi", "url", "citation_role", "data_citation_requirement"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _set_reference_manifest_outputs(project_path: Path) -> None:
    manifest_path = project_path / "references" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = ["idea/idea.md"]
    manifest["output_files"] = REFERENCE_OUTPUTS
    _write_json(manifest_path, manifest)


def write_reference_outputs(
    project: str | Path,
    items: list[dict[str, Any]],
    *,
    query: str = "",
    search_queries: dict[str, Any] | None = None,
    limit: int = MAX_REFERENCE_ITEMS,
) -> dict[str, Any]:
    """Write normalized references, BibTeX, citation evidence, and review notes."""
    state = load_project(project)
    references_dir = state.path / "references"
    references_dir.mkdir(parents=True, exist_ok=True)

    project_text = " ".join([state.metadata.get("idea", ""), state.metadata.get("field", ""), query])
    active_search_queries = search_queries or {"idea": query}
    candidates = list(items or [])
    rejected: list[dict[str, Any]] = []
    contract = active_search_queries.get("query_contract") if isinstance(active_search_queries, dict) else None
    if isinstance(contract, dict):
        from .literature_relevance import apply_relevance_gate

        candidates, rejected = apply_relevance_gate(candidates, contract)
    _write_json(references_dir / "literature_relevance_report.json", {
        "schema_version": "dpl.literature_relevance_report.v1",
        "contract_schema": contract.get("schema_version") if isinstance(contract, dict) else None,
        "candidate_count": len(candidates) + len(rejected),
        "accepted_count": len(candidates),
        "rejected_count": len(rejected),
        "accepted": [
            {
                "title": item.get("title", ""),
                "candidate_state": item.get("candidate_state", ""),
                "topic_relevance_score": item.get("topic_relevance_score", 0),
                "discipline_match_score": item.get("discipline_match_score", 0),
                "role_evidence_score": item.get("role_evidence_score", 0),
            }
            for item in candidates
        ],
    })
    normalized = select_references_by_context(
        candidates,
        project_text=project_text,
        target_journal=state.metadata.get("target_journal", ""),
        limit=max(0, int(limit)),
    )
    normalized = [enrich_pdf_text(item) for item in normalized]
    normalized = [item for item in normalized if has_readable_evidence(item) or _is_zotero_reference(item)]
    normalized = [{**item, "deep_summary": analyze_reference_item(item)} for item in normalized]
    _write_json(references_dir / "literature_items.json", normalized)
    (references_dir / "literature_candidates.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in candidates) + ("\n" if candidates else ""),
        encoding="utf-8",
    )
    _write_json(references_dir / "literature_rejection_report.json", {
        "schema_version": "dpl.literature_rejection_report.v1",
        "rejected_count": len(rejected),
        "rejections": rejected,
    })
    _write_json(references_dir / "search_queries.json", active_search_queries)
    source_registry = references_dir / "literature_source_registry.json"
    if not source_registry.exists():
        _write_json(source_registry, {"schema_version": "dpl.literature_source_registry.v1", "sources": [], "source_count": 0})
    zotero_manifest = references_dir / "zotero_collection_manifest.json"
    if not zotero_manifest.exists():
        _write_json(zotero_manifest, {"status": "not_used"})
    (references_dir / "library.bib").write_text(generate_bibtex(normalized), encoding="utf-8")
    _write_citation_evidence(references_dir / "citation_evidence.csv", citation_evidence_rows(normalized))
    review_notes = literature_review_notes(normalized, query=query)
    (references_dir / "literature_review_notes.md").write_text(review_notes, encoding="utf-8")
    write_html_report(references_dir / "literature_review_notes.html", review_notes, title="Literature Review Notes")
    html_outputs = write_literature_html_summaries(references_dir, normalized)

    from .literature_confirmation import build_literature_confirmation_packet

    build_literature_confirmation_packet(state.path)

    update_stage_status(state.path, "references", "draft")
    from .bibliography import build_reference_registry

    bibliography = build_reference_registry(state.path)
    _set_reference_manifest_outputs(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "item_count": len(normalized),
        "bibliography": bibliography,
        "outputs": REFERENCE_OUTPUTS + [item for item in html_outputs if item not in REFERENCE_OUTPUTS] + [
            "references/literature_candidates.jsonl",
            "references/literature_relevance_report.json",
            "references/literature_rejection_report.json",
        ],
    }
