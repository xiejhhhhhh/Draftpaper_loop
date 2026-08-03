"""Deterministic PDF extraction quality checks used by the parser router."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def extract_pypdf_pages(path: str | Path, *, max_pages: int | None = None) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except Exception:
        return []
    try:
        reader = PdfReader(str(path))
    except Exception:
        return []
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(reader.pages[:max_pages] if max_pages else reader.pages, start=1):
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except (TypeError, AttributeError, Exception):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
        pages.append({"page": index, "text": str(text), "char_count": len(str(text))})
    return pages


def assess_extraction_quality(pages: list[dict[str, Any]], *, purpose: str = "evidence") -> dict[str, Any]:
    page_count = len(pages)
    counts = [int(page.get("char_count") or len(str(page.get("text") or ""))) for page in pages]
    total_chars = sum(counts)
    empty_pages = sum(1 for count in counts if count < 20)
    text = "\n".join(str(page.get("text") or "") for page in pages)
    replacement_count = text.count("\ufffd")
    nonempty_lines = [line.strip() for line in text.splitlines() if line.strip()]
    short_line_ratio = sum(1 for line in nonempty_lines if len(line) <= 4) / max(1, len(nonempty_lines))
    repeated_lines = {line for line in nonempty_lines if nonempty_lines.count(line) >= max(3, page_count)}
    reasons: list[str] = []
    if page_count == 0:
        reasons.append("no_pages_extracted")
    if page_count and empty_pages / page_count >= 0.35:
        reasons.append("empty_text_ratio_high")
    if total_chars == 0:
        reasons.append("scan_likelihood_high")
    if total_chars and replacement_count / total_chars >= 0.01:
        reasons.append("garbled_text_high")
    if short_line_ratio >= 0.45:
        reasons.append("fragmented_text")
    if repeated_lines and len(repeated_lines) >= 2:
        reasons.append("repeated_header_footer_suspected")
    if purpose in {"tables", "formulas", "evidence", "full"} and not re.search(r"\b(method|result|discussion|table|figure|方法|结果|讨论|表|图)\b", text, flags=re.I):
        reasons.append("requested_section_or_block_missing")
    return {
        "schema_version": "dpl.extraction_quality.v1",
        "status": "passed" if not reasons else "upgrade_recommended",
        "purpose": purpose,
        "page_count": page_count,
        "total_chars": total_chars,
        "chars_per_page": counts,
        "empty_page_ratio": round(empty_pages / max(1, page_count), 4),
        "replacement_char_ratio": round(replacement_count / max(1, total_chars), 6),
        "short_line_ratio": round(short_line_ratio, 4),
        "repeated_line_count": len(repeated_lines),
        "reason_codes": reasons,
    }
