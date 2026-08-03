"""Parser-neutral document representation for pypdf and MinerU outputs."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _section_for_line(line: str, current: str) -> str:
    value = line.strip().strip("# ")
    if re.match(r"^(abstract|introduction|background|data|methods?|results?|discussion|conclusion|references?)$", value, flags=re.I):
        return value.lower()
    return current


def normalize_pypdf(path: str | Path, pages: list[dict[str, Any]], *, document_id: str, work_id: str, quality: dict[str, Any], parser_version: str = "") -> dict[str, Any]:
    normalized_pages: list[dict[str, Any]] = []
    for page in pages:
        current_section = "unknown"
        blocks: list[dict[str, Any]] = []
        for index, line in enumerate(str(page.get("text") or "").splitlines(), start=1):
            text = line.strip()
            if not text:
                continue
            current_section = _section_for_line(text, current_section)
            blocks.append({
                "block_id": f"p{page.get('page', 0)}-b{index}",
                "type": "text",
                "section": current_section,
                "text": text,
                "bbox": None,
                "text_sha256": _sha256_bytes(text.encode("utf-8")),
            })
        normalized_pages.append({"page": int(page.get("page") or 0), "blocks": blocks})
    return {
        "schema_version": "dpl.normalized_document.v1",
        "document_id": document_id,
        "work_id": work_id,
        "parser": {"name": "pypdf", "version": parser_version, "backend": "native_text", "mode": "local"},
        "pages": normalized_pages,
        "quality": quality,
    }


def normalize_mineru_markdown(markdown: str, *, document_id: str, work_id: str, parser_version: str = "", mode: str = "official-agent") -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    current_section = "unknown"
    for index, raw_line in enumerate(str(markdown or "").splitlines(), start=1):
        text = raw_line.strip()
        if not text:
            continue
        if text.startswith("#"):
            current_section = text.strip("# ").lower() or current_section
        blocks.append({
            "block_id": f"remote-b{index}",
            "type": "heading" if raw_line.lstrip().startswith("#") else "text",
            "section": current_section,
            "text": text,
            "bbox": None,
            "page": None,
            "text_sha256": _sha256_bytes(text.encode("utf-8")),
        })
    return {
        "schema_version": "dpl.normalized_document.v1",
        "document_id": document_id,
        "work_id": work_id,
        "parser": {"name": "mineru", "version": parser_version, "backend": "markdown", "mode": mode},
        "pages": [{"page": None, "blocks": blocks}],
        "quality": {"status": "remote_markdown", "page_locator": "unavailable"},
    }


def load_mineru_markdown_or_json(path: str | Path, *, document_id: str, work_id: str, parser_version: str = "", mode: str = "local") -> dict[str, Any]:
    source = Path(path)
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("pages"), list):
            payload.setdefault("schema_version", "dpl.normalized_document.v1")
            payload.setdefault("document_id", document_id)
            payload.setdefault("work_id", work_id)
            payload.setdefault("parser", {"name": "mineru", "version": parser_version, "mode": mode})
            return payload
        raw_blocks: list[dict[str, Any]] = []

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                text = value.get("text") or value.get("content") or value.get("md")
                if isinstance(text, str) and text.strip():
                    raw_blocks.append({
                        "block_id": str(value.get("id") or value.get("index") or f"remote-b{len(raw_blocks) + 1}"),
                        "type": str(value.get("type") or "text"),
                        "section": str(value.get("section") or "unknown"),
                        "text": text.strip(),
                        "bbox": value.get("bbox"),
                        "page": value.get("page_id") or value.get("page"),
                        "text_sha256": _sha256_bytes(text.strip().encode("utf-8")),
                    })
                for child in value.values():
                    if isinstance(child, (dict, list)):
                        collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(payload)
        if raw_blocks:
            return {
                "schema_version": "dpl.normalized_document.v1",
                "document_id": document_id,
                "work_id": work_id,
                "parser": {"name": "mineru", "version": parser_version, "backend": "json", "mode": mode},
                "pages": [{"page": None, "blocks": raw_blocks}],
                "quality": {"status": "remote_structured", "page_locator": "provider_dependent"},
            }
    return normalize_mineru_markdown(source.read_text(encoding="utf-8", errors="replace"), document_id=document_id, work_id=work_id, parser_version=parser_version, mode=mode)
