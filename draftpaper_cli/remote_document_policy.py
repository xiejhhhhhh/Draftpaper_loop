"""Policy checks for optional remote MinerU Agent parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any


OFFICIAL_AGENT_MAX_MB = 10
OFFICIAL_AGENT_MAX_PAGES = 20
ALLOWED_DEFAULT_CLASSES = {"published-public", "published_public_reference"}
SUPPORTED_DOCUMENT_CLASSES = {
    "published-public",
    "published_public_reference",
    "licensed-private",
    "unpublished",
    "sensitive",
    "unknown",
}


def check_remote_parse_eligibility(
    path: str | Path,
    *,
    page_count: int | None,
    document_class: str = "unknown",
    consent: str = "ask_once",
    max_mb: int = OFFICIAL_AGENT_MAX_MB,
    max_pages: int = OFFICIAL_AGENT_MAX_PAGES,
    allowed_document_classes: set[str] | None = None,
    require_known_page_count: bool = True,
) -> dict[str, Any]:
    source = Path(path)
    reasons: list[str] = []
    normalized_consent = str(consent or "ask_once").strip().lower()
    normalized_class = str(document_class or "unknown").strip().lower()
    allowed_classes = set(allowed_document_classes or ALLOWED_DEFAULT_CLASSES)
    if normalized_consent not in {"once", "project", "allow", "ask_once"}:
        reasons.append("remote_consent_missing")
    if normalized_class not in SUPPORTED_DOCUMENT_CLASSES:
        reasons.append("document_class_unknown")
    if normalized_class not in allowed_classes:
        reasons.append("document_class_not_public_reference")
    try:
        file_size = source.stat().st_size
    except OSError:
        file_size = 0
        reasons.append("file_missing")
    if file_size > max_mb * 1024 * 1024:
        reasons.append("file_over_provider_limit")
    if require_known_page_count and (page_count is None or page_count <= 0):
        reasons.append("page_count_unknown")
    if page_count is not None and page_count > max_pages:
        reasons.append("page_count_over_provider_limit")
    return {
        "status": "eligible" if not reasons and normalized_consent in {"once", "project", "allow"} else "review_required" if normalized_consent == "ask_once" and not reasons else "skipped",
        "eligible": not reasons and normalized_consent in {"once", "project", "allow"},
        "consent": normalized_consent,
        "document_class": normalized_class,
        "allowed_document_classes": sorted(allowed_classes),
        "file_size_bytes": file_size,
        "page_count": page_count,
        "max_file_mb": max_mb,
        "max_pages": max_pages,
        "reason_codes": reasons,
    }
