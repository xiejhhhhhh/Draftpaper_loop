"""Conservative PDF-to-reference work identity resolution."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def document_id(path: str | Path) -> str:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _work_id(item: dict[str, Any]) -> str:
    for key in ("doi", "pmid", "pmcid", "arxiv_id", "bibcode", "openalex_id"):
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value.lower().removeprefix('https://doi.org/')}"
    title = re.sub(r"[^a-z0-9]+", " ", str(item.get("title") or "").lower()).strip()
    author = re.sub(r"[^a-z0-9]+", " ", str((item.get("authors") or [""])[0]).lower()).strip()
    year = str(item.get("year") or "")
    return f"title:{title}|author:{author}|year:{year}" if title else ""


def reference_work_id(item: dict[str, Any]) -> str:
    return _work_id(item)


def resolve_work_identity(project: str | Path, text: str, *, input_document_id: str, explicit_work_id: str | None = None) -> dict[str, Any]:
    if explicit_work_id:
        return {"work_id": explicit_work_id, "status": "bound", "confidence": 1.0, "reason": "explicit_work_id"}
    references_path = Path(project) / "references" / "literature_items.json"
    try:
        items = json.loads(references_path.read_text(encoding="utf-8")) if references_path.is_file() else []
    except (OSError, json.JSONDecodeError):
        items = []
    items = items if isinstance(items, list) else items.get("items", []) if isinstance(items, dict) else []
    normalized_text = str(text or "").lower()
    identifiers = [
        ("doi", value.lower()) for value in re.findall(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+", normalized_text, flags=re.I)
    ]
    for item in items:
        for key, identifier in identifiers:
            if str(item.get(key) or "").lower().strip() == identifier:
                return {"work_id": _work_id(item), "status": "bound", "confidence": 1.0, "reason": f"matched_{key}"}
    first_lines = [re.sub(r"\s+", " ", line).strip() for line in str(text or "").splitlines() if len(line.strip()) >= 20]
    observed = first_lines[0].lower() if first_lines else ""
    candidates: list[tuple[float, dict[str, Any]]] = []
    for item in items:
        title = str(item.get("title") or "").lower()
        if not title or not observed:
            continue
        score = difflib.SequenceMatcher(None, title[:300], observed[:300]).ratio()
        candidates.append((score, item))
    candidates.sort(key=lambda value: value[0], reverse=True)
    if candidates and candidates[0][0] >= 0.82 and (len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= 0.08):
        return {"work_id": _work_id(candidates[0][1]), "status": "bound", "confidence": round(candidates[0][0], 4), "reason": "title_author_candidate"}
    return {"work_id": f"document:{input_document_id.removeprefix('sha256:')}", "status": "unresolved", "confidence": round(candidates[0][0], 4) if candidates else 0.0, "reason": "no_high_confidence_reference_match"}
