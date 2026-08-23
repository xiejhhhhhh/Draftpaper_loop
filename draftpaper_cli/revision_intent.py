"""Narrow revision intent contracts used to prevent accidental broad repairs."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from .artifact_identity import canonical_json


REVISION_INTENT_SCHEMA = "dpl.revision_intent.v1"
_ALLOWED_CHANGE_CLASSES = frozenset({"evidence_repair", "adapter_repair", "prose_only", "figure_metadata", "figure_semantic", "rerun"})


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def create_revision_intent(
    *,
    intent: str,
    allowed_change_classes: Iterable[str],
    protected_artifacts: Iterable[str] = (),
    expected_artifacts: Iterable[str] = (),
) -> dict[str, Any]:
    classes = sorted({str(item).strip() for item in allowed_change_classes if str(item).strip()})
    invalid = sorted(set(classes) - _ALLOWED_CHANGE_CLASSES)
    if invalid:
        raise ValueError("Unsupported revision intent change classes: " + ", ".join(invalid))
    payload = {
        "schema_version": REVISION_INTENT_SCHEMA,
        "intent": str(intent).strip(),
        "allowed_change_classes": classes,
        "protected_artifacts": sorted({str(item).replace("\\", "/") for item in protected_artifacts if str(item).strip()}),
        "expected_artifacts": sorted({str(item).replace("\\", "/") for item in expected_artifacts if str(item).strip()}),
    }
    if not payload["intent"] or not classes:
        raise ValueError("Revision intent and at least one change class are required.")
    payload["revision_intent_sha256"] = _hash(payload)
    return payload


def validate_revision_intent(intent: Any) -> list[str]:
    if not isinstance(intent, dict) or intent.get("schema_version") != REVISION_INTENT_SCHEMA:
        return ["Revision intent schema is invalid."]
    issues = []
    classes = set(intent.get("allowed_change_classes") or [])
    if not classes:
        issues.append("Revision intent has no allowed change class.")
    if not classes <= _ALLOWED_CHANGE_CLASSES:
        issues.append("Revision intent includes unsupported change classes.")
    expected = _hash({key: value for key, value in intent.items() if key != "revision_intent_sha256"})
    if intent.get("revision_intent_sha256") != expected:
        issues.append("Revision intent hash does not match its content.")
    return issues


__all__ = ["REVISION_INTENT_SCHEMA", "create_revision_intent", "validate_revision_intent"]
