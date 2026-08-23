"""Fail-closed repair routing for evidence-binding problems."""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Iterable

from .artifact_identity import canonical_json


EVIDENCE_BINDING_FAILURE_RECEIPT_SCHEMA = "dpl.evidence_binding_failure_receipt.v1"
_ORDER = ("producer", "adapter", "prose", "figure", "rerun")


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def classify_evidence_failure(code: str) -> str:
    token = str(code or "").lower()
    if any(value in token for value in ("missing", "source", "run_identity", "cohort", "split", "metric_identity", "evidence_identity")):
        return "producer"
    if any(value in token for value in ("schema", "validator", "adapter", "parser")):
        return "adapter"
    if any(value in token for value in ("caption", "prose", "wording", "citation")):
        return "prose"
    if any(value in token for value in ("figure", "series", "panel", "visual", "metadata")):
        return "figure"
    if any(value in token for value in ("data_change", "method_change", "rerun", "recompute")):
        return "rerun"
    return "producer"


def route_evidence_failures(failures: Iterable[dict[str, Any] | str]) -> dict[str, Any]:
    rows = []
    for item in failures:
        if isinstance(item, dict):
            code = str(item.get("code") or item.get("failure_class") or item.get("reason") or "unknown")
            detail = str(item.get("detail_zh") or item.get("message") or code)
        else:
            code = str(item)
            detail = code
        rows.append({"code": code, "detail_zh": detail, "repair_layer": classify_evidence_failure(code)})
    rows.sort(key=lambda item: (_ORDER.index(item["repair_layer"]), item["code"]))
    counts = Counter(item["repair_layer"] for item in rows)
    first = rows[0]["repair_layer"] if rows else None
    payload = {
        "schema_version": EVIDENCE_BINDING_FAILURE_RECEIPT_SCHEMA,
        "failures": rows,
        "recommended_repair_layer": first,
        "repair_order": list(_ORDER),
        "loop_guard": {
            "same_failure_class_count": max(counts.values(), default=0),
            "stop_and_report": max(counts.values(), default=0) >= 2,
        },
    }
    payload["receipt_sha256"] = _hash(payload)
    return payload


__all__ = ["EVIDENCE_BINDING_FAILURE_RECEIPT_SCHEMA", "classify_evidence_failure", "route_evidence_failures"]
