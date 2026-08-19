"""Hash-bound migration helpers for legacy literature summary indexes."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .literature_identity import canonical_work_id
from .literature_integrity import parse_literature_index
from .literature_repository import write_literature_registry
from .project_scaffold import _write_json
from .project_state import load_project
from .references import (
    _literature_snapshot_hash,
    _write_literature_output_manifest,
    _write_reference_projection_bundle,
    _load_existing_literature_items,
    _set_reference_manifest_outputs,
    normalize_reference_items,
)


PREVIEW_RELATIVE_PATH = "references/literature_migration_preview.json"
RECEIPT_RELATIVE_PATH = "references/literature_migration_receipt.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _packet_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key not in {"packet_hash", "created_at"}}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _copy_tree_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def _as_float(value: Any) -> float | None:
    if value in {None, "", "n/a", "not evaluated", "legacy zero ambiguous"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _column_map(headers: list[str], row: list[str]) -> dict[str, str]:
    return {
        str(header).casefold(): str(row[index]).strip() if index < len(row) else ""
        for index, header in enumerate(headers)
    }


def _existing_match(row: dict[str, str], existing: list[dict[str, Any]]) -> dict[str, Any] | None:
    key = row.get("citation key", "").strip().casefold()
    title = row.get("title", "").strip().casefold()
    for item in existing:
        if key and str(item.get("bibtex_key") or "").strip().casefold() == key:
            return deepcopy(item)
    for item in existing:
        if title and str(item.get("title") or "").strip().casefold() == title:
            return deepcopy(item)
    return None


def _source_records(row: dict[str, str]) -> list[dict[str, Any]]:
    records = []
    for source in (part.strip() for part in row.get("source categories", "").split(",")):
        if source:
            records.append({
                "source_type": source,
                "provider": source if source not in {"manual", "unknown"} else "",
                "logical_locator": row.get("local locator") or "legacy_index.html",
                "retention_policy": row.get("retention") or "legacy_preserved",
            })
    return records or [{"source_type": row.get("origin") or "legacy_index", "logical_locator": "legacy_index.html"}]


def _legacy_item(row: dict[str, str], existing: dict[str, Any] | None, index: int) -> dict[str, Any]:
    item = existing or {
        "title": row.get("title") or f"Legacy literature item {index + 1}",
        "authors": [],
        "year": "",
        "abstract": "",
        "publication": "",
    }
    item["title"] = item.get("title") or row.get("title") or f"Legacy literature item {index + 1}"
    item["bibtex_key"] = item.get("bibtex_key") or row.get("citation key") or f"legacy{index + 1}"
    item["source_records"] = list(item.get("source_records") or []) + _source_records(row)
    item["reference_origin"] = item.get("reference_origin") or row.get("origin") or "legacy_index"
    item["selection_policy"] = item.get("selection_policy") or row.get("retention") or "legacy_preserved"
    item["pdf_read_status"] = item.get("pdf_read_status") or row.get("pdf/parser") or "not_parsed"
    item["candidate_state"] = item.get("candidate_state") or row.get("candidate state") or "legacy_imported"
    contexts = [part.strip() for part in row.get("context", "").split(",") if part.strip()]
    if contexts:
        item["search_contexts"] = sorted(set([*(item.get("search_contexts") or []), *contexts]))
        item["search_context"] = item.get("search_context") or contexts[0]
    if row.get("zotero collection") and row.get("zotero collection") != "n/a":
        item["zotero_collection"] = item.get("zotero_collection") or row["zotero collection"]

    # A legacy table cannot prove that a zero was calculated under the current
    # score contract. Preserve the fact that the cell was zero, but make its
    # interpretation explicit and non-computable until an authorized rerun.
    statuses = dict(item.get("score_status") or {})
    provenance = dict(item.get("score_provenance") or {})
    for field, column in (
        ("citation_weight", "citation weight"),
        ("relevance_score", "relevance"),
        ("journal_score", "journal authority"),
    ):
        observed = _as_float(row.get(column))
        existing_value = _as_float(item.get(field))
        if (observed == 0.0 or existing_value == 0.0 or row.get(column) == "legacy zero ambiguous") and not provenance and not item.get("score_context_hash"):
            item[field] = None
            statuses[field] = "legacy_zero_ambiguous"
        elif existing_value is not None:
            item[field] = existing_value
            statuses.setdefault(field, "legacy_preserved")
        elif observed is not None:
            item[field] = observed
            statuses[field] = "legacy_preserved"
        else:
            item[field] = None
            statuses[field] = "not_evaluated"
    item["score_status"] = statuses
    item["score_provenance"] = provenance
    item["legacy_migration"] = {
        "source": "literature_summaries/index.html",
        "row_number": index + 1,
        "score_interpretation": "legacy_zero_ambiguous" if any(statuses.get(field) == "legacy_zero_ambiguous" for field in ("citation_weight", "relevance_score", "journal_score")) else "preserved",
    }
    item["work_id"] = str(item.get("work_id") or canonical_work_id(item))
    item["canonical_work_id"] = item["work_id"]
    return item


def _migration_items(project_root: Path, index_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parsed = parse_literature_index(index_path)
    if parsed.get("status") != "parsed":
        raise ValueError(f"Legacy literature index is {parsed.get('status')}: {index_path}")
    existing = _load_existing_literature_items(project_root / "references")
    headers = list(parsed.get("headers") or [])
    rows = list(parsed.get("rows") or [])
    items = normalize_reference_items([
        _legacy_item(_column_map(headers, row), _existing_match(_column_map(headers, row), existing), index)
        for index, row in enumerate(rows)
    ])
    legacy_zero_count = sum(
        1
        for item in items
        if any((item.get("score_status") or {}).get(field) == "legacy_zero_ambiguous" for field in ("citation_weight", "relevance_score", "journal_score"))
    )
    parser_counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("pdf_read_status") or "not_parsed")
        parser_counts[status] = parser_counts.get(status, 0) + 1
    return items, {
        "index_sha256": _sha256(index_path),
        "index_row_count": len(rows),
        "existing_item_count": len(existing),
        "proposed_item_count": len(items),
        "legacy_zero_ambiguous_count": legacy_zero_count,
        "pdf_status_counts": parser_counts,
    }


def build_literature_migration_preview(
    project: str | Path,
    *,
    index: str | Path | None = None,
) -> dict[str, Any]:
    state = load_project(project)
    index_path = Path(index).expanduser().resolve() if index else state.path / "references" / "literature_summaries" / "index.html"
    items, counts = _migration_items(state.path, index_path)
    snapshot = _read_json(state.path / "references" / "literature_snapshot.json", {})
    payload: dict[str, Any] = {
        "schema_version": "dpl.literature_migration_preview.v1",
        "project_path": str(state.path),
        "source_index": "references/literature_summaries/index.html" if index is None else str(index_path),
        "before_snapshot_hash": snapshot.get("snapshot_hash"),
        "mode": "local_only_no_network_no_reparse",
        "counts": counts,
        "work_ids": [str(item.get("work_id") or "") for item in items],
        "items": items,
    }
    payload["packet_hash"] = _packet_hash(payload)
    payload["created_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(state.path / PREVIEW_RELATIVE_PATH, payload)
    return {
        "status": "preview",
        "preview": PREVIEW_RELATIVE_PATH,
        "packet_hash": payload["packet_hash"],
        **counts,
    }


def migrate_literature_index(
    project: str | Path,
    *,
    index: str | Path | None = None,
    apply: bool = False,
    packet_hash: str | None = None,
) -> dict[str, Any]:
    preview = build_literature_migration_preview(project, index=index)
    if not apply:
        return preview
    return apply_literature_migration(project, packet_hash=packet_hash or str(preview["packet_hash"]))


def _write_migrated_outputs(root: Path, items: list[dict[str, Any]], packet_hash: str) -> dict[str, Any]:
    references = root / "references"
    references.mkdir(parents=True, exist_ok=True)
    search_queries = _read_json(references / "search_queries.json", {})
    snapshot_hash = _literature_snapshot_hash(items, search_queries)
    snapshot_payload = {
        "schema_version": "dpl.literature_snapshot.v2",
        "snapshot_hash": snapshot_hash,
        "merge_mode": "legacy_migration",
        "item_count": len(items),
        "baseline_count": len(items),
        "incoming_count": 0,
        "migration_packet_hash": packet_hash,
        "work_ids": [str(item.get("work_id") or "") for item in items],
    }
    _write_json(references / "literature_merge_report.json", {
        "schema_version": "dpl.literature_merge_report.v1",
        "status": "migrated",
        "merge_mode": "legacy_migration",
        "baseline_count": len(items),
        "incoming_count": 0,
        "final_count": len(items),
        "preserved_work_ids": [str(item.get("work_id") or "") for item in items],
        "dropped_work_ids": [],
        "snapshot_hash": snapshot_hash,
        "migration_packet_hash": packet_hash,
    })
    projection = _write_reference_projection_bundle(
        references,
        items,
        snapshot_hash=snapshot_hash,
        query=str(search_queries.get("idea") or ""),
        snapshot_payload=snapshot_payload,
    )
    items = projection["items"]
    outputs = projection["html_outputs"]
    from .bibliography import build_reference_registry
    build_reference_registry(root)
    registry = write_literature_registry(root, items)
    _set_reference_manifest_outputs(root)
    manifest = _write_literature_output_manifest(references, snapshot_hash)
    return {"snapshot_hash": snapshot_hash, "outputs": outputs, "registry": registry, "manifest": manifest}


def apply_literature_migration(project: str | Path, *, packet_hash: str) -> dict[str, Any]:
    state = load_project(project)
    preview_path = state.path / PREVIEW_RELATIVE_PATH
    payload = _read_json(preview_path, {})
    if not isinstance(payload, dict) or payload.get("packet_hash") != packet_hash or _packet_hash(payload) != packet_hash:
        raise ValueError("Literature migration preview hash does not match the current preview.")
    references = state.path / "references"
    backup_root = state.path / ".draftpaper" / "literature_migration_backups" / packet_hash.removeprefix("sha256:")[:16]
    backup = backup_root / "references"
    if backup_root.exists():
        raise ValueError("A migration backup for this packet already exists; refusing to overwrite it.")
    backup_root.mkdir(parents=True, exist_ok=True)
    _copy_tree_contents(references, backup)
    try:
        result = _write_migrated_outputs(state.path, [dict(item) for item in payload.get("items") or []], packet_hash)
    except Exception:
        if references.exists():
            shutil.rmtree(references)
        shutil.copytree(backup, references, dirs_exist_ok=True)
        receipt = {
            "schema_version": "dpl.literature_migration_receipt.v1",
            "status": "rolled_back",
            "packet_hash": packet_hash,
            "rollback_reason": "apply_failed",
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(state.path / RECEIPT_RELATIVE_PATH, receipt)
        raise
    receipt = {
        "schema_version": "dpl.literature_migration_receipt.v1",
        "status": "applied",
        "packet_hash": packet_hash,
        "snapshot_hash": result["snapshot_hash"],
        "source_index": payload.get("source_index"),
        "counts": payload.get("counts") or {},
        "rollback_archive": backup_root.relative_to(state.path).as_posix(),
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "rollback_available": True,
    }
    _write_json(state.path / RECEIPT_RELATIVE_PATH, receipt)
    return {"status": "applied", "receipt": RECEIPT_RELATIVE_PATH, **result, "item_count": len(payload.get("items") or [])}


def rollback_literature_migration(project: str | Path, *, receipt: str | Path | None = None) -> dict[str, Any]:
    """Restore the pre-migration reference tree from the migration archive."""
    state = load_project(project)
    receipt_path = state.path / (receipt or RECEIPT_RELATIVE_PATH)
    payload = _read_json(receipt_path, {})
    archive = state.path / str(payload.get("rollback_archive") or "")
    if not archive.is_dir():
        raise ValueError("Migration rollback archive is unavailable; no destructive rollback is attempted.")
    current_snapshot = _read_json(state.path / "references" / "literature_snapshot.json", {})
    if current_snapshot.get("snapshot_hash") != payload.get("snapshot_hash"):
        raise ValueError("Migration rollback is blocked because the current literature snapshot has changed.")
    references = state.path / "references"
    restored = archive / "references"
    temporary = Path(tempfile.mkdtemp(prefix="literature-rollback-")) / "references"
    _copy_tree_contents(references, temporary)
    try:
        shutil.rmtree(references)
        _copy_tree_contents(restored, references)
    except Exception:
        if references.exists():
            shutil.rmtree(references)
        _copy_tree_contents(temporary, references)
        raise
    shutil.rmtree(temporary.parent, ignore_errors=True)
    payload = {**payload, "status": "rolled_back", "rolled_back_at": datetime.now(timezone.utc).isoformat()}
    _write_json(receipt_path, payload)
    return {"status": "rolled_back", "receipt": receipt_path.relative_to(state.path).as_posix(), "restored_from": archive.relative_to(state.path).as_posix()}
