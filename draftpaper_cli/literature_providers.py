"""Optional cross-discipline literature provider router.

The router deliberately returns ordinary reference dictionaries so the existing
normalization and evidence gates remain the single source of truth.  Providers
are best-effort discovery inputs; a missing credential, timeout, or malformed
response is recorded as degraded rather than treated as evidence.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Callable

from .literature_provider_planner import PROVIDER_PROFILES, plan_provider_ids


PROVIDER_MANIFEST: tuple[dict[str, Any], ...] = (
    {"id": "openalex", "disciplines": ["general", "social_science", "economics", "humanities", "geography", "law", "materials_science"], "languages": ["zh-CN", "en"], "roles": PROVIDER_PROFILES["openalex"]["roles"], "identifier_types": ["doi", "openalex_id"], "credential": None, "default_enabled": True},
    {"id": "pubmed", "disciplines": ["medicine", "life_science", "bioinformatics"], "languages": ["en"], "roles": PROVIDER_PROFILES["pubmed"]["roles"], "identifier_types": ["pmid", "doi"], "credential": None, "default_enabled": False},
    {"id": "europe_pmc", "disciplines": ["medicine", "life_science", "bioinformatics"], "languages": ["en"], "roles": PROVIDER_PROFILES["europe_pmc"]["roles"], "identifier_types": ["pmid", "pmcid", "doi"], "credential": None, "default_enabled": False},
    {"id": "dblp", "disciplines": ["computer_science", "machine_learning"], "languages": ["en"], "roles": PROVIDER_PROFILES["dblp"]["roles"], "identifier_types": ["dblp_key", "doi"], "credential": None, "default_enabled": False},
    {"id": "nasa_ads", "disciplines": ["astronomy", "astrophysics", "physics"], "languages": ["en"], "roles": PROVIDER_PROFILES["nasa_ads"]["roles"], "identifier_types": ["bibcode", "doi", "arxiv"], "credential": "NASA_ADS_API_TOKEN", "default_enabled": False},
)


def provider_status_report() -> dict[str, Any]:
    providers = []
    for manifest in PROVIDER_MANIFEST:
        credential = manifest.get("credential")
        configured = True if not credential else bool(os.getenv(str(credential), "").strip())
        providers.append({**manifest, "configured": configured, "status": "ready" if configured else "credential_missing"})
    return {"schema_version": "dpl.literature_provider_router.v1", "providers": providers}


def _get_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 8) -> Any:
    query = f"?{urllib.parse.urlencode(params or {})}" if params else ""
    request = urllib.request.Request(
        f"{url}{query}",
        headers={"User-Agent": "Draftpaper-loop literature provider router", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _abstract_from_inverted_index(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    words: list[tuple[int, str]] = []
    for token, positions in index.items():
        for position in positions or []:
            try:
                words.append((int(position), str(token)))
            except (TypeError, ValueError):
                continue
    return " ".join(token for _, token in sorted(words))


def _openalex(query: str, limit: int) -> list[dict[str, Any]]:
    payload = _get_json(
        "https://api.openalex.org/works",
        params={"search": query, "per-page": min(limit, 25), "mailto": os.getenv("OPENALEX_MAILTO", "")},
    )
    results = []
    for work in (payload or {}).get("results", []) if isinstance(payload, dict) else []:
        primary = work.get("primary_location") or {}
        source = primary.get("source") or {}
        authors = [str((auth.get("author") or {}).get("display_name") or "") for auth in work.get("authorships", [])]
        results.append(
            {
                "title": work.get("title", ""),
                "authors": [author for author in authors if author],
                "year": work.get("publication_year", ""),
                "doi": str(work.get("doi") or "").removeprefix("https://doi.org/"),
                "url": str(primary.get("landing_page_url") or work.get("id") or ""),
                "pdf_url": str((primary.get("pdf") or {}).get("url") or ""),
                "abstract": _abstract_from_inverted_index(work.get("abstract_inverted_index")),
                "publication": str(source.get("display_name") or ""),
                "citation_count": int(work.get("cited_by_count") or 0),
                "source": "openalex",
                "source_type": "online_search",
                "source_provider": "openalex",
            }
        )
    return results


def _pubmed(query: str, limit: int) -> list[dict[str, Any]]:
    search = _get_json(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={"db": "pubmed", "term": query, "retmode": "json", "retmax": min(limit, 20)},
    )
    ids = ((search or {}).get("esearchresult") or {}).get("idlist") if isinstance(search, dict) else []
    if not ids:
        return []
    summary = _get_json(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
    )
    records = (summary or {}).get("result") if isinstance(summary, dict) else {}
    results = []
    for pmid in ids:
        data = records.get(str(pmid), {}) if isinstance(records, dict) else {}
        if not isinstance(data, dict) or not data.get("title"):
            continue
        authors = [str(author.get("name") or "") for author in data.get("authors", []) if isinstance(author, dict)]
        results.append(
            {
                "title": data.get("title", ""),
                "authors": [author for author in authors if author],
                "year": str(data.get("pubdate") or ""),
                "doi": next((str(item.get("value") or "") for item in data.get("articleids", []) if item.get("idtype") == "doi"), ""),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "publication": str(data.get("fulljournalname") or data.get("source") or ""),
                "citation_count": 0,
                "source": "pubmed",
                "source_type": "online_search",
                "source_provider": "pubmed",
                "pmid": str(pmid),
            }
        )
    return results


def _europe_pmc(query: str, limit: int) -> list[dict[str, Any]]:
    payload = _get_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params={"query": query, "format": "json", "pageSize": min(limit, 25), "resultType": "core"},
    )
    results = []
    for record in (payload or {}).get("resultList", {}).get("result", []) if isinstance(payload, dict) else []:
        authors = []
        author_list = (record.get("authorList") or {}).get("author", [])
        for author in author_list:
            if isinstance(author, dict):
                authors.append(str(author.get("fullName") or author.get("lastName") or ""))
        results.append(
            {
                "title": record.get("title", ""),
                "authors": [author for author in authors if author],
                "year": record.get("pubYear", ""),
                "doi": str(record.get("doi") or ""),
                "url": f"https://europepmc.org/article/{record.get('source') or 'MED'}/{record.get('id')}" if record.get("id") else "",
                "abstract": str(record.get("abstractText") or ""),
                "publication": str(record.get("journalTitle") or ""),
                "citation_count": int(record.get("citedByCount") or 0),
                "source": "europe_pmc",
                "source_type": "online_search",
                "source_provider": "europe_pmc",
                "pmid": str(record.get("pmid") or ""),
                "pmcid": str(record.get("pmcid") or ""),
            }
        )
    return results


def _dblp(query: str, limit: int) -> list[dict[str, Any]]:
    payload = _get_json("https://dblp.org/search/publ/api", params={"q": query, "format": "json", "h": min(limit, 20)})
    hits = (((payload or {}).get("result") or {}).get("hits") or {}).get("hit", []) if isinstance(payload, dict) else []
    results = []
    for hit in hits:
        info = hit.get("info") if isinstance(hit, dict) else {}
        if not isinstance(info, dict) or not info.get("title"):
            continue
        authors = [str(author.get("text") or "") for author in (info.get("authors") or {}).get("author", [])] if isinstance(info.get("authors"), dict) else []
        results.append(
            {
                "title": str(info.get("title") or "").rstrip("."),
                "authors": [author for author in authors if author],
                "year": str(info.get("year") or ""),
                "doi": str(info.get("doi") or ""),
                "url": str(info.get("ee") or info.get("url") or ""),
                "publication": str(info.get("venue") or ""),
                "citation_count": 0,
                "source": "dblp",
                "source_type": "online_search",
                "source_provider": "dblp",
            }
        )
    return results


def _nasa_ads(query: str, limit: int) -> list[dict[str, Any]]:
    token = os.getenv("NASA_ADS_API_TOKEN", "").strip()
    if not token:
        return []
    payload = _get_json(
        "https://api.adsabs.harvard.edu/v1/search/query",
        params={"q": query, "fl": "bibcode,title,author,year,doi,abstract,pub,citation_count,property", "rows": min(limit, 20)},
        headers={"Authorization": f"Bearer {token}"},
    )
    results = []
    for record in ((payload or {}).get("response") or {}).get("docs", []) if isinstance(payload, dict) else []:
        dois = record.get("doi") or []
        if isinstance(dois, str):
            dois = [dois]
        results.append(
            {
                "title": " ".join(record.get("title") or []),
                "authors": record.get("author") or [],
                "year": record.get("year") or "",
                "doi": dois[0] if dois else "",
                "url": f"https://ui.adsabs.harvard.edu/abs/{record.get('bibcode')}/abstract" if record.get("bibcode") else "",
                "abstract": record.get("abstract") or "",
                "publication": record.get("pub") or "",
                "citation_count": int(record.get("citation_count") or 0),
                "source": "nasa_ads",
                "source_type": "online_search",
                "source_provider": "nasa_ads",
                "bibcode": record.get("bibcode") or "",
            }
        )
    return results


_PROVIDERS: dict[str, Callable[[str, int], list[dict[str, Any]]]] = {
    "openalex": _openalex,
    "pubmed": _pubmed,
    "europe_pmc": _europe_pmc,
    "dblp": _dblp,
    "nasa_ads": _nasa_ads,
}


def search_provider_router(
    query: str,
    *,
    limit: int = 10,
    providers: list[str] | None = None,
    query_contract: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest_ids = [manifest["id"] for manifest in PROVIDER_MANIFEST]
    if providers is not None:
        selected = list(providers)
        decisions = {provider_id: ("planned" if provider_id in selected else "not_selected") for provider_id in manifest_ids}
    elif query_contract:
        selected, decisions = plan_provider_ids(query_contract, manifest_ids)
    else:
        selected = [manifest["id"] for manifest in PROVIDER_MANIFEST if manifest.get("default_enabled")]
        decisions = {provider_id: ("planned" if provider_id in selected else "skipped_default_disabled") for provider_id in manifest_ids}
    items: list[dict[str, Any]] = []
    statuses = []
    for provider_id in manifest_ids:
        if provider_id not in selected:
            statuses.append({"provider": provider_id, "status": decisions.get(provider_id, "not_selected"), "item_count": 0})
            continue
        function = _PROVIDERS.get(provider_id)
        if function is None:
            statuses.append({"provider": provider_id, "status": "unknown_provider", "item_count": 0})
            continue
        manifest = next((entry for entry in PROVIDER_MANIFEST if entry["id"] == provider_id), {})
        credential = manifest.get("credential")
        if credential and not os.getenv(str(credential), "").strip():
            statuses.append({"provider": provider_id, "status": "credential_missing", "item_count": 0})
            continue
        try:
            found = function(query, min(limit, 20))
            items.extend(found)
            statuses.append({"provider": provider_id, "status": "loaded" if found else "success_empty", "item_count": len(found)})
        except Exception as exc:  # provider failures are a normal degraded mode
            statuses.append({"provider": provider_id, "status": "degraded", "item_count": 0, "error_type": type(exc).__name__})
    return items, {
        "schema_version": "dpl.literature_provider_router.v1",
        "query": query,
        "selected_providers": selected,
        "execution_plan": decisions,
        "provider_status": statuses,
        "item_count": len(items),
        "degraded": any(status.get("status") in {"degraded", "credential_missing", "rate_limited"} for status in statuses),
    }


def aggregate_provider_runs(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse legacy and specialized router reports into one auditable view."""
    by_provider: dict[str, dict[str, Any]] = {}
    for report in reports:
        if not isinstance(report, dict):
            continue
        rows = report.get("provider_status") or report.get("providers") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            provider = str(row.get("provider") or row.get("id") or "unknown")
            target = by_provider.setdefault(provider, {"provider": provider, "runs": 0, "statuses": {}, "returned_count": 0})
            status = str(row.get("status") or "unknown")
            target["runs"] += 1
            target["statuses"][status] = int(target["statuses"].get(status, 0)) + 1
            target["returned_count"] += int(row.get("item_count") or 0)
    return {
        "schema_version": "dpl.literature_provider_execution.v2",
        "run_count": len(reports),
        "providers": sorted(by_provider.values(), key=lambda item: item["provider"]),
        "policy": "provider_success_does_not_imply_topic_relevance",
    }
