"""Atomic run-level evidence bundles.

Outputs from one scientific execution are promoted together.  A failed or
incomplete candidate never replaces the previous active bundle.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .artifact_identity import compute_artifact_identity
from .state_kernel import atomic_write_json


BUNDLE_SCHEMA = "dpl.run_evidence_bundle.v1"
BUNDLE_DIR = "results/run_evidence_bundles"
ACTIVE_POINTER = "results/active_run_evidence_bundle.json"
LATEST_BUNDLE = "results/run_evidence_bundle.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_relative(root: Path, raw: Any) -> str | None:
    text = str(raw or "").replace("\\", "/").strip()
    if not text or "://" in text:
        return None
    candidate = (root / text).resolve()
    try:
        relative = candidate.relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    return relative if relative else None


def _paths(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        raw = value.get("path") if isinstance(value, Mapping) else value
        text = str(raw or "").replace("\\", "/").strip()
        if text and text not in result:
            result.append(text)
    return result


def _artifact_list(root: Path, paths: Iterable[Any], *, role: str) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for raw in _paths(paths):
        relative = _safe_relative(root, raw)
        if not relative:
            artifacts.append({"path": raw, "role": role, "status": "invalid_path"})
            continue
        path = root / relative
        if not path.is_file():
            artifacts.append({"path": relative, "role": role, "status": "missing"})
            continue
        identity = compute_artifact_identity(path, relative)
        artifacts.append({"path": relative, "role": role, "status": "present", "identity": identity})
    return artifacts


def _transaction_id(run_manifest: Mapping[str, Any], *, run_id: str) -> str:
    value = str(
        run_manifest.get("run_transaction_id")
        or run_manifest.get("transaction_id")
        or run_manifest.get("execution_id")
        or run_id
        or "unknown-run"
    ).strip()
    return value or "unknown-run"


def _bundle_hash(payload: Mapping[str, Any]) -> str:
    stable = {key: value for key, value in payload.items() if key not in {"generated_at", "bundle_sha256"}}
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_run_evidence_bundle(
    project: str | Path,
    *,
    metric_identity: Mapping[str, Any] | None = None,
    count_identity: Mapping[str, Any] | None = None,
    figure_trace: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a candidate/validated bundle without changing the active pointer."""

    root = Path(project).expanduser().resolve(strict=True)
    run_manifest = _read_json(root / "methods" / "run_manifest.yaml")
    run_id = str(run_manifest.get("run_id") or run_manifest.get("execution_id") or "").strip()
    transaction_id = _transaction_id(run_manifest, run_id=run_id)
    outputs = run_manifest.get("output_files") or run_manifest.get("declared_outputs") or run_manifest.get("tables_generated") or []
    inputs = run_manifest.get("input_artifacts") or run_manifest.get("input_files") or []
    output_artifacts = _artifact_list(root, outputs, role="output")
    input_artifacts = _artifact_list(root, inputs, role="input")
    missing_outputs = [item for item in output_artifacts if item.get("status") != "present"]
    metric_status = str((metric_identity or {}).get("status") or "not_registered")
    count_status = str((count_identity or {}).get("status") or "not_registered")
    trace_payload = figure_trace or {}
    trace_status = "passed"
    if trace_payload:
        trace_status = "passed" if all(str(item.get("trace_status") or "") == "current" for item in trace_payload.get("traces") or []) else "blocked"
    receipts = [
        {"name": "run_status", "status": "passed" if str(run_manifest.get("status") or "").lower() == "success" else "failed"},
        {"name": "declared_outputs", "status": "passed" if not missing_outputs else "failed", "missing": missing_outputs},
        {"name": "metric_identity", "status": metric_status},
        {"name": "count_identity", "status": count_status},
        {"name": "figure_trace", "status": trace_status},
    ]
    strict_ok = (
        receipts[0]["status"] == "passed"
        and receipts[1]["status"] == "passed"
        and metric_status == "passed"
        and count_status in {"passed", "not_registered"}
        and trace_status == "passed"
    )
    status = "validated" if strict_ok else "candidate" if receipts[0]["status"] == "passed" else "failed"
    payload: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA,
        "run_transaction_id": transaction_id,
        "run_id": run_id,
        "status": status,
        "context": {
            key: run_manifest.get(key)
            for key in (
                "project_id", "plan_hash", "dataset_id", "cohort_id", "cohort_view_id", "task_id",
                "sample_unit", "validation_design_id", "validation_design", "split_id", "evaluation_split",
                "analysis_spec_id", "evidence_snapshot_id",
            )
            if run_manifest.get(key) not in (None, "")
        },
        "producer_fingerprint": run_manifest.get("producer_fingerprint") or {},
        "input_artifacts": input_artifacts,
        "output_artifacts": output_artifacts,
        "metric_record_refs": [str(item.get("metric_record_id")) for item in (metric_identity or {}).get("records") or [] if isinstance(item, dict) and item.get("metric_record_id")],
        "count_record_refs": [str(item.get("count_record_id")) for item in (count_identity or {}).get("records") or [] if isinstance(item, dict) and item.get("count_record_id")],
        "figure_trace_refs": [str(item.get("figure_id")) for item in trace_payload.get("traces") or [] if isinstance(item, dict) and item.get("figure_id")],
        "validation_receipts": receipts,
        "generated_at": generated_at or "",
    }
    payload["bundle_sha256"] = _bundle_hash(payload)
    return payload


def publish_run_evidence_bundle(project: str | Path, bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Write a bundle and atomically promote it only when it is validated."""

    root = Path(project).expanduser().resolve(strict=True)
    transaction_id = str(bundle.get("run_transaction_id") or "unknown-run")
    safe_id = hashlib.sha256(transaction_id.encode("utf-8")).hexdigest()[:24]
    path = root / BUNDLE_DIR / f"{safe_id}.json"
    payload = dict(bundle)
    payload["bundle_path"] = path.relative_to(root).as_posix()
    atomic_write_json(path, payload)
    atomic_write_json(root / LATEST_BUNDLE, payload)
    if str(payload.get("status")) == "validated":
        previous = _read_json(root / ACTIVE_POINTER)
        if previous and previous.get("bundle_sha256") != payload.get("bundle_sha256"):
            previous_receipt = {
                "schema_version": BUNDLE_SCHEMA,
                "status": "superseded",
                "superseded_by": payload.get("bundle_sha256"),
                "previous_bundle_sha256": previous.get("bundle_sha256"),
                "previous_bundle_path": previous.get("bundle_path"),
            }
            atomic_write_json(root / BUNDLE_DIR / f"{previous.get('bundle_sha256', 'unknown')[:24]}-superseded.json", previous_receipt)
        pointer = {
            "schema_version": "dpl.active_run_evidence_pointer.v1",
            "status": "active",
            "run_transaction_id": payload.get("run_transaction_id"),
            "run_id": payload.get("run_id"),
            "bundle_path": payload.get("bundle_path"),
            "bundle_sha256": payload.get("bundle_sha256"),
        }
        atomic_write_json(root / ACTIVE_POINTER, pointer)
        payload["active_pointer_path"] = ACTIVE_POINTER
    else:
        payload["active_pointer_path"] = None
    return payload


def load_active_run_evidence_bundle(project: str | Path) -> dict[str, Any]:
    root = Path(project).expanduser().resolve(strict=True)
    pointer = _read_json(root / ACTIVE_POINTER)
    relative = str(pointer.get("bundle_path") or "")
    if not relative:
        return {"status": "missing", "pointer": pointer}
    bundle = _read_json(root / relative)
    if not bundle:
        return {"status": "stale", "pointer": pointer}
    if bundle.get("bundle_sha256") != pointer.get("bundle_sha256"):
        return {"status": "stale", "pointer": pointer, "bundle": bundle}
    return {"status": "active", "pointer": pointer, "bundle": bundle}
