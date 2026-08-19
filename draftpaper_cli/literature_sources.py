"""Project-scoped literature source registration and local-file ingestion.

The source registry is deliberately separate from the ranked manuscript
selection. User-curated Zotero and local sources remain in the project
registry even when they are not selected for automatic citation.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project
from .references import enrich_pdf_text


SOURCE_REGISTRY = "references/literature_source_registry.json"
SUPPORTED_LOCAL_SUFFIXES = {".pdf", ".bib", ".ris", ".enw", ".json"}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_metadata(path: Path, root: Path, *, parser: str = "local_import") -> dict[str, Any]:
    stat = path.stat()
    metadata: dict[str, Any] = {
        "local_file_id": _file_hash(path),
        "local_logical_path": path.relative_to(root).as_posix(),
        "local_file_size": stat.st_size,
        "local_file_mtime_ns": stat.st_mtime_ns,
        "local_mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "local_parser": parser,
    }
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader

            metadata["local_page_count"] = len(PdfReader(str(path)).pages)
            metadata["local_parser_version"] = "pypdf"
        except Exception:
            metadata["local_page_count"] = None
            metadata["local_parser_version"] = "pypdf_unavailable_or_invalid"
    return metadata


def _read_registry(root: Path) -> dict[str, Any]:
    path = root / SOURCE_REGISTRY
    if not path.exists():
        return {"schema_version": "dpl.literature_source_registry.v1", "sources": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Literature source registry must be a JSON object.")
    payload.setdefault("schema_version", "dpl.literature_source_registry.v1")
    payload.setdefault("sources", [])
    return payload


def _write_registry(root: Path, payload: dict[str, Any]) -> Path:
    path = root / SOURCE_REGISTRY
    _write_json(path, payload)
    return path


def register_literature_source(
    project: str | Path,
    *,
    source_type: str,
    path: str | Path,
    context: str = "all",
    recursive: bool = True,
    copy_attachments: bool = False,
) -> dict[str, Any]:
    """Register a user-controlled source without copying its contents by default."""
    state = load_project(project)
    source_type = str(source_type).replace("-", "_").strip().lower()
    source_path = Path(path).expanduser().resolve()
    if source_type not in {"local_folder", "structured_file"}:
        raise ValueError("source_type must be local_folder or structured_file")
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if source_type == "local_folder" and not source_path.is_dir():
        raise ValueError("local_folder source must point to a directory")
    if source_type == "structured_file" and not source_path.is_file():
        raise ValueError("structured_file source must point to a file")
    identity = _sha256_text(f"{source_type}\0{source_path}")
    registry = _read_registry(state.path)
    sources = [item for item in registry.get("sources") or [] if isinstance(item, dict)]
    existing = next((item for item in sources if item.get("source_id") == identity), None)
    record = {
        "source_id": identity,
        "source_type": source_type,
        "path": str(source_path),
        "context": context,
        "recursive": bool(recursive),
        "copy_attachments": bool(copy_attachments),
        "retention_policy": "user_curated_preserve",
        "registered_at": existing.get("registered_at") if existing else None,
    }
    if existing:
        sources = [record if item.get("source_id") == identity else item for item in sources]
        status = "updated"
    else:
        sources.append(record)
        status = "registered"
    registry["sources"] = sources
    registry["source_count"] = len(sources)
    registry_path = _write_registry(state.path, registry)
    return {"status": status, "source": record, "path": registry_path.relative_to(state.path).as_posix()}


def list_literature_sources(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    registry = _read_registry(state.path)
    safe_sources = []
    for source in registry.get("sources") or []:
        item = dict(source)
        item["path"] = "<registered-local-source>"
        safe_sources.append(item)
    return {"status": "listed", "sources": safe_sources, "path": SOURCE_REGISTRY}


def _first_title(text: str, fallback: str) -> str:
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" #-\t")
        if len(line) >= 12 and not re.match(r"^(abstract|introduction|references?)\b", line, flags=re.I):
            return line[:300]
    return fallback


def _identifiers(text: str) -> tuple[str, str]:
    doi = ""
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", text or "", flags=re.I)
    if match:
        doi = match.group(0).rstrip(".,;)")
    arxiv = ""
    match = re.search(r"(?:arXiv:\s*|arxiv\.org/abs/)(\d{4}\.\d{4,5}(?:v\d+)?)", text or "", flags=re.I)
    if match:
        arxiv = match.group(1)
    return doi, arxiv


def _sidecar_metadata(pdf: Path) -> dict[str, Any]:
    for suffix in (".json", ".metadata.json"):
        candidate = pdf.with_suffix(suffix) if suffix == ".json" else pdf.with_name(pdf.stem + suffix)
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _local_pdf_item(
    pdf: Path,
    root: Path,
    context: str,
    source_id: str,
    *,
    attachment_path: Path | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    metadata = _sidecar_metadata(pdf)
    file_metadata = _file_metadata(pdf, root, parser="pypdf_quick_read")
    item: dict[str, Any] = {
        "title": metadata.get("title") or pdf.stem.replace("_", " ").replace("-", " "),
        "authors": metadata.get("authors") or [],
        "year": metadata.get("year") or "",
        "doi": metadata.get("doi") or "",
        "url": metadata.get("url") or "",
        "abstract": metadata.get("abstract") or "",
        "publication": metadata.get("publication") or metadata.get("venue") or "",
        "source": "local_folder",
        "source_type": "local_import",
        "reference_origin": "local_import",
        "selection_policy": "user_curated_preserve",
        "user_confirmed": True,
        "retained": True,
        "current_project_use": "retain_only",
        "search_context": context if context != "all" else "idea",
        "search_contexts": ["idea", "data", "methods"] if context == "all" else [context],
        **file_metadata,
        "local_document_id": file_metadata["local_file_id"],
        "local_source_id": source_id,
        "local_mime": mimetypes.guess_type(pdf.name)[0] or "application/pdf",
        "source_records": [{
            "source_type": "local_import",
            "source_id": source_id,
            "file_id": file_metadata["local_file_id"],
            "logical_locator": file_metadata["local_logical_path"],
            "size": file_metadata["local_file_size"],
            "mtime_ns": file_metadata["local_file_mtime_ns"],
            "page_count": file_metadata.get("local_page_count"),
            "parser": file_metadata["local_parser"],
            "retention_policy": "user_curated_preserve",
        }],
        "field_provenance": {
            "title": "local_sidecar_or_pdf",
            "authors": "local_sidecar_or_pdf",
            "year": "local_sidecar_or_pdf",
            "doi": "local_sidecar_or_pdf",
            "abstract": "local_sidecar_or_pdf",
        },
        "pdf_path": str(attachment_path or pdf),
    }
    if attachment_path is not None and project_root is not None:
        item["local_attachment_path"] = attachment_path.relative_to(project_root).as_posix()
    enriched = enrich_pdf_text(item)
    excerpt = str(enriched.get("pdf_text_excerpt") or "")
    if not metadata.get("title"):
        enriched["title"] = _first_title(excerpt, item["title"])
    doi, arxiv = _identifiers(" ".join([excerpt, str(metadata)]))
    enriched["doi"] = str(metadata.get("doi") or doi)
    if arxiv:
        enriched["arxiv_id"] = arxiv
        enriched["url"] = enriched.get("url") or f"https://arxiv.org/abs/{arxiv}"
    enriched.pop("pdf_path", None)
    enriched["pdf_read_status"] = enriched.get("pdf_read_status") or "metadata_only"
    enriched["parser_state"] = "quick_read_unbound" if enriched.get("pdf_text_excerpt") else "registered"
    enriched["binding_status"] = "identity_pending"
    return enriched


def collect_local_folder_source(source: dict[str, Any], *, project_root: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = Path(str(source.get("path") or "")).expanduser().resolve()
    if not root.is_dir():
        return [], {"source_id": source.get("source_id"), "status": "missing", "path": "<missing>"}
    pattern = "**/*" if source.get("recursive", True) else "*"
    files = [path for path in root.glob(pattern) if path.is_file() and path.suffix.lower() == ".pdf"]
    items = []
    attachment_root = None
    if source.get("copy_attachments") and project_root is not None:
        attachment_root = project_root / "references" / "local_attachments" / str(source.get("source_id") or "unknown")[:16]
        attachment_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(files):
        attachment_path = None
        if attachment_root is not None:
            attachment_path = attachment_root / f"{_file_hash(path)}{path.suffix.lower()}"
            if not attachment_path.exists():
                shutil.copy2(path, attachment_path)
        items.append(
            _local_pdf_item(
                path,
                root,
                str(source.get("context") or "all"),
                str(source.get("source_id") or ""),
                attachment_path=attachment_path,
                project_root=project_root,
            )
        )
    report = {
        "source_id": source.get("source_id"),
        "status": "loaded",
        "file_count": len(files),
        "parsed_count": sum(1 for item in items if item.get("pdf_text_excerpt")),
        "metadata_complete_count": sum(1 for item in items if item.get("doi") or item.get("authors")),
        "source_root_hash": _sha256_text(str(root)),
    }
    return items, report


def collect_registered_local_sources(project: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return collect_registered_sources(project)


def _structured_item_to_reference(item: dict[str, Any], *, source: dict[str, Any], locator: str) -> dict[str, Any]:
    """Convert a local BibTeX/RIS/JSON record without discarding its origin."""
    source_id = str(source.get("source_id") or "")
    source_path = Path(str(source.get("path") or "")).expanduser().resolve()
    file_metadata = _file_metadata(source_path, source_path.parent, parser=f"structured_{source_path.suffix.lower().lstrip('.')}") if source_path.is_file() else {}
    title = " ".join(str(item.get("title") or item.get("TITLE") or "").split())
    authors = item.get("authors") or item.get("author") or []
    if isinstance(authors, str):
        authors = [part.strip() for part in re.split(r"\s+and\s+|;|\n", authors) if part.strip()]
    if not isinstance(authors, list):
        authors = []
    result = dict(item)
    result.update(
        {
            "title": title or Path(locator).stem,
            "authors": [str(author).strip() for author in authors if str(author).strip()],
            "year": item.get("year") or item.get("date") or item.get("PY") or "",
            "doi": str(item.get("doi") or item.get("DOI") or "").strip(),
            "pmid": str(item.get("pmid") or item.get("PMID") or "").strip(),
            "pmcid": str(item.get("pmcid") or item.get("PMCID") or "").strip(),
            "arxiv_id": str(item.get("arxiv_id") or item.get("arXiv") or "").strip(),
            "bibcode": str(item.get("bibcode") or item.get("BIBCODE") or "").strip(),
            "url": str(item.get("url") or item.get("URL") or "").strip(),
            "publication": str(item.get("publication") or item.get("journal") or item.get("JO") or item.get("venue") or "").strip(),
            "source": "local_file",
            "source_type": "local_import",
            "reference_origin": "local_import",
            "selection_policy": "user_curated_preserve",
            "user_confirmed": True,
            "retained": True,
            "current_project_use": "retain_only",
            "local_source_id": source_id,
            **file_metadata,
            "local_logical_path": locator,
            "source_records": [
                {
                    "source_type": "local_import",
                    "source_id": source_id,
                    "file_id": file_metadata.get("local_file_id"),
                    "logical_locator": locator,
                    "format": Path(locator).suffix.lower().lstrip("."),
                    "size": file_metadata.get("local_file_size"),
                    "mtime_ns": file_metadata.get("local_file_mtime_ns"),
                    "parser": file_metadata.get("local_parser"),
                    "retention_policy": "user_curated_preserve",
                }
            ],
        }
    )
    return result


def _parse_structured_file(path: Path, source: dict[str, Any]) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return []
        raw_items = payload.get("items", payload) if isinstance(payload, dict) else payload
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        return [
            _structured_item_to_reference(item, source=source, locator=path.name)
            for item in (raw_items or [])
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ]
    if suffix == ".bib":
        try:
            import bibtexparser

            database = bibtexparser.loads(path.read_text(encoding="utf-8-sig"))
            entries = database.entries
        except Exception:
            entries = []
        return [
            _structured_item_to_reference(entry, source=source, locator=path.name)
            for entry in entries
            if isinstance(entry, dict) and str(entry.get("title") or "").strip()
        ]
    if suffix in {".ris", ".enw"}:
        records: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        authors: list[str] = []
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            lines = []
        for raw_line in lines + ["TY  - END"]:
            line = raw_line.strip()
            if not line or len(line) < 6 or "  - " not in line:
                continue
            tag, value = line.split("  - ", 1)
            tag = tag.strip().upper()
            value = value.strip()
            if tag == "TY" and current:
                current["authors"] = authors
                if current.get("title"):
                    records.append(_structured_item_to_reference(current, source=source, locator=path.name))
                current = {}
                authors = []
            if tag in {"ER", "END"}:
                continue
            if tag in {"AU", "A1", "A2"}:
                authors.append(value)
            elif tag in {"TI", "T1", "CT"}:
                current["title"] = value
            elif tag in {"PY", "Y1", "DA"}:
                current["year"] = value
            elif tag in {"DO", "DOI"}:
                current["doi"] = value
            elif tag in {"JO", "T2", "JF", "JA"}:
                current["publication"] = value
            elif tag in {"UR", "L1"}:
                current["url"] = value
            elif tag in {"AB", "N2"}:
                current["abstract"] = value
        return records
    return []


def collect_registered_sources(project: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collect all registered local folders/files into an analysis-only ledger."""
    state = load_project(project)
    registry = _read_registry(state.path)
    items: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for source in registry.get("sources") or []:
        if not isinstance(source, dict):
            continue
        if source.get("source_type") == "local_folder":
            source_items, report = collect_local_folder_source(source, project_root=state.path)
        elif source.get("source_type") == "structured_file":
            path = Path(str(source.get("path") or "")).expanduser().resolve()
            source_items = _parse_structured_file(path, source) if path.is_file() else []
            report = {
                "source_id": source.get("source_id"),
                "status": "loaded" if path.is_file() else "missing",
                "file_count": 1 if path.is_file() else 0,
                "item_count": len(source_items),
                "logical_path": path.name if path.is_file() else "<missing>",
            }
        else:
            continue
        items.extend(source_items)
        reports.append(report)
    return items, {"status": "loaded", "source_reports": reports, "item_count": len(items)}


def _registered_pdf_paths(project: str | Path) -> list[Path]:
    """Return registered PDF inputs for the parser stage without exposing paths in reports."""
    state = load_project(project)
    registry = _read_registry(state.path)
    paths: list[Path] = []
    for source in registry.get("sources") or []:
        if not isinstance(source, dict) or source.get("source_type") != "local_folder":
            continue
        root = Path(str(source.get("path") or "")).expanduser().resolve()
        if not root.is_dir():
            continue
        pattern = "**/*" if source.get("recursive", True) else "*"
        paths.extend(path for path in root.glob(pattern) if path.is_file() and path.suffix.lower() == ".pdf")
    return sorted(set(paths))


def collect_literature_sources(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    items, report = collect_registered_sources(project)
    output = state.path / "references" / "literature_source_collection.json"
    _write_json(output, report)
    return {
        "status": "collected",
        "project_path": str(state.path),
        "item_count": len(items),
        "source_reports": report.get("source_reports", []),
        "output": "references/literature_source_collection.json",
    }


def reconcile_literature_sources(project: str | Path) -> dict[str, Any]:
    """Merge registered local records with the current registry without live search."""
    state = load_project(project)
    local_items, report = collect_registered_sources(project)
    existing_path = state.path / "references" / "literature_items.json"
    existing: list[dict[str, Any]] = []
    if existing_path.is_file():
        try:
            payload = json.loads(existing_path.read_text(encoding="utf-8-sig"))
            existing = payload.get("items", payload) if isinstance(payload, dict) else payload
        except (OSError, json.JSONDecodeError):
            existing = []
    from .references import write_reference_outputs

    result = write_reference_outputs(
        state.path,
        [*(existing if isinstance(existing, list) else []), *local_items],
        query=str(state.metadata.get("idea") or ""),
        search_queries={"mode": "reconcile_local_sources", "merge_mode": "augment", "local_source_collection": report},
    )
    parse_results: list[dict[str, Any]] = []
    current_items_path = state.path / "references" / "literature_items.json"
    try:
        current_items = json.loads(current_items_path.read_text(encoding="utf-8-sig")) if current_items_path.is_file() else []
    except (OSError, json.JSONDecodeError):
        current_items = []
    current_items = current_items if isinstance(current_items, list) else current_items.get("items", []) if isinstance(current_items, dict) else []
    by_file_id = {str(item.get("local_file_id") or ""): item for item in current_items if isinstance(item, dict) and item.get("local_file_id")}
    from .mineru_adapter import parse_literature_document

    for pdf_path in _registered_pdf_paths(state.path):
        file_id = _file_hash(pdf_path)
        matched = by_file_id.get(file_id)
        try:
            parsed = parse_literature_document(
                state.path,
                pdf_path,
                use_mineru=True,
                parser="auto",
                purpose="evidence",
                work_id=str(matched.get("work_id") or "") if matched else None,
            )
            parse_results.append({"path": pdf_path.name, "status": parsed.get("status"), "binding": parsed.get("binding")})
        except (OSError, ValueError) as exc:
            parse_results.append({"path": pdf_path.name, "status": "failed", "error": str(exc)})
    result["reconciliation"] = "local_sources_merged_without_live_search"
    result["document_parse_results"] = parse_results
    return result


def parse_registered_literature_documents(project: str | Path, *, use_mineru: bool = True, timeout_seconds: int = 600) -> dict[str, Any]:
    """Parse every registered PDF independently with resumable per-file receipts."""
    state = load_project(project)
    items_path = state.path / "references" / "literature_items.json"
    try:
        payload = json.loads(items_path.read_text(encoding="utf-8-sig")) if items_path.is_file() else []
    except (OSError, json.JSONDecodeError):
        payload = []
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    items = items if isinstance(items, list) else []
    by_file_id = {
        str(item.get("local_file_id")): item
        for item in items
        if isinstance(item, dict) and item.get("local_file_id")
    }
    from .mineru_adapter import parse_literature_document

    results: list[dict[str, Any]] = []
    for pdf_path in _registered_pdf_paths(state.path):
        file_id = _file_hash(pdf_path)
        matched = by_file_id.get(file_id)
        try:
            parsed = parse_literature_document(
                state.path,
                pdf_path,
                use_mineru=use_mineru,
                parser="auto",
                purpose="evidence",
                timeout_seconds=timeout_seconds,
                work_id=str(matched.get("work_id") or "") if matched else None,
            )
            results.append({
                "file_id": file_id,
                "name": pdf_path.name,
                "status": parsed.get("status"),
                "cache_hit": bool((parsed.get("receipt") or {}).get("cache_hit")),
                "binding": parsed.get("binding"),
            })
        except Exception as exc:
            # A single invalid or unreadable PDF becomes a resumable record;
            # it must not invalidate successful documents in the same batch.
            results.append({"file_id": file_id, "name": pdf_path.name, "status": "failed", "error_type": type(exc).__name__, "error": str(exc)})
    counts: dict[str, int] = {}
    for result in results:
        status = str(result.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    report = {
        "schema_version": "dpl.document_parse_batch_report.v1",
        "status": "completed_with_failures" if counts.get("failed") else "completed",
        "document_count": len(results),
        "status_counts": counts,
        "results": results,
    }
    _write_json(state.path / "references" / "document_parse_batch_report.json", report)
    return {"status": report["status"], "document_count": len(results), "status_counts": counts, "report": "references/document_parse_batch_report.json"}
