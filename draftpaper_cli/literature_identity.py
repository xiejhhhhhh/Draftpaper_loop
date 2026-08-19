"""Stable, source-independent identities for literature works and attachments."""

from __future__ import annotations

import re
from typing import Any


IDENTIFIER_FIELDS = ("doi", "pmid", "pmcid", "arxiv_id", "bibcode", "openalex_id")


def _clean_identifier(value: Any) -> str:
    cleaned = str(value or "").strip().casefold()
    cleaned = re.sub(r"^(https?://(doi\.org/|arxiv\.org/abs/))", "", cleaned)
    return re.sub(r"\s+", "", cleaned)


def _clean_identity_text(value: Any) -> str:
    return re.sub(r"[^\w]+", " ", str(value or "").casefold(), flags=re.UNICODE).strip()


def canonical_work_id(item: dict[str, Any]) -> str:
    """Return a deterministic work identity, excluding local file identity."""
    explicit = str(item.get("work_id") or item.get("canonical_work_id") or "").strip()
    if explicit:
        return explicit
    for field in IDENTIFIER_FIELDS:
        value = _clean_identifier(item.get(field))
        if value:
            return f"{field}:{value}"
    title = _clean_identity_text(item.get("title"))
    authors = item.get("authors") or []
    first_author = _clean_identity_text(authors[0] if authors else "")
    year = str(item.get("year") or "").strip()
    return f"title:{title}|author:{first_author}|year:{year}" if title else ""


def identity_strength(item: dict[str, Any]) -> str:
    if str(item.get("work_id") or item.get("canonical_work_id") or "").strip():
        return "explicit"
    for field in IDENTIFIER_FIELDS:
        if _clean_identifier(item.get(field)):
            return field
    if str(item.get("title") or "").strip():
        return "title_author_year"
    return "unresolved"


def identity_aliases(item: dict[str, Any]) -> list[str]:
    """Return identifiers that can explain a merge without changing the work ID."""
    aliases: list[str] = []
    for field in IDENTIFIER_FIELDS:
        value = _clean_identifier(item.get(field))
        if value:
            aliases.append(f"{field}:{value}")
    local_id = str(item.get("local_document_id") or item.get("local_file_id") or "").strip()
    if local_id:
        aliases.append(f"local_artifact:{local_id}")
    return aliases
