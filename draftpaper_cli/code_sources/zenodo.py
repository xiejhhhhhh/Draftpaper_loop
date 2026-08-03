"""Zenodo metadata provider for versioned research-code records."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from .base import normalize_code_source


JsonFetcher = Callable[[str, dict[str, str]], tuple[int, dict[str, Any] | list[Any] | None, dict[str, str]]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_fetcher(url: str, headers: dict[str, str]) -> tuple[int, dict[str, Any] | list[Any] | None, dict[str, str]]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(4 * 1024 * 1024)
            return int(response.status), json.loads(body.decode("utf-8")), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return int(exc.code), None, dict(exc.headers.items())
    except (OSError, json.JSONDecodeError):
        return 0, None, {}


def _headers(token: str | None = None) -> dict[str, str]:
    value = token or os.environ.get("ZENODO_TOKEN")
    return {"Authorization": f"Bearer {value}"} if value else {}


def _file_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    files = raw.get("files") or (raw.get("metadata") or {}).get("files") or []
    rows = []
    for item in files:
        if not isinstance(item, dict):
            continue
        links = item.get("links") or {}
        rows.append({
            "key": item.get("key") or item.get("filename"),
            "size": item.get("size"),
            "checksum": item.get("checksum"),
            "download_url": item.get("download_url") or links.get("self"),
        })
    return rows


def zenodo_record_from_metadata(
    raw: dict[str, Any],
    *,
    work_id: str,
    source_intent: str = "knowledge_base",
    link_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else raw
    links = raw.get("links") if isinstance(raw.get("links"), dict) else {}
    record_id = str(raw.get("id") or metadata.get("record_id") or "") or None
    doi = raw.get("doi") or metadata.get("doi")
    concept_doi = raw.get("conceptdoi") or metadata.get("conceptdoi")
    version = raw.get("version") or metadata.get("version")
    files = _file_rows(raw)
    quality = dict(raw.get("quality_signals") or {})
    quality.setdefault("zenodo_downloads", raw.get("stats", {}).get("downloads") if isinstance(raw.get("stats"), dict) else None)
    quality.setdefault("signals_provider", "zenodo")
    quality.setdefault("signals_retrieved_at", _now())
    related = metadata.get("related_identifiers") or raw.get("related_identifiers") or []
    if isinstance(related, dict):
        related = [related]
    related_urls = [
        str(item.get("identifier") or item.get("url"))
        for item in related
        if isinstance(item, dict) and str(item.get("identifier") or item.get("url") or "").startswith(("http://", "https://"))
    ]
    repository_url = raw.get("repository_url") or raw.get("related_repository") or next((value for value in related_urls if "github.com" in value.lower()), None)
    record = normalize_code_source(
        {
            "canonical_url": raw.get("links", {}).get("html") or raw.get("links", {}).get("self") or (f"https://zenodo.org/records/{record_id}" if record_id else ""),
            "repository_url": repository_url,
            "doi": doi,
            "concept_doi": concept_doi,
            "record_id": record_id,
            "name": metadata.get("title") or raw.get("title"),
            "version": version,
            "release_date": raw.get("publication_date") or metadata.get("publication_date"),
            "license": metadata.get("license"),
            "files": files,
            "archive_url": links.get("archive") or (files[0].get("download_url") if files else None),
            "quality_signals": quality,
            "provider_receipt": {"provider": "zenodo", "status": "metadata_only", "retrieved_at": _now()},
        },
        work_id=work_id,
        source_type="zenodo",
        source_intent=source_intent,
        link_evidence=link_evidence,
    )
    record["concept_doi"] = str(concept_doi or "") or None
    record["version_doi"] = str(doi or "") or None
    record["related_identifiers"] = related
    record["latest_stable"] = str(raw.get("state") or "published") == "published" and not bool(raw.get("is_tombstone"))
    record["restricted"] = bool(raw.get("restricted") or metadata.get("access_right") == "restricted")
    record["tombstone"] = bool(raw.get("is_tombstone") or raw.get("state") == "tombstone")
    record["archive_available"] = bool(files) and not record["restricted"] and not record["tombstone"]
    if record["tombstone"]:
        record["limitations"].append("Zenodo record is tombstoned; archive availability is not asserted.")
    if record["restricted"]:
        record["limitations"].append("Zenodo files are restricted; metadata-only handling is required.")
    return record


def resolve_zenodo_doi(
    doi: str,
    *,
    work_id: str,
    source_intent: str = "knowledge_base",
    fetcher: JsonFetcher | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Resolve a version DOI to one public record without treating concept DOI as a version."""
    normalized_doi = str(doi).strip().rstrip(".,;)")
    match = re.search(r"zenodo\.(\d+)$", normalized_doi, flags=re.I)
    if not match:
        return {
            "provider": "zenodo",
            "status": "invalid_doi",
            "doi": doi,
            "records": [],
            "metadata_only": True,
            "provider_receipt": {"provider": "zenodo", "status": "invalid_doi", "metadata_only": True, "retrieved_at": _now()},
        }
    fetch = fetcher or _default_fetcher
    url = f"https://zenodo.org/api/records/{match.group(1)}"
    status_code, payload, headers = fetch(url, _headers(token))
    if status_code == 404:
        status = "not_found"
    elif status_code == 429:
        status = "rate_limited"
    elif status_code == 401:
        status = "auth_required"
    elif status_code >= 400 or not isinstance(payload, dict):
        status = "provider_error"
    else:
        status = "success_with_items"
    records = [zenodo_record_from_metadata(payload, work_id=work_id, source_intent=source_intent)] if status == "success_with_items" else []
    return {
        "provider": "zenodo",
        "status": status,
        "http_status": status_code,
        "doi": doi,
        "records": records,
        "record_count": len(records),
        "retry_after": headers.get("Retry-After"),
        "metadata_only": True,
        "retrieved_at": _now(),
        "provider_receipt": {
            "provider": "zenodo",
            "status": status,
            "http_status": status_code,
            "retrieved_at": _now(),
            "metadata_only": True,
        },
    }


def search_zenodo(
    query: str,
    *,
    work_id: str,
    limit: int = 10,
    source_intent: str = "knowledge_base",
    fetcher: JsonFetcher | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    fetch = fetcher or _default_fetcher
    url = "https://zenodo.org/api/records?" + urllib.parse.urlencode({"q": query, "size": max(1, min(limit, 25))})
    status_code, payload, headers = fetch(url, _headers(token))
    if status_code == 0:
        status = "provider_error"
    elif status_code == 401:
        status = "auth_required"
    elif status_code == 429:
        status = "rate_limited"
    elif status_code >= 400:
        status = "provider_error"
    else:
        hits_container = payload.get("hits") if isinstance(payload, dict) else None
        hits = hits_container.get("hits") if isinstance(hits_container, dict) else None
        if not isinstance(hits, list):
            status = "provider_schema_changed"
        else:
            status = "success_with_items" if hits else "success_empty"
    hits_container = payload.get("hits") if isinstance(payload, dict) else None
    hits = hits_container.get("hits") if isinstance(hits_container, dict) and isinstance(hits_container.get("hits"), list) else []
    records = [
        zenodo_record_from_metadata(item, work_id=work_id, source_intent=source_intent)
        for item in hits[: max(1, limit)]
        if isinstance(item, dict)
    ]
    return {
        "provider": "zenodo",
        "status": status,
        "http_status": status_code,
        "query": query,
        "work_id": work_id,
        "record_count": len(records),
        "records": records,
        "retrieved_at": _now(),
        "retry_after": headers.get("Retry-After"),
        "metadata_only": True,
        "provider_receipt": {
            "provider": "zenodo",
            "status": status,
            "http_status": status_code,
            "retrieved_at": _now(),
            "metadata_only": True,
        },
    }
