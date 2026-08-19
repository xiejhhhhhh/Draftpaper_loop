"""Canonical literature registry and snapshot helpers.

``literature_items.json`` remains a compatibility projection for existing
consumers.  The registry in this module is the only canonical literature
record written by the new merge path.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .literature_identity import canonical_work_id, identity_aliases, identity_strength
from .project_scaffold import _write_json
from .project_state import load_project
from .references import SCORE_FIELDS, _load_existing_literature_items, normalize_reference_items


REGISTRY_RELATIVE_PATH = "references/literature_work_registry.json"
REGISTRY_SCHEMA = "dpl.literature_work_registry.v3"


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    _write_json(temporary, payload)
    temporary.replace(path)


def _registry_hash(records: list[dict[str, Any]]) -> str:
    encoded = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _score_bundle(item: dict[str, Any]) -> dict[str, Any]:
    values = {field: item.get(field) for field in SCORE_FIELDS}
    statuses = dict(item.get("score_status") or {})
    return {
        "values": values,
        "status": {field: statuses.get(field) or ("computed" if value is not None else "not_evaluated") for field, value in values.items()},
        "provenance": deepcopy(item.get("score_provenance") or {}),
        "context_hash": item.get("score_context_hash"),
    }


def registry_record(item: dict[str, Any]) -> dict[str, Any]:
    work_id = str(item.get("work_id") or canonical_work_id(item)).strip()
    record = deepcopy(item)
    record["work_id"] = work_id
    record["canonical_work_id"] = work_id
    return {
        "work_id": work_id,
        "identity_strength": identity_strength(record),
        "identity_aliases": identity_aliases(record),
        "source_types": sorted({str(value.get("source_type") or "") for value in record.get("source_records") or [] if isinstance(value, dict) and value.get("source_type")}),
        "score_bundle": _score_bundle(record),
        "document_parse_count": len(record.get("document_parses") or []),
        "record": record,
    }


def build_literature_registry(items: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = normalize_reference_items(items)
    records = [registry_record(item) for item in normalized if canonical_work_id(item)]
    snapshot_hashes = {
        str(item.get("snapshot_hash"))
        for item in normalized
        if str(item.get("snapshot_hash") or "").strip()
    }
    return {
        "schema_version": REGISTRY_SCHEMA,
        "registry_hash": _registry_hash(records),
        "record_count": len(records),
        "snapshot_hash": next(iter(snapshot_hashes)) if len(snapshot_hashes) == 1 else None,
        "records": records,
    }


def load_literature_registry(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    path = state.path / REGISTRY_RELATIVE_PATH
    if not path.is_file():
        return build_literature_registry(_load_existing_literature_items(state.path / "references"))
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return build_literature_registry(_load_existing_literature_items(state.path / "references"))
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        return build_literature_registry(_load_existing_literature_items(state.path / "references"))
    return payload


def write_literature_registry(project: str | Path, items: list[dict[str, Any]]) -> dict[str, Any]:
    state = load_project(project)
    payload = build_literature_registry(items)
    path = state.path / REGISTRY_RELATIVE_PATH
    _atomic_json(path, payload)
    return {
        "status": "written",
        "path": REGISTRY_RELATIVE_PATH,
        "registry_hash": payload["registry_hash"],
        "record_count": payload["record_count"],
    }


def project_registry_items(project: str | Path) -> list[dict[str, Any]]:
    payload = load_literature_registry(project)
    return [
        deepcopy(entry.get("record"))
        for entry in payload.get("records") or []
        if isinstance(entry, dict) and isinstance(entry.get("record"), dict)
    ]
