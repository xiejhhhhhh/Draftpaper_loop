# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .paper_fetch_adapter import enrich_with_paper_fetch
from .project_state import load_project
from .references import domain_anchor_terms, domain_title_overlap, has_sufficient_metadata_or_pdf, normalize_reference_items, tokenize_for_relevance, write_reference_outputs
from .project_scaffold import _write_json
from .zotero_adapter import fetch_zotero_collection_items


def _read_text_if_exists(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def build_search_query(project: str | Path, query: str | None = None) -> str:
    if query:
        return query.strip()
    state = load_project(project)
    parts = [
        state.metadata.get("idea", ""),
        state.metadata.get("field", ""),
        state.metadata.get("target_journal", ""),
    ]
    return " ".join(part for part in parts if part).strip()


def _keywords_from_text(text: str, limit: int = 14) -> str:
    stopwords = {
        "using", "based", "with", "from", "data", "model", "models", "study", "research", "paper",
        "analysis", "method", "methods", "framework", "classification", "result", "results",
        "project", "target", "journal", "general", "academic",
        "file", "files", "count", "path", "raw", "description", "txt", "kind", "suffix", "size",
        "bytes", "readable", "null", "column", "columns", "row", "rows", "missing", "cells", "total", "cell",
    }
    tokens = []
    seen = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text or ""):
        lowered = token.lower()
        if lowered in stopwords or lowered in seen or len(lowered) > 36:
            continue
        tokens.append(token)
        seen.add(lowered)
        if len(tokens) >= limit:
            break
    return " ".join(tokens)


def _compact_query(text: str, limit: int = 220) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit].strip()


def _unique_queries(queries: list[str], limit: int = 5) -> list[str]:
    unique = []
    seen = set()
    for query in queries:
        compact = _compact_query(query)
        key = compact.lower()
        if not compact or key in seen:
            continue
        unique.append(compact)
        seen.add(key)
        if len(unique) >= limit:
            break
    return unique


def _unique_terms(terms: list[str], limit: int = 6) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for term in terms:
        compact = _compact_query(str(term or ""), limit=80)
        key = compact.lower()
        if not compact or key in seen:
            continue
        unique.append(compact)
        seen.add(key)
        if len(unique) >= limit:
            break
    return unique


def _split_semicolon_terms(text: str, limit: int = 5) -> list[str]:
    parts = re.split(r"[;；\n]+", text or "")
    return _unique_terms([part.strip(" -.") for part in parts if part.strip()], limit=limit)


def _idea_phrases(text: str, *, limit: int = 6) -> list[str]:
    raw = re.sub(r"[_/]+", " ", text or "")
    candidates: list[str] = []
    stopwords = {
        "the", "and", "for", "with", "using", "based", "study", "research", "framework",
        "test", "whether", "evaluate", "analysis", "approach", "method", "methods", "data",
    }
    for part in re.split(r",|;|:|\band\b|\busing\b|\bwith\b|\bfor\b|\bof\b|\bvia\b", raw, flags=re.IGNORECASE):
        words = [
            word
            for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{1,}", part)
            if word.lower() not in stopwords
        ]
        if 2 <= len(words) <= 5:
            candidates.append(" ".join(words))
        elif len(words) > 5:
            candidates.append(" ".join(words[:5]))
            candidates.append(" ".join(words[-4:]))
    keyword_tokens = _keywords_from_text(raw, limit=10).split()
    if len(keyword_tokens) >= 2:
        candidates.extend(
            " ".join(keyword_tokens[index:index + width])
            for width in (3, 2)
            for index in range(0, len(keyword_tokens) - width + 1, width)
        )
    return _unique_terms(candidates, limit=limit)


def _discipline_anchor(project_text: str, field: str) -> str:
    blob = f"{project_text} {field}".lower()
    declared = _keywords_from_text(field, limit=6)
    if declared:
        return declared
    broad_disciplines = [
        (("astronomy", "astrophysics", "galaxy", "stellar", "x-ray"), "astronomy astrophysics"),
        (("geography", "geospatial", "remote sensing", "climate", "crop"), "geography environmental science"),
        (("medical", "medicine", "clinical", "patient"), "medicine clinical research"),
        (("biology", "genomic", "transcriptomic", "protein"), "biology bioinformatics"),
        (("chemistry", "molecule", "compound"), "chemistry chemical informatics"),
        (("materials", "crystal", "alloy"), "materials science"),
        (("finance", "market", "asset pricing"), "finance empirical research"),
        (("machine learning", "deep learning", "neural network"), "machine learning applied research"),
    ]
    for markers, anchor in broad_disciplines:
        if any(marker in blob for marker in markers):
            return anchor
    return _domain_anchor(project_text, field, "")


def _query_entry(
    *,
    query_id: str,
    context: str,
    discipline: str,
    idea_terms: list[str],
    data_terms: list[str] | None = None,
    method_terms: list[str] | None = None,
    target_journal: str = "",
    combination_level: str,
) -> dict[str, Any]:
    components = {
        "discipline": [discipline] if discipline else [],
        "idea": idea_terms,
        "data": data_terms or [],
        "methods": method_terms or [],
        "target_journal": [target_journal] if target_journal else [],
    }
    query_parts = [discipline, *idea_terms, *(data_terms or []), *(method_terms or [])]
    if context == "target_journal_anchor" and target_journal:
        query_parts.append(target_journal)
    return {
        "query_id": query_id,
        "context": context,
        "discipline_anchor": discipline,
        "primary_terms": idea_terms,
        "secondary_terms": [*(data_terms or []), *(method_terms or [])],
        "combination_level": combination_level,
        "query": _compact_query(" ".join(part for part in query_parts if part), limit=240),
        "query_components": components,
    }


def _method_phrases(method_text: str) -> list[str]:
    phrases = []
    for raw_line in method_text.splitlines():
        line = raw_line.strip(" -;\t")
        if not line:
            continue
        lowered = line.lower()
        if line.startswith("#") or lowered.startswith((
            "research idea",
            "user-provided",
            "formal ",
            "title",
            "venue",
            "primary metric",
            "minimum acceptable",
            "current data",
            "the method can",
            "this paper",
            "the paper",
            "no explicit",
        )):
            continue
        phrase = re.split(r"[:：]", line, maxsplit=1)[0].strip()
        if phrase:
            phrases.append(phrase)
    return _unique_queries(phrases, limit=5)


def _topic_method_terms(idea: str, discipline: str) -> list[str]:
    blob = f"{idea} {discipline}".lower()
    terms: list[str] = []
    patterns = [
        ("dinov2", "DINOv2 self-supervised visual representation"),
        ("linear probe", "linear probing representation evaluation"),
        ("group-aware", "group-aware cross-validation"),
        ("spatial grouping", "spatial group held-out validation"),
        ("class imbalance", "class-imbalanced classification balanced accuracy"),
        ("confound", "confounder-controlled representation evaluation"),
        ("anomaly", "embedding anomaly detection uncertainty"),
        ("umap", "UMAP representation visualization"),
        ("transformer", "Transformer representation learning"),
        ("time-aware", "time-aware irregular time-series modeling"),
        ("light curve", "astronomical light-curve classification"),
        ("survival", "survival analysis validation"),
        ("rna", "differential expression analysis"),
    ]
    for marker, term in patterns:
        if marker in blob:
            terms.append(term)
    if not terms:
        terms.extend(["reproducible statistical analysis", "held-out validation and uncertainty"])
    return _unique_terms(terms, limit=5)


def _method_phrases_from_requirements(raw_json: str) -> list[str]:
    if not raw_json.strip():
        return []
    try:
        payload = json.loads(raw_json)
    except Exception:
        return []
    phrases: list[str] = []
    for family in payload.get("method_families") or []:
        phrases.append(str(family).replace("_", " "))
    user_method = str(payload.get("user_method") or "")
    if "source-held-out" in user_method.lower():
        phrases.append("source held-out validation")
    if "transformer" in user_method.lower():
        phrases.append("Transformer irregular time series")
    for feature in payload.get("required_data_features") or []:
        value = str(feature).replace("_", " ")
        if any(token in value.lower() for token in ["light", "spectral", "multi", "label"]):
            phrases.append(f"{value} classification")
    for item in payload.get("literature_methods") or []:
        title = str(item.get("title") or "")
        summary = str(item.get("method_summary") or "")
        blob = f"{title} {summary}".lower()
        if "time2vec" in blob:
            phrases.append("Time2Vec irregular observation time encoding")
        if "transformer" in blob and "light" in blob:
            phrases.append("light curve Transformer classification")
        if "ode" in blob and "irregular" in blob:
            phrases.append("neural ODE irregular time series")
        if "self-supervised" in blob:
            phrases.append("self-supervised light curve representation learning")
    return _unique_queries(phrases, limit=5)


def _objective_contract_terms(objective: Any, *, key: str, limit: int = 6) -> list[str]:
    """Return current human-revised contract terms without consulting stale plans."""
    if not isinstance(objective, dict):
        return []
    per_question: list[list[str]] = []
    for question in objective.get("primary_scientific_questions") or []:
        if not isinstance(question, dict):
            continue
        contract = question.get("figure_contract")
        if not isinstance(contract, dict):
            continue
        question_terms: list[str] = []
        for value in contract.get(key) or []:
            compact = str(value or "").replace("_", " ").strip()
            if compact:
                question_terms.append(compact)
        if key == "required_method":
            validation = str(contract.get("validation_metric") or "").replace("_", " ").strip()
            if validation:
                question_terms.append(validation)
        if question_terms:
            per_question.append(question_terms)
    terms: list[str] = []
    for offset in range(max((len(values) for values in per_question), default=0)):
        for values in per_question:
            if offset < len(values):
                terms.append(values[offset])
    return _unique_terms(terms, limit=limit)


def _data_terms(data_text: str) -> str:
    allowed = [
        "image cutout",
        "image classification label",
        "image embedding",
        "spectroscopy",
        "photometry",
        "redshift",
        "light curve",
        "spectral",
        "hardness ratio",
        "multi-band",
        "multiband",
        "catalog",
        "X-ray",
        "raster",
        "vector",
        "geospatial",
        "gene expression",
        "RNA sequencing",
        "clinical cohort",
        "survival outcome",
        "molecular descriptor",
        "crystal structure",
    ]
    found = []
    lowered = data_text.lower()
    for term in allowed:
        if term.lower() in lowered:
            found.append(term)
    return " ".join(found)


def _topic_data_terms(idea: str, discipline: str, extracted: str) -> list[str]:
    blob = f"{idea} {discipline} {extracted}".lower()
    terms = _unique_terms([extracted] if extracted else [], limit=5)
    candidates = [
        ("morphology", "galaxy morphology catalog labels"),
        ("image", "scientific image collection and quality metadata"),
        ("embedding", "precomputed representation matrix"),
        ("photometr", "multi-band photometry catalog"),
        ("spectro", "spectroscopic measurement catalog"),
        ("x-ray", "X-ray source catalog light curve spectral features"),
        ("light curve", "irregular light curve dataset"),
        ("rna", "gene expression count matrix and sample metadata"),
        ("clinical", "clinical cohort outcome table"),
        ("geograph", "geospatial raster vector observation dataset"),
        ("molecule", "molecular structure descriptor dataset"),
        ("material", "material composition structure property dataset"),
    ]
    for marker, term in candidates:
        if marker in blob:
            terms.append(term)
    if not terms:
        terms.append("dataset provenance sample construction missingness")
    return _unique_terms(terms, limit=5)


def _domain_anchor(project_text: str, field: str, target_journal: str) -> str:
    field_keywords = _keywords_from_text(field, limit=8)
    return _compact_query(field_keywords or _keywords_from_text(project_text, limit=8), limit=140)


def build_context_search_queries(project: str | Path, query: str | None = None) -> dict[str, Any]:
    state = load_project(project)
    idea_query = query or build_search_query(project)
    idea_terms = _idea_phrases(str(state.metadata.get("idea", "")), limit=5)
    if query:
        idea_terms = _unique_terms([*_idea_phrases(query, limit=3), *idea_terms], limit=5)
    if not idea_terms:
        idea_terms = _split_semicolon_terms(str(state.metadata.get("idea", "")), limit=3)
    field = str(state.metadata.get("field", ""))
    target_journal = str(state.metadata.get("target_journal", ""))
    discipline = _discipline_anchor(str(state.metadata.get("idea", "")), field)
    data_text = " ".join([
        _read_text_if_exists(state.path / "data" / "data_inventory.json"),
        _read_text_if_exists(state.path / "data" / "data_feasibility_report.json"),
        _read_text_if_exists(state.path / "idea" / "idea.md"),
    ])
    method_requirements_text = _read_text_if_exists(state.path / "methods" / "method_requirements.json", limit=12000)
    method_text = " ".join([
        _read_text_if_exists(state.path / "methods" / "method_plan.md"),
        method_requirements_text,
    ])
    objective = state.metadata.get("research_objective")
    objective_data_terms = _objective_contract_terms(objective, key="required_data")
    objective_method_terms = _objective_contract_terms(objective, key="required_method")
    data_terms = _data_terms(data_text)
    data_term_list = _unique_terms(
        [*objective_data_terms, *_topic_data_terms(str(state.metadata.get("idea", "")), discipline, data_terms)],
        limit=6,
    )
    if objective_method_terms:
        # A revised objective is authoritative while old method-plan files are stale.
        method_term_list = objective_method_terms
    else:
        method_term_list = (
            _method_phrases_from_requirements(method_requirements_text)
            or _method_phrases(method_text)
            or _topic_method_terms(str(state.metadata.get("idea", "")), discipline)
        )
    plan: list[dict[str, Any]] = []
    plan.append(_query_entry(
        query_id="all_idea_data_method_01",
        context="introduction",
        discipline=discipline,
        idea_terms=idea_terms[:2] or [idea_query],
        data_terms=data_term_list[:1],
        method_terms=method_term_list[:1],
        combination_level="all",
    ))
    plan.append(_query_entry(
        query_id="target_journal_anchor_01",
        context="target_journal_anchor",
        discipline=discipline,
        idea_terms=idea_terms[:2] or [idea_query],
        method_terms=method_term_list[:1],
        target_journal=target_journal,
        combination_level="all",
    ))
    for index, term in enumerate(data_term_list[:5], start=1):
        plan.append(_query_entry(
            query_id=f"data_pairwise_{index:02d}",
            context="data",
            discipline=discipline,
            idea_terms=idea_terms[:1] or [idea_query],
            data_terms=[term],
            combination_level="pairwise",
        ))
    for index, term in enumerate(method_term_list[:6], start=1):
        plan.append(_query_entry(
            query_id=f"methods_pairwise_{index:02d}",
            context="methods",
            discipline=discipline,
            idea_terms=idea_terms[:1] or [idea_query],
            method_terms=[term],
            combination_level="pairwise",
        ))
    plan.extend([
        _query_entry(
            query_id="introduction_single_idea_01",
            context="introduction",
            discipline=discipline,
            idea_terms=idea_terms[:2] or [idea_query],
            combination_level="single_fallback",
        ),
        _query_entry(
            query_id="data_single_01",
            context="data",
            discipline=discipline,
            idea_terms=[],
            data_terms=data_term_list[:1],
            combination_level="single_fallback",
        ),
        _query_entry(
            query_id="methods_single_01",
            context="methods",
            discipline=discipline,
            idea_terms=[],
            method_terms=method_term_list[:1],
            combination_level="single_fallback",
        ),
    ])
    data_queries = _unique_queries([entry["query"] for entry in plan if entry["context"] == "data"], limit=6)
    method_queries = _unique_queries([entry["query"] for entry in plan if entry["context"] == "methods"], limit=6)
    introduction_queries = _unique_queries([entry["query"] for entry in plan if entry["context"] == "introduction"], limit=4)
    return {
        "idea": introduction_queries[0] if introduction_queries else idea_query.strip(),
        "introduction": introduction_queries or [idea_query.strip()],
        "data": data_queries or [idea_query.strip()],
        "methods": method_queries or [idea_query.strip()],
        "target_journal_anchor": _unique_queries([entry["query"] for entry in plan if entry["context"] == "target_journal_anchor"], limit=2),
        "query_plan": plan,
    }


def _get_json(url: str, params: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 12) -> dict[str, Any]:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(full_url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def search_semantic_scholar(query: str, limit: int = 30) -> list[dict[str, Any]]:
    if not query:
        return []
    fields = ",".join([
        "title",
        "abstract",
        "year",
        "authors",
        "venue",
        "publicationVenue",
        "citationCount",
        "externalIds",
        "openAccessPdf",
        "url",
    ])
    headers = {}
    if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    payload = _get_json(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        {"query": query, "limit": min(limit, 100), "fields": fields},
        headers=headers,
    )

    items = []
    for paper in payload.get("data", []):
        external_ids = paper.get("externalIds") or {}
        publication_venue = paper.get("publicationVenue") or {}
        open_access_pdf = paper.get("openAccessPdf") or {}
        items.append({
            "title": paper.get("title", ""),
            "authors": [author.get("name", "") for author in paper.get("authors", []) if author.get("name")],
            "year": str(paper.get("year") or ""),
            "doi": external_ids.get("DOI", ""),
            "url": paper.get("url", ""),
            "abstract": paper.get("abstract") or "",
            "publication": publication_venue.get("name") or paper.get("venue", ""),
            "citation_count": paper.get("citationCount") or 0,
            "pdf_url": open_access_pdf.get("url", "") if isinstance(open_access_pdf, dict) else "",
            "source": "semantic_scholar",
        })
    return normalize_reference_items(items)


def _query_tokens(query: str, limit: int = 6) -> list[str]:
    stopwords = {"using", "based", "with", "from", "data", "model", "models", "study", "research"}
    tokens = []
    seen = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", query):
        lowered = token.lower()
        if lowered not in stopwords and lowered not in seen:
            tokens.append(token)
            seen.add(lowered)
        if len(tokens) >= limit:
            break
    return tokens


def search_arxiv(query: str, limit: int = 30) -> list[dict[str, Any]]:
    tokens = _query_tokens(query)
    if not tokens:
        return []
    params = urllib.parse.urlencode({
        "search_query": " AND ".join(f"all:{token}" for token in tokens[:5]),
        "start": 0,
        "max_results": min(limit, 20),
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    with urllib.request.urlopen(f"https://export.arxiv.org/api/query?{params}", timeout=12) as response:
        root = ET.fromstring(response.read().decode("utf-8"))

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("atom:entry", ns):
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        summary = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        url = entry.findtext("atom:id", default="", namespaces=ns) or ""
        authors = [
            (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
            for author in entry.findall("atom:author", ns)
        ]
        items.append({
            "title": title,
            "authors": [author for author in authors if author],
            "year": published[:4],
            "doi": "",
            "url": url,
            "abstract": summary,
            "publication": "arXiv",
            "citation_count": 0,
            "source": "arxiv",
        })
    return normalize_reference_items(items)


def search_crossref(query: str, limit: int = 30) -> list[dict[str, Any]]:
    if not query:
        return []
    payload = _get_json(
        "https://api.crossref.org/works",
        {
            "query.bibliographic": query,
            "rows": min(limit, 20),
            "select": "DOI,title,author,container-title,published-print,published-online,issued,URL,is-referenced-by-count,abstract,volume,issue,page,article-number,publisher",
        },
        headers={"User-Agent": "Draftpaper-loop local workflow (mailto:local@example.com)"},
    )

    items = []
    for work in (payload.get("message") or {}).get("items", []):
        title = " ".join((work.get("title") or [""])[0].split())
        authors = []
        for author in work.get("author") or []:
            name = " ".join([author.get("given", ""), author.get("family", "")]).strip()
            if name:
                authors.append(name)
        date_parts = (
            ((work.get("published-print") or {}).get("date-parts") or [[]])[0]
            or ((work.get("published-online") or {}).get("date-parts") or [[]])[0]
            or ((work.get("issued") or {}).get("date-parts") or [[]])[0]
        )
        abstract = re.sub(r"<[^>]+>", " ", work.get("abstract") or "")
        items.append({
            "title": title,
            "authors": authors,
            "year": str(date_parts[0]) if date_parts else "",
            "doi": work.get("DOI", ""),
            "url": work.get("URL", ""),
            "abstract": " ".join(abstract.split()),
            "publication": " ".join((work.get("container-title") or [""])[0].split()),
            "volume": str(work.get("volume") or ""),
            "issue": str(work.get("issue") or ""),
            "pages_or_article_number": str(work.get("page") or work.get("article-number") or ""),
            "publisher": str(work.get("publisher") or ""),
            "citation_count": work.get("is-referenced-by-count") or 0,
            "source": "crossref",
        })
    return normalize_reference_items(items)


def search_serpapi(query: str, limit: int = 30) -> list[dict[str, Any]]:
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key or not query:
        return []
    payload = _get_json(
        "https://serpapi.com/search.json",
        {"engine": "google_scholar", "q": query, "api_key": api_key, "num": min(limit, 20)},
    )
    items = []
    for index, paper in enumerate(payload.get("organic_results", [])[:limit]):
        publication_info = paper.get("publication_info") or {}
        year_match = re.search(r"(19|20)\d{2}", f"{publication_info.get('summary', '')} {paper.get('snippet', '')}")
        items.append({
            "title": paper.get("title", ""),
            "authors": [author.get("name", "") for author in publication_info.get("authors", []) if author.get("name")],
            "year": year_match.group(0) if year_match else "",
            "doi": "",
            "url": paper.get("link", ""),
            "abstract": paper.get("snippet", ""),
            "publication": publication_info.get("summary", ""),
            "citation_count": int((paper.get("inline_links") or {}).get("cited_by", {}).get("total", 0) or 0),
            "source": "google_scholar_serpapi",
        })
    return normalize_reference_items(items)


def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return normalize_reference_items(items)


class LiteratureSearchItems(list[dict[str, Any]]):
    """List-compatible search result carrying provider diagnostics."""

    def __init__(self, items: list[dict[str, Any]], provider_outcome: dict[str, Any]) -> None:
        super().__init__(items)
        self.provider_outcome = provider_outcome


def _provider_failure_status(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in {401, 403}:
            return "auth_required"
        if exc.code == 429:
            return "rate_limited"
    return "provider_error"


def _provider_search_outcome(
    provider_name: str,
    provider: Any,
    query: str,
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if provider_name == "serpapi" and not os.getenv("SERPAPI_API_KEY"):
        return [], {"provider": provider_name, "status": "auth_required", "item_count": 0, "reason_code": "api_key_missing"}
    try:
        items = list(provider(query, limit=limit))
    except Exception as exc:
        status = _provider_failure_status(exc)
        return [], {
            "provider": provider_name,
            "status": status,
            "item_count": 0,
            "reason_code": type(exc).__name__,
        }
    return items, {
        "provider": provider_name,
        "status": "success_with_items" if items else "success_empty",
        "item_count": len(items),
        "reason_code": None,
    }


def _aggregate_provider_status(provider_rows: list[dict[str, Any]], *, item_count: int) -> str:
    if item_count:
        return "success_with_items"
    statuses = {str(row.get("status") or "") for row in provider_rows}
    if "provider_error" in statuses:
        return "provider_error"
    if "rate_limited" in statuses:
        return "rate_limited"
    non_auth = statuses - {"auth_required", ""}
    if not non_auth and "auth_required" in statuses:
        return "auth_required"
    return "success_empty"


def search_free_literature_with_outcome(query: str, limit: int = 30) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    provider_rows: list[dict[str, Any]] = []
    provider_limit = min(30, max(6, limit * 3))
    providers = (
        ("semantic_scholar", search_semantic_scholar),
        ("arxiv", search_arxiv),
        ("crossref", search_crossref),
        ("serpapi", search_serpapi),
    )
    for provider_name, provider in providers:
        provider_items, provider_row = _provider_search_outcome(
            provider_name,
            provider,
            query,
            limit=provider_limit,
        )
        results.extend(provider_items)
        provider_rows.append(provider_row)
    results = dedupe_items(results)
    results.sort(
        key=lambda item: (
            _title_query_similarity(str(item.get("title") or ""), query),
            bool(item.get("doi")),
            bool(item.get("abstract")),
            int(item.get("citation_count") or 0),
        ),
        reverse=True,
    )
    results = results[:limit]
    return {
        "schema_version": "dpl.literature_provider_outcome.v1",
        "status": _aggregate_provider_status(provider_rows, item_count=len(results)),
        "query": query,
        "item_count": len(results),
        "items": results,
        "providers": provider_rows,
    }


def search_free_literature(query: str, limit: int = 30) -> list[dict[str, Any]]:
    outcome = search_free_literature_with_outcome(query, limit=limit)
    return LiteratureSearchItems(list(outcome["items"]), outcome)


def _query_provider_outcome(items: list[dict[str, Any]], *, query: str, context: str) -> dict[str, Any]:
    outcome = getattr(items, "provider_outcome", None)
    if isinstance(outcome, dict):
        row = {key: value for key, value in outcome.items() if key != "items"}
    else:
        row = {
            "schema_version": "dpl.literature_provider_outcome.v1",
            "status": "success_with_items" if items else "success_empty",
            "query": query,
            "item_count": len(items),
            "providers": [{"provider": "legacy_or_injected", "status": "success_with_items" if items else "success_empty", "item_count": len(items)}],
        }
    row["context"] = context
    return row


def _normalized_title(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _title_query_similarity(title: str, query: str) -> float:
    left = _normalized_title(title)
    right = _normalized_title(query)
    if not left or not right:
        return 0.0
    sequence = difflib.SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    coverage = len(left_tokens & right_tokens) / max(1, len(right_tokens))
    return max(sequence, coverage)


def _canonical_candidates(items: list[dict[str, Any]], identity: dict[str, Any]) -> list[dict[str, Any]]:
    expected_title = str(identity.get("expected_title") or "").strip()
    minimum = float(identity.get("minimum_title_similarity") or 0.86)
    accepted = []
    for item in items:
        similarity = _title_query_similarity(str(item.get("title") or ""), expected_title)
        if similarity < minimum:
            continue
        item["canonical_identity"] = {
            "expected_title": expected_title,
            "observed_title": str(item.get("title") or ""),
            "title_similarity": round(similarity, 4),
            "status": "verified",
        }
        accepted.append(item)
    accepted.sort(
        key=lambda item: float((item.get("canonical_identity") or {}).get("title_similarity") or 0),
        reverse=True,
    )
    return accepted[:1]


def _count_metadata_ready(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in normalize_reference_items(items) if has_sufficient_metadata_or_pdf(item))


def _fallback_query_plan(search_queries: dict[str, Any]) -> list[dict[str, Any]]:
    plan = search_queries.get("query_plan") if isinstance(search_queries.get("query_plan"), list) else []
    discipline = ""
    idea = ""
    data_terms: list[str] = []
    method_terms: list[str] = []
    for entry in plan:
        if not isinstance(entry, dict):
            continue
        discipline = discipline or str(entry.get("discipline_anchor") or "")
        components = entry.get("query_components") if isinstance(entry.get("query_components"), dict) else {}
        idea_terms = components.get("idea") if isinstance(components.get("idea"), list) else []
        if idea_terms and not idea:
            idea = str(idea_terms[0])
        for value in components.get("data") or []:
            if str(value) not in data_terms:
                data_terms.append(str(value))
        for value in components.get("methods") or []:
            if str(value) not in method_terms:
                method_terms.append(str(value))
    if not discipline:
        discipline = "scholarly research"
    candidates = [
        ("introduction_fallback_broad_01", "introduction", "single_fallback", f"{discipline} {idea}".strip()),
        ("data_fallback_broad_01", "data", "single_fallback", f"{discipline} {(data_terms or ['dataset provenance sample construction'])[0]}".strip()),
        ("methods_fallback_broad_01", "methods", "single_fallback", f"{discipline} {(method_terms or ['reproducible statistical analysis'])[0]}".strip()),
    ]
    if len(data_terms) > 1:
        candidates.append(("data_fallback_broad_02", "data", "single_fallback", f"{discipline} {data_terms[1]}".strip()))
    if len(method_terms) > 1:
        candidates.append(("methods_fallback_broad_02", "methods", "single_fallback", f"{discipline} {method_terms[1]}".strip()))
    if "high-energy" in discipline.lower() or "x-ray" in discipline.lower():
        candidates.extend([
            ("methods_fallback_astronomy_01", "methods", "single_fallback", "astronomical time series classification machine learning"),
            ("methods_fallback_astronomy_02", "methods", "single_fallback", "astronomical light curve transformer classification"),
            ("methods_fallback_astronomy_03", "methods", "single_fallback", "astronomical light curve foundation model time domain astronomy"),
            ("data_fallback_astronomy_01", "data", "single_fallback", "Einstein Probe WXT source classification"),
            ("data_fallback_astronomy_02", "data", "single_fallback", "X-ray transient source catalog light curve spectral feature"),
            ("introduction_fallback_astronomy_01", "introduction", "single_fallback", "high-energy transient astronomy machine learning classification"),
        ])
    return [
        {
            "query_id": query_id,
            "context": context,
            "combination_level": level,
            "discipline_anchor": discipline,
            "query": _compact_query(query, limit=220),
            "query_components": {"discipline": [discipline], "idea": [idea] if idea else [], "data": [], "methods": [], "target_journal": []},
        }
        for query_id, context, level, query in candidates
        if query.strip()
    ]


def _as_query_list(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


_LINEAGE_REFERENCE_PATH = "lineage/imported_sources/references/literature_items.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_verified_lineage_reference_seeds(project: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load topic-relevant parent references without activating parent workflow state."""
    state = load_project(project)
    lineage = state.metadata.get("lineage") if isinstance(state.metadata.get("lineage"), dict) else {}
    report: dict[str, Any] = {
        "status": "not_available",
        "source": _LINEAGE_REFERENCE_PATH,
        "candidate_count": 0,
        "accepted_count": 0,
        "rejected_count": 0,
    }
    parent_project_id = str(lineage.get("parent_project_id") or "").strip()
    if not parent_project_id:
        return [], report

    ledger_path = state.path / "lineage" / "import_ledger.json"
    source_path = state.path / Path(_LINEAGE_REFERENCE_PATH)
    if not ledger_path.is_file() or not source_path.is_file():
        report["status"] = "missing_verified_import"
        return [], report
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        report["status"] = "invalid_import_ledger"
        return [], report
    if (
        ledger.get("status") != "imported"
        or str(ledger.get("project_id") or "") != str(state.metadata.get("project_id") or "")
        or str(ledger.get("source_project_id") or "") != parent_project_id
    ):
        report["status"] = "lineage_mismatch"
        return [], report

    event = next(
        (
            entry
            for entry in (ledger.get("events") or [])
            if isinstance(entry, dict)
            and str(entry.get("target_path") or "").replace("\\", "/") == _LINEAGE_REFERENCE_PATH
            and entry.get("state") == "imported"
        ),
        None,
    )
    if not event or not event.get("sha256") or _sha256_file(source_path) != str(event.get("sha256")):
        report["status"] = "hash_verification_failed"
        return [], report
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        report["status"] = "invalid_reference_payload"
        return [], report
    candidates = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not isinstance(candidates, list):
        report["status"] = "invalid_reference_payload"
        return [], report

    project_text = " ".join(str(state.metadata.get(key) or "") for key in ("title", "idea", "field"))
    project_terms = tokenize_for_relevance(project_text)
    domain_terms = domain_anchor_terms(project_text)
    accepted: list[dict[str, Any]] = []
    rejected_titles: list[str] = []
    for item in candidates:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            continue
        evidence_text = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("abstract") or ""),
                str(item.get("evidence_notes") or ""),
                json.dumps(item.get("deep_summary") or {}, ensure_ascii=False),
            ]
        )
        overlap = sorted(project_terms & tokenize_for_relevance(evidence_text))
        domain_overlap = sorted(set(overlap) & domain_terms)
        title_domain_overlap = sorted(domain_title_overlap(str(item.get("title") or ""), domain_terms))
        prior_user_confirmed = bool(item.get("user_confirmed"))
        domain_supported = not domain_terms or (
            bool(domain_overlap) and (bool(title_domain_overlap) or len(domain_overlap) >= 2)
        )
        if not (prior_user_confirmed and overlap) and (len(overlap) < 2 or not domain_supported):
            rejected_titles.append(str(item.get("title") or ""))
            continue
        copied = dict(item)
        copied["lineage_previous_origin"] = str(item.get("reference_origin") or item.get("source") or "unknown")
        copied["reference_origin"] = "parent_lineage_curated"
        copied["selection_policy"] = "parent_lineage_topic_revalidated"
        copied["lineage_source_project_id"] = parent_project_id
        copied["lineage_asset_id"] = str(event.get("asset_id") or "")
        copied["lineage_topic_overlap"] = overlap
        copied["lineage_domain_overlap"] = domain_overlap
        copied["lineage_title_domain_overlap"] = title_domain_overlap
        copied["lineage_requires_current_citation_audit"] = True
        copied["_lineage_runtime_verified"] = True
        copied["prior_user_confirmed"] = prior_user_confirmed
        copied["user_confirmed"] = False
        accepted.append(copied)

    report.update(
        {
            "status": "loaded",
            "candidate_count": len(candidates),
            "accepted_count": len(accepted),
            "rejected_count": len(candidates) - len(accepted),
            "rejected_titles": rejected_titles,
            "source_project_id": parent_project_id,
            "asset_id": str(event.get("asset_id") or ""),
            "sha256": str(event.get("sha256") or ""),
            "selection_policy": "domain_anchor_plus_two_topic_terms_or_prior_confirmation_plus_one_topic_term",
        }
    )
    return accepted, report


def search_literature_for_project(
    project: str | Path,
    *,
    query: str | None = None,
    limit: int = 30,
    from_json: str | Path | None = None,
    zotero_collection: str | None = None,
    zotero_context: str = "idea",
    zotero_min_items: int = 20,
    zotero_supplement: bool = True,
) -> dict[str, Any]:
    final_query = build_search_query(project, query)
    search_queries = build_context_search_queries(project, query)
    state = load_project(project)
    zotero_manifest: dict[str, Any] | None = None
    provider_queries: list[dict[str, Any]] = []
    if from_json and zotero_collection:
        raise ValueError("Use either --from-json or --zotero-collection, not both.")
    if zotero_collection:
        items, zotero_manifest = fetch_zotero_collection_items(
            zotero_collection,
            limit=max(limit, zotero_min_items),
            context=zotero_context,
        )
        search_queries["zotero_collection"] = zotero_manifest.get("matched_collection") or zotero_collection
        search_queries["zotero_context"] = zotero_context
        minimum = max(0, min(zotero_min_items, limit))
        if zotero_supplement and len(items) < minimum:
            needed = minimum - len(items)
            supplemental = search_free_literature(final_query, limit=max(needed * 2, needed))
            provider_queries.append(_query_provider_outcome(supplemental, query=final_query, context="zotero_supplement"))
            existing_keys = {
                (str(item.get("doi") or "") or re.sub(r"[^a-z0-9]+", " ", str(item.get("title") or "").lower()).strip()).lower()
                for item in items
            }
            added = []
            for item in supplemental:
                key = (str(item.get("doi") or "") or re.sub(r"[^a-z0-9]+", " ", str(item.get("title") or "").lower()).strip()).lower()
                if key in existing_keys:
                    continue
                item["reference_origin"] = "supplemental_external"
                item["search_context"] = "idea"
                item["search_query"] = final_query
                added.append(item)
                existing_keys.add(key)
                if len(added) >= needed:
                    break
            items.extend(added)
            zotero_manifest["supplemental_item_count"] = len(added)
            zotero_manifest["supplemental_query"] = final_query
        else:
            zotero_manifest["supplemental_item_count"] = 0
    elif from_json:
        payload = json.loads(Path(from_json).read_text(encoding="utf-8-sig"))
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        if isinstance(payload, dict) and isinstance(payload.get("search_queries"), dict):
            search_queries.update({str(key): value for key, value in payload["search_queries"].items()})
    else:
        items = []
        query_plan = search_queries.get("query_plan") if isinstance(search_queries.get("query_plan"), list) else []
        if query_plan:
            iterable_queries = [
                (
                    str(entry.get("context") or "introduction"),
                    str(entry.get("query") or ""),
                    entry,
                )
                for entry in query_plan
                if str(entry.get("query") or "").strip()
            ]
        else:
            iterable_queries = []
            for context, context_query_value in search_queries.items():
                if context == "query_plan":
                    continue
                for context_query in _as_query_list(context_query_value):
                    iterable_queries.append((context, context_query, {}))
        canonical_resolution: list[dict[str, Any]] = []
        for context, context_query, plan_entry in iterable_queries:
                combination_level = str(plan_entry.get("combination_level") or "")
                per_query_limit = min(limit, 2) if context in {"data", "methods"} or combination_level == "all" else min(limit, 6)
                if isinstance(plan_entry.get("canonical_identity"), dict):
                    per_query_limit = min(limit, 8)
                if context == "target_journal_anchor":
                    per_query_limit = min(limit, 2)
                context_items = search_free_literature(context_query, limit=per_query_limit)
                provider_queries.append(_query_provider_outcome(context_items, query=context_query, context=context))
                identity = plan_entry.get("canonical_identity") if isinstance(plan_entry.get("canonical_identity"), dict) else {}
                if identity:
                    context_items = _canonical_candidates(context_items, identity)
                    canonical_resolution.append({
                        "query_id": plan_entry.get("query_id"),
                        "expected_title": identity.get("expected_title"),
                        "status": "resolved" if context_items else "unresolved",
                        "matched_title": context_items[0].get("title") if context_items else None,
                    })
                for item in context_items:
                    item["search_context"] = context
                    item["search_query"] = context_query
                    if plan_entry:
                        item["search_query_id"] = plan_entry.get("query_id")
                        item["combination_level"] = plan_entry.get("combination_level")
                        item["discipline_anchor"] = plan_entry.get("discipline_anchor")
                        item["query_components"] = plan_entry.get("query_components")
                        item["query_provenance"] = [{
                            "query_id": plan_entry.get("query_id"),
                            "context": context,
                            "combination_level": plan_entry.get("combination_level"),
                            "query": context_query,
                            "query_components": plan_entry.get("query_components"),
                        }]
                items.extend(context_items)
        if canonical_resolution:
            search_queries["canonical_resolution"] = canonical_resolution
        if _count_metadata_ready(items) < min(12, limit):
            fallback_entries = _fallback_query_plan(search_queries)
            existing_queries = {str(entry[1]).strip().lower() for entry in iterable_queries}
            for plan_entry in fallback_entries:
                context_query = str(plan_entry.get("query") or "")
                if not context_query or context_query.lower() in existing_queries:
                    continue
                context = str(plan_entry.get("context") or "introduction")
                fallback_limit = min(limit, 2) if context in {"data", "methods"} else min(limit, 6)
                context_items = search_free_literature(context_query, limit=fallback_limit)
                provider_queries.append(_query_provider_outcome(context_items, query=context_query, context=f"{context}_fallback"))
                for item in context_items:
                    item["search_context"] = context
                    item["search_query"] = context_query
                    item["search_query_id"] = plan_entry.get("query_id")
                    item["combination_level"] = plan_entry.get("combination_level")
                    item["discipline_anchor"] = plan_entry.get("discipline_anchor")
                    item["query_components"] = plan_entry.get("query_components")
                    item["query_provenance"] = [{
                        "query_id": plan_entry.get("query_id"),
                        "context": context,
                        "combination_level": plan_entry.get("combination_level"),
                        "query": context_query,
                        "query_components": plan_entry.get("query_components"),
                    }]
                items.extend(context_items)
                existing_queries.add(context_query.lower())
                if _count_metadata_ready(items) >= min(12, limit):
                    break
            if fallback_entries:
                search_queries["fallback_query_plan"] = fallback_entries
        items, _manifest = enrich_with_paper_fetch(project, items)
    external_item_count = len(items or [])
    lineage_seeds, lineage_report = _load_verified_lineage_reference_seeds(project)
    if lineage_seeds:
        items = [*lineage_seeds, *list(items or [])]
    search_queries["lineage_reference_seeds"] = lineage_report
    result = write_reference_outputs(project, list(items or []), query=final_query, search_queries=search_queries)
    if from_json:
        provider_status = "offline_fallback"
        source_mode = "local_json"
    elif zotero_collection:
        provider_status = "success_with_items" if external_item_count else "success_empty"
        source_mode = "zotero_collection"
    elif external_item_count:
        provider_status = "success_with_items"
        source_mode = "live_providers"
    elif lineage_seeds:
        provider_status = "offline_fallback"
        source_mode = "verified_lineage"
    else:
        provider_status = _aggregate_provider_status(provider_queries, item_count=0)
        source_mode = "live_providers"
    provider_report = {
        "schema_version": "dpl.literature_provider_report.v1",
        "status": provider_status,
        "source_mode": source_mode,
        "query_count": len(provider_queries),
        "external_item_count": external_item_count,
        "lineage_item_count": len(lineage_seeds),
        "final_item_count": int(result.get("item_count") or 0),
        "queries": provider_queries,
    }
    provider_report_path = state.path / "references" / "literature_provider_report.json"
    _write_json(provider_report_path, provider_report)
    stage_manifest_path = state.path / "references" / "stage_manifest.json"
    stage_manifest = json.loads(stage_manifest_path.read_text(encoding="utf-8"))
    stage_manifest["provider_status"] = provider_status
    stage_manifest["provider_report"] = "references/literature_provider_report.json"
    stage_manifest["output_files"] = list(dict.fromkeys([
        *(stage_manifest.get("output_files") or []),
        "references/literature_provider_report.json",
    ]))
    _write_json(stage_manifest_path, stage_manifest)
    manifest_path = state.path / "references" / "zotero_collection_manifest.json"
    if zotero_manifest is None:
        zotero_manifest = {"status": "not_used"}
    _write_json(manifest_path, zotero_manifest)
    if zotero_manifest.get("status") == "loaded":
        result["zotero_collection_manifest"] = str(manifest_path)
        result["zotero_imported_count"] = zotero_manifest.get("usable_item_count", 0)
        result["zotero_supplemental_count"] = zotero_manifest.get("supplemental_item_count", 0)
    result["provider_status"] = provider_status
    result["literature_provider_report"] = str(provider_report_path)
    return result
