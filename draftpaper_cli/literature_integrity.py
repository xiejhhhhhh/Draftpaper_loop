"""Read-only literature identity, score and full-text reachability audits."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .literature_identity import canonical_work_id
from .literature_scoring import identify_legacy_zero_scores, score_state_counts
from .project_scaffold import _write_json
from .project_state import load_project
from .references import _load_existing_literature_items


REPORT_RELATIVE_PATH = "references/literature_integrity_report.json"
ORPHAN_REPORT_RELATIVE_PATH = "references/orphan_literature_artifacts.json"
OUTPUT_MANIFEST_RELATIVE_PATH = "references/literature_output_manifest.json"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _json_payload(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, (dict, list)) else None


def _artifact_work_ids(payload: Any) -> set[str]:
    found: set[str] = set()
    values = payload if isinstance(payload, list) else [payload]
    for value in values:
        if not isinstance(value, dict):
            continue
        for key in ("work_id", "canonical_work_id"):
            if value.get(key):
                found.add(str(value[key]))
        record = value.get("record")
        if isinstance(record, dict) and record.get("work_id"):
            found.add(str(record["work_id"]))
    return found


def _artifact_identifiers(payload: Any) -> set[str]:
    found: set[str] = set()
    values = payload if isinstance(payload, list) else [payload]
    for value in values:
        if not isinstance(value, dict):
            continue
        for key in ("doi", "pmid", "pmcid", "arxiv_id", "bibcode", "openalex_id"):
            if value.get(key):
                found.add(f"{key}:{str(value[key]).strip().casefold().removeprefix('https://doi.org/')}")
        record = value.get("record")
        if isinstance(record, dict):
            found.update(_artifact_identifiers(record))
    return found


def _item_identifiers(item: dict[str, Any]) -> set[str]:
    return _artifact_identifiers(item)


def _snapshot_markers(path: Path) -> set[str]:
    """Extract snapshot markers without interpreting scientific content."""
    if not path.is_file():
        return set()
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = _json_payload(path)
        markers: set[str] = set()
        values = payload if isinstance(payload, list) else [payload]
        for value in values:
            if isinstance(value, dict):
                marker = str(value.get("snapshot_hash") or "").strip()
                if marker:
                    markers.add(marker)
        return markers
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return set()
    if suffix == ".bib":
        matches = re.findall(r"^%\s*Draftpaper-literature-snapshot:\s*(\S+)", text, flags=re.MULTILINE)
    elif suffix == ".md":
        matches = re.findall(r"^Snapshot hash:\s*`?([^`\s]+)`?", text, flags=re.MULTILINE)
    elif suffix == ".html":
        matches = re.findall(r"<meta\s+name=[\"']draftpaper-snapshot-hash[\"']\s+content=[\"']([^\"']+)", text, flags=re.IGNORECASE)
        matches.extend(re.findall(r"data-snapshot-hash=[\"']([^\"']+)", text, flags=re.IGNORECASE))
    else:
        matches = []
    return {str(value).strip() for value in matches if str(value).strip()}


def _audit_snapshot_output_binding(root: Path, expected_snapshot_hash: str) -> dict[str, Any]:
    manifest_path = root / OUTPUT_MANIFEST_RELATIVE_PATH
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "review_required",
            "manifest": OUTPUT_MANIFEST_RELATIVE_PATH,
            "issues": ["missing_output_manifest"],
            "artifacts": [],
        }
    if not isinstance(manifest, dict):
        return {
            "status": "review_required",
            "manifest": OUTPUT_MANIFEST_RELATIVE_PATH,
            "issues": ["invalid_output_manifest"],
            "artifacts": [],
        }
    issues: list[str] = []
    if str(manifest.get("snapshot_hash") or "") != expected_snapshot_hash:
        issues.append("manifest_snapshot_mismatch")
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    if not artifacts:
        issues.append("empty_output_manifest")
    audited: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            issues.append("invalid_manifest_artifact")
            continue
        relative = str(artifact.get("path") or "")
        path = root / relative
        record = {
            "path": relative,
            "exists": path.is_file(),
            "expected_sha256": artifact.get("sha256"),
            "actual_sha256": _file_sha256(path) if path.is_file() else None,
            "snapshot_hash": artifact.get("snapshot_hash"),
            "markers": sorted(_snapshot_markers(path)),
        }
        audited.append(record)
        if not path.is_file():
            issues.append(f"missing_output:{relative}")
            continue
        if artifact.get("sha256") and artifact.get("sha256") != record["actual_sha256"]:
            issues.append(f"output_hash_mismatch:{relative}")
        if str(artifact.get("snapshot_hash") or "") != expected_snapshot_hash:
            issues.append(f"manifest_artifact_snapshot_mismatch:{relative}")
        if path.name != "citation_evidence.csv" and expected_snapshot_hash not in record["markers"]:
            issues.append(f"output_snapshot_marker_mismatch:{relative}")
    return {
        "status": "passed" if not issues else "review_required",
        "manifest": OUTPUT_MANIFEST_RELATIVE_PATH,
        "snapshot_hash": expected_snapshot_hash,
        "artifact_count": len(audited),
        "issues": issues,
        "artifacts": audited,
    }


class _LiteratureIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._header_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._header_cell = tag == "th"

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append(value)
            if self._header_cell:
                self.headers.append(value)
            self._cell = None
            self._header_cell = False
        elif tag == "tr" and self._row is not None:
            if self._row and self._row != self.headers and any(self._row):
                self.rows.append(self._row)
            self._row = None


def _normalized_index_rows(headers: list[str], rows: list[list[str]]) -> list[list[str]]:
    """Align legacy rows that contain an unlabeled serial-number column."""
    normalized: list[list[str]] = []
    for row in rows:
        values = list(row)
        if len(values) == len(headers) + 1 and re.fullmatch(r"\d+", values[0].strip()):
            values = values[1:]
        normalized.append(values)
    return normalized


def parse_literature_index(path: Path) -> dict[str, Any]:
    """Parse a literature index without writing to the project."""
    if not path.is_file():
        return {"status": "missing", "headers": [], "rows": []}
    parser = _LiteratureIndexParser()
    try:
        parser.feed(path.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return {"status": "unreadable", "headers": [], "rows": []}
    return {
        "status": "parsed",
        "headers": parser.headers,
        "rows": _normalized_index_rows(parser.headers, parser.rows),
    }


def _audit_index(path: Path) -> dict[str, Any]:
    parsed = parse_literature_index(path)
    if parsed["status"] != "parsed":
        return {**parsed, "row_count": 0, "score_zero_counts": {}, "parser_status_counts": {}}
    headers = parsed["headers"]
    rows = parsed["rows"]
    header_map = {value.casefold(): index for index, value in enumerate(headers)}
    score_zero_counts: dict[str, int] = {}
    for key in ("citation weight", "relevance", "journal authority"):
        index = header_map.get(key)
        if index is not None:
            score_zero_counts[key] = sum(1 for row in rows if index < len(row) and row[index] in {"0", "0.0"})
    parser_counts: dict[str, int] = {}
    parser_index = header_map.get("pdf/parser")
    if parser_index is not None:
        for row in rows:
            if parser_index < len(row):
                parser_counts[row[parser_index]] = parser_counts.get(row[parser_index], 0) + 1
    return {
        "status": "parsed",
        "row_count": len(rows),
        "headers": headers,
        "score_zero_counts": score_zero_counts,
        "parser_status_counts": parser_counts,
    }


def _scan_fulltext_orphans(root: Path, active_work_ids: set[str], active_identifiers: set[str]) -> list[dict[str, Any]]:
    fulltext_root = root / "references" / "fulltext"
    if not fulltext_root.is_dir():
        return []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(fulltext_root.rglob("*.json")):
        payload = _json_payload(path)
        work_ids = _artifact_work_ids(payload)
        identifiers = _artifact_identifiers(payload)
        matched = bool(work_ids & active_work_ids or identifiers & active_identifiers)
        if matched:
            status = "active_bound"
        else:
            status = "foreign_project_suspected" if payload is not None else "unresolved"
        artifacts.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": _file_sha256(path),
            "status": status,
            "work_ids": sorted(work_ids),
            "identifiers": sorted(identifiers),
            "match_count": len((work_ids & active_work_ids) | (identifiers & active_identifiers)),
        })
    return artifacts


def audit_literature_integrity(project: str | Path, *, output: str | Path | None = None) -> dict[str, Any]:
    state = load_project(project)
    items = _load_existing_literature_items(state.path / "references")
    snapshot_payload = _json_payload(state.path / "references" / "literature_snapshot.json")
    snapshot_hash = str(snapshot_payload.get("snapshot_hash") or "") if isinstance(snapshot_payload, dict) else ""
    item_work_ids = {canonical_work_id(item) for item in items if canonical_work_id(item)}
    snapshot_work_ids = {
        str(value)
        for value in (snapshot_payload.get("active_work_ids") or snapshot_payload.get("work_ids") or [])
        if str(value).strip()
    } if isinstance(snapshot_payload, dict) else set()
    work_ids = snapshot_work_ids or item_work_ids
    active_items = [item for item in items if not work_ids or canonical_work_id(item) in work_ids]
    identifiers = set().union(*(_item_identifiers(item) for item in active_items)) if active_items else set()
    missing_work = [str(item.get("title") or "") for item in active_items if not canonical_work_id(item) or not item.get("work_id")]
    legacy_zero = [
        {"title": str(item.get("title") or ""), "fields": identify_legacy_zero_scores(item)}
        for item in active_items
        if identify_legacy_zero_scores(item)
    ]
    parse_status: dict[str, int] = {}
    active_fetch_artifacts: list[dict[str, Any]] = []
    for item in active_items:
        for receipt in item.get("document_parses") or []:
            if isinstance(receipt, dict):
                status = str(receipt.get("status") or "unknown")
                parse_status[status] = parse_status.get(status, 0) + 1
        fetch_path_value = str(item.get("paper_fetch_markdown_path") or "")
        if fetch_path_value:
            fetch_path = Path(fetch_path_value)
            if not fetch_path.is_absolute():
                fetch_path = state.path / fetch_path
            exists = fetch_path.is_file()
            actual_hash = _file_sha256(fetch_path) if exists else None
            expected_hash = str(item.get("paper_fetch_output_sha256") or "")
            active_fetch_artifacts.append(
                {
                    "work_id": canonical_work_id(item),
                    "path": fetch_path_value,
                    "exists": exists,
                    "expected_sha256": expected_hash or None,
                    "actual_sha256": actual_hash,
                    "identity_status": item.get("identity_resolution_status"),
                    "postfetch_state": item.get("postfetch_state"),
                    "reachable": bool(exists and (not expected_hash or expected_hash == actual_hash)),
                }
            )
    orphan_artifacts = _scan_fulltext_orphans(state.path, work_ids, identifiers)
    index_report = _audit_index(state.path / "references" / "literature_summaries" / "index.html")
    snapshot_binding = _audit_snapshot_output_binding(state.path, snapshot_hash) if snapshot_hash else {
        "status": "review_required",
        "manifest": OUTPUT_MANIFEST_RELATIVE_PATH,
        "issues": ["missing_snapshot_hash"],
        "artifacts": [],
    }
    issues: list[str] = []
    if missing_work:
        issues.append("missing_work_id")
    if legacy_zero:
        issues.append("legacy_zero_ambiguous")
    if any(value["status"] in {"foreign_project_suspected", "unresolved"} for value in orphan_artifacts):
        issues.append("orphan_fulltext_artifacts")
    if index_report.get("status") == "parsed" and index_report.get("row_count") != len(items):
        issues.append("index_item_count_mismatch")
    if snapshot_binding.get("status") != "passed":
        issues.extend(str(value) for value in snapshot_binding.get("issues") or [])
    if any(not artifact["reachable"] for artifact in active_fetch_artifacts):
        issues.append("active_fetch_artifact_unreachable")
    if any(str(artifact.get("path") or "").startswith("references/quarantine/") for artifact in active_fetch_artifacts):
        issues.append("quarantine_artifact_referenced_by_active_snapshot")
    report = {
        "schema_version": "dpl.literature_integrity_report.v1",
        "status": "passed" if not issues else "review_required",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_path": str(state.path),
        "index_path": "references/literature_summaries/index.html",
        "active_work_count": len(work_ids),
        "active_item_count": len(active_items),
        "missing_work_id_count": len(missing_work),
        "missing_work_titles": missing_work,
        "score_state_counts": score_state_counts(active_items),
        "legacy_zero_records": legacy_zero,
        "parse_status_counts": parse_status,
        "index_report": index_report,
        "snapshot_binding": snapshot_binding,
        "orphan_artifacts": orphan_artifacts,
        "active_fetch_artifacts": active_fetch_artifacts,
        "orphan_count": len([value for value in orphan_artifacts if value["status"] != "active_bound"]),
        "issues": issues,
    }
    report_path = Path(output) if output else state.path / REPORT_RELATIVE_PATH
    if not report_path.is_absolute():
        report_path = state.path / report_path
    _write_json(report_path, report)
    orphan_path = state.path / ORPHAN_REPORT_RELATIVE_PATH if output is None else report_path.with_name("orphan_literature_artifacts.json")
    _write_json(orphan_path, {
        "schema_version": "dpl.orphan_literature_artifact_report.v1",
        "source_report": REPORT_RELATIVE_PATH,
        "artifacts": orphan_artifacts,
    })
    report_locator = report_path.relative_to(state.path).as_posix() if state.path in report_path.parents else str(report_path)
    orphan_locator = orphan_path.relative_to(state.path).as_posix() if state.path in orphan_path.parents else str(orphan_path)
    return {
        "status": report["status"],
        "report": report_locator,
        "orphan_report": orphan_locator,
        "active_work_count": len(work_ids),
        "orphan_count": report["orphan_count"],
        "snapshot_binding": snapshot_binding,
        "issues": issues,
    }


def quarantine_orphan_literature_artifacts(project: str | Path, *, report: str | Path | None = None) -> dict[str, Any]:
    state = load_project(project)
    source_report = state.path / (report or REPORT_RELATIVE_PATH)
    payload = _json_payload(source_report)
    if not isinstance(payload, dict):
        raise ValueError("A literature integrity report is required before quarantine.")
    artifacts = [item for item in payload.get("orphan_artifacts") or [] if isinstance(item, dict) and item.get("status") != "active_bound"]
    quarantine_root = state.path / "references" / "quarantine" / "orphan_fulltext"
    moved: list[dict[str, Any]] = []
    for artifact in artifacts:
        source = state.path / str(artifact.get("path") or "")
        if not source.is_file() or state.path not in source.resolve().parents:
            continue
        expected_hash = str(artifact.get("sha256") or "")
        if expected_hash and _file_sha256(source) != expected_hash:
            raise ValueError(f"Orphan artifact changed after audit: {artifact.get('path')}")
        target = quarantine_root / str(artifact.get("sha256") or "unknown").removeprefix("sha256:")[:32] / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        moved.append({"from": artifact["path"], "to": target.relative_to(state.path).as_posix(), "sha256": artifact.get("sha256"), "status": artifact.get("status")})
    receipt = {
        "schema_version": "dpl.orphan_quarantine_receipt.v1",
        "status": "applied",
        "source_report": source_report.relative_to(state.path).as_posix(),
        "moved": moved,
        "rollback_available": True,
    }
    receipt_path = state.path / "references" / "orphan_quarantine_receipt.json"
    _write_json(receipt_path, receipt)
    return {"status": "applied", "receipt": receipt_path.relative_to(state.path).as_posix(), "moved_count": len(moved)}


def preview_orphan_literature_quarantine(project: str | Path, *, report: str | Path | None = None) -> dict[str, Any]:
    """Create a non-destructive, hash-bound orphan quarantine packet."""
    state = load_project(project)
    source_report = state.path / (report or REPORT_RELATIVE_PATH)
    payload = _json_payload(source_report)
    if not isinstance(payload, dict):
        raise ValueError("A literature integrity report is required before quarantine preview.")
    artifacts = [
        item
        for item in payload.get("orphan_artifacts") or []
        if isinstance(item, dict) and item.get("status") != "active_bound"
    ]
    packet = {
        "schema_version": "dpl.literature_quarantine_record.v1",
        "status": "preview",
        "operation": "orphan_fulltext_quarantine",
        "source_report": source_report.relative_to(state.path).as_posix(),
        "source_report_sha256": _file_sha256(source_report),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "apply_requires_packet_hash": True,
    }
    packet["packet_hash"] = _canonical_hash(packet)
    preview_path = state.path / "references" / "orphan_quarantine_preview.json"
    _write_json(preview_path, packet)
    return {
        "status": "preview",
        "preview": preview_path.relative_to(state.path).as_posix(),
        "packet_hash": packet["packet_hash"],
        "artifact_count": len(artifacts),
    }


def manage_orphan_literature_quarantine(
    project: str | Path,
    *,
    report: str | Path | None = None,
    apply: bool = False,
    packet_hash: str | None = None,
) -> dict[str, Any]:
    """Preview by default; apply only after the exact packet hash is supplied."""
    if not apply:
        return preview_orphan_literature_quarantine(project, report=report)
    state = load_project(project)
    preview_path = state.path / "references" / "orphan_quarantine_preview.json"
    preview = _json_payload(preview_path)
    if not isinstance(preview, dict) or preview.get("status") != "preview":
        raise ValueError("Create an orphan quarantine preview before apply.")
    if not packet_hash or packet_hash != preview.get("packet_hash"):
        raise ValueError("The orphan quarantine packet hash is missing or stale.")
    source_report = state.path / str(preview.get("source_report") or "")
    if not source_report.is_file() or _file_sha256(source_report) != preview.get("source_report_sha256"):
        raise ValueError("The literature integrity report changed after preview.")
    result = quarantine_orphan_literature_artifacts(project, report=preview.get("source_report"))
    receipt_path = state.path / str(result["receipt"])
    receipt = _json_payload(receipt_path)
    if isinstance(receipt, dict):
        receipt.update(
            {
                "packet_hash": packet_hash,
                "preview": preview_path.relative_to(state.path).as_posix(),
                "source_report_sha256": preview.get("source_report_sha256"),
            }
        )
        _write_json(receipt_path, receipt)
    return {**result, "packet_hash": packet_hash}


def rollback_orphan_literature_quarantine(project: str | Path, *, receipt: str | Path | None = None) -> dict[str, Any]:
    """Restore one orphan quarantine transaction after hash verification."""
    state = load_project(project)
    receipt_path = state.path / (receipt or "references/orphan_quarantine_receipt.json")
    payload = _json_payload(receipt_path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "dpl.orphan_quarantine_receipt.v1":
        raise ValueError("An orphan quarantine receipt is required before rollback.")
    if payload.get("status") == "rolled_back":
        return {"status": "already_rolled_back", "receipt": receipt_path.relative_to(state.path).as_posix(), "restored_count": 0}
    restored: list[dict[str, Any]] = []
    for moved in payload.get("moved") or []:
        if not isinstance(moved, dict):
            continue
        source = state.path / str(moved.get("to") or "")
        target = state.path / str(moved.get("from") or "")
        if not source.is_file():
            raise ValueError(f"Quarantine rollback source is missing: {moved.get('to')}")
        if target.exists():
            raise ValueError(f"Quarantine rollback would overwrite an existing file: {moved.get('from')}")
        expected = str(moved.get("sha256") or "")
        if expected and _file_sha256(source) != expected:
            raise ValueError(f"Quarantine rollback source hash changed: {moved.get('to')}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        restored.append({"from": moved.get("to"), "to": moved.get("from"), "sha256": expected})
    payload = {
        **payload,
        "status": "rolled_back",
        "restored": restored,
        "rolled_back_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(receipt_path, payload)
    rollback_path = receipt_path.with_name("orphan_quarantine_rollback_receipt.json")
    _write_json(rollback_path, payload)
    return {
        "status": "rolled_back",
        "receipt": receipt_path.relative_to(state.path).as_posix(),
        "rollback_receipt": rollback_path.relative_to(state.path).as_posix(),
        "restored_count": len(restored),
    }
