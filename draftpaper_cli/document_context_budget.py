"""Deterministic context selection and token estimation for document evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CONTEXT_POLICY: dict[str, Any] = {
    "schema_version": "dpl.document_context_policy.v1",
    "max_candidate_passages_per_work": 12,
    "max_context_passages_per_work": 6,
    "max_chars_per_passage": 1800,
    "max_total_chars_per_work": 9000,
    "include_sections": ["abstract", "methods", "results", "discussion"],
    "exclude_sections": ["references"],
    "send_raw_parser_json_to_llm": False,
}


def estimate_input_tokens(text: str, *, method: str = "conservative_chars_per_token_4") -> int:
    return max(0, (len(str(text or "")) + 3) // 4)


def load_context_policy(project: str | Path | None = None) -> dict[str, Any]:
    if project is None:
        return dict(DEFAULT_CONTEXT_POLICY)
    path = Path(project) / "references" / "document_context_policy.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONTEXT_POLICY)
    if not isinstance(payload, dict):
        return dict(DEFAULT_CONTEXT_POLICY)
    merged = dict(DEFAULT_CONTEXT_POLICY)
    merged.update(payload)
    return merged


def ensure_context_policy(project: str | Path) -> Path:
    path = Path(project) / "references" / "document_context_policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(json.dumps(DEFAULT_CONTEXT_POLICY, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def select_with_budget(
    passages: list[dict[str, Any]],
    *,
    max_passages: int = 6,
    max_chars: int = 9000,
    max_chars_per_passage: int = 1800,
    include_sections: set[str] | None = None,
    exclude_sections: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    total_chars = 0
    include = {str(value).strip().lower() for value in (include_sections or set()) if str(value).strip()}
    exclude = {str(value).strip().lower() for value in (exclude_sections or {"references"}) if str(value).strip()}
    skipped: list[dict[str, Any]] = []
    for passage in passages:
        section = str(passage.get("section") or "unknown").strip().lower()
        if section in exclude or (include and section != "unknown" and section not in include):
            skipped.append({"passage_id": passage.get("passage_id"), "reason": "section_policy"})
            continue
        text = str(passage.get("text") or "")[: max(1, int(max_chars_per_passage))]
        if len(selected) >= max_passages or total_chars + len(text) > max_chars:
            skipped.append({"passage_id": passage.get("passage_id"), "reason": "context_budget"})
            continue
        selected.append({**passage, "text": text})
        total_chars += len(text)
    manifest = {
        "schema_version": "dpl.document_context_manifest.v1",
        "candidate_passage_count": len(passages),
        "selected_passage_count": len(selected),
        "selected_chars": total_chars,
        "estimated_input_tokens": estimate_input_tokens(" ".join(str(item.get("text") or "") for item in selected)),
        "estimate_method": "conservative_chars_per_token_4",
        "raw_parser_json_sent_to_llm": False,
        "max_passages": int(max_passages),
        "max_chars": int(max_chars),
        "max_chars_per_passage": int(max_chars_per_passage),
        "skipped_passages": skipped,
    }
    return selected, manifest
