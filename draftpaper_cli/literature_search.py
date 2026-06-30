# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .paper_fetch_adapter import enrich_with_paper_fetch
from .project_state import load_project
from .references import has_sufficient_metadata_or_pdf, normalize_reference_items, write_reference_outputs
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


def _discipline_anchor(project_text: str, field: str) -> str:
    blob = f"{project_text} {field}".lower()
    if any(term in blob for term in ["x-ray", "astronomy", "transient", "wxt", "flare", "light curve"]):
        return "high-energy time-domain astronomy X-ray transient"
    if any(term in blob for term in ["ndvi", "remote sensing", "geography", "climate", "crop", "yield"]):
        return "geography remote sensing environmental analysis"
    if any(term in blob for term in ["medical", "clinical", "patient", "cohort"]):
        return "medicine clinical research"
    if any(term in blob for term in ["biology", "genomic", "rna", "protein"]):
        return "biology bioinformatics"
    if any(term in blob for term in ["finance", "market", "stock", "return"]):
        return "finance empirical asset pricing"
    if "machine learning" in blob:
        return "machine learning applied research"
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
    fallback = [
        "1D CNN ResNet",
        "Transformer irregular time series",
        "Temporal Convolutional Network",
        "multimodal network",
        "contrastive learning self-supervised pretraining",
    ]
    return _unique_queries(phrases + fallback, limit=5)


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


def _data_terms(data_text: str) -> str:
    allowed = [
        "light curve",
        "spectral",
        "hardness ratio",
        "multi-band",
        "multiband",
        "catalog",
        "WXT",
        "FXT",
        "Einstein Probe",
        "X-ray",
    ]
    found = []
    lowered = data_text.lower()
    for term in allowed:
        if term.lower() in lowered:
            found.append(term)
    return " ".join(found)


def _domain_anchor(project_text: str, field: str, target_journal: str) -> str:
    field_keywords = _keywords_from_text(field, limit=8)
    return _compact_query(field_keywords or _keywords_from_text(project_text, limit=8), limit=140)


def build_context_search_queries(project: str | Path, query: str | None = None) -> dict[str, str | list[str]]:
    state = load_project(project)
    idea_query = query or build_search_query(project)
    idea_terms = _split_semicolon_terms(str(state.metadata.get("idea", "")), limit=3)
    if query:
        idea_terms = _unique_terms([query, *idea_terms], limit=4)
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
    data_terms = _data_terms(data_text)
    data_term_list = _unique_terms([
        data_terms,
        "light curve dataset catalog",
        "spectral features hardness ratio dataset",
        "multi-band counterpart catalog source classification",
        "WXT FXT observation data release",
        "X-ray transient sample construction",
    ], limit=5)
    method_term_list = _method_phrases_from_requirements(method_requirements_text) or _method_phrases(method_text)
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
    for index, term in enumerate(method_term_list[:5], start=1):
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
    try:
        payload = _get_json(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            {"query": query, "limit": min(limit, 100), "fields": fields},
            headers=headers,
        )
    except Exception:
        return []

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
    try:
        with urllib.request.urlopen(f"https://export.arxiv.org/api/query?{params}", timeout=12) as response:
            root = ET.fromstring(response.read().decode("utf-8"))
    except Exception:
        return []

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
    try:
        payload = _get_json(
            "https://api.crossref.org/works",
            {
                "query.bibliographic": query,
                "rows": min(limit, 20),
                "select": "DOI,title,author,container-title,published-print,published-online,issued,URL,is-referenced-by-count,abstract",
            },
            headers={"User-Agent": "Draftpaper-loop local workflow (mailto:local@example.com)"},
        )
    except Exception:
        return []

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
            "citation_count": work.get("is-referenced-by-count") or 0,
            "source": "crossref",
        })
    return normalize_reference_items(items)


def search_serpapi(query: str, limit: int = 30) -> list[dict[str, Any]]:
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key or not query:
        return []
    try:
        payload = _get_json(
            "https://serpapi.com/search.json",
            {"engine": "google_scholar", "q": query, "api_key": api_key, "num": min(limit, 20)},
        )
    except Exception:
        return []
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


def search_free_literature(query: str, limit: int = 30) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for provider in (search_semantic_scholar, search_arxiv, search_crossref, search_serpapi):
        results.extend(provider(query, limit=limit))
        results = dedupe_items(results)
    return results[:limit]


def _count_metadata_ready(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in normalize_reference_items(items) if has_sufficient_metadata_or_pdf(item))


def _fallback_query_plan(search_queries: dict[str, Any]) -> list[dict[str, Any]]:
    plan = search_queries.get("query_plan") if isinstance(search_queries.get("query_plan"), list) else []
    discipline = ""
    idea = ""
    for entry in plan:
        if not isinstance(entry, dict):
            continue
        discipline = discipline or str(entry.get("discipline_anchor") or "")
        components = entry.get("query_components") if isinstance(entry.get("query_components"), dict) else {}
        idea_terms = components.get("idea") if isinstance(components.get("idea"), list) else []
        if idea_terms and not idea:
            idea = str(idea_terms[0])
    if not discipline:
        discipline = "scholarly research"
    candidates = [
        ("introduction_fallback_broad_01", "introduction", "single_fallback", f"{discipline} {idea}".strip()),
        ("data_fallback_broad_01", "data", "single_fallback", f"{discipline} survey catalog dataset observation sample".strip()),
        ("methods_fallback_broad_01", "methods", "single_fallback", f"{discipline} machine learning classification time series validation".strip()),
        ("methods_fallback_broad_02", "methods", "single_fallback", f"{discipline} transformer irregular time series classification".strip()),
        ("data_fallback_broad_02", "data", "single_fallback", f"{discipline} light curve spectral feature source catalog".strip()),
    ]
    if "astronomy" in discipline.lower() or "x-ray" in discipline.lower():
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
        for context, context_query, plan_entry in iterable_queries:
                combination_level = str(plan_entry.get("combination_level") or "")
                per_query_limit = min(limit, 2) if context in {"data", "methods"} or combination_level == "all" else min(limit, 6)
                if context == "target_journal_anchor":
                    per_query_limit = min(limit, 2)
                context_items = search_free_literature(context_query, limit=per_query_limit)
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
    result = write_reference_outputs(project, list(items or []), query=final_query, search_queries=search_queries)
    manifest_path = state.path / "references" / "zotero_collection_manifest.json"
    if zotero_manifest is None:
        zotero_manifest = {"status": "not_used"}
    _write_json(manifest_path, zotero_manifest)
    if zotero_manifest.get("status") == "loaded":
        result["zotero_collection_manifest"] = str(manifest_path)
        result["zotero_imported_count"] = zotero_manifest.get("usable_item_count", 0)
        result["zotero_supplemental_count"] = zotero_manifest.get("supplemental_item_count", 0)
    return result
