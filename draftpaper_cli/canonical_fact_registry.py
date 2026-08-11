"""Discipline-neutral canonical scientific fact registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .artifact_identity import canonical_json
from .passport import project_root, utc_now
from .state_kernel import atomic_write_json


REGISTRY_SCHEMA = "dpl.canonical_fact_registry.v2"
REGISTRY_DIR = "lineage/canonical_fact_registry"
ACTIVE_POINTER = ".draftpaper/active_canonical_fact_registry.json"


class CanonicalFactError(RuntimeError):
    """Raised when a canonical fact is incomplete or unsafe."""


def _hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def normalize_fact(fact: dict[str, Any], *, source_evidence_ids: Iterable[str] = ()) -> dict[str, Any]:
    if not isinstance(fact, dict):
        raise CanonicalFactError("A canonical fact must be an object.")
    fact_type = str(fact.get("fact_type") or fact.get("type") or "").strip()
    if not fact_type:
        raise CanonicalFactError("Canonical fact requires fact_type.")
    value = fact.get("value")
    identity = {
        "entity_type": str(fact.get("entity_type") or "") or None,
        "cohort_id": str(fact.get("cohort_id") or "") or None,
        "run_id": str(fact.get("run_id") or "") or None,
        "validation_design_id": str(fact.get("validation_design_id") or "") or None,
        "sample_unit": str(fact.get("sample_unit") or "") or None,
    }
    fact_id = str(fact.get("fact_id") or "").strip()
    if not fact_id:
        fact_id = "fact-" + _hash({"fact_type": fact_type, "identity": identity, "label": fact.get("label")})[:20]
    return {
        "fact_id": fact_id,
        "fact_type": fact_type,
        "label": str(fact.get("label") or fact_id),
        "value": value,
        "unit": fact.get("unit"),
        "uncertainty": fact.get("uncertainty"),
        **identity,
        "source_evidence_ids": sorted({str(item) for item in [*source_evidence_ids, *(fact.get("source_evidence_ids") or [])] if str(item).strip()}),
        "valid_from_baseline": fact.get("valid_from_baseline"),
        "superseded_by": fact.get("superseded_by"),
        "allowed_consumers": sorted({str(item) for item in fact.get("allowed_consumers") or []}),
        "must_preserve": bool(fact.get("must_preserve", False)),
        "discipline_adapter_id": fact.get("discipline_adapter_id"),
        "status": str(fact.get("status") or "active"),
    }


def create_fact_registry(
    project: str | Path,
    *,
    facts: Iterable[dict[str, Any]] = (),
    baseline_id: str | None = None,
    revision_cycle_id: str | None = None,
    parent_registry_id: str | None = None,
    source_evidence_ids: Iterable[str] = (),
) -> dict[str, Any]:
    root = project_root(project)
    normalized = [normalize_fact(item, source_evidence_ids=source_evidence_ids) for item in facts]
    normalized.sort(key=lambda item: str(item.get("fact_id")))
    registry_id = "registry-" + _hash({"baseline_id": baseline_id, "revision_cycle_id": revision_cycle_id, "facts": normalized})[:20]
    payload = {
        "schema_version": REGISTRY_SCHEMA,
        "registry_id": registry_id,
        "project_id": _project_id(root),
        "parent_registry_id": parent_registry_id,
        "baseline_id": baseline_id,
        "revision_cycle_id": revision_cycle_id,
        "facts": normalized,
        "created_at": utc_now(),
    }
    payload["registry_sha256"] = _hash(payload)
    path = root / REGISTRY_DIR / f"{registry_id}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8-sig"))
        if existing.get("registry_sha256") != payload["registry_sha256"]:
            raise CanonicalFactError(f"Immutable registry id collision: {registry_id}")
    else:
        atomic_write_json(path, payload)
    pointer = {
        "schema_version": "dpl.active_canonical_fact_registry.v1",
        "registry_id": registry_id,
        "registry_sha256": payload["registry_sha256"],
        "path": str(path.relative_to(root).as_posix()),
        "updated_at": utc_now(),
    }
    atomic_write_json(root / ACTIVE_POINTER, pointer)
    return {"status": "created", "project_path": str(root), "registry": payload, "registry_path": str(path.resolve()), "active_pointer": str((root / ACTIVE_POINTER).resolve())}


def load_fact_registry(project: str | Path, registry_id: str | None = None) -> dict[str, Any] | None:
    root = project_root(project)
    if registry_id:
        path = root / REGISTRY_DIR / f"{registry_id}.json"
        pointer = None
    else:
        pointer_path = root / ACTIVE_POINTER
        if not pointer_path.is_file():
            return None
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return None
        path = root / str(pointer.get("path") or "")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != REGISTRY_SCHEMA:
        return None
    if payload.get("registry_sha256") != _hash({key: value for key, value in payload.items() if key != "registry_sha256"}):
        return None
    if pointer is not None and (
        pointer.get("registry_id") != payload.get("registry_id")
        or pointer.get("registry_sha256") != payload.get("registry_sha256")
    ):
        return None
    return payload


def _project_id(root: Path) -> str | None:
    try:
        payload = json.loads((root / "project.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return str(payload.get("project_id") or "") or None


__all__ = ["ACTIVE_POINTER", "REGISTRY_SCHEMA", "CanonicalFactError", "create_fact_registry", "load_fact_registry", "normalize_fact"]
