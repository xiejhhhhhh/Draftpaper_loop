"""Hash-bound output binding receipts for existing scientific artifacts.

The receipt is deliberately separate from the output file and from the
generated evidence registry.  It records how an already-produced artifact is
bound to a run/analysis contract without rewriting the artifact or inventing a
new scientific run.
"""

from __future__ import annotations

import hashlib
import csv
import json
import re
import uuid
from pathlib import Path
from typing import Any

from .evidence_registry import REQUIRED_BINDING_FIELDS, _finalize_binding, _normalize_record
from .io_utils import read_json_object
from .loop_contract import stable_evidence_id
from .passport import project_root, utc_now
from .state_kernel import StateKernelError, append_jsonl_locked, atomic_write_json


BINDING_SCHEMA = "dpl.evidence_binding_packet.v1"
RECEIPT_SCHEMA = "dpl.evidence_binding_receipt.v1"
BINDING_DIR = "review/evidence_bindings"
RECEIPT_DIR = "results/evidence_binding_receipts"
RECEIPT_LEDGER = f"{RECEIPT_DIR}/receipt_ledger.jsonl"


class EvidenceBindingError(RuntimeError):
    """Raised when an output binding cannot be verified without guessing."""


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = read_json_object(path)
    except (OSError, StateKernelError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_pointer(payload: Any, pointer: str) -> Any:
    """Resolve a small RFC 6901 JSON pointer without guessing missing values."""
    if pointer == "":
        return payload
    if not pointer.startswith("/"):
        legacy = re.fullmatch(r"rows\[(\d+)\]\.([A-Za-z0-9_.-]+)", pointer)
        if legacy:
            index, field = int(legacy.group(1)), legacy.group(2)
            if isinstance(payload, dict) and isinstance(payload.get("rows"), list) and index < len(payload["rows"]):
                row = payload["rows"][index]
                if isinstance(row, dict) and field in row:
                    return row[field]
            # Older Draftpaper fixtures used the row-shaped locator for a
            # flattened JSON metric object.  Preserve that read-compatible
            # route while still checking the actual value.
            if index == 0 and isinstance(payload, dict) and field in payload:
                return payload[field]
        raise EvidenceBindingError(f"source_locator_invalid: JSON pointer must start with '/': {pointer}")
    current = payload
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise EvidenceBindingError(f"source_value_unavailable: locator does not resolve: {pointer}")
    return current


def _values_match(expected: Any, actual: Any, tolerance: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        try:
            epsilon = float(tolerance or 0.0)
            return abs(float(expected) - float(actual)) <= max(epsilon, epsilon * max(abs(float(expected)), abs(float(actual)), 1.0))
        except (TypeError, ValueError):
            return False
    return expected == actual


def _coerce_source_value(value: Any, expected: Any) -> Any:
    if isinstance(expected, bool):
        return str(value).strip().lower() in {"true", "1", "yes"} if isinstance(value, str) else bool(value)
    if isinstance(expected, int) and not isinstance(expected, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if isinstance(expected, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value


def _verify_source_value(path: Path, *, locator: Any, expected: Any, tolerance: Any) -> dict[str, Any]:
    if not locator:
        return {"status": "not_requested"}
    if isinstance(locator, dict):
        kind = str(locator.get("kind") or "json_pointer")
        if kind == "json_pointer":
            pointer = str(locator.get("pointer") or "")
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                raise EvidenceBindingError(f"source_value_unavailable: cannot parse {path.name}: {exc}") from exc
            actual = _json_pointer(payload, pointer)
            resolved_locator = pointer
        elif kind in {"csv_row", "tsv_row"}:
            if path.suffix.lower() not in {".csv", ".tsv"}:
                raise EvidenceBindingError(f"source_locator_invalid: {kind} requires CSV/TSV: {path.name}")
            key_columns = locator.get("key_columns") or locator.get("keys")
            value_column = str(locator.get("value_column") or locator.get("column") or "")
            if not isinstance(key_columns, dict) or not value_column:
                raise EvidenceBindingError("source_locator_invalid: CSV locator needs key_columns and value_column")
            delimiter = "\t" if kind == "tsv_row" or path.suffix.lower() == ".tsv" else ","
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle, delimiter=delimiter))
            except (OSError, csv.Error) as exc:
                raise EvidenceBindingError(f"source_value_unavailable: cannot parse {path.name}: {exc}") from exc
            matches = [row for row in rows if all(str(row.get(key, "")) == str(value) for key, value in key_columns.items())]
            if len(matches) != 1:
                raise EvidenceBindingError(
                    f"source_locator_invalid: expected one CSV row for keys, found {len(matches)}"
                )
            if value_column not in matches[0]:
                raise EvidenceBindingError(f"source_value_unavailable: column does not exist: {value_column}")
            actual = _coerce_source_value(matches[0][value_column], expected)
            resolved_locator = {"kind": kind, "key_columns": dict(key_columns), "value_column": value_column}
        else:
            raise EvidenceBindingError(f"source_locator_invalid: unsupported locator kind: {kind}")
    else:
        if path.suffix.lower() != ".json":
            raise EvidenceBindingError(
                f"source_value_unavailable: source locator validation currently requires JSON: {path.name}"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise EvidenceBindingError(f"source_value_unavailable: cannot parse {path.name}: {exc}") from exc
        actual = _json_pointer(payload, str(locator))
        resolved_locator = str(locator)
    if not _values_match(expected, actual, tolerance):
        raise EvidenceBindingError(
            f"source_value_mismatch: {locator} declares {expected!r}, but source contains {actual!r}"
        )
    return {
        "status": "verified",
        "locator": resolved_locator,
        "actual_value": actual,
        "tolerance": float(tolerance or 0.0),
    }


def _verify_source_identity(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Cross-check optional run-contract fields when the source records them."""
    if path.suffix.lower() != ".json":
        return {"status": "not_evaluated", "reason": "source_identity_schema_not_json"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise EvidenceBindingError(f"source_identity_unavailable: cannot parse {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        return {"status": "not_evaluated", "reason": "source_identity_not_object"}
    compared: dict[str, str] = {}
    for field in ("run_id", "analysis_spec_id", "cohort_view_id", "split_id", "model_id", "metric_dimension", "unit"):
        source_value = payload.get(field)
        declared_value = record.get(field)
        if source_value is None or declared_value in (None, ""):
            continue
        if str(source_value) != str(declared_value):
            raise EvidenceBindingError(
                f"source_identity_mismatch: {field} declares {declared_value!r}, but source contains {source_value!r}"
            )
        compared[field] = str(source_value)
    return {"status": "verified" if compared else "not_evaluated", "compared": compared}


def _relative_file(root: Path, raw: Any) -> tuple[str, Path]:
    relative = str(raw or "").replace("\\", "/").strip()
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise EvidenceBindingError(f"Binding artifact must be a project-relative path: {raw}")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise EvidenceBindingError("Binding artifact escapes the project root.") from exc
    if not path.is_file():
        raise EvidenceBindingError(f"Binding artifact does not exist: {relative}")
    return relative, path


def _binding_rows(root: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_rows = payload.get("bindings")
    if raw_rows is None:
        raw_rows = payload.get("records")
    if raw_rows is None:
        raw_rows = [payload]
    if not isinstance(raw_rows, list) or not raw_rows:
        raise EvidenceBindingError("Binding input must contain a non-empty bindings list.")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows, start=1):
        if not isinstance(raw, dict):
            raise EvidenceBindingError(f"Binding row {index} is not an object.")
        relative, path = _relative_file(root, raw.get("source_artifact") or raw.get("artifact"))
        actual_hash = _sha256(path)
        expected_hash = str(raw.get("source_hash") or raw.get("artifact_sha256") or "").strip()
        if expected_hash and expected_hash != actual_hash:
            raise EvidenceBindingError(
                f"Binding hash mismatch for {relative}: expected {expected_hash}, current {actual_hash}."
            )
        record = dict(raw)
        record["source_artifact"] = relative
        record["source_hash"] = actual_hash
        if not record.get("evidence_id"):
            scope = "|".join(
                str(record.get(key) or "")
                for key in ("entity_role", "run_id", "analysis_spec_id", "model_id", "split_id", "metric_dimension")
            )
            record["evidence_id"] = stable_evidence_id(
                "output_binding",
                title=f"{relative}|{actual_hash}|{scope}|{index}",
                sequence=index,
            )
        normalized = _normalize_record(record, source_artifact=relative, source_hash=actual_hash)
        if normalized is None:
            raise EvidenceBindingError(f"Binding row {index} is missing entity_role or value.")
        normalized["binding_source"] = "output_binding_receipt"
        normalized["binding_row"] = index
        normalized["source_locator"] = raw.get("source_locator") or raw.get("row_locator") or None
        normalized["source_value_verification"] = _verify_source_value(
            path,
            locator=normalized["source_locator"],
            expected=normalized.get("value"),
            tolerance=raw.get("value_tolerance") or raw.get("tolerance") or 0.0,
        )
        normalized["source_identity_verification"] = _verify_source_identity(path, normalized)
        _finalize_binding(normalized)
        missing = [field for field in REQUIRED_BINDING_FIELDS if not str(normalized.get(field) or "").strip()]
        if missing:
            raise EvidenceBindingError(
                f"Binding row {index} is incomplete; missing required identity fields: {', '.join(missing)}"
            )
        rows.append(normalized)
    return rows


def inspect_evidence_bindings(project: str | Path) -> dict[str, Any]:
    """Read the current registry and receipts without mutating the project."""
    root = project_root(project)
    registry = _read(root / "writing/scientific_evidence_registry.json")
    receipts: list[dict[str, Any]] = []
    receipt_root = root / RECEIPT_DIR
    if receipt_root.is_dir():
        for path in sorted(receipt_root.glob("*.json")):
            if path.name == "index.json":
                continue
            payload = _read(path)
            if payload.get("schema_version") == RECEIPT_SCHEMA:
                receipts.append(payload)
    incomplete = [
        item for item in registry.get("records") or []
        if isinstance(item, dict) and not item.get("binding_complete", False)
    ]
    stale: list[dict[str, Any]] = []
    for receipt in receipts:
        for binding in receipt.get("bindings") or []:
            try:
                relative, path = _relative_file(root, binding.get("source_artifact"))
                current_hash = _sha256(path)
            except EvidenceBindingError as exc:
                stale.append({"receipt_id": receipt.get("receipt_id"), "reason": str(exc)})
                continue
            if current_hash != str(binding.get("source_hash") or ""):
                stale.append({
                    "receipt_id": receipt.get("receipt_id"),
                    "source_artifact": relative,
                    "reason": "source_artifact_hash_changed",
                    "current_hash": current_hash,
                    "receipt_hash": binding.get("source_hash"),
                })
    return {
        "status": "ready" if not incomplete and not stale and registry else "repair_required",
        "project_path": str(root),
        "registry_path": str((root / "writing/scientific_evidence_registry.json").resolve()),
        "registry_status": registry.get("status") if registry else "missing",
        "record_count": int(registry.get("record_count") or 0) if registry else 0,
        "incomplete_binding_count": len(incomplete),
        "incomplete_binding_evidence_ids": [item.get("evidence_id") for item in incomplete],
        "receipt_count": len(receipts),
        "stale_receipt_count": len(stale),
        "stale_receipts": stale,
        "next_action": None if not incomplete and not stale else "prepare-evidence-rebind",
    }


def prepare_evidence_rebind(project: str | Path, *, binding_file: str) -> dict[str, Any]:
    """Create an immutable binding preview from a user-supplied JSON packet."""
    root = project_root(project)
    source = Path(binding_file).expanduser().resolve()
    if not source.is_file():
        raise EvidenceBindingError(f"Binding input file does not exist: {source}")
    payload = _read(source)
    rows = _binding_rows(root, payload)
    packet = {
        "schema_version": BINDING_SCHEMA,
        "packet_id": "binding-packet-" + uuid.uuid4().hex,
        "project_id": _read(root / "project.json").get("project_id"),
        "source_input_sha256": _sha256(source),
        "bindings": rows,
        "created_at": utc_now(),
        "policy": "A receipt binds existing bytes to an explicitly supplied run contract; it never changes the artifact or creates a scientific run.",
    }
    packet["packet_sha256"] = _hash(packet)
    output_dir = root / BINDING_DIR / packet["packet_id"]
    packet_path = output_dir / "binding_packet.json"
    atomic_write_json(packet_path, packet)
    return {
        "status": "prepared",
        "project_path": str(root),
        "packet_id": packet["packet_id"],
        "packet_hash": packet["packet_sha256"],
        "packet_path": str(packet_path.resolve()),
        "binding_count": len(rows),
        "release_eligible": False,
    }


def validate_binding_sources(project: str | Path, bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate source locators without creating a packet or receipt."""
    root = project_root(project)
    rows = _binding_rows(root, {"bindings": bindings})
    return [
        {
            "evidence_id": row.get("evidence_id"),
            "source_artifact": row.get("source_artifact"),
            "source_value_verification": row.get("source_value_verification"),
            "source_identity_verification": row.get("source_identity_verification"),
            "status": "passed",
        }
        for row in rows
    ]
def apply_evidence_rebind(project: str | Path, *, packet_path: str, packet_hash: str) -> dict[str, Any]:
    """Apply a hash-bound receipt only when the preview still matches files."""
    root = project_root(project)
    path = Path(packet_path).expanduser().resolve()
    try:
        path.relative_to((root / BINDING_DIR).resolve())
    except ValueError as exc:
        raise EvidenceBindingError("Binding packet must be inside the project binding directory.") from exc
    packet = _read(path)
    if packet.get("schema_version") != BINDING_SCHEMA or packet.get("packet_sha256") != packet_hash:
        raise EvidenceBindingError("Binding packet hash does not match its immutable preview.")
    packet_body = {key: value for key, value in packet.items() if key != "packet_sha256"}
    if _hash(packet_body) != packet_hash:
        raise EvidenceBindingError("Binding packet content digest is invalid.")
    rows = _binding_rows(root, {"bindings": packet.get("bindings") or []})
    if _hash(rows) != _hash(packet.get("bindings") or []):
        raise EvidenceBindingError("Binding packet rows changed after preparation.")
    receipt_id = "binding-receipt-" + uuid.uuid4().hex
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "receipt_id": receipt_id,
        "packet_id": packet.get("packet_id"),
        "packet_sha256": packet_hash,
        "project_id": packet.get("project_id"),
        "bindings": rows,
        "status": "applied",
        "applied_at": utc_now(),
        "policy": "This receipt preserves the existing scientific run identity and records only a verified artifact-to-contract binding.",
    }
    receipt["receipt_sha256"] = _hash(receipt)
    receipt_path = root / RECEIPT_DIR / f"{receipt_id}.json"
    atomic_write_json(receipt_path, receipt)
    append_jsonl_locked(root / RECEIPT_LEDGER, {
        "schema_version": RECEIPT_SCHEMA,
        "receipt_id": receipt_id,
        "packet_sha256": packet_hash,
        "status": "applied",
        "created_at": receipt["applied_at"],
        "path": receipt_path.relative_to(root).as_posix(),
    })
    from .evidence_registry import build_scientific_evidence_registry

    registry = build_scientific_evidence_registry(root)
    binding_ready = not any(
        int(registry.get(field) or 0)
        for field in (
            "incomplete_binding_count",
            "binding_receipt_stale_count",
            "binding_receipt_invalid_count",
            "blocking_conflict_count",
        )
    ) and registry.get("status") == "ready"
    return {
        "status": "applied",
        "project_path": str(root),
        "receipt_id": receipt_id,
        "receipt_path": str(receipt_path.resolve()),
        "receipt_hash": receipt["receipt_sha256"],
        "binding_count": len(rows),
        "registry_status": registry.get("status"),
        "binding_ready": binding_ready,
        "release_eligible": False,
        "release_eligibility_scope": "local_binding_only",
    }


__all__ = [
    "BINDING_DIR",
    "RECEIPT_DIR",
    "EvidenceBindingError",
    "apply_evidence_rebind",
    "inspect_evidence_bindings",
    "prepare_evidence_rebind",
    "validate_binding_sources",
]
