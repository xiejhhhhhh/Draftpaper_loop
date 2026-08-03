"""GitHub metadata provider with an offline-fixture-friendly interface."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from .base import canonical_url, normalize_code_source


JsonFetcher = Callable[[str, dict[str, str]], tuple[int, dict[str, Any] | list[Any] | None, dict[str, str]]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_fetcher(url: str, headers: dict[str, str]) -> tuple[int, dict[str, Any] | list[Any] | None, dict[str, str]]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(2 * 1024 * 1024)
            payload = json.loads(body.decode("utf-8"))
            return int(response.status), payload, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return int(exc.code), None, dict(exc.headers.items())
    except (OSError, json.JSONDecodeError):
        return 0, None, {}


def _headers(token: str | None = None) -> dict[str, str]:
    value = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return {"Authorization": f"Bearer {value}"} if value else {}


def github_record_from_metadata(
    raw: dict[str, Any],
    *,
    work_id: str,
    source_intent: str = "knowledge_base",
    link_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert GitHub API or offline-export metadata into a CodeSourceRecord."""
    license_data = raw.get("license")
    license_spdx = license_data.get("spdx_id") if isinstance(license_data, dict) else license_data
    release = raw.get("latest_release") if isinstance(raw.get("latest_release"), dict) else {}
    quality = dict(raw.get("quality_signals") or {})
    quality.setdefault("github_stars", raw.get("stargazers_count"))
    quality.setdefault("github_forks", raw.get("forks_count") or raw.get("forks"))
    quality.setdefault("github_contributors", raw.get("contributors_count"))
    quality.setdefault("github_updated_at", raw.get("updated_at"))
    quality.setdefault("signals_provider", "github")
    quality.setdefault("signals_retrieved_at", _now())
    release_version = raw.get("tag_name") or release.get("tag_name") or raw.get("latest_release_tag")
    record = normalize_code_source(
        {
            **raw,
            "license_spdx": license_spdx,
            "tag_name": release_version,
            "release_date": raw.get("release_date") or release.get("published_at"),
            "quality_signals": quality,
            "provider_receipt": {
                "provider": "github",
                "status": "metadata_only",
                "retrieved_at": _now(),
            },
        },
        work_id=work_id,
        source_type="github",
        source_intent=source_intent,
        link_evidence=link_evidence,
    )
    record["latest_stable"] = bool(release_version) and not bool(raw.get("prerelease") or release.get("prerelease"))
    record["unreleased_head"] = not bool(release_version)
    record["has_readme"] = bool(raw.get("has_readme") or raw.get("readme_url"))
    record["has_tests"] = bool(raw.get("has_tests") or raw.get("test_signals"))
    record["has_license"] = bool(license_spdx)
    record["source_url"] = canonical_url(raw.get("html_url") or raw.get("url"))
    record["paper_alignment"] = str(raw.get("paper_alignment") or "unverified")
    return record


def search_github(
    query: str,
    *,
    work_id: str,
    limit: int = 10,
    source_intent: str = "knowledge_base",
    fetcher: JsonFetcher | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Search public repository metadata without cloning or downloading code."""
    fetch = fetcher or _default_fetcher
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({"q": query, "per_page": max(1, min(limit, 30))})
    status_code, payload, headers = fetch(url, _headers(token))
    if status_code == 0:
        status = "provider_error"
    elif status_code == 401:
        status = "auth_required"
    elif status_code == 403 or status_code == 429:
        status = "rate_limited"
    elif status_code >= 400:
        status = "provider_error"
    elif not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        status = "provider_schema_changed"
    else:
        status = "success_with_items" if payload.get("items") else "success_empty"
    raw_items = payload.get("items") if isinstance(payload, dict) and isinstance(payload.get("items"), list) else []
    records = [
        github_record_from_metadata(item, work_id=work_id, source_intent=source_intent)
        for item in raw_items[: max(1, limit)]
        if isinstance(item, dict)
    ]
    return {
        "provider": "github",
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
            "provider": "github",
            "status": status,
            "http_status": status_code,
            "retrieved_at": _now(),
            "metadata_only": True,
        },
    }
