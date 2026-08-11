"""Immutable scientific baseline bundles and active pointers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json
from .canonical_fact_registry import create_fact_registry, load_fact_registry
from .passport import collect_artifacts, project_root, utc_now
from .state_kernel import atomic_write_json


BASELINE_SCHEMA = "dpl.scientific_baseline_bundle.v1"
BASELINE_DIR = "lineage/scientific_baselines"
ACTIVE_POINTER = ".draftpaper/active_scientific_baseline.json"


class ScientificBaselineError(RuntimeError):
    """Raised when an immutable scientific baseline cannot be created."""


def _hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _read_json(root: Path, relative: str) -> dict[str, Any]:
    try:
        payload = json.loads((root / relative).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def create_scientific_baseline(
    project: str | Path,
    *,
    decision_receipt_id: str | None = None,
    revision_cycle_id: str | None = None,
    reason: str = "checkpoint_review",
    facts: list[dict[str, Any]] | None = None,
    registry_id: str | None = None,
) -> dict[str, Any]:
    root = project_root(project)
    parent = load_active_baseline(root)
    parent_id = str(parent.get("baseline_id")) if parent else None
    registry = load_fact_registry(root, registry_id) if registry_id else load_fact_registry(root)
    if facts is not None:
        registry_result = create_fact_registry(root, facts=facts, baseline_id=None, revision_cycle_id=revision_cycle_id, parent_registry_id=(registry or {}).get("registry_id"))
        registry = registry_result["registry"]
    artifact_hashes = {
        str(item.get("path")): str(item.get("evidence_sha256") or item.get("semantic_sha256") or item.get("byte_sha256") or item.get("sha256"))
        for item in collect_artifacts(root)
        if item.get("path")
    }
    project_payload = _read_json(root, "project.json")
    plan_hash = _first_from_project(root, ("research_plan/research_plan_hash.json", "research_plan/research_plan.json"), ("plan_hash", "research_plan_hash"))
    claim_hash = _first_from_project(root, ("research_plan/claim_contract.json",), ("claim_contract_hash", "contract_hash"))
    run_id = _first_from_project(root, ("methods/run_manifest.yaml", "methods/run_manifest.json"), ("run_id", "resolved_run_id"))
    core = {
        "project_id": project_payload.get("project_id"),
        "parent_baseline_id": parent_id,
        "revision_cycle_id": revision_cycle_id,
        "plan_hash": plan_hash,
        "claim_contract_hash": claim_hash,
        "data_contract_hash": _first_from_project(root, ("data/formal_data_run_binding.json", "data/data_contract.json"), ("data_contract_hash", "contract_hash")),
        "cohort_and_split_identity": _identity_from_files(root, ("data/formal_data_run_binding.json", "results/metric_identity_report.json")),
        "method_contract_hash": _first_from_project(root, ("methods/method_plan.json", "methods/method_contract.json"), ("method_contract_hash", "contract_hash")),
        "active_run_bundle_id": run_id,
        "evidence_snapshot_id": _first_from_project(root, ("results/promoted_evidence_snapshot.json", "core_evidence/core_evidence_report.json"), ("snapshot_id", "promoted_evidence_snapshot_id", "evidence_snapshot_id")),
        "figure_trace_set_hash": _first_from_project(root, ("results/figure_code_trace.json",), ("trace_set_hash", "figure_trace_set_hash")),
        "canonical_fact_registry_id": (registry or {}).get("registry_id"),
        "reference_work_set_hash": _first_from_project(root, ("references/reference_registry.json", "references/literature_registry.json"), ("work_set_hash", "reference_work_set_hash")),
        "manuscript_snapshot_id": _first_from_project(root, ("latex/manuscript_snapshot.json", "writing/manuscript_snapshot.json"), ("snapshot_id", "manuscript_snapshot_id")),
        "decision_receipt_id": decision_receipt_id,
        "runtime_fingerprint": _first_from_project(root, (".draftpaper/runtime_lock.json",), ("runtime_fingerprint", "source_commit")),
        "artifact_hashes": artifact_hashes,
        "reason": reason,
        "created_at": utc_now(),
    }
    baseline_id = "baseline-" + _hash(core)[:20]
    payload = {"schema_version": BASELINE_SCHEMA, "baseline_id": baseline_id, **core}
    payload["baseline_sha256"] = _hash(payload)
    path = root / BASELINE_DIR / f"{baseline_id}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8-sig"))
        if existing.get("baseline_sha256") != payload["baseline_sha256"]:
            raise ScientificBaselineError(f"Immutable baseline id collision: {baseline_id}")
    else:
        atomic_write_json(path, payload)
    pointer = {
        "schema_version": "dpl.active_scientific_baseline.v1",
        "baseline_id": baseline_id,
        "baseline_sha256": payload["baseline_sha256"],
        "path": str(path.relative_to(root).as_posix()),
        "updated_at": utc_now(),
    }
    atomic_write_json(root / ACTIVE_POINTER, pointer)
    return {"status": "created", "project_path": str(root), "baseline": payload, "baseline_path": str(path.resolve()), "active_pointer": str((root / ACTIVE_POINTER).resolve())}


def load_active_baseline(project: str | Path) -> dict[str, Any] | None:
    root = project_root(project)
    pointer_path = root / ACTIVE_POINTER
    if not pointer_path.is_file():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8-sig"))
        path = (root / str(pointer.get("path") or "")).resolve()
        path.relative_to(root.resolve())
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != BASELINE_SCHEMA:
        return None
    if payload.get("baseline_sha256") != _hash({key: value for key, value in payload.items() if key != "baseline_sha256"}):
        return None
    if pointer.get("baseline_id") != payload.get("baseline_id") or pointer.get("baseline_sha256") != payload.get("baseline_sha256"):
        return None
    return payload


def show_scientific_baseline(project: str | Path, *, baseline_id: str | None = None) -> dict[str, Any]:
    root = project_root(project)
    payload = load_active_baseline(root) if not baseline_id else _load_baseline(root, baseline_id)
    if not payload:
        return {"status": "not_found", "project_path": str(root)}
    path = root / BASELINE_DIR / f"{payload['baseline_id']}.json"
    return {"status": "passed", "project_path": str(root), "baseline": payload, "baseline_path": str(path.resolve()), "active": load_active_baseline(root) == payload}


def _load_baseline(root: Path, baseline_id: str) -> dict[str, Any] | None:
    try:
        payload = json.loads((root / BASELINE_DIR / f"{baseline_id}.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != BASELINE_SCHEMA:
        return None
    return payload if payload.get("baseline_sha256") == _hash({key: value for key, value in payload.items() if key != "baseline_sha256"}) else None


def _first_from_project(root: Path, paths: tuple[str, ...], keys: tuple[str, ...]) -> str | None:
    for relative in paths:
        path = root / relative
        if not path.is_file():
            continue
        if path.suffix.lower() in {".yaml", ".yml"}:
            for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                for key in keys:
                    if line.strip().startswith(key + ":"):
                        value = line.split(":", 1)[1].strip().strip("'\"")
                        if value:
                            return value
            continue
        payload = _read_json(root, relative)
        found = _find_scalar(payload, set(keys))
        if found:
            return found
    return None


def _find_scalar(payload: Any, keys: set[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) in keys and isinstance(value, (str, int, float, bool)):
                return str(value)
        for value in payload.values():
            found = _find_scalar(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_scalar(value, keys)
            if found:
                return found
    return None


def _identity_from_files(root: Path, paths: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for relative in paths:
        payload = _read_json(root, relative)
        for key in ("cohort_id", "cohort", "sample_unit", "validation_design", "split", "model_id", "run_id"):
            value = _find_scalar(payload, {key})
            if value and key not in result:
                result[key] = value
    return result


__all__ = ["ACTIVE_POINTER", "BASELINE_SCHEMA", "ScientificBaselineError", "create_scientific_baseline", "load_active_baseline", "show_scientific_baseline"]
