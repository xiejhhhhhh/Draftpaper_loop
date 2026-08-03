"""Stable identity and common normalization for code-source providers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = "dpl.code_source_record.v2"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def canonical_url(value: Any) -> str:
    raw = _compact(value)
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urlsplit(raw)
    host = parsed.netloc.lower()
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    if host in {"github.com", "www.github.com"}:
        path = re.sub(r"\.git$", "", path)
    return urlunsplit((parsed.scheme.lower(), host, path, "", ""))


def normalize_work_id(item: dict[str, Any]) -> str:
    """Build a stable work identity independent of citation-key renaming."""
    doi = _compact(item.get("doi") or item.get("DOI")).lower()
    if doi:
        return f"work:doi:{doi}"
    existing = _compact(item.get("work_id"))
    if existing:
        return existing
    title = re.sub(r"[^a-z0-9]+", " ", _compact(item.get("title")).lower()).strip()
    authors = _compact(item.get("authors") or item.get("author")).lower()
    year = _compact(item.get("year") or item.get("date"))[:4]
    material = "|".join((title, authors, year))
    return f"work:sha256:{_digest(material)[:32]}"


def code_work_id(source: dict[str, Any]) -> str:
    """Build identity shared by GitHub and its Zenodo archive."""
    repository = canonical_url(source.get("repository_url") or source.get("html_url") or source.get("url"))
    if repository and "github.com/" in repository:
        return f"codework:github:{repository.split('github.com/', 1)[1].lower()}"
    concept_doi = _compact(source.get("concept_doi") or source.get("conceptdoi")).lower()
    if concept_doi:
        return f"codework:zenodo-concept:{concept_doi}"
    doi = _compact(source.get("doi") or source.get("doi_url")).lower()
    if doi:
        return f"codework:doi:{doi}"
    material = "|".join((canonical_url(source.get("canonical_url")), _compact(source.get("name"))))
    return f"codework:sha256:{_digest(material)[:32]}"


@dataclass
class CodeSourceRecord:
    source_type: str
    work_id: str
    source_role: str = "research_code_lead"
    source_intent: str = "knowledge_base"
    canonical_url: str = ""
    repository_url: str = ""
    doi: str | None = None
    concept_doi: str | None = None
    record_id: str | None = None
    full_name: str | None = None
    version: str | None = None
    commit_sha: str | None = None
    release_date: str | None = None
    license: str | None = None
    persistence: str = "unknown"
    verification_status: str = "metadata_only"
    download_status: str = "not_requested"
    execution_status: str = "not_run"
    promotion_status: str = "candidate"
    link_evidence: list[dict[str, Any]] = field(default_factory=list)
    quality_signals: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    provider_receipt: dict[str, Any] = field(default_factory=dict)
    archive_url: str | None = None
    files: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "code_source_id": self.source_id,
            "code_work_id": code_work_id(self.__dict__),
            **self.__dict__,
        }
        payload["canonical_url"] = canonical_url(payload.get("canonical_url"))
        payload["repository_url"] = canonical_url(payload.get("repository_url"))
        return payload

    @property
    def source_id(self) -> str:
        identity = "|".join(
            (
                self.source_type,
                canonical_url(self.canonical_url),
                _compact(self.doi).lower(),
                _compact(self.version).lower(),
                _compact(self.commit_sha).lower(),
            )
        )
        return f"codesrc:{_digest(identity)[:32]}"


def normalize_code_source(
    source: dict[str, Any],
    *,
    work_id: str,
    source_type: str,
    source_intent: str = "knowledge_base",
    link_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize provider data while preserving unknown fields in provenance."""
    source_type = source_type.strip().lower()
    if source_type not in {"github", "zenodo", "project_local", "academicforge"}:
        raise ValueError(f"Unsupported code source type: {source_type}")
    raw_license = source.get("license")
    license_value = raw_license.get("spdx_id") if isinstance(raw_license, dict) else raw_license
    record = CodeSourceRecord(
        source_type=source_type,
        work_id=work_id,
        source_intent=source_intent,
        canonical_url=canonical_url(source.get("canonical_url") or source.get("html_url") or source.get("url")),
        repository_url=canonical_url(source.get("repository_url") or source.get("html_url") or source.get("url")),
        doi=_compact(source.get("doi") or source.get("doi_url")) or None,
        concept_doi=_compact(source.get("concept_doi") or source.get("conceptdoi")) or None,
        record_id=_compact(source.get("record_id") or source.get("id")) or None,
        full_name=_compact(source.get("full_name") or source.get("name")) or None,
        version=_compact(source.get("version") or source.get("tag_name")) or None,
        commit_sha=_compact(source.get("commit_sha") or source.get("target_commitish")) or None,
        release_date=_compact(source.get("release_date") or source.get("published_at") or source.get("publication_date")) or None,
        license=_compact(source.get("license_spdx") or license_value) or None,
        persistence="versioned_archive" if source_type == "zenodo" else "live_repository" if source_type == "github" else "unknown",
        link_evidence=list(link_evidence or source.get("link_evidence") or []),
        quality_signals=dict(source.get("quality_signals") or {}),
        limitations=list(source.get("limitations") or []),
        provider_receipt=dict(source.get("provider_receipt") or {}),
        archive_url=_compact(source.get("archive_url") or source.get("download_url")) or None,
        files=[item for item in source.get("files") or [] if isinstance(item, dict)],
    )
    return record.to_dict()
