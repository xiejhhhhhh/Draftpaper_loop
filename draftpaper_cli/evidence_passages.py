"""Select bounded, locatable evidence passages from normalized documents."""

from __future__ import annotations

from typing import Any

from .literature_language import tokenize_multilingual


def _flatten(document: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in document.get("pages") or []:
        for block in page.get("blocks") or []:
            if not isinstance(block, dict) or not str(block.get("text") or "").strip():
                continue
            row = dict(block)
            row.setdefault("page", page.get("page"))
            rows.append(row)
    return rows


def select_evidence_passages(document: dict[str, Any], *, anchors: list[str] | None = None, max_passages: int = 12, max_chars: int = 1800) -> list[dict[str, Any]]:
    anchor_tokens = tokenize_multilingual(" ".join(anchors or []))
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, block in enumerate(_flatten(document)):
        text = str(block.get("text") or "")
        lowered = text.lower()
        if str(block.get("section") or "").lower() == "references":
            continue
        overlap = len(anchor_tokens & tokenize_multilingual(text))
        role_bonus = 1 if any(term in lowered for term in ("method", "result", "data", "limitation", "方法", "结果", "数据", "局限")) else 0
        ranked.append((overlap + role_bonus, -index, block))
    ranked.sort(reverse=True, key=lambda value: (value[0], value[1]))
    passages: list[dict[str, Any]] = []
    for score, _, block in ranked[:max_passages]:
        text = str(block.get("text") or "")[:max_chars]
        passages.append({
            "passage_id": str(block.get("text_sha256") or ""),
            "section": str(block.get("section") or "unknown"),
            "page": block.get("page"),
            "block_id": block.get("block_id"),
            "text": text,
            "score": score,
            "locator_status": "page_block" if block.get("page") is not None else "document_block",
            "human_verified": False,
        })
    return passages
