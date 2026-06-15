from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any


ZOTERO_API_ROOT = "https://api.zotero.org"
ZOTERO_ITEM_LIMIT = 100


class ZoteroAdapterError(RuntimeError):
    """Raised when Zotero collection import cannot proceed."""


def _zotero_config() -> tuple[str, str, str]:
    library_id = os.getenv("ZOTERO_LIBRARY_ID", "").strip()
    api_key = os.getenv("ZOTERO_API_KEY", "").strip()
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", "user").strip().lower() or "user"
    if library_type not in {"user", "group"}:
        raise ZoteroAdapterError("ZOTERO_LIBRARY_TYPE must be either 'user' or 'group'.")
    if not library_id or not api_key:
        raise ZoteroAdapterError("ZOTERO_LIBRARY_ID and ZOTERO_API_KEY are required for Zotero collection import.")
    return library_id, library_type, api_key


def _library_prefix(library_id: str, library_type: str) -> str:
    root = "users" if library_type == "user" else "groups"
    return f"{ZOTERO_API_ROOT}/{root}/{urllib.parse.quote(library_id)}"


def _get_json_list(url: str, api_key: str, params: dict[str, Any] | None = None, *, limit: int | None = None) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    start = 0
    page_limit = min(limit or ZOTERO_ITEM_LIMIT, ZOTERO_ITEM_LIMIT)
    while True:
        request_params = dict(params or {})
        request_params.update({"format": "json", "limit": page_limit, "start": start})
        request = urllib.request.Request(
            f"{url}?{urllib.parse.urlencode(request_params)}",
            headers={
                "Zotero-API-Key": api_key,
                "User-Agent": "Draftpaper-loop local workflow",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                page = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ZoteroAdapterError(f"Zotero API request failed: {exc}") from exc
        if not isinstance(page, list):
            raise ZoteroAdapterError("Zotero API returned an unexpected non-list response.")
        collected.extend(item for item in page if isinstance(item, dict))
        if not page or (limit is not None and len(collected) >= limit) or len(page) < page_limit:
            break
        start += len(page)
    return collected[:limit] if limit is not None else collected


def list_zotero_collections() -> list[dict[str, str]]:
    """List collection names and keys without exposing credentials."""
    library_id, library_type, api_key = _zotero_config()
    collections = _get_json_list(f"{_library_prefix(library_id, library_type)}/collections", api_key)
    return [
        {
            "key": str(collection.get("key") or ""),
            "name": str((collection.get("data") or {}).get("name") or ""),
        }
        for collection in collections
        if collection.get("key") and (collection.get("data") or {}).get("name")
    ]


def find_zotero_collection_key(collection_name: str) -> tuple[str, str]:
    """Find a Zotero collection key by exact, case-insensitive, or substring match."""
    wanted = collection_name.strip().lower()
    if not wanted:
        raise ZoteroAdapterError("A Zotero collection name is required.")
    collections = list_zotero_collections()
    for collection in collections:
        if collection["name"].strip().lower() == wanted:
            return collection["key"], collection["name"]
    for collection in collections:
        name = collection["name"].strip().lower()
        if wanted in name or name in wanted:
            return collection["key"], collection["name"]
    raise ZoteroAdapterError(f"Zotero collection not found: {collection_name}")


def _creator_name(creator: dict[str, Any]) -> str:
    if creator.get("name"):
        return str(creator.get("name")).strip()
    return " ".join(str(creator.get(key) or "").strip() for key in ("firstName", "lastName")).strip()


def _authors(data: dict[str, Any]) -> list[str]:
    authors = []
    for creator in data.get("creators") or []:
        if not isinstance(creator, dict):
            continue
        if creator.get("creatorType") not in {"author", "editor", "contributor"}:
            continue
        name = _creator_name(creator)
        if name:
            authors.append(name)
    return authors


def _contexts(context: str) -> list[str]:
    clean = (context or "idea").strip().lower()
    if clean == "all":
        return ["idea", "data", "methods"]
    if clean not in {"idea", "data", "methods"}:
        raise ZoteroAdapterError("Zotero context must be one of: idea, data, methods, all.")
    return [clean]


def zotero_item_to_reference(item: dict[str, Any], *, collection_name: str, context: str = "idea") -> dict[str, Any] | None:
    data = item.get("data") or {}
    if not isinstance(data, dict):
        return None
    item_type = str(data.get("itemType") or "")
    if item_type in {"attachment", "note", "annotation"} or data.get("parentItem"):
        return None
    title = " ".join(str(data.get("title") or "").split())
    if not title:
        return None
    contexts = _contexts(context)
    query_label = f"Zotero collection: {collection_name}"
    return {
        "zotero_key": str(item.get("key") or data.get("key") or ""),
        "title": title,
        "authors": _authors(data),
        "year": str(data.get("date") or ""),
        "doi": str(data.get("DOI") or data.get("doi") or "").strip(),
        "url": str(data.get("url") or "").strip(),
        "abstract": " ".join(str(data.get("abstractNote") or "").split()),
        "publication": str(data.get("publicationTitle") or data.get("conferenceName") or data.get("proceedingsTitle") or "").strip(),
        "citation_count": 0,
        "source": "zotero_collection",
        "reference_origin": "existing_zotero",
        "zotero_collection": collection_name,
        "item_type": item_type,
        "search_context": contexts[0],
        "search_contexts": contexts,
        "search_query": query_label,
        "search_queries": [query_label],
    }


def fetch_zotero_collection_items(
    collection_name: str,
    *,
    limit: int = 50,
    context: str = "idea",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch article-like items from a named Zotero collection."""
    library_id, library_type, api_key = _zotero_config()
    collection_key, matched_name = find_zotero_collection_key(collection_name)
    raw_items = _get_json_list(
        f"{_library_prefix(library_id, library_type)}/collections/{urllib.parse.quote(collection_key)}/items",
        api_key,
        limit=max(1, limit),
    )
    items = [
        item
        for item in (
            zotero_item_to_reference(raw, collection_name=matched_name, context=context)
            for raw in raw_items
        )
        if item
    ]
    manifest = {
        "status": "loaded",
        "library_type": library_type,
        "library_id_configured": bool(library_id),
        "requested_collection": collection_name,
        "matched_collection": matched_name,
        "collection_key": collection_key,
        "requested_limit": limit,
        "raw_item_count": len(raw_items),
        "usable_item_count": len(items),
        "context": context,
    }
    return items, manifest
