"""Score-state normalization and audit helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .references import SCORE_FIELDS, _optional_float


def normalize_score_bundle(item: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(item)
    statuses = dict(result.get("score_status") or {})
    for field in SCORE_FIELDS:
        value = _optional_float(result.get(field))
        result[field] = value
        statuses[field] = statuses.get(field) or ("computed" if value is not None else "not_evaluated")
    result["score_status"] = statuses
    result.setdefault("score_provenance", {})
    return result


def score_state_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"computed": 0, "not_evaluated": 0, "stale": 0, "legacy_zero_ambiguous": 0}
    for item in items:
        statuses = item.get("score_status") if isinstance(item.get("score_status"), dict) else {}
        for field in ("citation_weight", "relevance_score", "journal_score"):
            status = str(statuses.get(field) or ("computed" if _optional_float(item.get(field)) is not None else "not_evaluated"))
            if status in counts:
                counts[status] += 1
            elif status.startswith("legacy"):
                counts["legacy_zero_ambiguous"] += 1
    return counts


def identify_legacy_zero_scores(item: dict[str, Any]) -> list[str]:
    """Flag all-zero rows when no reproducible scoring provenance exists."""
    if item.get("score_provenance") or item.get("score_context_hash"):
        return []
    fields = ("citation_weight", "relevance_score", "journal_score")
    if all(item.get(field) in {0, 0.0, "0", "0.0"} for field in fields):
        return list(fields)
    return []
