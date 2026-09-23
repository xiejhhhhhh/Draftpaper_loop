"""Conflict-aware merging for plugin and project-local capability bindings."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


def binding_key(binding: dict[str, Any]) -> tuple[str, str, str, str]:
    """Return the stable identity of one binding candidate."""
    return (
        str(binding.get("requirement_id") or ""),
        str(binding.get("kind") or ""),
        str(binding.get("binding_scope") or binding.get("scope") or ""),
        str(binding.get("plugin_id") or ""),
    )


def merge_binding_records(
    existing: Iterable[dict[str, Any]],
    incoming: Iterable[dict[str, Any]],
    *,
    producer: str,
) -> list[dict[str, Any]]:
    """Merge new assessment results without deleting local binding history.

    Registry assessment and project-local audit are different observations of
    the same requirement.  A later observation may add a better candidate or
    mark one candidate unavailable, but it must not erase a still auditable
    project-local binding.  Exact duplicates are collapsed; competing
    candidates remain visible and are sorted deterministically.
    """
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in existing:
        if not isinstance(item, dict):
            continue
        copied = deepcopy(item)
        copied.setdefault("binding_status", "retained")
        merged[binding_key(copied)] = copied
    for item in incoming:
        if not isinstance(item, dict):
            continue
        copied = deepcopy(item)
        copied["binding_source"] = producer
        copied["binding_status"] = "observed"
        key = binding_key(copied)
        prior = merged.get(key)
        if prior:
            # Preserve prior audit metadata while accepting the latest
            # verification fields.  The semantic binding key remains stable.
            preserved = {
                field: prior[field]
                for field in ("first_seen_at", "historical_receipts")
                if field in prior
            }
            copied.update(preserved)
        merged[key] = copied
    return sorted(
        merged.values(),
        key=lambda item: (
            str(item.get("requirement_id") or ""),
            str(item.get("kind") or ""),
            str(item.get("binding_scope") or item.get("scope") or ""),
            str(item.get("plugin_id") or ""),
        ),
    )


__all__ = ["binding_key", "merge_binding_records"]
